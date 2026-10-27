"""Review tools embedded in Report / Export."""
import json
import streamlit as st
from reports.review_workflow import (review_readiness, propose_override, build_review_packet,
    save_review_revision, compare_review_revisions, verify_review_packet, overrides)
from reports.replay import replay_calculation


def review_tools(conn, project_id):
    key = f'review_tools_{project_id}'
    st.subheader('Review readiness and reproducibility')
    ready = review_readiness(conn, project_id)
    st.caption(f"{ready['current_calculations']} current calculations · {ready['historical_calculations']} historical records · {ready['review_status']}")
    for issue in ready['issues']:
        st.caption('• ' + issue)
    if st.button('Build reproducible review packet', key=key+'_build'):
        st.session_state[key+'_packet'] = build_review_packet(conn, project_id)
    packet = st.session_state.get(key+'_packet')
    if packet:
        st.caption('Last-built evidence packet. Includes captured design tables and user-imported packages. Rebuild after editing project data.')
        st.download_button('Download review packet (JSON)', json.dumps(packet,indent=2,allow_nan=False),
                           file_name=f'project_{project_id}_review_packet.json',mime='application/json')
    with st.expander('Verify a downloaded review packet'):
        upload = st.file_uploader('Review packet JSON',type=['json'],max_upload_size=40,key=key+'_upload')
        if upload and st.button('Verify packet checksum',key=key+'_verify'):
            try:
                info = verify_review_packet(json.loads(upload.getvalue().decode('utf-8-sig')))
                st.success('Packet content checksum matches. This is not an engineering signature or approval.')
                st.json(info)
            except (ValueError,TypeError,KeyError) as error:
                st.error(str(error))
    with st.expander('Save and compare review revisions'):
        with st.form(key+'_revision'):
            label = st.text_input('Review revision label',value='R1')
            actor = st.text_input('Revision recorded by')
            if st.form_submit_button('Save immutable review revision'):
                try:
                    save_review_revision(conn, project_id, label, actor)
                    st.success('Review revision saved; earlier evidence remains available.')
                except ValueError as error:
                    st.error(str(error))
        revisions = conn.execute('SELECT * FROM review_snapshots WHERE project_id=? ORDER BY revision',(project_id,)).fetchall()
        if revisions:
            lookup = {r['snapshot_id']:r for r in revisions}
            selected = st.selectbox('Saved review revision',list(lookup),format_func=lambda k,rows=lookup:f"{rows[k]['revision']}: {rows[k]['label']}",key=key+'_snapshot')
            st.download_button('Download saved revision',lookup[selected]['packet_json'],file_name=f"review_{lookup[selected]['revision']}.json",mime='application/json')
            if len(revisions)>1:
                previous = st.selectbox('Compare against revision',list(lookup),format_func=lambda k,rows=lookup:f"{rows[k]['revision']}: {rows[k]['label']}",key=key+'_previous')
                st.json(compare_review_revisions(conn,project_id,previous,selected))
    calculations = conn.execute('SELECT calc_id,calc_type FROM calculations WHERE project_id=? ORDER BY created_at DESC',(project_id,)).fetchall()
    if calculations:
        with st.expander('Reproduce a saved calculation or record an override proposal'):
            lookup = {r['calc_id']:r['calc_type'] for r in calculations}
            chosen = st.selectbox('Recorded calculation',list(lookup),format_func=lambda k:f'{k} ({lookup[k]})',key=key+'_calc')
            if st.button('Reproduce from recorded inputs',key=key+'_replay'):
                try:
                    st.json(replay_calculation(conn,project_id,chosen))
                except (ValueError,TypeError,KeyError) as error:
                    st.error(str(error))
            st.caption('Overrides are attributed proposals with reasons. Original computed values and engineering-review status remain intact.')
            with st.form(key+'_override'):
                field = st.selectbox('Proposed override field',['result_value','required_value','selected_value'])
                value = st.number_input('Proposed value',value=0.)
                unit = st.text_input('Proposed value unit')
                actor = st.text_input('Override reviewer')
                reason = st.text_area('Override reason and evidence')
                if st.form_submit_button('Record override proposal'):
                    try:
                        propose_override(conn,project_id,chosen,field,value,unit,actor,reason)
                        st.success('Proposal recorded; it has not replaced the calculation.')
                    except ValueError as error:
                        st.error(str(error))
            proposals = overrides(conn,project_id)
            if proposals:
                st.dataframe(proposals,width='stretch',alt='Recorded override proposals, reviewers and reasons; computed values remain unchanged')
