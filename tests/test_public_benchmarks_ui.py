import pytest
from tests.test_streamlit_app import fresh_app,_create_project


def open_public(at):
    at=_create_project(at);at.sidebar.radio[0].set_value('Release Readiness').run(timeout=30)
    assert not at.exception
    return at


def test_public_registry_is_visible_and_cannot_approve_engineering(fresh_app):
    at=open_public(fresh_app)
    assert any('do not approve a plumbing design' in str(w.value) for w in at.warning)
    assert any(b.label=='Download public benchmark catalogue' for b in at.get('download_button'))
    next(b for b in at.button if b.label=='Run public benchmark candidate').click().run(timeout=30)
    assert not at.exception and not at.error
    assert next(m for m in at.metric if m.label=='Public software comparison').value=='PASS'
    assert any('Approval eligible: false' in c.value for c in at.caption)
    assert at.session_state.conn.execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0


def test_registered_open_data_does_not_show_a_run_button(fresh_app):
    at=open_public(fresh_app)
    next(s for s in at.selectbox if s.label=='Public benchmark candidate').set_value('swmmcanada-graham-creek').run(timeout=30)
    assert not at.exception
    assert not any(b.label=='Run public benchmark candidate' for b in at.button)
    assert any('not installed' in str(info.value) for info in at.info)
