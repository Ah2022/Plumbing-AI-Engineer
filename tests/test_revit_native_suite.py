"""Opt-in inspection of actual native evidence; no record means skipped, never passed."""
import json
import os
from pathlib import Path
import pytest
from bim.revit_handoff import checksum, TEXT_FIELDS, NUMBER_FIELDS, FLAG_FIELDS
from bim.round_trip import verify_round_trip
from bim.revit_bindings import shared_parameter_guids


def test_native_acceptance_suite():
    location=os.environ.get('PLUMBING_REAL_REVIT_SUITE')
    if not location:pytest.skip('Native suite pending: set PLUMBING_REAL_REVIT_SUITE to suite.json')
    path=Path(location)
    read=lambda name:json.loads((path.parent/name).read_text(encoding='utf-8-sig'))
    suite=read(path.name)
    assert suite['schema_version']=='revit-evidence-suite-1'
    assert suite['execution_environment']=='REVIT_API' and suite['revit_version'].isdigit()
    assert suite['status']=='PASS'
    cases={r['name']:r for r in suite['cases']}
    required={'host_partitioned_extraction','large_model_partitioned_extraction','loaded_link_extraction_and_instance_identity',
              'workshared_native_ownership','shared_guid_instance_category_bindings',
              'native_dry_run_write_and_rollback_fresh_read','native_committed_write_and_fresh_comparison',
              'changed_geometry','deleted_element','replacement_identity','duplicate_identity',
              'rollback_restoration_and_saved_test_copy'}
    assert required<=cases.keys()
    assert all(cases[k]['status']=='PASS' and cases[k]['seconds']>=0 for k in required)
    bindings=cases['shared_guid_instance_category_bindings']['detail']
    manifest=shared_parameter_guids()
    result_names=set(TEXT_FIELDS)|set(NUMBER_FIELDS)|set(FLAG_FIELDS)
    assert {r['name']:r['guid'].lower() for r in bindings}=={name:manifest[name] for name in result_names}
    assert all(not r['read_only'] for r in bindings)
    links=cases['loaded_link_extraction_and_instance_identity']['detail']['links']
    loaded=[r for r in links if r['loaded'] and r.get('extracted',0)]
    assert loaded
    instance_keys=[]
    for row in loaded:
        payload=read('link-{}.json'.format(row['instance_id']))
        assert len(payload['inventory']['objects'])==row['extracted']
        expected=[row['instance_uid']+'|'+payload['revit_model_id']+'|'+obj['source_id']
                  for obj in payload['inventory']['objects']]
        assert row['instance_object_keys']==expected
        instance_keys.extend(expected)
    assert len(set(instance_keys))==len(instance_keys)
    if 'controlled_link_fixture' in cases:
        fixture=cases['controlled_link_fixture']
        assert fixture['status']=='PASS'
        pair=[r for r in loaded if r['instance_uid'] in fixture['detail']['instance_uids']]
        assert len(pair)==2 and pair[0]['model_identity']==pair[1]['model_identity']
        assert pair[0]['transform_feet']!=pair[1]['transform_feet']
        assert abs(pair[0]['transform_feet'][3][0]-pair[1]['transform_feet'][3][0])==20
    dry=read('dry-run.json')
    assert dry['write']['status']=='DRY_RUN_ROLLED_BACK'
    assert dry['write']['tested_elements']>0 and dry['write']['written']==0
    assert dry['before']['inventory']==dry['after']['inventory']
    committed=read('committed.json')
    assert committed['write']['status']=='COMMITTED'
    assert verify_round_trip(committed['before'],committed['after'],committed['handoff'])['status']=='PASS'
    assert verify_round_trip(committed['before'],read('after-adversarial-tests.json'),committed['handoff'])['status']=='PASS'
    benchmark=cases['large_model_partitioned_extraction']['detail']
    assert benchmark['candidate_elements']>10000
    count=0
    identities=set()
    for partition in benchmark['partitions']:
        payload=read(partition['file'])
        assert checksum(payload)==partition['sha256']
        assert partition['seconds']>0 and partition['selected']<=5000
        for obj in payload['inventory']['objects']:
            assert obj['source_id'] not in identities
            identities.add(obj['source_id'])
        count+=len(payload['inventory']['objects'])
    assert count==benchmark['extracted_objects'] and count>10000
