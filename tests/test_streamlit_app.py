"""
tests/test_streamlit_app.py
------------------------------
Headless UI regression test using Streamlit's official AppTest harness
(streamlit.testing.v1). Actually executes app/streamlit_app.py's script
and every page's real buttons — this is what caught two real bugs during
development (SQLite thread-affinity across Streamlit reruns, and a wrong
column name in the Report page's query) that a syntax check alone would
have missed.
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).parent.parent / "app" / "streamlit_app.py"


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    # Point the app at a throwaway DB file for this test only.
    monkeypatch.chdir(Path(__file__).parent.parent)
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("PLUMBING_ENGINE_DB_PATH", str(db_path))
    at = AppTest.from_file(str(APP_PATH))
    at.run(timeout=30)
    try:
        yield at
    finally:
        if "conn" in at.session_state:
            at.session_state["conn"].close()


def _create_project(at):
    btn = [b for b in at.button if b.label == "Create project"]
    btn[0].click().run(timeout=30)
    return at


def test_project_page_loads_without_exceptions(fresh_app):
    assert list(fresh_app.exception) == []


def test_create_project_succeeds(fresh_app):
    at = _create_project(fresh_app)
    assert list(at.exception) == []
    assert at.session_state["project_id"] == 1


@pytest.mark.parametrize("page", [
    "Design Basis", "Fixtures & Water", "Drainage & Vent",
    "Hot Water", "Tanks", "Pumps", "Stormwater",
    "Code Compliance / QA-QC", "QA/QC Dashboard", "Report / Export",
])
def test_every_page_loads_without_exceptions(fresh_app, page):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value(page).run(timeout=30)
    assert list(at.exception) == []


def test_velocity_check_with_manufacturer_material_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Fixtures & Water").run(timeout=30)
    mat = [t for t in at.text_input if t.label == "Material (optional, e.g. PPR)"][0]
    mat.set_value("PPR")
    run_btn = [b for b in at.button if b.label == "Run velocity check"][0]
    run_btn.click().run(timeout=30)
    assert list(at.exception) == []
    assert any("PASS" in m.value for m in at.markdown)


def test_drainage_sizing_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Drainage & Vent").run(timeout=30)
    btn = [b for b in at.button if b.label == "Size the pipe"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_compliance_run_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Code Compliance / QA-QC").run(timeout=30)
    btn = [b for b in at.button if "Run full compliance" in b.label][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_pipe_sizing_from_demand_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Fixtures & Water").run(timeout=30)
    btn = [b for b in at.button if b.label == "Size the pipe from demand"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_hot_water_temperature_check_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Hot Water").run(timeout=30)
    btn = [b for b in at.button if b.label == "Check"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_heater_capacity_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Hot Water").run(timeout=30)
    btn = [b for b in at.button if b.label == "Calculate heater capacity"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_tank_sizing_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Tanks").run(timeout=30)
    btn = [b for b in at.button if b.label == "Size the tank"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_pump_duty_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Pumps").run(timeout=30)
    btn = [b for b in at.button if b.label == "Calculate duty point"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []


def test_stormwater_rainfall_intensity_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Stormwater").run(timeout=30)
    btn = [b for b in at.button if b.label == "Calculate intensity"][0]
    btn.click().run(timeout=30)
    assert list(at.exception) == []
    assert any("Design intensity" in m.value for m in at.markdown)


def test_stormwater_full_chain_buttons_succeed(fresh_app):
    """Runs all four Stormwater steps in sequence, as an engineer would."""
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Stormwater").run(timeout=30)

    at = [b for b in at.button if b.label == "Calculate intensity"][0].click().run(timeout=30)
    assert list(at.exception) == []

    at = [b for b in at.button if b.label == "Calculate peak flow"][0].click().run(timeout=30)
    assert list(at.exception) == []
    assert any("Peak flow" in m.value for m in at.markdown)

    at = [b for b in at.button if b.label == "Size the leader"][0].click().run(timeout=30)
    assert list(at.exception) == []
    assert any("Leader size" in m.value for m in at.markdown)

    at = [b for b in at.button if b.label == "Size the pipe"][0].click().run(timeout=30)
    assert list(at.exception) == []
    assert any("Pipe size" in m.value for m in at.markdown)


def test_qaqc_dashboard_button_succeeds(fresh_app):
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("QA/QC Dashboard").run(timeout=30)
    btn = [b for b in at.button if "Run QA/QC checks" in b.label][0]
    at = btn.click().run(timeout=30)
    assert list(at.exception) == []
    # 6 checks defined in reports/qaqc_dashboard.py -> dataframe should be populated
    assert len(at.dataframe) >= 1


def test_report_page_download_after_qaqc_and_compliance(fresh_app):
    """Report page must render the Markdown report without exceptions even
    after other pages have populated calculations/compliance/qaqc data."""
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Code Compliance / QA-QC").run(timeout=30)
    at = [b for b in at.button if "Run full compliance" in b.label][0].click().run(timeout=30)
    at.sidebar.radio[0].set_value("QA/QC Dashboard").run(timeout=30)
    at = [b for b in at.button if "Run QA/QC checks" in b.label][0].click().run(timeout=30)
    at.sidebar.radio[0].set_value("Report / Export").run(timeout=30)
    assert list(at.exception) == []


def test_fixture_unit_dropdown_add_and_total_succeeds(fresh_app):
    """Default project code is SAUDI_SBC_701, which has real WSFU choices --
    the dropdown path (not the manual-entry fallback) should be exercised."""
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value("Fixtures & Water").run(timeout=30)
    assert len(at.selectbox) >= 1
    at.selectbox[0].select_index(0).run(timeout=30)
    add_btn = [b for b in at.button if b.label == "Add to list"][0]
    at = add_btn.click().run(timeout=30)
    assert list(at.exception) == []
    calc_btn = [b for b in at.button if b.label == "Calculate total fixture units"][0]
    at = calc_btn.click().run(timeout=30)
    assert list(at.exception) == []
    assert any("Total cold-water FU" in s.value for s in at.success)
