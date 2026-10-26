# Phase 2: code profiles, design basis and verification governance

**Implemented:** 26 October 2026. **First verification target:** IPC 2024, selected by the owner. **Previous baseline:** Phase 1 commit `a5cb857837413a2dff6ae8cea2e6b91af64a9b81`.

This implements the second phase of the plan in chat: code editions, project applicability, rule/data provenance, approval records, and independent benchmark requirements. It is separate from the original engine's historical development-phase numbering.

## What is implemented

- Three separate versioned profiles: IPC-2024, SBC701-2024, and EGYPT-301-1-2003. UPC and BS_EN remain legacy datasets without a newly verified profile.
- Project-specific jurisdiction, adopting authority, amendments, occupancy, systems, units, methods, exclusions and precedence records. No local authority or code adoption is inferred from the code name.
- Draft revisions and a named adoption-review decision with evidence. Approving project adoption does not approve the engine or its rule/data packages.
- A rule coverage matrix containing edition, supplied reference, source note/classification, executable-predicate status, applicability, input/unit/exception review, evidence, benchmark and reviewer status.
- Independent numeric benchmark records with original inputs/units, expected and observed results, tolerance policy, source evidence and reviewer. Non-finite values and invalid tolerances are rejected. Expected values are supplied/reviewed independently, not copied from engine output.
- Versioned calculation snapshots containing engine/registry identity, code profile, basis revision, source-file fingerprints, loaded rule/table fingerprints, rule reviews and review status. Calculation notes are now retained.
- Invalidation after profile/design-basis/review changes; source/loaded-data drift is also detected by fingerprint comparison. Historical values are retained, labeled stale and excluded from current Revit exports.
- Compliance outputs distinguish the technical predicate result from the governed compliance result. A technical PASS with unresolved adoption/verification becomes NOT_EVALUATED.
- Additive migration of existing databases, an event history, a new Streamlit Code Profiles page, report/QA-QC review information, and downloadable coverage/context JSON.

## Profile provenance and limits

| Profile | Edition evidence checked | What remains unverified |
| --- | --- | --- |
| IPC-2024 | [Official ICC product metadata](https://shop.iccsafe.org/international-codes/model-codes/2024-international-plumbing-coder.html) identifies the 2024 document. The supplied JSON also names IPC 2024. | Individual rule provisions, numeric workbook editions/accuracy, local adoption and amendments |
| SBC701-2024 | The [official SBC table of contents](https://sbc.gov.sa/ar/BC/Documents/tableofcontent2024/SBC%20701/SBC701-CR_241224-FA.pdf) identifies SBC 701-CR-2024. | The table of contents is not full provision verification, a numeric dataset audit, or project adoption evidence |
| EGYPT-301-1-2003 | Label comes from the supplied rules README; its [HBRC catalogue URL](https://www.hbrc.edu.eg/ar/egyptian-code-2) could not be fetched during this phase. | Edition currency, exact scope, governing project requirements, rules and datasets |

No restricted code text or numeric workbook cells were republished. The registry's source labels do not turn metadata or supplied annotations into verified engineering requirements. The existing cross-code fallback mechanics remain preliminary; the governing review status cannot become verified while the data/applicability gaps remain.

## Use the workflow

1. Create/open a project. New projects default to IPC; its 2024 candidate basis starts DRAFT.
2. Open **Code Profiles**. Record every required criterion, including explicit confirmed 'none' statements where appropriate.
3. Save the draft. A different code/basis revision invalidates prior calculations, compliance records and QA/QC snapshots, and clears cached fixture/storm inputs.
4. An engineer records project adoption approval using an actual approved project reference. Blank criteria/reviewer/evidence are rejected.
5. Review the separate rule matrix and benchmark acceptance records. A VERIFIED executable rule requires a current passing independent benchmark in the same profile/domain, source evidence and named reviewer. Unsupported rules cannot be labeled verified executable checks.
6. Recalculate and rerun checks after a change. Review technical results, review status and stale indicators in exports/reports.

Unit selection records the design basis. Existing calculation forms still use their explicit units; this phase does not implement automatic unit conversion of those forms. Unsupported systems such as specialist medical-gas design are not added to the profile scope.

## Benchmark acceptance requirements

The seeded benchmark records start PENDING, one acceptance record for each of water, drainage, vent and storm per profile. They are placeholders for an independent verification pack, not passing examples.

| Domain | Required evidence before engineering acceptance |
| --- | --- |
| Water | Correct fixture classifications; approved demand method; table bounds/interpolation; minimum connections; internal diameters; elevation/friction/equipment losses; pressure-path and insufficient-pressure cases |
| Drainage | Correct branch/stack/building-drain categories; cumulative loads; minimum slopes; boundaries and unsupported configurations |
| Vent | Applicable arrangements, developed lengths, loading/size boundaries and trap-arm limits; unsupported special arrangements remain explicit |
| Storm | Independent rainfall basis and dimensional volume-to-flow identity; area/runoff assumptions; leader/pipe boundaries; unsupported primary/secondary drainage cases |

Each submitted record must specify inputs, units, method/applicability, independent expected-result source, observed result, justified comparison tolerance, reviewer and disposition. A numeric agreement alone does not establish the appropriateness of the method or scope. Source and loaded-data fingerprints bind accepted evidence to the tested dataset version.

## Database compatibility and verification

The original schema is retained. `database.governance_schema.ensure_governance_schema` adds columns/tables without deleting existing project or calculation rows. Legacy calculations preserve their raw status but start `LEGACY_UNVERIFIED` and not current; no edition is silently assigned to a legacy project. Streamlit applies the migration on open. Explicit command:

```bash
python -m database.governance_schema --db-path PATH
```

Rule reload now uses non-destructive upserts and no longer resets the default database. Governance changes retain an event snapshot; project adoption is reset to draft when its basis changes. This is a local trusted-user review workflow, not a production authentication or tamper-proof signature system.

Verification covers profile separation, missing criteria, mismatched editions/units/systems, approved adoption versus verified engineering, stale data, benchmark requirements, cross-code requests, old result retention, migration idempotence, rule reload, reports, BIM stale suppression, and the new Streamlit workflow. See the [old/new comparison](ENGINE_COMPARISON.md) and the machine-readable [coverage inventory](CODE_COVERAGE.json).

## Acceptance status

The Phase 2 software workflow is implemented and tested. Actual project adoption, authoritative rule/table verification and engineering acceptance remain owner/engineer decisions. No real project was approved by the assistant. Initial rule reviews and benchmark records remain pending. Numeric dataset edition/applicability and unresolved Phase 1 defects intentionally keep current results at REVIEW_REQUIRED.

The original stormwater arithmetic, invalid-input handling, low-level predicate defects, global calculation-ID collisions and Revit identity/update defects are not claimed fixed by this phase. Their strict expected-failure tests remain. AUD-006 (lost notes) is resolved by the new persisted calculation trace.
