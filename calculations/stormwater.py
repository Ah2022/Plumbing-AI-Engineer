"""
calculations/stormwater.py  —  Phase 5 (complete)
-----------------------------------------------------
Full chain: design rainfall intensity -> Rational Method peak flow ->
roof-drain (leader) sizing -> storm drainage pipe sizing.

This module was gated pending the Riyadh 24-hour design rainfall depth
(docs/ARCHITECTURE.md Section 0b, item 1) -- Ahmed independently verified
that value (Al-Saleh 1997) and it's loaded via
database/load_confirmed_additions.py. Once loaded, everything downstream
turned out to already be present in the SBC701 workbook Ahmed supplied:
Table 1106's leader-sizing and pipe-sizing sub-tables were parsed and
loaded by database/load_design_tables.py from day one -- they were never
actually missing, only unusable without the depth input. That's why this
whole module unblocks in one pass rather than needing new data collection.

Design duration and return period are NOT decided here -- the code's own
storm rules (SBC701-S-001/002 in compliance/) require these to be entered
and APPROVED as design-basis items before storm sizing proceeds (spec
Section 18: "must show its source"). Callers pass them explicitly.
"""

from __future__ import annotations

from calculations.hydraulics import rational_method_peak_flow  # re-exported, usable since Phase 1
from database.design_table_api import (
    get_rainfall_depth_24hr, get_duration_ratio, duration_label_to_hours,
    get_leader_size, get_storm_drain_pipe_size,
)
from models import CalculationResult, MissingCodeDataError


def design_rainfall_intensity(conn, code_id: str, return_period_yr: int, duration_label: str,
                               calc_id: str, station: str = "riyadh_station_mm") -> CalculationResult:
    """
    Design rainfall intensity (mm/hr) = (24hr depth * duration ratio) / duration(hr).

    Chain, each link real code/project data, nothing invented:
      24hr depth  -- Al-Saleh (1997), Ahmed-verified, source_classification=PROJECT
      duration ratio -- SBC701 Table 8 depth-duration ratios, source_classification=CODE
      duration(hr) -- deterministic conversion of the SAME duration_label used for the ratio lookup
    """
    depth = get_rainfall_depth_24hr(conn, code_id, return_period_yr, station=station)
    if depth is None:
        raise MissingCodeDataError(
            what=f"24-hour design rainfall depth for {return_period_yr}-yr return period",
            where=f"code={code_id}, station={station} -- see database/load_confirmed_additions.py",
        )
    ratio = get_duration_ratio(conn, code_id, duration_label)
    if ratio is None:
        raise MissingCodeDataError(
            what=f"Depth-duration ratio for duration='{duration_label}'",
            where=f"code={code_id}:8_Rainfall_Intensity (duration ratios) -- label must match the "
                  f"table's own rows, e.g. '15 min', '1 hr', '6 hr'",
        )
    duration_hr = duration_label_to_hours(duration_label)
    if duration_hr is None:
        raise MissingCodeDataError(
            what=f"Duration-to-hours conversion for '{duration_label}'",
            where="calculations/stormwater.py:_DURATION_TO_HOURS has no entry for this label",
        )

    design_depth_mm = depth.value * ratio.value
    intensity_mm_hr = design_depth_mm / duration_hr

    confidence = "FLAGGED" if (depth.confidence == "FLAGGED" or ratio.confidence == "FLAGGED") else "CONFIRMED"

    return CalculationResult(
        calc_id=calc_id,
        calc_type="design_rainfall_intensity",
        formula="I (mm/hr) = (depth_24hr_mm * ratio_to_24hr) / duration_hr",
        inputs={
            "return_period_yr": (return_period_yr, "yr"),
            "duration_label": (duration_label, "-"),
            "duration_hr": (duration_hr, "hr"),
            "station": (station, "-"),
        },
        intermediate={
            "depth_24hr_mm": depth.value,
            "duration_ratio": ratio.value,
            "design_depth_mm": round(design_depth_mm, 3),
        },
        result_value=round(intensity_mm_hr, 3),
        result_unit="mm/hr",
        status="CALCULATED_NOT_APPROVED" if confidence == "CONFIRMED" else "WARNING",
        reference=f"{depth.table_reference} + {ratio.table_reference}",
        notes=(None if confidence == "CONFIRMED" else
               "Uses a FLAGGED underlying table row -- confirm before sign-off.") ,
    )


