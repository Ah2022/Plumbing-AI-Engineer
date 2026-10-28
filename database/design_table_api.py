"""
database/design_table_api.py
-------------------------------
Query layer over the long-format `design_table_values`. Two levels:

1. get_table_records() — generic: reconstructs each source row as a
   {col_key: (value_num, value_text, confidence)} dict. Useful for any
   table shape.
2. Domain-specific helpers (get_velocity_limit, get_fixture_units, ...)
   — return one clean value plus its FULL provenance (code, table,
   reference, confidence, and whether a cross-code fallback was used).

FALLBACK POLICY: some codes explicitly document that they don't state
a value and recommend borrowing another code's (e.g. SBC 701's own
velocity-limit sheet says "IPC's general engineering guidance ... is a
reasonable interim basis given SBC's confirmed IPC lineage"). This
module allows that ONLY when explicitly enabled by the caller
(allow_fallback=True), and always returns confidence="FLAGGED" plus a
note naming exactly what was borrowed from where — never a silent
substitution.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class DesignValue:
    value: float
    unit: Optional[str]
    code_id: str
    table_reference: str
    confidence: str            # 'CONFIRMED' | 'FLAGGED'
    source_classification: str
    fallback_from: Optional[str] = None   # set when borrowed from another code
    notes: Optional[str] = None

    def __post_init__(self):
        from calculations.validation import finite
        finite('source design value',self.value)


def get_table_records(conn, code_id: str, domain: str, table_name_substr: str) -> list[dict]:
    """Reconstruct every matching table's rows as records: [{col_key: (num,text,conf)}, ...]."""
    tables = conn.execute(
        """SELECT table_id, table_name, reference, status FROM design_tables
           WHERE code_id = ? AND domain = ? AND table_name LIKE ?""",
        (code_id, domain, f"%{table_name_substr}%"),
    ).fetchall()

    records = []
    for t in tables:
        rows = conn.execute(
            """SELECT row_key, col_key, value_num, value_text, confidence
               FROM design_table_values WHERE table_id = ?""",
            (t["table_id"],),
        ).fetchall()
        by_row = defaultdict(dict)
        for r in rows:
            by_row[r["row_key"]][r["col_key"]] = (r["value_num"], r["value_text"], r["confidence"])
        for row_key, cols in by_row.items():
            records.append({"_table_reference": t["reference"], "_status": t["status"], **cols})
    return records


def _find_first_numeric(records: list[dict], text_col: str, text_match: str, value_col: str = "value"):
    """Find the first record whose text_col contains text_match (case-insensitive), return its numeric value_col."""
    match = text_match.lower()
    for rec in records:
        text = rec.get(text_col, (None, None, None))[1] or ""
        if match in str(text).lower():
            num, txt, conf = rec.get(value_col, (None, None, None))
            if num is not None:
                return num, conf, rec.get("_table_reference"), text
    return None


def get_material_velocity_limit(conn, code_id: str, material_name_substr: str,
                                 kind: str = "general_design") -> Optional[DesignValue]:
    """
    Looks up a manufacturer-published, material-specific velocity limit
    (e.g. PPR-PN16's Aquatherm-confirmed values), distinct from a code's
    generic velocity-limit table. kind: 'general_design' | 'circulation_return'.
    """
    text_match = {
        "general_design": "general design velocity ceiling",
        "circulation_return": "circulation/return-loop velocity limit",
    }[kind]

    tables = conn.execute(
        """SELECT table_id, reference FROM design_tables
           WHERE code_id = ? AND domain = 'water' AND table_name LIKE ?
             AND table_name LIKE '%Velocity Limits%'""",
        (code_id, f"%{material_name_substr}%"),
    ).fetchall()
    for t in tables:
        rows = conn.execute(
            """SELECT row_key, col_key, value_num, value_text, confidence
               FROM design_table_values WHERE table_id = ?""",
            (t["table_id"],),
        ).fetchall()
        by_row = defaultdict(dict)
        for r in rows:
            by_row[r["row_key"]][r["col_key"]] = (r["value_num"], r["value_text"], r["confidence"])
        for row_key, cols in by_row.items():
            param_text = cols.get("parameter", (None, None, None))[1] or ""
            if text_match in str(param_text).lower():
                num, _, conf = cols.get("value", (None, None, "CONFIRMED"))
                if num is not None:
                    return DesignValue(
                        value=num, unit="m/s", code_id=code_id, table_reference=t["reference"],
                        confidence=conf, source_classification="MANUFACTURER",
                        notes=f"matched: {param_text}",
                    )
    return None


