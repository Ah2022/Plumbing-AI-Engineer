"""
calculations/pumps.py
------------------------
Pump duty-point calculation: Total Dynamic Head + hydraulic power, using
the public-domain formulas in calculations/hydraulics.py. Matching an
actual catalogue pump to the duty point is [MANUFACTURER] data (a pump
curve) -- not loaded here, and not invented; select_pump_duty() returns
the REQUIRED duty point (flow, head, power) for the engineer or a future
manufacturer-catalogue module to match against.
"""

from __future__ import annotations

from calculations.hydraulics import total_dynamic_head, pump_power
from models import CalculationResult


def select_pump_duty(design_flow_lps: float, static_head_m: float, friction_loss_m: float,
                      fitting_loss_m: float, equipment_loss_m: float, required_residual_head_m: float,
                      efficiency: float, calc_id: str) -> CalculationResult:
    """
    Two-step, fully traced: TDH first, then hydraulic power at that TDH.
    Both intermediate CalculationResults are preserved in `intermediate`
    so the full chain is auditable, not just the final power figure.
    """
    tdh_result = total_dynamic_head(
        static_head_m, friction_loss_m, fitting_loss_m, equipment_loss_m,
        required_residual_head_m, calc_id=f"{calc_id}-TDH",
    )
    power_result = pump_power(design_flow_lps, tdh_result.result_value, efficiency, calc_id=f"{calc_id}-PWR")

    return CalculationResult(
        calc_id=calc_id,
        calc_type="pump_duty_selection",
        formula="TDH = static + friction + fitting + equipment + required residual head; "
                "P = rho*g*Q*TDH/efficiency",
        inputs={"design_flow_lps": (design_flow_lps, "L/s"), "efficiency": (efficiency, "-")},
        intermediate={
            "tdh_m": tdh_result.result_value,
            "tdh_breakdown": tdh_result.inputs,
            "power_kw": power_result.result_value,
        },
        result_value=power_result.result_value,
        result_unit="kW",
        selected_value=tdh_result.result_value,
        status="CALCULATED_NOT_APPROVED",
        reference="Standard pump-head-balance + hydraulic-power relationships (public-domain hydraulics)",
        notes=f"Duty point: {design_flow_lps} L/s @ {tdh_result.result_value} m TDH -> "
              f"{power_result.result_value} kW efficiency-adjusted power. Motor sizing and actual pump "
              f"selection need a manufacturer curve -- not loaded/invented here.",
    )
