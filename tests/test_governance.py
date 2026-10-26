"""Synthetic governance acceptance tests. No licensed table values required."""
import json
import sqlite3
from pathlib import Path

import pytest

from app.db_helpers import save_calculation
from bim.exchange import import_revit_extract, export_results_for_revit
from bim.schemas import empty_extract_payload
from calculations.hydraulics import velocity_from_flow
from compliance.engine import run_compliance_for_project
from compliance.governance import (
    profiles, seed_review_inventory, set_basis, get_basis, approve_basis, context,
    coverage, review_rule, record_benchmark, calculation_is_current,
)
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from database.db import init_db
from database.governance_schema import ensure_governance_schema
from reports.report_generator import generate_calculation_report


@pytest.fixture
def db(tmp_path):
    conn = init_db(tmp_path / 'governance.db')
    load_all_rules(conn)
    sync_predicate_flags(conn)
    for pid in (1,2):
        conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (?,?,'Office','IPC')", (pid,f'Example {pid}'))
    conn.commit()
    yield conn
    conn.close()


def criteria(**updates):
    c = dict(jurisdiction='Synthetic jurisdiction', authority='Synthetic authority',
             amendments='None for this synthetic test', occupancy='Office', systems=['water'],
             units='SI', method='Synthetic independent test method', exclusions='Special arrangements',
             precedence='Project adoption > declared code; conflicts require review')
    c.update(updates)
    return c


def basis(db, profile='IPC-2024', pid=1):
    return set_basis(db,pid,profile,criteria(),'Synthetic engineer')


def saved(db):
    r = velocity_from_flow(1,25,'T-001')
    r.notes = 'Synthetic rationale'
    save_calculation(db,1,r)
    return db.execute("SELECT * FROM calculations WHERE calc_id='T-001'").fetchone()


def benchmark(db, **updates):
    args = dict(expected=1.,actual=1.,tolerance=0.,reviewer='Synthetic independent reviewer',
                source_evidence='Synthetic independently established identity',inputs={'depth_mm':1},
                units='L',comparison_policy='Exact identity',case_reference='Synthetic verification case')
    args.update(updates)
    return record_benchmark(db,'IPC-2024:water:independent-example',**args)


def rule_review(db, **updates):
    args = dict(profile_id='IPC-2024',rule_id='IPC-W-002',status='VERIFIED',
                applicability='Synthetic applicability', inputs='Approved pressure and PRV record',units='psi',
                exceptions='All unsupported cases require review',reviewer='Synthetic reviewer',
                source_evidence='Synthetic reviewed clause',benchmark_id='IPC-2024:water:independent-example')
    args.update(updates)
    return review_rule(db,**args)


def test_three_separate_profiles():
    assert {p['code_id'] for p in profiles()} == {'IPC','SAUDI_SBC_701','EGYPT_LOCAL'}
    assert len({p['profile_id'] for p in profiles()}) == 3
    assert all(p['numeric_dataset_edition']=='UNVERIFIED' for p in profiles())


def test_inventory_does_not_auto_verify(db):
    rows = coverage(db,'IPC-2024')
    assert len(rows)==9
    assert all(r['verification_status']=='PENDING' for r in rows)
    assert sum(r['has_predicate'] for r in rows)==3


def test_seed_is_idempotent(db):
    seed_review_inventory(db)
    seed_review_inventory(db)
    assert db.execute('SELECT COUNT(*) FROM rule_reviews').fetchone()[0]==23
    assert db.execute('SELECT COUNT(*) FROM verification_benchmarks').fetchone()[0]==12


def test_new_unreviewed_rule_cannot_disappear_from_coverage(db):
    db.execute("INSERT INTO code_rules(rule_id,code_id,domain,severity,condition_text,action_text) VALUES ('IPC-NEW','IPC','water','warning','synthetic','review')")
    row=next(r for r in coverage(db,'IPC-2024') if r['rule_id']=='IPC-NEW')
    assert row['verification_status']=='PENDING'


def test_legacy_project_not_approved(db):
    assert context(db,1)['review_status']=='REVIEW_REQUIRED'
    assert get_basis(db,1) is None


def test_basis_captures_edition_and_draft(db):
    basis(db)
    row=db.execute('SELECT code_id,code_edition FROM projects WHERE project_id=1').fetchone()
    assert tuple(row)==('IPC','2024')
    assert get_basis(db,1)['basis_status']=='DRAFT'


def test_unsupported_profile_rejected(db):
    with pytest.raises(ValueError,match='Unsupported profile'):
        basis(db,'IPC-2021')


def test_profile_unit_mismatch_rejected(db):
    with pytest.raises(ValueError,match='unit system'):
        set_basis(db,1,'EGYPT-301-1-2003',criteria(units='US_CUSTOMARY'),'Engineer')


