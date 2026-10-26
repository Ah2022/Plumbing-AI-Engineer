"""
calculations/hydraulics.py
----------------------------
Generic hydraulic formulas — Q=VA, Darcy-Weisbach, Hazen-Williams,
Total Dynamic Head, pump power. These are standard, public-domain
engineering-mechanics relationships (not copyrighted code-table
content), so they are safe to implement directly, unlike fixture-unit
tables or DFU tables which must come from the licensed code text.

Every function returns a models.CalculationResult so the full
INPUT -> FORMULA -> RESULT chain is preserved for the report/QA-QC
engine. Nothing here decides PASS/FAIL against a code limit — that
happens in calculations/water.py etc., where the limit is read from
design_table_values (and raises MissingCodeDataError if absent).
"""

from __future__ import annotations

import math

from models import CalculationResult

G = 9.80665  # m/s^2


def velocity_from_flow(flow_lps: float, internal_diameter_mm: float, calc_id: str) -> CalculationResult:
    """V = Q / A.  Q in L/s, D in mm -> V in m/s."""
    q_m3s = flow_lps / 1000.0
    d_m = internal_diameter_mm / 1000.0
    area_m2 = math.pi * (d_m ** 2) / 4.0
    velocity = q_m3s / area_m2 if area_m2 > 0 else float("inf")

    return CalculationResult(
        calc_id=calc_id,
        calc_type="velocity_from_flow",
        formula="V = Q / A,  A = pi * D^2 / 4",
        inputs={"flow_lps": (flow_lps, "L/s"), "internal_diameter_mm": (internal_diameter_mm, "mm")},
        intermediate={"flow_m3_s": q_m3s, "area_m2": area_m2},
        result_value=round(velocity, 4),
        result_unit="m/s",
        reference="Continuity equation (public-domain fluid mechanics)",
        status="CALCULATED_NOT_APPROVED",
    )


def darcy_weisbach_head_loss(
    flow_lps: float,
    internal_diameter_mm: float,
    length_m: float,
    friction_factor: float,
    calc_id: str,
) -> CalculationResult:
    """hf = f * (L/D) * (V^2 / 2g)."""
    d_m = internal_diameter_mm / 1000.0
    v_calc = velocity_from_flow(flow_lps, internal_diameter_mm, calc_id + "-V")
    velocity = v_calc.result_value

    hf = friction_factor * (length_m / d_m) * (velocity ** 2) / (2 * G)

    return CalculationResult(
        calc_id=calc_id,
        calc_type="darcy_weisbach_head_loss",
        formula="hf = f * (L / D) * (V^2 / 2g)",
        inputs={
            "flow_lps": (flow_lps, "L/s"),
            "internal_diameter_mm": (internal_diameter_mm, "mm"),
            "length_m": (length_m, "m"),
            "friction_factor": (friction_factor, "-"),
        },
        intermediate={"velocity_m_s": velocity, "d_m": d_m},
        result_value=round(hf, 4),
        result_unit="m",
        reference="Darcy-Weisbach equation (public-domain fluid mechanics)",
        status="CALCULATED_NOT_APPROVED",
        notes="friction_factor (Darcy f) must itself come from a Moody-chart/Colebrook "
              "calculation or a manufacturer's C-value conversion — not hardcoded.",
    )


def hazen_williams_head_loss(
    flow_lps: float,
    internal_diameter_mm: float,
    length_m: float,
    c_factor: float,
    calc_id: str,
) -> CalculationResult:
    """
    Hazen-Williams (SI form):
        hf = 10.67 * L * Q^1.852 / (C^1.852 * D^4.8704)
    with Q in m^3/s, D in m, hf in m.
    """
    q_m3s = flow_lps / 1000.0
    d_m = internal_diameter_mm / 1000.0

    hf = 10.67 * length_m * (q_m3s ** 1.852) / (c_factor ** 1.852 * d_m ** 4.8704)

    return CalculationResult(
        calc_id=calc_id,
        calc_type="hazen_williams_head_loss",
        formula="hf = 10.67 * L * Q^1.852 / (C^1.852 * D^4.8704)   [SI units]",
        inputs={
            "flow_lps": (flow_lps, "L/s"),
            "internal_diameter_mm": (internal_diameter_mm, "mm"),
            "length_m": (length_m, "m"),
            "c_factor": (c_factor, "-"),
        },
        intermediate={"flow_m3_s": q_m3s, "d_m": d_m},
        result_value=round(hf, 4),
        result_unit="m",
        reference="Hazen-Williams equation, SI form (public-domain fluid mechanics)",
        status="CALCULATED_NOT_APPROVED",
        notes="c_factor is material-dependent — must be read from materials.roughness_value "
              "(roughness_model='hazen_williams_C'), not assumed.",
    )


