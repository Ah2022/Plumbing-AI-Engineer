"""
calculations/water.py
------------------------
Cold water demand + pipe-sizing/velocity-check engine.

Phase 2 update: check_velocity_limit() now reads a REAL numeric limit
via database/design_table_api.py instead of the placeholder lookup —
backed by the design-table data loaded from database/code_design_data/.

Where a code has no stated value (a documented gap — e.g. SAUDI_SBC_701
has no explicit numeric velocity ceiling), the caller may opt into an
explicit, logged fallback to another code (see design_table_api's
FALLBACK POLICY). The result is always tagged so the report shows
exactly what was used and from where — never a silent substitution.
"""

from __future__ import annotations

from calculations.validation import finite

import math

from calculations.hydraulics import velocity_from_flow
from database.design_table_api import (
    get_velocity_limit, get_table_records, get_demand_from_wsfu, get_min_pipe_size,
)
from models import CalculationResult, MissingCodeDataError

# Confirmed by Ahmed (2026-09): clinical sinks, bedpan washers, and autopsy
# tables are NOT separately-rated fixtures under IPC Section 713.2 or
# SBC 701-2007 Section 2.22.6 (both fetched and confirmed directly) -- they
# are rated as a water closet for fixture-unit purposes. A candidate table
# assigning them distinct values ("bedpan washer=10, clinical sink=6") was
# checked against these sections and found inconsistent -- explicitly not
# merged. Hospital fixture names below resolve to "Water closet" instead of
# requiring their own fixture-table row.
HOSPITAL_FIXTURE_ALIASES = {
    "clinical sink": "water closet",
    "bedpan washer": "water closet",
    "bedpan sanitizer": "water closet",
    "autopsy table": "water closet",
}


def check_velocity_limit(conn, project_id: int, code_id: str, pipe_id: str,
                          flow_lps: float, internal_diameter_mm: float, calc_id: str,
                          velocity_kind: str = "recommended_design",
                          allow_fallback_code: str = None,
                          material: str = None) -> CalculationResult:
    """Compute pipe velocity and check it against a real code- or manufacturer-sourced velocity limit.

    If `material` is given (e.g. "PPR"), a manufacturer-confirmed material-specific
    limit is checked first and takes precedence over the code's generic table."""
    v_result = velocity_from_flow(flow_lps, internal_diameter_mm, calc_id)

    limit = get_velocity_limit(conn, code_id, kind=velocity_kind,
                                allow_fallback_code=allow_fallback_code, material=material)
    if limit is None:
        raise MissingCodeDataError(
            what=f"Velocity limit ({velocity_kind}) for cold water distribution",
            where=f"code={code_id} — no value in design_table_values; "
                  f"set allow_fallback_code to permit an explicit cross-code fallback",
        )

    finite('velocity limit',limit.value,positive=True)

    status = "PASS" if v_result.result_value <= limit.value else "FAIL"
    if limit.confidence == "FLAGGED":
        status = status if status == "FAIL" else "WARNING"  # a borrowed/flagged limit can PASS but must WARN

    v_result.calc_type = "cold_water_velocity_check"
    v_result.required_value = limit.value
    v_result.selected_value = v_result.result_value
    v_result.status = status
    v_result.reference = f"{limit.code_id}:{limit.table_reference}" + (
        f" (fallback from {limit.fallback_from})" if limit.fallback_from else ""
    )
    v_result.notes = limit.notes
    return v_result


def total_fixture_units(conn, code_id: str, fixtures: list[dict]) -> dict:
    """
    Sum cold-water fixture units across a fixture list.

    Each fixture dict may either:
      (a) carry "wsfu_value" already (set when picked from a real dropdown
          choice via database.design_table_api.list_water_fixture_unit_choices
          -- the exact table row is already known, so no re-lookup happens), or
      (b) be free-text ("fixture_name"/"occupancy"/"control") for backward
          compatibility, matched against the code's own table as before.

    fixtures: [{"fixture_name": "Water closet", "occupancy": "Public",
                "control": "Flushometer valve", "quantity": 40}, ...]
             or [{"fixture_name": "...", "quantity": 40, "wsfu_value": 6.0,
                  "confidence": "CONFIRMED"}, ...]
    """
    for f in fixtures:
        finite('quantity',f.get('quantity'),minimum=0)
        if f.get('wsfu_value') is not None: finite('wsfu_value',f['wsfu_value'],minimum=0)
    records = get_table_records(conn, code_id, "water", "1_Fixture_Units")
    total = 0.0
    missing = []
    matched_confidence = []

    for f in fixtures:
        if f.get("wsfu_value") is not None:
            total += f["wsfu_value"] * f["quantity"]
            matched_confidence.append(f.get("confidence", "CONFIRMED"))
            continue
        rec = _match_fixture(records, f)
        if rec is None:
            missing.append(f["fixture_name"])
            continue
        cold_fu = rec.get("cold", (None, None, None))[0]
        if cold_fu is None:
            missing.append(f["fixture_name"])
            continue
        total += cold_fu * f["quantity"]
        matched_confidence.append(rec.get("cold", (None, None, "CONFIRMED"))[2])

    if missing:
        raise MissingCodeDataError(
            what=f"Cold-water fixture-unit value for: {', '.join(sorted(set(missing)))}",
            where=f"code={code_id}, table=1_Fixture_Units",
        )
    return {
        "total_cold_fu": total,
        "confidence": "FLAGGED" if "FLAGGED" in matched_confidence else "CONFIRMED",
    }


