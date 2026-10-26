# Original engine versus Phases 3–5

Comparison date: 26 October 2026. Original means supplied v0.6.2, uploaded as commit `397e8d9f9b8031c6ce31a69aae64c4accaa75a23`. Phase 1 was `a5cb857837413a2dff6ae8cea2e6b91af64a9b81`; Phase 2 was `627077d3f01b1e6160d5b5e98e0a85798b0ed6ef`. Current scope is documented in [PHASES_3_4_5.md](PHASES_3_4_5.md).

| Area | Original v0.6.2 | Current build |
| --- | --- | --- |
| Foundations | Tenfold rain conversion error; incomplete finite/domain checks and rounded intermediates | Correct mm/hr-to-L/s conversion, shared input/trace validation, full-precision Darcy intermediates |
| Water networks | Individual calculation forms | Explicit tree demand accumulation, actual-bore catalogue selection, elevation/friction/fitting/equipment losses, all terminal pressure margins |
| Demand tables | Out-of-range values could use the next row; IPC gpm columns not normalized | Inclusive endpoints, no extrapolation, conflicting rows rejected, US gpm converted to L/min |
| Drainage | Individual DFU/table lookups | Tree DFU accumulation, actual slope/fall, selected-code context and interval capacity checks, explicit nominal mapping |
| Vents | Simple sizing could conceal missing context | Supported dry-vent load/length and trap-arm distance checks; unsupported arrangements stay unevaluated |
| Project identity | Per-project counters against a global calculation ID; model elements could cross project boundaries | Project-tagged UUIDs, project/model element identity, atomic updates, dependency invalidation |
| Compliance | Pending pressure input could pass; unapproved data could justify sizing | Latest approved facts required; technical status separate from code governance and review state |
| Provenance | Notes lost on save; no versioned approval snapshot | Notes, code/basis/source fingerprints, complete network input/findings, stale history |
| Model export | Single latest result could hide another check | Current per-object findings aggregated with failure precedence and explicit model selection |
| CAD/IFC | Revit JSON exchange only | Mapped-JSON calculation boundary plus [IFC/DXF feasibility study](CAD_IFC_DESIGN_CHECK_STUDY.md); no raw-file scanner yet |

## Executed identical-input comparison

`tools/compare_engines.py` launches separate old/current processes with in-memory databases. It never opens either application's default database. Inputs are synthetic and contain no private workbook values. Raw evidence: [ENGINE_COMPARISON.json](ENGINE_COMPARISON.json).

| Synthetic case | Original | Current | Interpretation |
| --- | --- | --- | --- |
| Velocity: 1 L/s, 25 mm bore | 2.0372 m/s | 2.0372 m/s | Valid numerical result retained |
| Hazen-Williams: 2.5 L/s, 50 mm, 40 m, C=150 | 1.3111 m | 1.3111 m | Valid numerical result retained |
| Pump: 5 L/s, 41 m, efficiency 0.7 | 2.8719 kW | 2.8719 kW | Valid numerical result retained |
| Rain: 3,600 mm/hr, 1 m², C=1 | 10 L/s | 1 L/s | Corrected dimensional identity |
| Pending pressure input | PASS | NOT_EVALUATED, including technical predicate | Unapproved input cannot justify a pass |
| Saved rationale | Missing | Retained | Notes round-trip fixed |
| Review context | Absent | REVIEW_REQUIRED with versioned snapshot | Engineering-review state explicit |
| Profile change | No invalidation | Prior result marked not current | Recalculation required |
| Declared edition/adoption | Empty / absent | IPC 2024 / DRAFT | Selection does not imply approval |

Reproduce with both source trees available:

```bash
python -m tools.compare_engines --old-root PATH_TO_ORIGINAL_ENGINE --output comparison.json
```

## Test evidence and limits

Phase 1 reported 93 passed and 11 strict expected failures; Phase 2 reported 139 passed and 10 strict expected failures. Current full local suite: **238 passed, no expected failures**, including all ten remaining defect reproductions, independent synthetic pressure-path checks, source-unit/boundary tests, drainage/vent cases and Streamlit interactions. Test-count growth also includes new scope; it does not establish authoritative code coverage.

The original suite comprised 84 cases and had a Windows UI connection-cleanup failure when audited. [BASELINE_AUDIT.md](BASELINE_AUDIT.md) records that historical state. Full workbook tests run locally; public CI omits private workbooks and tests synthetic tables and formula/UI behavior on Windows and Linux. No live Revit/CAD/IFC validation or final engineering approval was performed.

Water currently supports directed trees, not loops or multiple pressure zones. WSFU mode is a diversified design envelope. Drainage is DFU/table checking, not a partial-flow solver. Broader vent arrangements and full-model compliance remain unevaluated. Code editions, table applicability and project adoption require independent review.

Local review services when running on the owner's computer: [Phase 1](http://localhost:8501), [Phase 2](http://localhost:8502), [current build](http://localhost:8503). The retained Phase 1 UI is an intermediate audit build; the executed comparison uses the original calculation source.