def total_dynamic_head(
    static_head_m: float,
    friction_loss_m: float,
    fitting_loss_m: float,
    equipment_loss_m: float,
    required_residual_head_m: float,
    calc_id: str,
) -> CalculationResult:
    """TDH = Static Head + Friction Loss + Fitting/Equipment Loss + Required Residual Head."""
    tdh = static_head_m + friction_loss_m + fitting_loss_m + equipment_loss_m + required_residual_head_m

    return CalculationResult(
        calc_id=calc_id,
        calc_type="total_dynamic_head",
        formula="TDH = Static Head + Friction Loss + Fitting Loss + Equipment Loss + Required Residual Head",
        inputs={
            "static_head_m": (static_head_m, "m"),
            "friction_loss_m": (friction_loss_m, "m"),
            "fitting_loss_m": (fitting_loss_m, "m"),
            "equipment_loss_m": (equipment_loss_m, "m"),
            "required_residual_head_m": (required_residual_head_m, "m"),
        },
        intermediate={},
        result_value=round(tdh, 4),
        result_unit="m",
        reference="Standard pump-head-balance relationship (public-domain hydraulics)",
        status="CALCULATED_NOT_APPROVED",
    )


def pump_power(
    flow_lps: float,
    head_m: float,
    efficiency: float,
    calc_id: str,
    fluid_density_kg_m3: float = 1000.0,
) -> CalculationResult:
    """P (kW) = rho * g * Q * H / (efficiency * 1000)."""
    q_m3s = flow_lps / 1000.0
    power_w = fluid_density_kg_m3 * G * q_m3s * head_m / efficiency
    power_kw = power_w / 1000.0

    return CalculationResult(
        calc_id=calc_id,
        calc_type="pump_power",
        formula="P = rho * g * Q * H / efficiency",
        inputs={
            "flow_lps": (flow_lps, "L/s"),
            "head_m": (head_m, "m"),
            "efficiency": (efficiency, "-"),
            "fluid_density_kg_m3": (fluid_density_kg_m3, "kg/m3"),
        },
        intermediate={"flow_m3_s": q_m3s},
        result_value=round(power_kw, 4),
        result_unit="kW",
        reference="Standard pump hydraulic-power relationship (public-domain hydraulics)",
        status="CALCULATED_NOT_APPROVED",
    )


def rational_method_peak_flow(
    runoff_coefficient: float,
    rainfall_intensity_mm_hr: float,
    catchment_area_m2: float,
    calc_id: str,
) -> CalculationResult:
    """
    Rational Method: Q = C * I * A
    SI convenience form used here: Q (L/s) = C * I(mm/hr) * A(m2) / 360
    """
    q_lps = runoff_coefficient * rainfall_intensity_mm_hr * catchment_area_m2 / 360.0

    return CalculationResult(
        calc_id=calc_id,
        calc_type="rational_method_peak_flow",
        formula="Q (L/s) = C * I(mm/hr) * A(m2) / 360",
        inputs={
            "runoff_coefficient": (runoff_coefficient, "-"),
            "rainfall_intensity_mm_hr": (rainfall_intensity_mm_hr, "mm/hr"),
            "catchment_area_m2": (catchment_area_m2, "m2"),
        },
        intermediate={},
        result_value=round(q_lps, 4),
        result_unit="L/s",
        reference="Rational Method (public-domain hydrology). Rainfall intensity itself "
                  "must be sourced from CODE / PROJECT / LOCAL RAINFALL DATA per spec section 18.",
        status="CALCULATED_NOT_APPROVED",
    )


def q_heat(mass_flow_kg_s: float, specific_heat_kj_kgc: float, delta_t_c: float, calc_id: str) -> CalculationResult:
    """Q = m_dot * Cp * Delta T  (hot-water heater/recovery duty)."""
    q_kw = mass_flow_kg_s * specific_heat_kj_kgc * delta_t_c

    return CalculationResult(
        calc_id=calc_id,
        calc_type="q_heat",
        formula="Q = m_dot * Cp * Delta T",
        inputs={
            "mass_flow_kg_s": (mass_flow_kg_s, "kg/s"),
            "specific_heat_kj_kgc": (specific_heat_kj_kgc, "kJ/kg.C"),
            "delta_t_c": (delta_t_c, "C"),
        },
        intermediate={},
        result_value=round(q_kw, 4),
        result_unit="kW",
        reference="Standard sensible-heat relationship (public-domain thermodynamics)",
        status="CALCULATED_NOT_APPROVED",
    )
