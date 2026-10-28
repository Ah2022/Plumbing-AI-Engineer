"""Shared IFC/Revit mapping workspace. Every diagnostic is partial and attributable."""
import json
import pandas as pd
import streamlit as st
from bim.mapping import (SERVICES,initial_mapping,initial_boundaries,diagnostics,snapshot,
    validate_snapshot,save_snapshot,compare_snapshots)
from bim.revit_handoff import checksum


def _rows(frame):
    return [{k:None if pd.isna(v) else v for k,v in row.items()} for row in frame.to_dict('records')]


def mapping_workspace(conn,pid,inventory,key):
    st.subheader('BIM mapping, connectivity and revisions')
    st.caption('Scope: reviewed source objects and extracted physical ports; topology diagnostics and revision comparison. '
        'Source data: object IDs, source systems, geometry and connector references. '
        'Validation: software contract tests; real-model round-trip acceptance pending. Code compliance is not evaluated.')
    st.caption('Nominal diameter, internal bore, design flow and elevation are separate reviewed inputs. '
        'Enter drainage invert levels in source-axis order. Multi-service fixtures require explicit connection requirements. '
        'Expected source/supply/discharge ends can be marked as intentional terminals with reviewer and evidence.')
    scope=key+'_'+checksum(inventory)
    with st.expander('Extracted source facts for mapping'):
        st.dataframe([{k:o.get(k) for k in ('source_id','element_id','kind','system','nominal_mm','internal_mm','flow_lps',
            'elevation_m','start_xyz_m','end_xyz_m','length_m','ports','properties','extraction_issues')} for o in inventory['objects']],
            width='stretch',alt='Source geometry, equipment properties, elevations and connector evidence before mapping')
    base=initial_mapping(inventory)
    uploaded=st.file_uploader('Restore reviewed mapping snapshot',type=['json'],max_upload_size=20,key=scope+'_restore')
    restored=None
    if uploaded is not None:
        try:
            restored=validate_snapshot(json.loads(uploaded.getvalue().decode('utf-8-sig')))
            if checksum(restored['inventory'])!=checksum(inventory):raise ValueError('Snapshot is from another extraction; compare revisions instead of restoring stale mappings')
            base=restored['mapping']
        except (ValueError,KeyError,TypeError) as error:
            st.error(str(error));return None
    mapping_identity=scope+'_'+checksum(base)
    frame=pd.DataFrame(base)
    for column in ('nominal_mm','internal_mm','design_flow_lps','elevation_m','invert_start_m','invert_end_m'):
        if column in frame:frame[column]=pd.to_numeric(frame[column]).astype(float)
    config={'service':st.column_config.SelectboxColumn('Service',options=SERVICES,required=True),
        'nominal_mm':st.column_config.NumberColumn('Nominal diameter (mm)'),
        'internal_mm':st.column_config.NumberColumn('Actual internal bore (mm)'),
        'design_flow_lps':st.column_config.NumberColumn('Design flow (L/s)'),
        'elevation_m':st.column_config.NumberColumn('Reviewed elevation (m)'),
        'invert_start_m':st.column_config.NumberColumn('Start invert (m)'),
        'invert_end_m':st.column_config.NumberColumn('End invert (m)')}
    edited=st.data_editor(frame,disabled=['source_id','connectivity_basis'],column_config=config,
        key=mapping_identity+'_object_map',hide_index=True,width='stretch',
        alt='Explicit per-source-object system, service, bore, flow, elevations, connectivity review and engineering evidence')
    boundary_base=restored['boundaries'] if restored else initial_boundaries(inventory)
    boundaries=[]
    if boundary_base:
        with st.expander('Review intentional terminals and open ends'):
            edited_boundaries=st.data_editor(pd.DataFrame(boundary_base),disabled=['port_id'],hide_index=True,width='stretch',
                key=mapping_identity+'_boundary_map',alt='Per-port intentional terminal decisions with reviewer and evidence')
            boundaries=_rows(edited_boundaries)
    reviewer=st.text_input('Snapshot engineering reviewer',value=restored['engineering_reviewer'] if restored else '',key=mapping_identity+'_reviewer')
    evidence=st.text_input('Snapshot evidence reference / revision',value=restored['evidence_reference'] if restored else '',key=mapping_identity+'_evidence')
    try:
        rows=_rows(edited)
        current=checksum(dict(mapping=rows,boundaries=boundaries,reviewer=reviewer,evidence=evidence))
    except (ValueError,TypeError) as error:
        st.error('Mapping must contain finite scalar values: '+str(error));return None
    result_key=mapping_identity+'_result_'+current
    if st.button('Run connectivity diagnostics',key=mapping_identity+'_diagnose'):
        try:
            st.session_state[result_key]=diagnostics(inventory,rows,boundaries)
        except (ValueError,TypeError,KeyError) as error:st.error(str(error))
    report=st.session_state.get(result_key)
    if report:
        st.caption('Technical status: '+report['technical_status']+' · Engineering review required · Code compliance not evaluated')
        st.dataframe(report['findings'],width='stretch',alt='Disconnected components, open ends, identity, flow, elevation, slope and fixture diagnostics')
        with st.expander('Connected component membership by system and service'):st.json(report['networks'])
        st.download_button('Download connectivity diagnostics',json.dumps(report,indent=2,allow_nan=False),
            file_name='bim-connectivity-diagnostics.json',mime='application/json',key=result_key+'_download')
    packet=None
    if reviewer.strip() and evidence.strip():
        try:packet=snapshot(inventory,rows,boundaries,reviewer,evidence)
        except (ValueError,KeyError,TypeError) as error:st.caption('Snapshot unavailable: '+str(error))
    if packet:
        st.download_button('Download reviewed extraction snapshot',json.dumps(packet,indent=2,allow_nan=False),
            file_name='bim-reviewed-snapshot.json',mime='application/json',key=result_key+'_snapshot_download')
        if st.button('Save immutable extraction snapshot',key=mapping_identity+'_save'):
            save_snapshot(conn,pid,packet);st.success('Extraction, mapping and diagnostics saved together. Engineering acceptance remains pending.')
    previous=st.file_uploader('Earlier extraction snapshot for revision comparison',type=['json'],max_upload_size=20,key=scope+'_previous')
    if previous is not None and packet:
        try:
            comparison=compare_snapshots(json.loads(previous.getvalue().decode('utf-8-sig')),packet)
            st.caption('Recalculation required: '+str(comparison['recalculation_required']))
            st.dataframe(comparison['objects'],width='stretch',alt='Stable-ID object additions, removals and changed fields between model revisions')
            st.json({k:v for k,v in comparison.items() if k!='objects'})
            st.download_button('Download model revision comparison',json.dumps(comparison,indent=2),file_name='bim-revision-comparison.json',key=result_key+'_compare')
        except (ValueError,KeyError,TypeError) as error:st.error(str(error))
    return packet