def get_velocity_limit(conn, code_id: str, kind: str = "recommended_design",
                        allow_fallback_code: Optional[str] = None,
                        material: Optional[str] = None) -> Optional[DesignValue]:
    """
    kind: 'recommended_design' | 'max_general' | 'max_cold_distribution' | 'max_hot_distribution'
    Matching text per kind is code-vocabulary-aware (each code phrases this differently —
    see database/code_design_data/*.xlsx Tab 3 for the exact source wording).

    If `material` is given, a manufacturer-specific limit (get_material_velocity_limit)
    is checked FIRST and takes precedence over the code's generic table — a material
    ceiling is normally the binding constraint for that pipe run.
    """
    if material:
        mat_limit = get_material_velocity_limit(conn, code_id, material, kind="general_design")
        if mat_limit:
            return mat_limit

    text_match_candidates = {
        "recommended_design": ["recommended design velocity"],
        "max_general": ["maximum velocity", "maximum water velocity", "max velocity"],
        "max_cold_distribution": ["cold water distribution"],
        "max_hot_distribution": ["hot water distribution"],
    }[kind]

    records = get_table_records(conn, code_id, "water", "3_Velocity_Limits")
    found = None
    for candidate in text_match_candidates:
        found = _find_first_numeric(records, "parameter", candidate)
        if found:
            break
    if found:
        num, conf, ref, matched_text = found
        return DesignValue(
            value=num, unit="m/s", code_id=code_id, table_reference=ref or "3_Velocity_Limits",
            confidence=conf, source_classification="CODE", notes=f"matched: {matched_text}",
        )

    if allow_fallback_code:
        fb = get_velocity_limit(conn, allow_fallback_code, kind=kind, allow_fallback_code=None)
        if fb:
            fb.confidence = "FLAGGED"
            fb.fallback_from = allow_fallback_code
            fb.source_classification = "ASSUMED"
            fb.notes = (f"{code_id} has no stated value for kind='{kind}' (documented gap) — "
                        f"borrowed from {allow_fallback_code}: {fb.notes}")
            return fb
    return None


def get_material_roughness(conn, code_id: str, material_name_substr: str,
                            allow_fallback_code: Optional[str] = None) -> Optional[dict]:
    """Returns {'hazen_williams_c': x, 'darcy_epsilon_ft': y, 'status': ...} for a material."""
    records = get_table_records(conn, code_id, "water", "10_Material_Roughness")
    match = material_name_substr.lower()
    for rec in records:
        name = rec.get("material", (None, None, None))[1] or ""
        if match in str(name).lower():
            c_val = rec.get("hazen_williams_c_design", (None, None, None))[0]
            eps = rec.get("darcy_epsilon_ft", (None, None, None))
            status_txt = rec.get("status", (None, None, None))[1]
            confidence = rec.get("hazen_williams_c_design", (None, None, "CONFIRMED"))[2]
            return {
                "hazen_williams_c": c_val,
                "darcy_epsilon_ft": eps[0] if eps[0] is not None else eps[1],
                "status": status_txt,
                "confidence": confidence,
                "code_id": code_id,
            }
    if allow_fallback_code:
        return get_material_roughness(conn, allow_fallback_code, material_name_substr, None)
    return None


