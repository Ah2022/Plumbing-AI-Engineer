"""A guided project front door over the existing calculation and review tools."""
import datetime as dt
import json
import sqlite3

import streamlit as st
from reports.project_workspace import (ROLES, PRIORITIES, STATUSES, STAGES, rows, add_member,
    add_evidence, save_issue, project_summary, workflow_state, record_workflow)

WORKSPACES = {
    'Overview': ['Project dashboard'],
    'Project setup': ['Project', 'Code Profiles', 'Design Basis', 'Team & evidence'],
    'Models & networks': ['CAD / IFC Checks', 'Revit Exchange', 'Network Review'],
    'Calculations': ['Fixtures & Water', 'Drainage & Vent', 'Hot Water', 'Tanks', 'Pumps', 'Stormwater',
                     'Engineering Modules', 'Calculation Sheets'],
    'Review & approval': ['Issues', 'Approval workflow', 'Code Compliance / QA-QC', 'QA/QC Dashboard', 'Release Readiness'],
    'Reports': ['Report / Export'],
}


def go(page):
    group = next(k for k, values in WORKSPACES.items() if page in values)
    st.session_state['workspace'] = group
    st.session_state['tool_' + group] = page


def action(label, page, key, **kwargs):
    st.button(label, key=key, on_click=go, args=(page,), **kwargs)


def locate_model(source_id):
    st.session_state['workspace_model_focus'] = dict(project_id=st.session_state.get('project_id'), source_id=source_id)
    go('CAD / IFC Checks')


def reviewer_field(label, key, value='', roles=None):
    conn, pid = st.session_state.conn, st.session_state.get('project_id')
    members = rows(conn, 'project_team', pid) if pid else []
    members = [m for m in members if not roles or m['role'] in roles]
    if not members:
        return st.text_input(label, value=value, key=key, help='Register reusable reviewers in Project setup → Team & evidence.')
    options = ['Enter another reviewer'] + [m['name'] + ' · ' + m['role'] for m in members]
    chosen = st.selectbox(label, options, index=0, key=key + '_member',
                          help='Team roles attribute work. They do not authenticate an identity or professional qualification.')
    if chosen == options[0]:
        return st.text_input(label + ' name', value=value, key=key)
    return members[options.index(chosen)-1]['name']


def evidence_field(label, key, value=''):
    pid = st.session_state.get('project_id')
    records = rows(st.session_state.conn, 'project_evidence', pid) if pid else []
    if not records:
        return st.text_input(label, value=value, key=key,
                             help='Use a document identifier, revision and section. Reuse references from Team & evidence.')
    options = ['Enter another reference'] + [r['title'] + ' · ' + r['revision'] for r in records]
    picked = st.selectbox(label, range(len(options)), format_func=lambda i: options[i], key=key + '_library')
    if not picked:
        return st.text_input(label + ' reference', value=value, key=key)
    r = records[picked-1]
    return f"{r['title']} | {r['reference']} | Rev {r['revision']}"


def project_context():
    """Persistent project switcher; never silently picks a different project."""
    conn = st.session_state.conn
    projects = [dict(r) for r in conn.execute('SELECT * FROM projects ORDER BY project_id')]
    pid = st.session_state.get('project_id')
    ids = [None] + [r['project_id'] for r in projects]
    names = {r['project_id']: f"#{r['project_id']} · {r['project_name']} · {r['code_id']}" for r in projects}
    st.session_state['_active_project_picker'] = pid if pid in ids else None

    def switch():
        from app.code_profiles_page import clear_result_session
        clear_result_session()
        st.session_state['project_id'] = st.session_state['_active_project_picker']

    st.sidebar.selectbox('Active project', ids, format_func=lambda i: names.get(i, 'Select a project'),
        key='_active_project_picker', on_change=switch)
    if not projects:
        st.sidebar.caption('Create your first project in Project setup.')
    return pid


