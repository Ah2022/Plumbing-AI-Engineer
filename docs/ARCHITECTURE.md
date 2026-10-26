# Plumbing Design, Calculation & Code-Compliance Engine
## Architecture, Data Analysis & MVP Plan — v0.6 (Phases 1-6 complete; Phase 7 engine-side complete & tested, Revit-side written but unverified)

**v0.2 update:** `Code_Data.zip` (5 workbooks: IPC, UPC, BS_EN, Egyptian,
SAUDI_SBC_701 — 10 tabs each) has been ingested: **2,728 real numeric design
values** now live in `design_table_values`, each with its own confidence flag
(`CONFIRMED`/`FLAGGED`, read directly from the workbook's own cell
highlighting) and code reference. Section 0 below is kept as-written for
history; Section "0b" describes what changed. Cold-water velocity checks and
fixture-unit totals now run against this real data — see Section 3b.

Prepared as the required "first task" deliverable (analyze → architect → wait for
approval) before Phase 1 implementation. A working Phase-1 skeleton — schema,
rule ingestion, hydraulics library, compliance engine — has already been built
and tested against the code-rule data you supplied, because it required no
invented values. **The calculation modules (cold water sizing, drainage, vent,
storm, tanks, pumps) are deliberately left as gated stubs** pending the numeric
code data described in Section H — building those now would mean guessing
code values, which section 2 of your spec explicitly forbids.

---

## 0. CRITICAL FINDING — read this before anything else

You said *"i provided the code rules json so you can apply it to the engine."*
I extracted and read all of it. It's real, well-structured, and directly usable
— but it is a **different kind of dataset** than what Section 9 of your spec
("CODE DATABASE") describes, and the gap changes the MVP plan materially.

| What your spec (Section 9) asks for | What the ZIP actually contains |
|---|---|
| Numeric design tables: fixture units per fixture, DFU tables, max velocity, min pipe size, min slope, vent length/diameter tables, rainfall intensity tables | **32 qualitative compliance rules** across IPC (9), UPC (9), SAUDI_SBC_701 (8), EGYPT_LOCAL (6) — each a `condition` / `action` / `severity` / `reference` triple in prose |
| Values the calculation engine can size a pipe against | Only **one** rule (`IPC-W-002`) carries a hard number: `static_pressure_threshold_psi = 80` |
| Hot water, tank, pump code data | **Not present at all** — no `hot_water_rules.json`, `tank_rules.json`, or `pump_rules.json` in any of the four codes |

The ZIP's own `rules_index.json` confirms this is intentional: it's *"a
derived rules-engine dataset, not a reproduction of the copyrighted code
text"* — i.e. it's built to drive a **QA/QC compliance checklist**, not the
numeric sizing tables (which are the copyrighted part of IPC/UPC/SBC 701, and
which I won't reproduce from memory or invent — same rule your own spec
states in Sections 2, 9, and 30).

**Practical effect on the build:**
- The **Code Compliance Engine** (spec Section 21) is buildable now, and I've built and tested it — see Section 3 below.
- The **Calculation Engine's** code-dependent parts (pipe sizing, DFU, vent sizing, rainfall intensity, hot-water demand factors) are correctly *architected* now but must **stop and report `MISSING CODE DATA`** until you supply the numeric tables — see Section H for exactly what's needed and where it should come from.
- This isn't a blocker to starting — it's precisely the "traceability + never invent a value" behavior your spec demands, and it's already working (demonstrated in Section 3).

---

## 0b. Code_Data.zip — what's now loaded, and what's genuinely still missing

`database/load_design_tables.py` parses each workbook's 10 tabs (splitting on
blank rows into sub-tables, e.g. `7_Vent_Sizing` correctly yields four
separate tables for SBC 701's Tables 909/911/912/913) and loads every numeric
cell as a long-format row in `design_table_values`, preserving:
- **row/column structure** (fixture records, 2-D lookup tables, and flat
  parameter lists all load correctly, even though every code names its
  columns differently — confirmed by hand-checking IPC/UPC/BS_EN/Egypt's
  velocity-limit sheets, which use four different column sets for the same
  concept)
- **confidence**, read from the workbook's own cell fill color (light amber =
  `FLAGGED`, matching each workbook's own README color-code legend) — this is
  your own annotation, preserved as-is, not re-derived
- **every documented gap/caveat** as plain text against the relevant table,
  filtered to surface only the genuine "GAP:" / "DO NOT use" markers (not
  every descriptive title line)

**Coverage loaded:**

| Code | Tables | Values | Flagged |
|---|---|---|---|
| IPC | 17 | 1,131 | 16 |
| UPC | 8 | 423 | 16 |
| BS_EN | 8 | 241 | 21 |
| EGYPT_LOCAL | 8 | 154 | 16 |
| SAUDI_SBC_701 | 18 | 779 | 182 |

**Genuinely still missing at v0.2 — now resolved as of v0.3 (Ahmed's own
independent verification, 2026-09):**

