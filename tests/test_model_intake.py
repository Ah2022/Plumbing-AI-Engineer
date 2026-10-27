"""Real IFC/DXF parser benchmarks using synthetic models and independent measurements."""
from copy import deepcopy
import math
import pytest
from bim.model_intake import inspect_model
from bim.model_review import initial_mapping, review_model
from database.design_table_api import DesignValue
from tools.generate_model_examples import ifc_example, dxf_example


@pytest.fixture
def ifc_inventory():
    pytest.importorskip('ifcopenshell')
    return inspect_model(ifc_example(), 'synthetic.ifc')


@pytest.fixture
def dxf_inventory():
    pytest.importorskip('ezdxf')
    return inspect_model(dxf_example(), 'synthetic.dxf')


def test_ifc_millimetres_nested_rotation_and_ports(ifc_inventory):
    inv = ifc_inventory
    assert inv['unit_evidence']['length_scale_to_m'] == .001
    water = next(o for o in inv['objects'] if 'rotated' in o['name'])
    assert water['length_m'] == pytest.approx(1)
    assert water['start_xyz_m'] == pytest.approx([10, 20, 3])
    assert water['end_xyz_m'] == pytest.approx([10, 21, 3])
    assert water['nominal_mm'] is None  # No geometric/internal/nominal diameter substitution.
    assert len(water['ports']) == 2 and len(inv['connections']) == 1
    assert water['properties']['Pset_PLM_Pilot']['Evidence'].startswith('SYNTHETIC')
    assert 'SYNTHETIC cold water' in water['system']


def test_dxf_units_crossings_and_ignored_geometry(dxf_inventory):
    inv = dxf_inventory
    assert inv['unit_evidence']['length_scale_to_m'] == pytest.approx(.001)
    assert len(inv['objects']) == 3 and inv['connections'] == []
    assert inv['ignored_entities']['ARC'] == 1
    drain = next(o for o in inv['objects'] if o['system'] == 'PLM_DRAIN')
    assert drain['horizontal_run_m'] == 10
    assert drain['length_m'] == pytest.approx(math.sqrt(100 + .04))
    assert not any(row['include'] for row in initial_mapping(inv))


def test_dxf_unitless_requires_override():
    ezdxf = pytest.importorskip('ezdxf')
    from io import StringIO
    doc = ezdxf.new(); doc.units = 0
    doc.modelspace().add_line((0, 0, 0), (12, 0, 0))
    out = StringIO(); doc.write(out); data = out.getvalue().encode()
    with pytest.raises(ValueError, match='no declared drawing units'):
        inspect_model(data, 'unitless.dxf')
    inv = inspect_model(data, 'unitless.dxf', dxf_unit='in')
    assert inv['objects'][0]['length_m'] == pytest.approx(.3048)
    assert inv['unit_evidence']['override'] == 'in'


def test_ifc_missing_units_and_axis_never_guess():
    ifcopenshell = pytest.importorskip('ifcopenshell')
    f = ifcopenshell.file.from_string(ifc_example().decode())
    f.by_type('IfcProject')[0].UnitsInContext = None
    with pytest.raises(ValueError, match='length units are missing'):
        inspect_model(f.to_string().encode(), 'bad.ifc')
    f = ifcopenshell.file.from_string(ifc_example().decode())
    for pipe in f.by_type('IfcPipeSegment'):
        pipe.Representation = None
    inv = inspect_model(f.to_string().encode(), 'no_axis.ifc')
    assert all(o['length_m'] is None for o in inv['objects'])


@pytest.mark.parametrize('filename,data', [('a.dwg', b'anything'), ('bad.ifc', b'garbage'), ('empty.dxf', b'')])
def test_invalid_files_are_actionable(filename, data):
    with pytest.raises(ValueError):
        inspect_model(data, filename)


def mapped_water(inv):
    rows = initial_mapping(inv)
    for row in rows:
        row.update(include=False, exclusion_reason='Synthetic scope excludes this object')
    rows[0].update(include=True, service='cold_water', internal_mm=25., design_flow_lps=1., input_reference='SYNTHETIC measured bore and assigned flow')
    return rows


def test_water_velocity_independent_identity_and_partial_scope(ifc_inventory):
    inv = ifc_inventory; rows = mapped_water(inv)
    result = review_model(None, 'IPC', inv, rows, reviewed=True, mapping_reference='SYNTHETIC reviewer',
                          velocity_limit_m_s=3, velocity_reference='SYNTHETIC criterion; not code')
    finding = next(f for f in result['findings'] if f['check_id'] == 'water_velocity')
    assert finding['actual'] == pytest.approx(.001 / (math.pi * .025**2 / 4))
    assert finding['status'] == 'PASS'
    assert result['technical_status'] == 'PARTIAL' and result['coverage_status'] == 'PARTIAL'
    assert result['review_status'] == 'REVIEW_REQUIRED'
    assert any(f['check_id'] == 'water_pressure_and_network' and f['status'] == 'NOT_EVALUATED' for f in result['findings'])
    fail = review_model(None, 'IPC', inv, rows, reviewed=True, mapping_reference='SYNTHETIC', velocity_limit_m_s=1, velocity_reference='SYNTHETIC')
    assert fail['failure_count'] == 1 and fail['technical_status'] == 'FAIL'


