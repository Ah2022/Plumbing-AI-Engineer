"""Connectivity rendering must use the current mapping and never invent endpoints."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from app.network_preview import network_dot

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['water_network.json', 'drainage_network.json'])
def test_schematic_matches_all_mapped_connections(name):
    model = json.loads((ROOT/'examples'/name).read_text(encoding='utf-8'))
    dot = network_dot(model)
    ids = {n['id']: f'n{i}' for i, n in enumerate(model['nodes'])}
    for pipe in model['pipes']:
        assert f"{ids[pipe['from_node']]} -> {ids[pipe['to_node']]}" in dot
    assert dot.count(' -> ') == len(model['pipes'])
    assert 'doubleoctagon' in dot and ' m' in dot
    dark = network_dot(model, dark=True)
    assert 'bgcolor="#111827"' in dark and 'fontcolor="#e5edf9"' in dark


def test_missing_and_duplicate_nodes_never_become_implicit_nodes():
    model = json.loads((ROOT/'examples/water_network.json').read_text(encoding='utf-8'))
    bad = deepcopy(model); bad['pipes'][0]['to_node'] = 'not mapped'
    with pytest.raises(ValueError, match='unknown node'):
        network_dot(bad)
    bad = deepcopy(model); bad['nodes'][1]['id'] = bad['nodes'][0]['id']
    with pytest.raises(ValueError, match='Duplicate preview node'):
        network_dot(bad)


def test_source_ids_are_escaped_labels_not_graph_statements():
    identity = 'A"; URL="https://example.invalid/'
    model = dict(schema_version='1.0', units='SI', root=identity,
                 nodes=[dict(id=identity, kind='source'), dict(id='B', kind='fixture')],
                 pipes=[dict(id='P1', from_node=identity, to_node='B')])
    dot = network_dot(model)
    assert 'n0 -> n1' in dot
    assert 'label=' + json.dumps(identity+'\nsource') in dot
    assert 'URL="https://' not in dot


def test_nonfinite_values_and_oversized_drafts_are_actionable():
    model = json.loads((ROOT/'examples/water_network.json').read_text(encoding='utf-8'))
    model['nodes'][0]['elevation_m'] = float('inf')
    with pytest.raises(ValueError, match='finite'):
        network_dot(model)
    model['nodes'] = [dict(id=str(i)) for i in range(501)]
    with pytest.raises(ValueError, match='500 nodes'):
        network_dot(model)