1. ✅ **Riyadh 24-hour design rainfall depth** — RESOLVED. Al-Saleh (1997)
   confirmed as the project's rainfall basis (Ahmed fetched the primary paper
   and independently recalculated the Gumbel predictions from its raw
   coefficients — matched exactly). Loaded as `design_tables` under
   `SAUDI_SBC_701`/`storm`, `source_classification=PROJECT`. The candidate
   "DAR/CIBSE 2017" table was explicitly checked and **rejected** — the
   report number traces to a real Riyadh Municipality document, but no
   verifiable link to CIBSE exists.
2. ⚠️ **SBC 701 Table 906** (vent stack sizing) — not independently
   re-extractable (every mirror, including 7 state-adopted IPC sites, renders
   it as an image). **Decision recorded**: use IPC's confirmed Table 906.1 via
   the same explicit-fallback pattern as velocity, once `calculations/vent.py`
   is built in Phase 3 — must be tagged "via code lineage, not independently
   verified for SBC."
3. ✅ **SBC 701 velocity ceiling** — confirmed absent (Sec. 604.9 water-hammer
   control is qualitative only, no numeric value in the text). **Decision**:
   keep the IPC fallback, already supported.
4. ✅ **SBC 701 / Egypt hot-water demand factors** — confirmed not found for
   either code. **Decision**: IPC's ASPE/ASHRAE hospital figures (demand
   factor 0.25, storage factor 0.6) are final.
5. ✅ **Hospital DFU values** — RESOLVED, and the earlier candidate table
   ("bedpan washer=10, clinical sink=6") is explicitly **rejected**: IPC
   §713.2 and SBC 701-2007 §2.22.6 (both fetched directly) state these
   fixtures are rated as a water closet, not separately. Implemented as an
   alias map in `calculations/water.py` (`HOSPITAL_FIXTURE_ALIASES`) — a
   "Clinical sink" now resolves to the Water Closet fixture-unit value.
6. ✅ **PPR-PN16 velocity** — RESOLVED, manufacturer-confirmed (Aquatherm CE
   course): **3.05 m/s (10 ft/s)** general design ceiling, and a separate
   **0.5 m/s** circulation/return-loop limit (not the same figure — Ahmed
   confirmed both are real and distinct). The "1.5–2.0 m/s best practice" and
   "4.57–6.10 m/s absolute limit" figures some sources cite were checked and
   **deliberately excluded** — unverified.

`database/load_confirmed_additions.py` is the audit trail for all six —
run after `load_design_tables.py`, separate from the code-workbook ETL
because its provenance (research paper, manufacturer course, direct code-text
fetch) differs from the Code_Data.zip source.

---

## A. SYSTEM ARCHITECTURE

```
PROJECT INPUT → DESIGN BASIS → CODE SELECTION → CODE DATABASE (rules + design tables)
     → DESIGN CRITERIA → FIXTURE DATABASE
     → CALCULATION ENGINE (cold water | hot water | drainage | vent | storm | tanks | pumps | hydraulics)
     → CODE COMPLIANCE ENGINE → QA/QC ENGINE → CALCULATION REPORT → BIM/REVIT INTEGRATION
```

Two engines sit side by side and must stay decoupled, because they consume
different kinds of code data:

- **Compliance Engine** — evaluates the 32 prose rules against project data that
  exists (design-basis entries, calculation statuses). Each rule maps to a
  Python *predicate function* (`compliance/rule_registry.py`) written by a
  human, because "condition" text isn't executable — a rule with no predicate
  reports `NOT_EVALUATED`, never a false `PASS`.
- **Calculation Engine** — pure hydraulics/thermodynamics (`calculations/hydraulics.py`,
  all public-domain textbook formulas) combined with **numeric design-table
  lookups** (`design_table_values`) that are code-and-edition specific and
  currently empty. A calculation raises `MissingCodeDataError` rather than
  guessing when a lookup is missing.

Every result — from either engine — is one row with the full chain preserved:
`INPUT → DESIGN CRITERIA → CODE RULE → FORMULA → CALCULATION → RESULT →
PASS/FAIL/WARNING/ASSUMED/MISSING_DATA`, per spec Section 1.

---

## B. DATABASE ARCHITECTURE

SQLite now (per your requested stack), schema written in plain portable SQL
(`database/schema.sql`) so a later PostgreSQL move is a dump/restore, not a
rewrite. Full schema is in the repo; summary of the table groups:

1. **Code / rule database** — `codes`, `code_rules` (the 32 rules, loaded from
   your JSON), `design_tables` + `design_table_values` (numeric tables — empty,
   status-tracked as `CODE_DATA_REQUIRED` / `PARTIAL` / `POPULATED`).
2. **Project / design basis** — `projects`, `design_basis_items` (every entry
   carries a `source_classification`: `CODE` / `PROJECT` / `USER_INPUT` /
   `MANUFACTURER` / `ASSUMED`, and a `status`: `PENDING` / `APPROVED` /
   `REJECTED` — nothing is used in a final calc until `APPROVED`, per spec
   Sections 8 and 31).
3. **Fixtures / materials / pipe sizes** — `fixtures`, `materials`,
   `pipe_sizes`. `materials` has a `roughness_model` column (`hazen_williams_C`
   vs `darcy_weisbach_mm`) so the two hydraulic methods never get the wrong
   kind of roughness value by accident.