def test_nominal_diameter_does_not_substitute_for_bore(ifc_inventory):
    rows = mapped_water(ifc_inventory); rows[0].update(internal_mm=None, nominal_mm=25)
    result = review_model(None, 'IPC', ifc_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC', velocity_limit_m_s=3, velocity_reference='SYNTHETIC')
    assert next(f for f in result['findings'] if f['check_id'] == 'water_velocity')['status'] == 'MISSING_DATA'


def test_drainage_uses_reviewed_inverts_and_active_code(dxf_inventory, monkeypatch):
    import bim.model_review as module
    calls = []
    def limit(conn, code, nominal):
        calls.append((code, nominal))
        return DesignValue(2., '%', code, 'SYNTHETIC_TABLE', 'CONFIRMED', 'SYNTHETIC')
    monkeypatch.setattr(module, 'get_min_slope', limit)
    rows = initial_mapping(dxf_inventory)
    row = next(r for r in rows if r['source_id'] == next(o['source_id'] for o in dxf_inventory['objects'] if o['system'] == 'PLM_DRAIN'))
    row.update(include=True, service='drainage', nominal_mm=100, invert_start_m=4., invert_end_m=3.7,
               direction_confirmed=True, input_reference='SYNTHETIC independently reviewed inverts')
    result = review_model(None, 'TEST_CODE', dxf_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')
    slope = next(f for f in result['findings'] if f['check_id'] == 'drainage_slope')
    assert slope['actual'] == pytest.approx(3)  # Not the 2% centreline slope in the source.
    assert slope['status'] == 'PASS' and calls == [('TEST_CODE', 100)]
    assert any(f['check_id'] == 'invert_geometry_consistency' and f['status'] == 'WARNING' for f in result['findings'])
    row['invert_end_m'] = 4.1
    result = review_model(None, 'TEST_CODE', dxf_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')
    assert result['failure_count'] == 1
    row['direction_confirmed'] = False
    result = review_model(None, 'TEST_CODE', dxf_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')
    assert next(f for f in result['findings'] if f['check_id'] == 'drainage_slope')['status'] == 'MISSING_DATA'


def test_review_gate_and_foreign_mapping_ids(ifc_inventory):
    rows = initial_mapping(ifc_inventory)
    with pytest.raises(ValueError, match='Confirm the mapping'):
        review_model(None, 'IPC', ifc_inventory, rows, reviewed=False, mapping_reference='')
    rows[0]['source_id'] = 'foreign'
    with pytest.raises(ValueError, match='every source object'):
        review_model(None, 'IPC', ifc_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')


def test_nonfinite_mapping_rejected(ifc_inventory):
    for diameter in (float('nan'), 1e-300, 1e308):
        rows = mapped_water(ifc_inventory); rows[0]['internal_mm'] = diameter
        with pytest.raises(ValueError):
            review_model(None, 'IPC', ifc_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC', velocity_limit_m_s=3, velocity_reference='SYNTHETIC')


def test_missing_and_flagged_slope_data_remain_visible(dxf_inventory, monkeypatch):
    import bim.model_review as module
    rows = initial_mapping(dxf_inventory)
    rows[0].update(include=True, service='drainage', nominal_mm=50., invert_start_m=1., invert_end_m=.9,
                   direction_confirmed=True, input_reference='SYNTHETIC inverts')
    monkeypatch.setattr(module, 'get_min_slope', lambda *args: None)
    report = review_model(None, 'NO_DATA', dxf_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')
    assert next(f for f in report['findings'] if f['check_id'] == 'drainage_slope')['status'] == 'MISSING_DATA'
    monkeypatch.setattr(module, 'get_min_slope', lambda *args: DesignValue(2., '%', 'TEST', 'SYNTHETIC', 'FLAGGED', 'SYNTHETIC'))
    report = review_model(None, 'TEST', dxf_inventory, rows, reviewed=True, mapping_reference='SYNTHETIC')
    assert next(f for f in report['findings'] if f['check_id'] == 'drainage_slope')['status'] == 'WARNING'
    inv = deepcopy(dxf_inventory); inv['objects'][0]['axis_segment_count'] = 2
    report = review_model(None, 'TEST', inv, rows, reviewed=True, mapping_reference='SYNTHETIC')
    assert next(f for f in report['findings'] if f['check_id'] == 'drainage_slope')['status'] == 'UNSUPPORTED'
