"""
units/convert.py
------------------
Explicit unit conversion layer. Internal engine units are SI
(mm/m, L/s, kPa, m head, m2, C, kW, m/s, mm/hr) per project spec
section 29. Every conversion function is named for exactly what it
does — no implicit/guessed conversions anywhere else in the codebase.
"""

from __future__ import annotations

from calculations.validation import finite, checked_numeric

# --- Pressure ---------------------------------------------------------

@checked_numeric
def psi_to_kpa(psi: float) -> float:
    finite('psi',psi)
    return psi * 6.894757293168


@checked_numeric
def kpa_to_psi(kpa: float) -> float:
    finite('kpa',kpa)
    return kpa / 6.894757293168


@checked_numeric
def kpa_to_m_head(kpa: float, fluid_density_kg_m3: float = 1000.0) -> float:
    """Head (m) = Pressure (Pa) / (rho * g)."""
    finite('kpa',kpa)
    finite('fluid_density_kg_m3',fluid_density_kg_m3,positive=True)
    g = 9.80665
    return (kpa * 1000.0) / (fluid_density_kg_m3 * g)


@checked_numeric
def m_head_to_kpa(m_head: float, fluid_density_kg_m3: float = 1000.0) -> float:
    finite('m_head',m_head)
    finite('fluid_density_kg_m3',fluid_density_kg_m3,positive=True)
    g = 9.80665
    return fluid_density_kg_m3 * g * m_head / 1000.0


# --- Flow ---------------------------------------------------------------

@checked_numeric
def gpm_to_lps(gpm: float) -> float:
    finite('gpm',gpm)
    return gpm * 0.0630901964


@checked_numeric
def lps_to_gpm(lps: float) -> float:
    finite('lps',lps)
    return lps / 0.0630901964


@checked_numeric
def lps_to_m3_s(lps: float) -> float:
    finite('lps',lps)
    return lps / 1000.0


@checked_numeric
def m3_s_to_lps(m3_s: float) -> float:
    finite('m3_s',m3_s)
    return m3_s * 1000.0


# --- Length / diameter ----------------------------------------------------

@checked_numeric
def inch_to_mm(inch: float) -> float:
    finite('inch',inch)
    return inch * 25.4


@checked_numeric
def mm_to_inch(mm: float) -> float:
    finite('mm',mm)
    return mm / 25.4


@checked_numeric
def ft_to_m(ft: float) -> float:
    finite('ft',ft)
    return ft * 0.3048


@checked_numeric
def m_to_ft(m: float) -> float:
    finite('m',m)
    return m / 0.3048


# --- Temperature -------------------------------------------------------------

@checked_numeric
def f_to_c(f: float) -> float:
    finite('f',f)
    return (f - 32.0) * 5.0 / 9.0


@checked_numeric
def c_to_f(c: float) -> float:
    finite('c',c)
    return c * 9.0 / 5.0 + 32.0


# --- Rainfall -------------------------------------------------------------

@checked_numeric
def in_hr_to_mm_hr(in_hr: float) -> float:
    finite('in_hr',in_hr)
    return in_hr * 25.4
