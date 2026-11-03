# -*- coding: utf-8 -*-
"""Reuse process CPython without resetting PythonDLL on each command invocation.

This IronPython entry point executes the native suite in CPython, on the Revit
API thread under the GIL. It never shuts down the shared Python.NET runtime.
"""
import os
import traceback
import clr
from pyrevit import script

bundle = os.path.dirname(__file__)
repo = os.path.abspath(os.path.join(bundle, '..', '..', '..', '..', '..', '..'))
workspace = os.environ.get('PLM_EVIDENCE_WORKSPACE', repo)
candidate = repo
while not os.environ.get('PLM_EVIDENCE_WORKSPACE'):
    if os.path.isdir(os.path.join(candidate, '.venv')):
        workspace = candidate
        break
    parent = os.path.dirname(candidate)
    if parent == candidate:break
    candidate = parent
review_dir = os.path.join(workspace, '.review')
if not os.path.isdir(review_dir):os.makedirs(review_dir)
bridge_log = os.path.join(workspace, '.review', 'native-evidence-bridge.log')
engine_dir = os.environ.get('PLM_CPYTHON_HOME') or os.path.join(os.environ['APPDATA'], 'pyRevit-Master', 'bin', 'cengines', 'CPY3123')
try:
    clr.AddReference('pyRevitLabs.PythonNet')
    from Python.Runtime import PythonEngine, Py, Runtime
    with open(bridge_log, 'w') as target:
        target.write('Native evidence bridge; initialized={0}; dll={1}\n'.format(PythonEngine.IsInitialized,Runtime.PythonDLL))
    if not PythonEngine.IsInitialized:
        # A pyRevit reload can clear PythonEngine.IsInitialized while the native
        # runtime still owns its DLL. Never reset an already configured DLL.
        if not Runtime.PythonDLL:
            Runtime.PythonDLL = os.path.join(engine_dir, 'python312.dll')
            PythonEngine.PythonHome = engine_dir
        PythonEngine.Initialize()
    gil = Py.GIL()
    scope = None
    try:
        scope = Py.CreateScope('plm_native_evidence_run')
        runner = os.path.join(bundle, 'native_runner.py')
        scope.Set('__file__', runner)
        scope.Set('native_uiapp', __revit__)
        scope.Set('native_workspace',workspace)
        scope.Set('native_engine_dir',engine_dir)
        scope.Set('native_source_copy',globals().get('PLM_SOURCE_COPY',os.environ.get('PLM_SOURCE_COPY',os.path.join(workspace,'.review','test-models','native-source.rvt'))))
        scope.Set('native_controlled_host_copy',globals().get('PLM_ISOLATED_HOST_COPY',False))
        scope.Set('native_performance_source',globals().get('PLM_PERFORMANCE_SOURCE',None))
        with open(runner, 'r') as source:
            code = source.read()
        scope.Exec(code)
    finally:
        if scope is not None:scope.Dispose()
        gil.Dispose()
    script.get_output().print_md('Native evidence run finished. See the private `.review/native-evidence` folder and `suite.json` for measured results.')
except Exception:
    with open(bridge_log, 'a') as target:target.write(traceback.format_exc())
    raise