def page_dashboard():
    st.title('Project overview')
    st.caption('Set the basis. Map the model. Calculate. Resolve findings. Review the evidence.')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Choose an active project in the sidebar, or create a project to begin.')
        action('Create or open a project', 'Project', 'dashboard_start', type='primary', icon=':material/add:')
        st.subheader('Your project workflow')
        st.markdown('**01 Setup → 02 Model intake → 03 Mapping → 04 Calculation → 05 QA/QC → 06 Approval & issue**')
        return
    s = project_summary(st.session_state.conn, pid)
    p = s['project']
    st.subheader(p['project_name'])
    st.caption(f"{p.get('project_number') or 'Project number pending'} · {p['code_id']} · Revision {p.get('revision') or '—'}")
    state = workflow_state(st.session_state.conn, pid, s)
    st.badge(state['status'], color='orange' if state['blockers'] else 'blue', icon=':material/fact_check:')
    cols = st.columns(4)
    for col, label, value, hint in zip(cols,
        ['Source blockers', 'Open issues', 'Unresolved assumptions', 'Current calculations'],
        [s['source_blockers'], s['open_issues'], s['assumptions'], s['current_calculations']],
        ['Live data and governance findings; closing a task does not clear them.', 'Assigned project tasks, including unresolved findings.',
         'Assumptions awaiting an explicit engineering decision.', 'Results current under the project basis; this does not mean approved.']):
        col.metric(label, value, help=hint, border=True)
    if s['overdue']:
        st.warning(f"{s['overdue']} project issue(s) are overdue. Open the issue register to review owners and due dates.")
    st.subheader('Guided workflow')
    stages = [
        ('01 · Project setup', 'Code Profiles', 'Confirm edition, adoption, criteria and responsibility.', bool(s['evidence']) and len({m['role'] for m in s['team']}) == 4),
        ('02 · Model intake', 'CAD / IFC Checks', 'Inspect IFC/Revit or drawing evidence and units.', bool(s['model_health'])),
        ('03 · Mapping', 'CAD / IFC Checks', 'Review service, bore, flow, connectivity and source references.', bool(s['model_health']) and all(m['status'] not in ('FAIL', 'INVALID_SNAPSHOT', 'MAPPING_NOT_SAVED') for m in s['model_health'])),
        ('04 · Calculation', 'Fixtures & Water', 'Run checks for the project scope and save the trace.', s['current_calculations'] > 0),
        ('05 · QA/QC', 'Issues', 'Resolve source findings; assign and track remaining work.', not s['approval_blockers']),
        ('06 · Approval & issue', 'Approval workflow', 'Route a revision through four independent review roles.', state['next_stage'] is None),
    ]
    st.caption('Milestones show recorded activity. Scope completion and engineering acceptance require review.')
    for offset in (0, 3):
        for col, (title, target, detail, done) in zip(st.columns(3), stages[offset:offset+3]):
            with col.container(border=True, height='stretch'):
                st.markdown('**' + title + '**')
                st.badge('Recorded' if done else 'Action needed', color='blue' if done else 'gray')
                st.caption(detail)
                action('Open', target, 'step_' + title, width='stretch')
    left, right = st.columns([3, 2])
    with left:
        st.subheader('Priority actions')
        if not s['findings']:
            st.info('No source blockers detected. Review declared scope and independent engineering evidence before approval.')
        for i, f in enumerate(s['findings'][:6]):
            with st.container(border=True):
                st.markdown(f"**{f['title']}**")
                if f['location']:
                    st.caption('Location / object: ' + f['location'])
                action('Review source', f['target'], 'source_action_' + str(i), icon=':material/arrow_forward:')
        if len(s['findings']) > 6:
            action(f"View all {len(s['findings'])} source findings", 'Issues', 'all_findings')
    with right:
        st.subheader('Model health')
        if not s['model_health']:
            st.info('No saved model diagnostic snapshot. For a calculation-only project, document that scope in the design basis.')
        for model in s['model_health']:
            with st.container(border=True):
                st.markdown('**' + model['model'] + '**')
                st.caption(f"{model['objects']} objects · {model['geometry']} extracted axes · {model['status'].replace('_', ' ').lower()}")
        action('Inspect model', 'CAD / IFC Checks', 'health_model', width='stretch')
        st.subheader('Next review stage')
        st.write(state['next_stage'] or 'All routing stages recorded')
        st.caption('Review routing is tied to the current project snapshot. Data changes require fresh review.')
        action('Open approval workflow', 'Approval workflow', 'dashboard_approval', width='stretch')


