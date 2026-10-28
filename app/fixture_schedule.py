"""Referenced, project-scoped fixture schedules shared by design pages."""
import streamlit as st
from compliance.governance import get_basis


def fixture_schedule(conn, project_id, code_id, name, choices, unit):
    basis = get_basis(conn, project_id)
    key = f'fixture_schedule_{project_id}_{code_id}_{basis["revision"] if basis else 0}_{name}'
    st.subheader(f'{name} fixture list')
    if not choices:
        st.info(f'No {unit} fixture table is loaded for this basis. Enter a reviewed total where supported; no other code is substituted.')
        return [], 0.0
    if any(c.get('catalogue_revision') for c in choices):
        st.caption('IPC 2024 fixture-load candidates; engineering review pending. DFU is a probabilistic code load, not a hydraulic flow in L/s.')
        with st.expander('Full fixture load register and application conditions'):
            st.dataframe([{k:v for k,v in c.items() if k!='label'} for c in choices],width='stretch',alt='Edition-specific drainage fixture types, DFU, trap sizes, sources and unresolved conditions')
            st.download_button('Download drainage fixture register',__import__('json').dumps(choices,indent=2),file_name='ipc-2024-fixture-candidates.json',mime='application/json')
    with st.form(key + '_add'):
        selected = st.selectbox('Fixture', range(len(choices)),
            format_func=lambda index: choices[index]['label'], key=key + '_choice')
        quantity = st.number_input('Fixture quantity', min_value=1, value=1, step=1, key=key + '_quantity')
        indirect=any(c.get('unit_value') is None for c in choices)
        if indirect:
            assessed=st.number_input('Reviewed indirect-receptor DFU per fixture',min_value=0.,value=0.,key=key+'_assessed')
            evidence=st.text_input('Indirect-receptor load evidence (required when no fixed DFU is listed)',key=key+'_evidence')
            receives=st.checkbox('Selected floor drain receives indirect fixture discharges',key=key+'_receives')
        if st.form_submit_button('Add fixture', key=key + '_submit'):
            choice = dict(choices[selected])
            choice['unit_value'] = choice.get('unit_value', choice.get('wsfu_value'))
            if choice['unit_value'] is None or indirect and receives and choice.get('fixture_id')=='floor_drain':
                if not evidence.strip() or assessed<=0:
                    st.error('Resolve the receptor load from connected fixtures, applicable minimum and evidence before adding it.')
                    choice['unit_value']=None
                else:choice.update(unit_value=max(choice['unit_value'] or 0,assessed),load_evidence=evidence.strip())
            if choice['unit_value'] is not None:
                choice['quantity'] = quantity
                choice['subtotal'] = quantity * choice['unit_value']
                st.session_state.setdefault(key, []).append(choice)
    rows = st.session_state.get(key, [])
    if rows:
        if any('group' in r.get('fixture_id','') for r in rows) and len(rows)>1:
            st.warning('Group and individual fixtures are both listed. Confirm their physical identities to avoid counting group members twice.')
        st.dataframe([{k: v for k, v in row.items() if k not in ('label', 'wsfu_value')} for row in rows],
            width='stretch', alt=f'{name} quantities, unit loads, subtotals and source references')
        remove = st.selectbox('Fixture row to remove', range(len(rows)),
            format_func=lambda i: f'{i + 1}: {rows[i]["fixture_name"]}', key=key + '_remove_choice')
        if st.button('Remove fixture', key=key + '_remove'):
            rows.pop(remove)
            st.rerun()
        if st.button('Clear fixture list', key=key + '_clear'):
            st.session_state[key] = []
            st.rerun()
    total = sum(row['subtotal'] for row in rows)
    st.metric(f'Total {unit}', f'{total:g}')
    return rows, total