def round_trip_evidence(key):
    st.subheader('Revit round-trip evidence')
    st.caption('The native pyRevit Round Trip Test command extracts, imports, calculates reviewed water velocity, '
        'writes PLM result fields and re-extracts. It requires a disposable model copy, matching reviewed mapping, '
        'an existing engine project and correctly bound PLM parameters. Default dry run rolls back. '
        'Only a committed run can produce round-trip comparison evidence. No manual database editing is needed.')
    upload=st.file_uploader('Native Revit harness execution record',type=['json'],max_upload_size=20,key=key+'_harness_record')
    if upload is not None:
        try:
            from bim.round_trip import verify_round_trip
            record=json.loads(upload.getvalue().decode('utf-8-sig'))
            if record.get('schema_version')!='revit-native-harness-1' or record.get('write',{}).get('status')!='COMMITTED':
                raise ValueError('Record has no committed native write; dry-run evidence cannot pass a round trip')
            result=verify_round_trip(record['before'],record['after'],record['handoff'])
            st.metric('Re-extraction comparison',result['status'])
            st.caption('Uploaded execution metadata is recorded as supplied; this comparison does not authenticate the host or provide engineering approval.')
            st.dataframe(result['findings'],width='stretch',alt='Re-extracted identity, source facts and PLM status discrepancies')
            st.download_button('Download independently compared round-trip evidence',json.dumps(result,indent=2),file_name='bim-round-trip-verification.json',key=key+'_verified_record')
        except (ValueError,KeyError,TypeError) as error:st.error(str(error))