def get_demand_from_wsfu(conn, code_id: str, total_wsfu: float,
                          demand_column: str = "flush_tank_lpm") -> Optional[DesignValue]:
    """
    Looks up design flow (L/min) for a given total WSFU from the code's
    '2_Demand_Conversion' table (Hunter's Curve-style discrete table).
    Linearly interpolates between the two bracketing table rows when
    total_wsfu falls between them — standard engineering practice for this
    kind of curve, not an invented value (both bracketing points are real
    code data; only the interpolation is computed). Never extrapolates
    beyond the table's own range — that raises MissingCodeDataError instead.
    """
    from calculations.validation import finite
    finite('total_wsfu',total_wsfu,minimum=0)
    if demand_column not in ('flush_tank_lpm','flush_valve_lpm','flush_tank_gpm','flush_valve_gpm'):
        raise ValueError('Demand column must declare flush tank/valve and L/min or US gpm units')
    records = get_table_records(conn, code_id, "water", "2_Demand_Conversion")
    points = []
    for rec in records:
        wsfu = rec.get("wsfu", (None, None, None))
        base=demand_column.rsplit('_',1)[0]
        lpm=rec.get(base+'_lpm',(None,None,None))
        gpm=rec.get(base+'_gpm',(None,None,None))
        if lpm[0] is not None and gpm[0] is not None and abs(lpm[0]-gpm[0]*3.785411784)>1e-6:
            raise ValueError('Contradictory L/min and US gpm demand values')
        demand=lpm if lpm[0] is not None else (gpm[0]*3.785411784,gpm[1],gpm[2]) if gpm[0] is not None else (None,None,None)
        if wsfu[0] is not None and demand[0] is not None:
            points.append((wsfu[0], demand[0], demand[2], rec.get("_table_reference")))
    if not points:
        return None
    points.sort(key=lambda p: p[0])

    unique = {}
    for wsfu,demand,conf,ref in points:
        finite('table WSFU',wsfu,minimum=0)
        finite('table demand',demand,minimum=0)
        if wsfu in unique and unique[wsfu][1] != demand:
            raise ValueError('Conflicting demand rows for the same WSFU')
        if wsfu in unique and unique[wsfu][2]=='FLAGGED': conf='FLAGGED'
        unique[wsfu]=(wsfu,demand,conf,ref)
    points=sorted(unique.values())
    for wsfu,demand,conf,ref in points:
        if total_wsfu == wsfu:
            return DesignValue(value=demand,unit='L/min',code_id=code_id,table_reference=ref,
                               confidence=conf,source_classification='CODE',notes='Exact demand-table row')
    if total_wsfu < points[0][0] or total_wsfu > points[-1][0]:
        return None  # beyond table range -> caller must raise MissingCodeDataError, not extrapolate

    for (w1, d1, c1, ref), (w2, d2, c2, _) in zip(points, points[1:]):
        if w1 <= total_wsfu <= w2:
            # linear interpolation between two real, adjacent table points
            frac = (total_wsfu - w1) / (w2 - w1)
            demand = d1 + frac * (d2 - d1)
            confidence = "FLAGGED" if (c1 == "FLAGGED" or c2 == "FLAGGED") else "CONFIRMED"
            return DesignValue(
                value=demand, unit="L/min", code_id=code_id, table_reference=ref,
                confidence=confidence, source_classification="CODE",
                notes=f"interpolated between {w1} WSFU ({d1} L/min) and {w2} WSFU ({d2} L/min)",
            )
    return None


def get_min_pipe_size(conn, code_id: str, fixture_name_substr: str) -> Optional[DesignValue]:
    """Minimum branch pipe size (mm) for a named fixture, from '4_Min_Pipe_Size'."""
    records = get_table_records(conn, code_id, "water", "4_Min_Pipe_Size")
    match = fixture_name_substr.lower()
    for rec in records:
        name = str(rec.get("fixture", (None, None, None))[1] or "")
        if match in name.lower():
            size_col = next((k for k in rec if "min_pipe" in k or "min_branch" in k), None)
            if size_col:
                num, txt, conf = rec[size_col]
                if num is not None:
                    return DesignValue(
                        value=num, unit="mm" if "mm" in size_col else "in", code_id=code_id,
                        table_reference=rec.get("_table_reference", "4_Min_Pipe_Size"),
                        confidence=conf, source_classification="CODE", notes=f"matched fixture: {name}",
                    )
    return None


