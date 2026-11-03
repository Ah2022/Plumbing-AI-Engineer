"""Actual signature verification, independent trust and data/document binding."""
from copy import deepcopy
import base64,datetime,hashlib,json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from engineering.source_authentication import canonical,checksum,source_payload,verify_attestation
from engineering.service import run_module
from tests.test_coupled_research import example


def signed():
    package=example('equipment_selection');private=Ed25519PrivateKey.generate();document=b'Fictional manufacturer data for signature tests only.'
    payload=source_payload(package,'SYN')
    manifest=dict(schema_version='source-attestation-1',key_id='TEST-KEY',issuer='Fictional source issuer',subject='Fictional test catalogue',
        data_sha256=checksum(payload),document_sha256=hashlib.sha256(document).hexdigest(),issued_on='2026-01-01',expires_on='2090-01-01',purpose='MANUFACTURER_DATA_RELEASE')
    item=dict(source_id='SYN',manifest=manifest,signature_base64=base64.b64encode(private.sign(canonical(manifest))).decode(),document_base64=base64.b64encode(document).decode())
    trust=dict(schema_version='source-trust-1',keys=[dict(key_id='TEST-KEY',issuer='Fictional source issuer',role='MANUFACTURER',
        public_key_base64=base64.b64encode(private.public_key().public_bytes_raw()).decode(),identity_evidence='Fictional out-of-band enrollment for test only',
        not_before='2020-01-01',not_after='2099-01-01',revoked=False)])
    return package,payload,item,trust


def test_real_detached_signature_and_document_integrity_are_verified():
    package,payload,item,trust=signed();r=verify_attestation(item,payload,trust,as_of=datetime.date(2026,11,3))
    assert r['status']=='SIGNATURE_AND_CONTENT_VERIFIED' and r['signer_role']=='MANUFACTURER'
    assert r['data_sha256']==checksum(payload)


@pytest.mark.parametrize('mutation',[
    lambda item,trust:item['manifest'].update(issuer='Impersonated vendor'),
    lambda item,trust:item['manifest'].update(subject='Altered after signing'),
    lambda item,trust:item.update(document_base64=base64.b64encode(b'Different source bytes').decode()),
    lambda item,trust:item.update(signature_base64=base64.b64encode(bytes(64)).decode()),
    lambda item,trust:trust['keys'][0].update(revoked=True),
    lambda item,trust:trust['keys'][0].update(key_id='UNTRUSTED'),
    lambda item,trust:item['manifest'].update(expires_on='2025-01-01'),
    lambda item,trust:item['manifest'].update(issued_on='2080-01-01'),
    lambda item,trust:trust['keys'][0].update(role='ENGINEERING_REVIEWER'),
])
def test_tamper_unknown_keys_revocation_expiry_and_wrong_roles_fail_closed(mutation):
    package,payload,item,trust=signed();mutation(item,trust)
    with pytest.raises(ValueError):verify_attestation(item,payload,trust,as_of=datetime.date(2026,11,3))


def test_changed_numerical_ratings_or_source_revision_invalidate_signature():
    package,payload,item,trust=signed();package['data']['catalogue'][0]['max_pressure_kpa']+=1
    with pytest.raises(ValueError,match='catalogue/source'):verify_attestation(item,source_payload(package,'SYN'),trust)
    package,payload,item,trust=signed();package['sources'][0]['revision']='changed'
    with pytest.raises(ValueError,match='catalogue/source'):verify_attestation(item,source_payload(package,'SYN'),trust)


def test_upload_cannot_enroll_its_own_trust_key(monkeypatch):
    package,payload,item,trust=signed();package['source_attestations']=[item]
    monkeypatch.delenv('PLUMBING_SOURCE_TRUST_STORE',raising=False)
    with pytest.raises(ValueError,match='server-owned'):run_module(package)


def test_verified_signature_keeps_source_role_and_engineering_acceptance_separate(tmp_path,monkeypatch):
    package,payload,item,trust=signed();package['source_attestations']=[item]
    path=tmp_path/'trust.json';path.write_text(json.dumps(trust));monkeypatch.setenv('PLUMBING_SOURCE_TRUST_STORE',str(path))
    r=run_module(package)
    assert r['source_authentication']['status']=='PROVIDED_ATTESTATIONS_VERIFIED'
    assert r['source_status']=='SYNTHETIC' and r['review_status']=='REVIEW_REQUIRED' and r['code_compliance_status']=='NOT_EVALUATED'
    # Lack of an attestation never becomes authenticated through a source-status assertion.
    package.pop('source_attestations');package['sources'][0].update(verification_status='REVIEWED_AS_REPORTED',reviewed_by='Claimed reviewer')
    r=run_module(package)
    assert r['source_authentication']['status']=='NOT_PROVIDED'


def test_claimed_trusted_key_in_uploaded_record_is_rejected():
    package,payload,item,trust=signed();item['public_key_base64']=trust['keys'][0]['public_key_base64']
    with pytest.raises(ValueError,match='Unsupported input fields'):verify_attestation(item,payload,trust)
