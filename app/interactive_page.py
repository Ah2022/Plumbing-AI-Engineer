"""Interactive calculation forms from portable packages, with in-app conversion."""
from pathlib import Path
import json,zipfile
import streamlit as st

from app.db_helpers import next_calc_id,save_calculation
from app.status_ui import project_status
from compliance.governance import context,get_basis
from models import CalculationResult
from workbooks.interactive import (LOCAL,decode_package,encode_package,import_bytes,install_project_packages,
                                   choices_for,run_package,bundle)
from workbooks.demo import demo_package
from workbooks.formulas import Evaluator,FormulaError


@st.cache_data(show_spinner=False,max_entries=64)
def read_package_file(path,mtime_ns,size):return decode_package(Path(path).read_bytes())


@st.cache_data(show_spinner=False,max_entries=64)
def read_package_json(text):return decode_package(text.encode('utf-8'))


@st.cache_data(show_spinner=False,max_entries=2)
def local_index(signature):
    records=[]
    for filename,mtime,size in signature:
        p=json.loads(Path(filename).read_text(encoding='utf-8'))
        records.append(dict(id=p['package_sha256'],title=p['title'],path=filename,mtime=mtime,size=size))
    return records


def page_calculation_sheets():
    st.header('Interactive calculation sheets')
    st.caption('Enter values in labelled fields, choose the calculation method and calculate. Excel is not required after conversion.')
    pid=st.session_state.get('project_id');conn=st.session_state.conn
    if pid:project_status(context(conn,pid))
    else:st.info('Create or open a project to import calculations and save results.')
    installed=any(LOCAL.glob('*.plmcalc')) or bool(pid and conn.execute('SELECT 1 FROM project_calculation_packages WHERE project_id=? LIMIT 1',(pid,)).fetchone())
    if not installed:st.info('Your calculation library is empty. Upload your Excel files or converted library ZIP below. The demonstration works immediately.')
    with st.expander('Add Excel sheets or an interactive library',expanded=not installed):
        st.caption('Upload XLSX/XLSM workbooks, a supplied ZIP, or a converted .plmcalc library. Conversion keeps formulas and data but removes the Excel/VBA runtime.')
        files=st.file_uploader('Calculation files',type=['xlsx','xlsm','plmcalc','zip'],accept_multiple_files=True,key=f'calculation_upload_{pid}')
        if st.button('Import and convert',disabled=not pid or not files):
            try:
                with st.spinner('Converting calculation sheets into interactive forms…'):
                    packages=[]
                    for file in files:
                        packages.extend(import_bytes(file.getvalue(),file.name))
                        if len(packages)>100:raise ValueError('Import at most 100 calculations per batch')
                    install_project_packages(conn,pid,packages)
                st.session_state[f'calculation_picker_{pid}']=packages[0]['package_sha256']
                st.session_state['_calculation_import_notice']=f'Imported {len(packages)} interactive calculations into this project.'
                st.rerun()
            except (ValueError,TypeError,KeyError,UnicodeError,zipfile.BadZipFile) as error:st.error('Import failed: '+str(error))
    if '_calculation_import_notice' in st.session_state:st.success(st.session_state.pop('_calculation_import_notice'))
    demo=demo_package();available={demo['package_sha256']:dict(id=demo['package_sha256'],title=demo['title'],demo=True)}
    signature=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(LOCAL.glob('*.plmcalc')))
    for record in local_index(signature):available[record['id']]=record
    if pid:
        for row in conn.execute('SELECT package_sha256,title FROM project_calculation_packages WHERE project_id=? ORDER BY title',(pid,)):
            available[row['package_sha256']]=dict(id=row['package_sha256'],title=row['title'],project=True)
    records=sorted(available.values(),key=lambda r:(r.get('demo',False),r['title'],r['id']))
    st.caption(f'{len(records)-1} imported or installed calculations, plus a synthetic demonstration.')
    ids=[r['id'] for r in records];pick_key=f'calculation_picker_{pid}'
    if st.session_state.get(pick_key) not in ids:st.session_state[pick_key]=ids[0]
    selected=st.selectbox('Calculation',ids,format_func=lambda k:available[k]['title'],key=pick_key)
    record=available[selected]
    try:
        if record.get('demo'):package=demo
        elif record.get('project'):
            text=conn.execute('SELECT package_json FROM project_calculation_packages WHERE project_id=? AND package_sha256=?',(pid,selected)).fetchone()[0]
            package=read_package_json(text)
        else:package=read_package_file(record['path'],record['mtime'],record['size'])
    except (ValueError,OSError,KeyError,TypeError) as error:st.error('Unable to open this calculation: '+str(error));return
    forms=package['forms']
    if not forms:st.warning('No labelled calculation form could be generated for this source.');return
    name=st.selectbox('Calculation method',list(forms))
    metadata=package.get('metadata',{})
    references=metadata.get('primary_bases',[]) or metadata.get('all_bases',[])
    st.caption('Calculation references: '+(', '.join(references) or 'Not identified in the source'))
    if record.get('demo'):st.info('Synthetic demonstration: flow × duration. This example is not a code requirement.')
    revision=(get_basis(conn,pid) or {}).get('revision',0) if pid else 0
    token=f'{pid}:{revision}:{selected}:{name}'
    draft_key='calculation_draft_'+token;draft=st.session_state.setdefault(draft_key,{})
    values=dict(draft);fields=forms[name]['inputs'];book=package['workbook']
    st.subheader('Design inputs')
    sections=list(dict.fromkeys(f['section'] for f in fields))
    for i,section in enumerate(sections):
        with st.expander(section,expanded=i<2):
            section_fields=[f for f in fields if f['section']==section]
            grid=[f for f in section_fields if f['kind']=='number' and not f['percent'] and not f.get('validation') and not f.get('label_cell')]
            grid_cells=set()
            if len(grid)>=16:
                grid_cells={f['cell'] for f in grid}
                rows=[{'Input':f['label'],'Value':values.get(f['cell'],book['sheets'][name]['cells'][f['cell']]['value'])} for f in grid]
                edited=st.data_editor(rows,key='calculation_grid_'+token+':'+section,disabled=['Input'],hide_index=True,
                                      column_config={'Value':st.column_config.NumberColumn('Value')},
                                      width='stretch',alt='Editable numeric design schedule with labelled inputs')
                for f,row in zip(grid,edited):values[f['cell']]=row['Value']
            for field in (f for f in section_fields if f['cell'] not in grid_cells):
                cell=field['cell'];original=book['sheets'][name]['cells'][cell]['value']
                current=values.get(cell,original);key='calculation_field_'+token+':'+cell
                choices=choices_for(book,name,field,{name+'!'+c:v for c,v in values.items()})
                help_text='Source field: '+cell
                label=field['label']
                if field.get('label_cell'):
                    try:
                        ev=Evaluator(book,{name+'!'+c:v for c,v in values.items()},max_overrides=500)
                        label=ev.cell(name,field['label_cell'])
                        if not label:
                            values.setdefault(cell,original);continue
                        label=str(label)
                    except FormulaError:label=field['label']
                if choices:
                    options=choices if current in choices else [current]+choices
                    value=st.selectbox(label,options,index=options.index(current),key=key,help=help_text,
                                       format_func=lambda v,percent=field['percent']:f'{v*100:g}%' if percent and isinstance(v,(int,float)) else 'Not supplied' if v is None else str(v))
                    if value not in choices:st.caption('This source value is outside the listed choices. Review this field before accepting the result.')
                elif field['kind']=='boolean':value=st.checkbox(label,value=bool(current),key=key,help=help_text)
                elif field['kind']=='number':
                    scale=100 if field['percent'] else 1
                    value=st.number_input(label,value=float(current)*scale if current is not None else None,key=key,help=help_text)
                    if value is not None:value/=scale
                else:value=st.text_input(label,value='' if current is None else str(current),key=key,help=help_text)
                values[cell]=value
    st.session_state[draft_key]=values
    if st.button('Calculate and save',disabled=not pid):
        try:
            report=run_package(package,name,values)
            report.update(project_id=pid,basis_revision=revision,title=package['title'])
            result=CalculationResult(next_calc_id(conn,pid,'reference_workbook_scenario'),'reference_workbook_scenario',
                'Interactive source formulas with declared inputs and original source units',
                {'package_sha256':selected,'worksheet':name,'values':values},report,None,'Source form units',
                status=report['technical_status'],reference=package['title']+' / '+name,
                notes='Interactive reference method; engineering applicability remains subject to project review.')
            save_calculation(conn,pid,result,target_type='reference_workbook',target_id=selected+'/'+name)
            report['calc_id']=result.calc_id;st.session_state['workbook_result']=dict(token=token,report=report)
        except (ValueError,TypeError,KeyError) as error:st.session_state.pop('workbook_result',None);st.error(str(error))
    saved=st.session_state.get('workbook_result')
    if saved and saved.get('token')==token:
        report=saved['report'];st.subheader('Calculated results')
        if report['inputs']!=values:st.warning('Inputs have changed. Calculate again to update these saved results.')
        st.caption('Saved calculation · '+report['calc_id']+'. Engineering acceptance remains pending.')
        labels={'CALCULATED_NOT_APPROVED':'Calculated · review pending','MISSING_DATA':'Missing or inconsistent source data','NOT_EVALUATED':'Unsupported calculation'}
        st.dataframe([{'Result':r['label'],'Value':format(r['value'],',.8g') if isinstance(r['value'],(int,float)) else str(r['value']) if r['value'] is not None else 'Unavailable',
                       'Status':labels[r['status']],'Details':r['reason']} for r in report['results']],
                     hide_index=True,width='stretch',alt='Labelled results in original source units with review and error explanations')
        st.download_button('Download calculation report',json.dumps(report,indent=2),file_name='calculation-report.json',mime='application/json')
    with st.expander('References, source issues and portable calculation'):
        for note in metadata.get('review_notes',[]):st.warning(note)
        for warning in metadata.get('warnings',[]):st.caption(warning)
        st.caption('Original file and package fingerprints are retained. Macros and external workbook links are not executed.')
        evidence=metadata.get('reference_evidence',[])
        if evidence:st.dataframe(evidence,hide_index=True,width='stretch',alt='Source reference labels with original worksheet locations')
        st.download_button('Download this interactive calculation',encode_package(package),file_name=package['title']+'.plmcalc',mime='application/json')
    with st.expander('Download a portable library'):
        if st.button('Prepare interactive library download'):
            packages=[]
            for r in records:
                if r.get('demo'):continue
                if r.get('project'):
                    text=conn.execute('SELECT package_json FROM project_calculation_packages WHERE project_id=? AND package_sha256=?',(pid,r['id'])).fetchone()[0]
                    packages.append(read_package_json(text))
                else:packages.append(read_package_file(r['path'],r['mtime'],r['size']))
            st.session_state['_interactive_bundle']=(pid,tuple(ids),bundle(packages))
        ready=st.session_state.get('_interactive_bundle')
        if ready and ready[:2]==(pid,tuple(ids)):st.download_button('Download interactive library ZIP',ready[2],file_name='Interactive_Calculation_Library.zip',mime='application/zip')