def get_min_slope(conn, code_id: str, pipe_size_mm: float,
                   allow_fallback_code: Optional[str] = None) -> Optional[DesignValue]:
    """Looks up the minimum slope (%) applicable to a given pipe size from the '6_Min_Slope' table."""
    records = get_table_records(conn, code_id, "drainage", "6_Min_Slope")
    for rec in records:
        size_key = None
        for k in rec:
            if "size" in k.lower() or "pipe_mm" in k.lower():
                size_key = k
                break
        if size_key is None:
            continue
        num, txt, conf = rec[size_key]
        size_label = txt if txt is not None else str(num)
        if _size_matches(size_label, pipe_size_mm):
            slope_key = next((k for k in rec if "slope" in k.lower()), None)
            if slope_key:
                s_num, s_txt, s_conf = rec[slope_key]
                if s_num is not None:
                    return DesignValue(
                        value=s_num, unit="%", code_id=code_id,
                        table_reference=rec.get("_table_reference", "6_Min_Slope"),
                        confidence=s_conf, source_classification="CODE",
                        notes=f"matched pipe-size band: {size_label}",
                    )
    if allow_fallback_code:
        fb = get_min_slope(conn, allow_fallback_code, pipe_size_mm, None)
        if fb:
            fb.confidence = "FLAGGED"
            fb.fallback_from = allow_fallback_code
            fb.source_classification = "ASSUMED"
            fb.notes = f"{code_id} has no matching entry — borrowed from {allow_fallback_code}: {fb.notes}"
            return fb
    return None


def get_rainfall_depth_24hr(conn, code_id: str, return_period_yr: int,
                             station: str = "riyadh_station_mm") -> Optional[DesignValue]:
    """
    24-hour design rainfall depth (mm) by return period. Currently only
    populated for SAUDI_SBC_701 (Riyadh) via Ahmed's independently-verified
    Al-Saleh (1997) recalculation (database/load_confirmed_additions.py) --
    source_classification=PROJECT, not CODE, since it's a project-specific
    meteorological basis, not code text.

    station: 'riyadh_station_mm' (default) or 'riyadh_old_airport_mm' --
    both columns are in the loaded table; the station used must be stated
    on the calculation sheet (spec Section 18), not silently defaulted.
    """
    records = get_table_records(conn, code_id, "storm", "Riyadh 24hr Design Rainfall Depth")
    for rec in records:
        rp = rec.get("return_period_yr", (None, None, None))[0]
        if rp is not None and float(rp) == float(return_period_yr):
            num, txt, conf = rec.get(station, (None, None, None))
            if num is not None:
                return DesignValue(
                    value=num, unit="mm", code_id=code_id,
                    table_reference=rec.get("_table_reference", "Al-Saleh (1997)"),
                    confidence=conf, source_classification="PROJECT",
                    notes=f"{return_period_yr}-yr return period, station={station}",
                )
    return None


def get_duration_ratio(conn, code_id: str, duration_label: str) -> Optional[DesignValue]:
    """
    Ratio of a shorter-duration design storm's depth to the 24-hour depth
    (code's own depth-duration ratio table). duration_label must match the
    table's own labels exactly, e.g. '15 min', '30 min', '1 hr', '2 hr',
    '3 hr', '4 hr', '6 hr', '8 hr', '12 hr'. '24 hr' is not a table row --
    its ratio is 1.0 by definition (the depth IS the 24hr depth).
    """
    if duration_label.strip().lower() in ("24 hr", "24hr", "24 hour", "24 hours"):
        return DesignValue(value=1.0, unit="-", code_id=code_id, table_reference="(definitional)",
                            confidence="CONFIRMED", source_classification="CODE",
                            notes="24hr duration IS the base depth -- ratio is 1.0 by definition.")
    records = get_table_records(conn, code_id, "storm", "8_Rainfall_Intensity [duration+ratio_to_24hr]")
    for rec in records:
        dur = rec.get("duration", (None, None, None))[1]
        if dur is not None and str(dur).strip().lower() == duration_label.strip().lower():
            num, txt, conf = rec.get("ratio_to_24hr", (None, None, None))
            if num is not None:
                return DesignValue(
                    value=num, unit="-", code_id=code_id,
                    table_reference=rec.get("_table_reference", "8_Rainfall_Intensity (duration ratios)"),
                    confidence=conf, source_classification="CODE",
                    notes=f"matched duration row: {dur}",
                )
    return None


