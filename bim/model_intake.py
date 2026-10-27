"""Read-only local IFC/DXF intake. No geometric proximity becomes connectivity."""
from hashlib import sha256
from pathlib import Path
from calculations.validation import finite

MAX_BYTES = 20 * 1024 * 1024
MAX_OBJECTS = 500
ADAPTER_REVISION = 2


def inspect_model(data: bytes, filename: str, *, dxf_unit=None, dwg_dxf_data=None, dwg_pair_confirmed=False):
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise ValueError('Supply a nonempty IFC, DXF, DWG or PDF file up to 20 MB; partition larger models explicitly.')
    extension = Path(filename).suffix.lower()
    if extension == '.ifc':
        from bim.ifc_intake import read_ifc
        result = read_ifc(data)
    elif extension == '.dxf':
        from bim.dxf_intake import read_dxf
        result = read_dxf(data, dxf_unit)
    elif extension == '.dwg':
        from bim.dwg_intake import read_dwg
        result = read_dwg(data, companion_dxf=dwg_dxf_data, pair_confirmed=dwg_pair_confirmed, dxf_unit=dxf_unit)
    elif extension == '.pdf':
        from bim.pdf_intake import read_pdf
        result = read_pdf(data)
    else:
        raise ValueError('Supported formats: .ifc, .dxf, .dwg and .pdf.')
    result.setdefault('geometry_ready', True)
    if not result['objects'] and result['geometry_ready']:
        raise ValueError('No supported plumbing objects found. DXF requires explicit layer selection after import; IFC requires pipe/fixture types.')
    if len(result['objects']) > MAX_OBJECTS:
        raise ValueError('Pilot limit is 500 objects. Partition the model; no elements were silently truncated.')
    ids = [row['source_id'] for row in result['objects']]
    if any(not isinstance(identity, str) or not identity.strip() for identity in ids):
        raise ValueError('Every source object needs a nonempty stable ID.')
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate source object IDs; repair the source model before mapping.')
    if result['geometry_ready']:
        finite('source length scale', result['unit_evidence']['length_scale_to_m'], positive=True)
    for row in result['objects']:
        for key in ('length_m', 'nominal_mm'):
            if row.get(key) is not None:
                finite(key, row[key], positive=True)
        for key in ('start_xyz_m', 'end_xyz_m'):
            for value in row.get(key) or []:
                finite(key, value)
    result.update(source_sha256=sha256(data).hexdigest(), filename=Path(filename).name,
                  adapter_revision=ADAPTER_REVISION, review_status='REVIEW_REQUIRED')
    return result
