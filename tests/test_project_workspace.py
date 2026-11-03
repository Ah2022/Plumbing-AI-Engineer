"""Project isolation, independent routing and live-source blockers, using disposable records."""
import json
from pathlib import Path

import pytest
from tests.test_review_workflow import project, saved
from reports.project_workspace import (ensure_workspace_schema, add_member, add_evidence, save_issue,
    rows, project_summary, workflow_state, record_workflow, ROLES, STAGES)
from reports.review_workflow import build_review_packet
from app.model_viewer import geometry_payload, network_payload, apply_network_event
from calculations.network import analyze_water_network


def setup(conn, pid):
    ensure_workspace_schema(conn)
    members = [add_member(conn, pid, 'Reviewer '+str(i), role) for i, role in enumerate(ROLES)]
    ref = add_evidence(conn, pid, 'Design basis', 'DB-01, section 3', 'R1', 'Project')
    return members, ref


def test_workflow_uses_distinct_roles_and_revision_bound_evidence(project):
    conn, pid = project
    members, ref = setup(conn, pid)
    state = workflow_state(conn, pid)
    with pytest.raises(ValueError, match='order'):
        record_workflow(conn, pid, STAGES[1], members[1], ref, 'Checked', state['fingerprint'])
    record_workflow(conn, pid, STAGES[0], members[0], ref, 'Submitted with declared limitations', state['fingerprint'])
    assert workflow_state(conn, pid)['next_stage'] == STAGES[1]
    record_workflow(conn, pid, STAGES[1], members[1], ref, 'Review findings recorded', state['fingerprint'])
    record_workflow(conn, pid, STAGES[2], members[2], ref, 'Coordination review with outstanding items', state['fingerprint'])
    with pytest.raises(ValueError, match='Resolve source blockers'):
        record_workflow(conn, pid, STAGES[3], members[3], ref, 'Approve', state['fingerprint'])
    add_evidence(conn, pid, 'Revised model', 'M-02', 'R2', 'Model')
    new = workflow_state(conn, pid)
    assert new['next_stage'] == STAGES[0] and len(new['events']) == 3 and not new['current']
    with pytest.raises(ValueError, match='Project changed'):
        record_workflow(conn, pid, STAGES[0], members[0], ref, 'Old snapshot', state['fingerprint'])


def test_same_name_cannot_serve_as_own_independent_checker(project):
    conn, pid = project
    members, ref = setup(conn, pid)
    checker = add_member(conn, pid, 'Reviewer 0', 'Checker')
    state = workflow_state(conn, pid)
    record_workflow(conn, pid, STAGES[0], members[0], ref, 'Submitted', state['fingerprint'])
    with pytest.raises(ValueError, match='different named reviewer'):
        record_workflow(conn, pid, STAGES[1], checker, ref, 'Own check', state['fingerprint'])


def test_issue_closure_never_clears_underlying_source_findings(project):
    conn, pid = project
    members, ref = setup(conn, pid)
    source = project_summary(conn, pid)['findings'][0]
    issue = save_issue(conn, pid, title=source['title'], owner_id=members[1], actor_id=members[0],
                       priority='High', due_date='2020-01-01', source_key=source['source_key'], location='L02 / riser R1')
    assert project_summary(conn, pid)['overdue'] == 1
    with pytest.raises(ValueError, match='resolution'):
        save_issue(conn, pid, issue_id=issue, title='Fix source', owner_id=members[1], actor_id=members[1],
                   priority='High', due_date=None, status='Resolved')
    save_issue(conn, pid, issue_id=issue, title=source['title'], owner_id=members[1], actor_id=members[1],
               priority='High', due_date=None, status='Resolved', resolution='Task reviewed; source still needs approval')
    summary = project_summary(conn, pid)
    assert summary['open_issues'] == 0 and source['source_key'] in {f['source_key'] for f in summary['findings']}
    packet = build_review_packet(conn, pid)
    assert len(packet['payload']['coordination']['project_issue_events']) == 2
    assert packet['payload']['coordination']['project_issues'][0]['resolution']


def test_cross_project_owners_actors_issues_and_evidence_are_rejected(project):
    conn, pid = project
    members, ref = setup(conn, pid)
    other = add_member(conn, 2, 'Other reviewer', 'Designer')
    for field in ('owner_id', 'actor_id'):
        args = dict(title='Task', owner_id=members[0], actor_id=members[0], priority='Low', due_date=None)
        args[field] = other
        with pytest.raises(ValueError, match='belonging'):
            save_issue(conn, pid, **args)
    other_ref = add_evidence(conn, 2, 'Other evidence', 'X', 'R1', 'Other')
    with pytest.raises(ValueError, match='registered to this project'):
        record_workflow(conn, pid, STAGES[0], members[0], other_ref, 'Review', workflow_state(conn, pid)['fingerprint'])


def test_changed_calculation_invalidates_routing(project):
    conn, pid = project
    members, ref = setup(conn, pid)
    saved(conn, pid)
    before = workflow_state(conn, pid)
    record_workflow(conn, pid, STAGES[0], members[0], ref, 'Review', before['fingerprint'])
    conn.execute("UPDATE calculations SET selected_value=999 WHERE project_id=?", (pid,))
    assert workflow_state(conn, pid)['next_stage'] == STAGES[0]


def test_saved_mapping_populates_model_health_and_live_diagnostics(project):
    pytest.importorskip('ifcopenshell')
    from bim.model_intake import inspect_model
    from bim.mapping import initial_mapping, initial_boundaries, snapshot, save_snapshot
    conn, pid = project
    setup(conn, pid)
    path = Path(__file__).parents[1]/'examples/model_pilot.ifc'
    inventory = inspect_model(path.read_bytes(), path.name)
    packet = snapshot(inventory, initial_mapping(inventory), initial_boundaries(inventory), 'Synthetic reviewer', 'MODEL R1')
    save_snapshot(conn, pid, packet)
    summary = project_summary(conn, pid)
    assert summary['model_health'][0]['objects'] == 3 and summary['model_health'][0]['geometry'] == 2
    assert any(f['source_key'].startswith('model:') for f in summary['findings'])


def test_viewer_uses_only_finite_extracted_axes():
    inventory = dict(objects=[
        dict(source_id='pipe', system='CW', start_xyz_m=[0,0,0], end_xyz_m=[3,0,2]),
        dict(source_id='missing', system='CW'),
        dict(source_id='invalid', system='HW', start_xyz_m=[0,0,0], end_xyz_m=[float('nan'),1,2])])
    payload, selected = geometry_payload(inventory)
    assert len(payload['objects']) == 1 and payload['missing_geometry'] == 2
    assert geometry_payload(inventory, 'HW')[0]['missing_geometry'] == 1
    assert geometry_payload(inventory, query='pipe')[1][0]['source_id'] == 'pipe'


def test_schematic_layout_does_not_change_hydraulic_results():
    model = json.loads((Path(__file__).parents[1]/'examples/water_network.json').read_text())
    moved = apply_network_event(model, dict(action='move', id='S', xy=[350,100]))
    assert network_payload(moved)['nodes'][0]['xyz'] == [350,100,0]
    assert 'schematic_layout' not in model
    before, after = analyze_water_network(model), analyze_water_network(moved)
    for key in ('minimum_pressure_margin_m', 'pipes', 'terminals', 'technical_status'):
        assert before[key] == after[key]
    with pytest.raises(ValueError, match='position'):
        apply_network_event(model, dict(action='move', id='S', xy=[float('inf'),0]))
