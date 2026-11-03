from tests.test_streamlit_app import fresh_app, _create_project, navigate
from reports.project_workspace import add_member, add_evidence, ROLES


def test_dashboard_has_six_workspaces_and_project_actions(fresh_app):
    at = _create_project(fresh_app)
    navigate(at, 'Project dashboard')
    assert not at.exception
    assert len(at.sidebar.radio[0].options) == 6
    assert {m.label for m in at.metric} >= {'Source blockers','Open issues','Unresolved assumptions','Current calculations'}
    next(b for b in at.button if b.label == 'Open approval workflow').click().run(timeout=30)
    assert not at.exception and any(h.value == 'Approval workflow' for h in at.header)


def test_create_and_resolve_assigned_issue(fresh_app):
    at = _create_project(fresh_app)
    conn = at.session_state['conn']
    add_member(conn, 1, 'Synthetic coordinator', 'BIM coordinator')
    navigate(at, 'Issues')
    next(t for t in at.text_input if t.label == 'Issue title').set_value('Review open riser end')
    next(t for t in at.text_input if t.label == 'Model object / level / location').set_value('L03 / P-12')
    next(b for b in at.button if b.label == 'Save issue').click().run(timeout=30)
    assert not at.exception
    issue = conn.execute('SELECT * FROM project_issues').fetchone()
    assert issue['location'] == 'L03 / P-12'
    next(s for s in at.selectbox if s.label == 'Create or update issue').set_value(issue['issue_id']).run(timeout=30)
    next(s for s in at.selectbox if s.label == 'Issue status').set_value('Resolved')
    next(t for t in at.text_area if t.label == 'Resolution / evidence').set_value('Confirmed intentional terminal; see M-01 R2')
    next(b for b in at.button if b.label == 'Save issue').click().run(timeout=30)
    assert not at.exception and conn.execute('SELECT status FROM project_issues').fetchone()[0] == 'Resolved'
    assert conn.execute('SELECT COUNT(*) FROM project_issue_events').fetchone()[0] == 2


def test_workflow_ui_records_submission_but_no_engineering_approval(fresh_app):
    at = _create_project(fresh_app)
    conn = at.session_state['conn']
    for i, role in enumerate(ROLES):
        add_member(conn, 1, 'Synthetic reviewer '+str(i), role)
    add_evidence(conn, 1, 'Design basis', 'DB-01', 'R1', 'Project')
    navigate(at, 'Approval workflow')
    next(t for t in at.text_area if t.label == 'Review decision and scope').set_value('Design submitted with listed limitations')
    next(c for c in at.checkbox if c.label.startswith('I reviewed this project snapshot')).set_value(True)
    next(b for b in at.button if b.label == 'Record design submission').click().run(timeout=30)
    assert not at.exception and conn.execute('SELECT COUNT(*) FROM project_workflow_events').fetchone()[0] == 1
    assert any(b.label == 'Record independent check' for b in at.button)
    assert any('Approval blocked' in w.value for w in at.warning)


def test_graphical_editor_adds_and_connects_nodes_without_json(fresh_app):
    at = _create_project(fresh_app)
    navigate(at, 'Network Review')
    assert not at.exception
    next(s for s in at.segmented_control if s.label == 'Graph editing task').set_value('Add node').run(timeout=30)
    next(t for t in at.text_input if t.label == 'New node ID').set_value('J2')
    next(b for b in at.button if b.label == 'Add node').click().run(timeout=30)
    assert not at.exception
    next(s for s in at.segmented_control if s.label == 'Graph editing task').set_value('Connect nodes').run(timeout=30)
    next(t for t in at.text_input if t.label == 'New pipe ID').set_value('P2-new')
    next(s for s in at.selectbox if s.label == 'From node').set_value('J')
    next(s for s in at.selectbox if s.label == 'To node').set_value('J2')
    next(b for b in at.button if b.label == 'Connect nodes').click().run(timeout=30)
    assert not at.exception
    scope = at.session_state['_network_scope']
    model = at.session_state['network_draft_' + scope]
    assert any(p['id'] == 'P2-new' and p['to_node'] == 'J2' for p in model['pipes'])
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0] == 0