def test_unknown_system_rejected(db):
    with pytest.raises(ValueError,match='systems'):
        set_basis(db,1,'IPC-2024',criteria(systems=['medical_gas']),'Engineer')


def test_identical_draft_is_not_new_revision(db):
    assert basis(db)==1
    assert basis(db)==1
    assert db.execute('SELECT COUNT(*) FROM governance_events').fetchone()[0]==1


def test_incomplete_adoption_cannot_be_approved(db):
    set_basis(db,1,'IPC-2024',{'units':'SI','systems':['water']},'Engineer')
    with pytest.raises(ValueError,match='Missing'):
        approve_basis(db,1,'Reviewer','Adoption evidence')


def test_whitespace_criteria_cannot_be_approved(db):
    set_basis(db,1,'IPC-2024',criteria(authority='   '),'Engineer')
    with pytest.raises(ValueError,match='authority'):
        approve_basis(db,1,'Reviewer','Adoption evidence')


@pytest.mark.parametrize('reviewer,evidence',[('','Evidence'),('Engineer','')])
def test_adoption_requires_reviewer_and_evidence(db,reviewer,evidence):
    basis(db)
    with pytest.raises(ValueError):
        approve_basis(db,1,reviewer,evidence)


def test_adoption_approval_does_not_verify_engine(db):
    basis(db)
    approve_basis(db,1,'Reviewer','Synthetic adoption record')
    assert get_basis(db,1)['basis_status']=='APPROVED'
    g=context(db,1)
    assert g['review_status']=='REVIEW_REQUIRED'
    assert any('Numeric dataset' in i for i in g['issues'])


def test_profile_switch_invalidates_and_retains_history(db):
    basis(db)
    saved(db)
    basis(db,'SBC701-2024')
    row=db.execute('SELECT * FROM calculations').fetchone()
    assert row['result_value']==pytest.approx(2.0372)
    assert row['is_current']==0
    assert get_basis(db,1)['revision']==2
    assert get_basis(db,1)['basis_status']=='DRAFT'


def test_amendment_edit_revokes_adoption_and_results(db):
    basis(db)
    approve_basis(db,1,'Reviewer','Synthetic adoption')
    saved(db)
    set_basis(db,1,'IPC-2024',criteria(amendments='Revised amendment'),'Engineer')
    assert get_basis(db,1)['reviewer'] is None
    assert db.execute('SELECT is_current FROM calculations').fetchone()[0]==0


def test_other_project_not_invalidated(db):
    basis(db,pid=2)
    save_calculation(db,2,velocity_from_flow(1,25,'OTHER-001'))
    basis(db)
    basis(db,'SBC701-2024')
    assert db.execute("SELECT is_current FROM calculations WHERE project_id=2").fetchone()[0]==1


def test_old_profile_cannot_reactivate_old_results(db):
    basis(db)
    saved(db)
    basis(db,'SBC701-2024')
    basis(db,'IPC-2024')
    assert db.execute('SELECT is_current FROM calculations').fetchone()[0]==0


def test_new_records_include_notes_and_versioned_context(db):
    basis(db)
    row=saved(db)
    g=json.loads(row['governance_json'])
    assert row['notes']=='Synthetic rationale'
    assert g['profile']['edition']=='2024'
    assert g['basis']['revision']==1
    assert g['sources']
    assert row['review_status']=='REVIEW_REQUIRED'
    assert calculation_is_current(db,1,row)


def test_loaded_rule_change_invalidates_context(db):
    basis(db)
    approve_basis(db,1,'Reviewer','Synthetic adoption')
    row=saved(db)
    db.execute("UPDATE code_rules SET source_note='changed source' WHERE rule_id='IPC-W-002'")
    assert not calculation_is_current(db,1,row)
    assert any('changed' in i for i in context(db,1)['issues'])


def test_direct_project_edition_drift_is_detected(db):
    basis(db)
    db.execute("UPDATE projects SET code_edition='2021' WHERE project_id=1")
    assert any('differs' in i for i in context(db,1)['issues'])


def test_cross_code_compliance_request_rejected(db):
    with pytest.raises(ValueError,match='differs'):
        run_compliance_for_project(db,1,'SAUDI_SBC_701')


def test_unverified_technical_pass_is_not_compliance_pass(db):
    db.execute("INSERT INTO design_basis_items(project_id,item_key,item_value,status) VALUES (1,'static_pressure_psi','60','APPROVED')")
    rows=run_compliance_for_project(db,1,'IPC')
    r=next(r for r in rows if r['rule_id']=='IPC-W-002')
    assert r['technical_status']=='PASS'
    assert r['status']=='NOT_EVALUATED'


def test_review_cannot_borrow_other_code_rule(db):
    with pytest.raises(ValueError,match='belong'):
        rule_review(db,rule_id='SBC701-W-002')


