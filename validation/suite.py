"""Golden comparisons never update expected outputs."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from validation.adapter import DATA,load,reference_connection,run_method,run_project
from validation.gate import validation_gate
from validation.reference_math import epanet_convention_pressures
from validation.epanet_runner import run_epanet


def run_validation(*,epanet_library=None):
    gate=validation_gate()
    conn=reference_connection();methods=[];projects=[]
    try:
        for case in load('method-cases.json'):
            try:methods.append(run_method(case,conn))
            except Exception as error:methods.append(dict(case=case['id'],software_status='FAIL',error=str(error)))
        for folder in sorted((DATA/'projects').iterdir()):
            if not folder.is_dir():continue
            project=json.loads((folder/'input.json').read_text(encoding='utf-8'))
            expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
            row=run_project(project,expected,conn)
            recorded=json.loads((folder/'epanet-results.json').read_text(encoding='utf-8'))
            inp=(folder/'epanet.inp').read_text(encoding='ascii')
            epanet=run_epanet(inp,epanet_library) if epanet_library else recorded
            errors=[];conventions=epanet_convention_pressures(project)
            for tid,target in conventions.items():
                if abs(epanet['nodes'][tid]['pressure_m']-target)>1e-6:errors.append(tid+': unexplained EPANET pressure discrepancy')
            for pid,target in expected['pipes'].items():
                if abs(epanet['pipes'][pid]['flow_lps']-target['flow_lps'])>1e-6:errors.append(pid+': unexplained EPANET flow discrepancy')
            if epanet['input_sha256']!=hashlib.sha256(inp.encode('ascii')).hexdigest():errors.append('EPANET evidence input checksum differs')
            allowed=[dict(operation='EN_solveH',code=6)] if project['project_id']=='hospital' else []
            if epanet['warnings']!=allowed:errors.append('Unexpected EPANET warning set')
            row['epanet']=dict(mode='LIVE_EXTERNAL_RUN' if epanet_library else 'RECORDED_EXTERNAL_RUN',version=epanet['version'],
                software_status='FAIL' if errors else 'PASS',errors=errors,warnings=epanet['warnings'])
            if errors:row['software_status']='FAIL'
            projects.append(row)
    finally:conn.close()
    okay=all(r['software_status']=='PASS' for r in methods+projects)
    if not okay:
        gate=dict(gate,authoritative=False,release_label='ENGINEERING_VALIDATION_PENDING',engineering_status='REVIEW_REQUIRED',
                  issues=gate['issues']+['Golden reference comparisons failed; unresolved discrepancies block acceptance'])
    return dict(schema_version='phase1a-validation-result-1',software_status='PASS' if okay else 'FAIL',
                engineering_gate=gate,methods=methods,projects=projects)


def review_bundle():
    """A local reviewer download, never a transmission or an approval."""
    buffer=BytesIO()
    with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:
        for file in sorted(DATA.rglob('*')):
            if file.is_file():archive.write(file,'phase1a/'+file.relative_to(DATA).as_posix())
        for name in ('reference_math.py','epanet_runner.py'):
            archive.write(Path(__file__).parent/name,name)
        guide=DATA.parent.parent/'docs/ENGINEERING_VALIDATION.md'
        if guide.is_file():archive.write(guide,'REVIEW_GUIDE.md')
    return buffer.getvalue()
