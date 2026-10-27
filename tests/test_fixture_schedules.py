"""Synthetic schedule benchmarks; no private workbook data is required."""
import json
import pytest
import database.design_table_api as api
import calculations.hot_water as hw
from app.network_editor import parse_network, merge_rows
from tests.test_streamlit_app import fresh_app, _create_project


def cell(value):
    return (value, None, 'FLAGGED') if isinstance(value, (int, float)) else (None, value, 'FLAGGED')


def record(**values):
    return dict(_table_reference='SYNTHETIC benchmark', **{key: cell(value) for key, value in values.items()})


def test_fixture_units_keep_services_and_codes_separate(monkeypatch):
    rows = [record(fixture='Test tap', cold=2, hot=1, dfu_ipc=3, dfu_upc=99),
            record(fixture='Trap fixture', trap_in=2, private=8),
            record(fixture='Supply fixture', min_branch_in=1, private=4)]
    monkeypatch.setattr(api, 'get_table_records', lambda conn, code, domain, table: rows if domain == 'water' and code == 'IPC' else [])
    assert [r['wsfu_value'] for r in api.list_water_fixture_unit_choices(None, 'IPC', 'hot')] == [1]
    assert [r['wsfu_value'] for r in api.list_water_fixture_unit_choices(None, 'IPC')] == [2, 4]
    assert [r['unit_value'] for r in api.list_drainage_fixture_unit_choices(None, 'IPC')] == [3]
    assert api.list_drainage_fixture_unit_choices(None, 'SAUDI_SBC_701') == []
    assert api.list_water_fixture_unit_choices(None, 'UPC', 'hot') == []


def test_upc_trap_table_is_drainage_not_water(monkeypatch):
    rows = [record(fixture='Test fixture', trap_in=2, private=7, public=9)]
    monkeypatch.setattr(api, 'get_table_records', lambda conn, code, domain, table: rows if domain == 'water' else [])
    assert api.list_water_fixture_unit_choices(None, 'UPC') == []
    assert [r['unit_value'] for r in api.list_drainage_fixture_unit_choices(None, 'UPC')] == [7, 9]


def test_hot_demand_exact_match_and_saved_schedule(monkeypatch):
    monkeypatch.setattr(hw, 'get_table_records', lambda *args: [record(fixture='Test shower', gph=10)])
    result = hw.hot_water_demand(None, [{'fixture_name': 'Test shower', 'quantity': 3}], 'TEST')
    assert result.result_value == 7.5
    assert result.inputs['fixture_schedule'][0]['subtotal_gph'] == 30
    with pytest.raises(hw.MissingCodeDataError):
        hw.hot_water_demand(None, [{'fixture_name': 'shower', 'quantity': 3}], 'TEST')
    monkeypatch.setattr(hw, 'get_table_records', lambda *args: [record(fixture='Test shower', gph=10)] * 2)
    with pytest.raises(ValueError, match='Ambiguous'):
        hw.hot_water_demand(None, [{'fixture_name': 'Test shower', 'quantity': 1}], 'TEST')


def test_network_row_edits_preserve_nested_data_and_removal():
    original = [{'id': 'A', 'length_m': 2, 'advanced': {'losses': [1, 2]}}, {'id': 'B'}]
    edited = merge_rows(original, [{'id': 'A', 'length_m': 5, 'unused': None}])
    assert edited == [{'id': 'A', 'length_m': 5, 'advanced': {'losses': [1, 2]}}]
    assert merge_rows([{'size_id': 'S1', 'extra': {'x': 1}}], [{'size_id': 'S1', 'internal_mm': 20}])[0]['extra'] == {'x': 1}
    with pytest.raises(ValueError, match='active project'):
        parse_network(json.dumps(dict(code_id='OTHER', nodes=[], pipes=[])), 'IPC')
    with pytest.raises(ValueError, match='Non-finite'):
        parse_network('{"code_id":"IPC","nodes":[],"pipes":[],"head":NaN}', 'IPC')


def choice(value, unit):
    return dict(label=f'Synthetic fixture: {value} {unit}', fixture_name='Synthetic fixture',
        unit_value=value, wsfu_value=value, unit=unit, confidence='FLAGGED', table_reference='SYNTHETIC benchmark')


def test_drainage_fixture_list_totals_and_removal(fresh_app, monkeypatch):
    monkeypatch.setattr(api, 'list_drainage_fixture_unit_choices', lambda *args: [choice(3, 'DFU')])
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value('Drainage & Vent').run(timeout=30)
    next(n for n in at.number_input if n.label == 'Fixture quantity').set_value(4)
    next(b for b in at.button if b.label == 'Add fixture').click().run(timeout=30)
    assert not at.exception
    assert next(m for m in at.metric if m.label == 'Total DFU').value == '12'
    assert next(c for c in at.checkbox if c.label == 'Use fixture list for drainage sizing').value
    next(b for b in at.button if b.label == 'Remove fixture').click().run(timeout=30)
    assert next(m for m in at.metric if m.label == 'Total DFU').value == '0'


def test_hot_water_has_separate_wsfu_and_gph_lists(fresh_app, monkeypatch):
    monkeypatch.setattr(api, 'list_water_fixture_unit_choices', lambda *args, **kwargs: [choice(2, 'WSFU')])
    monkeypatch.setattr(api, 'list_hot_water_demand_choices', lambda *args: [choice(10, 'GPH')])
    at = _create_project(fresh_app)
    at.sidebar.radio[0].set_value('Hot Water').run(timeout=30)
    assert not at.exception
    add = [b for b in at.button if b.label == 'Add fixture']
    add[0].click().run(timeout=30)
    [b for b in at.button if b.label == 'Add fixture'][1].click().run(timeout=30)
    assert not at.exception
    assert next(m for m in at.metric if m.label == 'Total hot WSFU').value == '2'
    assert next(m for m in at.metric if m.label == 'Total GPH').value == '10'