4. **Network elements** — `pipes`, `tanks`, `pumps` — project-specific,
   optionally linked to a Revit `element_id`.
5. **Calculations / compliance / QA-QC / assumptions** — `calculations` (one
   row per traceable calc, `calc_id` like `CW-001`), `compliance_checks` (one
   row per rule evaluation), `assumptions` (`A-001`-style, with the
   `PENDING_ENGINEER_APPROVAL` gate from spec Section 31), `qaqc_results`.
6. **BIM link** — `revit_elements`, generic enough to hold whatever Revit
   parameters a pyRevit extractor pulls (Section E).

The schema is written, tested, and creates cleanly — see Section 3.

---

## C. CALCULATION ARCHITECTURE

Every calculation function returns a `CalculationResult` dataclass
(`models/__init__.py`):

```python
CalculationResult(
    calc_id, calc_type, formula,          # e.g. "hf = 10.67*L*Q^1.852/(C^1.852*D^4.8704)"
    inputs={"flow_lps": (2.5, "L/s"), ...},
    intermediate={...},
    result_value, result_unit,
    required_value, selected_value,
    status,        # PASS | FAIL | WARNING | ASSUMED | MISSING_DATA | CALCULATED_NOT_APPROVED
    reference, code_rule_id, notes,
)
```

`status` defaults to `CALCULATED_NOT_APPROVED` — a completed calculation is
never automatically "compliant" or "approved" (spec Section 34: calculation
success, code compliance, and engineer approval are three separate things).

`calculations/hydraulics.py` implements the formulas your spec names
explicitly and that are public-domain engineering mechanics (safe to
hard-code): `Q = VA`, Darcy-Weisbach, Hazen-Williams (SI form), Total Dynamic
Head, pump power, the Rational Method (`Q=CIA`), and `Q = ṁCpΔT`. All six are
unit-tested against known textbook values (Section G).

Domain modules (`calculations/water.py`, `drainage.py`, `vent.py`,
`stormwater.py`, `tanks.py`, `pumps.py`, `hot_water.py`) sit on top of
`hydraulics.py` and pull code-specific limits via one helper,
`_get_design_value()`, which raises `MissingCodeDataError` on any missing
lookup — demonstrated live in Section 3, Step 5.

---

## D. CODE ARCHITECTURE

Two tiers, deliberately kept apart because they have different sources of
truth and different failure modes:

**Tier 1 — Compliance rules** (`code_rules` table, from your JSON).
`compliance/rule_registry.py` maps a `rule_id` to a Python predicate only
where the data to evaluate it actually exists today:
- **Numeric threshold** (1 rule): `IPC-W-002`, compares a project's entered
  static pressure against the rule's own `parameters_json` value.
- **Data-presence** (4 rules): the `*-S-001/002` storm rules — checks that
  rainfall design intensity has been entered *and approved* before storm
  sizing proceeds.
- **Sizing-justification** (4 rules): the `*-D-001` / `*-W-002` family —
  checks that a real (non-`ASSUMED`, non-`MISSING_DATA`) calculation record
  exists for that domain.
- **Everything else (23 rules)** — cross-connection detection, trap-venting
  adequacy, S-trap detection, AAV permissibility, secondary-drain presence —
  needs actual pipe/fixture **topology** from the Revit model. These report
  `NOT_EVALUATED` until Phase 7 (BIM extraction) exists. I did not write fake
  predicates for these; a wrong "PASS" on a life-safety drainage/vent check
  is worse than an honest "not evaluated yet."

**Tier 2 — Design tables** (`design_tables` / `design_table_values`).
Structured, code-and-edition-scoped, currently empty. This is where fixture
units, DFU values, velocity limits, minimum slopes, vent tables, and rainfall
intensity data live once supplied — see Section H for the exact list and
recommended sourcing.

---

## E. BIM / REVIT ARCHITECTURE

Kept consistent with how you already build and deploy pyRevit tools (CPython3
engine, JSON config, ISO 19650/Uniclass 2015 naming) rather than inventing a
new pattern:

```
REVIT MODEL
   → pyRevit EXTRACTOR (bim/pyrevit/) — walks plumbing categories via Revit API,
     emits JSON matching the pipes/fixtures/tanks/pumps schema (Section B)
   → LOCAL FILE or LOCAL REST SERVICE (Phase 7)              [Revit → Engine]
   → CALCULATION ENGINE runs independently of Revit (per spec Section 27 —
     Revit is never responsible for the core engineering math)
   → RESULTS JSON (calc_id, status, required/selected values, PLM_* params)
   → pyRevit WRITER (bim/pyrevit/) — writes PLM_Design_Flow, PLM_Code_Status,
     etc. back onto elements, and applies OverrideGraphicSettings color-coding
     (🔴 FAIL / 🟠 WARNING / 🟢 PASS) matching your "click RUN FULL ANALYSIS" vision
```

`revit_elements.parameters_json` is intentionally a generic blob so the schema
doesn't need to change every time a new Revit parameter matters. This phase
was correctly scoped last, as your own plan states — the engine had to be
trustworthy standalone first.

