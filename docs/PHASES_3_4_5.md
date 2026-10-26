# Phases 3–5 implementation and supported scope

**Date:** 26 October 2026. **Baseline:** Phase 2 commit `627077d3f01b1e6160d5b5e98e0a85798b0ed6ef`. Phase numbering follows the plan in chat: foundations, domestic water, sanitary drainage/venting.

## Phase 3: foundations

- Shared finite-number and physical-domain validation rejects NaN/infinity, Boolean pseudo-numbers, invalid diameters, negative loads/losses and impossible efficiency. Unit conversions validate finite inputs and calculation records reject non-finite traces.
- Rational Method now divides mm/hour × m² by **3,600** to obtain L/s; the original divisor of 360 was a tenfold error. Darcy-Weisbach retains full intermediate velocity precision. Pump records distinguish hydraulic from efficiency-adjusted power.
- Static-pressure checks require the latest approved input in psi; rejected/unapproved PRV records cannot justify a pass. Failed/unapproved current sizing records do not become sizing-justification passes.
- Calculation IDs use project-tagged UUIDs rather than per-project counters against a global key. Superseded target results remain as stale history, and saves are transactional.
- Model imports validate structure, finite values and unique element IDs, scope identity to project/model, update changed connectivity/flow/elevations and roll back failed imports. Re-import conservatively invalidates all project calculations and saved compliance/QA checks because downstream dependencies may have changed. Multiple model identities require explicit export selection; exports aggregate current per-object failures so a later pass cannot hide them.
- Existing project/calculation rows are preserved by additive migration. Legacy model rows with no model key are not silently reassigned to a new model. Supply a stable model ID for federation; model name is only a fallback identity.

The ten expected failures remaining after Phase 2 are now ordinary passing regression tests. Their passing status is evidence of the reproduced fixes, not authoritative approval of all code tables or every design arrangement.

## Phase 4: domestic water

`calculations.network.analyze_water_network` validates a directed tree and evaluates every source-to-terminal path. It supports declared cold or hot service with separately allocated demands, explicit terminal-flow summation or a typed selected-code WSFU demand adapter, continuous demands, material friction inputs, actual internal bores, catalogue nominal constraints, elevation, fitting coefficients, equipment losses and required residual heads.

It reports the governing terminal/path and all pressure margins. Optional catalogue selection starts with valid sizes and greedily upsizes along governing paths until the supported constraints are met or no beneficial size remains. It is a feasible-design procedure, not a global least-cost optimiser. Insufficient source head remains a failure; the engine does not invent a booster or choose an arbitrary largest pipe.

The existing WSFU lookup now accepts exact first/last rows, rejects extrapolation below/above the table and rejects conflicting duplicate rows. IPC source demand columns in US gpm are converted to L/min; contradictory dual-unit columns are rejected. Interpolation remains the declared existing method between adjacent points; project/code applicability still needs approval. Nominal fixture minima and hydraulically required internal diameter are stored separately. No nominal catalogue size is invented when no catalogue is supplied.

For WSFU mode, segment design flows are a diversified design envelope, not a simultaneous mass-balanced hydraulic solution. Explicit terminal-flow mode conserves the supplied branch flows. Loops, multiple pressure zones, transient analysis and source/equipment curves beyond the supplied design condition are unsupported.

## Phase 5: drainage and vents

`analyze_drainage_network` accumulates drainage DFU toward the declared outlet. It distinguishes branches, stack contexts, branch intervals and building drains/sewers using available selected-code table shapes. It checks selected nominal size, separate fixture/minimum-size criteria, actual fall, horizontal slope and source-table or explicitly referenced minimum slopes. Slope-dependent capacity columns are selected conservatively without rounding to a steeper column. Missing/ambiguous tables remain missing data.

Stack interval counts and all contributing fixture assignments are required where relevant; per-interval and total loading can both govern, including inch-based source designations. Flagged capacity or slope sources remain warnings in per-pipe findings. Offsets are explicitly unevaluated. This is DFU/table and geometric checking, not a partial-flow gravity solver; no discharge flow is invented from DFU.

Dry-vent checks use supported load/length/stack dimensions. Trap-arm checks evaluate source-table maximum distance only. Wet/circuit/AAV arrangements, missing trap/connection information, incomplete source tables and other unsupported conditions cannot default to a pass. Distance checks do not establish trap-weir, fall, connection or exception compliance.

DN and NPS are designations, not interchangeable dimensions. Inch-based source-table selections retain their source nominal value/unit; the network requires an explicit source-size mapping rather than treating DN as inches converted to millimetres. For IPC vent tables, provide stack/selected nominal sizes in the table's inch designations. The source references and catalogue mapping must be reviewed.

## Review interface and reproducibility

The **Network Review** page accepts explicit SI JSON with a `network_id` and matching project `code_id`. Synthetic examples in `examples/` demonstrate the contract; their criteria/catalogues are not code requirements or manufacturer products. The saved record contains the complete original model, per-pipe/terminal results, references, input hash and Phase 2 governance snapshot. Draft input and saved results are distinguished; project/basis changes clear or separate cached drafts/results.

The interface does not scan raw CAD or IFC. The separate [CAD/IFC study](CAD_IFC_DESIGN_CHECK_STUDY.md) specifies the proposed adapters and acceptance evidence. No live CAD/IFC/Revit model was certified in this work.

Run all regressions with the five original local workbooks:

```bash
python -m pytest tests/ -q
```

The final local suite passed 241 tests with no expected failures on Python 3.12.14 / Streamlit 1.66.1. Data-independent CI also exercises synthetic source tables, pressure-path hand calculations, catalogue constraints, negative topology/units, drainage and vent boundaries, transactions, source/model identity and the new Streamlit page. Workbook contents remain excluded from the public repository.

## Acceptance limits

The supported software scope is implemented and tested. Code-edition/table applicability, project adoption and independent engineering acceptance remain pending review. Technical checks and final compliance remain separate; `REVIEW_REQUIRED` is retained. A partial coverage report or a passing synthetic benchmark is not a full-model compliance certificate.
