"""Fail-closed engineering acceptance; software agreement cannot grant approval."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(__file__).parent/'phase1a'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_entrypoints():
    result=set()
    for path in (ROOT/'calculations').glob('*.py'):
        if path.stem in ('validation','__init__'):continue
        for node in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(node,ast.FunctionDef) and not node.name.startswith('_'):
                result.add(f'calculations.{path.stem}.{node.name}')
    return result


def _signed_evidence_exists(review):
    name=review.get('signature_artifact_path')
    if not isinstance(name,str) or not name:return False
    private=(ROOT/'.review/engineering_validation').resolve()
    path=(private/name).resolve()
    return path.is_relative_to(private) and path.is_file() and sha(path)==review.get('signature_artifact_sha256')


def _entry_accepted(entry):
    """An ACCEPTED flag alone cannot fill a missing independent reference."""
    if entry.get('engineering_status')!='ACCEPTED' or entry.get('evidence_class')!='AUTHENTICATED_CODE_OR_APPROVED_PROJECT_REFERENCE':return False
    review=entry.get('review',{})
    name=entry.get('independent_reference_path')
    if not isinstance(name,str) or not name:return False
    private=(ROOT/'.review/engineering_validation').resolve();path=(private/name).resolve()
    return (path.is_relative_to(private) and path.is_file() and sha(path)==entry.get('independent_reference_sha256') and
            review.get('reference_sha256')==entry.get('independent_reference_sha256') and
            review.get('decision')=='ACCEPTED' and review.get('qualified_plumbing_engineer') is True and
            review.get('independent_of_implementation') is True and _signed_evidence_exists(review) and
            all(review.get(k) for k in ('reviewer_name','credentials','signed_at','source_authentication_evidence')))


def validation_gate(data=DATA):
    data=Path(data);issues=[]
    try:
        manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
        actual_files={p.relative_to(data).as_posix() for p in data.rglob('*') if p.is_file() and p.name!='manifest.json'}
        if set(manifest['files'])!=actual_files:issues.append('Reference manifest omits evidence files or contains missing entries')
        for name,digest in manifest['files'].items():
            path=(data/name).resolve()
            if not path.is_relative_to(data.resolve()) or not path.is_file() or sha(path)!=digest:
                issues.append('Reference evidence changed or missing: '+name)
        coverage=json.loads((data/'coverage.json').read_text(encoding='utf-8'))
        registered={r['entrypoint'] for r in coverage['core_calculations']}
        unregistered=sorted(core_entrypoints()-registered)
        if unregistered:issues.append('Unregistered supported calculations: '+', '.join(unregistered))
        if registered-core_entrypoints():issues.append('Reference registry contains removed/renamed calculations')
        # Every supported converted form must remain visible as a separate gap.
        forms=json.loads((ROOT/'docs/INTERACTIVE_FORM_CHECK.json').read_text(encoding='utf-8'))
        expected_forms={(c['package_sha256'],f['worksheet']) for c in forms['calculations'] for f in c['forms']}
        registered_forms={(r['package_sha256'],r['worksheet']) for r in coverage['interactive_forms']}
        if expected_forms!=registered_forms:issues.append('Interactive form coverage registry differs from installed-library inventory')
        pending=[r for group in ('core_calculations','interactive_forms') for r in coverage[group] if not _entry_accepted(r)]
        if pending:issues.append(f'{len(pending)} calculation/form entries lack accepted independent engineering references')
        pending_modules=0
        if (ROOT/'engineering/registry.py').is_file():
            from engineering.registry import MODULES
            reviews_path=ROOT/'.review/engineering_validation/module_reviews.json'
            module_reviews=json.loads(reviews_path.read_text(encoding='utf-8')) if reviews_path.is_file() else []
            approved={r.get('id') for r in module_reviews if isinstance(r,dict) and _entry_accepted(r)}
            pending_modules=sum(m['id'] not in approved for m in MODULES)
            if pending_modules:issues.append(f'{pending_modules} scoped engineering modules need accepted independent reference/source evidence; software examples do not approve them')
        projects=[]
        for folder in sorted((data/'projects').iterdir()):
            if not folder.is_dir():continue
            project=json.loads((folder/'input.json').read_text(encoding='utf-8'))
            review=json.loads((folder/'review.json').read_text(encoding='utf-8'))
            okay=(project.get('provenance')=='INDEPENDENT_REAL_REFERENCE_PROJECT' and
                  project.get('code_adoption')=='APPROVED' and review.get('decision')=='ACCEPTED' and
                  review.get('expected_sha256')==sha(folder/'expected.json') and
                  review.get('input_sha256')==sha(folder/'input.json') and
                  review.get('qualified_plumbing_engineer') is True and
                  review.get('independent_of_implementation') is True and
                  _signed_evidence_exists(review) and
                  all(review.get(k) for k in ('reviewer_name','credentials','signed_at','signature_artifact_sha256','source_authentication_evidence')))
            projects.append(dict(project_id=project['project_id'],building_type=project['building_type'],
                provenance=project['provenance'],reviewer_role=review.get('designated_reviewer_role'),
                engineering_status='ACCEPTED' if okay else 'PENDING'))
            if not okay:issues.append(project['project_id']+': approved independent reference/source/reviewer evidence is pending')
        if {p['project_id'] for p in projects}!={'residential','office','hotel','hospital','mixed_use'}:
            issues.append('The five required building-type reference projects are incomplete')
        discrepancies=json.loads((data/'discrepancies.json').read_text(encoding='utf-8'))
        if any(r['engineering_review']!='ACCEPTED' for r in discrepancies):issues.append('EPANET convention differences and warning decisions await engineering acceptance')
        return dict(schema_version='engineering-validation-gate-1',release_label='ENGINEERING_VALIDATION_PENDING' if issues else 'ENGINEERING_ACCEPTED',
            engineering_status='REVIEW_REQUIRED' if issues else 'ACCEPTED',authoritative=not issues,
            core_calculations=len(registered),unregistered_calculations=unregistered,
            interactive_forms=len(registered_forms),pending_reference_entries=len(pending),pending_module_scopes=pending_modules,
            projects=projects,issues=issues,reviewer='BIM MANAGER',
            limitation='Checks evidence completeness and integrity; external signature authenticity and professional qualifications require human verification.')
    except (OSError,ValueError,KeyError,TypeError) as error:
        return dict(schema_version='engineering-validation-gate-1',release_label='ENGINEERING_VALIDATION_PENDING',
                    engineering_status='REVIEW_REQUIRED',authoritative=False,projects=[],issues=['Validation evidence unavailable/invalid: '+str(error)])