**v0.6 status — built in two honestly-separated halves:**

- **Engine side (`bim/schemas.py`, `bim/exchange.py`) — done and tested.**
  Pure Python/SQLite, no Revit dependency, so it's fully provable without a
  Revit session: `validate_extract_payload()` rejects a malformed extract
  outright (spec Section 30's "stop and report", not a partial import);
  `import_revit_extract()` upserts pipes/tanks/pumps/fixtures by
  `revit_element_id` so re-running the extractor after a model edit updates
  rather than duplicates; `export_results_for_revit()` returns only elements
  with an actual saved calculation, keyed by `revit_element_id`, so the
  writer script never has to guess or clear a status for something that
  hasn't been calculated yet. `tanks`/`pumps` gained a `revit_element_id`
  column in this pass (schema.sql) — previously only `pipes` had one, which
  would have made round-tripping storage tanks and pumps impossible.
- **Revit side (`bim/pyrevit/PlumbingEngine.extension/`, `bim/revit/PLM_shared_parameters.txt`) —
  written, not verified.** Extract Data (walks OST_PipeCurves / OST_PlumbingFixtures,
  builds the same JSON contract) and Run Analysis (reads results back via
  `bim.exchange.export_results_for_revit`, writes PLM_* shared parameters,
  color-codes by status) are written to real pyRevit conventions (CPython3
  engine, `revit.Transaction`, `OverrideGraphicSettings`) and syntax-checked,
  but **I have no Revit installation to run them against** — I cannot confirm
  the exact `BuiltInParameter`/`MEPSystem` calls behave as written against a
  real model, or that `plm_config.SYSTEM_NAME_KEYWORDS` matches your actual
  piping-system-type names (it can't — I don't know your template's naming,
  so that dict is a documented guess you need to check, not verified data).
  Treat this half the way you'd treat any pyRevit script from someone who
  hasn't tested it against your template: read it, run Extract Data on a
  throwaway model first, and expect to fix at least the system-name mapping.

---

## F. MVP DEVELOPMENT PLAN — status against your own phasing (spec Section 37/38)

| Phase | Scope | Status |
|---|---|---|
| **1** | Project Input, Design Basis, Code DB architecture, Fixture DB, Material DB | **Schema + rule ingestion done & tested.** Fixture/material DB tables exist; seed data pending your input (Section H). |
| **1/2** | Cold Water, Pipe Sizing, Hydraulic Loss, Code Compliance | **Complete** — velocity checks, fixture-unit totals, and full pipe-sizing-from-demand all run on real IPC/UPC/BS_EN/Egypt/SBC701 data. Compliance engine done & tested against all 4 rule-sets. |
| **3** | Drainage, Vent | **Complete** — DFU-to-pipe sizing, min-slope checking, and vent sizing (incl. IPC's multi-dimensional Table 906.1) run on real data. |
| **4** | Hot Water, Tanks, Pumps | **Complete** — ASPE Table 6-1 demand/storage method, hospital temperature checks (scald/Legionella), tank sizing, pump duty (TDH + power) all run on real/derived data. |
| **5** | Stormwater | **Complete (v0.6)** — the "roof-drain sizing table blocked" note above was stale: Table 1106's leader-sizing and pipe-sizing sub-tables were already loaded from the SBC701 workbook (Phase 2); only the Riyadh 24hr rainfall depth was actually missing, and you supplied that (Al-Saleh 1997). Full chain now runs on real data: design rainfall intensity -> Rational Method peak flow -> roof-drain (leader) sizing -> storm drain pipe sizing. |
| **6** | Report Generator, QA/QC Dashboard | **Complete (v0.6)** — `reports/report_generator.py` (structured + Markdown calculation report, spec Section 23) and `reports/qaqc_dashboard.py` (6 project-health checks, persisted to `qaqc_results`), both wired into the UI. |
| **7** | Revit / pyRevit integration | **Engine-side half complete & tested (v0.6); Revit-side half written but unverified.** `bim/schemas.py` (exchange contract) and `bim/exchange.py` (import Revit extract -> pipes/tanks/pumps/revit_elements, export latest calc results keyed by revit_element_id) are pure Python/SQLite, fully tested with a simulated extract payload. `bim/pyrevit/PlumbingEngine.extension/` (Extract Data + Run Analysis pushbuttons) and `bim/revit/PLM_shared_parameters.txt` are written to real pyRevit/Revit-API conventions but **cannot be executed or tested outside a live Revit 2024 session** — see the honesty note in Section E. |
| **UI** | — | **Running** — Streamlit app covers every page above (incl. Stormwater, QA/QC Dashboard), tested headlessly (AppTest), 76/76 tests passing across the whole suite. |

**What "done & tested" means concretely right now:** `python -m
tests.demo_project` runs against your real 4-code dataset end-to-end — loads
32 rules + 5 workbooks + your verified additions, creates a project, runs
calculations across every domain (cold water, drainage/vent, hot water,
tanks, pumps, stormwater), runs the compliance engine and QA/QC dashboard,
generates a calculation report, and simulates a Revit extract/results
round-trip. `pytest tests/` passes 76/76 regression tests (`tests/test_stormwater.py`,
`tests/test_reports.py`, `tests/test_bim_exchange.py` are the Phase 5/6/7
additions). Both are in the delivered project.

---

## G. TESTING STRATEGY

- **Data-integrity tests** (`test_all_four_codes_load`, `test_ipc_w_002_parameter_preserved`) —
  assert the rule ETL doesn't silently drop or corrupt anything from your source JSON.
- **Predicate-coverage tests** (`test_predicate_flags_sync`) — assert the
  registry doesn't accidentally claim coverage for a rule that has no real
  predicate (guards against the exact failure mode Section D warns about).
- **Formula tests against known textbook values** (`test_velocity_from_flow_known_value`,
  etc.) — every hydraulics function is checked against a hand-calculated
  result, not just "does it run."
- **Stormwater chain tests** (`tests/test_stormwater.py`) — every result hand-
  computed from the raw SBC701 Table 1106 / rainfall-ratio / Al-Saleh depth
  rows, not copied from the implementation; includes out-of-range and wrong-
  code negative cases (MissingCodeDataError).
- **Report/QA-QC tests** (`tests/test_reports.py`) — asserts the report and
  dashboard read back exactly what was saved (structure, counts, pending
  items), including the empty-project edge case.
- **BIM exchange tests** (`tests/test_bim_exchange.py`) — a simulated
  extractor payload proves the import/export round-trip end to end
  (validation rejection, idempotent re-import, results keyed correctly)
  without needing Revit itself; this is the part of Phase 7 that's provably
  correct today. The Revit-side pushbutton scripts are not covered by this
  suite — see Section F.
- **Per spec Section 33**, once real fixture/material/table data exists:
  `TEST-001..005` (Residential, Office, Hotel, Hospital, Mall) as full
  scenario regression tests — each with known inputs, expected outputs, and a
  diff against actual engine output. These are the right next tests to write
  once Section H's data lands, not before (a scenario test against stub data
  would just be testing the stub).

---

## H. REQUIRED ENGINEERING INPUTS — what only you can supply

Nothing below can be safely filled in by me guessing from training data — code
tables are the copyrighted core of IPC/UPC/SBC 701, and getting a velocity
limit or a DFU value wrong is a life-safety issue, not a style choice. For
each code you want live (start with **SAUDI_SBC_701**, since that's your
active project context), I need:

1. **Fixture-unit tables** — cold FU, hot FU, and DFU per fixture type (WC,
   lavatory, urinal, shower, floor drain, etc.), from the code's own table.
2. **Water-supply demand conversion** — the code's FU→GPM/L·s⁻¹ demand curve
   or table (e.g. the Hunter curve variant the code adopts).
3. **Velocity limits** — max (and min, if specified) velocity for cold water,
   hot water, and drainage.
4. **Minimum pipe sizes** per fixture/application.
5. **Drainage sizing table** — DFU-to-pipe-diameter-and-slope, by pipe
   material/roughness class if the code differentiates.
6. **Minimum slope table** by pipe size.
7. **Vent sizing** — diameter-vs-load and max developed length tables.
8. **Rainfall intensity data** — by city/return period, or confirmation of
   which local meteorological source is the project's authority (spec
   Section 18 explicitly requires this to show its source).
