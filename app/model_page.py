"""Local IFC/DXF pilot: inspect evidence, review mappings, save partial checks."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import pandas as pd
import streamlit as st
from app.db_helpers import next_calc_id, save_calculation
from bim.model_intake import inspect_model
from bim.model_review import initial_mapping, review_model
from compliance.governance import context
from models import CalculationResult, MissingCodeDataError

ROOT = Path(__file__).resolve().parents[1]


def page_model_review():
    st.header('CAD / IFC design checks')
    pid = st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.')
        return
    conn = st.session_state.conn
    code = conn.execute('SELECT code_id FROM projects WHERE project_id=?', (pid,)).fetchone()[0]
    scope = f'{pid}_{context(conn, pid)["fingerprint"]}'
    key = 'model_intake_' + scope
    st.info('Local pilot: IFC and DXF intake, mapped water velocity and straight-segment drainage slope. '
            'Findings retain engineering review requirements and partial coverage.')
    st.caption('Native DWG: export to DXF or IFC. No model is sent to an external conversion service. '
               'Optional parsers: python -m pip install -r requirements-models.txt')
    upload = st.file_uploader('Upload plumbing model (IFC or DXF, up to 20 MB)', type=['ifc', 'dxf'],
                              max_upload_size=20, key=key + '_upload')
    unit = st.selectbox('DXF drawing units', ['Use declared file units', 'mm', 'm', 'ft', 'in'], key=key + '_unit')
    demo = st.selectbox('Synthetic test model', ['IFC', 'DXF'], key=key + '_demo_type')
    import_clicked = st.button('Inspect uploaded model', disabled=upload is None)
    demo_clicked = st.button('Load synthetic model')
    if import_clicked or demo_clicked:
        try:
            filename = upload.name if import_clicked else 'model_pilot.' + demo.lower()
            data = upload.getvalue() if import_clicked else (ROOT / 'examples' / filename).read_bytes()
            inventory = inspect_model(data, filename, dxf_unit=None if unit == 'Use declared file units' else unit)
            st.session_state[key] = inventory
            st.session_state.pop(key + '_report', None)
        except (ValueError, OSError, RuntimeError) as error:
            st.session_state.pop(key, None)
            st.session_state.pop(key + '_report', None)
            st.error(str(error))
    inventory = st.session_state.get(key)
    if inventory is None:
        st.caption('Inspect a model to see source geometry, units, connections and editable engineering mappings.')
        return
    digest = inventory['source_sha256']
    model_key = key + '_' + digest
    st.subheader('Extracted model evidence')
    st.caption(f"{inventory['filename']} · {inventory['format']} {inventory['schema']} · {len(inventory['objects'])} objects")
    with st.expander('Source identity, units, properties and explicit port connections'):
        st.json(inventory)
    for limitation in inventory['limitations']:
        st.caption(limitation)
    st.dataframe([{k: obj.get(k) for k in ('source_id', 'source_class', 'kind', 'name', 'system',
        'length_m', 'horizontal_run_m', 'axis_segment_count', 'geometry_status', 'start_xyz_m', 'end_xyz_m')}
        for obj in inventory['objects']], width='stretch', alt='Read-only source objects and extracted geometry in metres')
    st.download_button('Download extracted model evidence', json.dumps(inventory, indent=2, allow_nan=False),
        file_name='model-evidence.json', mime='application/json')
    identity = st.text_input('Model identifier (keep stable across revisions)',
        inventory.get('model_id') or Path(inventory['filename']).stem, key=model_key + '_identity')
    st.subheader('Review the engineering mapping')
    st.caption('IFC pipe objects are initially included; DXF linework requires an explicit Include selection. '
               'Enter actual internal bore for water. For drainage, enter upstream/downstream invert levels '
               'against the axis start/end order, then confirm direction. Source centreline Z is never used as invert.')
    mapping = initial_mapping(inventory)
    numeric = ['nominal_mm', 'internal_mm', 'design_flow_lps', 'invert_start_m', 'invert_end_m']
    frame = pd.DataFrame(mapping)
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column]).astype(float)
    config = {column: st.column_config.NumberColumn(column.replace('_', ' ')) for column in numeric}
    config['service'] = st.column_config.SelectboxColumn('Service', options=['UNMAPPED', 'cold_water', 'hot_water', 'drainage'], required=True)
    with st.form(model_key + '_review'):
        edited = st.data_editor(frame, disabled=['source_id', 'source_name', 'source_system'], column_config=config, hide_index=True,
            column_order=['include', 'source_name', 'service', 'nominal_mm', 'internal_mm', 'design_flow_lps',
                'invert_start_m', 'invert_end_m', 'direction_confirmed', 'input_reference', 'exclusion_reason',
                'source_id', 'source_system'],
            width='stretch', key=model_key + '_mapping', alt='Per-object scope, service, engineering inputs and evidence references')
        mapping_reference = st.text_input('Mapping reviewer / evidence reference', key=model_key + '_reviewer')
        velocity_limit = st.number_input('Project water velocity limit (m/s; 0 means missing)', min_value=0.0, value=0.0)
        velocity_reference = st.text_input('Water velocity criterion reference')
        reviewed = st.checkbox('I reviewed the selected scope, service, units, inputs and their evidence')
        run = st.form_submit_button('Run and save model checks')
    if run:
        try:
            if not identity.strip():
                raise ValueError('A stable model identifier is required.')
            # Pandas nulls must become missing inputs, never NaN in calculation traces.
            rows = [{k: (None if v is None or (isinstance(v, float) and pd.isna(v)) else v)
                     for k, v in row.items()} for row in edited.to_dict('records')]
            report = review_model(conn, code, inventory, rows, mapping_reference=mapping_reference, reviewed=reviewed,
                velocity_limit_m_s=velocity_limit or None, velocity_reference=velocity_reference)
            report['governance'] = context(conn, pid)
            report['model_identifier'] = identity
            criteria = dict(mapping_reference=mapping_reference, velocity_limit_m_s=velocity_limit or None,
                            velocity_reference=velocity_reference)
            result = CalculationResult(next_calc_id(conn, pid, 'model_design_check'), 'model_design_check',
                'Velocity = Q / internal area; straight drainage slope = 100 * invert fall / plan run',
                dict(source_sha256=digest, adapter_revision=inventory['adapter_revision'], mappings=rows,
                     criteria=criteria, source_objects=inventory['objects'], source_units=inventory['unit_evidence']),
                report, report['failure_count'], 'failed checks', status='FAIL' if report['failure_count'] else 'WARNING',
                reference=f'{code}; per-object criterion/table references', notes='Partial model-design pilot; review required.')
            save_calculation(conn, pid, result, target_type='model_design',
                             target_id=hashlib.sha256(identity.encode()).hexdigest())
            report['calc_id'] = result.calc_id
            st.session_state[model_key + '_last_mapping'] = deepcopy(rows)
            st.session_state[key + '_report'] = report
        except (ValueError, TypeError, MissingCodeDataError) as error:
            st.session_state.pop(key + '_report', None)
            st.error(str(error))
    report = st.session_state.get(key + '_report')
    if report:
        st.subheader('Last saved model check')
        st.metric('Failed checks', report['failure_count'])
        st.caption(f"{report['technical_status']} · Partial coverage · Engineering review required · {report['calc_id']}")
        st.caption('These findings apply to the last saved mapping. Run and save again after editing inputs.')
        st.dataframe(report['findings'], width='stretch', alt='Per-object check results, missing data and unevaluated scope')
        st.download_button('Download model findings (JSON)', json.dumps(report, indent=2, allow_nan=False),
            file_name='model-findings.json', mime='application/json')
        st.download_button('Download model findings (CSV)', pd.DataFrame(report['findings']).to_csv(index=False),
            file_name='model-findings.csv', mime='text/csv')
