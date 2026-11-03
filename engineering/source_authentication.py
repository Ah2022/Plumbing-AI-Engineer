"""Detached Ed25519 source attestations anchored in a server-owned trust store.

Uploaded packages cannot supply or enroll trusted public keys. A valid signature
proves possession of a configured key, not product fitness or a medical licence.
No network fetching, private-key handling or arbitrary file paths are accepted.
"""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
from engineering.common import fields,text,flag


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def checksum(value):return hashlib.sha256(canonical(value)).hexdigest()


def source_payload(package,source_id):
    source=next((s for s in package['sources'] if s['id']==source_id),None)
    if source is None:raise ValueError('Unknown authenticated source ID')
    if package.get('module') not in ('equipment_selection','relief_selection','liquid_gas_inventory'):
        raise ValueError('Source authentication currently binds equipment/relief catalogues and liquid-source vaporizer ratings')
    key='vaporizers' if package['module']=='liquid_gas_inventory' else 'catalogue'
    records=[r for r in package['data'].get(key,[]) if r.get('source_id')==source_id]
    if not records:raise ValueError('Authenticated source has no bound numerical catalogue records')
    return dict(source={k:source[k] for k in ('id','type','document','revision','locator','sha256') if k in source},records=records)


def _decode(value,label,limit):
    if not isinstance(value,str) or len(value)>4*((limit+2)//3):raise ValueError(label+' exceeds its encoded byte bound')
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError) as e:raise ValueError(label+' must use valid base64') from e
    if len(raw)>limit:raise ValueError(label+' exceeds its byte bound')
    return raw


def verify_attestation(attestation,payload,trust_store,*,as_of=None):
    fields(attestation,'source_id manifest signature_base64 document_base64');source_id=text(attestation,'source_id')
    manifest=attestation.get('manifest');fields(manifest,'schema_version key_id issuer subject data_sha256 document_sha256 issued_on expires_on purpose')
    if manifest.get('schema_version')!='source-attestation-1':raise ValueError('Unsupported source attestation version')
    for key in ('key_id','issuer','subject','data_sha256','document_sha256','issued_on','expires_on','purpose'):text(manifest,key)
    if manifest['data_sha256']!=checksum(payload):raise ValueError('Signed source-data checksum does not match current catalogue/source records')
    document=_decode(attestation.get('document_base64'),'Source document',2000000)
    if not document or hashlib.sha256(document).hexdigest()!=manifest['document_sha256']:raise ValueError('Source document bytes do not match the signed document checksum')
    source=payload.get('source',{})
    if source.get('id')!=source_id:raise ValueError('Source attestation binding does not match its payload')
    if source.get('sha256') not in (None,manifest['document_sha256']):raise ValueError('Source record document checksum differs from authenticated evidence')
    if (not isinstance(trust_store,dict) or trust_store.get('schema_version')!='source-trust-1'
        or not isinstance(trust_store.get('keys'),list) or not 1<=len(trust_store['keys'])<=1000
        or not all(isinstance(k,dict) for k in trust_store['keys'])):raise ValueError('Server source trust store is invalid')
    keys=[k for k in trust_store['keys'] if k.get('key_id')==manifest['key_id']]
    if len(keys)!=1:raise ValueError('Signer key is unknown or duplicated in the server trust store')
    key=keys[0];fields(key,'key_id issuer role public_key_base64 identity_evidence not_before not_after revoked')
    for name in ('issuer','role','identity_evidence','not_before','not_after'):text(key,name)
    role=key['role'];expected={'MANUFACTURER':'MANUFACTURER_DATA_RELEASE','ENGINEERING_REVIEWER':'ENGINEERING_SOURCE_REVIEW'}
    if role not in expected or manifest['purpose']!=expected[role] or manifest['issuer']!=key['issuer']:raise ValueError('Attestation issuer/purpose is outside the trusted key role')
    if flag(key,'revoked'):raise ValueError('Source signer key has been revoked in the local trust store')
    today=as_of or datetime.datetime.now(datetime.timezone.utc).date()
    try:
        issued=datetime.date.fromisoformat(manifest['issued_on']);expires=datetime.date.fromisoformat(manifest['expires_on'])
        first=datetime.date.fromisoformat(key['not_before']);last=datetime.date.fromisoformat(key['not_after'])
    except ValueError as e:raise ValueError('Trust and signature dates must be ISO YYYY-MM-DD') from e
    if not first<=issued<=today<=expires<=last:raise ValueError('Source attestation is expired, future-dated or outside key validity')
    public=_decode(key.get('public_key_base64'),'Trusted public key',32);signature=_decode(attestation.get('signature_base64'),'Detached signature',64)
    if len(public)!=32 or len(signature)!=64:raise ValueError('Ed25519 requires a 32-byte public key and 64-byte signature')
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as e:raise ValueError('Install requirements-source-authentication.txt before verifying signed sources') from e
    try:Ed25519PublicKey.from_public_bytes(public).verify(signature,canonical(manifest))
    except InvalidSignature as e:raise ValueError('Source attestation cryptographic signature is invalid') from e
    return dict(source_id=source_id,key_id=manifest['key_id'],issuer=key['issuer'],signer_role=role,
        status='SIGNATURE_AND_CONTENT_VERIFIED',document_sha256=manifest['document_sha256'],data_sha256=manifest['data_sha256'],
        verified_on=today.isoformat(),trust_store_sha256=checksum(trust_store),
        limitation='Identity relies on operator-enrolled key evidence; offline revocation snapshot only. No numerical correctness, product approval or professional certification is conferred.')


def verify_package_sources(package):
    attestations=package.get('source_attestations',[])
    if not isinstance(attestations,list) or len(attestations)>20:raise ValueError('At most 20 source attestations are accepted')
    if not attestations:return dict(status='NOT_PROVIDED',sources=[],engineering_acceptance='REVIEW_REQUIRED')
    raw=os.environ.get('PLUMBING_SOURCE_TRUST_STORE')
    if not raw:raise ValueError('Configure the server-owned PLUMBING_SOURCE_TRUST_STORE after independently verifying signer identities; uploaded public keys cannot establish trust')
    path=Path(raw).resolve()
    if not path.is_file() or path.stat().st_size>200000:raise ValueError('Server source trust store is absent or exceeds its bound')
    trust=json.loads(path.read_text(encoding='utf-8'));seen=set();reports=[]
    for item in attestations:
        source_id=text(item,'source_id')
        if source_id in seen:raise ValueError('Duplicate source attestation')
        seen.add(source_id);reports.append(verify_attestation(item,source_payload(package,source_id),trust))
    return dict(status='PROVIDED_ATTESTATIONS_VERIFIED',sources=reports,engineering_acceptance='REVIEW_REQUIRED',
        limitation='Status covers the listed source IDs only; unattested inputs and source correctness are not promoted.')
