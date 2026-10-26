"""
tests/test_stormwater.py
----------------------------
Regression tests for Phase 5 (Stormwater) — the design-rainfall-intensity
chain, roof-drain (leader) sizing, and storm-drain pipe sizing, all
against the real SBC701 Table 1106 data + Ahmed's verified Riyadh
rainfall depth. Expected values below are hand-computed from the source
workbook rows, not copied from the implementation.
"""

import pytest

from database.db import init_db
from database.load_design_tables import load_all_workbooks
from database.load_confirmed_additions import load_all_confirmed_additions
from calculations.stormwater import (
    design_rainfall_intensity, size_roof_drain, size_storm_drain_pipe,
)
from calculations.hydraulics import rational_method_peak_flow
from models import MissingCodeDataError


def _conn(tmp_path):
    conn = init_db(db_path=tmp_path / "test.db", reset=True)
    load_all_workbooks(conn)
    load_all_confirmed_additions(conn)
    return conn


def test_design_rainfall_intensity_10yr_15min(tmp_path):
    conn = _conn(tmp_path)
    r = design_rainfall_intensity(conn, "SAUDI_SBC_701", 10, "15 min", "ST-001")
    # depth(10yr, riyadh_station)=28.7mm, ratio(15min)=0.44 -> 12.628mm / 0.25hr = 50.512 mm/hr
    assert r.result_value == pytest.approx(50.512, abs=0.001)
    assert r.result_unit == "mm/hr"
    assert r.status == "CALCULATED_NOT_APPROVED"


def test_design_rainfall_intensity_100yr_1hr_old_airport_station(tmp_path):
    conn = _conn(tmp_path)
    r = design_rainfall_intensity(conn, "SAUDI_SBC_701", 100, "1 hr", "ST-002",
                                   station="riyadh_old_airport_mm")
    # depth(100yr, old_airport)=56.4mm, ratio(1hr)=0.56 -> 31.584mm / 1hr = 31.584 mm/hr
    assert r.result_value == pytest.approx(31.584, abs=0.001)


def test_design_rainfall_intensity_unknown_return_period_raises(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(MissingCodeDataError):
        design_rainfall_intensity(conn, "SAUDI_SBC_701", 999, "15 min", "ST-003")


def test_design_rainfall_intensity_not_available_for_other_codes(tmp_path):
    """Riyadh rainfall depth is a PROJECT-classified fact for this specific
    project's site -- it must not silently apply to IPC/UPC/Egypt."""
    conn = _conn(tmp_path)
    with pytest.raises(MissingCodeDataError):
        design_rainfall_intensity(conn, "IPC", 10, "15 min", "ST-004")


def test_roof_drain_leader_sizing_rounds_rate_up(tmp_path):
    conn = _conn(tmp_path)
    # 50.51 mm/hr must round UP to the 75 mm/hr column, never down to 50.
    r = size_roof_drain(conn, "SAUDI_SBC_701", 500, 50.512, "ST-005")
    assert r.result_value == 100.0  # 100mm leader: max area at 75mm/hr = 569 m2 >= 500
    assert r.status == "PASS"


def test_roof_drain_leader_sizing_out_of_range_raises(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(MissingCodeDataError):
        size_roof_drain(conn, "SAUDI_SBC_701", 100, 400.0, "ST-006")  # beyond 300 mm/hr max column


def test_storm_drain_pipe_vertical(tmp_path):
    conn = _conn(tmp_path)
    r = size_storm_drain_pipe(conn, "SAUDI_SBC_701", 63.14, "ST-007", orientation="vertical")
    # 63.14 L/s = 3788.4 L/min -> smallest pipe with vertical_drain_lpm >= 3788.4 is 200mm (4230)
    assert r.result_value == 200.0
    assert r.status == "PASS"


def test_storm_drain_pipe_horizontal_needs_valid_slope(tmp_path):
    conn = _conn(tmp_path)
    r = size_storm_drain_pipe(conn, "SAUDI_SBC_701", 5.0, "ST-008", orientation="horizontal", slope_mm_per_m=20)
    assert r.status == "PASS"
    with pytest.raises(MissingCodeDataError):
        size_storm_drain_pipe(conn, "SAUDI_SBC_701", 5.0, "ST-009", orientation="horizontal", slope_mm_per_m=17)


def test_full_chain_rational_method_to_pipe(tmp_path):
    """End-to-end: rainfall intensity -> Rational Method Q=CIA -> pipe size,
    matching the pattern the roof/pipe sizing calcs are meant to be used in."""
    conn = _conn(tmp_path)
    intensity = design_rainfall_intensity(conn, "SAUDI_SBC_701", 10, "15 min", "ST-010")
    peak_flow = rational_method_peak_flow(0.9, intensity.result_value, 500, "ST-011")
    pipe = size_storm_drain_pipe(conn, "SAUDI_SBC_701", peak_flow.result_value, "ST-012", orientation="vertical")
    assert peak_flow.result_value == pytest.approx(63.14, abs=0.01)
    assert pipe.result_value == 200.0
