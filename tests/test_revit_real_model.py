"""Opt-in real Revit execution evidence; absent evidence is a skip, never a pass."""
import json
import os
from pathlib import Path
import pytest
from bim.round_trip import verify_round_trip


def test_real_revit_model_committed_round_trip():
    path=os.environ.get('PLUMBING_REAL_REVIT_RUN')
    if not path:pytest.skip('Real-model acceptance pending: provide native harness execution record via PLUMBING_REAL_REVIT_RUN')
    record=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    assert record['schema_version']=='revit-native-harness-1' and record['execution_environment']=='REVIT_API'
    assert record['revit_version'].isdigit() and record['write']['status']=='COMMITTED'
    assert record['before']['extractor_version']=='phase4a-1' and record['after']['extractor_version']=='phase4a-1'
    assert record['before']['pipes'] and record['before']['inventory']['objects']
    assert not record['before']['revit_model_id'].startswith('SYNTHETIC')
    assert verify_round_trip(record['before'],record['after'],record['handoff'])['status']=='PASS'
