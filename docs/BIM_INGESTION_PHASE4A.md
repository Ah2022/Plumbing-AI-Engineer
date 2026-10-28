# IFC / Revit ingestion and round-trip testing

Phase 4A adds explicit mapping and source-connector diagnostics before further DWG automation. The engine remains the calculation/provenance layer; the Revit commands read model facts and write only the existing PLM result parameters.

## Scope and validation status

Implemented software scope:

| Area | Supported scope | Explicit limits |
| --- | --- | --- |
| Mapping | Stable source object, source system, mapped system/service, nominal diameter, actual bore, design flow, reviewed elevation, drainage inverts, orientation, physical connectivity basis, per-object engineering reviewer and evidence | Source values are shown separately; nominal diameter never supplies internal bore. Engineering acceptance is not inferred from a typed reviewer name. |
| Connectivity | Components per reviewed system/service, open/unresolved ports, repeated object/port IDs, conflicting declared flow direction, missing reviewed elevations, adverse/inconsistent straight drainage grades, fixture water/drainage paths | No geometric proximity joins. Partition/excluded objects can cause unresolved evidence. Components and open ends are warnings requiring interpretation, not automatic code failures. |
| Revit extraction | Pipe, fitting, fixture family/type, explicitly classified tank/pump/valve, physical piping ports, source endpoints, native bore/flow where available, model revision metadata and PLM values | Non-piping domains, linked models, fabrication parts and hydraulic curves/ratings inside vendor families are not comprehensively extracted. Unknown piping equipment is reported; family-name matching never classifies it. |
| IFC extraction | Existing project-unit and supported polyline-axis extraction, sanitary terminal/pump/tank plus valve classification, property-set and port evidence | Unsupported body geometry stays unevaluated. Property-set values require manual engineering mapping. |
| Revisions | Immutable local extraction/mapping/diagnostics snapshots; stable-ID additions/removals/source field changes; connection/mapping/boundary comparison; separate PLM result changes | Uploaded checksums establish integrity, not third-party signature authenticity. A changed ElementId or UniqueId is a change, not silently relinked. |
| Native round trip | Extract → normal engine import API → reviewed water-pipe velocity check → guarded native PLM write → fresh extraction → identity/source/result comparison | Initial harness analysis is **water-pipe velocity against a supplied criterion**. It does not certify pressure networks, drainage, fixture loads, pump duty or code compliance. Existing equipment calculations may still be attributed through Revit Exchange. |

Validation is split into synthetic software/API contracts and an opt-in real Revit run. The native acceptance criterion remains **PENDING** until a disposable real plumbing model completes a committed run and its re-extraction comparison passes. A dry run returns `NOT_EXECUTED` for round-trip verification. CI skips the real-model test when no execution record is supplied; that skip is never a real-model pass. Every calculation retains `REVIEW_REQUIRED`; code compliance remains unevaluated.

The designated local test target is a disposable SMC3 model copy. The RVT file, actual source extracts, snapshots, native execution records and project database are private test evidence and must not be committed. At implementation time the Revit bridge was unavailable and the native window could not be captured after recovery. No live-model acceptance is claimed.

## Map and diagnose an IFC or Revit extraction

1. Open the engine project. For IFC, use **CAD / IFC Checks**, upload and inspect the file. For Revit, run **Extract Data** in pyRevit and preview its JSON under **Revit Exchange**.
2. In **BIM mapping, connectivity and revisions**, inspect the extracted source facts, units, family/type identities and physical port IDs. The source inventory is read-only.
3. Fill in the mapping table. Enter the mapped system and service, nominal diameter, actual bore, design flow and reviewed elevation. Each included row needs its engineering reviewer and evidence reference. Source nominal/bore/flow values remain visible in the source table for review; nothing is silently promoted.
4. For gravity pipes, enter source-axis start/end invert levels and confirm upstream-to-downstream direction. Vertical, curved and multi-segment slope analysis remains unevaluated. If using upstream/downstream port IDs, choose two distinct ports owned by that object. IFC source/sink and Revit in/out declarations are checked against the reviewed orientation.
5. For fixtures, explicitly review whether water and/or drainage are required. Paths may traverse extracted fittings/valves, but cannot jump through another fixture. A missing demonstrated path is a warning with partition/mapping limitations.
6. In **Review intentional terminals and open ends**, mark actual inlet/outlet/terminal boundaries with reviewer and evidence. Ordinary unresolved ends stay visible.
7. Run connectivity diagnostics. Correct identity errors before calculation. Missing data, skipped objects and unevaluated checks remain explicit. Editing mappings hides stale diagnostics.
8. Enter snapshot reviewer and evidence/revision; download or save the immutable snapshot. Restore requires the exact same extraction fingerprint. For a new revision, upload an earlier snapshot in the comparison control, review changes, then remap and recalculate. Result-parameter changes are reported separately and do not alone imply a source-model recalculation.

