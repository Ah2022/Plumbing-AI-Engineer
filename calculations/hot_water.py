"""
calculations/hot_water.py
----------------------------
Hot water demand + storage sizing (ASPE Table 6-1 methodology, confirmed
by Ahmed as final for SAUDI_SBC_701 and EGYPT_LOCAL since neither code
states its own factors), and temperature checks against IPC's confirmed
hospital-specific figures (docs/ARCHITECTURE.md Section 0b item 4 --
directly relevant to SMC-3).

Demand/storage factor source: referenced in the IPC workbook's own
'9_Hot_Water_Basis' sheet caption ("Hospital-specific hourly demand (ASPE
Table 6-1) -- most relevant to SMC-3 | Demand factor: 0.25 | Storage
capacity factor: 0.6") -- these were captions in the workbook, not table
rows, so they're recorded here explicitly rather than silently assumed.
"""

from __future__ import annotations

from database.design_table_api import get_table_records
from calculations.hydraulics import q_heat
from models import CalculationResult, MissingCodeDataError

# ASPE Table 6-1 hourly demand factor / storage capacity factor -- confirmed
# by Ahmed (2026-09) as the final basis for hospital hot-water sizing where
# a code has no factors of its own (SAUDI_SBC_701, EGYPT_LOCAL).
ASPE_HOSPITAL_DEMAND_FACTOR = 0.25
ASPE_HOSPITAL_STORAGE_CAPACITY_FACTOR = 0.6
ASPE_FACTOR_REFERENCE = "ASPE Table 6-1 (via IPC workbook caption), confirmed final by Ahmed 2026-09"


def hot_water_demand(conn, fixtures: list[dict], calc_id: str,
                      demand_factor: float = ASPE_HOSPITAL_DEMAND_FACTOR,
                      storage_capacity_factor: float = ASPE_HOSPITAL_STORAGE_CAPACITY_FACTOR) -> CalculationResult:
    """
    fixtures: [{"fixture_name": "Showers", "quantity": 20}, ...]

    total_connected_gph = sum(fixture_gph * quantity)
    design_hourly_demand_gph = total_connected_gph * demand_factor
    storage_tank_capacity_gal = design_hourly_demand_gph * storage_capacity_factor

    Uses IPC's real fixture-GPH table (9_Hot_Water_Basis) -- the only code
    with this table loaded; SAUDI_SBC_701/EGYPT_LOCAL have none of their own
    (confirmed gap, Section 0b item 4).
    """
    records = get_table_records(conn, "IPC", "hot_water", "9_Hot_Water_Basis [fixture+gph")
    total_gph = 0.0
    missing = []
    for f in fixtures:
        match = None
        for rec in records:
            name = str(rec.get("fixture", (None, None, None))[1] or "")
            if f["fixture_name"].lower() in name.lower() or name.lower() in f["fixture_name"].lower():
                match = rec
                break
        if match is None:
            missing.append(f["fixture_name"])
            continue
        gph = match.get("gph", (None, None, None))[0]
        if gph is None:
            missing.append(f["fixture_name"])
            continue
        total_gph += gph * f["quantity"]

    if missing:
        raise MissingCodeDataError(
            what=f"Hourly hot-water demand (GPH) for: {', '.join(sorted(set(missing)))}",
            where="code=IPC, table=9_Hot_Water_Basis [fixture+gph]",
        )

    design_hourly_demand_gph = total_gph * demand_factor
    storage_gal = design_hourly_demand_gph * storage_capacity_factor

    return CalculationResult(
        calc_id=calc_id,
        calc_type="hot_water_demand",
        formula="Design hourly demand = sum(fixture_gph * qty) * demand_factor; "
                "Storage capacity = design hourly demand * storage_capacity_factor",
        inputs={"demand_factor": (demand_factor, "-"), "storage_capacity_factor": (storage_capacity_factor, "-")},
        intermediate={"total_connected_demand_gph": total_gph},
        result_value=round(design_hourly_demand_gph, 1),
        result_unit="GPH",
        selected_value=round(storage_gal, 1),
        status="CALCULATED_NOT_APPROVED",
        reference=ASPE_FACTOR_REFERENCE,
        notes=f"Recommended storage tank capacity: {round(storage_gal, 1)} gal "
              f"({round(storage_gal * 3.78541, 1)} L)",
    )


