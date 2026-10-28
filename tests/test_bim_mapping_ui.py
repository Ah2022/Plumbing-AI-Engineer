"""Real Streamlit mapping actions, using disposable databases and synthetic extracts."""
from tests.test_streamlit_app import fresh_app,_create_project


def open_mapping(at):
    at=_create_project(at);at.sidebar.radio[0].set_value('Revit Exchange').run(timeout=30)
    next(b for b in at.button if b.label=='Preview synthetic Revit extract').click().run(timeout=30)
    assert not at.exception
    return at


def test_scope_then_diagnostics_and_attributed_snapshot(fresh_app):
    at=open_mapping(fresh_app)
    assert any('real-model round-trip acceptance pending' in c.value for c in at.caption)
    next(b for b in at.button if b.label=='Run connectivity diagnostics').click().run(timeout=30)
    assert not at.exception and not at.error
    assert not any(b.label=='Save immutable extraction snapshot' for b in at.button)
    next(t for t in at.text_input if t.label=='Snapshot engineering reviewer').set_value('Synthetic reviewer')
    next(t for t in at.text_input if t.label=='Snapshot evidence reference / revision').set_value('Synthetic R1').run(timeout=30)
    next(b for b in at.button if b.label=='Save immutable extraction snapshot').click().run(timeout=30)
    assert not at.exception and not at.error
    conn=at.session_state['conn']
    assert conn.execute('SELECT count(*) FROM bim_extraction_snapshots').fetchone()[0]==1
    assert conn.execute('SELECT count(*) FROM calculations').fetchone()[0]==0


def test_mapping_edit_hides_previous_diagnostics(fresh_app):
    at=open_mapping(fresh_app)
    next(b for b in at.button if b.label=='Run connectivity diagnostics').click().run(timeout=30)
    assert any(b.label=='Download connectivity diagnostics' for b in at.get('download_button'))
    editor=next(k for k in at.session_state if k.endswith('_object_map'))
    at.session_state[editor]={'edited_rows':{0:{'service':'cold_water','internal_mm':20.}},'added_rows':[],'deleted_rows':[]}
    at.run(timeout=30)
    assert not at.exception
    assert not any(b.label=='Download connectivity diagnostics' for b in at.get('download_button'))
