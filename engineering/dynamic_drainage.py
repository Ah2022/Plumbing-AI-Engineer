"""Bounded structured-input boundary to EPA SWMM dynamic-wave liquid hydraulics.

The native library always runs in a disposable child process. User-provided INP
files, external file references and control scripts are deliberately not accepted.
"""
import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from engineering.common import fields, num, text, rows, unique, check, result


def _identifier(row, key):
    value = text(row, key)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', value):
        raise ValueError(key+' must use a letter followed by at most 39 letters, digits, underscores or hyphens')
    return value


def _clock(seconds):
    seconds = int(seconds)
    return f'{seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02}'


def _input(data):
    fields(data, 'source_id duration_s routing_step_s report_step_s minimum_node_area_m2 maximum_continuity_error_pct nodes pipes inflows')
    ref = text(data, 'source_id')
    duration = num(data, 'duration_s', positive=True, maximum=86400)
    report = num(data, 'report_step_s', minimum=1, maximum=3600)
    step = num(data, 'routing_step_s', minimum=.05, maximum=30)
    nodearea = num(data, 'minimum_node_area_m2',positive=True)
    if duration != int(duration) or report != int(report) or duration < report or duration % report:
        raise ValueError('Duration and report step must be whole seconds; duration must be a multiple of report step')
    num(data, 'maximum_continuity_error_pct', positive=True, maximum=5)
    nodes = rows(data, 'nodes', limit=100); unique(nodes)
    pipes = rows(data, 'pipes', limit=200); unique(pipes)
    if len(nodes)*duration/report + len(pipes)*duration/report > 50000:
        raise ValueError('At most 50000 node/link report samples; increase report step or shorten event')
    ids = {}; junctions = []; outfalls = []
    for n in nodes:
        fields(n, 'id source_id kind invert_m maximum_depth_m initial_depth_m outfall_type tailwater_head_m')
        identity = _identifier(n, 'id'); text(n, 'source_id'); ids[identity] = n
        invert = num(n, 'invert_m')
        if n.get('kind') == 'junction':
            depth = num(n, 'maximum_depth_m', positive=True)
            initial = num(n, 'initial_depth_m', minimum=0, maximum=depth)
            junctions.append(f'{identity} {invert} {depth} {initial} 0 0')
        elif n.get('kind') == 'outfall':
            typ = n.get('outfall_type')
            if typ not in ('FREE', 'FIXED'): raise ValueError('Outfall type must be FREE or FIXED')
            head = num(n, 'tailwater_head_m')
            outfalls.append(f'{identity} {invert} {typ}'+(f' {head}' if typ=='FIXED' else '')+' NO')
        else: raise ValueError('Node kind must be junction or outfall')
    if not outfalls: raise ValueError('At least one outfall is required')
    conduits = []; sections = []; neighbours = {n: set() for n in ids}
    for p in pipes:
        fields(p, 'id source_id from_node to_node length_m internal_mm manning_n inlet_offset_m outlet_offset_m entry_loss_k exit_loss_k average_loss_k')
        identity = _identifier(p, 'id'); text(p, 'source_id')
        a = _identifier(p, 'from_node'); b = _identifier(p, 'to_node')
        if a not in ids or b not in ids or a==b: raise ValueError('Conduit endpoints must name two different existing nodes')
        if ids[a]['kind']=='outfall' and ids[b]['kind']=='outfall': raise ValueError('A conduit cannot connect two outfalls')
        length = num(p, 'length_m', positive=True); d = num(p, 'internal_mm', positive=True)/1000
        rough = num(p, 'manning_n', positive=True)
        off1 = num(p, 'inlet_offset_m', minimum=0); off2 = num(p, 'outlet_offset_m', minimum=0)
        for name in ('entry_loss_k','exit_loss_k','average_loss_k'): num(p, name, minimum=0)
        conduits.append(f'{identity} {a} {b} {length} {rough} {off1} {off2} 0 0')
        sections.append(f'{identity} CIRCULAR {d} 0 0 0 1')
        neighbours[a].add(b); neighbours[b].add(a)
    reachable = {n for n in ids if ids[n]['kind']=='outfall'}; todo = list(reachable)
    for n in todo:
        for other in neighbours[n]-reachable: reachable.add(other); todo.append(other)
    if reachable != set(ids): raise ValueError('Disconnected network: every node must have a path to an outfall')
    inflows = rows(data, 'inflows', empty=True, limit=100); unique(inflows)
    ts = []; inlines = []
    for i, flow in enumerate(inflows):
        fields(flow, 'id source_id node hydrograph'); text(flow, 'source_id'); _identifier(flow, 'id')
        node = _identifier(flow, 'node')
        if node not in ids or ids[node]['kind']!='junction': raise ValueError('Inflows require existing junctions')
        points = rows(flow, 'hydrograph', limit=1000)
        last = -1
        for point in points:
            fields(point, 'time_s flow_lps')
            t = num(point, 'time_s', minimum=0, maximum=duration); q = num(point, 'flow_lps', minimum=0)
            if t != int(t) or t <= last: raise ValueError('Hydrograph times must be strictly increasing whole seconds')
            last = t; ts.append(f'TS{i} {_clock(t)} {q}')
        if points[0]['time_s']!=0 or last!=duration:
            raise ValueError('Every hydrograph must explicitly cover time zero through event end; no extrapolation')
        inlines.append(f'{node} FLOW TS{i} FLOW 1.0 1.0 0')
    end = datetime.datetime(2020,1,1)+datetime.timedelta(seconds=duration)
    options = ['FLOW_UNITS LPS', 'FLOW_ROUTING DYNWAVE', 'START_DATE 01/01/2020', 'START_TIME 00:00:00',
        'REPORT_START_DATE 01/01/2020', 'REPORT_START_TIME 00:00:00',
        'END_DATE '+end.strftime('%m/%d/%Y'), 'END_TIME '+end.strftime('%H:%M:%S'),
        'REPORT_STEP '+_clock(report), 'ROUTING_STEP '+str(step), 'LINK_OFFSETS DEPTH',
        'INERTIAL_DAMPING PARTIAL', 'NORMAL_FLOW_LIMITED BOTH', 'ALLOW_PONDING NO',
        'VARIABLE_STEP 0.75', 'MINIMUM_STEP 0.01', 'MAX_TRIALS 20', 'HEAD_TOLERANCE 0.0001',
        'MIN_SURFAREA '+str(nodearea),'THREADS 1']
    losses = [f"{p['id']} {p['entry_loss_k']} {p['exit_loss_k']} {p['average_loss_k']} NO 0" for p in pipes]
    sections_text = [('OPTIONS',options), ('JUNCTIONS',junctions), ('OUTFALLS',outfalls),
        ('CONDUITS',conduits), ('XSECTIONS',sections), ('LOSSES',losses), ('INFLOWS',inlines), ('TIMESERIES',ts),
        ('REPORT',['INPUT NO','CONTINUITY YES','FLOWSTATS YES','NODES ALL','LINKS ALL'])]
    return '\n\n'.join('['+name+']\n'+'\n'.join(lines) for name,lines in sections_text)+'\n', ref


