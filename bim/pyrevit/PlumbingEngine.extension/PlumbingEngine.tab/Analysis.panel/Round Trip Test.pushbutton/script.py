#! python3
# -*- coding: utf-8 -*-
"""Execute the actual extract/analyze/write/re-extract harness on a disposable model."""
import json
from pyrevit import revit,DB,forms,script
import plm_config
from bim.round_trip import run_in_revit


def main():
    if not forms.alert('Use a disposable test model copy. This command imports a fresh extraction and saves linked calculation records in the selected engine project. Continue?',yes=True,no=True):return
    path=forms.pick_file(file_ext='json',title='Select the reviewed extraction/mapping snapshot from Revit Exchange')
    if not path:return
    conn=None
    try:
        with open(path,'r',encoding='utf-8-sig') as source:reviewed=json.load(source)
        conn=plm_config.get_engine_db_connection()
        projects=conn.execute('SELECT project_id,project_name FROM projects ORDER BY project_id').fetchall()
        choices={'#{} — {}'.format(p['project_id'],p['project_name']):p['project_id'] for p in projects}
        chosen=forms.SelectFromList.show(sorted(choices),title='Choose the existing engine test project')
        if not chosen:return
        limit=forms.ask_for_string(prompt='Reviewed water velocity criterion, m/s (positive finite number)',title='Harness criterion')
        reference=forms.ask_for_string(prompt='Criterion document, revision and clause / project evidence',title='Harness source reference')
        if limit is None or reference is None:return
        output=forms.save_file(file_ext='json',default_name='plm-native-round-trip.json')
        if not output:return
        choice=forms.CommandSwitchWindow.show(['Dry run (roll back)','Commit result fields and verify'],message='Default testing rolls back. Commit writes PLM result fields only.')
        if choice is None:return
        commit=choice=='Commit result fields and verify'
        if commit and not forms.alert('Commit the mapped test pipe results to this disposable model copy and re-extract for verification? Engineering acceptance remains pending.',yes=True,no=True):return
        record=run_in_revit(revit.doc,DB,conn,choices[chosen],reviewed,plm_config.classify_system,float(limit),reference,commit=commit)
        with open(output,'w',encoding='utf-8') as target:json.dump(record,target,indent=2,allow_nan=False)
        script.get_output().print_md('Write: {}. Re-extraction comparison: {}. Upload the record in Revit Exchange for independent comparison. This command does not save the RVT file or approve the design.'.format(record['write']['status'],record['verification']['status']))
    except Exception as error:forms.alert('Round trip stopped: '+str(error))
    finally:
        if conn is not None:conn.close()


main()