# IPC's confirmed hospital-specific temperature figures -- directly relevant
# to SMC-3 (docs/ARCHITECTURE.md Section 0b item 4).
TEMPERATURE_CHECKS = {
    "scald_protection_patient_areas": {
        "parameter_match": "max hot water discharge",
        "comparison": "max",  # selected_temp must be <= the code value
    },
    "legionella_recirc_minimum": {
        "parameter_match": "recirculating dhw minimum",
        "comparison": "min",  # selected_temp must be >= the code value
    },
    "legionella_storage_minimum": {
        "parameter_match": "stored dhw minimum",
        "comparison": "min",
    },
}


def check_hot_water_temperature(conn, check_type: str, selected_temp_c: float, calc_id: str) -> CalculationResult:
    """check_type: one of TEMPERATURE_CHECKS' keys."""
    if check_type not in TEMPERATURE_CHECKS:
        raise ValueError(f"Unknown check_type '{check_type}'. Valid: {list(TEMPERATURE_CHECKS)}")
    spec = TEMPERATURE_CHECKS[check_type]

    records = get_table_records(conn, "IPC", "hot_water", "9_Hot_Water_Basis [parameter+value+unit+applicability")
    match_text = spec["parameter_match"]
    row = None
    for rec in records:
        param = str(rec.get("parameter", (None, None, None))[1] or "")
        if match_text in param.lower():
            row = rec
            break
    if row is None:
        raise MissingCodeDataError(what=f"Temperature criterion for '{check_type}'", where="code=IPC, table=9_Hot_Water_Basis")

    limit_val, _, confidence = row.get("value", (None, None, "CONFIRMED"))
    applicability = row.get("applicability", (None, None, None))[1]
    if limit_val is None:
        raise MissingCodeDataError(what=f"Numeric temperature value for '{check_type}'", where="code=IPC")

    if spec["comparison"] == "max":
        status = "PASS" if selected_temp_c <= limit_val else "FAIL"
    else:
        status = "PASS" if selected_temp_c >= limit_val else "FAIL"
    if confidence == "FLAGGED" and status == "PASS":
        status = "WARNING"

    return CalculationResult(
        calc_id=calc_id,
        calc_type="hot_water_temperature_check",
        formula=f"selected_temp_c {'<=' if spec['comparison']=='max' else '>='} code limit",
        inputs={"selected_temp_c": (selected_temp_c, "C"), "check_type": (check_type, "-")},
        intermediate={},
        result_value=selected_temp_c,
        result_unit="C",
        required_value=limit_val,
        selected_value=selected_temp_c,
        status=status,
        reference=f"IPC:9_Hot_Water_Basis ({applicability})",
        notes=None if confidence == "CONFIRMED" else "Underlying row is FLAGGED — confirm before sign-off.",
    )


def heater_capacity(mass_flow_kg_s: float, cold_water_temp_c: float, hot_water_temp_c: float, calc_id: str) -> CalculationResult:
    """Wraps hydraulics.q_heat for the specific case of a heater's required duty."""
    cp_water = 4.186  # kJ/kg.C, public-domain physical property of water
    delta_t = hot_water_temp_c - cold_water_temp_c
    result = q_heat(mass_flow_kg_s, cp_water, delta_t, calc_id)
    result.calc_type = "hot_water_heater_capacity"
    result.inputs["cold_water_temp_c"] = (cold_water_temp_c, "C")
    result.inputs["hot_water_temp_c"] = (hot_water_temp_c, "C")
    return result
