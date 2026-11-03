"""Read-only source register and explicitly triggered public candidate runs."""
import json
import streamlit as st
from validation.public_benchmarks import catalogue,case,artifact_path,import_bytes,run_case,save_result,recorded_result,runner_fingerprint,sha,CATALOGUE


def public_benchmarks_panel():
    st.subheader('Public benchmark candidates')
    st.warning('Software reference coverage only. Public benchmarks and uncalibrated open data do not approve a plumbing design or unlock professional engineering acceptance.')
    register=catalogue()
    with st.expander('Pinned public sources and licensing/provenance screen'):
        st.dataframe(register['sources'],width='stretch',alt='Six public repositories, pinned commits, recorded source terms and engineering-review exclusions')
        st.download_button('Download public benchmark catalogue',json.dumps(register,indent=2),file_name='public-benchmark-catalogue.json',mime='application/json')
    ids=[c['id'] for c in register['cases']];lookup={c['id']:c for c in register['cases']}
    identity=st.selectbox('Public benchmark candidate',ids,format_func=lambda k:lookup[k]['title'],key='public_benchmark_candidate')
    record=case(identity)
    st.caption('Evidence: '+record['evidence_class']+' · SOFTWARE_REFERENCE_ONLY · ENGINEERING_REVIEW_REQUIRED')
    st.write('Coverage: '+', '.join(record['modules']))
    st.write('Limit: '+record['limitation'])
    st.link_button('Open pinned upstream source','https://github.com/'+record['repository']+'/tree/'+record['commit'])
    if not record['artifacts']:
        st.info('Source registered only. A complete reviewed input/data bundle is not installed; no executed comparison or calibration is claimed.');return
    st.caption('Licensing/provenance screen: '+record['license_status']+'. Local-only assets are excluded from the public repository.')
    for a in record['artifacts']:
        p=artifact_path(a);available=p.is_file();valid=available and sha(p.read_bytes())==a['sha256']
        st.caption(a['role']+': '+('pinned bytes installed' if valid else 'checksum mismatch' if available else 'missing input')+' · SHA-256 '+a['sha256'])
        if not valid:
            st.link_button('Pinned '+a['role']+' source',a['url'])
            upload=st.file_uploader('Import pinned '+a['role']+' bytes',key='public_import_'+identity+'_'+a['role'],max_upload_size=2)
            if upload and st.button('Verify and install '+a['role'],key='public_install_'+identity+'_'+a['role']):
                try:import_bytes(identity,a['role'],upload.getvalue());st.success('Pinned input installed with engineering review still pending.');st.rerun()
                except ValueError as error:st.error(str(error))
    key='public_benchmark_result_'+identity
    if st.button('Run public benchmark candidate',key='public_run_'+identity):
        try:
            with st.spinner('Running isolated public software comparison…'):
                report=run_case(identity);save_result(report);st.session_state[key]=report
        except (ValueError,OSError,KeyError,TypeError) as error:st.error('Benchmark could not run: '+str(error))
    report=st.session_state.get(key)
    if report is None:
        report=recorded_result(identity)
        if report:st.caption('Recorded public software execution. Run the candidate to create a fresh local result.')
    if report:
        if report['runner_sha256']!=runner_fingerprint() or report['catalogue_sha256']!=sha(CATALOGUE.read_bytes()):
            st.info('Benchmark runner or catalogue changed. Rerun before reviewing this result.');return
        installed={a['role']:sha(artifact_path(a).read_bytes()) if artifact_path(a).is_file() else None for a in record['artifacts']}
        if report.get('software_status') in ('PASS','FAIL') and report.get('input_sha256')!=installed:
            st.info('Public input bytes changed or are missing. Import the pinned files and rerun; previous results are hidden.');return
        st.metric('Public software comparison',report['software_status'])
        st.caption('Engineering status: ENGINEERING_REVIEW_REQUIRED. Approval eligible: false. A software PASS is not a field-calibrated or professionally signed result.')
        if report.get('comparisons'):
            st.dataframe([dict(r,actual=json.dumps(r['actual']),expected=json.dumps(r['expected'])) for r in report['comparisons']],
                width='stretch',alt='Public benchmark source invariants, conservation or mapped solver differences with explicit expected values and tolerances')
        for issue in report.get('issues',[]):st.caption(str(issue))
        st.download_button('Download public benchmark findings',json.dumps(report,indent=2),file_name=identity+'-software-evidence.json',mime='application/json')