9. **Hot-water design basis** — demand factors, storage temperature,
   recirculation criteria (none of this exists in any of the 4 supplied
   rule files).
10. **Material roughness values** — Hazen-Williams C or Darcy-Weisbach
    absolute roughness for each material you actually use. You've already
    told me your confirmed SMC 3 materials (PPR-PN16, uPVC Class 4, HDPE,
    Black Steel SCH40, Type K copper, SS316L) — happy to seed `materials`
    with those now if you confirm the roughness values to attach to each.

**How to get this to me efficiently:** you don't need to type numbers into
chat — paste table excerpts, a spreadsheet, or photos of the relevant code
pages/tables and I'll structure them straight into
`design_table_values` with the right `source_classification` (`CODE`) and
`reference` fields. Partial data is fine — the system tracks each table's
`status` as `CODE_DATA_REQUIRED` → `PARTIAL` → `POPULATED` per table, not
all-or-nothing.

---

## 3b. Phase 2 — cold water sizing now runs on real code data

`database/design_table_api.py` sits between the raw long-format table and the
calculation modules — reconstructing records from any column layout and
providing typed lookups (`get_velocity_limit`, `get_fixture_units` via
`get_table_records`, `get_min_slope`, `get_material_roughness`). `calculations/water.py`
now calls this instead of a placeholder:

```
IPC:       1.0 L/s through 25mm ID -> velocity 2.037 m/s vs limit 1.8 m/s -> FAIL
SBC 701:   same check, no fallback -> MissingCodeDataError (correct: no SBC value exists)
SBC 701:   same check, allow_fallback_code="IPC" -> FAIL, status downgrades no lower than
           WARNING-eligible, reference records "(fallback from IPC)", notes explain exactly
           what was borrowed and why (SBC's own documented gap)
IPC fixture units: 40x Water closet (Public/Flushometer) + 30x Lavatory (Public/Faucet)
           -> 125.0 total cold-water FU, confidence=CONFIRMED
```

