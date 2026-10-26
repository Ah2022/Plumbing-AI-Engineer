# Phase 1 baseline audit

**Date:** 26 October 2026. **Source baseline:** `397e8d9f9b8031c6ce31a69aae64c4accaa75a23`, plus five owner-supplied local workbooks. Phase 1 means the first phase in the owner's chat: audit the existing engine. Older development-phase numbers in ARCHITECTURE.md describe different work.

## Outcome

The implementation exists and runs, but its original tests did not establish engineering correctness. Independent dimensional and negative-case checks reproduced a tenfold stormwater-flow error, false compliance passes, and cross-project identifier defects. The engine remains a review build.

Engineering formulas, data, and current sizing outputs were preserved. This phase adds an evidence-based issue register, reproduction cases, inventory, and safe validation/setup workflows. Numerical and schema fixes below remain proposed for review.

## Verification evidence

Environment: Windows, CPython 3.12.14, pytest 9.1.1, openpyxl 3.1.5, Streamlit 1.66.1, pandas 3.1.0. Exact installed versions are in `requirements-lock.txt`.

| Check | Result |
| --- | --- |
| Original suite, isolated copy | 61 passed, 25 error events: first UI test passed but its teardown failed on an open SQLite connection; 24 subsequent setup failures followed |
| Original case count | 84 cases; historical 76-test documentation was stale |
| Full suite after setup/fixture fixes | 93 passed, 11 strict expected failures, no unexpected failures |
| Independent formula checks | Seven pass: continuity, Darcy-Weisbach, Hazen-Williams, head balance, efficiency-adjusted pump power, heating duty, storage volume |
| Defect reproduction | Eleven strict xfails, covering AUD-001 through AUD-007 |
| Public-copy regressions (workbooks absent) | 22 passed, 1 skipped (full-demo preservation requires local workbooks), 11 expected failures |
| Public-copy interface navigation | 11 passed, 14 deselected; all navigation destinations open without workbooks |
| Existing data-backed checks and demo | Run using the local source workbooks; the original source database's checksum remained unchanged during this audit |
| Revit | Synthetic JSON exchange only; no live Revit acceptance |
| Cloud | Deployment not completed: browser control could not safely establish the current Edge URL; no public app URL verified |

Initial sandbox execution encountered Windows temporary-directory permission errors; the reported baseline/final suites were rerun with normal temporary-directory access. That environment limitation is distinct from the reproduced UI connection-cleanup defect.

Run `python -m pytest tests/ -q -rx` with the workbooks installed. Strict xfails are open defects, not acceptance evidence; an unexpected pass fails so a future fix must update/remove the marker.

## Inventory and workflow

Streamlit inputs → calculation modules/table lookups → SQLite records → compliance and QA/QC → Markdown/CSV reports → Revit JSON exchange. There is no implemented LLM/AI-provider integration in the audited source.

There are 17 application tables. Five local workbooks load 59 tables and 2,728 numeric cells, including 251 flagged cells. `BASELINE_INVENTORY.json` stores counts and file hashes, not workbook contents.

| Rule package | Rules | Executable predicates |
| --- | --- | --- |
| EGYPT_LOCAL | 6 | 2 |
| IPC | 9 | 3 |
| SAUDI_SBC_701 | 8 | 3 |
| UPC | 9 | 3 |
| Total | 32 | 11 |

Twenty-one rules have no predicate. BS_EN has a numeric workbook but no qualitative JSON rule package. Predicate presence and populated tables do not prove code compliance. Editions, adoption, amendments, source authority, and each table's accuracy were not independently approved in this audit.

## Prioritized findings

P0 blocks trusting the affected output or project isolation. P1 is a material correctness/reproducibility issue. P2 concerns documentation/deployment.

| ID / priority | Reproduction and affected files | Proposed fix / acceptance | Status |
| --- | --- | --- | --- |
| AUD-001 / P0 | `hydraulics.rational_method_peak_flow` divides by 360 with mm/hr and m². C=1, I=3600, A=1 must give 1 L/s; actual is 10 L/s. Existing chain tests repeat the wrong expectation. | Correct dimensional conversion; independently recheck stormwater chains and pipe selections; invalidate/recalculate affected saved results. | Open; 1 xfail |
| AUD-002 / P1 | `hydraulics.py` accepts zero diameter (infinity), NaN flow, and efficiency >1. | Explicit finite-value/physical-domain validation, including zero/negative inputs and unit boundaries. | Open; 3 xfails |
| AUD-003 / P0 | `check_static_pressure_threshold` ignores approval status. Pending pressure and a rejected PRV record can produce PASS. | Require approved, valid, applicable design-basis records; test unresolved/rejected cases and units. | Open; 2 xfails |
| AUD-004 / P0 | `_check_sizing_justified` returns PASS for a saved FAIL sizing calculation. | Define acceptable statuses and applicable/latest records; failed required sizing must prevent PASS. | Open; 1 xfail |
| AUD-005 / P0 | `app/db_helpers.py` creates per-project CW-001 while schema has a global `calc_id` primary key; project 2 collides with project 1. | Migration-safe project-scoped or globally unique identity; verify multiple projects, deletion, and concurrent saves. | Open; 1 xfail |
| AUD-006 / P1 | `CalculationResult.as_row`, schema, and saving omit `notes`; saved output loses displayed rationale. | Persist notes/provenance compatibly and round-trip them through reports/exports. | Open; 1 xfail |
| AUD-007 / P0 | `bim/exchange.py` derives pipe IDs solely from Revit IDs. Equal IDs in two projects collide. Re-import ignores changed flow/connectivity. | Project/model-scoped identity, complete atomic updates, migration/rollback and repeat-import tests. | Open; 2 xfails |
| AUD-008 / P1 | Original demo/DB CLI reset the application DB. UI fixtures deleted that same DB and left connections open. | Temporary demo, explicit destructive CLI flag, temporary UI DBs, connection cleanup, sentinel-preservation tests. | Fixed for default demo/CLI/UI-test workflows; explicit reset remains destructive |
| AUD-009 / P1 | Project form does not require editions/amendments; authoritative applicability/benchmark coverage is incomplete. | Confirm each project's adopted requirements and independently verify code-specific coverage. | Open; source finding, not a code/legal determination |
| AUD-010 / P2 | Stale completion/test claims; public checkout lacks workbooks and a verified Cloud app. | Accurate README/audit, local test link, deployment settings, documented source-data limits. | Documentation fixed; Cloud URL and public workbooks pending |

Every synthetic reproduction is in `tests/test_audit_benchmarks.py`. AUD-008 has integration tests in `tests/test_runtime_safety.py`.

## Changes delivered

- Seven independent passing benchmarks and eleven explicit defect reproductions.
- In-memory inventory command that emits metadata/counts only.
- Temporary demo database; DB CLI retains existing data unless `--reset` is explicitly supplied.
- `PLUMBING_ENGINE_DB_PATH` used consistently by UI/bootstrap and connection helpers.
- Disposable UI-test databases with closed connections; source database preserved during verification.
- Review-build labeling, pinned dependencies, public-checkout CI, local test link and Cloud setup instructions.

This is representative source/behavior review, not an exhaustive engineering or security certification. Network solvers, pressure-path completeness, hot-water applicability, every numeric lookup, live Revit, and public multi-user deployment require further review. Per-test isolation is not production authentication or project access control.

## Acceptance boundary

Audit artifacts and reproducible evidence are delivered for owner review. AUD-001 through AUD-007 and AUD-009 remain open; this audit did not silently change their engineering behavior. Owner acceptance and approval of subsequent implementation phases remain outstanding. The improvement plan is kept in chat.