def page_team():
    st.header('Team & evidence')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Select or create a project first.'); return
    conn = st.session_state.conn
    st.caption('Register once, reuse in mappings and review forms. Roles attribute responsibilities; this local workbench does not authenticate users or provide digital signatures.')
    view = st.segmented_control('Register', ['Team', 'Evidence'], default='Team', key=f'register_{pid}')
    if view == 'Team':
        st.caption('Designer prepares the design; Checker independently checks; BIM coordinator reviews model coordination; Approver authorizes the reviewed revision.')
        records = rows(conn, 'project_team', pid)
        if records:
            st.dataframe([{k: r[k] for k in ('name', 'role', 'credentials')} for r in records], hide_index=True, width='stretch', alt='Project team and review responsibilities')
        with st.form(f'team_add_{pid}', clear_on_submit=True):
            name = st.text_input('Team member name', max_chars=120)
            role = st.selectbox('Responsibility', ROLES)
            credentials = st.text_input('Credentials / organization', max_chars=500)
            if st.form_submit_button('Add team member', type='primary'):
                try:
                    add_member(conn, pid, name, role, credentials); st.rerun()
                except (ValueError, sqlite3.IntegrityError) as error:
                    st.error('Check the name and responsibility. This combination may already be registered.' if isinstance(error, sqlite3.IntegrityError) else str(error))
    elif view == 'Evidence':
        records = rows(conn, 'project_evidence', pid)
        if records:
            st.dataframe([{k: r[k] for k in ('title', 'reference', 'revision', 'category')} for r in records], hide_index=True, width='stretch', alt='Reusable project evidence references and revisions')
        st.caption('A register entry is a reference locator, not proof that the source is authenticated or accepted.')
        with st.form(f'evidence_add_{pid}', clear_on_submit=True):
            title = st.text_input('Evidence title', max_chars=180)
            ref = st.text_input('Document / URL / section', max_chars=2000)
            revision = st.text_input('Evidence revision', max_chars=80)
            category = st.selectbox('Evidence category', ['Project', 'Code', 'Manufacturer', 'Model', 'Calculation', 'Other'])
            if st.form_submit_button('Register evidence', type='primary'):
                try:
                    add_evidence(conn, pid, title, ref, revision, category); st.rerun()
                except ValueError as error:
                    st.error(str(error))