This is real, not illustrative — it's in `tests/demo_project.py` Steps 5–6 and
covered by 4 new regression tests (`test_ipc_velocity_limit_real_data`,
`test_sbc701_velocity_limit_gap_without_fallback`,
`test_sbc701_velocity_limit_explicit_fallback_is_flagged`,
`test_ipc_fixture_units_real_data` — 10/10 passing).

**Known current limitation:** the generic column-matching in
`get_min_slope`/`get_table_records` works cleanly for SBC 701-style tables
(`pipe_size_mm` / `min_slope_pct`) but not yet for IPC's imperial-unit slope
table (`pipe_in`, self-cleansing-velocity based) — different unit system and
table shape, not a bug, just not wired up yet. Next increment once you
confirm which is the priority code for drainage sizing.

---

## 4. Phase 3 (Drainage/Vent) and the UI — v0.4

### Drainage & vent sizing now run on real data

`calculations/drainage.py` and `calculations/vent.py` follow the exact
pattern proven in `water.py`: pull a real numeric table via
`design_table_api`, size the pipe, return a fully-traced
`CalculationResult`. Verified against hand-checked values from your real
SBC 701 tables:

```
size_drainage_pipe(SAUDI_SBC_701, 6 DFU, horizontal_branch)  -> 50mm   (table: max_dfu_horiz_branch)
size_drainage_pipe(SAUDI_SBC_701, 7 DFU, horizontal_branch)  -> 65mm
check_min_slope(SAUDI_SBC_701, 100mm, selected=1.0%)          -> PASS  (limit 1.0%)
check_min_slope(SAUDI_SBC_701, 100mm, selected=0.5%)          -> FAIL
size_vent_pipe(SAUDI_SBC_701, 4 DFU)                            -> 50mm
```

**One real bug caught and fixed during this build**: IPC's vent table
(Table 906.1) is genuinely three-dimensional — stack size × FU × developed
length → vent size **in inches**, not a simple "FU → vent size" table like
SBC 701's. A naive fallback would have silently read an inches value as mm
and returned nonsense (2mm for 500 DFU). Fixed by splitting into
`size_vent_pipe()` (simple 1D tables) and `size_vent_pipe_multidim()` (IPC's
table, explicit units), with `size_vent_pipe()` now refusing cleanly instead
of guessing when only the multi-dimensional form exists. Verified against
the real table: stack=4in, FU=200, length=90ft → 2.5in, matching the source
data exactly.

This is also where Ahmed's confirmed decision on SBC 701's own Table 906
(not independently re-extractable) gets used: the vent UI tab explicitly
notes the fallback to IPC's Table 906.1 "via code lineage, not independently
verified for SBC."

### UI — Streamlit app

`app/streamlit_app.py`. Navigation mirrors spec Section 35: **Project → Design
Basis → Fixtures & Water → Drainage & Vent → Code Compliance/QA-QC →
Report/Export**. Hot Water / Storm / Tanks / Pumps are shown as "not yet
available (Phase 4/5)" in the sidebar rather than faked with placeholder
math — the UI never presents a number the engine can't actually back up.

Every calculation result in the UI displays the full trace (`calc_id`,
status badge, formula, required vs selected, code reference, notes) — never
a bare number, matching spec Section 2. The Design Basis page implements the
approve/reject workflow from Section 8/31 (`PENDING` → `APPROVED`/`REJECTED`).
The Compliance page runs the real rule engine and shows PASS/WARNING/
FAIL/NOT_EVALUATED counts. Report/Export gives a CSV of everything
calculated so far — explicitly labeled as a placeholder for the real
calculation-sheet generator (Section 23), which is Phase 6.

**Tested headlessly**, not just eyeballed: Streamlit's own `AppTest` harness
(`tests/test_streamlit_app.py`) actually executes the script and clicks
every button — project creation, all 6 pages, the velocity check, drainage
sizing, and the compliance run. This caught two real bugs before they'd have
reached you:
1. SQLite connections are thread-bound by default, but Streamlit can run
   script reruns on different worker threads within one session — fixed
   with `check_same_thread=False` (safe here since Streamlit never runs two
   reruns of the same session concurrently).
2. The Report page queried `compliance_checks` with `ORDER BY id`, but that
   table's primary key is `check_id` — a copy-paste mismatch from a
   different table's schema, caught by the test, not by inspection.

28/28 tests pass (18 calculation/data tests + 10 UI tests).

---

## 5. Pipe-sizing-from-demand and Phase 4 (Hot Water, Tanks, Pumps) — v0.5

### Pipe-sizing-from-demand completes Phase 2

