# Setup and data requirements

Use Python 3.12 and the pinned dependencies in `requirements-lock.txt`, included by `requirements.txt`. Start from the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py --server.port 8504
```

The app initializes its database on first use. [localhost:8504](http://localhost:8504/) works on the computer running the app; no verified public Streamlit deployment URL is currently provided. The SQLite application is intended for a trusted local user. Public multi-user project access control is not implemented.

## Optional capabilities

| Capability | Required setup |
| --- | --- |
| IFC, DXF and PDF parsing | Install `python -m pip install -r requirements-models.txt`, then restart the app. |
| DWG geometry | Supply a confirmed companion DXF or configure a supported local converter; see [DWG/PDF intake](DWG_PDF_UPLOADS.md). |
| Looped or extended-period hydraulics | Configure a trusted EPANET 2.2 native library using `PLUMBING_EPANET_LIBRARY`; see [solver setup](GENERAL_HYDRAULIC_SOLVER.md#configure-epanet). The interface and tree layer can run without it. |
| Revit extraction and result handoff | Install/load the repository's `bim/pyrevit/PlumbingEngine.extension`, configure repository/database paths, and bind the required PLM shared parameters. See the [native test procedure](BIM_INGESTION_PHASE4A.md#run-the-real-revit-harness). |
| Private interactive calculation forms | Import XLSX/XLSM files or a converted library through **Calculation Sheets**. A synthetic demonstration is bundled; private forms are not included in a public clone. |

## Numeric design tables

Formula-only and synthetic example features can run without private source workbooks. Workbook-dependent demand, capacity and sizing methods require the applicable source files in `database/code_design_data/`:

- `IPC_Plumbing_Design_Data.xlsx`
- `UPC_Plumbing_Design_Data.xlsx`
- `BS_EN_Plumbing_Design_Data.xlsx`
- `Egyptian_Plumbing_Design_Data.xlsx`
- `SBC701_Saudi_Plumbing_Design_Data.xlsx`

These files are excluded from the public repository. Loading a workbook does not authenticate its edition, numeric values or project applicability. Missing code tables remain missing; another code is not silently substituted. Restart after adding the applicable files and confirm their availability/review status in the app.

## Project data and validation

The default database is `database/plumbing_engine.db`. Set `PLUMBING_ENGINE_DB_PATH` to a separate database file in an existing writable directory for isolated reviews. Retain project/model evidence and backups locally. Private workbooks, calculation packages, model files, credentials and databases must not be published.

The full local test suite uses private workbooks and optional native-library evidence. GitHub Actions runs the public-checkout checks defined in [the validation workflow](../.github/workflows/validation.yml). A native committed Revit execution record is required for the opt-in real-model round-trip test; a skipped test or rollback probe is not a completed round trip.

```bash
python -m pytest tests/ -q
```

Independent reference/source acceptance and engineering approval are tracked separately from software regression results. See [engineering validation](ENGINEERING_VALIDATION.md) and [review/release workflow](REVIEW_AND_RELEASE.md).
