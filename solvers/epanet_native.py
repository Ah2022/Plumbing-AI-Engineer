"""EPANET 2.2 toolkit in a disposable worker process. Never code approval."""
import ctypes as c
import hashlib
import math
from pathlib import Path
import os
import tempfile
from solvers.epanet_input import build_input

ADVICE={1:'Hydraulic iterations did not balance. Check disconnected demand, pump curve range, incompatible valve settings and control thresholds; revise the physical model before changing numerical tolerances.',
 2:'Hydraulic link status oscillated. Inspect overlapping pump/valve controls, tank thresholds and pressure settings.',
 3:'Demand is disconnected from supply. Check closed links, pump failure, empty/full tank restrictions and the flagged nodes.',
 4:'Pump operated outside its specified curve range. Check manufacturer curve, speed, connected system resistance and required operating duty.',
 5:'Valve cannot achieve its requested setting. Check upstream pressure, imposed flow and adjacent valve/pump settings.',
 6:'Negative pressure occurred. Review minimum source head, elevations, losses and booster/zone requirements; use PDA to assess curtailed demand rather than treating forced DDA flow as delivered service.',
 110:'Hydraulic equations could not be solved. Check source connectivity, contradictory valve/control settings, demand and pump-curve operating range.'}


class ToolkitError(Exception):
    def __init__(self,diagnostic):self.diagnostic=diagnostic;super().__init__(diagnostic['message'])


