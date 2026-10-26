"""Run identical synthetic cases in separate old/new engine processes.

No default engine database is opened. No workbook values are published.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PROBE = r'''
import json, math
from calculations.hydraulics import velocity_from_flow, hazen_williams_head_loss, pump_power, rational_method_peak_flow
from database.db import init_db
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from compliance.engine import run_compliance_for_project
from app.db_helpers import save_calculation
conn=init_db(':memory:')
load_all_rules(conn)
sync_predicate_flags(conn)
conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (1,'Synthetic comparison','Office','IPC')")
conn.execute("INSERT INTO design_basis_items(project_id,item_key,item_value,status) VALUES (1,'static_pressure_psi','60','PENDING')")
conn.commit()
result=velocity_from_flow(1,25,'T-001')
result.notes='Synthetic comparison rationale'
save_calculation(conn,1,result)
check=next(r for r in run_compliance_for_project(conn,1,'IPC') if r['rule_id']=='IPC-W-002')
row=dict(conn.execute("SELECT * FROM calculations WHERE calc_id='T-001'").fetchone())
out={
 'velocity_1lps_25mm':result.result_value,
 'hazen_2_5lps_50mm_40m_C150':hazen_williams_head_loss(2.5,50,40,150,'T-2').result_value,
 'pump_5lps_41m_eta0_7':pump_power(5,41,.7,'T-3').result_value,
 'rain_3600mmhr_1m2_C1':rational_method_peak_flow(1,3600,1,'T-4').result_value,
 'pending_pressure_compliance_status':check['status'],
 'pending_pressure_technical_status':check.get('technical_status',check['status']),
 'saved_notes':row.get('notes'),
 'saved_review_status':row.get('review_status','ABSENT'),
 'has_versioned_governance':bool(row.get('governance_json')),
 'profile_switch_invalidates':'UNAVAILABLE'
}
try:
 from compliance.governance import set_basis, get_basis
 set_basis(conn,1,'IPC-2024',{'systems':['water'],'units':'SI'},'Synthetic comparison engineer')
 out['profile_switch_invalidates']=conn.execute("SELECT is_current FROM calculations WHERE calc_id='T-001'").fetchone()[0]==0
 out['declared_edition']=conn.execute('SELECT code_edition FROM projects WHERE project_id=1').fetchone()[0]
 out['adoption_status']=get_basis(conn,1)['basis_status']
except ModuleNotFoundError:
 out['declared_edition']=conn.execute('SELECT code_edition FROM projects WHERE project_id=1').fetchone()[0]
 out['adoption_status']='ABSENT'
print(json.dumps(out,allow_nan=False))
conn.close()
'''


def probe(root):
    root = Path(root).resolve()
    if not (root/'database/db.py').is_file():
        raise ValueError(f'Not an engine source root: {root}')
    run = subprocess.run([sys.executable,'-c',PROBE],cwd=root,capture_output=True,text=True,timeout=60)
    if run.returncode:
        raise RuntimeError(run.stderr)
    return json.loads(run.stdout)


def compare(old_root,new_root):
    old,new = probe(old_root),probe(new_root)
    return {'baseline':'Original v0.6.2 / source commit 397e8d9f9b8031c6ce31a69aae64c4accaa75a23',
            'updated':'Phase 2 code governance; preceding Phase 1 commit a5cb857837413a2dff6ae8cea2e6b91af64a9b81',
            'method':'Identical synthetic inputs; separate processes; in-memory databases; no workbook values',
            'cases':[{'case':key,'old':old[key],'updated':new[key],'changed':old[key]!=new[key]} for key in old],
            'engineering_limit':'The rain identity must be 1 L/s. Both versions return 10 L/s: AUD-001 remains unresolved.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root',type=Path,required=True)
    parser.add_argument('--new-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=json.dumps(compare(args.old_root,args.new_root),indent=2)
    if args.output:
        args.output.write_text(report+'\n',encoding='utf-8')
    print(report)