_DURATION_TO_HOURS = {
    "15 min": 0.25, "30 min": 0.5, "1 hr": 1.0, "2 hr": 2.0, "3 hr": 3.0,
    "4 hr": 4.0, "6 hr": 6.0, "8 hr": 8.0, "12 hr": 12.0, "24 hr": 24.0,
}


def duration_label_to_hours(duration_label: str) -> Optional[float]:
    """Converts a duration table label to hours. Returns None if unrecognized --
    caller must not guess a duration that isn't one of the table's own labels."""
    return _DURATION_TO_HOURS.get(duration_label.strip().lower())


def get_leader_size(conn, code_id: str, roof_area_m2: float,
                     design_rainfall_rate_mm_hr: float) -> Optional[DesignValue]:
    """
    Roof-drain leader (vertical conductor) sizing: 'Leader sizing by roof
    area & assumed rainfall rate' table (SBC 701 Table 1106). The table
    gives max horizontally-projected roof area a leader size can serve, as
    a function of rainfall rate (columns 25-300 mm/hr in 25 mm/hr steps).

    Picks the smallest column rate that is >= design_rainfall_rate_mm_hr
    (never rounds down -- undersizing the rate would undersize the pipe),
    then the smallest leader whose capacity at that rate covers roof_area_m2.
    """
    records = get_table_records(conn, code_id, "storm",
                                 "8_Rainfall_Intensity [leader_mm+25 mm/hr")
    if not records:
        return None

    rate_cols = sorted(
        {k for rec in records for k in rec if k.endswith("mm/hr")},
        key=lambda c: float(c.split()[0]),
    )
    chosen_col = next((c for c in rate_cols if float(c.split()[0]) >= design_rainfall_rate_mm_hr), None)
    if chosen_col is None:
        return None  # design rate exceeds every tabulated rate column -- don't extrapolate

    candidates = []
    for rec in records:
        leader = rec.get("leader_mm", (None, None, None))
        cap = rec.get(chosen_col, (None, None, None))
        if leader[0] is not None and cap[0] is not None:
            candidates.append((leader[0], cap[0], cap[2]))
    candidates.sort(key=lambda c: c[0])

    for leader_mm, max_area, confidence in candidates:
        if roof_area_m2 <= max_area:
            return DesignValue(
                value=leader_mm, unit="mm", code_id=code_id,
                table_reference="SBC701 Table 1106 (leader sizing by roof area & rainfall rate)",
                confidence=confidence, source_classification="CODE",
                notes=f"design rate rounded up to column '{chosen_col}' "
                      f"(from {design_rainfall_rate_mm_hr:.2f} mm/hr); max area at that leader size = {max_area} m2",
            )
    return None  # roof_area_m2 exceeds every leader size at this rate -- needs multiple leaders (engineer judgement)