def simulate(model,library):
    dll=(c.WinDLL if os.name=='nt' else c.CDLL)(str(library));handle=c.c_void_p();opened=False;hydraulics=False
    signatures={'EN_getversion':[c.POINTER(c.c_int)],'EN_geterror':[c.c_int,c.c_char_p,c.c_int],
      'EN_createproject':[c.POINTER(c.c_void_p)],'EN_deleteproject':[c.c_void_p],
      'EN_open':[c.c_void_p,c.c_char_p,c.c_char_p,c.c_char_p],'EN_close':[c.c_void_p],
      'EN_openH':[c.c_void_p],'EN_initH':[c.c_void_p,c.c_int],'EN_runH':[c.c_void_p,c.POINTER(c.c_long)],
      'EN_nextH':[c.c_void_p,c.POINTER(c.c_long)],'EN_closeH':[c.c_void_p],
      'EN_getnodeindex':[c.c_void_p,c.c_char_p,c.POINTER(c.c_int)],'EN_getlinkindex':[c.c_void_p,c.c_char_p,c.POINTER(c.c_int)],
      'EN_getnodevalue':[c.c_void_p,c.c_int,c.c_int,c.POINTER(c.c_double)],'EN_getlinkvalue':[c.c_void_p,c.c_int,c.c_int,c.POINTER(c.c_double)]}
    for name,args in signatures.items():getattr(dll,name).argtypes=args;getattr(dll,name).restype=c.c_int
    diagnostics=[];snapshots=[];current_time=0;fatal=False
    def call(name,*args):
        nonlocal current_time
        code=getattr(dll,name)(*args)
        if name=='EN_runH':current_time=c.cast(args[-1],c.POINTER(c.c_long)).contents.value
        if code:
            msg=c.create_string_buffer(512);dll.EN_geterror(code,msg,512)
            item=dict(operation=name,code=code,time_s=current_time,message=msg.value.decode('utf-8',errors='replace'),
                      action=ADVICE.get(code,'Review element definitions and EPANET report details; correct the model and rerun.'),
                      severity='ERROR' if code>=100 or code in (1,2) else 'WARNING')
            if len(diagnostics)<1000:diagnostics.append(item)
            if code>=100:raise ToolkitError(item)
        return code
    def value(name,index,prop):
        out=c.c_double();call(name,handle,index,prop,c.byref(out))
        if not math.isfinite(out.value):raise ValueError('EPANET produced a non-finite hydraulic value')
        return out.value
    version=c.c_int();call('EN_getversion',c.byref(version))
    if version.value!=20200:raise ValueError('Use the supported EPANET 2.2 toolkit (version 20200)')
    inp=build_input(model)
    with tempfile.TemporaryDirectory(prefix='plm_general_solver_') as folder:
        path=Path(folder);(path/'network.inp').write_text(inp,encoding='ascii');call('EN_createproject',c.byref(handle))
        try:
            call('EN_open',handle,os.fsencode(path/'network.inp'),os.fsencode(path/'network.rpt'),b'');opened=True
            ni={};li={}
            for objects,table,fn in [(model['nodes'],ni,'EN_getnodeindex'),(model['links'],li,'EN_getlinkindex')]:
                for row in objects:
                    index=c.c_int();call(fn,handle,row['id'].encode('ascii'),c.byref(index));table[row['id']]=index.value
            call('EN_openH',handle);hydraulics=True;call('EN_initH',handle,0)
            while True:
                t=c.c_long();warning=call('EN_runH',handle,c.byref(t));current_time=t.value
                if warning in (1,2):fatal=True;break
                node_rows=[];node_heads={}
                for node in model['nodes']:
                    index=ni[node['id']];head=value('EN_getnodevalue',index,10);node_heads[node['id']]=head
                    row=dict(node_id=node['id'],kind=node['kind'],head_m=head,pressure_m=value('EN_getnodevalue',index,11))
                    if node['kind']=='source':
                        # Reservoir surface pressure from EPANET is not pressure
                        # at the user's declared plumbing boundary elevation.
                        row.pop('pressure_m')
                        row.update(boundary_pressure_head_m=head-node['elevation_m'],net_supply_lps=-value('EN_getnodevalue',index,9))
                    if node['kind']=='junction':
                        pattern=model['patterns'].get(node.get('demand_pattern'),[1]);mult=pattern[(current_time//model['simulation']['pattern_step_s'])%len(pattern)]
                        requested=node['demand_lps']*mult+node['fire_demand_lps'];delivered=value('EN_getnodevalue',index,9)
                        row.update(requested_demand_lps=requested,delivered_demand_lps=delivered,
                            demand_deficit_lps=max(0,requested-delivered),required_pressure_m=node['required_pressure_m'],
                            pressure_margin_m=row['pressure_m']-node['required_pressure_m'])
                    if node['kind']=='tank':
                        row['level_m']=value('EN_getnodevalue',index,8);row['volume_m3']=value('EN_getnodevalue',index,24)
                        row['net_inflow_lps']=value('EN_getnodevalue',index,9)
                    node_rows.append(row)
                link_rows=[]
                for link in model['links']:
                    index=li[link['id']];row=dict(link_id=link['id'],kind=link['kind'],flow_lps=value('EN_getlinkvalue',index,8),
                        status='OPEN' if value('EN_getlinkvalue',index,11)>0 else 'CLOSED',
                        head_drop_m=node_heads[link['from_node']]-node_heads[link['to_node']])
                    if link['kind']!='pump':row['velocity_m_s']=value('EN_getlinkvalue',index,9)
                    else:row['relative_speed']=value('EN_getlinkvalue',index,12)
                    if link['kind']=='valve':
                        row.update(configured_setting=link['setting'],setting_unit=link['setting_unit'])
                        if link['valve_type']=='FCV':row['flow_setting_residual_lps']=row['flow_lps']-link['setting']
                    link_rows.append(row)
                snapshots.append(dict(time_s=current_time,nodes=node_rows,links=link_rows))
                if len(snapshots)*(len(ni)+len(li))>200000:raise ValueError('Result limit exceeded; shorten duration or simplify network before rerunning')
                step=c.c_long();call('EN_nextH',handle,c.byref(step))
                if step.value==0:break
        except ToolkitError:
            fatal=True
        finally:
            if hydraulics:dll.EN_closeH(handle)
            if opened:dll.EN_close(handle)
            dll.EN_deleteproject(handle)
        report=(path/'network.rpt').read_text(encoding='utf-8',errors='replace') if (path/'network.rpt').exists() else ''
    complete=bool(snapshots) and snapshots[-1]['time_s']==model['simulation']['duration_s'] and not fatal
    result=dict(solver_status='NOT_CONVERGED' if fatal else 'INCOMPLETE' if not complete else 'CONVERGED_WITH_WARNINGS' if diagnostics else 'CONVERGED',
        complete=complete,snapshots=snapshots,diagnostics=diagnostics,report_excerpt=report[-16000:],
        toolkit_version=version.value,library_sha256=hashlib.sha256(Path(library).read_bytes()).hexdigest(),
        epanet_input_sha256=hashlib.sha256(inp.encode('ascii')).hexdigest(),solved_until_s=snapshots[-1]['time_s'] if snapshots else None)
    return result
