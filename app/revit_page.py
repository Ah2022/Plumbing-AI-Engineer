"""Read/preview/import explicit extracts, calculate linked values and export guarded result files."""
import datetime
import json
import hashlib
import streamlit as st
from app.db_helpers import next_calc_id, save_calculation
from bim.exchange import import_revit_extract
from bim.schemas import validate_extract_payload
from bim.revit_handoff import build_handoff
from bim.linked_calculations import link_equipment_calculation
from calculations.hydraulics import velocity_from_flow
from calculations.drainage import check_min_slope
from models import MissingCodeDataError


def page_revit_exchange():
    st.header('Revit exchange')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.'); return
    conn = st.session_state.conn
    from database.review_schema import ensure_review_schema
    ensure_review_schema(conn)
    key = f'revit_exchange_{pid}'
    st.caption('Extract read-only in pyRevit → review/import here → calculate or attribute linked results → download a handoff → preview/dry-run in Revit. No geometry or native pipe sizes are written.')
    upload = st.file_uploader('Revit extract JSON',type=['json'],max_upload_size=20,key=key+'_upload')
    if st.button('Preview extract',disabled=upload is None,key=key+'_preview'):
        try:
            payload = json.loads(upload.getvalue().decode('utf-8-sig'))
            errors = validate_extract_payload(payload)
            if errors:
                raise ValueError('; '.join(errors))
            st.session_state[key+'_payload'] = payload
        except (ValueError,TypeError) as error:
            st.session_state.pop(key+'_payload',None); st.error(str(error))
    if st.button('Preview synthetic Revit extract',key=key+'_demo'):
        st.session_state[key+'_payload'] = dict(schema_version='1.0',units='SI',
            revit_model_id='SYNTHETIC-NOT-A-REAL-REVIT-MODEL',revit_model_name='Synthetic Revit exchange example',
            extracted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            pipes=[dict(revit_element_id='101',revit_unique_id='SYNTHETIC-PIPE-101',system='cold_water',length_m=10.,nominal_diameter_mm=25.)],
            fixtures=[],tanks=[],pumps=[])
    payload = st.session_state.get(key+'_payload')
    if payload:
        st.subheader('Extract preview')
        st.caption(f"{payload['revit_model_name']} · " + ' · '.join(f'{group}: {len(payload.get(group,[]))}' for group in ('pipes','fixtures','tanks','pumps')))
        with st.expander('Model identity, source values and skipped objects'):
            st.json(payload)
        confirm_key = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        confirmed = st.checkbox('I reviewed this model identity and extract; importing will invalidate current project results and retain their history',key=key+'_confirm_'+confirm_key)
        if st.button('Import reviewed extract',disabled=not confirmed,key=key+'_import'):
            try:
                counts = import_revit_extract(conn,pid,payload)
                st.success('Extract imported. Recalculate under the current model/basis. '+str(counts))
            except (ValueError,TypeError,KeyError) as error:
                st.error(str(error))
    models = conn.execute('SELECT * FROM revit_model_imports WHERE project_id=? ORDER BY model_name,model_key',(pid,)).fetchall()
    if not models:
        st.info('Import a reviewed extract to calculate linked results.'); return
    lookup = {r['model_key']:r for r in models}
    model_key = st.selectbox('Imported model',list(lookup),format_func=lambda k:lookup[k]['model_name'],key=key+'_model')
    scoped = key+'_'+model_key
    pipes = conn.execute('SELECT * FROM pipes WHERE project_id=? AND revit_model_key=? ORDER BY pipe_id',(pid,model_key)).fetchall()
    if pipes:
        with st.expander('Calculate a linked pipe check'):
            pipe_lookup = {r['pipe_id']:r for r in pipes}
            selected = st.selectbox('Linked pipe',list(pipe_lookup),format_func=lambda k:pipe_lookup[k]['revit_element_id']+' — '+pipe_lookup[k]['system'],key=scoped+'_pipe')
            pipe = pipe_lookup[selected]
            st.caption('Source nominal size is not an internal bore. Enter reviewed design inputs; these checks do not establish full network adequacy.')
            with st.form(scoped+'_check'):
                bore = st.number_input('Reviewed internal bore (mm)',min_value=0.,value=0.)
                flow = st.number_input('Reviewed design flow (L/s)',min_value=0.,value=0.)
                slope = st.number_input('Reviewed drainage slope (%)',min_value=0.,value=0.)
                reviewer = st.text_input('Linked-check reviewer / input evidence')
                run = st.form_submit_button('Calculate linked pipe check')
            if run:
                try:
                    if not reviewer.strip():
                        raise ValueError('Provide the linked input reviewer/evidence')
                    code = conn.execute('SELECT code_id FROM projects WHERE project_id=?',(pid,)).fetchone()[0]
                    if pipe['system'] in ('cold_water','hot_water'):
                        result = velocity_from_flow(flow,bore,next_calc_id(conn,pid,'cold_water_velocity_check'))
                    elif pipe['system']=='drainage':
                        result = check_min_slope(conn,code,pipe['nominal_diameter_mm'],slope,next_calc_id(conn,pid,'drainage_min_slope_check'))
                    else:
                        raise ValueError('This linked-pipe pilot supports water velocity and drainage minimum slope only')
                    result.inputs.update(revit_source_sha256=lookup[model_key]['source_sha256'],input_evidence=reviewer)
                    save_calculation(conn,pid,result,target_type='pipe',target_id=selected)
                    st.success(f'Linked result saved: {result.result_value} {result.result_unit}; {result.status}. Engineering review remains required.')
                except (ValueError,MissingCodeDataError) as error:
                    st.error(str(error))
    with st.expander('Attribute a current tank or pump calculation'):
        target_type = st.selectbox('Equipment kind',['tank','pump'],key=scoped+'_kind')
        table, field, calc_type = ('tanks','tank_id','tank_sizing') if target_type=='tank' else ('pumps','pump_id','pump_duty_selection')
        targets = conn.execute(f'SELECT * FROM {table} WHERE project_id=? AND revit_model_key=?',(pid,model_key)).fetchall()
        calcs = conn.execute('SELECT calc_id FROM calculations WHERE project_id=? AND calc_type=? AND is_current=1',(pid,calc_type)).fetchall()
        if targets and calcs:
            target = st.selectbox('Revit equipment target',[str(r[field]) for r in targets],key=scoped+'_target_'+target_type)
            calc = st.selectbox('Equipment calculation',[r['calc_id'] for r in calcs],key=scoped+'_calc_'+target_type)
            actor = st.text_input('Linking reviewer',key=scoped+'_actor')
            evidence = st.text_input('Equipment applicability evidence',key=scoped+'_evidence')
            if st.button('Attribute equipment calculation',key=scoped+'_link'):
                try:
                    st.success('Linked copy saved: '+link_equipment_calculation(conn,pid,model_key,target_type,target,calc,actor,evidence))
                except ValueError as error:
                    st.error(str(error))
        else:
            st.caption('A classified equipment target and a current matching calculation are required.')
    st.subheader('Result handoff preview')
    handoff = build_handoff(conn,pid,model_key)
    st.caption(f"{len(handoff['payload']['updates'])} linked element(s). Review status: REVIEW_REQUIRED.")
    for blocker in handoff['payload']['blockers']:
        st.caption('• '+blocker)
    with st.expander('Preview exact PLM values and source identity'):
        st.json(handoff)
    st.download_button('Download Revit handoff JSON',json.dumps(handoff,indent=2,allow_nan=False),file_name='plm_revit_handoff.json',mime='application/json')
    st.caption('In pyRevit, Review Results validates model/element identity, unchanged source geometry, PLM bindings and storage types. Preview is default; dry run rolls back; committing requires an explicit choice.')
