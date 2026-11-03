# Native Revit evidence

The **Plumbing Engine â†’ Analysis â†’ Native Evidence** command measures the actual Revit API adapter and guarded writer. Register `bim/pyrevit` as a pyRevit extension search directory. The IronPython launcher enters CPython 3.12 through Python.NET under the GIL, retaining an existing initialized runtime and restoring its standard-library path. It never shuts down the shared interpreter. If another extension has left Python.NET partially initialized, use a fresh isolated Revit process; repeated Reload is not a recovery procedure.

It reads all six supported host categories in explicit 5,000-element partitions, preserving each actual extraction and timing. It samples up to 100 eligible elements per loaded link and records link-instance identities and transforms without claiming federated connectivity. These timings are measured observations, not an agreed performance SLA or evidence across multiple building types.

The default button writes only in a separately opened, detached copy of `.review/test-models/native-source.rvt`. The command preserves worksharing, saves a new local controlled RVT, creates one disconnected test pipe, and binds the 13 result fields from the checked-in shared-parameter manifest. It validates exact shared GUIDs, instance/category bindings, storage and numerical specifications. The production host is neither saved nor synchronized.

For isolated batch execution, the launcher accepts `PLM_SOURCE_COPY`, `PLM_ISOLATED_HOST_COPY=True`, and optional `PLM_PERFORMANCE_SOURCE` globals. The caller must activate a disposable local source detached with worksets preserved before invoking the launcher. The runner rejects cloud hosts and checks the source path, including Revit's detached document name. This mode saves the active disposable host to the evidence directory and creates an actual linked RVT containing a copied native pipe. Two link instances, one translated 20 feet, exercise instance-qualified identities. When original project links are unloaded to limit memory use, their contents are not covered by this fixture.

A supplemental performance copy is opened, measured, and closed without saving. Large-model acceptance requires more than 10,000 extracted supported objects; without a supplemental model the host must satisfy that threshold. Partition counts, durations, and checksums are preserved. A large file or a high total native element count alone does not satisfy this criterion.

The native harness uses explicitly labeled software-test bore/flow/criterion inputs. It imports and calculates through the engine's normal APIs, writes and rolls back with a fresh comparison, then commits and independently re-extracts all target values. Geometry changes, deletion, copied/replacement identity and duplicate packet identities must block stale handoffs. Transaction-scoped geometry/deletion changes roll back before a final comparison and local save. This validates software behavior; the controlled numeric inputs are not reviewed production engineering data.

Each run writes incremental `suite.json`, host/link extracts, a disposable database, `dry-run.json`, `committed.json`, the final extract and `controlled.rvt` under the workspace's private `.review/native-evidence/<timestamp>`. A failed/interrupted run remains FAIL/INCOMPLETE/RUNNING, never acceptance. Keep private model evidence local.

Validate completed evidence from the repository root:

```powershell
$env:PLUMBING_REAL_REVIT_SUITE = 'C:\absolute\private\run\suite.json'
$env:PLUMBING_REAL_REVIT_RUN = 'C:\absolute\private\run\committed.json'
python -m pytest tests/test_revit_native_suite.py tests/test_revit_real_model.py -q
```

Missing evidence skips the opt-in tests. An uploaded JSON record cannot independently authenticate execution. Local API receipts and the saved test model supply execution context.

Remaining separate coverage: simultaneous multi-user contention, cloud synchronization, unloaded link contents, transformed federated port graphs, and additional hotel/mixed-use datasets. A single-user detached workshared run must not be described as covering those cases.

## Ribbon artwork

The four command bundles contain original SVG source plus transparent 96 px `icon.png` and `icon.dark.png` assets. The extension root contains the Plumbing Engine logo and `ribbon-icons-preview.png`. Rebuild them with `python -m tools.build_revit_icons` (Pillow required). Reload pyRevit after the native command has finished to refresh the ribbon artwork.

API basis: [Autodesk shared-parameter binding](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-API/files/Revit_API_Developers_Guide/Basic_Interaction_with_Revit_Elements/Parameters/Shared_Parameters/Revit_API_Revit_API_Developers_Guide_Basic_Interaction_with_Revit_Elements_Parameters_Shared_Parameters_Binding_html.html) and [opening workshared documents](https://help.autodesk.com/cloudhelp/2018/ENU/Revit-API/Revit_API_Developers_Guide/Advanced_Topics/Worksharing/Opening_a_Workshared_Document.html).

Launcher configuration: PLM_EVIDENCE_WORKSPACE selects the private working directory (otherwise the nearest ancestor with .venv, or the repository root). PLM_SOURCE_COPY selects a disposable RVT. PLM_CPYTHON_HOME overrides the embedded CPython directory, which otherwise defaults to the pyRevit-Master CPY3123 installation under the current user's APPDATA. The runner receives these paths from the launcher; no personal absolute path is embedded.
