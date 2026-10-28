"""Compare fixed engineering references and stamp bounded software evidence only."""
import hashlib,json,math
from pathlib import Path
from engineering.registry import CASES,EVIDENCE,implementation_fingerprint
from engineering.service import run_module


def validate():
    cases=json.loads(CASES.read_text(encoding='utf-8'));results=[]
    for case in cases:
        try:
            actual=run_module(case['input']);errors=[]
            for key,expected in case['expected_values'].items():
                value=actual['values'][key]
                good=math.isclose(value,expected,rel_tol=0,abs_tol=case['absolute_tolerance']) if isinstance(expected,(float,int)) else value==expected
                if not good:errors.append(dict(field=key,expected=expected,actual=value))
            if actual['technical_status']!=case['expected_status'] or actual['complete']!=case['complete']:errors.append(dict(field='technical_status/completion',actual=actual['technical_status']))
        except Exception as error:errors=[dict(error=str(error))]
        results.append(dict(case=case['id'],module=case['module'],software_status='FAIL' if errors else 'PASS',discrepancies=errors))
    return dict(schema_version='engineering-software-evidence-1',software_status='PASS' if results and all(r['software_status']=='PASS' for r in results) else 'FAIL',
        implementation_sha256=implementation_fingerprint(),reference_cases_sha256=hashlib.sha256(CASES.read_text(encoding='utf-8').encode()).hexdigest(),
        cases=results,engineering_status='REVIEW_REQUIRED',code_compliance_status='NOT_EVALUATED',
        limitations=['Author-prepared arithmetic and condition-action candidates; not independently approved real-project/code/manufacturer validation.','Passing software evidence cannot grant code adoption, engineering approval or certification.'])


def main():
    evidence=validate();EVIDENCE.parent.mkdir(parents=True,exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(software_status=evidence['software_status'],cases=len(evidence['cases']),engineering_status=evidence['engineering_status'])))
    raise SystemExit(0 if evidence['software_status']=='PASS' else 1)


if __name__=='__main__':main()
