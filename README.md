# Plumbing Design, Calculation & Code-Compliance Engine

**Technical documentation:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
The proposed improvement plan is reviewed in chat.

**Upload status (26 October 2026):** Source code and rules are present. Publication of the five design-data workbooks is pending owner approval; numeric-table setup and workbook-dependent tests require those files under `database/code_design_data/`. The generated local database is excluded.

## Quickstart

```bash
cd Plumbing-AI-Engineer
pip install -r requirements.txt

# Initialize the DB, load the 32 code rules AND the 2,728 numeric design values
python -m database.db
python -m database.load_design_tables

# Run the full end-to-end demo (resets database/plumbing_engine.db) (rules -> tables -> project -> calc -> compliance
# -> stormwater -> QA/QC dashboard -> report -> simulated Revit exchange)
python -m tests.demo_project

# Run the regression tests
python -m pytest tests/ -v

# Launch the UI (Project / Design Basis / Fixtures & Water / Drainage & Vent /
# Hot Water / Tanks / Pumps / Stormwater / Code Compliance / QA-QC Dashboard /
# Report / Export — first launch auto-initializes the DB)
streamlit run app/streamlit_app.py
```

## Layout

```
plumbing_engine/
├── docs/ARCHITECTURE.md      ← full write-up, read this first
├── app/
│   ├── streamlit_app.py       ← UI: Project / Design Basis / Fixtures & Water /
│   │                              Drainage & Vent / Code Compliance / Report
│   └── db_helpers.py           ← calc-ID generation, saving CalculationResults, status badges
├── database/
│   ├── schema.sql             ← SQLite schema (portable SQL)
│   ├── db.py                  ← connection + init helper
│   ├── design_table_api.py     ← query layer: velocity limits, fixture units, min slope, etc.
│   ├── load_design_tables.py    ← ETL: Code_Data.zip workbooks -> design_table_values
│   ├── load_confirmed_additions.py ← ETL: Ahmed's independently-verified data (rainfall, PPR)
│   └── codes/                 ← the code-rule JSON you supplied, as-is
├── compliance/
│   ├── rule_loader.py         ← loads codes/*.json into SQLite (real, tested)
│   ├── rule_registry.py       ← rule_id -> Python predicate mapping
│   └── engine.py                ← runs predicates, records compliance_checks
├── calculations/
│   ├── hydraulics.py           ← public-domain formulas (Q=VA, Darcy-Weisbach,
│   │                              Hazen-Williams, TDH, pump power, Q=CIA, Q=mCpΔT)
│   ├── water.py                 ← cold water: velocity checks, fixture-unit totals,
│   │                                pipe-sizing-from-demand (real data, Phase 2 complete)
│   ├── drainage.py               ← DFU-to-pipe sizing, min-slope check (real data)
│   ├── vent.py                    ← DFU-to-vent sizing, incl. IPC's multi-dimensional Table 906.1
│   ├── hot_water.py                 ← ASPE demand/storage method, hospital temp checks (real data)
│   ├── tanks.py                      ← domestic + hot-water storage tank sizing
│   ├── pumps.py                       ← TDH + hydraulic power duty-point calc
│   └── stormwater.py                    ← full chain: rainfall intensity -> Rational Method
│                                           -> roof-drain (leader) sizing -> storm pipe sizing (real data)
├── reports/
│   ├── report_generator.py               ← Markdown calculation report (spec Section 23)
│   └── qaqc_dashboard.py                  ← 6 project-health checks -> qaqc_results table
├── models/__init__.py           ← CalculationResult, MissingCodeDataError
├── units/convert.py              ← explicit unit conversions
├── tests/                         ← demo_project.py, pytest regression tests (76 passing,
│                                     incl. a headless Streamlit UI test suite)
└── bim/                             ← Revit/pyRevit exchange (Phase 7)
    ├── schemas.py                          ← JSON exchange contract (engine <-> Revit)
    ├── exchange.py                          ← engine-side import/export -- tested, no Revit needed
    ├── pyrevit/PlumbingEngine.extension/     ← Extract Data + Run Analysis pushbuttons
    │                                            (written to pyRevit conventions, unverified — no Revit here)
    └── revit/PLM_shared_parameters.txt        ← shared-parameter definitions for PLM_* results
```

## Current status (v0.6 — Phase 1-6 complete; Phase 7 engine-side complete & tested, Revit-side written but unverified)

- Code-rule database, numeric design tables (2,728+ values), compliance
  engine, hydraulics formulas: **built and tested**.
- Cold water, drainage/vent, hot water/tanks/pumps (Phases 1-4) — **run on
  real data**, as before.
- **Stormwater (Phase 5) — now complete.** The previously-noted "roof-drain
  table blocked" gap turned out to be stale: the SBC701 workbook already had
  Table 1106's leader/pipe-sizing sub-tables loaded; only the Riyadh 24hr
  rainfall depth was missing, and that's now supplied (Al-Saleh 1997). Full
  chain — design rainfall intensity → Rational Method peak flow → roof-drain
  (leader) sizing → storm drain pipe sizing — runs on real data.
- **Report Generator + QA/QC Dashboard (Phase 6) — complete.** A Markdown
  calculation report (spec Section 23) and a 6-check project-health
  dashboard, both reading back only what's already been calculated/checked.
- **Revit/pyRevit exchange (Phase 7) — engine side complete & tested; Revit
  side written but unverified.** `bim/schemas.py`/`bim/exchange.py` (the
  JSON contract + import/export logic) are pure Python/SQLite and fully
  tested with a simulated extract. The pyRevit pushbutton scripts and shared-
  parameter file are written to real conventions but **have not been run
  against an actual Revit session** — there's no Revit install available to
  test them here. See `docs/ARCHITECTURE.md` Section E/F for exactly what
  that means and what to check first.
- **UI**: Streamlit app now covers all 10 pages including Stormwater and
  QA/QC Dashboard. Tested headlessly via `AppTest` — every page and button
  runs without exceptions. **76/76 tests pass.**

Nothing in this repo invents a code value. Where a numeric limit or table
isn't in the supplied data, the relevant function raises
`MissingCodeDataError` instead of guessing — or, where the source data
itself names an explicit interim substitute, that substitution is available
only via an explicit opt-in parameter and is always tagged FLAGGED with a
note naming exactly what was borrowed from where.
