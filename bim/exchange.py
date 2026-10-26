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
    """Atomic, project/model-scoped import. Legacy unassigned rows are retained."""
    import hashlib
    errors=validate_extract_payload(payload)
    if errors: raise InvalidExtractPayload(errors)
    if not conn.execute('SELECT 1 FROM projects WHERE project_id=?',(project_id,)).fetchone():
        raise InvalidExtractPayload(['Unknown project'])
    identity=payload.get('revit_model_id') or payload['revit_model_name']
    model_key=hashlib.sha256(identity.encode()).hexdigest()
    counts={key:len(payload.get(key,[])) for key in ('pipes','fixtures','tanks','pumps')}
    conn.execute('SAVEPOINT model_import')
    try:
        for pipe in payload.get('pipes',[]):
            eid=pipe['revit_element_id']
            existing=conn.execute('SELECT pipe_id FROM pipes WHERE project_id=? AND revit_model_key=? AND revit_element_id=?',(project_id,model_key,eid)).fetchone()
            pipe_id=existing['pipe_id'] if existing else f'RVT-P{project_id}-{model_key}-{eid}'
            conn.execute('''INSERT INTO pipes(pipe_id,project_id,system,from_node,to_node,length_m,nominal_diameter_mm,
                flow_lps,elevation_diff_m,level,revit_element_id,slope_percent,revit_model_key)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(pipe_id) DO UPDATE SET
                system=excluded.system,from_node=excluded.from_node,to_node=excluded.to_node,
                length_m=excluded.length_m,nominal_diameter_mm=excluded.nominal_diameter_mm,
                flow_lps=excluded.flow_lps,elevation_diff_m=excluded.elevation_diff_m,level=excluded.level,
                slope_percent=excluded.slope_percent''', (pipe_id,project_id,pipe['system'],pipe.get('from_node'),pipe.get('to_node'),
                pipe['length_m'],pipe['nominal_diameter_mm'],pipe.get('flow_lps'),pipe.get('elevation_diff_m'),
                pipe.get('level'),eid,pipe.get('slope_percent'),model_key))
            # Model edits invalidate previous results targeting this element.
            conn.execute("UPDATE calculations SET is_current=0 WHERE project_id=? AND target_type='pipe' AND target_id=?",(project_id,pipe_id))
        for group,table,pk in [('tanks','tanks','tank_id'),('pumps','pumps','pump_id')]:
            for item in payload.get(group,[]):
                eid=item['revit_element_id']
                old=conn.execute(f'SELECT {pk} FROM {table} WHERE project_id=? AND revit_model_key=? AND revit_element_id=?',(project_id,model_key,eid)).fetchone()
                if old:
                    if group=='tanks': conn.execute('UPDATE tanks SET tank_type=? WHERE tank_id=?',(item['tank_type'],old[0]))
                    conn.execute('UPDATE calculations SET is_current=0 WHERE project_id=? AND target_type=? AND target_id=?',(project_id,group[:-1],str(old[0])))
                elif group=='tanks':
                    conn.execute("INSERT INTO tanks(project_id,tank_type,revit_element_id,revit_model_key,status) VALUES (?,?,?,?,'PENDING_SIZING')",(project_id,item['tank_type'],eid,model_key))
                else:
                    conn.execute("INSERT INTO pumps(project_id,revit_element_id,revit_model_key,status) VALUES (?,?,?,'PENDING_SIZING')",(project_id,eid,model_key))
        for fx in payload.get('fixtures',[]):
            old=conn.execute('SELECT id FROM revit_elements WHERE project_id=? AND revit_model_key=? AND element_id=?',(project_id,model_key,fx['revit_element_id'])).fetchone()
            values=(fx['family'],fx['type_name'],fx.get('system'),fx.get('level'),_to_json(fx.get('parameters',{})))
            if old: conn.execute('UPDATE revit_elements SET family=?,type_name=?,system=?,level=?,parameters_json=?,last_synced=CURRENT_TIMESTAMP WHERE id=?',(*values,old['id']))
            else: conn.execute("INSERT INTO revit_elements(family,type_name,system,level,parameters_json,project_id,element_id,category,revit_model_key) VALUES (?,?,?,?,?,?,?,'PlumbingFixtures',?)",(*values,project_id,fx['revit_element_id'],model_key))
        conn.execute('UPDATE compliance_checks SET is_current=0 WHERE project_id=?',(project_id,))
        conn.execute('UPDATE calculations SET is_current=0 WHERE project_id=?',(project_id,))
        conn.execute('DELETE FROM qaqc_results WHERE project_id=?',(project_id,))
        conn.execute('RELEASE SAVEPOINT model_import')
    except BaseException:
        conn.execute('ROLLBACK TO SAVEPOINT model_import');conn.execute('RELEASE SAVEPOINT model_import');raise
    conn.commit()
    return counts


def export_results_for_revit(conn, project_id: int, model_key=None) -> dict:
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
    keys={r[0] for r in conn.execute('SELECT DISTINCT revit_model_key FROM pipes WHERE project_id=? UNION SELECT DISTINCT revit_model_key FROM tanks WHERE project_id=? UNION SELECT DISTINCT revit_model_key FROM pumps WHERE project_id=?',(project_id,project_id,project_id))}
    if model_key is None:
        if len(keys)>1: raise ValueError('Multiple model identities: select model_key explicitly')
        model_key=next(iter(keys),None)
    elif model_key not in keys: raise ValueError('Unknown model_key for this project')
    results = {}

    for kind, table, id_col in (
        ("pipe", "pipes", "pipe_id"),
        ("tank", "tanks", "tank_id"),
        ("pump", "pumps", "pump_id"),
    ):
        elements = conn.execute(
            f"SELECT {id_col} AS eid, revit_element_id FROM {table} "
            f"WHERE project_id=? AND revit_model_key IS ? AND revit_element_id IS NOT NULL",
            (project_id,model_key),
        ).fetchall()
        for el in elements:
            candidates = conn.execute(
                """SELECT calc_id, calc_type, status, required_value, selected_value,
                          result_value, result_unit, reference,is_current,governance_json,review_status
                   FROM calculations
                   WHERE project_id=? AND target_type=? AND target_id=?
                   ORDER BY created_at DESC, rowid DESC""",
                (project_id, kind, str(el["eid"])),
            ).fetchall()
            from compliance.governance import calculation_is_current
            current=[c for c in candidates if calculation_is_current(conn,project_id,c)]
            if not current: continue
            calc=current[0]
            rank={'FAIL':5,'MISSING_DATA':4,'ASSUMED':3,'WARNING':3,'CALCULATED_NOT_APPROVED':2,'PASS':1}
            technical=max((c['status'] for c in current),key=lambda status:rank[status])
            review='VERIFIED' if all(c['review_status']=='VERIFIED' for c in current) else 'REVIEW_REQUIRED'
            results[el["revit_element_id"]] = {
                "calc_id": calc["calc_id"],
                "calc_type": calc["calc_type"],
                "status": 'WARNING' if technical == 'PASS' and review != 'VERIFIED' else technical,
                "technical_status": technical,
                "check_ids": [c['calc_id'] for c in current],
                "review_status": review,
                "required_value": calc["required_value"],
                "selected_value": calc["selected_value"],
                "result_value": calc["result_value"],
                "result_unit": calc["result_unit"],
                "reference": calc["reference"],
            }

    return {
        "project_id": project_id,
        "model_key": model_key,
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
