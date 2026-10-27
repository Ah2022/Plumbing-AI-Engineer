"""Build synthetic IFC/DXF intake examples; contains no licensed design tables."""
from pathlib import Path
from io import StringIO


def ifc_example():
    import ifcopenshell
    from ifcopenshell import guid
    f = ifcopenshell.file(schema='IFC4')
    def xyz(coords):
        return f.create_entity('IfcCartesianPoint', Coordinates=tuple(float(x) for x in coords))
    def axis(coords, rotated=False):
        return f.create_entity('IfcAxis2Placement3D', Location=xyz(coords),
            Axis=f.create_entity('IfcDirection', DirectionRatios=(0., 0., 1.)),
            RefDirection=f.create_entity('IfcDirection', DirectionRatios=(0., 1., 0.) if rotated else (1., 0., 0.)))
    context = f.create_entity('IfcGeometricRepresentationContext', ContextType='Model', CoordinateSpaceDimension=3,
        Precision=0.00001, WorldCoordinateSystem=axis((0, 0, 0)))
    assignment = f.create_entity('IfcUnitAssignment', Units=[f.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix='MILLI', Name='METRE')])
    f.create_entity('IfcProject', GlobalId=guid.compress('11111111111111111111111111111111'),
        Name='SYNTHETIC plumbing pilot — not a code-compliant design', RepresentationContexts=[context], UnitsInContext=assignment)
    parent = f.create_entity('IfcLocalPlacement', RelativePlacement=axis((10000, 20000, 3000), True))
    placement = f.create_entity('IfcLocalPlacement', PlacementRelTo=parent, RelativePlacement=axis((0, 0, 0)))
    def pipe(name, start, end, object_placement):
        polyline = f.create_entity('IfcPolyline', Points=[xyz(start), xyz(end)])
        shape = f.create_entity('IfcShapeRepresentation', ContextOfItems=context, RepresentationIdentifier='Axis',
            RepresentationType='Curve3D', Items=[polyline])
        return f.create_entity('IfcPipeSegment', GlobalId=guid.new(), Name=name, ObjectPlacement=object_placement,
            Representation=f.create_entity('IfcProductDefinitionShape', Representations=[shape]), PredefinedType='RIGIDSEGMENT')
    water = pipe('SYNTHETIC water pipe: rotated nested placement', (0, 0, 0), (1000, 0, 0), placement)
    drain = pipe('SYNTHETIC drain: centreline is not an invert', (0, 0, 0), (10000, 0, -200),
        f.create_entity('IfcLocalPlacement', RelativePlacement=axis((0, 0, 2000))))
    fixture = f.create_entity('IfcSanitaryTerminal', GlobalId=guid.new(), Name='SYNTHETIC fixture',
        ObjectPlacement=placement, PredefinedType='SINK')
    inlet = f.create_entity('IfcDistributionPort', GlobalId=guid.new(), Name='Inlet', FlowDirection='SINK')
    outlet = f.create_entity('IfcDistributionPort', GlobalId=guid.new(), Name='Outlet', FlowDirection='SOURCE')
    terminal_port = f.create_entity('IfcDistributionPort', GlobalId=guid.new(), Name='Fixture inlet', FlowDirection='SINK')
    f.create_entity('IfcRelNests', GlobalId=guid.new(), RelatingObject=water, RelatedObjects=[inlet, outlet])
    f.create_entity('IfcRelNests', GlobalId=guid.new(), RelatingObject=fixture, RelatedObjects=[terminal_port])
    f.create_entity('IfcRelConnectsPorts', GlobalId=guid.new(), RelatingPort=outlet, RelatedPort=terminal_port)
    group = f.create_entity('IfcDistributionSystem', GlobalId=guid.new(), Name='SYNTHETIC cold water', PredefinedType='DOMESTICCOLDWATER')
    f.create_entity('IfcRelAssignsToGroup', GlobalId=guid.new(), RelatedObjects=[water, fixture], RelatingGroup=group)
    prop = f.create_entity('IfcPropertySingleValue', Name='Evidence', NominalValue=f.create_entity('IfcText', 'SYNTHETIC inputs require mapping review'))
    pset = f.create_entity('IfcPropertySet', GlobalId=guid.new(), Name='Pset_PLM_Pilot', HasProperties=[prop])
    f.create_entity('IfcRelDefinesByProperties', GlobalId=guid.new(), RelatedObjects=[water, drain], RelatingPropertyDefinition=pset)
    return f.to_string().encode('utf-8')


def dxf_example():
    import ezdxf
    from ezdxf import units
    doc = ezdxf.new('R2010')
    doc.units = units.MM
    for name in ('PLM_WATER', 'PLM_DRAIN', 'ARCH_REFERENCE'):
        doc.layers.new(name)
    space = doc.modelspace()
    space.add_line((0, 0, 3000), (1000, 0, 3000), dxfattribs={'layer': 'PLM_WATER'})
    space.add_line((0, 1000, 2000), (10000, 1000, 1800), dxfattribs={'layer': 'PLM_DRAIN'})
    # An unconnected crossing and an arc deliberately exercise scope and unsupported geometry.
    space.add_line((500, -1000, 3000), (500, 1000, 3000), dxfattribs={'layer': 'ARCH_REFERENCE'})
    space.add_arc((0, 0), 1000, 0, 90, dxfattribs={'layer': 'PLM_WATER'})
    out = StringIO()
    doc.write(out)
    return out.getvalue().encode('utf-8')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / 'examples'
    (root / 'model_pilot.ifc').write_bytes(ifc_example())
    (root / 'model_pilot.dxf').write_bytes(dxf_example())
    print('Wrote synthetic model_pilot.ifc and model_pilot.dxf')
