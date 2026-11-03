#! python3
"""Run local native evidence collection; writes only a disposable detached model."""
import sys
# pyRevit's embedded engine can replace sys.path with bundle paths. Restore its
# installed standard library before even importing pathlib/traceback.
_cpy = str(native_engine_dir).replace('\\','/')
for _path in (_cpy, _cpy+'/python312.zip', _cpy+'/Lib', _cpy+'/Lib/site-packages'):
    if _path not in sys.path:sys.path.append(_path)
import traceback
from pathlib import Path

repo=Path(__file__).resolve().parents[6]
workspace=Path(native_workspace)
sys.path.insert(0,str(repo))
sys.path.append(str(workspace/'.venv/Lib/site-packages'))
log=workspace/'.review/native-evidence-launch.log'
try:
    log.write_text('CPython command launched. Python: '+sys.version+'\n',encoding='utf-8')
    import clr
    clr.AddReference('RevitAPI')
    import Autodesk.Revit.DB as DB
    # CPython engines may cache modules between button clicks. Each evidence run
    # must execute the source currently under test, including compatibility fixes.
    for name in tuple(sys.modules):
        if name.startswith('bim.') or name=='tools.revit_native_evidence':
            del sys.modules[name]
    from tools.revit_native_evidence import run
    result=run(native_uiapp,DB,native_source_copy,
               workspace/'.review/native-evidence',controlled_host_copy=native_controlled_host_copy,
               performance_source=native_performance_source)
    with log.open('a',encoding='utf-8') as target:target.write('Evidence: '+result+'\n')
except Exception:
    with log.open('a',encoding='utf-8') as target:target.write(traceback.format_exc())
    raise