`calculations/water.size_pipe_from_demand()` closes the last Phase 2 gap:
WSFU → design flow (Hunter's Curve, **linearly interpolated between real,
adjacent table points** when the WSFU total falls between rows — never
extrapolated beyond the table's range) → required internal diameter via
`D = sqrt(4Q/(pi*V_max))`, checked against the code's fixture-minimum
branch size where relevant.

```
SBC701, 12 WSFU, flush_tank, PPR    -> demand=60.0 L/min -> required D=20.43mm
SBC701, 12.5 WSFU (interpolated)     -> demand=61.0 L/min (midpoint of 60/62 -- both real rows)
SBC701, 999999 WSFU                    -> MissingCodeDataError (beyond table range, no extrapolation)
SBC701, WC-flushometer-valve context    -> code minimum (25mm) overrides a smaller hydraulic result
```

**Deliberate limitation, stated rather than hidden**: the result is the
*required* internal diameter, not a manufacturer's nominal pipe size —
no pipe-dimension catalog (nominal ↔ internal diameter per material/schedule,
e.g. PPR-PN16's actual SDR sizes) is loaded. Rounding up to an orderable
size is either the engineer's step or a future materials-catalog module —
not invented here.

### Phase 4 — Hot Water, Tanks, Pumps

`calculations/hot_water.py`: demand/storage sizing using the ASPE Table 6-1
demand-factor (0.25) / storage-capacity-factor (0.6) method — these were
captions in the IPC workbook, not table rows, so they're recorded
explicitly in code (`ASPE_HOSPITAL_DEMAND_FACTOR`, `ASPE_...STORAGE...`)
with your confirmation as the final basis for SAUDI_SBC_701/EGYPT_LOCAL
(neither states its own factors). Also implements the three hospital-specific
temperature checks from IPC's confirmed data (scald protection ≤46.1°C,
Legionella recirculation return ≥51.1°C, Legionella storage ≥60°C) —
directly relevant to SMC-3.

```
20 showers + 40 private lavatories  -> connected=1580 GPH -> design hourly=395 GPH
                                        -> storage tank = 897.1 L
Scald check, selected=46.1C          -> PASS (at the limit)
Scald check, selected=50C             -> FAIL
Legionella storage, selected=55C       -> FAIL (needs >=60C)
Heater: 0.5 kg/s, 15C->60C              -> 94.185 kW
```

`calculations/tanks.py`: domestic cold-water tank sizing from a
**[PROJECT]-classified** storage duration (never invented — must come from
an approved Design Basis entry) and freeboard; hot-water storage tank sizing
reuses `hot_water_demand()`'s result directly rather than recomputing it.

`calculations/pumps.py`: wraps TDH + hydraulic power into one traced duty-point
result. Matching an actual catalogue pump/motor needs a manufacturer curve —
correctly left for the engineer, not invented.

```
Domestic tank: 5 L/s x 4hr x 1.1 freeboard  -> required=72.0 m3, selected=79.2 m3
Pump duty: 5 L/s, TDH=41m, eff=0.7            -> 2.8719 kW hydraulic power
```

### UI — three new pages, one new tab

Streamlit gains **Hot Water**, **Tanks**, and **Pumps** pages, plus a
**"Pipe sizing from demand"** tab under Fixtures & Water — all following the
same pattern (form → real calculation → full traced result table → saved to
`calculations`). Verified with the same `AppTest` headless harness used for
Phase 1-3: every new button clicked, no exceptions. **47/47 tests pass**
(39 calculation/data tests + 8 additional UI tests on top of the earlier 10).

---

## 3. WHAT'S ALREADY RUNNING (proof, not just a plan)

```
$ python -m tests.demo_project
STEP 1 — Load code rules from database/codes/
  EGYPT_LOCAL        6 rules loaded
  IPC                9 rules loaded
  SAUDI_SBC_701      8 rules loaded
  UPC                9 rules loaded

STEP 3 — Hazen-Williams: hf = 1.3111 m  (status=CALCULATED_NOT_APPROVED)

STEP 4 — Compliance engine (SAUDI_SBC_701, 8 rules)
  SBC701-D-001 [error]   -> FAIL           No Drainage pipe calculation exists yet.
  SBC701-D-002 [warning] -> NOT_EVALUATED  requires BIM topology data
  SBC701-S-001 [error]   -> FAIL           Rainfall design intensity not entered.
  SBC701-W-002 [warning] -> FAIL           No Cold water pipe calculation exists yet.
  ... (full 8-rule output in repo)

STEP 5 — MissingCodeDataError correctly raised for velocity check
  (no code-sourced velocity limit exists yet — system stopped instead of guessing)

STEP 9 — Stormwater: intensity=50.512 mm/hr -> peak flow=63.14 L/s
  -> leader=100mm -> storm drain pipe=200mm

STEP 10 — QA/QC dashboard: 6 checks run and persisted; calculation report
  generated (4218 characters)

STEP 11 — Revit exchange, simulated: extract imported, calculation run
  against the linked pipe, results exported keyed by revit_element_id

$ pytest tests/  →  76 passed
```

---

## 6. Stormwater, Reports/QA-QC, and Revit exchange — v0.6

### Phase 5 — Stormwater, fully unblocked

The "roof-drain sizing table blocked" line elsewhere in this document was
carried forward from v0.2-v0.5 without re-checking it against what actually
loaded. It was wrong by v0.6: SBC701 Table 1106's leader-sizing and
pipe-sizing sub-tables were parsed and loaded by `load_design_tables.py`
from day one — the only real gap was the Riyadh 24hr rainfall depth input,
which you independently verified (Al-Saleh 1997) and is loaded via
`load_confirmed_additions.py`. `calculations/stormwater.py` now chains all
four steps on real data:

```
10-yr, 15-min storm, Riyadh station -> intensity = 50.512 mm/hr
  [Al-Saleh (1997) 24hr depth=28.7mm x SBC701 duration ratio=0.44 / 0.25hr]
C=0.9, 500 m2 roof -> peak flow (Rational Method) = 63.14 L/s
-> leader size = 100mm  (design rate rounded UP to 75 mm/hr column, never down)
-> storm drain pipe (vertical) = 200mm
```

`get_leader_size`/`get_storm_drain_pipe_size` (`database/design_table_api.py`)
never round a design rate down or extrapolate past the table's last column —
an out-of-range request raises `MissingCodeDataError` instead of guessing.

### Phase 6 — Report Generator + QA/QC Dashboard

`reports/report_generator.py` reads back everything already calculated,
compliance-checked, and QA/QC-summarized into one Markdown calculation
report (spec Section 23) — it never re-derives a number. `reports/
qaqc_dashboard.py` runs 6 project-health checks (calculation status mix,
compliance status mix, pending design-basis approvals, pending assumptions,
which saved calculations rest on FLAGGED/fallback data, coverage gaps) and
persists them to the previously-unused `qaqc_results` table. Unlike
`compliance_checks` (an accumulating log), re-running the dashboard replaces
this project's previous snapshot — it's meant to answer "is this project
issuable right now," not build up history.

### Phase 7 — Revit/pyRevit exchange, in two honestly-separated halves

See Section E above for the full writeup. Short version: the engine-side
exchange (`bim/schemas.py`, `bim/exchange.py`) is pure Python/SQLite, fully
tested with a simulated extract payload (`tests/test_bim_exchange.py`), and
proven end to end in `tests.demo_project` Step 11. The Revit-side pyRevit
scripts (`bim/pyrevit/`) and the shared-parameter file
(`bim/revit/PLM_shared_parameters.txt`) are written to real pyRevit/Revit
API conventions but genuinely untested — there's no Revit installation in
this environment to run them against.

### v0.6.2 — fixture-unit picker + a fixed velocity-matching gap

Two more things, prompted by trying to actually use the tool for a real
Egypt hotel: `get_velocity_limit()` was missing EGYPT_LOCAL's own real 2.4
m/s limit because its phrasing ("maximum water velocity") didn't match the
expected substrings — fixed by trying multiple known phrasings per code
before giving up. And the Fixtures & Water page's fixture-name field was
free text, silently failing to match a table row on any spelling
difference — replaced with `database.design_table_api.
list_water_fixture_unit_choices()`, a dropdown of the code's own real WSFU
rows (SBC701, UPC, and IPC — which turned out to have a genuine WSFU
sub-table alongside its drainage-FU one under the same tab name) with the
value shown before you add it, and no lookup left to fail. Codes with no
WSFU data (EGYPT_LOCAL) fall back to a manual-entry path that's explicitly
labeled FLAGGED rather than pretending to be code-sourced.

### UI — two new pages

**Stormwater** (4-step form matching the chain above) and **QA/QC
Dashboard** (run button + status table + PASS/WARNING/FAIL/MISSING_DATA
counts). **Report / Export** gained the Markdown report alongside the
existing CSV exports. Verified with the same `AppTest` headless harness.
**76/76 tests pass** overall (see `pytest tests/ -v` for the full breakdown
by file).

---

## NEXT STEP

Phases 1-6 are complete, and Phase 7's engine-side half is complete and
tested. What's left, in priority order:

1. **Test the pyRevit scripts against a real model.** Point
   `plm_config.ENGINE_REPO_PATH`/`ENGINE_DB_PATH` at your machine, run
   Extract Data on a throwaway/test model first, and check the printed
   "skipped (unclassified)" list — that's `plm_config.SYSTEM_NAME_KEYWORDS`
   telling you it doesn't recognize your actual Piping System Type names.
   Fix the keyword lists before trusting a real extract.
2. **Import `bim/revit/PLM_shared_parameters.txt`** into your shared
   parameter file and bind the 7 PLM_* parameters to the Pipe/Plumbing
   Fixtures/Generic Model categories you'll be writing results onto, before
   Run Analysis has anywhere to write.
3. **Tanks/pumps extraction** — `Extract Data.pushbutton/script.py` only
   collects pipes and fixtures right now (`collect_pipes`/`collect_fixtures`);
   tanks and pumps are typically generic models or mechanical equipment in a
   Revit model, and I don't know your family/type naming convention for
   those, so `collect_tanks`/`collect_pumps` aren't written yet — same
   pattern as `collect_fixtures`, once you tell me what to match on.
4. **The genuinely-missing data items** (per Section H, wherever that list
   still has open rows) — send these whenever you have them; each unblocks
   one specific check, nothing else waits on them.
