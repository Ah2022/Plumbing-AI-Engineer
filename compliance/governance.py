"""Code identity, adoption approval, verification evidence and stale-result control.

Metadata identification is never treated as engineering or project approval.
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'database' / 'code_profiles.json'
ENGINE_VERSION = '0.6.2-phases3-5'
DOMAINS = ('water', 'drainage', 'vent', 'storm')
REQUIRED_CRITERIA = ('jurisdiction', 'authority', 'amendments', 'occupancy',
                     'systems', 'units', 'method', 'exclusions', 'precedence')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def profiles():
    return json.loads(REGISTRY.read_text(encoding='utf-8'))['profiles']


def profile(profile_id):
    for p in profiles():
        if p['profile_id'] == profile_id:
            return p
    raise ValueError(f'Unsupported profile: {profile_id}')


def profile_for_code(code_id):
    return next((p for p in profiles() if p['code_id'] == code_id), None)


def source_manifest():
    """Fingerprints only; no licensed workbook cells in the snapshot/export."""
    paths = [REGISTRY, *sorted((ROOT / 'database' / 'codes').rglob('*.json')),
             *sorted((ROOT / 'database' / 'code_design_data').glob('*.xlsx')),
             *sorted((ROOT / 'calculations').glob('*.py')),
             *sorted((ROOT / 'compliance').glob('*.py')),
             *sorted((ROOT / 'models').glob('*.py')), *sorted((ROOT / 'units').glob('*.py')),
             *sorted((ROOT / 'bim').glob('*.py')),
             ROOT / 'database' / 'design_table_api.py', ROOT / 'database' / 'load_design_tables.py',
             ROOT / 'database' / 'load_confirmed_additions.py', ROOT / 'requirements-lock.txt']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def source_fingerprint(conn):
    data = {}
    for table, order in [('code_rules','rule_id'), ('design_tables','table_id'), ('design_table_values','id')]:
        data[table] = digest([dict(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY {order}')])
    return digest({'files': source_manifest(), 'loaded_database': data})


def seed_review_inventory(conn):
    """New supplied rules start pending; no automatic verification/approval."""
    for p in profiles():
        for rule in conn.execute('SELECT rule_id FROM code_rules WHERE code_id=?', (p['code_id'],)):
            conn.execute('''INSERT OR IGNORE INTO rule_reviews
                (profile_id,rule_id,applicability,inputs,units,exceptions) VALUES (?,?,?,?,?,?)''',
                         (p['profile_id'], rule['rule_id'], 'REQUIRES_ENGINEER_APPLICABILITY_REVIEW',
                          'REQUIRES_INPUT_CONTRACT_REVIEW', 'REQUIRES_UNIT_REVIEW', 'NOT_VERIFIED'))
        for domain in DOMAINS:
            bid = f"{p['profile_id']}:{domain}:independent-example"
            conn.execute('''INSERT OR IGNORE INTO verification_benchmarks
                (benchmark_id,profile_id,domain,purpose) VALUES (?,?,?,?)''',
                         (bid, p['profile_id'], domain,
                          'Independent source-reviewed example, boundaries and unsupported cases'))
    conn.commit()


def _event(conn, project_id, kind, actor, snapshot):
    conn.execute('INSERT INTO governance_events(project_id,event_type,actor,snapshot_json) VALUES (?,?,?,?)',
                 (project_id, kind, actor, json.dumps(snapshot, sort_keys=True)))


def _invalidate(conn, project_id):
    conn.execute('UPDATE calculations SET is_current=0 WHERE project_id=?', (project_id,))
    conn.execute('UPDATE compliance_checks SET is_current=0 WHERE project_id=?', (project_id,))
    conn.execute('DELETE FROM qaqc_results WHERE project_id=?', (project_id,))


def get_basis(conn, project_id):
    row = conn.execute('SELECT * FROM project_code_basis WHERE project_id=?', (project_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result['criteria'] = json.loads(result.pop('criteria_json'))
    return result


def set_basis(conn, project_id, profile_id, criteria, actor):
    """Save a draft revision and invalidate prior results atomically."""
    p = profile(profile_id)
    if not isinstance(criteria, dict):
        raise ValueError('Design-basis criteria must be a structured record')
    digest(criteria)
    if not actor.strip():
        raise ValueError('Name the person recording the design basis')
    if not conn.execute('SELECT 1 FROM projects WHERE project_id=?', (project_id,)).fetchone():
        raise ValueError('Unknown project')
    if criteria.get('units') and criteria['units'] not in p['units']:
        raise ValueError('Unsupported unit system for this profile')
    systems = criteria.get('systems', [])
    if not isinstance(systems, list) or any(s not in DOMAINS for s in systems):
        raise ValueError('Choose supported systems explicitly')
    old = get_basis(conn, project_id)
    if old and old['profile_id'] == profile_id and old['criteria'] == criteria:
        return old['revision']
    revision = old['revision'] + 1 if old else 1
    with conn:
        conn.execute('''INSERT INTO project_code_basis
            (project_id,profile_id,revision,criteria_json,basis_status) VALUES (?,?,?,?,'DRAFT')
            ON CONFLICT(project_id) DO UPDATE SET profile_id=excluded.profile_id,
              revision=excluded.revision,criteria_json=excluded.criteria_json,basis_status='DRAFT',
              reviewer=NULL,adoption_evidence=NULL,approved_context=NULL,updated_at=CURRENT_TIMESTAMP''',
                     (project_id, profile_id, revision, json.dumps(criteria, sort_keys=True)))
        conn.execute('UPDATE projects SET code_id=?,code_edition=? WHERE project_id=?',
                     (p['code_id'], p['edition'], project_id))
        _invalidate(conn, project_id)
        _event(conn, project_id, 'BASIS_REVISED', actor,
               {'profile_id': profile_id, 'revision': revision, 'criteria': criteria})
    return revision


def _approval_identity(conn, basis):
    return {'profile': profile(basis['profile_id']), 'criteria': basis['criteria'],
            'revision': basis['revision'], 'source_fingerprint': source_fingerprint(conn)}


def approve_basis(conn, project_id, reviewer, adoption_evidence):
    basis = get_basis(conn, project_id)
    if not basis:
        raise ValueError('Record the project code basis first')
    missing = [k for k in REQUIRED_CRITERIA
               if (not basis['criteria'].get(k) if k == 'systems'
                   else not isinstance(basis['criteria'].get(k), str) or not basis['criteria'][k].strip())]
    if missing:
        raise ValueError('Missing design-basis criteria: ' + ', '.join(missing))
    if not reviewer.strip() or not adoption_evidence.strip():
        raise ValueError('Named reviewer and project adoption evidence are required')
    with conn:
        conn.execute('''UPDATE project_code_basis SET basis_status='APPROVED',reviewer=?,
            adoption_evidence=?,approved_context=?,updated_at=CURRENT_TIMESTAMP WHERE project_id=?''',
                     (reviewer, adoption_evidence, digest(_approval_identity(conn, basis)), project_id))
        _invalidate(conn, project_id)
        _event(conn, project_id, 'BASIS_APPROVED', reviewer,
               {'revision': basis['revision'], 'adoption_evidence': adoption_evidence})


def record_benchmark(conn, benchmark_id, expected, actual, tolerance, reviewer, source_evidence,
                     *, inputs, units, comparison_policy, case_reference):
    row = conn.execute('SELECT * FROM verification_benchmarks WHERE benchmark_id=?', (benchmark_id,)).fetchone()
    if row is None:
        raise ValueError('Choose a registered profile benchmark')
    if not reviewer.strip() or not source_evidence.strip():
        raise ValueError('Independent expected-result source and named reviewer are required')
    if not isinstance(inputs, dict) or not inputs or not units.strip() or not comparison_policy.strip() or not case_reference.strip():
        raise ValueError('Record benchmark inputs, units, comparison policy and reference/case purpose')
    case = dict(inputs=inputs, units=units, comparison_policy=comparison_policy, case_reference=case_reference)
    digest(case)  # reject non-finite/non-serializable benchmark input records
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Tolerance must be finite and nonnegative')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (expected, actual)):
        raise ValueError('Expected and actual values must be finite numbers')
    status = 'PASS' if abs(expected - actual) <= tolerance else 'FAIL'
    with conn:
        conn.execute('''UPDATE verification_benchmarks SET expected_json=?,actual_json=?,tolerance=?,
            reviewer=?,source_evidence=?,status=?,source_fingerprint=?,case_json=?,updated_at=CURRENT_TIMESTAMP
            WHERE benchmark_id=?''', (json.dumps(expected), json.dumps(actual), tolerance, reviewer,
                                     source_evidence, status, source_fingerprint(conn), json.dumps(case,sort_keys=True), benchmark_id))
        _invalidate_profile(conn, row['profile_id'])
        _event(conn, None, 'BENCHMARK_REVIEWED', reviewer,
               dict(benchmark_id=benchmark_id,status=status,expected=expected,actual=actual,
                    tolerance=tolerance,source_evidence=source_evidence,case=case,
                    source_fingerprint=source_fingerprint(conn)))
    return status


def _invalidate_profile(conn, profile_id):
    for row in conn.execute('SELECT project_id FROM project_code_basis WHERE profile_id=?', (profile_id,)):
        _invalidate(conn, row['project_id'])


def review_rule(conn, profile_id, rule_id, status, applicability, inputs, units, exceptions,
                reviewer, source_evidence, benchmark_id=None):
    p = profile(profile_id)
    rule = conn.execute('SELECT * FROM code_rules WHERE rule_id=? AND code_id=?',
                        (rule_id, p['code_id'])).fetchone()
    if not rule:
        raise ValueError('Rule does not belong to this code profile')
    if status not in ('PENDING', 'VERIFIED', 'UNSUPPORTED'):
        raise ValueError('Unsupported rule-review status')
    if not all(str(v).strip() for v in (applicability, inputs, units, exceptions, reviewer, source_evidence)):
        raise ValueError('Complete applicability, inputs, units, exceptions, reviewer and source evidence')
    if status == 'VERIFIED':
        from compliance.rule_registry import RULE_PREDICATES
        if rule_id not in RULE_PREDICATES:
            raise ValueError('An unimplemented rule cannot be verified as an executable check')
        b = conn.execute('SELECT * FROM verification_benchmarks WHERE benchmark_id=?', (benchmark_id,)).fetchone()
        if not b or b['profile_id'] != profile_id or b['domain'] != rule['domain'] or b['status'] != 'PASS' or b['source_fingerprint'] != source_fingerprint(conn):
            raise ValueError('A current passing independent benchmark for this profile/domain is required')
    with conn:
        conn.execute('INSERT OR IGNORE INTO rule_reviews(profile_id,rule_id) VALUES (?,?)', (profile_id,rule_id))
        conn.execute('''UPDATE rule_reviews SET status=?,applicability=?,inputs=?,units=?,exceptions=?,
            reviewer=?,source_evidence=?,benchmark_id=?,source_fingerprint=?,updated_at=CURRENT_TIMESTAMP
            WHERE profile_id=? AND rule_id=?''', (status, applicability, inputs, units, exceptions,
                reviewer, source_evidence, benchmark_id, source_fingerprint(conn), profile_id, rule_id))
        _invalidate_profile(conn, profile_id)
        _event(conn, None, 'RULE_REVIEWED', reviewer,
               dict(profile_id=profile_id,rule_id=rule_id,status=status,applicability=applicability,
                    inputs=inputs,units=units,exceptions=exceptions,source_evidence=source_evidence,
                    benchmark_id=benchmark_id,source_fingerprint=source_fingerprint(conn)))


def coverage(conn, profile_id):
    p = profile(profile_id)
    rows = conn.execute('''SELECT r.rule_id,r.domain,r.reference,r.source_note,r.has_predicate,
        COALESCE(v.status,'PENDING') AS verification_status,v.applicability,v.inputs,v.units,v.exceptions,v.reviewer,
        v.source_evidence,v.benchmark_id,v.source_fingerprint
        FROM code_rules r LEFT JOIN rule_reviews v ON v.rule_id=r.rule_id AND v.profile_id=?
        WHERE r.code_id=? ORDER BY r.rule_id''', (profile_id, p['code_id'])).fetchall()
    result = [dict(r) for r in rows]
    current = source_fingerprint(conn)
    for r in result:
        r.update(profile_id=profile_id, edition=p['edition'], source_classification='SUPPLIED_DERIVED_RULE',
                 official_metadata_url=p['source_url'],
                 implementation_status='EXECUTABLE_UNVERIFIED' if r['has_predicate'] else 'NOT_IMPLEMENTED')
        if r['verification_status'] == 'VERIFIED' and r['source_fingerprint'] != current:
            r['verification_status'] = 'STALE'
        elif r['verification_status'] == 'VERIFIED':
            b = conn.execute('SELECT status,source_fingerprint FROM verification_benchmarks WHERE benchmark_id=?',
                             (r['benchmark_id'],)).fetchone()
            if not b or b['status'] != 'PASS' or b['source_fingerprint'] != current:
                r['verification_status'] = 'BENCHMARK_REVIEW_REQUIRED'
    return result


def context(conn, project_id):
    project = conn.execute('SELECT code_id,code_edition FROM projects WHERE project_id=?', (project_id,)).fetchone()
    basis = get_basis(conn, project_id)
    issues = []
    if project is None:
        raise ValueError('Unknown project')
    if basis is None:
        issues.append('No declared project code profile/design basis')
        p, rows = None, []
    else:
        p = profile(basis['profile_id'])
        rows = coverage(conn, p['profile_id'])
        if project['code_id'] != p['code_id'] or project['code_edition'] != p['edition']:
            issues.append('Project code/edition differs from its declared profile')
        if basis['basis_status'] != 'APPROVED':
            issues.append('Project adoption/design basis is not approved')
        elif basis['approved_context'] != digest(_approval_identity(conn, basis)):
            issues.append('Profile or source data changed after adoption approval')
        systems = basis['criteria'].get('systems', [])
        unresolved = [r['rule_id'] for r in rows if r['domain'] in systems and r['verification_status'] != 'VERIFIED']
        if unresolved:
            issues.append(f'{len(unresolved)} applicable supplied rules remain unverified/unsupported')
        if not systems:
            issues.append('No supported systems selected')
        if p['numeric_dataset_edition'] != 'VERIFIED':
            issues.append('Numeric dataset edition/applicability remains unverified')
        issues.append('Independent engineering acceptance of supported methods and model completeness remains required')
    benchmarks = [dict(r) for r in conn.execute('SELECT * FROM verification_benchmarks WHERE profile_id=? ORDER BY benchmark_id',
                                               (p['profile_id'],))] if p else []
    payload = {'engine_version': ENGINE_VERSION, 'registry_version': json.loads(REGISTRY.read_text())['registry_version'],
               'profile': p, 'basis': basis, 'rule_coverage': rows, 'sources': source_manifest(),
               'verification_benchmarks': benchmarks,
               'source_fingerprint': source_fingerprint(conn),
               'review_status': 'REVIEW_REQUIRED' if issues else 'VERIFIED', 'issues': issues}
    payload['fingerprint'] = digest(payload)
    return payload


def calculation_is_current(conn, project_id, row):
    if not row['is_current'] or not row['governance_json']:
        return False
    try:
        saved = json.loads(row['governance_json'])
        return isinstance(saved, dict) and saved.get('fingerprint') == context(conn, project_id)['fingerprint']
    except (ValueError, TypeError):
        return False
