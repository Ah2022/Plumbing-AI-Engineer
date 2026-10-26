"""
tests/test_bim_exchange.py
----------------------------------
Regression tests for Phase 7's engine-side exchange layer (bim/schemas.py,
bim/exchange.py). Simulates what a pyRevit extractor would emit as a
plain JSON-compatible dict -- no Revit API / pyRevit dependency needed,
which is exactly why this half of Phase 7 is testable and the
bim/pyrevit/ scripts (which DO need a live Revit session) are not.
"""

import pytest

from database.db import init_db
from compliance.rule_loader import load_all_rules
from calculations.hydraulics import hazen_williams_head_loss
from app.db_helpers import save_calculation
from bim.schemas import validate_extract_payload, empty_extract_payload
from bim.exchange import import_revit_extract, export_results_for_revit, InvalidExtractPayload


def _project(tmp_path):
    conn = init_db(db_path=tmp_path / "test.db", reset=True)
    load_all_rules(conn)  # populates `codes` for the projects FK
    cur = conn.execute(
        "INSERT INTO projects (project_name, building_type, code_id) VALUES (?,?,?)",
        ("Revit-linked project", "Hospital", "SAUDI_SBC_701"),
    )
    project_id = cur.lastrowid
    conn.commit()
    return conn, project_id


def _sample_payload():
    payload = empty_extract_payload("SMC3-Plumbing.rvt", "2026-09-09T10:00:00")
    payload["pipes"].append({
        "revit_element_id": "123456", "system": "cold_water",
        "from_node": "CW-Riser-1", "to_node": "CW-Branch-1",
        "length_m": 40.0, "nominal_diameter_mm": 50.0, "level": "L01",
    })
    payload["fixtures"].append({
        "revit_element_id": "223344", "family": "Water Closet - Wall Hung",
        "type_name": "WC-Standard", "level": "L01", "system": "drainage",
        "parameters": {"Mark": "WC-101"},
    })
    return payload


def test_validate_extract_payload_accepts_well_formed_payload():
    payload = _sample_payload()
    assert validate_extract_payload(payload) == []


def test_validate_extract_payload_flags_missing_fields():
    payload = empty_extract_payload("Model.rvt", "2026-09-09T10:00:00")
    payload["pipes"].append({"revit_element_id": "1"})  # missing system/length/diameter
    errors = validate_extract_payload(payload)
    assert any("pipes[0]" in e for e in errors)


def test_validate_extract_payload_flags_invalid_system():
    payload = empty_extract_payload("Model.rvt", "2026-09-09T10:00:00")
    payload["pipes"].append({
        "revit_element_id": "1", "system": "chilled_water",  # not a plumbing system
        "length_m": 10.0, "nominal_diameter_mm": 25.0,
    })
    errors = validate_extract_payload(payload)
    assert any("not one of" in e for e in errors)


def test_import_revit_extract_rejects_invalid_payload(tmp_path):
    conn, project_id = _project(tmp_path)
    bad = {"pipes": [{"revit_element_id": "1"}]}  # missing top-level + pipe fields
    with pytest.raises(InvalidExtractPayload):
        import_revit_extract(conn, project_id, bad)
    # nothing partially imported
    assert conn.execute("SELECT COUNT(*) AS n FROM pipes WHERE project_id=?",
                         (project_id,)).fetchone()["n"] == 0


def test_import_revit_extract_creates_pipe_and_fixture(tmp_path):
    conn, project_id = _project(tmp_path)
    counts = import_revit_extract(conn, project_id, _sample_payload())
    assert counts == {"pipes": 1, "fixtures": 1, "tanks": 0, "pumps": 0}

    pipe = conn.execute("SELECT * FROM pipes WHERE project_id=?", (project_id,)).fetchone()
    assert pipe["revit_element_id"] == "123456"
    assert pipe["system"] == "cold_water"
    assert pipe["length_m"] == 40.0

    fx = conn.execute("SELECT * FROM revit_elements WHERE project_id=?", (project_id,)).fetchone()
    assert fx["element_id"] == "223344"
    assert fx["family"] == "Water Closet - Wall Hung"


def test_import_revit_extract_is_idempotent_on_rerun(tmp_path):
    """Re-running the extractor after a model tweak must UPDATE the existing
    pipe row (same revit_element_id), not create a duplicate."""
    conn, project_id = _project(tmp_path)
    import_revit_extract(conn, project_id, _sample_payload())

    payload2 = _sample_payload()
    payload2["pipes"][0]["length_m"] = 55.0  # engineer changed the run in Revit
    import_revit_extract(conn, project_id, payload2)

    rows = conn.execute("SELECT * FROM pipes WHERE project_id=?", (project_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["length_m"] == 55.0


def test_export_results_for_revit_round_trip(tmp_path):
    """Full loop: import a Revit-linked pipe -> run a real calculation
    against it -> export results keyed by revit_element_id, as the
    pyRevit writer script would consume them."""
    conn, project_id = _project(tmp_path)
    import_revit_extract(conn, project_id, _sample_payload())
    pipe = conn.execute("SELECT pipe_id FROM pipes WHERE project_id=?", (project_id,)).fetchone()

    result = hazen_williams_head_loss(flow_lps=2.5, internal_diameter_mm=50.0, length_m=40.0,
                                       c_factor=150, calc_id="CW-001")
    save_calculation(conn, project_id, result, target_type="pipe", target_id=pipe["pipe_id"])

    payload = export_results_for_revit(conn, project_id)
    assert "123456" in payload["results"]
    r = payload["results"]["123456"]
    assert r["calc_id"] == "CW-001"
    assert r["status"] == result.status
    assert r["result_value"] == result.result_value


def test_export_results_for_revit_omits_elements_without_calculations(tmp_path):
    """A Revit-linked pipe with no saved calculation yet must not appear
    in the results (so the writer script leaves its PLM_* params alone
    instead of clearing or guessing them)."""
    conn, project_id = _project(tmp_path)
    import_revit_extract(conn, project_id, _sample_payload())
    payload = export_results_for_revit(conn, project_id)
    assert payload["results"] == {}
