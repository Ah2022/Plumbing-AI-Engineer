"""
bim/exchange.py  —  Phase 7
--------------------------------
Engine-side half of the Revit exchange (spec Section E). Runs standalone
(sqlite3 + stdlib only, importable from a pyRevit CPython3 script or from
the Streamlit app) -- never talks to the Revit API directly, so it's
fully testable outside Revit. See bim/schemas.py for the JSON contract
and bim/pyrevit/ for the Revit-side scripts that produce/consume it.

    import_revit_extract()      Revit extract JSON  -> pipes/tanks/pumps/
                                 revit_elements rows (upsert by
                                 revit_element_id / element_id)
    export_results_for_revit()  calculations (+status) -> Results JSON,
                                 keyed by revit_element_id, for the
                                 pyRevit writer script to apply
"""

from __future__ import annotations

from bim.schemas import validate_extract_payload, PLM_PARAMETER_NAMES


class InvalidExtractPayload(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid Revit extract payload:\n  " + "\n  ".join(errors))


def import_revit_extract(conn, project_id: int, payload: dict) -> dict:
    """
    Ingests a pyRevit extractor payload. Validates first (spec Section 30:
    stop and report rather than partially import). Upserts by
    revit_element_id so re-running the extractor after a model change
    updates existing rows instead of duplicating them.
    """
    errors = validate_extract_payload(payload)
    if errors:
        raise InvalidExtractPayload(errors)

    counts = {"pipes": 0, "fixtures": 0, "tanks": 0, "pumps": 0}

    for pipe in payload.get("pipes", []):
        existing = conn.execute(
            "SELECT pipe_id FROM pipes WHERE project_id=? AND revit_element_id=?",
            (project_id, pipe["revit_element_id"]),
        ).fetchone()
        pipe_id = existing["pipe_id"] if existing else f"RVT-{pipe['revit_element_id']}"
        conn.execute(
            """INSERT INTO pipes (pipe_id, project_id, system, from_node, to_node, length_m,
                 nominal_diameter_mm, flow_lps, elevation_diff_m, level, revit_element_id, slope_percent)
               VALUES (:pipe_id,:project_id,:system,:from_node,:to_node,:length_m,
                 :nominal_diameter_mm,:flow_lps,:elevation_diff_m,:level,:revit_element_id,:slope_percent)
               ON CONFLICT(pipe_id) DO UPDATE SET
                 system=excluded.system, length_m=excluded.length_m,
                 nominal_diameter_mm=excluded.nominal_diameter_mm, level=excluded.level,
                 slope_percent=excluded.slope_percent""",
            {
                "pipe_id": pipe_id, "project_id": project_id, "system": pipe["system"],
                "from_node": pipe.get("from_node"), "to_node": pipe.get("to_node"),
                "length_m": pipe["length_m"], "nominal_diameter_mm": pipe["nominal_diameter_mm"],
                "flow_lps": pipe.get("flow_lps"), "elevation_diff_m": pipe.get("elevation_diff_m"),
                "level": pipe.get("level"), "revit_element_id": pipe["revit_element_id"],
                "slope_percent": pipe.get("slope_percent"),
            },
        )
        counts["pipes"] += 1

    for tank in payload.get("tanks", []):
        existing = conn.execute(
            "SELECT tank_id FROM tanks WHERE project_id=? AND revit_element_id=?",
            (project_id, tank["revit_element_id"]),
        ).fetchone()
        if existing:
            conn.execute("UPDATE tanks SET tank_type=? WHERE tank_id=?",
                         (tank["tank_type"], existing["tank_id"]))
        else:
            conn.execute(
                "INSERT INTO tanks (project_id, tank_type, revit_element_id, status) VALUES (?,?,?,?)",
                (project_id, tank["tank_type"], tank["revit_element_id"], "PENDING_SIZING"),
            )
        counts["tanks"] += 1

    for pump in payload.get("pumps", []):
        existing = conn.execute(
            "SELECT pump_id FROM pumps WHERE project_id=? AND revit_element_id=?",
            (project_id, pump["revit_element_id"]),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO pumps (project_id, revit_element_id, status) VALUES (?,?,?)",
                (project_id, pump["revit_element_id"], "PENDING_SIZING"),
            )
        counts["pumps"] += 1

    for fx in payload.get("fixtures", []):
        existing = conn.execute(
            "SELECT id FROM revit_elements WHERE project_id=? AND element_id=?",
            (project_id, fx["revit_element_id"]),
        ).fetchone()
        params_json = _to_json(fx.get("parameters", {}))
        if existing:
            conn.execute(
                "UPDATE revit_elements SET family=?, type_name=?, level=?, parameters_json=?, "
                "last_synced=CURRENT_TIMESTAMP WHERE id=?",
                (fx["family"], fx["type_name"], fx.get("level"), params_json, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO revit_elements (project_id, element_id, category, system, family,
                     type_name, level, parameters_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (project_id, fx["revit_element_id"], "PlumbingFixtures", fx.get("system"),
                 fx["family"], fx["type_name"], fx.get("level"), params_json),
            )
        counts["fixtures"] += 1

    conn.commit()
    return counts


def export_results_for_revit(conn, project_id: int) -> dict:
    """
    Builds the Results payload for the pyRevit writer script: for every
    Revit-linked pipe/tank/pump, the MOST RECENT saved calculation
    targeting it (by calc_id, which is assigned in ascending creation
    order per app/db_helpers.next_calc_id -- highest calc_id per element
    is the latest run). Elements with no saved calculation yet are
    omitted, not filled with a fake status -- the writer script must
    leave those elements' PLM_* parameters untouched rather than clear
    or guess them.
    """
    results = {}

    for kind, table, id_col in (
        ("pipe", "pipes", "pipe_id"),
        ("tank", "tanks", "tank_id"),
        ("pump", "pumps", "pump_id"),
    ):
        elements = conn.execute(
            f"SELECT {id_col} AS eid, revit_element_id FROM {table} "
            f"WHERE project_id=? AND revit_element_id IS NOT NULL",
            (project_id,),
        ).fetchall()
        for el in elements:
            calc = conn.execute(
                """SELECT calc_id, calc_type, status, required_value, selected_value,
                          result_value, result_unit, reference
                   FROM calculations
                   WHERE project_id=? AND target_type=? AND target_id=?
                   ORDER BY calc_id DESC LIMIT 1""",
                (project_id, kind, str(el["eid"])),
            ).fetchone()
            if calc is None:
                continue
            results[el["revit_element_id"]] = {
                "calc_id": calc["calc_id"],
                "calc_type": calc["calc_type"],
                "status": calc["status"],
                "required_value": calc["required_value"],
                "selected_value": calc["selected_value"],
                "result_value": calc["result_value"],
                "result_unit": calc["result_unit"],
                "reference": calc["reference"],
            }

    return {
        "project_id": project_id,
        "plm_parameter_names": PLM_PARAMETER_NAMES,
        "results": results,
    }


def _to_json(d: dict) -> str:
    import json
    return json.dumps(d)


if __name__ == "__main__":
    from database.db import get_connection
    conn = get_connection()
    pid_row = conn.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
    if pid_row is None:
        print("No project found — run tests/demo_project.py first.")
    else:
        payload = export_results_for_revit(conn, pid_row["project_id"])
        print(f"Results for {len(payload['results'])} Revit-linked element(s):")
        for element_id, r in payload["results"].items():
            print(f"  {element_id}: {r['calc_id']} -> {r['status']}")
    conn.close()
