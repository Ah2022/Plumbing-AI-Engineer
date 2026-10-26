"""
units/convert.py
------------------
Explicit unit conversion layer. Internal engine units are SI
(mm/m, L/s, kPa, m head, m2, C, kW, m/s, mm/hr) per project spec
section 29. Every conversion function is named for exactly what it
does — no implicit/guessed conversions anywhere else in the codebase.
"""

from __future__ import annotations

# --- Pressure ---------------------------------------------------------

def psi_to_kpa(psi: float) -> float:
    return psi * 6.894757293168


def kpa_to_psi(kpa: float) -> float:
    return kpa / 6.894757293168


def kpa_to_m_head(kpa: float, fluid_density_kg_m3: float = 1000.0) -> float:
    """Head (m) = Pressure (Pa) / (rho * g)."""
    g = 9.80665
    return (kpa * 1000.0) / (fluid_density_kg_m3 * g)


def m_head_to_kpa(m_head: float, fluid_density_kg_m3: float = 1000.0) -> float:
    g = 9.80665
    return fluid_density_kg_m3 * g * m_head / 1000.0


# --- Flow ---------------------------------------------------------------

def gpm_to_lps(gpm: float) -> float:
    return gpm * 0.0630901964


def lps_to_gpm(lps: float) -> float:
    return lps / 0.0630901964


def lps_to_m3_s(lps: float) -> float:
    return lps / 1000.0


def m3_s_to_lps(m3_s: float) -> float:
    return m3_s * 1000.0


# --- Length / diameter ----------------------------------------------------

def inch_to_mm(inch: float) -> float:
    return inch * 25.4


def mm_to_inch(mm: float) -> float:
    return mm / 25.4


def ft_to_m(ft: float) -> float:
    return ft * 0.3048


def m_to_ft(m: float) -> float:
    return m / 0.3048


# --- Temperature -------------------------------------------------------------

def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


# --- Rainfall -------------------------------------------------------------

def in_hr_to_mm_hr(in_hr: float) -> float:
    return in_hr * 25.4
