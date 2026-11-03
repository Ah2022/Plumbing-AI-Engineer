"""Select/arrange nodes and edit explicit connections without manipulating JSON."""
from copy import deepcopy

import streamlit as st
from app.model_viewer import _component, network_payload, apply_network_event
from app.workspace import evidence_field


def graphical_network(model, key, draft_key, scope, water):
    edited = deepcopy(model)
    payload = network_payload(edited)
    selected_key = 'network_graph_selection_' + scope
    ids = [n['id'] for n in edited['nodes']] + [p['id'] for p in edited['pipes']]
    if st.session_state.get(selected_key) not in ids:
        st.session_state[selected_key] = ids[0]
    payload['selected'] = st.session_state[selected_key]
    st.caption('Schematic editor: drag nodes, select a node or pipe, then edit its properties or connect nodes below. '
               'Layout positions are visual only; lengths, elevations, bores and criteria remain explicit engineering inputs.')
    def handle_event():
        event = st.session_state[key + '_canvas'].event
        current = st.session_state.get(draft_key, model)
        if event and event.get('id') in ids:
            try:
                st.session_state[draft_key] = apply_network_event(current, event)
                st.session_state[selected_key] = event['id']
            except ValueError:
                # A stale or malformed frontend event cannot replace the saved draft.
                return

    _component()(data=payload, key=key + '_canvas', on_event_change=handle_event)

    def commit(value):
        st.session_state[draft_key] = value
        st.session_state['network_editor_generation_' + scope] = st.session_state.get('network_editor_generation_' + scope, 0) + 1
        st.session_state.pop('network_result', None)
        st.rerun()

    selected = st.selectbox('Selected network object', ids, key=selected_key)
    node = next((n for n in edited['nodes'] if n['id'] == selected), None)
    pipe = next((p for p in edited['pipes'] if p['id'] == selected), None)
    task = st.segmented_control('Graph editing task', ['Inspect & edit', 'Add node', 'Connect nodes', 'Design criteria'],
                                default='Inspect & edit', key=key + '_task')
    if task == 'Inspect & edit':
        original = node or pipe
        with st.form(key + '_properties_' + selected):
            st.markdown('**' + ('Node ' if node else 'Pipe ') + selected + '**')
            fields = ['elevation_m', 'design_flow_lps', 'water_wsfu', 'required_residual_head_m'] if node and water else (
                ['elevation_m', 'drainage_dfu'] if node else ['length_m', 'minimum_nominal_mm', 'fittings_k', 'equipment_loss_m'] if water else
                ['length_m', 'horizontal_run_m', 'nominal_mm', 'minimum_slope_pct'])
            updates = {}
            labels = dict(elevation_m='Elevation (m)', design_flow_lps='Design flow (L/s)', water_wsfu='Water demand (WSFU)',
                required_residual_head_m='Required residual head (m)', drainage_dfu='Drainage demand (DFU)',
                length_m='Measured length (m)', minimum_nominal_mm='Minimum nominal size (mm)', fittings_k='Fitting loss coefficient K',
                equipment_loss_m='Equipment loss (m)', horizontal_run_m='Horizontal run (m)', nominal_mm='Nominal diameter (mm)', minimum_slope_pct='Minimum slope (%)')
            for field in fields:
                updates[field] = st.number_input(labels[field], value=float(original[field]) if original.get(field) is not None else None,
                    min_value=None if field == 'elevation_m' else 0., help='Explicit engineering input. Empty means missing; schematic positions never supply this value.')
            if pipe and water and edited.get('materials'):
                material = st.selectbox('Pipe material', list(edited['materials']), index=list(edited['materials']).index(pipe['material']) if pipe.get('material') in edited['materials'] else 0)
                # Size choices depend on material; apply a material change first, then select its size.
                updates['material'] = material
                if material == pipe.get('material'):
                    sizes = [s['size_id'] for s in edited.get('catalogues', {}).get(material, [])]
                    updates['selected_size_id'] = st.selectbox('Catalogue size', [None]+sizes, index=([None]+sizes).index(pipe.get('selected_size_id')) if pipe.get('selected_size_id') in sizes else 0,
                        help='Review actual internal bores and source references in Editable tables → Materials and manufacturer size catalogues.')
                else:
                    updates['selected_size_id'] = None
            ref_field = 'demand_reference' if node else 'minimum_size_reference'
            updates[ref_field] = evidence_field('Object evidence reference', key + '_object_ref_' + selected, original.get(ref_field, ''))
            if st.form_submit_button('Apply object changes', type='primary'):
                for field, value in updates.items():
                    if value is None:
                        original.pop(field, None)
                    else:
                        original[field] = value
                commit(edited)
        if pipe and st.button('Remove selected pipe', key=key + '_remove'):
            edited['pipes'] = [p for p in edited['pipes'] if p['id'] != selected]
            commit(edited)
    elif task == 'Add node':
        with st.form(key + '_add'):
            identity = st.text_input('New node ID', max_chars=120)
            kind = st.selectbox('Node type', ['junction', 'fixture', 'source' if water else 'outlet'])
            elevation = st.number_input('New node elevation (m)', value=None)
            if st.form_submit_button('Add node', type='primary'):
                if not identity.strip() or identity.strip() in ids:
                    st.error('Enter a unique, nonempty node ID.')
                elif len(edited['nodes']) >= 500:
                    st.error('The schematic editor supports up to 500 nodes. Split the network into reviewed systems.')
                else:
                    edited['nodes'].append(dict(id=identity.strip(), kind=kind, elevation_m=elevation))
                    commit(edited)
    elif task == 'Connect nodes':
        with st.form(key + '_connect'):
            identity = st.text_input('New pipe ID', max_chars=120)
            node_ids = [n['id'] for n in edited['nodes']]
            start = st.selectbox('From node', node_ids)
            end = st.selectbox('To node', node_ids, index=min(1, len(node_ids)-1))
            length = st.number_input('Measured pipe length (m)', min_value=.001, value=1.)
            st.caption('Water direction is source → fixture; drainage direction is fixture → outlet. Complete catalogue, capacity and slope criteria after adding the connection.')
            if st.form_submit_button('Connect nodes', type='primary'):
                if not identity.strip() or identity.strip() in ids or start == end:
                    st.error('Enter a unique pipe ID and two different nodes.')
                elif len(edited['pipes']) >= 500:
                    st.error('The schematic editor supports up to 500 pipes.')
                else:
                    edited['pipes'].append(dict(id=identity.strip(), from_node=start, to_node=end, length_m=length))
                    commit(edited)
    elif task == 'Design criteria':
        with st.form(key + '_criteria'):
            node_ids = [n['id'] for n in edited['nodes']]
            root = st.selectbox('Source / outlet node', node_ids, index=node_ids.index(edited['root']) if edited.get('root') in node_ids else 0)
            basis = evidence_field('Network design-basis reference', key + '_criteria_ref', edited.get('basis_reference', ''))
            head, velocity = edited.get('available_head_m'), edited.get('velocity_limit_m_s')
            if water:
                head = st.number_input('Available source head (m)', min_value=0., value=float(head) if head is not None else None)
                velocity = st.number_input('Velocity criterion (m/s)', min_value=0., value=float(velocity) if velocity is not None else None)
                velocity_ref = evidence_field('Velocity criterion reference', key + '_velocity_ref', edited.get('velocity_reference', ''))
            if st.form_submit_button('Apply network criteria', type='primary'):
                edited.update(root=root, basis_reference=basis)
                if water:
                    edited.update(available_head_m=head, velocity_limit_m_s=velocity, velocity_reference=velocity_ref)
                commit(edited)
    return edited
