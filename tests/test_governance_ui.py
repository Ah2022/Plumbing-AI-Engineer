"""Headless acceptance of the new code-profile workflow."""
from tests.test_streamlit_app import fresh_app


def create_ipc(at):
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    assert not at.exception
    return at


def text(at,label,value):
    next(t for t in at.text_input if t.label==label).set_value(value)


def test_default_project_declares_ipc_2024_as_draft(fresh_app):
    at=create_ipc(fresh_app)
    row=at.session_state['conn'].execute('SELECT * FROM project_code_basis').fetchone()
    assert row['profile_id']=='IPC-2024' and row['basis_status']=='DRAFT'


def test_code_profile_page_displays_coverage_and_pending_review(fresh_app):
    at=create_ipc(fresh_app)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    assert not at.exception
    assert any(len(d.value)==9 for d in at.dataframe)
    assert any('unverified' in c.value.lower() for c in at.caption)


def test_blank_adoption_review_is_rejected(fresh_app):
    at=create_ipc(fresh_app)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    next(b for b in at.button if b.label=='Approve project adoption').click().run(timeout=30)
    assert not at.exception
    assert at.error
    assert at.session_state['conn'].execute('SELECT basis_status FROM project_code_basis').fetchone()[0]=='DRAFT'


def test_profile_switch_clears_cached_fixture_inputs(fresh_app):
    at=create_ipc(fresh_app)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    at.session_state['fixture_list']=[{'fixture_name':'Synthetic','wsfu_value':1}]
    next(s for s in at.selectbox if s.label=='Code profile').set_value('SBC701-2024').run(timeout=30)
    text(at,'Recorded by','Synthetic reviewer')
    next(b for b in at.button if b.label=='Save draft code basis').click().run(timeout=30)
    assert not at.exception
    row=at.session_state['conn'].execute('SELECT profile_id,revision FROM project_code_basis').fetchone()
    assert tuple(row)==('SBC701-2024',2)
    assert 'fixture_list' not in at.session_state


def test_profile_status_has_readable_summary_without_raw_json(fresh_app):
    at=create_ipc(fresh_app)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    assert not at.get('json')
    assert any(m.label=='Code profile' and m.value=='IPC-2024' for m in at.metric)
    assert any('Draft' in c.value for c in at.caption)
    assert any('complete and save' in w.value.lower() for w in at.warning)


def test_adoption_approval_and_later_edit_update_status_and_revision(fresh_app):
    at=create_ipc(fresh_app)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    for label,value in [('Jurisdiction / project location','Synthetic location'),('Adopting authority','Synthetic authority'),
                         ('Occupancy / supported use','Office'),('Recorded by','Synthetic engineer')]:text(at,label,value)
    for label,value in [('Local amendments (state none explicitly if confirmed)','None for synthetic case'),
                         ('Selected methods and references','Synthetic pressure and DFU benchmarks'),
                         ('Exclusions / unsupported arrangements','Loops excluded'),
                         ('Requirement precedence / conflict resolution','Synthetic reviewed precedence')]:
        next(t for t in at.text_area if t.label==label).set_value(value)
    next(m for m in at.multiselect if m.label=='Systems in scope').set_value(['water','drainage'])
    next(b for b in at.button if b.label=='Save draft code basis').click().run(timeout=30)
    assert not at.exception
    text(at,'Adoption reviewer','Synthetic reviewer')
    next(t for t in at.text_area if t.label=='Project adoption evidence / approved design-basis reference').set_value('Synthetic reviewed adoption record')
    next(c for c in at.checkbox if c.label=='I reviewed the project adoption and design-basis criteria').check()
    next(b for b in at.button if b.label=='Approve project adoption').click().run(timeout=30)
    row=at.session_state['conn'].execute('SELECT basis_status,revision FROM project_code_basis').fetchone()
    assert tuple(row)==('APPROVED',2) and not at.exception
    assert any('Project adoption recorded' in c.value for c in at.caption)
    assert any('Engineering review is pending' in i.value for i in at.info)
    text(at,'Jurisdiction / project location','Changed synthetic location')
    text(at,'Recorded by','Synthetic engineer')
    next(b for b in at.button if b.label=='Save draft code basis').click().run(timeout=30)
    row=at.session_state['conn'].execute('SELECT basis_status,revision,reviewer FROM project_code_basis').fetchone()
    assert tuple(row)==('DRAFT',3,None) and not at.exception


def test_code_basis_form_state_does_not_leak_to_another_project(fresh_app):
    from compliance.governance import set_basis
    at=create_ipc(fresh_app);at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    text(at,'Jurisdiction / project location','First project draft location')
    conn=at.session_state['conn']
    conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (2,'Other synthetic project','Office','IPC')")
    conn.commit();set_basis(conn,2,'IPC-2024',{'systems':['water'],'units':'SI'},'Synthetic engineer')
    at.session_state['project_id']=2;at.run(timeout=30)
    assert not at.exception
    assert next(t for t in at.text_input if t.label=='Jurisdiction / project location').value==''
