# Project workspace

The interface groups tools into six workspaces. **Overview** is the front door; choose an active project in the sidebar. Project IDs and code identifiers distinguish projects with the same name.

| Workspace | Use it for |
| --- | --- |
| Overview | Live readiness blockers, open/overdue issues, unresolved assumptions, current calculations, saved model health and guided next actions. |
| Project setup | Project identity, code profile, adoption, design criteria, team responsibilities and a reusable evidence register. |
| Models & networks | IFC/DXF/DWG/PDF intake, Revit exchange, object mapping, connectivity diagnostics, a centreline explorer and schematic network editing. |
| Calculations | Fixture schedules, water, drainage/vents, hot water, pumps, tanks, stormwater, scoped engineering modules and converted calculation sheets. |
| Review & approval | An integrated issue register, staged review routing, code checks, QA/QC and release/benchmark evidence. |
| Reports | Calculation reports, reproducible evidence packets and immutable review revisions. |

## A normal project session

1. Create/open the project, then confirm code edition and project adoption. Register the Designer, Checker, BIM coordinator and Approver in **Team & evidence**. Record document identifiers, revisions and sections once for reuse. Criteria templates provide names/units, never assumed engineering values.
2. Inspect model/drawing units and source coverage. In **CAD / IFC Checks**, choose **Explore model**, **Map & diagnose**, or **Design checks**. Revit has equivalent exploration and mapping tasks alongside exchange/calculation. The object explorer filters by system, name or source ID; use 3D, plan or elevation and select an object to inspect its facts.
3. Map explicit services, internal bores, demands, elevations and physical connections. Save reviewed extraction snapshots so model diagnostics appear on the project dashboard. An inspected session-only file is not a saved reviewed mapping. Revit imports without saved mapping are marked accordingly.
4. Use **Network Review → Graphical editor** to arrange nodes, select and edit objects, add nodes and connect/remove pipes. Enter measured lengths and engineering criteria explicitly. Use **Editable tables** for complete material/catalogue, slope and vent properties; use JSON only for advanced exchange. Run and save the affected checks.
5. Open **Issues** to assign findings with owner, priority, due date, status and location. Search/filter the register or create tasks directly from live source findings. Use an extracted source ID as the location to locate it in the model explorer. General level/location notes remain text and do not imply an inferred coordinate.
6. Use **Approval workflow** to record Design submission → Independent check → BIM coordination → Approval. Each stage requires its assigned role, a different named person, evidence and a scope note. Final approval is blocked by live source findings, unresolved tasks and missing independent engineering acceptance. Export the record or include it in a reproducible review packet.

## Review controls

Workflow steps are tied to a fingerprint of the current project, basis, source state, calculations, assumptions, compliance/QA results, saved mappings, imported models, team, evidence and issues. Changes leave earlier events visible as **Superseded** and restart routing. Submission/check/coordination may record reviews with outstanding findings; these steps do not assert an accepted design.

Issue creation and updates retain before/after records with the recording team member. A resolution needs an explanation. Resolving a task does **not** suppress its underlying source finding or change calculation/code statuses. Registers and histories are project-scoped and included in review-packet checksums. Existing projects and calculations are preserved by additive schema creation.

Team/evidence pickers are available in code-basis/adoption and model-mapping forms, with manual entry retained for references not yet registered. A reference locator is not source authentication; team role selection is not identity authentication or a qualified engineering signature.

## Visual scope and operating limits

- The local explorer displays **extracted start/end centrelines**, not tessellated BIM solids. Missing axes stay missing and objects remain accessible in the selector. A curved/polyline object is represented by its extracted endpoint chord, not every segment. The viewer does not infer missing geometry, invert levels or hydraulic connectivity. No model data is sent to a third-party renderer. Filter views exceeding 2,000 axes.
- Plan/elevation are projected geometry views, not registered overlays on an architectural drawing sheet. PDF review remains in the drawing-intake tool.
- The graph editor is a **schematic**, not Revit/CAD authoring. Dragged positions are saved in the network draft/JSON and are independent of measured pipe lengths and elevations. It supports up to 500 nodes/500 pipes; loops and hydraulic validity still require the appropriate solver and checks. Catalogue data and advanced properties remain explicit and are preserved across editing modes.
- Browser draft work is session-scoped. Export mapped JSON or save the calculated trace/snapshot to retain evidence. Earlier results are labelled as last submitted; graph property/topology edits clear the displayed result. Software PASS, workflow activity and engineering acceptance remain distinct.
- This remains a local Streamlit/SQLite engineering review application. It does not provide authenticated multi-user access, server-enforced role permissions, electronic signatures, live simultaneous model editing, BCF synchronization or an enterprise common data environment. Those require a separate authenticated service and deployment design. Review database errors offer recovery and a local support reference; parser-specific errors remain close to their input.

Tests cover project isolation, issue audit records, preserved live blockers after task closure, review ordering/identity separation, stale-review invalidation, geometry omissions, unchanged hydraulic values after visual layout edits and real UI actions. Software tests do not establish independent engineering approval.
