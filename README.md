# Plumbing AI Engineer

Python/SQLite plumbing calculation engine with a Streamlit interface, code-rule checks, reports, and Revit JSON exchange.

**Phase 4A — BIM ingestion:** IFC and Revit now share explicit engineering mapping, physical-port connectivity diagnostics, attributed immutable snapshots and model-revision comparison. Revit extraction includes family/type evidence for fixtures and explicitly classified tanks, pumps and valves. A new pyRevit **Round Trip Test** command uses normal engine APIs to extract, calculate reviewed water-pipe velocity, write guarded PLM results and re-extract for identity/status verification. **Real-model acceptance is pending**; synthetic tests and rollback runs cannot mark the integration verified. [Mapping workflow, supported scope and native test procedure](docs/BIM_INGESTION_PHASE4A.md). [Test locally](http://localhost:8504/).

**BIM diagnostic correction:** when physical port inventories are missing, component coverage is explicitly `NOT_EVALUATED`; the engine does not infer disconnected components from unavailable topology. Regression coverage includes this case. Live readiness audits and a transaction rollback probe do not establish a completed extraction/write-back/re-extraction round trip.

**Phase 5 — missing engineering modules:** **Engineering Modules** now covers the twelve requested priorities with the existing pressure solver and thirteen new scoped tools: pump/system operating points, thermal recirculation/balancing, fixture minimums, partial-flow Manning drainage, trap/air-pressure budgets, supplied wet/circuit/AAV checks, backwater/overflow screens, level-pool storm storage, fire/domestic separation, manufacturer-catalogue candidate filtering, noise risk, simple surge and thermal/vessel expansion. Scope, required source data, software validation and unevaluated checks are shown before calculation. Thirty fixed candidate references and source/validation fingerprints gate exposure; outputs retain `REVIEW_REQUIRED` and code compliance `NOT_EVALUATED`. [Capabilities, formulas, sources, boundaries and usage](docs/PLUMBING_ENGINEERING_MODULES.md). [Test the updated local app](http://localhost:8504/).

**Phase 2 A — general hydraulic backend:** **Network Review → General pressure network** now supports loops, explicit pump H-Q curves, tanks, five valve types, simple controls, PDA and extended-period simulation through EPANET2.2. Seven scenario overlays and five equivalent-tree comparisons are included. The existing tree evaluator remains unchanged. General runs need a configured native toolkit and retain `REVIEW_REQUIRED` / code compliance `NOT_EVALUATED`. [Setup, units, routing, diagnostics and supported scope](docs/GENERAL_HYDRAULIC_SOLVER.md). [Test locally](http://localhost:8504/).

**Phase 1 A — engineering validation:** five frozen building-type reference candidates, independently prepared mathematical outputs, actual EPANET 2.2 comparisons, golden regression tests, a discrepancy register and a **BIM MANAGER** review package are available in **Release Readiness**. The package registers all 29 native calculation entry points and 103 converted forms. **Authoritative acceptance remains pending:** the cases are illustrative; independent engineer review, authenticated code/manufacturer data and independent references for the converted forms are still required. Synthetic PASS cannot label a release verified. [Review package and acceptance procedure](docs/ENGINEERING_VALIDATION.md).

**Phases 6–7 implementation: 27 October 2026.** **Report / Export** now includes complete evidence packets, immutable review revisions, comparison, supported calculation replay and attributed override proposals. **Release Readiness** runs nine isolated software benchmarks. **Revit Exchange** imports reviewed extracts, links supported checks and prepares guarded PLM-only result handoffs. [Usage, implemented scope and outstanding engineering/live-model acceptance](docs/REVIEW_AND_RELEASE.md). Live Revit writeback has not been validated; preview and rollback are the defaults.

**Phases 3–5: 26 October 2026.** Calculation foundations, domestic-water tree networks, and drainage/vent checks are implemented for the [documented supported scope](docs/PHASES_3_4_5.md). IPC 2024 is the first verification target. Code adoption, numeric-table verification and engineering acceptance remain pending; outputs retain `REVIEW_REQUIRED`.

## Test the engine

**[Open the updated calculation-sheet and network Streamlit app](http://localhost:8504)** — works on the computer running Streamlit. This is a local URL, not an internet deployment.

```bash
git clone https://github.com/Ah2022/Plumbing-AI-Engineer.git
cd Plumbing-AI-Engineer
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py --server.port 8504
```

The app initializes a database on first use. After each implementation, pull the latest `main` and refresh the page; restart if dependencies changed. Streamlit reloads saved source changes. Use synthetic review projects while audit findings remain open.

### Streamlit Community Cloud

**Public app URL: pending first deployment.** No verified `streamlit.app` URL is available yet.

[Open Streamlit Community Cloud to deploy](https://share.streamlit.io/), then select:

| Setting | Value |
| --- | --- |
| Repository | `Ah2022/Plumbing-AI-Engineer` |
| Branch | `main` |
| Main file | `app/streamlit_app.py` |
| Python | `3.12` |

Once deployed, add its actual URL here as the permanent test link. Community Cloud updates an app when its connected repository changes; see the [official deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

**Data availability:** the five numeric design workbooks are available locally but excluded from this public repository pending permission to publish them. A fresh clone/Cloud deployment can open the interface and run formula-only features; workbook-dependent sizing requires the original files in `database/code_design_data/`:

- `IPC_Plumbing_Design_Data.xlsx`
- `UPC_Plumbing_Design_Data.xlsx`
- `BS_EN_Plumbing_Design_Data.xlsx`
- `Egyptian_Plumbing_Design_Data.xlsx`
- `SBC701_Saudi_Plumbing_Design_Data.xlsx`

## CAD / IFC design-check pilot

Open **CAD / IFC Checks** in the [local app](http://localhost:8504/). Upload an IFC, DXF, DWG or PDF. IFC/DXF provide source geometry for reviewed engineering mappings. DWG accepts a confirmed companion DXF or a configured local converter; PDF offers page previews, extracted text and saved drawing-review notes. Bundled synthetic IFC and DXF examples are available on the page.

Install the optional parsers with `python -m pip install -r requirements-models.txt`, then restart Streamlit. The first pilot checks **water velocity** from actual internal bore and design flow, and **straight-segment drainage slope** from reviewed invert levels against the active code's available minimum-slope table. Source facts and reviewed engineering inputs remain separate. It does not infer connections from crossings, replace missing bore with DN, or replace invert levels with centreline Z.

Whole-network pressure, connected fixture loads, capacity, vents and unsupported geometry remain explicitly unevaluated. Findings retain **partial coverage** and **engineering review required**. DWG conversion readiness and PDF drawing review are described in the [DWG/PDF upload guide](docs/DWG_PDF_UPLOADS.md). See the [implemented scope, workflow, synthetic benchmarks and next milestones](docs/CAD_IFC_PILOT.md).

## Interactive calculation sheets

The supplied 48 workbooks are converted into **103 interactive forms**. Open **Calculation Sheets**, select the calculation/method, enter values in labelled fields or editable schedules, then **Calculate and save**. No cell-address JSON or Excel installation is needed to use a converted calculation.

For a deployed app or another computer, open **Add Excel sheets or an interactive library**, upload your converted library ZIP (or XLSX/XLSM files), and click **Import and convert**. Packages are stored with the active project in its database. A working synthetic demonstration is included in every checkout. Private calculation packages remain local or user-imported; they contain the supplied standards/catalogue data and are excluded from public Git.

See the [interactive workflow and profile fixes](docs/INTERACTIVE_CALCULATIONS.md), [all-form execution evidence](docs/INTERACTIVE_FORM_CHECK.json), and [source/code attribution](docs/CALCULATION_SHEETS_REVIEW.md). Code Profiles now uses readable status summaries, project-scoped forms and an explicit draft/adoption/revision workflow. Pending engineering verification is not silently converted into approval.

## Review workflow

1. Create a project; IPC 2024 is the default first verification target.
2. Open **Code Profiles** and record jurisdiction, adopting authority, amendments, occupancy, systems, units, methods, exclusions, and requirement precedence.
3. Save a draft. A named engineer can record adoption approval with project evidence; this does not verify the code package.
4. Review the per-profile coverage matrix and independent benchmark records. New rules start pending; unsupported checks remain explicit.
5. Recalculate after a profile/basis/source change. Reports and BIM export exclude or identify stale results and preserve review status.

6. Open **Network Review** and choose water or drainage/vents. A live **Rendered network** diagram shows mapped nodes, directed pipe connections, lengths and loads in both input modes. Raw JSON stays inside **Advanced JSON editor**. The preview is a connectivity schematic, not a scaled CAD drawing or a calculation/approval result; invalid JSON or unknown endpoints cannot display a stale diagram. Edit the node loads, pipe connections, elevations, criteria, materials and catalogue sizes directly in the tables. Replace synthetic example data with reviewed project data, then run and download the findings. **Mapped network JSON** mode supports upload, direct entry, and loading an imported model into the tables; advanced vent mappings are retained. Water supports explicit terminal flows or selected-code WSFU demand lookup; drainage capacity checks require the relevant workbook.
7. **Drainage & Vent** has a referenced fixture list with quantities, DFU subtotals, removal controls and a total that can drive pipe sizing. **Hot Water** has separate hot WSFU and hourly GPH fixture lists. Hot WSFU uses only an explicit hot-water column from the active code; the ASPE hospital GPH method remains separately identified. Missing source tables are shown as missing, without silently substituting another code. Lists are scoped to the project, code and design-basis revision.

The ten defect reproductions left after Phase 2 now pass. Numeric dataset editions and project applicability still require review. US customary/SI selection records the design basis; calculation forms and mapped network JSON retain explicitly labeled units.

For local comparison, retained [Phase 1](http://localhost:8501) and [Phase 2](http://localhost:8502) apps run separately from the [current build](http://localhost:8504). These services must be running on your computer.

## Verification

```bash
# Full suite; requires the five local workbooks
python -m pytest tests/ -q

# Public-checkout checks
python -m pytest tests/test_audit_benchmarks.py tests/test_bim_exchange.py tests/test_reports.py tests/test_runtime_safety.py tests/test_governance.py tests/test_governance_ui.py tests/test_foundations.py tests/test_networks.py tests/test_network_ui.py tests/test_network_preview.py tests/test_fixture_schedules.py tests/test_workbooks.py tests/test_workbook_ui.py tests/test_interactive_packages.py tests/test_model_intake.py tests/test_model_ui.py tests/test_drawing_uploads.py -q

# Inventory; uses an in-memory database and prints no workbook values
python -m tools.baseline_inventory

# End-to-end demo; uses its own temporary database
python -m tests.demo_project
```

The last full local suite passed **353 tests** with no expected failures. The rendered-network update additionally passed **55** network/preview regressions and all **15** page-navigation checks. The public model/drawing-upload suites passed **23 tests**, and all **15** page-navigation checks passed without private workbooks. All 103 converted forms were also exercised from portable packages; unsupported or missing source calculations remain explicit. The Phases 3–5 baseline passed **241 tests** on Windows/Python 3.12.14 with Streamlit 1.66.1. The workbook and interactive-package suites validate formula semantics, macro-free import, portable packages, labelled inputs, project isolation and profile approval/revision transitions. Synthetic network tests cover independent pressure-path calculations, catalogue constraints, invalid topology, drainage/vent boundaries and model-import isolation. The [Phases 3–5 inventory](docs/PHASE345_INVENTORY.json) records dependency versions, source-file fingerprints, and rule coverage. `requirements-lock.txt` records tested package versions.

GitHub Actions runs public-checkout regression and interface-navigation checks after pushes and pull requests. It does not claim full workbook or live Revit validation.

## Database protection

The default database is `database/plumbing_engine.db`. Set `PLUMBING_ENGINE_DB_PATH` to a different file in an existing writable directory to isolate a review database. UI tests use disposable databases and close connections. The demo uses a temporary database.

```bash
# Create a missing database; existing files are retained
python -m database.db
python -m compliance.rule_loader
python -m database.load_design_tables
python -m database.load_confirmed_additions
```

`python -m database.db --reset` explicitly deletes the selected database and is intended only for disposable data. The Streamlit app applies the additive governance migration on open; existing projects and raw results are retained. Legacy results are marked unverified/stale. Back up an existing database before deliberate migration. The explicit migration command is `python -m database.governance_schema --db-path PATH`.

## Implementation and limits

| Area | Present implementation | Verification limit |
| --- | --- | --- |
| Foundations | Finite/domain validation, unit corrections, full-precision intermediates, globally unique IDs and transactional/current-result storage | Tested reproduction fixes; no blanket code-compliance claim |
| Domestic water | Demand accumulation, actual-bore catalogue sizing, every terminal pressure path, governing margin | Directed trees only; WSFU mode is a design envelope; no loop/zone solver |
| Drainage / vents | DFU accumulation, selected-code context capacities, slope/fall/minima, interval loading, supported dry vents and trap-arm distance | No gravity-flow solver; wet/circuit/AAV and offsets remain explicit unsupported checks |
| Rules | 32 rules; 11 registered predicates across four code families | 21 unevaluated rules; editions and applicability need confirmation |
| Interface | Project/design basis, calculation pages, QA/QC, reports | Headless interaction tests do not independently validate all engineering outputs |
| Reports | Notes, governance context, complete network input/findings, Markdown/CSV/JSON | Review state and incomplete coverage remain visible |
| BIM | Atomic project/model-scoped JSON import/export and pyRevit scripts | Synthetic exchange tests; live Revit and raw CAD/IFC ingestion unverified |

The current SQLite interface is a single trusted-user local review workflow. Public multi-user project access control has not been implemented.

See the [implemented scope](docs/PHASES_3_4_5.md), [old/new comparison](docs/ENGINE_COMPARISON.md), and [CAD/IFC design-check study](docs/CAD_IFC_DESIGN_CHECK_STUDY.md). The study recommends IFC intake first, mapped DXF next, with explicit unit/connectivity/data-readiness gates before engineering checks. The current app accepts mapped JSON and does not scan raw CAD/IFC.

The [Phase 2 governance record](docs/CODE_GOVERNANCE.md), [baseline audit](docs/BASELINE_AUDIT.md), and [architecture notes](docs/ARCHITECTURE.md) describe earlier states. The improvement plan remains in chat for owner review.

## License

[MIT](LICENSE). Standards and third-party design data may have separate terms.