def test_verified_rule_requires_independent_benchmark(db):
    with pytest.raises(ValueError,match='benchmark'):
        rule_review(db)


def test_failed_benchmark_is_not_accepted(db):
    assert benchmark(db,actual=2.)=='FAIL'
    with pytest.raises(ValueError,match='benchmark'):
        rule_review(db)


@pytest.mark.parametrize('tol',[-1,float('nan'),float('inf')])
def test_invalid_tolerance_rejected(db,tol):
    with pytest.raises(ValueError,match='Tolerance'):
        benchmark(db,tolerance=tol)


def test_benchmark_units_required(db):
    with pytest.raises(ValueError,match='units'):
        benchmark(db,units='')


def test_rule_verification_is_evidence_record_not_blanket_approval(db):
    basis(db)
    assert benchmark(db)=='PASS'
    rule_review(db)
    rows=coverage(db,'IPC-2024')
    assert next(r for r in rows if r['rule_id']=='IPC-W-002')['verification_status']=='VERIFIED'
    assert context(db,1)['review_status']=='REVIEW_REQUIRED'


def test_unimplemented_rule_cannot_be_verified(db):
    benchmark(db)
    with pytest.raises(ValueError,match='unimplemented'):
        rule_review(db,rule_id='IPC-W-001')


def test_rule_review_goes_stale_after_loaded_data_change(db):
    benchmark(db)
    rule_review(db)
    db.execute("UPDATE code_rules SET source_note='changed' WHERE rule_id='IPC-W-002'")
    assert next(r for r in coverage(db,'IPC-2024') if r['rule_id']=='IPC-W-002')['verification_status']=='STALE'


def test_failed_rebenchmark_revokes_rule_verification(db):
    benchmark(db)
    rule_review(db)
    benchmark(db,actual=2)
    assert next(r for r in coverage(db,'IPC-2024') if r['rule_id']=='IPC-W-002')['verification_status']=='BENCHMARK_REVIEW_REQUIRED'


def test_benchmark_record_retains_full_review_evidence(db):
    basis(db)
    benchmark(db)
    event=json.loads(db.execute("SELECT snapshot_json FROM governance_events WHERE event_type='BENCHMARK_REVIEWED'").fetchone()[0])
    assert event['expected']==1 and event['actual']==1 and event['case']['units']=='L'
    row=saved(db)
    g=json.loads(row['governance_json'])
    b=next(b for b in g['verification_benchmarks'] if b['domain']=='water')
    assert b['expected_json']=='1.0' and b['reviewer']=='Synthetic independent reviewer'


def test_migration_is_additive_and_idempotent(tmp_path):
    # Construct the pre-governance schema and preserve a real existing row.
    conn=sqlite3.connect(tmp_path/'legacy.db')
    conn.row_factory=sqlite3.Row
    conn.executescript((Path(__file__).parents[1]/'database/schema.sql').read_text())
    conn.execute("INSERT INTO projects(project_id,project_name,building_type) VALUES (1,'Retain','Office')")
    conn.execute("INSERT INTO calculations(calc_id,project_id,calc_type,formula,inputs_json,status) VALUES ('OLD',1,'legacy','x','{}','PASS')")
    conn.commit()
    ensure_governance_schema(conn)
    ensure_governance_schema(conn)
    row=conn.execute('SELECT * FROM calculations').fetchone()
    assert row['calc_id']=='OLD' and row['status']=='PASS'
    assert row['review_status']=='LEGACY_UNVERIFIED' and row['is_current']==0
    assert conn.execute('SELECT project_name FROM projects').fetchone()[0]=='Retain'
    conn.close()


def test_rule_reload_preserves_projects_and_review_records(db):
    basis(db)
    load_all_rules(db)
    assert get_basis(db,1)['profile_id']=='IPC-2024'
    assert db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==2


def test_reports_label_stale_results(db):
    basis(db)
    saved(db)
    basis(db,'SBC701-2024')
    report=generate_calculation_report(db,1)
    assert report['calculations'][0]['review_status']=='STALE_RECALCULATION_REQUIRED'
    assert report['governance']['basis']['profile_id']=='SBC701-2024'


def test_revit_export_excludes_stale_results(db):
    basis(db)
    payload=empty_extract_payload('Synthetic.rvt','2026-10-26T00:00:00')
    payload['pipes']=[dict(revit_element_id='42',system='cold_water',length_m=1,nominal_diameter_mm=25)]
    import_revit_extract(db,1,payload)
    save_calculation(db,1,velocity_from_flow(1,25,'R-1'),target_type='pipe',target_id='RVT-42')
    assert '42' in export_results_for_revit(db,1)['results']
    basis(db,'SBC701-2024')
    assert not export_results_for_revit(db,1)['results']
