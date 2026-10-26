"""Engineer-facing project adoption, coverage and verification records."""
import json
import streamlit as st

from compliance.governance import (
    profiles, profile, get_basis, set_basis, approve_basis, context,
    coverage, review_rule, record_benchmark,
)

RESULT_SESSION_KEYS = ('fixture_list', 'hw_fixture_list', 'storm_intensity', 'storm_flow_lps',
                       'compliance_results', 'qaqc_results','network_result')


def clear_result_session():
    for key in RESULT_SESSION_KEYS:
        st.session_state.pop(key, None)


def page_code_profiles():
    st.header('Code profiles and verification')
    conn = st.session_state.conn
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.')
        return
    basis = get_basis(conn, pid)
    choices = {p['profile_id']: p for p in profiles()}
    selected = basis['profile_id'] if basis else 'IPC-2024'
    if selected not in choices:
        selected = 'IPC-2024'
    p = choices[selected]
    st.caption('IPC 2024 is the first verification target. Edition identity, project adoption, '
               'and verified engineering coverage are separate decisions.')
    st.info('Changing a code profile or design basis retains historical results and marks them stale. '
            'Recalculate under the new basis. Unit selection records the design basis; it does not '
            'change the explicit units on existing calculation forms.')
    criteria = basis['criteria'] if basis else {}
    with st.form('code_basis'):
        profile_id = st.selectbox('Code profile', list(choices), index=list(choices).index(selected))
        jurisdiction = st.text_input('Jurisdiction / project location', criteria.get('jurisdiction', ''))
        authority = st.text_input('Adopting authority', criteria.get('authority', ''))
        amendments = st.text_area('Local amendments (state none explicitly if confirmed)', criteria.get('amendments', ''))
        occupancy = st.text_input('Occupancy / supported use', criteria.get('occupancy', ''))
        systems = st.multiselect('Systems in scope', ['water','drainage','vent','storm'], default=criteria.get('systems', []))
        units = st.selectbox('Design-basis units', ['SI','US_CUSTOMARY'], index=1 if criteria.get('units') == 'US_CUSTOMARY' else 0)
        method = st.text_area('Selected methods and references', criteria.get('method', ''))
        exclusions = st.text_area('Exclusions / unsupported arrangements', criteria.get('exclusions', ''))
        precedence = st.text_area('Requirement precedence / conflict resolution', criteria.get('precedence', ''))
        actor = st.text_input('Recorded by')
        if st.form_submit_button('Save draft code basis'):
            try:
                set_basis(conn, pid, profile_id, dict(jurisdiction=jurisdiction, authority=authority,
                    amendments=amendments, occupancy=occupancy, systems=systems, units=units,
                    method=method, exclusions=exclusions, precedence=precedence), actor)
                clear_result_session()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    g = context(conn, pid)
    st.write({'review_status': g['review_status'], 'profile': g['basis']['profile_id'] if g['basis'] else None,
              'basis_revision': g['basis']['revision'] if g['basis'] else None,
              'adoption_status': g['basis']['basis_status'] if g['basis'] else 'NOT_DECLARED'})
    for issue in g['issues']:
        st.caption(issue)
    if not g['basis']:
        return
    p = profile(g['basis']['profile_id'])
    st.link_button('Edition source / metadata', p['source_url'])
    st.caption(p['source_limit'])
    with st.form('approve_code_basis'):
        reviewer = st.text_input('Adoption reviewer')
        evidence = st.text_area('Project adoption evidence / approved design-basis reference')
        confirmed = st.checkbox('I reviewed the project adoption and design-basis criteria')
        if st.form_submit_button('Approve project adoption'):
            try:
                if not confirmed:
                    raise ValueError('Confirm review before approving adoption')
                approve_basis(conn, pid, reviewer, evidence)
                clear_result_session()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    rows = coverage(conn, p['profile_id'])
    st.subheader('Rule coverage and applicability')
    st.dataframe(rows, width='stretch', alt='Rule coverage, references and verification status')
    st.download_button('Download coverage matrix', json.dumps(rows, indent=2),
                       file_name=f"{p['profile_id']}-coverage.json", mime='application/json')
    benchmarks = [dict(r) for r in conn.execute('SELECT * FROM verification_benchmarks WHERE profile_id=? ORDER BY benchmark_id', (p['profile_id'],))]
    st.subheader('Independent benchmark acceptance records')
    st.dataframe(benchmarks, width='stretch', alt='Pending and reviewed profile benchmark records')
    with st.expander('Record an independent benchmark'):
        with st.form('benchmark_review'):
            bid = st.selectbox('Benchmark', [r['benchmark_id'] for r in benchmarks])
            expected = st.number_input('Independently established expected value', value=0.0)
            actual = st.number_input('Observed engine value', value=0.0)
            tolerance = st.number_input('Absolute tolerance', min_value=0.0, value=0.0)
            inputs = st.text_area('Original benchmark inputs and units (JSON)', '{}')
            bunit = st.text_input('Result unit')
            policy = st.text_input('Tolerance rationale / comparison policy')
            case = st.text_input('Case purpose, method and applicability')
            br = st.text_input('Independent benchmark reviewer')
            bs = st.text_area('Independent expected-result source / reviewed reference')
            if st.form_submit_button('Record benchmark result'):
                try:
                    status = record_benchmark(conn, bid, expected, actual, tolerance, br, bs,
                        inputs=json.loads(inputs), units=bunit, comparison_policy=policy, case_reference=case)
                    clear_result_session()
                    st.success(f'Benchmark recorded: {status}. This does not approve a code package.')
                except (ValueError, TypeError) as e:
                    st.error(str(e))
    with st.expander('Review a supplied rule'):
        with st.form('rule_review'):
            rid = st.selectbox('Rule', [r['rule_id'] for r in rows])
            status = st.selectbox('Verification decision', ['PENDING','VERIFIED','UNSUPPORTED'])
            applicability = st.text_area('Applicability and limitations')
            ri = st.text_input('Required rule inputs')
            ru = st.text_input('Rule input/result units')
            exceptions = st.text_area('Exceptions and unsupported cases (state none explicitly)')
            rr = st.text_input('Rule reviewer')
            rs = st.text_area('Authoritative clause/table review evidence')
            rb = st.selectbox('Supporting benchmark', [''] + [r['benchmark_id'] for r in benchmarks])
            if st.form_submit_button('Save rule review'):
                try:
                    review_rule(conn, p['profile_id'], rid, status, applicability, ri, ru, exceptions, rr, rs, rb or None)
                    clear_result_session()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    st.download_button('Download verification context', json.dumps(context(conn,pid), indent=2),
                       file_name='verification-context.json', mime='application/json')
