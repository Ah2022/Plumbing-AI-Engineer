# Review evidence and release workflow

Implemented 27 October 2026, engine version `0.6.2-review-release-1`. This document describes the delivered software and its acceptance limits; it does not approve a code package or a project.

## Report / Export

1. Select the project and review its Code Profiles basis. Recalculate after changing code, basis, source model or engine/runtime. Earlier records remain available as history.
2. Open **Report / Export**. Read current/historical counts and unresolved review issues. Markdown reports include full inputs, intermediate values, references, governance information and captured engine/input fingerprints. Current summaries exclude superseded results.
3. Click **Build reproducible review packet**, then download JSON. The packet captures calculation evidence, applicable rules and design tables, user-imported interactive calculation packages, review proposals and runtime information. It can contain private project and licensed source data: distribute it only to intended reviewers. The app does not publish it to GitHub.
4. Use **Save and compare review revisions** to record a label and reviewer. Saved packets remain unchanged; comparison identifies changed basis, calculations and proposal counts. Download any saved revision.
5. Under **Reproduce a saved calculation or record an override proposal**, select a calculation. Replay supports heater capacity, domestic tank sizing, pump duty, rational stormwater flow and hourly hot-water demand. It checks recorded inputs, engine and current basis before reproducing. Other methods explicitly report unsupported replay. Legacy calculations without captured provenance cannot establish their historical execution environment.
6. Record a proposed result/required/selected value with its unit, reviewer, reason and evidence. This preserves the original calculation and remains `REVIEW_REQUIRED`. It does not silently approve or replace the computed result. Outstanding proposals block affected Revit handoffs.

An exported packet checksum detects content changes; it is not a digital signature or proof of engineering approval. Packet verification is read-only. There is no automatic packet execution or database restoration. Original files, local-only workbook packages and the matching engine remain necessary for methods outside the supported replay set.

## Release Readiness

Click **Run remaining-system benchmarks**. Nine fixed-expectation cases cover heater heat balance, domestic storage, pump power, rational runoff, synthetic hourly demand and storage, and synthetic rainfall/leader/storm sizing. Each displays expected and actual values with tolerances. The runner uses an isolated in-memory database and does not add calculations to the active project.

The checks also guard finite temperatures, appropriate hot-water storage source types, unrounded pump head in power calculations, and fractional storm-table lookups. Synthetic table cases verify lookup behavior; they do not validate the edition, adoption or numeric contents of a design code. Software PASS therefore retains engineering review requirements. Project readiness lists outstanding evidence separately. Live Revit writeback remains `NOT_VALIDATED`.

## Revit Exchange

1. Install the repository's `bim/pyrevit/PlumbingEngine.extension` into a compatible pyRevit environment with its Python 3 engine. Set `PLUMBING_ENGINE_REPO_PATH` if the extension is copied outside the checkout. Revit-specific deployment is still subject to live validation.
2. Run **Extract Data**. Choose the entire model or current selection. Extraction reads source data; it does not modify the model. Output includes model/element UniqueIds, explicit SI units, available source pipe geometry and connector identities, extract scope and skipped items. Unmapped system classifications are listed rather than guessed. Optional equipment requires explicit `PLM_Equipment_Class` (`tank` or `pump`); tanks also require `PLM_Tank_Type`.
3. In the engine's **Revit Exchange**, upload and review the extract before confirming import. Import invalidates affected project calculations conservatively. Use synthetic preview only for a demonstration project. Legacy extracts can be imported, but missing stable identities block guarded handoffs.
4. Calculate linked water velocity using reviewed internal bore and flow, or a drainage minimum-slope check using reviewed slope and the active code's available table. Nominal diameter is not substituted for internal bore. Current matching tank/pump calculations can be attributed to imported equipment with reviewer/applicability evidence, creating a linked copy.
5. Review the exact handoff values and blockers; download the handoff JSON. Source fingerprints and original calculations remain available. The governing failed check supplies both the failure status and its corresponding values.
6. In pyRevit **Review Results**, select the handoff. Preview is the first choice. **Dry run (roll back)** validates and attempts all writes within a transaction before rolling back. **Commit PLM result fields** additionally requires an explicit confirmation. A missing binding, wrong model/element/type, changed source geometry/connectors, invalid storage type or failed parameter write blocks or rolls back the operation.

Bind all 13 result parameters from `bim/revit/PLM_shared_parameters.txt` as writable **instance** parameters for the intended categories. Numeric result fields use dimensionless **Number** plus `PLM_Result_Unit`; they must not use a native Length/Flow specification. Availability flags distinguish a real zero from an absent result. The two equipment-classification text parameters are optional for pipe-only use.

Only the named PLM result parameters are written. The workflow does not resize pipes, change geometry, create missing shared parameters, perform full connected-network analysis or grant code approval. `PLM_Technical_Status`, `PLM_Review_Status` and `PLM_Code_Status` remain distinct. Source/identity checks do not detect every possible project edit; re-extract and recalculate after design changes.

## Validation and acceptance limits

Automated coverage includes packet/revision integrity, input and engine changes, legacy records, review proposals, current-result QAQC, numerical benchmarks, Streamlit workflows and simulated Revit transactions (default rollback, explicit commit, partial-failure rollback and identity/type/parameter rejection). CI runs the public synthetic tests on Windows and Linux without private workbooks.

Local verification: **384 tests passed**, including **22 new review/release/Revit tests** and navigation through all 17 pages. All **nine remaining-system software benchmarks passed**. Private numeric workbooks were available for the full local suite; the public CI test selection separately excludes calculations requiring those files.

A read-only connector sample of three pipes from an available live Revit model was inspected. Required PLM fields were missing on the sampled elements; a later property probe timed out. This does not witness the new pyRevit extractor or any live rollback/commit. Real-model acceptance still requires a controlled test model with the parameter bindings, extraction review, witnessed rollback, and explicitly authorized commit/readback. No live model was modified during implementation. IPC 2024 engineering verification and project adoption remain pending; software benchmark success does not change those statuses.