def page_issues():
    st.header('Project issues')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Select or create a project first.'); return
    conn = st.session_state.conn
    summary = project_summary(conn, pid)
    team = {r['member_id']: f"{r['name']} · {r['role']}" for r in summary['team']}
    names = {r['member_id']: r['name'] for r in summary['team']}
    st.caption('Assign owners, priority, due dates and model locations. Source blockers remain live until their underlying inputs or checks are corrected.')
    view = st.segmented_control('Issue view', ['Assigned issues', 'Source findings'], default='Assigned issues', key=f'issues_view_{pid}')
    if view == 'Source findings':
        findings = {f['source_key']: f for f in summary['findings']}
        if not findings:
            st.info('No source findings currently detected.'); return
        selected = st.selectbox('Source finding', list(findings), format_func=lambda k: findings[k]['title'])
        f = findings[selected]
        st.caption('Location: ' + (f['location'] or 'Project-wide'))
        action('Open source tool', f['target'], 'issue_open_source')
        if not team:
            st.info('Add project team members before assigning an issue.'); return
        existing = next((r for r in summary['issues'] if r['source_key'] == selected), None)
        if existing:
            st.info('This finding already has an issue. Update it in Assigned issues. Closing the issue does not dismiss the source finding.')
        elif st.button('Create issue from finding'):
            actor = st.session_state.get('workspace_actor')
            if actor not in team:
                st.error('Choose your acting team member in the sidebar first.')
            else:
                save_issue(conn, pid, title=f['title'], owner_id=actor, priority=f['priority'], due_date=None,
                           location=f['location'], actor_id=actor, source_key=selected)
                st.success('Finding assigned to you. Set the owner and due date in Assigned issues.'); st.rerun()
        return
    status_filter = st.multiselect('Show statuses', STATUSES, default=['Open', 'In progress'], key=f'issue_filter_{pid}')
    owner_filter = st.selectbox('Filter by owner', ['All owners', 'Unassigned'] + list(team),
        format_func=lambda k: team.get(k, k), key=f'issue_owner_filter_{pid}')
    query = st.text_input('Search issues', key=f'issue_search_{pid}', placeholder='Title, location or resolution')
    items = [r for r in summary['issues'] if r['status'] in status_filter
             and (owner_filter == 'All owners' or (owner_filter == 'Unassigned' and not r['owner_id']) or r['owner_id'] == owner_filter)
             and query.casefold() in (r['title'] + ' ' + r['location'] + ' ' + r['resolution']).casefold()]
    items.sort(key=lambda r: (PRIORITIES.index(r['priority']), r['due_date'] or '9999'))
    if items:
        st.dataframe([dict(Issue=r['title'], Owner=names.get(r['owner_id'], 'Unassigned'), Priority=r['priority'],
                           Due=r['due_date'] or 'Not set', Status=r['status'], Location=r['location']) for r in items],
            hide_index=True, width='stretch', alt='Filtered project issues with owner, priority, due date, status and location')
    else:
        st.info('No issues match these statuses.')
    st.download_button('Export issue register', json.dumps(summary['issues'], indent=2), file_name=f'project-{pid}-issues.json', mime='application/json')
    if not team:
        action('Set up the project team', 'Team & evidence', 'issue_team'); return
    choices = {r['issue_id']: r for r in summary['issues']}
    selected = st.selectbox('Create or update issue', [None] + list(choices), format_func=lambda k: choices[k]['title'] if k else 'New issue')
    original = choices.get(selected, {})
    if original.get('location'):
        st.button('Locate issue in model explorer', key='locate_issue_' + str(selected), on_click=locate_model,
                  args=(original['location'],), help='Matches an extracted source ID. Free-text level/location notes remain visible in the issue.')
    with st.form(f'issue_edit_{pid}_{selected}'):
        title = st.text_input('Issue title', original.get('title', ''), max_chars=500)
        location = st.text_input('Model object / level / location', original.get('location', ''), max_chars=500)
        owner = st.selectbox('Issue owner', [None] + list(team), index=([None] + list(team)).index(original.get('owner_id')),
                             format_func=lambda k: team.get(k, 'Unassigned'))
        cols = st.columns(3)
        priority = cols[0].selectbox('Priority', PRIORITIES, index=PRIORITIES.index(original.get('priority', 'Medium')))
        due = cols[1].date_input('Due date', value=dt.date.fromisoformat(original['due_date']) if original.get('due_date') else None)
        status = cols[2].selectbox('Issue status', STATUSES, index=STATUSES.index(original.get('status', 'Open')))
        resolution = st.text_area('Resolution / evidence', original.get('resolution', ''))
        actor = st.selectbox('Issue recorded by', list(team), format_func=team.get)
        if st.form_submit_button('Save issue', type='primary'):
            try:
                save_issue(conn, pid, title=title, owner_id=owner, priority=priority, due_date=due, status=status,
                           location=location, resolution=resolution, actor_id=actor, issue_id=selected)
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def page_approval():
    st.header('Approval workflow')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Select or create a project first.'); return
    conn = st.session_state.conn
    state = workflow_state(conn, pid)
    st.caption('Designer → Checker → BIM coordinator → Approver. Each step records a different named reviewer and project evidence against the same project snapshot.')
    st.info('This is an attributed review record, not an authenticated electronic signature. Final approval stays blocked by unresolved source findings, issues or independent engineering acceptance.')
    completed = {r['stage'] for r in state['current']}
    for col, stage in zip(st.columns(4), STAGES):
        with col.container(border=True):
            st.markdown('**' + stage + '**')
            st.badge('Recorded' if stage in completed else 'Next' if stage == state['next_stage'] else 'Waiting', color='blue' if stage in completed else 'gray')
    if state['blockers']:
        st.warning(f"Approval blocked by {len(state['blockers'])} unresolved requirement(s).")
        for issue in state['blockers'][:8]:
            st.caption('• ' + issue)
        action('Review project findings', 'Issues', 'approval_issues')
    stage = state['next_stage']
    members = [r for r in rows(conn, 'project_team', pid) if stage and r['role'] == ROLES[STAGES.index(stage)]]
    evidence = rows(conn, 'project_evidence', pid)
    if stage and members and evidence:
        with st.form(f'workflow_{pid}_{state["fingerprint"]}_{stage}'):
            st.subheader(stage)
            member = st.selectbox('Stage reviewer', members, format_func=lambda r: r['name'])
            ref = st.selectbox('Review evidence', evidence, format_func=lambda r: r['title'] + ' · ' + r['revision'])
            note = st.text_area('Review decision and scope')
            confirmed = st.checkbox('I reviewed this project snapshot, source limitations and outstanding findings')
            if st.form_submit_button('Record ' + stage.lower(), type='primary', disabled=stage == 'Approval' and bool(state['blockers'])):
                try:
                    if not confirmed:
                        raise ValueError('Confirm snapshot review before recording the step.')
                    record_workflow(conn, pid, stage, member['member_id'], ref['evidence_id'], note, state['fingerprint'])
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
    elif stage:
        st.info('Register the required reviewer role and evidence before routing this stage.')
        action('Open team & evidence', 'Team & evidence', 'approval_team')
    if state['events']:
        lookup = {r['member_id']: r['name'] for r in rows(conn, 'project_team', pid)}
        st.subheader('Review history')
        st.dataframe([dict(Stage=r['stage'], Reviewer=lookup.get(r['member_id']), Recorded=r['created_at'],
                           Snapshot='Current' if r in state['current'] else 'Superseded', Note=r['note']) for r in state['events']],
            hide_index=True, width='stretch', alt='Immutable project review steps; superseded snapshots require fresh review')
    st.download_button('Export workflow record', json.dumps(state, indent=2), file_name=f'project-{pid}-workflow.json', mime='application/json')
    action('Open release evidence', 'Release Readiness', 'workflow_release')
