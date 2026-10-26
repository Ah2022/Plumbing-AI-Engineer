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
    next(s for s in at.selectbox if s.label=='Code profile').set_value('SBC701-2024')
    text(at,'Recorded by','Synthetic reviewer')
    next(b for b in at.button if b.label=='Save draft code basis').click().run(timeout=30)
    assert not at.exception
    row=at.session_state['conn'].execute('SELECT profile_id,revision FROM project_code_basis').fetchone()
    assert tuple(row)==('SBC701-2024',2)
    assert 'fixture_list' not in at.session_state
