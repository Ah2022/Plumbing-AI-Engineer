"""
calculations/tanks.py
------------------------
Tank sizing. Two paths:

1. Domestic cold-water / break tank: required volume is a function of
   PROJECT-supplied storage duration (spec Section 8: this is a [PROJECT]
   classification value, not a code table) times average daily demand.
   storage_duration_hr must be supplied explicitly by the caller (read
   from an APPROVED design_basis_items entry in the UI layer) -- this
   module never invents a duration.

2. Hot water storage tank: reuses calculations/hot_water.hot_water_demand()'s
   storage-capacity result directly (ASPE Table 6-1 method) rather than
   recomputing anything here.
"""

from __future__ import annotations

from models import CalculationResult


def size_domestic_water_tank(avg_daily_demand_lps: float, storage_duration_hr: float, calc_id: str,
                              freeboard_pct: float = 10.0) -> CalculationResult:
    """
    required_volume_m3 = avg_daily_demand_lps * storage_duration_hr * 3600 / 1000
    selected_volume_m3 = required_volume_m3 * (1 + freeboard_pct/100)
    """
    required_m3 = avg_daily_demand_lps * storage_duration_hr * 3600.0 / 1000.0
    selected_m3 = required_m3 * (1 + freeboard_pct / 100.0)

    return CalculationResult(
        calc_id=calc_id,
        calc_type="tank_sizing",
        formula="Required volume (m3) = demand (L/s) * duration (hr) * 3600 / 1000; "
                "Selected = Required * (1 + freeboard%)",
        inputs={"avg_daily_demand_lps": (avg_daily_demand_lps, "L/s"),
                "storage_duration_hr": (storage_duration_hr, "hr"),
                "freeboard_pct": (freeboard_pct, "%")},
        intermediate={"required_volume_m3": round(required_m3, 3)},
        result_value=round(selected_m3, 3),
        result_unit="m3",
        required_value=round(required_m3, 3),
        selected_value=round(selected_m3, 3),
        status="CALCULATED_NOT_APPROVED",
        reference="Standard storage-duration sizing method (public-domain); "
                  "storage_duration_hr is a [PROJECT] design-basis input, not a code value.",
        notes="storage_duration_hr must come from an APPROVED design-basis entry -- "
              "confirm it's approved before treating this result as final.",
    )


def size_hot_water_storage_tank_from_demand(hot_water_demand_result, calc_id: str) -> CalculationResult:
    """
    Wraps a CalculationResult from calculations.hot_water.hot_water_demand()
    into a tank-sizing result -- the storage volume was already computed
    there (design hourly demand * ASPE storage capacity factor); this just
    reframes it as a tank_sizing record so it shows up consistently
    alongside other tank results.
    """
    storage_gal = hot_water_demand_result.selected_value
    storage_l = storage_gal * 3.78541 if storage_gal is not None else None

    return CalculationResult(
        calc_id=calc_id,
        calc_type="tank_sizing",
        formula="Hot water storage volume = design hourly demand (GPH) * ASPE storage capacity factor "
                "(see calculations.hot_water.hot_water_demand)",
        inputs={"source_calc_id": (hot_water_demand_result.calc_id, "-")},
        intermediate={"storage_gal": storage_gal},
        result_value=round(storage_l, 1) if storage_l is not None else None,
        result_unit="L",
        selected_value=round(storage_l, 1) if storage_l is not None else None,
        status=hot_water_demand_result.status,
        reference=hot_water_demand_result.reference,
        notes=f"Derived from hot water demand calc {hot_water_demand_result.calc_id}.",
    )
