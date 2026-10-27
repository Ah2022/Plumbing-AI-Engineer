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
    with st.form(key + '_add'):
        selected = st.selectbox('Fixture', range(len(choices)),
            format_func=lambda index: choices[index]['label'], key=key + '_choice')
        quantity = st.number_input('Fixture quantity', min_value=1, value=1, step=1, key=key + '_quantity')
        if st.form_submit_button('Add fixture', key=key + '_submit'):
            choice = dict(choices[selected])
            choice['unit_value'] = choice.get('unit_value', choice.get('wsfu_value'))
            choice['quantity'] = quantity
            choice['subtotal'] = quantity * choice['unit_value']
            st.session_state.setdefault(key, []).append(choice)
    rows = st.session_state.get(key, [])
    if rows:
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
