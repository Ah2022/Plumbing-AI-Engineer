# Original engine versus Phase 2

Comparison date: 26 October 2026. Original means supplied v0.6.2 (source uploaded in commit `397e8d9f9b8031c6ce31a69aae64c4accaa75a23`). The intermediate Phase 1 audit is commit `a5cb857837413a2dff6ae8cea2e6b91af64a9b81`. Updated means the Phase 2 governance implementation in this repository.

## User-visible differences

| Area | Original v0.6.2 | Updated Phase 2 |
| --- | --- | --- |
| Code identity | Family selectable; edition not collected by the project form | Separate IPC 2024/SBC701 2024/Egyptian candidate profiles; IPC is the first verification target |
| Project adoption | No code-adoption review record | Draft revisions, required jurisdiction/authority/amendments/methods/scope and named adoption approval with evidence |
| Rule coverage | Presence of a predicate; no edition-specific verification record | Edition-specific applicability/input/unit/exception matrix, references, reviewer, evidence and benchmark status |
| Compliance PASS | Predicate can pass a pending pressure input | Technical PASS retained as evidence; governed status is NOT_EVALUATED while adoption/verification is unresolved |
| Profile/basis changes | Saved results have no profile-revision invalidation | Retained as history, marked stale and require recalculation; cached fixture/storm inputs cleared |
| Provenance | Formula/reference fields; notes dropped on save | Notes plus versioned profile/basis/review and source/loaded-data fingerprints |
| Reports / Revit | No governance-based stale-result filter | Explicit review status and stale indicators; stale results omitted from current Revit exports |
| Database/testing | Demo and setup could reset default DB; Windows UI tests left it open | Phase 1 protections retained; additive migration; non-destructive rule reload; isolated tests |
| Mathematical accuracy | Known stormwater conversion and input-domain defects | The same mathematical defects remain; this phase controls review/approval, not numerical-method correction |

## Executed identical-input comparison

`tools/compare_engines.py` launches separate old/new processes with in-memory databases. It does not run the destructive original demo or open either default application database. Inputs below are synthetic and use no private workbook data. Raw evidence is in [ENGINE_COMPARISON.json](ENGINE_COMPARISON.json).

| Synthetic case | Original | Updated | Interpretation |
| --- | --- | --- | --- |
| Velocity: 1 L/s, 25 mm internal diameter | 2.0372 m/s | 2.0372 m/s | Numerical result preserved |
| Hazen-Williams: 2.5 L/s, 50 mm, 40 m, C=150 | 1.3111 m | 1.3111 m | Numerical result preserved |
| Pump: 5 L/s, 41 m, efficiency 0.7 | 2.8719 kW | 2.8719 kW | Numerical result preserved |
| Rain: 3,600 mm/hr, 1 m², C=1 | 10 L/s | 10 L/s | Both are wrong; dimensional identity gives 1 L/s. AUD-001 is open |
| Pending pressure input | Compliance PASS | NOT_EVALUATED; technical predicate PASS shown separately | Unresolved verification no longer presented as a governed compliance pass |
| Saved rationale | Missing | Retained | Notes round-trip now passes |
| Saved review context | Absent | REVIEW_REQUIRED with versioned snapshot | Explicit engineering-review state |
| Profile-change invalidation | Unavailable | Historical result marked not current | Recalculation required |
| Declared edition/adoption | Edition empty; adoption state absent | IPC 2024; DRAFT | Selection does not imply approval |

Reproduce locally with both source trees available:

```bash
python -m tools.compare_engines --old-root PATH_TO_ORIGINAL_ENGINE --output comparison.json
```

## Test evidence and limits

Phase 1 reported 93 passed and 11 strict expected failures after fixing validation isolation. Phase 2 reports 139 passed and 10 strict expected failures. The increased pass count includes new governance/UI tests, not a claim that every old numerical defect was fixed. The notes-persistence reproduction moved from expected failure to pass.

The original suite comprised 84 cases and had a Windows UI connection-cleanup failure when audited. See [BASELINE_AUDIT.md](BASELINE_AUDIT.md) for that historical baseline. Tests requiring numeric workbooks run locally; public-checkout CI excludes those full-data cases. No live Revit comparison or authoritative engineering approval was performed.

Local review services, when running on the owner's computer: [Phase 1](http://localhost:8501), [updated Phase 2](http://localhost:8502). Phase 1 is an intermediate audit build, not an untouched original UI. The executed comparison above uses the untouched original calculation code.