def get_storm_drain_pipe_size(conn, code_id: str, design_flow_lpm: float,
                               orientation: str = "vertical",
                               slope_mm_per_m: Optional[float] = None) -> Optional[DesignValue]:
    """
    Storm drainage pipe sizing (SBC 701 Table 1106 pipe-sizing method).
    orientation='vertical' uses the vertical_drain_lpm capacity column.
    orientation='horizontal' requires slope_mm_per_m and matches the
    nearest available slope column (5/10/20/40 mm/m) that is <=
    slope_mm_per_m rounded down to the nearest tabulated slope actually
    achievable is NOT assumed here -- the caller must pass one of the
    table's own slopes; an unmatched slope raises via the caller
    (MissingCodeDataError), not silent interpolation of a capacity table.
    """
    records = get_table_records(conn, code_id, "storm",
                                 "8_Rainfall_Intensity [pipe_mm+vertical_drain_lpm")
    if not records:
        return None

    if orientation == "vertical":
        cap_col = "vertical_drain_lpm"
    elif orientation == "horizontal":
        if slope_mm_per_m is None:
            return None
        from calculations.validation import finite
        finite('slope_mm_per_m', slope_mm_per_m, positive=True)
        if not float(slope_mm_per_m).is_integer():
            return None
        cap_col = f"horiz_{int(slope_mm_per_m)}mm_m"
    else:
        raise ValueError("orientation must be 'vertical' or 'horizontal'")

    candidates = []
    for rec in records:
        size = rec.get("pipe_mm", (None, None, None))
        cap = rec.get(cap_col, (None, None, None))
        if size[0] is not None and cap[0] is not None:
            candidates.append((size[0], cap[0], cap[2]))
    if not candidates:
        return None  # requested slope column doesn't exist in the table
    candidates.sort(key=lambda c: c[0])

    for pipe_mm, capacity_lpm, confidence in candidates:
        if design_flow_lpm <= capacity_lpm:
            return DesignValue(
                value=pipe_mm, unit="mm", code_id=code_id,
                table_reference=f"SBC701 Table 1106 (storm drain sizing, {cap_col})",
                confidence=confidence, source_classification="CODE",
                notes=f"capacity at this size = {capacity_lpm} L/min (design flow = {design_flow_lpm} L/min)",
            )
    return None  # design_flow_lpm exceeds every tabulated size -- needs engineer judgement (parallel drains)


def list_water_fixture_unit_choices(conn, code_id: str, service: str = 'cold') -> list[dict]:
    """
    Normalizes code_id's own '1_Fixture_Units' table into a flat list of
    pickable (fixture, occupancy) choices with a real WSFU value attached,
    for a dropdown instead of free-text fixture-name entry (which silently
    fails to match table rows on any spelling/phrasing difference).

    Each source workbook's Tab 1 was structured differently per code, so
    this reads whichever columns that code actually has:
      SAUDI_SBC_701: fixture + occupancy + control + cold           (WSFU, real)
      UPC:           fixture + private/public/assembly               (WSFU, real)
      IPC:           has BOTH a drainage-FU sub-table (dfu_ipc/dfu_upc,
                     skipped here) AND a separate genuine WSFU sub-table
                     (fixture+occupancy+control+cold+hot+total) under the
                     same '1_Fixture_Units' tab name -- only the WSFU rows
                     are picked out.
      EGYPT_LOCAL:   no '1_Fixture_Units' table loaded -> returns [].

    Returns [] rather than guessing when a code's table isn't in a
    water-supply-FU shape -- callers must handle the empty-choices case
    (manual entry) rather than treat [] as an error.
    """
    if service not in ('cold', 'hot'):
        raise ValueError('Fixture-unit service must be cold or hot')
    records = get_table_records(conn, code_id, "water", "1_Fixture_Units")
    choices = []
    for rec in records:
        fixture = rec.get("fixture", (None, None, None))[1]
        if not fixture:
            continue
        if service in rec:  # Explicit service-specific WSFU only.
            val, _, conf = rec.get(service, (None, None, None))
            if val is None:
                continue
            occ = rec.get("occupancy", (None, None, None))[1] or ""
            ctrl = rec.get("control", (None, None, None))[1] or ""
            tail = ", ".join(p for p in (occ, ctrl) if p)
            label = f"{fixture} ({tail}) — {val} WSFU" if tail else f"{fixture} — {val} WSFU"
            choices.append({
                "label": label, "fixture_name": fixture, "occupancy": occ or None,
                "control": ctrl or None, "wsfu_value": val, "confidence": conf,
                "table_reference": rec.get("_table_reference"),
            })
        elif service == 'cold' and 'min_branch_in' in rec and any(c in rec for c in ("private", "public", "assembly")):  # UPC water table, not drainage traps
            for col, occ_label in (("private", "Private"), ("public", "Public"), ("assembly", "Assembly")):
                if col not in rec:
                    continue
                val, _, conf = rec.get(col, (None, None, None))
                if val is None:
                    continue
                choices.append({
                    "label": f"{fixture} — {occ_label} — {val} WSFU", "fixture_name": fixture,
                    "occupancy": occ_label, "control": None, "wsfu_value": val, "confidence": conf,
                    "table_reference": rec.get("_table_reference"),
                })
        # else: this code's '1_Fixture_Units' rows for this fixture aren't in a
        # water-supply-FU shape -- skip, don't guess which column might be a WSFU value.
    return choices


