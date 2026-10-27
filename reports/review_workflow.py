"""Immutable review revisions, complete evidence packets and reasoned override proposals."""
import datetime
import json
import re
from uuid import uuid4
from calculations.validation import finite
from compliance.governance import calculation_is_current
from database.review_schema import ensure_review_schema
from reports.provenance import digest, engine_manifest


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' is required')
    return value.strip()


def overrides(conn, project_id):
    ensure_review_schema(conn)
    return [dict(r) for r in conn.execute('SELECT * FROM calculation_overrides WHERE project_id=? ORDER BY created_at,override_id', (project_id,))]


def propose_override(conn, project_id, calc_id, field, value, unit, actor, reason):
    ensure_review_schema(conn)
    if field not in ('result_value', 'required_value', 'selected_value'):
        raise ValueError('Only a result, required or selected value may be proposed')
    value = finite('proposed value', value)
    actor, reason, unit = _text(actor, 'Reviewer'), _text(reason, 'Reason'), _text(unit, 'Unit')
    row = conn.execute('SELECT * FROM calculations WHERE project_id=? AND calc_id=?', (project_id, calc_id)).fetchone()
    if row is None:
        raise ValueError('Calculation does not belong to this project')
    identity = uuid4().hex
    with conn:
        conn.execute('''INSERT INTO calculation_overrides
            (override_id,project_id,calc_id,field,computed_json,proposed_value,unit,actor,reason,input_sha256)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (identity, project_id, calc_id, field, json.dumps(row[field]), value, unit, actor, reason,
             digest(json.loads(row['inputs_json']))))
    return identity


def review_readiness(conn, project_id):
    from compliance.governance import context
    ensure_review_schema(conn)
    governance = context(conn, project_id)
    rows = conn.execute('SELECT * FROM calculations WHERE project_id=?', (project_id,)).fetchall()
    current = [row for row in rows if calculation_is_current(conn, project_id, row)]
    issues = list(governance['issues'])
    if not current:
        issues.append('No current calculated results are available')
    historical = len(rows)-len(current)
    stale = sum(bool(r['is_current']) and not calculation_is_current(conn, project_id, r) for r in rows)
    if stale:
        issues.append(f'{stale} latest calculation(s) have a stale basis/source and require recalculation')
    bad = [r['calc_id'] for r in current if r['status'] != 'PASS' or r['review_status'] != 'VERIFIED']
    if bad:
        issues.append(f'{len(bad)} current calculation(s) need technical or engineering review')
    missing = [r['calc_id'] for r in rows if not conn.execute('SELECT 1 FROM calculation_provenance WHERE calc_id=?', (r['calc_id'],)).fetchone()]
    if missing:
        issues.append(f'{len(missing)} legacy calculation(s) have no captured engine fingerprint; historical execution cannot be asserted')
    proposals = overrides(conn, project_id)
    if proposals:
        issues.append(f'{len(proposals)} override proposal(s) require review; computed results have not been replaced')
    return dict(review_status='REVIEW_REQUIRED' if issues else 'VERIFIED', issues=issues,
                current_calculations=len(current), historical_calculations=historical,
                current_status_counts={s: sum(r['status']==s for r in current) for s in sorted({r['status'] for r in current})})


def build_review_packet(conn, project_id):
    from reports.report_generator import generate_calculation_report
    ensure_review_schema(conn)
    report = generate_calculation_report(conn, project_id)
    if not report['project']:
        raise ValueError('Unknown project')
    code = report['project']['code_id']
    references = ' '.join(str(c.get('reference') or '') for c in report['calculations'])
    codes = {code} | {r[0] for r in conn.execute('SELECT code_id FROM codes')
                    if re.search(r'\b'+re.escape(r[0])+r'\b', references)}
    tables = [dict(r) for r in conn.execute('SELECT * FROM design_tables ORDER BY table_id') if r['code_id'] in codes]
    source_values = []
    for table in tables:
        source_values.extend(dict(r) for r in conn.execute('SELECT * FROM design_table_values WHERE table_id=? ORDER BY id', (table['table_id'],)))
    provenance = [dict(r) for r in conn.execute('''SELECT p.* FROM calculation_provenance p JOIN calculations c ON c.calc_id=p.calc_id
                                                 WHERE c.project_id=? ORDER BY p.calc_id''', (project_id,))]
    packages = [dict(r) for r in conn.execute('SELECT * FROM project_calculation_packages WHERE project_id=? ORDER BY package_sha256', (project_id,))]
    payload = dict(schema_version='review-packet-1', exported_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        report=report, readiness=review_readiness(conn, project_id), override_proposals=overrides(conn, project_id),
        calculation_provenance=provenance, runtime_at_export=engine_manifest(),
        numeric_tables=tables, numeric_values=source_values, interactive_packages=packages,
        rules=[dict(r) for r in conn.execute('SELECT * FROM code_rules ORDER BY rule_id') if r['code_id'] in codes],
        limitations=['Checksums detect changed packet contents; they are not an engineering signature.',
            'Legacy engine versions and local-only workbook packages are not reconstructed. Retain original source files where the packet reports gaps.',
            'This packet can contain private numeric tables and calculation packages; review its contents before sharing.'])
    return dict(payload=payload, sha256=digest(payload))


def verify_review_packet(packet):
    if not isinstance(packet, dict) or not isinstance(packet.get('payload'), dict):
        raise ValueError('Review packet must contain a payload and checksum')
    if packet['payload'].get('schema_version') != 'review-packet-1' or packet.get('sha256') != digest(packet['payload']):
        raise ValueError('Review packet checksum/schema does not match its contents')
    return dict(sha256=packet['sha256'], project=packet['payload']['report']['project'],
                readiness=packet['payload']['readiness'])


def save_review_revision(conn, project_id, label, actor):
    label, actor = _text(label, 'Revision label'), _text(actor, 'Reviewer')
    packet = build_review_packet(conn, project_id)
    identity = uuid4().hex
    with conn:
        conn.execute('''INSERT INTO review_snapshots(snapshot_id,project_id,revision,label,actor,packet_sha256,packet_json)
            SELECT ?,?,COALESCE(MAX(revision),0)+1,?,?,?,? FROM review_snapshots WHERE project_id=?''',
            (identity, project_id, label, actor, packet['sha256'], json.dumps(packet, allow_nan=False), project_id))
    return identity


def compare_review_revisions(conn, project_id, old_id, new_id):
    def get(identity):
        row = conn.execute('SELECT packet_json FROM review_snapshots WHERE snapshot_id=? AND project_id=?', (identity,project_id)).fetchone()
        if row is None:
            raise ValueError('Review revision does not belong to this project')
        packet = json.loads(row[0]); verify_review_packet(packet)
        return packet['payload']
    old, new = get(old_id), get(new_id)
    a = {c['calc_id']: c for c in old['report']['calculations']}
    b = {c['calc_id']: c for c in new['report']['calculations']}
    return dict(added=sorted(b.keys()-a.keys()), removed=sorted(a.keys()-b.keys()),
        changed=sorted(k for k in a.keys() & b.keys() if digest(a[k]) != digest(b[k])),
        basis_changed=old['report']['governance']['fingerprint'] != new['report']['governance']['fingerprint'],
        override_proposals_added=len(new['override_proposals'])-len(old['override_proposals']))