## Run the real Revit harness

Prerequisites: a disposable plumbing project model, Revit with pyRevit **CPython3**, this repository's `bim/pyrevit/PlumbingEngine.extension`, an existing engine test project, and correctly bound `PLM_*` parameters. Use `bim/revit/PLM_shared_parameters.txt`; numerical result fields must be dimensionless **Number**, availability fields Integer/Yes-No, and text fields String. The command does not create model geometry or bypass read-only parameter bindings.

Set `PLUMBING_ENGINE_REPO_PATH` to the repository root and `PLUMBING_ENGINE_DB_PATH` to the existing engine database before launching Revit. Restart/reload pyRevit after installing/updating the extension through its normal extension workflow. The extension adds **Extract Data**, the existing result handoff command and **Round Trip Test** to its Analysis panel.

1. Open the disposable model copy, not the production model. Keep its path stable across extraction/review/write-back; the path is part of local model identity. For workshared models, detach/open the copy through the appropriate Revit workflow; copying an RVT is not evidence of detachment.
2. Use **Extract Data**, choosing the full model or an explicit selected partition. Mark equipment using `PLM_Equipment_Class` values `tank`, `pump`, `valve`; tanks may also supply `PLM_Tank_Type`. Confirm all skipped/unsupported objects. Entire-model and selected extracts are explicitly distinguished.
3. Preview the extract in the engine. Complete mapping/review and download its reviewed extraction snapshot. Include at least one explicitly classified cold/hot water pipe, actual bore, nonnegative design flow and a named engineering reviewer/evidence. Snapshot missing-data diagnostics do not become approval.
4. Run **Round Trip Test** in Revit. Select the reviewed snapshot, existing engine test project, positive water velocity criterion and its source reference. Choose the output execution-record path. The command re-extracts and refuses stale mappings or changed source identity/geometry/connectivity. Service conflicts must be resolved before linked analysis.
5. Start with **Dry run (roll back)**. The same normal import/save APIs as the app create calculation/provenance records; the native write rolls back. Resolve missing/wrongly typed PLM bindings and any source-state errors. No manual SQL edits are part of the workflow.
6. Choose **Commit result fields and verify** on the disposable model when ready. The command runs preflight again inside the transaction, writes PLM values, re-extracts, and compares all stable identities, source geometry/equipment/port facts and every targeted PLM value/status/availability flag. It also detects unintended PLM changes on non-target objects. Source-geometry changes block preflight. Any parameter-write failure rolls the transaction back.
7. Upload the native execution record in **Revit Exchange → Revit round-trip evidence**. The engine independently re-runs the comparison. A typed/external `PASS` status is not trusted. Uploaded execution metadata is recorded as supplied and cannot authenticate a host execution or grant engineering approval.

The harness does not save the RVT file. A successful committed write followed by a failed comparison is reported as a failed verification; review the test model and Revit undo before any further use. Engine records are retained for audit. A transaction dry run does not undo engine import/calculation records.

Independently compare a native record:

```powershell
python -m tools.bim_round_trip path/to/plm-native-round-trip.json --output path/to/comparison.json
$env:PLUMBING_REAL_REVIT_RUN = 'path/to/plm-native-round-trip.json'
python -m pytest tests/test_revit_real_model.py -q
```

Do not publish private model evidence to run CI. Use locally retained records with model/reviewer authorization. Independent engineering review is a separate acceptance process.

## References

- [Autodesk: MEP connectors and physical connection traversal](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-API/files/Revit_API_Developers_Guide/Discipline_Specific_Functionality/MEP_Engineering/Revit_API_Revit_API_Developers_Guide_Discipline_Specific_Functionality_MEP_Engineering_Connectors_html.html) — extraction uses physical piping connectors and `IsConnectedTo`, not arbitrary `AllRefs` entries.
- [Autodesk: UnitUtils and internal-unit conversion](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/128dd879-fea8-5d7b-1eb2-d64f87753990.htm) — source dimensions and native flow are converted explicitly to SI.
- [Autodesk: DocumentVersion](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/3574fa56-016e-b146-1499-b3b1c9129705.htm) — version GUID/save count are revision evidence, not stable model identity; actual extracted facts are compared separately.

These API references describe integration mechanisms, not plumbing-code validation or certification.
