"""Native mapped-network editing. Unknown imported properties are retained."""
from copy import deepcopy
import json
import pandas as pd
import streamlit as st


def parse_network(text, code):
    def reject(value):
        raise ValueError('Non-finite JSON constant: ' + value)
    model = json.loads(text, parse_constant=reject)
    if not isinstance(model, dict) or model.get('code_id') != code:
        raise ValueError('Network code_id must match the active project code')
    for name in ('nodes', 'pipes'):
        if not isinstance(model.get(name), list) or not all(isinstance(row, dict) for row in model[name]):
            raise ValueError(f'{name} must be a list of mapped objects')
    if not isinstance(model.get('materials', {}), dict) or not isinstance(model.get('catalogues', {}), dict):
        raise ValueError('Materials and catalogues must be mappings')
    if not all(isinstance(value, dict) for value in model.get('materials', {}).values()):
        raise ValueError('Each material must be a mapped object')
    if not all(isinstance(value, list) and all(isinstance(row, dict) for row in value)
               for value in model.get('catalogues', {}).values()):
        raise ValueError('Each catalogue must be a list of mapped sizes')
    return model


def merge_rows(original, edited):
    """Preserve nested, non-editable properties by stable row id, never row position."""
    identity = 'size_id' if original and 'size_id' in original[0] else 'id'
    previous = {row.get(identity): row for row in original}
    result = []
    for row in edited:
        merged = deepcopy(previous.get(row.get(identity), {}))
        for key, value in row.items():
            if value is None or (isinstance(value, float) and pd.isna(value)) or value == '':
                merged.pop(key, None)
            else:
                merged[key] = value
        result.append(merged)
    return result


def edit_rows(rows, columns, key, title):
    st.subheader(title)
    names = list(dict.fromkeys(columns + [k for row in rows for k, v in row.items()
                                        if not isinstance(v, (dict, list))]))
    frame = pd.DataFrame([{k: row.get(k) for k in names} for row in rows], columns=names)
    configs = {name: st.column_config.TextColumn(name.replace('_', ' ').capitalize()) for name in names
               if name in ('id', 'kind', 'from_node', 'to_node', 'material', 'selected_size_id',
                           'context', 'demand_reference', 'minimum_size_reference', 'minimum_slope_reference')}
    numeric = {'elevation_m', 'design_flow_lps', 'water_wsfu', 'required_residual_head_m',
        'drainage_dfu', 'length_m', 'minimum_nominal_mm', 'fittings_k', 'equipment_loss_m',
        'horizontal_run_m', 'nominal_mm', 'selected_source_nominal_in', 'minimum_slope_pct',
        'c_factor', 'friction_factor', 'internal_mm', 'continuous_flow_lps'}
    for name in numeric.intersection(names):
        frame[name] = pd.to_numeric(frame[name], errors='raise').astype(float)
        configs[name] = st.column_config.NumberColumn(name.replace('_', ' ').capitalize())
    edited = st.data_editor(frame, num_rows='dynamic', hide_index=True, width='stretch',
        key=key, column_config=configs, alt=title + '; add, edit or delete mapped rows')
    return merge_rows(rows, edited.to_dict('records'))


def network_tables(model, key, water):
    edited = deepcopy(model)
    edited['network_id'] = st.text_input('Network ID', str(model.get('network_id', '')), key=key + '_id')
    edited['root'] = st.text_input('Source node ID' if water else 'Outlet node ID',
                                  str(model.get('root', '')), key=key + '_root')
    edited['basis_reference'] = st.text_input('Design criteria reference', model.get('basis_reference', ''), key=key + '_basis')
    if water:
        for field, label in [('available_head_m', 'Available supply head (m)'),
                             ('velocity_limit_m_s', 'Velocity limit (m/s)')]:
            edited[field] = st.number_input(label, value=float(model.get(field, 0)), min_value=0.0, key=key + field)
        edited['velocity_reference'] = st.text_input('Velocity criterion reference', model.get('velocity_reference', ''), key=key + '_velocity_ref')
        edited['service'] = st.selectbox('Water service', ['cold_water', 'hot_water'],
            index=['cold_water', 'hot_water'].index(model.get('service', 'cold_water')), key=key + '_service')
        flow_options = ['explicit_terminal_flows', 'wsfu_table']
        edited['flow_basis'] = st.selectbox('Demand basis', flow_options,
            index=flow_options.index(model.get('flow_basis', flow_options[0])), key=key + '_flow')
        edited['control_type'] = st.selectbox('Demand control', ['flush_tank', 'flush_valve'],
            index=['flush_tank', 'flush_valve'].index(model.get('control_type', 'flush_tank')), key=key + '_control')
    st.caption('Use matching node IDs in each pipe. Water pipes run from source to fixtures; drainage pipes run from fixtures to outlet. All lengths and elevations are metres.')
    node_columns = ['id', 'kind', 'elevation_m'] + (
        ['design_flow_lps', 'water_wsfu', 'required_residual_head_m', 'demand_reference'] if water
        else ['drainage_dfu', 'demand_reference'])
    edited['nodes'] = edit_rows(model.get('nodes', []), node_columns, key + '_nodes', 'Nodes and fixture loads')
    pipe_columns = ['id', 'from_node', 'to_node', 'length_m'] + (
        ['material', 'selected_size_id', 'minimum_nominal_mm', 'fittings_k', 'equipment_loss_m'] if water
        else ['horizontal_run_m', 'nominal_mm', 'selected_source_nominal_in', 'context',
              'minimum_nominal_mm', 'minimum_slope_pct', 'minimum_slope_reference'])
    edited['pipes'] = edit_rows(model.get('pipes', []), pipe_columns, key + '_pipes', 'Pipe connections and design criteria')
    if water:
        with st.expander('Materials and manufacturer size catalogues'):
            st.caption('Replace synthetic catalogue dimensions and material coefficients with referenced manufacturer data.')
            materials = [dict(id=name, **value) for name, value in model.get('materials', {}).items()]
            material_rows = edit_rows(materials, ['id', 'method', 'c_factor', 'friction_factor', 'reference'], key + '_materials', 'Materials')
            if any(not r.get('id') for r in material_rows):
                raise ValueError('Enter an ID for every material')
            if len({r.get('id') for r in material_rows}) != len(material_rows):
                raise ValueError('Material IDs must be unique')
            edited['materials'] = {r['id']: {k: v for k, v in r.items() if k != 'id'} for r in material_rows}
            for name in edited['materials']:
                sizes = model.get('catalogues', {}).get(name, [])
                edited['catalogues'][name] = edit_rows(sizes, ['size_id', 'nominal_mm', 'internal_mm', 'reference'],
                    key + '_catalogue_' + name, f'{name} sizes')
    else:
        st.caption('Vent arrangements and additional imported properties are preserved. Use JSON mode for advanced vent mappings.')
    return edited
