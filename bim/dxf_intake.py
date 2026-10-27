"""Explicit DXF modelspace linework intake; no block explosion or crossing joins."""
from collections import Counter
from math import dist, hypot
from pathlib import Path
from tempfile import TemporaryDirectory


def read_dxf(data, unit_override=None):
    try:
        import ezdxf
        from ezdxf import units
    except ImportError as error:
        raise ValueError('DXF parser unavailable. Install requirements-models.txt and restart the app.') from error
    with TemporaryDirectory(prefix='plumbing-dxf-') as folder:
        path = Path(folder) / 'model.dxf'
        path.write_bytes(data)
        try:
            doc = ezdxf.readfile(path)
        except (ezdxf.DXFError, OSError, UnicodeError, ValueError) as error:
            raise ValueError('Unable to parse DXF: ' + str(error)) from error
    declared = int(doc.header.get('$INSUNITS', 0))
    overrides = {'mm': units.MM, 'm': units.M, 'ft': units.FT, 'in': units.IN}
    if unit_override is not None and unit_override not in overrides:
        raise ValueError('DXF unit override must be mm, m, ft or in')
    actual = overrides[unit_override] if unit_override else declared
    if not actual:
        raise ValueError('DXF has no declared drawing units. Select an explicit unit override and re-import.')
    try:
        scale = units.conversion_factor(actual, units.M)
    except (ValueError, TypeError) as error:
        raise ValueError('Unsupported DXF drawing units') from error
    objects, ignored = [], Counter()
    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind not in ('LINE', 'LWPOLYLINE', 'POLYLINE'):
            ignored[kind] += 1
            continue
        row = dict(source_id=entity.dxf.handle, source_class=kind, kind='pipe_candidate',
                   name=entity.dxf.layer, system=entity.dxf.layer, length_m=None, nominal_mm=None,
                   start_xyz_m=None, end_xyz_m=None, geometry_status='UNSUPPORTED', properties={})
        points = None
        if kind == 'LINE':
            points = [entity.dxf.start, entity.dxf.end]
        elif kind == 'LWPOLYLINE' and not entity.closed and not entity.has_arc:
            points = list(entity.vertices_in_wcs())
        elif kind == 'POLYLINE' and entity.is_3d_polyline and not entity.is_closed:
            points = list(entity.points())
        if points and len(points) >= 2:
            points = [[float(v) * scale for v in p] for p in points]
            row.update(length_m=sum(dist(a, b) for a, b in zip(points, points[1:])),
                       horizontal_run_m=sum(hypot(a[0]-b[0], a[1]-b[1]) for a, b in zip(points, points[1:])),
                       axis_segment_count=len(points)-1,
                       start_xyz_m=points[0], end_xyz_m=points[-1], geometry_status='EXTRACTED',
                       length_reference='DXF modelspace centreline vertices, WCS; drawing-unit conversion')
        else:
            row['geometry_note'] = 'Closed, curved, mesh or unsupported polyline; length not approximated.'
        objects.append(row)
        if len(objects) > 500:
            raise ValueError('Pilot limit is 500 objects. Partition the model; no elements were silently truncated.')
    return dict(format='DXF', schema=doc.dxfversion, model_id=doc.header.get('$FINGERPRINTGUID') or None,
        unit_evidence=dict(declared_insunits=declared, override=unit_override, length_scale_to_m=scale),
        objects=objects, connections=[], ignored_entities=dict(ignored), limitations=[
            'Linework is only a pipe candidate until its layer/identity is reviewed.',
            'Crossings and touching endpoints are not connected automatically.',
            'INSERT blocks, xrefs, paperspace, curved and closed polylines are not evaluated.',
            'Centreline Z is not a drainage invert; pipe diameter, loads and service require mapping.'])
