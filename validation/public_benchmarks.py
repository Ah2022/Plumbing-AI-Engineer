"""Pinned public software candidates. Nothing here grants engineering acceptance."""
import datetime,hashlib,json,os,re,subprocess,sys,tempfile,urllib.request
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'validation/public_benchmarks'
CATALOGUE=DATA/'catalogue.json'
LOCAL=ROOT/'local_sources/public_benchmarks'
TAGS=('PUBLIC_BENCHMARK','SOFTWARE_REFERENCE_ONLY','ENGINEERING_REVIEW_REQUIRED')


def sha(data):return hashlib.sha256(data).hexdigest()


def catalogue():
    result=json.loads(CATALOGUE.read_text(encoding='utf-8'))
    if result.get('schema_version')!='public-benchmarks-1':raise ValueError('Unsupported public benchmark catalogue')
    for row in result['cases']:
        if row.get('engineering_status')!='ENGINEERING_REVIEW_REQUIRED' or row.get('evidence_class') not in ('PUBLIC_BENCHMARK','REAL_OPEN_DATA_UNCALIBRATED'):
            raise ValueError('Public catalogue cannot contain approved engineering references')
        if row.get('runner') not in ('swmm','epanet','ifc','registered') or not re.fullmatch('[a-z0-9_-]{1,60}',row.get('id','')):raise ValueError('Invalid public benchmark runner/identity')
        if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',row.get('repository','')) or not re.fullmatch('[a-f0-9]{40}',row.get('commit','')):raise ValueError('Public sources require an exact repository/commit pin')
    return result


def case(identity):
    matches=[c for c in catalogue()['cases'] if c['id']==identity]
    if len(matches)!=1:raise ValueError('Unknown or duplicate public benchmark ID')
    return matches[0]


def artifact_path(record):
    root=DATA if record['redistribute'] else LOCAL
    name=PurePosixPath(record['local_path'])
    if name.is_absolute() or '..' in name.parts or '\\' in str(name):raise ValueError('Unsafe benchmark asset path')
    path=(root/str(name)).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Benchmark asset leaves its controlled directory')
    return path


def import_bytes(identity,role,raw):
    c=case(identity);matches=[a for a in c['artifacts'] if a['role']==role]
    if len(matches)!=1:raise ValueError('Unknown benchmark artifact role')
    a=matches[0]
    if not isinstance(raw,bytes) or not raw or len(raw)>2000000 or sha(raw)!=a['sha256']:raise ValueError('Imported bytes do not match the pinned source checksum/size bound')
    p=artifact_path(a);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists() and p.read_bytes()!=raw:raise ValueError('Existing asset changed; preserve it for review instead of overwriting')
    if not p.exists():p.write_bytes(raw)
    return dict(path=str(p),sha256=a['sha256'],evidence_class=c['evidence_class'],engineering_status='ENGINEERING_REVIEW_REQUIRED')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise ValueError('Public source redirect refused; review and pin the new origin explicitly')


def fetch_case(identity):
    """Explicit invocation only. Exact allowlisted commit URLs; no user URLs/scripts."""
    c=case(identity);result=[];opener=urllib.request.build_opener(_NoRedirect())
    for a in c['artifacts']:
        if artifact_path(a).exists():
            if sha(artifact_path(a).read_bytes())!=a['sha256']:raise ValueError('Installed public asset checksum changed')
            continue
        expected='https://raw.githubusercontent.com/'+c['repository']+'/'+c['commit']+'/'+a['source_path']
        if a['url']!=expected or not re.fullmatch('[a-f0-9]{40}',c['commit']):raise ValueError('Asset URL is not a pinned approved repository path')
        with opener.open(expected,timeout=20) as response:raw=response.read(2000001)
        result.append(import_bytes(identity,a['role'],raw))
    return result


