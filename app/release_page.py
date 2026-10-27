"""Separate software regression evidence from project and live-model acceptance."""
import json
import streamlit as st
from reports.release_checks import run_release_benchmarks
from reports.review_workflow import review_readiness


def page_release_readiness():
    st.header('Release readiness')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.'); return
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
