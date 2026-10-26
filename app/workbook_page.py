"""Review supplied reference methods without silently adopting them as code."""
import json
from pathlib import Path
import streamlit as st

from app.db_helpers import next_calc_id,save_calculation
from models import CalculationResult
from workbooks.library import catalog,source_path,load_source,run_scenario


@st.cache_data(show_spinner=False,max_entries=3)
def cached_source(entry,mtime_ns,size):
    return load_source(entry)


def page_calculation_sheets():
    st.header('Calculation sheets')
    entries=catalog()['workbooks']
    if not entries:
        st.info('No reference workbooks registered. Import the supplied ZIPs with python -m workbooks.library.');return
    group=st.selectbox('System',sorted({str(Path(e['filename']).parent) for e in entries}))
    choices={e['workbook_id']:e for e in entries if str(Path(e['filename']).parent)==group}
    wid=st.selectbox('Workbook',list(choices),format_func=lambda k:Path(choices[k]['filename']).name)
    entry=choices[wid]
    st.write({'declared_primary_bases':entry['primary_bases'] or ['UNIDENTIFIED'],
              'all_reference_bases_including_auxiliary_sheets':entry['all_bases'],
              'verification':entry['verification_status'],'edition':entry['edition_status']})
    st.caption('References identify the workbook method. They do not establish its edition, correctness or adoption for the active project.')
    for warning in entry['warnings']:st.warning(warning)
    for note in entry.get('review_notes',[]):st.warning(note)
    with st.expander('Source references and file identity'):
        st.code(entry['sha256'],language=None)
        st.dataframe(entry['reference_evidence'],width='stretch',alt='Workbook reference text with worksheet and cell locations')
    p=source_path(entry)
    if not p.is_file():
        st.info('The original workbook is local-only and is not installed in this checkout. Import its ZIP to use its calculations.');return
    try:
        stat=p.stat();book=cached_source(entry,stat.st_mtime_ns,stat.st_size)
    except (ValueError,OSError) as e:st.error(str(e));return
    sheets=[s['name'] for s in entry['sheets'] if not s['auxiliary'] and s['state']=='visible' and s['cells']]
    if not sheets:st.info('No visible calculation worksheet is available.');return
    name=st.selectbox('Worksheet',sheets)
    cells=book['sheets'][name]['cells']
    st.dataframe([dict(cell=addr,source_value=c['value'],formula=c['formula']) for addr,c in cells.items()],
                 width='stretch',alt='Selected worksheet source cells, saved values and formulas')
    st.caption('Source values are saved workbook values, not fresh results. Source units and source rounding are retained.')
    pid=st.session_state.get('project_id')
    if not pid:st.info('Create or open a project to recalculate and save a scenario.');return
    conn=st.session_state.conn
    code=conn.execute('SELECT code_id FROM projects WHERE project_id=?',(pid,)).fetchone()[0]
    st.caption('Active project code: '+code+'. Workbook methods remain separate from approved project code tables.')
    from compliance.governance import get_basis
    basis=get_basis(conn,pid);revision=basis['revision'] if basis else 0
    token=f'{pid}_{revision}_{wid}_{name}'
    if st.session_state.get('_workbook_token')!=token:
        st.session_state.pop('workbook_result',None);st.session_state['_workbook_token']=token
    formulas=[addr for addr,c in cells.items() if c['formula']]
    selected=st.multiselect('Output cells to recalculate',formulas,default=formulas[:5],key='wb_outputs_'+token)
    text=st.text_area('Input overrides as JSON',value='{}',key='wb_inputs_'+token,
                      help='Existing non-formula cells only. Example: {"Filter Sizing!Z10": 30}. Do not change reference tables to simulate project inputs.')
    if st.button('Recalculate selected cells'):
        try:
            def reject(v):raise ValueError('Non-finite JSON constant: '+v)
            overrides=json.loads(text,parse_constant=reject)
            if not isinstance(overrides,dict):raise ValueError('Input overrides must be an object')
            # Keep reference tables and other methods immutable in this project scenario.
            if any(not isinstance(k,str) or k.rsplit('!',1)[0].strip("'")!=name for k in overrides):
                raise ValueError('Overrides must belong to the selected calculation worksheet')
            report=run_scenario(book,[name+'!'+a for a in selected],overrides)
            report.update(workbook_id=wid,worksheet=name,declared_bases=entry['primary_bases'],source_warnings=entry['warnings'])
            result=CalculationResult(next_calc_id(conn,pid,'reference_workbook_scenario'),'reference_workbook_scenario',
                'Evaluate explicit supported source-cell formulas; preserve original units and rounding',
                {'source_sha256':entry['sha256'],'outputs':selected,'overrides':overrides},report,None,
                'Source worksheet units; see labels',status=report['technical_status'],
                reference=entry['filename']+' / '+name,notes='Reference method only; no code adoption or compliance approval.')
            save_calculation(conn,pid,result,target_type='reference_workbook',target_id=wid+'/'+name)
            report['calc_id']=result.calc_id;st.session_state['workbook_result']=report
        except (ValueError,TypeError,KeyError) as e:
            st.session_state.pop('workbook_result',None);st.error(str(e))
    report=st.session_state.get('workbook_result')
    if report:
        st.subheader('Last saved scenario')
        st.caption('Run again after changing inputs or outputs. Status: '+report['technical_status']+'; REVIEW_REQUIRED.')
        st.dataframe(report['results'],width='stretch',alt='Fresh selected-cell results and explicit unsupported or missing-data findings')
        st.download_button('Download workbook calculation trace',json.dumps(report,indent=2),file_name='workbook-scenario.json',mime='application/json')
