"""IFC semantic/axis extraction without tessellation, external references or guesses."""
from math import dist, hypot, isfinite


def property_evidence(value):
    """Keep opaque IFC property values readable without treating them as numeric inputs."""
    if isinstance(value, dict):
        return {str(k): property_evidence(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [property_evidence(v) for v in value]
    if isinstance(value, float) and not isfinite(value):
        return {'invalid_source_number': str(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def read_ifc(data):
    try:
        import ifcopenshell
        from ifcopenshell.util import element, placement, system, unit
        import numpy as np
    except ImportError as error:
        raise ValueError('IFC parser unavailable. Install requirements-models.txt and restart the app.') from error
    try:
        text = data.decode('utf-8-sig').lstrip()
        if not text.startswith('ISO-10303-21;') or 'END-ISO-10303-21;' not in text:
            raise ValueError('IFC STEP header or terminator is missing')
        model = ifcopenshell.file.from_string(text)
    except (ifcopenshell.Error, RuntimeError, ValueError, UnicodeError, OSError) as error:
        raise ValueError('Unable to parse IFC STEP file: ' + str(error)) from error
    assignment = unit.get_unit_assignment(model)
    if assignment is None or not any(getattr(u, 'UnitType', None) == 'LENGTHUNIT' for u in assignment.Units):
        raise ValueError('IFC project length units are missing; no SI default is assumed.')
    if sum(getattr(u, 'UnitType', None) == 'LENGTHUNIT' for u in assignment.Units) != 1:
        raise ValueError('Ambiguous IFC project length units; repair the unit assignment.')
    scale = unit.calculate_unit_scale(model)
    objects, connections = [], []
    ignored = 0
    for obj in model.by_type('IfcDistributionElement'):
        typed = element.get_type(obj)
        classification = obj.is_a() + ' ' + (typed.is_a() if typed else '')
        kind = next((name for token, name in [('PipeSegment', 'pipe'), ('PipeFitting', 'fitting'),
            ('SanitaryTerminal', 'fixture'), ('Pump', 'pump'), ('Tank', 'tank'), ('Valve', 'valve')]
            if token in classification), None)
        if kind is None:
            ignored += 1
            continue
        row = dict(source_id=obj.GlobalId, source_class=obj.is_a(), kind=kind,
            name=obj.Name or '', system='; '.join(s.Name or s.GlobalId for s in system.get_element_systems(obj)),
            length_m=None, nominal_mm=None, start_xyz_m=None, end_xyz_m=None,
            geometry_status='MISSING_DATA', properties=property_evidence(element.get_psets(obj)), ports=[])
        # Only an explicit Axis/IfcPolyline gives a supported centreline. No chord of a curved body.
        try:
            if obj.ObjectPlacement is None or not obj.ObjectPlacement.is_a('IfcLocalPlacement'):
                raise ValueError('Missing or unsupported local placement')
            matrix = placement.get_local_placement(obj.ObjectPlacement)
            axes = [rep for rep in (obj.Representation.Representations if obj.Representation else [])
                    if rep.RepresentationIdentifier == 'Axis']
            if len(axes) == 1 and len(axes[0].Items) == 1 and axes[0].Items[0].is_a('IfcPolyline'):
                points = [list((matrix @ np.array([*p.Coordinates, *([0.] if len(p.Coordinates) == 2 else []), 1.]))[:3] * scale)
                          for p in axes[0].Items[0].Points]
                if len(points) >= 2:
                    row.update(length_m=sum(dist(a, b) for a, b in zip(points, points[1:])),
                        horizontal_run_m=sum(hypot(a[0]-b[0], a[1]-b[1]) for a, b in zip(points, points[1:])),
                        axis_segment_count=len(points)-1,
                        start_xyz_m=points[0], end_xyz_m=points[-1], geometry_status='EXTRACTED',
                        length_reference='IFC Axis/IfcPolyline, composed local placement; project length units')
        except (AttributeError, TypeError, ValueError, RuntimeError):
            row['geometry_note'] = 'Unsupported placement or axis; geometry requires review.'
        for port in system.get_ports(obj):
            row['ports'].append(dict(source_id=port.GlobalId, flow_direction=port.FlowDirection))
            for relation in list(port.ConnectedTo or ()) + list(port.ConnectedFrom or ()):
                connections.append(dict(from_port=relation.RelatingPort.GlobalId,
                    to_port=relation.RelatedPort.GlobalId, evidence='IfcRelConnectsPorts'))
        objects.append(row)
        if len(objects) > 500:
            raise ValueError('Pilot limit is 500 plumbing objects. Partition the model; no elements were silently truncated.')
    projects = model.by_type('IfcProject')
    if len(projects) != 1:
        raise ValueError('IFC intake requires exactly one IfcProject identity.')
    # Property-set values remain source facts, not accepted engineering inputs. Explicit mapping is required.
    return dict(format='IFC', schema=model.schema, model_id=projects[0].GlobalId,
        unit_evidence=dict(length_scale_to_m=scale, source='IfcProject.UnitsInContext'), objects=objects,
        connections=list({(r['from_port'], r['to_port']): r for r in connections}.values()),
        ignored_distribution_elements=ignored, limitations=[
            'Only explicit polyline Axis geometry is measured; swept bodies/mapped representations are unevaluated.',
            'Ports and declared flow directions are evidence only; no complete hydraulic topology is inferred.',
            'Property sets, nominal diameter, outside diameter and internal bore are distinct; engineering mapping is required.',
            'Centreline elevations do not establish drainage invert elevations.'])