def sections(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>2000000:raise ValueError('Benchmark input must be nonempty and at most 2 MB')
    try:text=raw.decode('ascii')
    except UnicodeError as e:raise ValueError('Native INP benchmark requires ASCII text') from e
    result={};group=None
    for line in text.splitlines():
        line=line.split(';',1)[0].strip()
        if not line:continue
        if line.startswith('['):
            if not re.fullmatch(r'\[[A-Za-z_]+\]',line):raise ValueError('Invalid INP section')
            group=line[1:-1].upper();result.setdefault(group,[]);continue
        if group is None:raise ValueError('Native data before a section header')
        result[group].append(line.split())
    return result


def screen_inp(raw,engine):
    s=sections(raw)
    if s.get('FILES') or s.get('LID_USAGE'):raise ValueError('External file/save interfaces are not accepted in native benchmark intake')
    for group,records in s.items():
        if group in ('TITLE','LABELS','TAGS'):continue
        for tokens in records:
            upper=[x.upper() for x in tokens]
            if any(x in ('NAN','INF','INFINITY','-INF') for x in upper):raise ValueError('Nonfinite INP value')
            if 'FILE' in upper and not (group=='BACKDROP' and upper==['FILE']):raise ValueError('External FILE reference rejected')
            if 'HYDRAULICS' in upper or 'INCLUDE' in upper:raise ValueError('External hydraulics/include interface rejected')
            if any('\\' in x or re.match(r'^[A-Za-z]:',x) or '..' in x or '/' in x and group not in ('OPTIONS','TIMES','TIMESERIES') for x in tokens):
                raise ValueError('Path-like native input rejected')
    if engine=='swmm':
        import datetime
        options={r[0].upper():r[1:] for r in s.get('OPTIONS',[])}
        units=options.get('FLOW_UNITS',['CFS'])[0].upper()
        if units not in ('CFS','GPM','MGD','CMS','LPS','MLD'):raise ValueError('Unsupported SWMM flow units')
        def clock(value):
            if ':' not in value:return float(value)
            v=[float(x) for x in value.split(':')]
            return v[0]*3600+v[1]*60+(v[2] if len(v)>2 else 0)
        start=datetime.datetime.strptime(options.get('START_DATE',['01/01/2000'])[0],'%m/%d/%Y')
        end=datetime.datetime.strptime(options.get('END_DATE',options.get('START_DATE',['01/01/2000']))[0],'%m/%d/%Y')
        duration=(end-start).total_seconds()+clock(options.get('END_TIME',['24:00:00'])[0])-clock(options.get('START_TIME',['00:00:00'])[0])
        report=clock(options.get('REPORT_STEP',['00:15:00'])[0])
        count=sum(len(s.get(k,[])) for k in ('JUNCTIONS','OUTFALLS','STORAGE','DIVIDERS','CONDUITS','PUMPS','ORIFICES','WEIRS','OUTLETS'))
        if not 0<duration<=604800 or report<=0 or count>1000 or count*duration/report>100000:raise ValueError('SWMM event exceeds native benchmark time/object/output bounds')
    elif engine=='epanet':
        units=next((r[1].upper() for r in s.get('OPTIONS',[]) if r[0].upper()=='UNITS'),'GPM')
        if units!='LPS':raise ValueError('This EPANET comparison adapter supports explicitly declared LPS inputs only; US units are not relabeled SI')
        duration=next((r[1] for r in s.get('TIMES',[]) if r[0].upper()=='DURATION'),'0:00')
        if duration not in ('0','0:00','00:00','0:00:00'):raise ValueError('EPANET adapter currently compares steady-state inputs only')
    else:raise ValueError('Unsupported benchmark engine')
    return s


def epanet_model(raw):
    s=screen_inp(raw,'epanet')
    unsupported=[g for g in ('PUMPS','VALVES','TANKS','CONTROLS','RULES','DEMANDS','EMITTERS','STATUS') if s.get(g)]
    if unsupported:raise ValueError('EPANET conversion requires explicit mapping for: '+', '.join(unsupported))
    if any(float(v)!=1 for row in s.get('PATTERNS',[]) for v in row[1:]):raise ValueError('Nonconstant patterns require explicit demand mapping')
    option={row[0].upper():row[1:] for row in s.get('OPTIONS',[])}
    if option.get('HEADLOSS',['H-W'])[0].upper()!='H-W':raise ValueError('Only explicit H-W comparison mapping is supported')
    for key in ('VISCOSITY',):
        if key in option and float(option[key][0])!=1:raise ValueError('Nondefault fluid options need explicit mapping')
    for row in s.get('OPTIONS',[]):
        words=[v.upper() for v in row]
        if words[:2] in (['DEMAND','MULTIPLIER'],['SPECIFIC','GRAVITY']) and float(row[2])!=1:raise ValueError('Nondefault multiplier/gravity mapping is unsupported')
        if words[:2]==['DEMAND','MODEL'] and words[2]!='DDA':raise ValueError('Pressure-dependent demand requires explicit mapping')
        if words[0]=='PRESSURE' or 'PRESSURE' in words[:2]:raise ValueError('Pressure unit/PDA options require explicit mapping')
    reference='Pinned public benchmark, software comparison only; not adopted plumbing/code criteria'
    nodes=[dict(id='N'+r[0],kind='junction',elevation_m=float(r[1]),demand_lps=float(r[2]) if len(r)>2 else 0,
        required_pressure_m=0,demand_reference=reference,reference=reference) for r in s.get('JUNCTIONS',[])]
    if any(len(r)>2 for r in s.get('RESERVOIRS',[])):raise ValueError('Reservoir patterns require explicit mapping')
    nodes += [dict(id='N'+r[0],kind='source',elevation_m=0,head_m=float(r[1]),reference=reference) for r in s.get('RESERVOIRS',[])]
    links=[]
    for r in s.get('PIPES',[]):
        status=r[7].upper() if len(r)>7 else 'OPEN'
        if status not in ('OPEN','CLOSED'):raise ValueError('Check valves require explicit mapping')
        links.append(dict(id='P'+r[0],kind='pipe',from_node='N'+r[1],to_node='N'+r[2],length_m=float(r[3]),internal_mm=float(r[4]),
            roughness=float(r[5]),roughness_unit='C',minor_loss_k=float(r[6]) if len(r)>6 else 0,status=status,reference=reference))
    from solvers.graph import normalize_graph
    model=dict(schema_version='pressure-network-1',units='SI',code_id='PUBLIC_BENCHMARK',basis_reference=reference,nodes=nodes,links=links,
        simulation=dict(duration_s=0,headloss='H-W',accuracy=float(option.get('ACCURACY',['.001'])[0])),demand_model=dict(type='DDA',reference=reference))
    return normalize_graph(model)[0]


def runner_fingerprint():
    files=[Path(__file__),ROOT/'validation/public_benchmark_worker.py',ROOT/'bim/ifc_intake.py',ROOT/'bim/model_intake.py',
        ROOT/'solvers/graph.py',ROOT/'solvers/service.py',ROOT/'solvers/epanet_input.py',ROOT/'solvers/epanet_native.py',ROOT/'validation/epanet_runner.py']
    return sha(json.dumps({p.relative_to(ROOT).as_posix():sha(p.read_text(encoding='utf-8').encode()) for p in files},sort_keys=True).encode())


def run_case(identity,*,library=None):
    c=case(identity);inputs={}
    base=dict(schema_version='public-benchmark-result-1',case_id=identity,evidence_class=c['evidence_class'],
        evidence_tags=list(TAGS)+(['REAL_OPEN_DATA_UNCALIBRATED'] if c['evidence_class']=='REAL_OPEN_DATA_UNCALIBRATED' else []),
        engineering_status='ENGINEERING_REVIEW_REQUIRED',acceptance_eligible=False,code_compliance_status='NOT_EVALUATED',
        executed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_commit=c['commit'],repository=c['repository'],runner_sha256=runner_fingerprint(),catalogue_sha256=sha(CATALOGUE.read_bytes()))
    for a in c['artifacts']:
        p=artifact_path(a)
        if not p.is_file():return dict(base,software_status='MISSING_INPUT',issues=['Import the pinned '+a['role']+' artifact before running'],comparisons=[])
        raw=p.read_bytes()
        if sha(raw)!=a['sha256']:return dict(base,software_status='INPUT_CHANGED',issues=['Pinned source checksum mismatch: '+a['role']],comparisons=[])
        inputs[a['role']]=raw
    if not inputs:return dict(base,software_status='SOURCE_REGISTERED_ONLY',issues=[c['limitation']],comparisons=[])
    kind=c['runner']
    if kind=='epanet':screen_inp(inputs['model'],'epanet')
    if kind=='swmm':screen_inp(inputs['model'],'swmm')
    with tempfile.TemporaryDirectory(prefix='plm-public-benchmark-') as temp:
        folder=Path(temp)
        for role,raw in inputs.items():
            if not re.fullmatch('[a-z_]+',role):raise ValueError('Unsafe artifact role')
            (folder/(role+'.dat')).write_bytes(raw)
        request=dict(case=c,library=str(library) if library else None)
        (folder/'request.json').write_text(json.dumps(request),encoding='utf-8')
        try:proc=subprocess.run([sys.executable,'-m','validation.public_benchmark_worker',str(folder)],cwd=ROOT,capture_output=True,timeout=60,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:return dict(base,software_status='TIMEOUT',issues=['Isolated benchmark exceeded 60 seconds; partition or review the case'],comparisons=[])
        target=folder/'result.json'
        if proc.returncode or not target.is_file() or target.stat().st_size>20000000:
            return dict(base,software_status='RUN_FAILED',issues=[proc.stderr.decode(errors='replace')[-2000:] or 'Native worker failed'],comparisons=[])
        report=json.loads(target.read_text())
    protected={'schema_version','case_id','evidence_class','evidence_tags','engineering_status','acceptance_eligible','code_compliance_status','repository','source_commit','runner_sha256','catalogue_sha256'}
    if protected.intersection(report):raise ValueError('Native result cannot override public provenance or engineering acceptance')
    base.update(input_sha256={role:sha(raw) for role,raw in inputs.items()},**report)
    if base['software_status'] not in ('PASS','FAIL','BACKEND_UNAVAILABLE'):raise ValueError('Unexpected public software result')
    return base


def recorded_result(identity):
    case(identity)
    p=DATA/'recorded_results'/(identity+'.json')
    if not p.is_file():return None
    report=json.loads(p.read_text(encoding='utf-8'))
    if report.get('case_id')!=identity or report.get('acceptance_eligible') is not False or report.get('engineering_status')!='ENGINEERING_REVIEW_REQUIRED':raise ValueError('Recorded public result has an invalid provenance/acceptance contract')
    return report


def save_result(report,root=None):
    destination=(Path(root) if root else ROOT/'.review/public_benchmarks').resolve();destination.mkdir(parents=True,exist_ok=True)
    identity=report.get('case_id','')
    if not re.fullmatch('[a-z0-9_-]{1,60}',identity) or report.get('acceptance_eligible') is not False or report.get('engineering_status')!='ENGINEERING_REVIEW_REQUIRED':raise ValueError('Public evidence cannot claim engineering acceptance')
    path=destination/(identity+'-'+sha(json.dumps(report,sort_keys=True).encode())[:12]+'.json')
    path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');return path