def size_roof_drain(conn, code_id: str, roof_area_m2: float, rainfall_intensity_mm_hr: float,
                     calc_id: str) -> CalculationResult:
    """
    Selects a leader (vertical roof-drain conductor) size from SBC701 Table
    1106's roof-area-vs-rainfall-rate table. Does NOT invent a rainfall rate --
    takes the design intensity as computed by design_rainfall_intensity()
    (or any other traceable source) and rounds UP to the nearest tabulated
    rate column, never down.
    """
    dv = get_leader_size(conn, code_id, roof_area_m2, rainfall_intensity_mm_hr)
    if dv is None:
        raise MissingCodeDataError(
            what=f"Leader size for {roof_area_m2} m2 roof area at {rainfall_intensity_mm_hr} mm/hr",
            where=f"code={code_id}:Table 1106 leader-sizing -- either the design rate exceeds every "
                  f"tabulated rate column (300 mm/hr max), or the area exceeds every leader size at "
                  f"that rate (needs multiple leaders -- engineer judgement, not an automatic guess).",
        )
    return CalculationResult(
        calc_id=calc_id,
        calc_type="roof_drain_leader_sizing",
        formula="Select smallest leader size whose max-served-area (at the design rainfall rate) >= roof_area_m2",
        inputs={"roof_area_m2": (roof_area_m2, "m2"), "rainfall_intensity_mm_hr": (rainfall_intensity_mm_hr, "mm/hr")},
        intermediate={},
        result_value=dv.value,
        result_unit="mm",
        required_value=roof_area_m2,
        selected_value=dv.value,
        status="PASS" if dv.confidence == "CONFIRMED" else "WARNING",
        reference=dv.table_reference,
        notes=dv.notes if dv.confidence == "CONFIRMED" else f"{dv.notes} -- underlying row is FLAGGED, confirm before sign-off.",
    )


def size_storm_drain_pipe(conn, code_id: str, design_flow_lps: float, calc_id: str,
                           orientation: str = "vertical", slope_mm_per_m: float = None) -> CalculationResult:
    """
    Sizes a storm drainage pipe (horizontal conductor or vertical stack)
    from SBC701 Table 1106's own pipe-capacity table -- the SBC-specific
    method the workbook's own notes name explicitly, distinct from the
    roof-area leader table above (this one sizes the drain PIPE given a
    flow, once you already know the flow from the Rational Method / roof
    drain step).
    """
    flow_lpm = design_flow_lps * 60.0
    dv = get_storm_drain_pipe_size(conn, code_id, flow_lpm, orientation=orientation, slope_mm_per_m=slope_mm_per_m)
    if dv is None:
        where = f"code={code_id}:Table 1106 pipe-sizing, orientation={orientation}"
        if orientation == "horizontal":
            where += f", slope_mm_per_m={slope_mm_per_m} (must be one of the table's own slopes: 5/10/20/40)"
        raise MissingCodeDataError(
            what=f"Storm drain pipe size for {flow_lpm:.1f} L/min",
            where=where + " -- or design flow exceeds every tabulated size (needs engineer judgement).",
        )
    return CalculationResult(
        calc_id=calc_id,
        calc_type="storm_drain_pipe_sizing",
        formula="Select smallest pipe whose tabulated capacity (L/min, this orientation/slope) >= design flow",
        inputs={
            "design_flow_lps": (design_flow_lps, "L/s"), "design_flow_lpm": (round(flow_lpm, 2), "L/min"),
            "orientation": (orientation, "-"), "slope_mm_per_m": (slope_mm_per_m, "mm/m"),
        },
        intermediate={},
        result_value=dv.value,
        result_unit="mm",
        required_value=round(flow_lpm, 2),
        selected_value=dv.value,
        status="PASS" if dv.confidence == "CONFIRMED" else "WARNING",
        reference=dv.table_reference,
        notes=dv.notes,
    )