def _match_fixture(records: list[dict], fixture: dict):
    name_match = fixture["fixture_name"].lower()
    name_match = HOSPITAL_FIXTURE_ALIASES.get(name_match, name_match)
    for rec in records:
        rec_name = str(rec.get("fixture", (None, None, None))[1] or "").lower()
        if name_match in rec_name or rec_name in name_match:
            if "occupancy" in fixture:
                rec_occ = str(rec.get("occupancy", (None, None, None))[1] or "").lower()
                if fixture["occupancy"].lower() not in rec_occ:
                    continue
            if "control" in fixture:
                rec_ctl = str(rec.get("control", (None, None, None))[1] or "").lower()
                if fixture["control"].lower() not in rec_ctl:
                    continue
            return rec
    return None


def size_pipe_from_demand(conn, code_id: str, total_wsfu: float, calc_id: str,
                           control_type: str = "flush_tank",
                           material: str = None,
                           fixture_min_size_context: str = None,
                           allow_velocity_fallback_code: str = None) -> CalculationResult:
    """
    Completes the chain: total WSFU -> design flow (Hunter's Curve lookup,
    interpolated) -> required pipe diameter (Q=VA, rearranged, against a
    real code/manufacturer velocity limit) -> checked against the code's
    fixture minimum branch size if fixture_min_size_context is given.

    Returns the REQUIRED internal diameter (mm) as a calculated value, not
    a manufacturer nominal size — no pipe-dimension catalog (nominal vs.
    internal diameter per material/schedule) is loaded yet (see
    docs/ARCHITECTURE.md), so rounding up to an actual orderable pipe size
    is left to the engineer / a future materials-catalog module, not
    invented here. status stays CALCULATED_NOT_APPROVED for that reason.

    control_type: 'flush_tank' | 'flush_valve' -- selects which demand
    column to read (SBC701's real table gives both; flush valve fixtures
    draw a higher instantaneous demand than flush tank fixtures for the
    same WSFU total).
    """
    finite('total_wsfu',total_wsfu,minimum=0)
    if control_type not in ('flush_tank','flush_valve'): raise ValueError('Unsupported demand control type')
    demand_column = "flush_tank_lpm" if control_type == "flush_tank" else "flush_valve_lpm"
    demand = get_demand_from_wsfu(conn, code_id, total_wsfu, demand_column=demand_column)
    if demand is None:
        raise MissingCodeDataError(
            what=f"Design flow for {total_wsfu} WSFU ({control_type})",
            where=f"code={code_id}, table=2_Demand_Conversion — either no table found, or "
                  f"{total_wsfu} WSFU is outside the table's range (no extrapolation performed)",
        )
    demand_lps = demand.value / 60.0

    limit = get_velocity_limit(conn, code_id, kind="recommended_design",
                                allow_fallback_code=allow_velocity_fallback_code, material=material)
    if limit is None:
        raise MissingCodeDataError(
            what="Velocity limit needed to size the pipe from demand flow",
            where=f"code={code_id} — set material= or allow_velocity_fallback_code= to resolve",
        )

    q_m3s = demand_lps / 1000.0
    finite('velocity limit',limit.value,positive=True)
    required_diameter_m = math.sqrt(4 * q_m3s / (math.pi * limit.value))
    required_diameter_mm = required_diameter_m * 1000.0

    floor_note = None
    min_mm = None
    min_confidence = 'CONFIRMED'
    if fixture_min_size_context:
        min_size = get_min_pipe_size(conn, code_id, fixture_min_size_context)
        if min_size is None:
            raise MissingCodeDataError("Fixture minimum connection", f"code={code_id}, fixture={fixture_min_size_context}")
        min_mm = min_size.value * 25.4 if min_size.unit == "in" else min_size.value
        min_confidence = min_size.confidence
        floor_note = (f'Code minimum nominal connection: {min_mm}mm. '
                      'Check this separately against catalogue nominal size; it is not an internal diameter.')

    confidence = "FLAGGED" if 'FLAGGED' in (demand.confidence,limit.confidence,min_confidence) else "CONFIRMED"

    return CalculationResult(
        calc_id=calc_id,
        calc_type="cold_water_pipe_sizing",
        formula="D = sqrt(4*Q / (pi*V_max)),  Q from WSFU via Hunter's Curve (code table)",
        inputs={"total_wsfu": (total_wsfu, "WSFU"), "control_type": (control_type, "-")},
        intermediate={"demand_lpm": demand.value, "demand_lps": round(demand_lps, 4),
                      "velocity_limit_m_s": limit.value,"fixture_min_nominal_mm":min_mm},
        result_value=round(required_diameter_mm, 2),
        result_unit="mm (required internal diameter -- not yet a catalog nominal size)",
        required_value=round(required_diameter_mm,2),
        selected_value=None,
        status="WARNING" if confidence == "FLAGGED" else "CALCULATED_NOT_APPROVED",
        reference=f"{code_id}:2_Demand_Conversion + {limit.code_id}:{limit.table_reference}",
        notes=" | ".join(filter(None, [demand.notes, limit.notes, floor_note])),
    )