def dynamic_drainage(data):
    inp, ref = _input(data)
    with tempfile.TemporaryDirectory(prefix='plumbing-swmm-') as directory:
        folder = Path(directory); (folder/'model.inp').write_text(inp, encoding='ascii')
        try:
            process = subprocess.run([sys.executable, '-m', 'engineering.dynamic_drainage', '--worker', str(folder)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=45,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as error:
            raise ValueError('SWMM exceeded 45 seconds. Shorten the event, simplify the network or review unstable geometry/boundaries.') from error
        if process.returncode or not (folder/'result.json').exists():
            diagnostic = ((folder/'model.rpt').read_text(errors='replace') if (folder/'model.rpt').exists() else '')+'\n'+process.stderr.decode(errors='replace')
            errors = [line.strip() for line in diagnostic.splitlines() if re.search(r'ERROR\s+\d+|\w*Error:|Exception:',line)]
            raise ValueError('SWMM could not complete. '+(' '.join(errors)[-1600:] or 'Check native swmm-toolkit installation and network geometry/boundaries. Install requirements-hydraulics.txt.'))
        native = json.loads((folder/'result.json').read_text())
    trace = native['trace']; mb = native['continuity_error_pct']; flooding = native['flooding_volume_m3']
    checks = [check('liquid_continuity',abs(mb)<=data['maximum_continuity_error_pct'],mb,data['maximum_continuity_error_pct'],'%',ref),
        check('node_flooding',flooding<=1e-9,flooding,0,'m³',ref),
        check('routing_nonconvergence',native['nonconverging_steps']==0,native['nonconverging_steps'],0,'steps',ref)]
    return result(dict(continuity_error_pct=mb, flooding_volume_m3=flooding,
        maximum_depth_m=max((r.get('depth_m',0) for r in trace),default=0),
        maximum_absolute_flow_lps=max((abs(r.get('flow_lps',0)) for r in trace),default=0),
        report_periods=native['periods'], nonconverging_steps=native['nonconverging_steps'], solver_version=native['version']),
        dict(continuity_error_pct='%',flooding_volume_m3='m³',maximum_depth_m='m',maximum_absolute_flow_lps='L/s',
            report_periods='count',nonconverging_steps='steps',solver_version='SWMM'), checks, trace,
        complete=native['nonconverging_steps']==0 and abs(mb)<=data['maximum_continuity_error_pct'],
        notes=['EPA SWMM dynamic-wave Saint-Venant liquid hydraulics; native process isolated with a 45-second execution limit.',
            'Hydrograph inputs are L/s, independently supplied. DFU is not converted to flow. Flooding leaves the model; no surface ponding or re-entry is modeled.',
            'Circular conduits, junction storage and free/fixed-head outfalls. Backwater, reverse liquid flow and surcharge are included. Review supplied minimum nodal storage area; initial depths and initial zero pipe flows affect startup.',
            'Building-stack annular flow, entrained air, solids, trap air pressure, detailed fixture discharge and code compliance are not established by SWMM.',
            'Failed continuity or convergence invalidates hydraulic acceptance: review initial storage, nodal area, boundary/tailwater conditions and timestep, then rerun a complete event or a justified steady-state initialization. A converged run can still fail continuity.',
            'Peaks in trace are sampled at report intervals; flooding volume and convergence use full-step solver statistics. Nonconverging steps is the sum of node nonconverged step counts. Reduce report/routing steps and compare results for the project.'])


def _worker(folder):
    from swmm.toolkit import solver, output, shared_enum as E
    folder = Path(folder); opened = False
    try:
        solver.swmm_open(str(folder/'model.inp'),str(folder/'model.rpt'),str(folder/'model.out')); opened=True
        version = str(solver.swmm_get_version())
        solver.swmm_start(1)
        while solver.swmm_step() > 0: pass
        flooding = 0.; nonconverging = 0
        for index in range(solver.project_get_count(E.ObjectType.NODE)):
            stats = solver.node_get_stats(index)
            flooding += stats.volFlooded
            nonconverging += stats.nonConvergedCount
        solver.swmm_end()
        mb = solver.swmm_get_mass_balance()[1]
        solver.swmm_report(); solver.swmm_close(); opened=False
        h = output.init()
        try:
            output.open(h,str(folder/'model.out'))
            periods = output.get_times(h,E.Time.NUM_PERIODS); interval = output.get_times(h,E.Time.REPORT_STEP)
            counts = output.get_proj_size(h); trace=[]
            for index in range(counts[1]):
                identity = output.get_elem_name(h,E.ElementType.NODE,index)
                series = {name:output.get_node_series(h,index,attribute,0,periods-1) for name,attribute in
                    [('depth_m',E.NodeAttribute.INVERT_DEPTH),('head_m',E.NodeAttribute.HYDRAULIC_HEAD),('flooding_lps',E.NodeAttribute.FLOODING_LOSSES)]}
                for j in range(periods): trace.append(dict(kind='node',id=identity,time_s=(j+1)*interval,**{k:v[j] for k,v in series.items()}))
            for index in range(counts[2]):
                identity = output.get_elem_name(h,E.ElementType.LINK,index)
                series = {name:output.get_link_series(h,index,attribute,0,periods-1) for name,attribute in
                    [('flow_lps',E.LinkAttribute.FLOW_RATE),('depth_m',E.LinkAttribute.FLOW_DEPTH),('velocity_m_s',E.LinkAttribute.FLOW_VELOCITY),('capacity_ratio',E.LinkAttribute.CAPACITY)]}
                for j in range(periods): trace.append(dict(kind='pipe',id=identity,time_s=(j+1)*interval,**{k:v[j] for k,v in series.items()}))
        finally: output.close(h)
        if any(not math.isfinite(v) for row in trace for v in row.values() if isinstance(v,(int,float))):
            raise ValueError('SWMM produced nonfinite output; inspect geometry, timestep and hydraulic boundaries')
        (folder/'result.json').write_text(json.dumps(dict(version=version,continuity_error_pct=mb,
            flooding_volume_m3=flooding,nonconverging_steps=nonconverging,periods=periods,trace=trace),allow_nan=False))
    finally:
        if opened: solver.swmm_close()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--worker': raise SystemExit('Internal native-worker entry point')
    _worker(sys.argv[2])
