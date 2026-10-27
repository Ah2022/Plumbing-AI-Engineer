"""DWG intake contracts and real PDF extraction/rendering; all source data is synthetic."""
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import pytest
from bim.model_intake import inspect_model
from bim.model_review import review_model
from tools.generate_model_examples import dxf_example
from tests.test_streamlit_app import fresh_app, _create_project


def pdf_bytes(pages=1, text=True):
    """Small in-memory PDF fixture with a line and optional searchable text."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        ('<< /Type /Pages /Count %d /Kids [%s] >>' % (pages, ' '.join(f'{3+i*3} 0 R' for i in range(pages)))).encode()]
    for i in range(pages):
        page = 3+i*3
        content = b'1 w 40 150 m 260 150 l S\n'
        if text:
            content += b'BT /F1 12 Tf 40 200 Td (SYNTHETIC plumbing drawing - DN100) Tj ET\n'
        objects += [f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 240] /Resources << /Font << /F1 {page+1} 0 R >> >> /Contents {page+2} 0 R >>'.encode(),
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'endstream']
    out = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start = len(out)
    out.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        out.extend(f'{offset:010} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(out)


def dwg_header():
    # Header-only contract fixture; deliberately not claimed to be a valid converted DWG.
    return b'AC1032' + b'\0'*122


def test_pdf_text_pages_and_bounded_preview():
    pytest.importorskip('pypdfium2')
    from bim.pdf_intake import preview_pdf
    from PIL import Image
    from io import BytesIO
    data = pdf_bytes(2)
    inv = inspect_model(data, 'drawing.PDF')
    assert inv['format'] == 'PDF' and len(inv['objects']) == 2
    assert 'DN100' in inv['objects'][0]['text']
    assert inv['unit_evidence']['length_scale_to_m'] is None and not inv['geometry_ready']
    assert inv['source_sha256'] == sha256(data).hexdigest()
    image = Image.open(BytesIO(preview_pdf(data, 0)))
    assert image.size == (600, 480)
    assert max(image.size) <= 1400
    assert image.convert('L').getextrema()[0] < 50
    with pytest.raises(ValueError, match='no mapped plumbing geometry'):
        review_model(None, 'IPC', inv, [], mapping_reference='SYNTHETIC', reviewed=True)
    with pytest.raises(ValueError, match='Unknown PDF page'):
        preview_pdf(data, 2)


def test_pdf_empty_text_and_limits():
    pytest.importorskip('pypdfium2')
    inv = inspect_model(pdf_bytes(text=False), 'scan.pdf')
    assert inv['objects'][0]['text_status'] == 'NO_TEXT_OR_SCAN'
    with pytest.raises(ValueError, match='1–50 pages'):
        inspect_model(pdf_bytes(51), 'large.pdf')
    with pytest.raises(ValueError, match='PDF header'):
        inspect_model(b'not pdf', 'wrong.pdf')


def test_dwg_without_converter_is_accepted_but_not_evaluated(monkeypatch):
    monkeypatch.setattr('bim.dwg_intake.converter_path', lambda: None)
    inv = inspect_model(dwg_header(), 'drawing.dwg')
    assert inv['format'] == 'DWG' and inv['schema'] == 'AC1032'
    assert inv['content_validation'] == 'HEADER_ONLY'
    assert not inv['geometry_ready'] and inv['intake_status'] == 'CONVERSION_REQUIRED'
    with pytest.raises(ValueError, match='no mapped plumbing geometry'):
        review_model(None, 'IPC', inv, [], mapping_reference='SYNTHETIC', reviewed=True)


def test_dwg_companion_requires_review_and_preserves_both_hashes():
    pytest.importorskip('ezdxf')
    drawing, dxf = dwg_header(), dxf_example()
    with pytest.raises(ValueError, match='Confirm that the companion'):
        inspect_model(drawing, 'drawing.dwg', dwg_dxf_data=dxf)
    inv = inspect_model(drawing, 'drawing.dwg', dwg_dxf_data=dxf, dwg_pair_confirmed=True)
    assert inv['geometry_ready'] and len(inv['objects']) == 3
    assert inv['source_sha256'] == sha256(drawing).hexdigest()
    assert inv['conversion']['dxf_sha256'] == sha256(dxf).hexdigest()
    assert inv['conversion']['correspondence'] == 'USER_CONFIRMED'
    assert inv['unit_evidence']['length_scale_to_m'] == pytest.approx(.001)


def test_local_conversion_contract_and_timeout(monkeypatch):
    pytest.importorskip('ezdxf')
    import bim.dwg_intake as module
    dxf = dxf_example()
    def run(arguments, **options):
        assert options['shell'] is False and options['timeout'] == 60
        assert arguments[3:] == ['ACAD2018', 'DXF', '0', '1', 'model.dwg']
        assert (Path(arguments[1])/'model.dwg').read_bytes() == dwg_header()
        (Path(arguments[2])/'model.dxf').write_bytes(dxf)
        return subprocess.CompletedProcess(arguments, 0)
    monkeypatch.setattr(module, 'converter_path', lambda: 'installed-converter')
    monkeypatch.setattr(module.subprocess, 'run', run)
    inv = inspect_model(dwg_header(), 'drawing.dwg')
    assert inv['conversion']['method'] == 'LOCAL_ODA_CONVERSION'
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('converter', 60)
    monkeypatch.setattr(module.subprocess, 'run', timeout)
    inv = inspect_model(dwg_header(), 'drawing.dwg')
    assert not inv['geometry_ready'] and '60 seconds' in inv['conversion_error']


def open_drawing(at, inventory, data=None):
    at = _create_project(at)
    at.sidebar.radio[0].set_value('CAD / IFC Checks').run(timeout=30)
    key = next(key.removesuffix('_upload') for key in at.session_state if key.startswith('model_intake_') and key.endswith('_upload'))
    at.session_state[key] = inventory
    at.session_state[key+'_pdf_bytes'] = data
    at.run(timeout=30)
    assert not at.exception
    return at


def test_pdf_ui_preview_and_review_note_never_certify(fresh_app, monkeypatch):
    pytest.importorskip('pypdfium2')
    data = pdf_bytes()
    at = open_drawing(fresh_app, inspect_model(data, 'drawing.pdf'), data)
    assert at.get('imgs') or at.get('image')
    assert not any(b.label == 'Run and save model checks' for b in at.button)
    import compliance.governance as governance
    original = governance.context
    monkeypatch.setattr(governance, 'context', lambda *args: dict(original(*args), review_status='VERIFIED'))
    next(t for t in at.text_area if t.label == 'Drawing review note').set_value('SYNTHETIC: confirm pipe sizes against schedule')
    next(t for t in at.text_input if t.label == 'Drawing reviewer / evidence reference').set_value('SYNTHETIC reviewer')
    next(b for b in at.button if b.label == 'Save drawing review note').click().run(timeout=30)
    assert not at.exception and not at.error
    row = at.session_state['conn'].execute("SELECT * FROM calculations WHERE calc_type='model_document_review'").fetchone()
    assert row['status'] == 'WARNING' and row['review_status'] == 'REVIEW_REQUIRED'
    assert json.loads(row['intermediate_json'])['coverage_status'] == 'NOT_EVALUATED'


def test_dwg_pending_ui_is_actionable(fresh_app, monkeypatch):
    monkeypatch.setattr('bim.dwg_intake.converter_path', lambda: None)
    at = open_drawing(fresh_app, inspect_model(dwg_header(), 'drawing.dwg'))
    assert any('DWG conversion required' == h.value for h in at.subheader)
    assert any('Attach a DXF' in w.value for w in at.warning)
    assert not any(b.label == 'Run and save model checks' for b in at.button)
    upload = at.get('file_uploader')[0]
    assert {'.ifc', '.dxf', '.dwg', '.pdf'} <= set(upload.proto.type)
    assert upload.proto.max_upload_size_mb == 20
