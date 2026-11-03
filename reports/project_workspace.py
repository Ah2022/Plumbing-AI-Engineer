"""Project coordination records and revision-bound review routing.

Team roles attribute actions; they are not login identities or electronic signatures.
Source findings remain live until corrected in their source, regardless of issue status.
"""
import datetime as dt
import json
from uuid import uuid4

from compliance.governance import context, calculation_is_current
from reports.provenance import digest
from reports.review_workflow import review_readiness

ROLES = ('Designer', 'Checker', 'BIM coordinator', 'Approver')
PRIORITIES = ('Critical', 'High', 'Medium', 'Low')
STATUSES = ('Open', 'In progress', 'Resolved')
STAGES = ('Design submission', 'Independent check', 'BIM coordination', 'Approval')


def ensure_workspace_schema(conn):
    for sql in (
        '''CREATE TABLE IF NOT EXISTS project_team (
            member_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            name TEXT NOT NULL, role TEXT NOT NULL, credentials TEXT NOT NULL DEFAULT '',
            UNIQUE(project_id,name,role))''',
        '''CREATE TABLE IF NOT EXISTS project_evidence (
            evidence_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            title TEXT NOT NULL, reference TEXT NOT NULL, revision TEXT NOT NULL, category TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS project_issues (
            issue_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            source_key TEXT, title TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
            owner_id TEXT REFERENCES project_team(member_id), priority TEXT NOT NULL,
            due_date TEXT, status TEXT NOT NULL, resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id,source_key))''',
        '''CREATE TABLE IF NOT EXISTS project_workflow_events (
            event_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            stage TEXT NOT NULL, member_id TEXT NOT NULL REFERENCES project_team(member_id),
            evidence_id TEXT NOT NULL REFERENCES project_evidence(evidence_id),
            snapshot_sha256 TEXT NOT NULL, note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS project_issue_events (
            event_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            issue_id TEXT NOT NULL REFERENCES project_issues(issue_id), actor_id TEXT NOT NULL REFERENCES project_team(member_id),
            before_json TEXT, after_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
    ):
        conn.execute(sql)


def rows(conn, table, pid):
    if table not in ('project_team', 'project_evidence', 'project_issues', 'project_workflow_events', 'project_issue_events'):
        raise ValueError('Unsupported workspace register')
    return [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE project_id=? ORDER BY rowid', (pid,))]


def text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} is required and must be {limit} characters or fewer.')
    return value.strip()


def _member(conn, pid, member_id):
    member = next((r for r in rows(conn, 'project_team', pid) if r['member_id'] == member_id), None)
    if not member:
        raise ValueError('Choose a team member belonging to this project.')
    return member


def add_member(conn, pid, name, role, credentials=''):
    if role not in ROLES:
        raise ValueError('Choose a supported project role.')
    name = text(name, 'Name', 120)
    identity = uuid4().hex
    with conn:
        conn.execute('INSERT INTO project_team(member_id,project_id,name,role,credentials) VALUES (?,?,?,?,?)',
                     (identity, pid, name, role, str(credentials).strip()[:500]))
    return identity


def add_evidence(conn, pid, title, reference, revision, category):
    if category not in ('Project', 'Code', 'Manufacturer', 'Model', 'Calculation', 'Other'):
        raise ValueError('Choose an evidence category.')
    identity = uuid4().hex
    with conn:
        conn.execute('INSERT INTO project_evidence(evidence_id,project_id,title,reference,revision,category) VALUES (?,?,?,?,?,?)',
                     (identity, pid, text(title, 'Evidence title', 180), text(reference, 'Reference'),
                      text(revision, 'Revision', 80), category))
    return identity


def save_issue(conn, pid, *, title, owner_id, priority, due_date, status='Open', location='',
               resolution='', actor_id, issue_id=None, source_key=None):
    _member(conn, pid, actor_id)
    if owner_id:
        _member(conn, pid, owner_id)
    if priority not in PRIORITIES or status not in STATUSES:
        raise ValueError('Choose a supported priority and status.')
    if due_date:
        dt.date.fromisoformat(str(due_date))
    if status == 'Resolved' and not str(resolution).strip():
        raise ValueError('Describe the resolution before closing an issue.')
    before = None
    if issue_id:
        before = next((r for r in rows(conn, 'project_issues', pid) if r['issue_id'] == issue_id), None)
        if before is None:
            raise ValueError('Issue does not belong to this project.')
        source_key = before['source_key']
    identity = issue_id or uuid4().hex
    values = (text(title, 'Issue title', 500), str(location)[:500], owner_id or None, priority,
              str(due_date) if due_date else None, status, str(resolution)[:4000])
    with conn:
        if before:
            conn.execute('''UPDATE project_issues SET title=?,location=?,owner_id=?,priority=?,due_date=?,status=?,
                            resolution=?,updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND issue_id=?''', (*values, pid, identity))
        else:
            conn.execute('''INSERT INTO project_issues(title,location,owner_id,priority,due_date,status,resolution,project_id,issue_id,source_key)
                            VALUES (?,?,?,?,?,?,?,?,?,?)''', (*values, pid, identity, source_key))
        after = next(r for r in rows(conn, 'project_issues', pid) if r['issue_id'] == identity)
        conn.execute('''INSERT INTO project_issue_events(event_id,project_id,issue_id,actor_id,before_json,after_json)
                        VALUES (?,?,?,?,?,?)''', (uuid4().hex, pid, identity, actor_id,
                                               json.dumps(before), json.dumps(after)))
    return identity


def _optional(conn, table, pid):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return []
    # Only internal constant table names are supplied.
    return [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE project_id=? ORDER BY rowid', (pid,))]


def project_summary(conn, pid):
    """Live source blockers plus coordination records; never turns a task closure into approval."""
    project = conn.execute('SELECT * FROM projects WHERE project_id=?', (pid,)).fetchone()
    if project is None:
        raise ValueError('Select an existing project.')
    ready = review_readiness(conn, pid)
    findings = []

    def finding(key, title, target, location='', priority='High'):
        findings.append(dict(source_key=key, title=title, target=target, location=location, priority=priority))

    for issue in ready['issues']:
        finding('readiness:' + digest(issue)[:20], issue, 'Code Profiles')
    calculations = _optional(conn, 'calculations', pid)
    for r in calculations:
        if calculation_is_current(conn, pid, r) and r['status'] != 'PASS':
            finding('calc:' + r['calc_id'], f"{r['calc_type'].replace('_', ' ')}: {r['status'].replace('_', ' ').lower()}",
                    'Report / Export', r.get('target_id') or r['calc_id'], 'Critical' if r['status'] == 'FAIL' else 'High')
    basis_items = _optional(conn, 'design_basis_items', pid)
    for r in basis_items:
        if r['status'] != 'APPROVED':
            finding('basis:' + str(r['id']), f"Design criterion requires review: {r['item_key']}", 'Design Basis')
    assumptions = _optional(conn, 'assumptions', pid)
    for r in assumptions:
        if r['status'] != 'APPROVED':
            finding('assumption:' + r['assumption_id'], r['description'], 'QA/QC Dashboard')
    checks = _optional(conn, 'compliance_checks', pid)
    for r in checks:
        if r.get('is_current') and r['status'] != 'PASS':
            finding('compliance:' + str(r['check_id']), r['reason'] or r['status'], 'Code Compliance / QA-QC', r.get('target_id') or '')
    snapshots = _optional(conn, 'bim_extraction_snapshots', pid)
    latest = {}
    for r in snapshots:
        latest[r['model_id']] = r
    health = []
    for model, r in latest.items():
        try:
            from bim.mapping import validate_snapshot
            body = validate_snapshot(json.loads(r['packet_json']))
            inventory, report = body['inventory'], body['diagnostics']
            objects = inventory['objects']
            axis_count = sum(bool(o.get('start_xyz_m') and o.get('end_xyz_m')) for o in objects)
            health.append(dict(model=model, objects=len(objects), geometry=axis_count, status=report['technical_status']))
            for f in report['findings']:
                if f['status'] != 'PASS':
                    source = f.get('source_id') or model
                    finding('model:' + digest([model, f])[:24], f.get('detail') or f['check'], 'CAD / IFC Checks', source)
        except (ValueError, KeyError, TypeError):
            health.append(dict(model=model, objects=0, geometry=0, status='INVALID_SNAPSHOT'))
            finding('model-invalid:' + model, 'Stored model snapshot needs re-import and verification', 'CAD / IFC Checks', model)
    imports = _optional(conn, 'revit_model_imports', pid)
    if not health and imports:
        health = [dict(model=r['model_name'], objects=0, geometry=0, status='MAPPING_NOT_SAVED') for r in imports]
        finding('model-mapping', 'Imported Revit model needs a saved reviewed mapping and connectivity diagnostics', 'Revit Exchange')
    team, evidence, issues = (rows(conn, name, pid) for name in ('project_team', 'project_evidence', 'project_issues'))
    roles = {m['role'] for m in team}
    for role in ROLES:
        if role not in roles:
            finding('role:' + role, 'Assign a project ' + role.lower(), 'Team & evidence')
    if not evidence:
        finding('evidence', 'Register project evidence and revision references', 'Team & evidence')
    if not calculations:
        finding('calculations', 'Run the calculations needed for the declared project scope', 'Fixtures & Water')
    findings.sort(key=lambda f: (PRIORITIES.index(f['priority']), f['source_key']))
    active = [r for r in issues if r['status'] != 'Resolved']
    overdue = [r for r in active if r['due_date'] and r['due_date'] < dt.date.today().isoformat()]
    return dict(project=dict(project), readiness=ready, findings=findings, issues=issues, team=team,
                evidence=evidence, model_health=health, current_calculations=ready['current_calculations'],
                assumptions=sum(r['status'] != 'APPROVED' for r in assumptions), overdue=len(overdue),
                open_issues=len(active), source_blockers=len(findings),
                approval_blockers=[f['title'] for f in findings] + [f"Open issue: {r['title']}" for r in active])


def workflow_state(conn, pid, summary=None):
    summary = summary or project_summary(conn, pid)
    from validation.gate import validation_gate
    gate = validation_gate()
    # Include complete coordination/evidence/model/result state. A change revokes earlier routing steps.
    snapshot = dict(governance=context(conn, pid)['fingerprint'], project=summary['project'],
        calculations=_optional(conn, 'calculations', pid), design_basis=_optional(conn, 'design_basis_items', pid),
        assumptions=_optional(conn, 'assumptions', pid), compliance=_optional(conn, 'compliance_checks', pid),
        qa=_optional(conn, 'qaqc_results', pid), models=_optional(conn, 'bim_extraction_snapshots', pid),
        imports=_optional(conn, 'revit_model_imports', pid), team=summary['team'], evidence=summary['evidence'],
        issues=summary['issues'], findings=summary['findings'], validation=gate)
    fingerprint = digest(snapshot)
    events = rows(conn, 'project_workflow_events', pid)
    current = [r for r in events if r['snapshot_sha256'] == fingerprint]
    completed = {r['stage'] for r in current}
    next_stage = next((s for s in STAGES if s not in completed), None)
    blockers = list(summary['approval_blockers'])
    if gate['engineering_status'] != 'ACCEPTED':
        blockers.append('Independent engineering validation is pending. Public software benchmarks cannot satisfy this gate.')
    return dict(fingerprint=fingerprint, events=events, current=current, next_stage=next_stage,
                blockers=blockers, status='Approval recorded' if next_stage is None else 'Review required')


def record_workflow(conn, pid, stage, member_id, evidence_id, note, expected_fingerprint):
    member = _member(conn, pid, member_id)
    state = workflow_state(conn, pid)
    if state['fingerprint'] != expected_fingerprint:
        raise ValueError('Project changed while this review was open. Refresh and review the updated snapshot.')
    if stage not in STAGES or stage != state['next_stage'] or member['role'] != ROLES[STAGES.index(stage)]:
        raise ValueError('Complete review stages in order using the assigned project role.')
    prior_names = {m['name'].casefold() for m in rows(conn, 'project_team', pid)
                   if m['member_id'] in {e['member_id'] for e in state['current']}}
    if member['name'].casefold() in prior_names:
        raise ValueError('Use a different named reviewer for each independent review stage.')
    if stage == 'Approval' and state['blockers']:
        raise ValueError('Resolve source blockers, open issues and engineering acceptance before recording approval.')
    if not any(r['evidence_id'] == evidence_id for r in rows(conn, 'project_evidence', pid)):
        raise ValueError('Select evidence registered to this project.')
    with conn:
        conn.execute('''INSERT INTO project_workflow_events(event_id,project_id,stage,member_id,evidence_id,snapshot_sha256,note)
                        VALUES (?,?,?,?,?,?,?)''', (uuid4().hex, pid, stage, member_id, evidence_id,
                                               state['fingerprint'], text(note, 'Review note')))
