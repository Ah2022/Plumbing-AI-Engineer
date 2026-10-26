# Plumbing AI Engineer

Python/SQLite plumbing calculation engine with a Streamlit interface, code-rule checks, reports, and Revit JSON exchange.

**Phase 1 audit: 26 October 2026.** This is a testing build with unresolved numerical, compliance-status, and project-isolation defects. Engineering outputs have been preserved for review. See the [baseline audit](docs/BASELINE_AUDIT.md).

## Test the engine

**[Open the local Streamlit test app](http://localhost:8501)** — works on the computer running Streamlit. This is a local URL, not an internet deployment.

```bash
git clone https://github.com/Ah2022/Plumbing-AI-Engineer.git
cd Plumbing-AI-Engineer
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py
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

## Verification

```bash
# Full suite; requires the five local workbooks
python -m pytest tests/ -q -rx

# Public-checkout checks
python -m pytest tests/test_audit_benchmarks.py tests/test_bim_exchange.py tests/test_reports.py tests/test_runtime_safety.py -q -rx

# Inventory; uses an in-memory database and prints no workbook values
python -m tools.baseline_inventory

# End-to-end demo; uses its own temporary database
python -m tests.demo_project
```

Verified on Windows/Python 3.12.14 with Streamlit 1.66.1: **93 passed, 11 expected failures**. The strict `xfail` cases reproduce open defects, not accepted engineering results. The [inventory](docs/BASELINE_INVENTORY.json) records dependency versions, source-file fingerprints, and rule coverage. `requirements-lock.txt` records tested package versions.

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

`python -m database.db --reset` explicitly deletes the selected database and is intended only for disposable data. Existing databases are not automatically migrated by this audit.

## Implementation and limits

| Area | Present implementation | Verification limit |
| --- | --- | --- |
| Calculations | Water, drainage, vents, hot water, tanks, pumps, stormwater | Open audit defects; no blanket compliance claim |
| Rules | 32 rules; 11 registered predicates across four code families | 21 unevaluated rules; editions and applicability need confirmation |
| Interface | Project/design basis, calculation pages, QA/QC, reports | Headless interaction tests do not independently validate all engineering outputs |
| Reports | Saved calculations, Markdown/CSV | Calculation notes are not persisted; AUD-006 |
| BIM | JSON import/export, pyRevit scripts | Synthetic engine-side tests; live Revit unverified |

The current SQLite interface is a single trusted-user local review workflow. Public multi-user project access control has not been implemented.

See the [audit](docs/BASELINE_AUDIT.md) and [historical architecture notes](docs/ARCHITECTURE.md). The improvement plan remains in chat for owner review.

## License

[MIT](LICENSE). Standards and third-party design data may have separate terms.