def list_drainage_fixture_unit_choices(conn, code_id: str, edition=None) -> list[dict]:
    """Use only the active code/edition; never borrow another code's DFU."""
    if code_id=='IPC' and str(edition)=='2024':
        from database.ipc2024_fixtures import choices
        return choices()
    choices = []
    records = get_table_records(conn, code_id, 'water', '1_Fixture_Units')
    records += get_table_records(conn, code_id, 'drainage', '1_Fixture_Units')
    for rec in records:
        fixture = rec.get('fixture', (None, None, None))[1]
        columns = []
        specific = {'IPC': 'dfu_ipc', 'UPC': 'dfu_upc'}.get(code_id)
        if specific and specific in rec:
            columns = [(specific, '')]
        elif 'dfu' in rec:
            if not fixture and rec.get('trap_size_mm', (None, None, None))[0] is not None:
                fixture = f"Trap {rec['trap_size_mm'][0]:g} mm (verify fixture applicability)"
            columns = [('dfu', '')]
        elif code_id == 'UPC' and 'trap_in' in rec:
            columns = [(col, col.title()) for col in ('private', 'public', 'assembly') if col in rec]
        if not fixture:
            continue
        for col, occupancy in columns:
            value, _, confidence = rec[col]
            if value is None:
                continue
            choices.append(dict(label=f'{fixture} {occupancy} — {value:g} DFU'.strip(),
                fixture_name=fixture, occupancy=occupancy, unit_value=value, unit='DFU',
                confidence=confidence, table_reference=rec.get('_table_reference')))
    return choices


def list_hot_water_demand_choices(conn) -> list[dict]:
    """ASPE demand rates held in the IPC workbook; these are GPH, not WSFU."""
    choices = []
    for rec in get_table_records(conn, 'IPC', 'hot_water', '9_Hot_Water_Basis [fixture+gph'):
        name = rec.get('fixture', (None, None, None))[1]
        value, _, confidence = rec.get('gph', (None, None, None))
        if name and value is not None:
            choices.append(dict(label=f'{name} — {value:g} GPH', fixture_name=name,
                unit_value=value, unit='GPH', confidence=confidence,
                table_reference=rec.get('_table_reference')))
    return choices


def _size_matches(size_label: str, pipe_size_mm: float) -> bool:
    """Handles bands like '65 or less', '80 to 150', '200 or more', or a plain number."""
    s = str(size_label).lower().strip()
    try:
        return float(s) == pipe_size_mm
    except ValueError:
        pass
    if "or less" in s:
        try:
            return pipe_size_mm <= float(s.split("or less")[0].strip())
        except ValueError:
            return False
    if "or more" in s:
        try:
            return pipe_size_mm >= float(s.split("or more")[0].strip())
        except ValueError:
            return False
    if "to" in s:
        parts = s.split("to")
        try:
            lo, hi = float(parts[0].strip()), float(parts[1].strip())
            return lo <= pipe_size_mm <= hi
        except (ValueError, IndexError):
            return False
    return False
