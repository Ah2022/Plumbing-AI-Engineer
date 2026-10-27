"""Separate software regression evidence from project and live-model acceptance."""
import json
import streamlit as st
from reports.release_checks import run_release_benchmarks
from reports.review_workflow import review_readiness
from validation.gate import validation_gate
from validation.suite import run_validation,review_bundle


def page_release_readiness():
    st.header('Release readiness')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.'); return
    st.subheader('Phase 1 A: independent engineering validation')
    gate=validation_gate()
    st.warning('Engineering validation pending. Numerical agreement alone does not verify a release.')
    st.caption('Designated reviewer: BIM MANAGER. Reviewer identity, plumbing-engineering qualifications, independence and signed acceptance evidence remain pending.')
    st.dataframe([{'Project':r['building_type'],'Reference type':'Illustrative candidate',
        'Engineering review':r['engineering_status']} for r in gate['projects']],
        width='stretch',alt='Five building-type reference candidates and independent engineering review status')
    st.caption(f"{gate.get('core_calculations',0)} core entry points · {gate.get('interactive_forms',0)} converted forms · {gate.get('pending_reference_entries',0)} entries await engineering acceptance")
    with st.expander('Engineering acceptance gaps'):
        for issue in gate['issues']:st.caption('• '+issue)
    st.download_button('Download BIM MANAGER review package',review_bundle(),file_name='phase1a_engineering_review.zip',mime='application/zip')
    if st.button('Run five golden reference projects'):
        st.session_state['phase1a_evidence']=run_validation()
    evidence=st.session_state.get('phase1a_evidence')
    if evidence:
        st.metric('Golden comparison status',evidence['software_status'])
        st.caption('Uses frozen hand references and recorded actual EPANET 2.2 results. This button does not rerun EPANET or approve the references. Engineering acceptance remains pending.')
        st.dataframe([dict(project=r['project_id'],software=r['software_status'],water=r['water']['technical_status'],
            epanet=r['epanet']['software_status'],engineering=r['engineering_status']) for r in evidence['projects']],
            width='stretch',alt='Project-by-project golden agreement, technical pressure findings and pending engineering acceptance')
        st.dataframe([dict(r,expected=str(r.get('expected')),actual=str(r.get('actual'))) for r in evidence['methods']],
            width='stretch',alt='Core method golden comparisons against independent candidate values')
        st.download_button('Download Phase 1 A comparison evidence',json.dumps(evidence,indent=2,allow_nan=False),file_name='phase1a_comparison.json',mime='application/json')
    st.subheader('Existing software benchmarks')
    st.caption('Independent hand-calculation benchmarks use isolated synthetic sources. They do not approve code data, manufacturer selection or real-model writeback.')
    key = f'release_evidence_{pid}'
    if st.button('Run remaining-system benchmarks'):
        st.session_state[key] = run_release_benchmarks()
    report = st.session_state.get(key)
    if report:
        st.metric('Software benchmark status',report['software_status'])
        st.dataframe(report['cases'],width='stretch',alt='Independent hot-water, storage, pump and stormwater benchmark results and tolerances')
        st.caption('Engineering acceptance: REVIEW_REQUIRED. Live Revit writeback: NOT_VALIDATED until separately witnessed on a test model.')
        st.download_button('Download release evidence',json.dumps(report,indent=2),file_name='plm_release_evidence.json',mime='application/json')
    st.subheader('Current project review gates')
    readiness = review_readiness(st.session_state.conn,pid)
    for issue in readiness['issues']:
        st.caption('• '+issue)
    st.caption('Remaining acceptance: approved project basis and verified applicable code data; manufacturer curves/selections; complete fixture/topology mapping; witnessed Revit parameter binding and rollback/commit tests.')
