"""Drawing-only review for PDF pages and DWG files awaiting geometry conversion."""
import hashlib
import json
import streamlit as st
from app.db_helpers import next_calc_id, save_calculation
from compliance.governance import context
from models import CalculationResult


@st.cache_data(max_entries=4, ttl=3600, show_spinner=False)
def page_preview(data, page_index):
    from bim.pdf_intake import preview_pdf
    return preview_pdf(data, page_index)


def drawing_review(conn, pid, inventory, source_bytes, key):
    if inventory['format'] == 'PDF':
        st.subheader('PDF drawing review')
        st.caption('Page preview and text extraction are available. Pipe topology, drawing scale and engineering inputs require separate mapping.')
        number = st.number_input('Drawing page', min_value=1, max_value=len(inventory['objects']), value=1,
                                 step=1, key=key + '_page')
        page = inventory['objects'][number - 1]
        if source_bytes:
            try:
                st.image(page_preview(source_bytes, number-1), width='stretch', alt=f'PDF drawing page {number}')
            except (ValueError, RuntimeError) as error:
                st.error('Page preview unavailable: ' + str(error))
        if page['text'].strip():
            with st.expander('Extracted page text', expanded=True):
                st.text(page['text'])
            if page['text_truncated']:
                st.warning('Text extraction reached its size limit; review the original page for the complete content.')
        else:
            st.warning('No readable text was extracted. This may be a scanned drawing; OCR or manual review is required.')
        st.caption(f"Page size: {page['page_width_pt']:g} × {page['page_height_pt']:g} PDF points. This is not the drawing's engineering scale.")
    else:
        st.subheader('DWG conversion required')
        st.warning('The DWG is accepted, but plumbing geometry is not yet available. Attach a DXF export from the same revision, confirm the pair, then inspect again. A configured local ODA converter is another option.')
        st.caption(f"Detected DWG signature: {inventory['schema']} ({inventory['dwg_version']}). Only the header has been inspected.")
        if inventory.get('conversion_error'):
            st.error(inventory['conversion_error'])
    st.download_button('Download drawing intake evidence', json.dumps(inventory, indent=2, allow_nan=False),
        file_name='drawing-intake.json', mime='application/json')
    with st.form(key + '_drawing_note'):
        note = st.text_area('Drawing review note')
        reference = st.text_input('Drawing reviewer / evidence reference')
        save = st.form_submit_button('Save drawing review note')
    if save:
        if not note.strip() or not reference.strip():
            st.error('Enter a drawing review note and reviewer/evidence reference.')
        else:
            report = dict(source_sha256=inventory['source_sha256'], filename=inventory['filename'],
                source_format=inventory['format'], note=note, evidence_reference=reference,
                technical_status='NOT_EVALUATED', coverage_status='NOT_EVALUATED', review_status='REVIEW_REQUIRED',
                governance=context(conn, pid), limitations=inventory['limitations'])
            result = CalculationResult(next_calc_id(conn, pid, 'model_document_review'), 'model_document_review',
                'Record drawing evidence and manual review; no automatic engineering calculation',
                dict(source=inventory, reviewed_page=number if inventory['format'] == 'PDF' else None),
                report, None, None, status='WARNING', reference=reference, notes=note)
            save_calculation(conn, pid, result, target_type='model_document',
                target_id=hashlib.sha256(inventory['filename'].encode()).hexdigest())
            st.session_state[key + '_drawing_report'] = dict(report, calc_id=result.calc_id)
            st.success('Drawing review note saved. Engineering checks remain unevaluated.')
    report = st.session_state.get(key + '_drawing_report')
    if report:
        st.download_button('Download drawing review note', json.dumps(report, indent=2, allow_nan=False),
            file_name='drawing-review.json', mime='application/json')
