# Phased improvement plan

**Prepared:** 26 October 2026  
**Status:** proposed; implementation approval pending.  
**Basis:** the [repository assessment](PROJECT_ASSESSMENT.md). The supplied GitHub/cloud baseline contains no engine implementation. The owner's separate local engine folder has been identified through the desktop project registry, but its files are unavailable here. This is a provisional roadmap rather than a confirmed refactoring backlog.

**Confirmed requirement:** select IPC, Egyptian, or Saudi plumbing code according to each project. Editions and local adoption details remain to be confirmed.

## Objective and approval process

Develop a plumbing design engine whose calculations are applicable to a declared code edition, reproducible, independently verified, and clear enough for an engineer to review.

The README, assessment, and plan are the documentation work requested for this review. No application implementation is authorized by this plan.

Before each implementation phase, present the owner with the proposed files/modules, behavior changes, engineering method, acceptance evidence, and effort estimate. Obtain explicit approval for that phase before changing the application. Changes to scope, code edition, sizing method, or major architecture require renewed approval.

Do not commit to a rewrite, framework, database, cloud service, or AI provider before reviewing the existing source. Preserve working behavior through benchmarks and incremental changes wherever feasible.

## Phase overview

| Phase | Focus | Dependency | Completion evidence |
| --- | --- | --- | --- |
| 0 | Recover source and establish the baseline | Source location from owner | Reproducible baseline and evidence-based audit |
| 1 | Approve design basis and code-rule coverage | Phase 0; authoritative sources | Approved scope, rule inventory, and benchmark definitions |
| 2 | Strengthen calculation foundations | Phase 1 | Verified units, topology, rule contracts, and calculation records |
| 3 | Validate the first system: provisionally domestic water | Phase 2 | Independently checked demand, sizing, and pressure-path examples |
| 4 | Validate sanitary drainage and venting | Phase 2; separate approval | Independently checked drainage and vent arrangements |
| 5 | Deliver reporting and an engineer review workflow | First accepted module | Reproducible reports and complete input-to-review examples |
| 6 | Expand coverage and prepare controlled releases | Accepted core and workflow | Approved extension benchmarks and release evidence |

The first system choice is provisional. If drainage and venting is the priority, Phase 4 can precede Phase 3 after the shared foundations pass. Initial report traces should be built with each module; Phase 5 turns them into the full user workflow.

Effort and dates will be estimated after Phase 0. Unknown source size, code coverage, target platform, and benchmark availability make a reliable schedule premature.

## Phase 0 — Source recovery and baseline audit

**Purpose:** establish what actually exists and preserve its current behavior.

**Inputs:** engine repository or archive, branch/commit, setup information, sample input/output projects, and any existing calculation references.

**Proposed work:**

- Inventory application modules, dependencies, interfaces, data tables, persistence, and deployment configuration.
- Reproduce setup and run existing checks; record failures and environment requirements.
- Map the fixture-to-result workflow and separate calculations from rule data, presentation, and AI behavior.
- Compare representative existing outputs with independent calculations; record discrepancies without silently changing results.
- Produce an evidence-based issue register with severity, affected files, reproduction steps, and recommended fixes.
- Revise later phases around the existing architecture and identify any migration requirements.

**Deliverables:** baseline audit, capability matrix, dependency and data inventory, reproducible setup instructions, initial benchmark records, and scoped Phase 1 proposal.

**Acceptance:** a named commit can be inspected and, where applicable, run reproducibly; implemented and unsupported functions are identified; unverified outputs are clearly recorded. If the engine is not yet implemented, the owner confirms this and approves a new-build scope.

**Approval gate:** owner approves the baseline findings and initial product scope.

## Phase 1 — Design basis and code-rule governance

**Purpose:** define exactly what “according to code” means for the first release.

**Proposed work:**

- Define separate project-selectable IPC, Egyptian, and Saudi code profiles. Confirm the exact code document, adopted edition, local amendments, system scope, occupancy classes, and unit systems for each profile.
- Select the first profile for verification without treating the other required profiles as implemented. Track coverage per system, rule, and edition, rather than a single global “supports code” flag.
- Define supported design methods, user-entered criteria, exclusions, and the authority/source for each requirement.
- Build a rule coverage matrix: rule ID, reference, edition, applicability, inputs, units, result, exceptions, data source, reviewer, and validation status.
- Define conflict handling and the project-specific order of precedence for adopted requirements and amendments. Do not treat a Saudi or Egyptian profile as a renamed IPC profile; verify its actual provisions and any adopted or modified references independently.
- Preserve the selected profile and edition in saved projects. Switching profiles must invalidate prior calculated results, trigger validation and recalculation, and report changed or unsupported checks; silent fallback to another profile is prohibited.
- Review permission to use and redistribute reference tables; retain citations and derived test cases without publishing restricted source text.
- Prepare an engineering verification pack with independent expected values, tolerances, table boundaries, and unsupported cases.
- Agree what constitutes a calculation result, an individual check result, and an overall review status.

**Deliverables:** approved design-basis specification, initial rule inventory, applicability matrix, reference-data policy, and benchmark acceptance plan.

**Acceptance:** every rule in the initial scope has a verified reference and applicability statement, or is explicitly marked unsupported. The coverage matrix lists IPC, Egyptian, and Saudi profiles separately. No unapproved mixing of code families or editions is permitted. An engineer approves the benchmark basis before implementation.

**Approval gate:** owner approves the governing code, supported use cases, first module, and Phase 2 scope.

## Phase 2 — Calculation foundations and verification infrastructure

**Purpose:** make engineering calculations deterministic and testable independently of the interface.

**Proposed work:**

- Define explicit models for fixtures, classifications, pipe segments, materials, internal diameters, elevations, equipment, connectivity, and operating conditions.
- Normalize units at a defined calculation boundary while preserving original input units for reporting.
- Keep water-supply fixture units, drainage fixture units, flow, pressure/head, and nominal pipe sizes as distinct concepts.
- Establish versioned rule and material datasets with validated dimensions, bounds, provenance, and lookup behavior.
- Validate model topology, missing inputs, duplicate identifiers, non-finite or physically invalid values, and unsupported arrangements.
- Define deterministic calculation interfaces and explicit failure behavior; prohibit silent fallback sizing and extrapolation without an approved method.
- Record inputs, assumptions, method, engine/rule/data versions, intermediate results, and warnings for each run.
- Add focused automated checks and CI using independent benchmark expectations.

**Deliverables:** approved calculation interfaces, validated project model, versioned rule/data contracts, calculation trace format, and foundational test suite.

**Acceptance:** equivalent supported unit inputs produce physically equivalent results within approved tolerances; invalid models return actionable errors; repeated runs with fixed inputs and versions reproduce results; all foundational benchmark and boundary checks pass.

**Approval gate:** review the interfaces, data migration impact, and verification evidence before system-module changes.

## Phase 3 — Domestic water demand, sizing, and pressure checks

**Purpose:** deliver an auditable first design module, subject to owner selection.

**Proposed work:**

- Validate fixture classifications, water-supply fixture-unit assignments, minimum connection requirements, and hot/cold demand treatment.
- Implement or verify the approved demand conversion method, including any applicable continuous demands and limits.
- Use material- and size-specific internal diameters, approved friction methods, documented fittings treatment, and equipment losses at the relevant flow.
- Account for available source pressure under stated conditions, static elevation change, pipe and fitting losses, component losses, and required outlet pressure.
- Evaluate all supported supply-to-terminal paths; report the governing path and pressure margin.
- Select from valid available sizes against all applicable constraints, with clear failure when no size works.
- Define the limits of the initial network solver. Looped networks, booster pumps, and multiple pressure zones require explicit supported models or exclusions.

**Deliverables:** water module, calculation records, benchmark examples, and supported-method documentation.

**Acceptance:** independent examples agree within approved tolerances across low/high demand, fixture classifications, table boundaries, elevation changes, fittings/equipment losses, insufficient source pressure, and governing-path changes. Selected sizes satisfy every implemented constraint; missing checks remain visible.

**Approval gate:** owner reviews calculations and acceptance evidence before enabling this module for intended users.

## Phase 4 — Sanitary drainage and venting

**Purpose:** evaluate code-specific drainage and vent configurations explicitly.

**Proposed work:**

- Verify drainage fixture-unit assignments, minimum connections, and fixture classification rules.
- Separate horizontal branches, vertical stacks, offsets, building drains, and sewers in both the model and sizing logic.
- Apply the correct cumulative loads, slopes, branch-interval conditions, and applicable connection limits.
- Model vent arrangements, developed lengths, trap arms, and size constraints for the approved venting methods.
- Check cleanout, trap protection, and other selected arrangement requirements where represented by the model.
- Treat wet venting, circuit venting, air-admittance devices, and other special arrangements as separate applicability rules.
- Identify requirements the available geometry cannot evaluate and keep them in an explicit engineer review list.

**Deliverables:** drainage and vent modules, arrangement coverage matrix, calculation records, and benchmark examples.

**Acceptance:** independently reviewed examples cover branches, stacks, offsets where supported, slope and loading boundaries, valid and invalid vent arrangements, and trap-arm limits. Unsupported special arrangements return “not evaluated” and cannot receive an overall compliance pass.

**Approval gate:** owner approves supported arrangements and engineering evidence before release.

## Phase 5 — Engineering reports and design workflow

**Purpose:** make results reviewable and projects reproducible.

**Proposed work:**

- Build a clear input sequence for design basis, fixtures, network, elevations, materials, and design conditions.
- Show missing information and failed checks at the affected object, with the applicable rule reference.
- Present assumptions, intermediate calculations, governing paths, selected sizes, margins, and unsupported checks.
- Export calculation reports and schedules with project metadata, original inputs/units, governing references, engine/rule/data versions, and review status.
- Support saved project revisions and recorded engineer overrides with reasons and affected checks.
- Include a clear method for reopening and recalculating an earlier project without silently changing its governing rules.

**Deliverables:** engineer-facing workflow, report templates, project save/load behavior, and documented example projects.

**Acceptance:** an independent reviewer can reproduce a sample result from its report and saved project; saving and reopening preserves relevant inputs and versions; exports retain failed and unevaluated checks; missing information prevents an unwarranted overall pass.

**Approval gate:** owner accepts the full input-to-report workflow and supported release scope.

## Phase 6 — Approved extensions and release readiness

**Purpose:** add scope only after the initial engine has reliable engineering evidence.

**Potential extensions, each separately approved:**

- **Hot water:** demand profile, generation/storage/recovery, distribution, recirculation heat loss and balancing, temperature control, expansion, and equipment selection criteria.
- **Stormwater:** sourced design rainfall, effective roof/catchment area, gutters/outlets/downpipes, horizontal piping, primary/secondary drainage, and relevant ponding/overflow coordination.
- **Advanced networks:** booster pumps, pressure zones, looped distribution, and additional solver methods.
- **Integration:** structured import/export, BIM/CAD or spreadsheet exchange, with mapping and unit validation.
- **AI assistance:** explain verified traces, propose structured inputs for confirmation, and retrieve approved references with citations. An AI response cannot alter approved rule data or bypass deterministic checks.
- **Complete required code coverage:** extend independently verified IPC, Egyptian, and Saudi rule packages to the agreed system coverage, then consider other jurisdictions through separate approval. A profile remains incomplete until its own applicability review and benchmark suite pass.

**Release work:** select deployment architecture after source review; verify dependency maintenance, secrets handling, project-data protection, applicable access controls, migrations, CI, versioning, rollback, and release documentation for the chosen deployment model.

**Acceptance:** each extension has its own approved design basis and passing benchmarks; an end-to-end example reproduces expected results; unresolved limitations appear in the release notes; the owner accepts the release candidate.

**Approval gate:** approve each extension scope and then the concrete release candidate before production publication.

## Required verification record

For every accepted calculation benchmark, retain:

| Field | Required content |
| --- | --- |
| Case and purpose | Supported system and behavior being verified |
| Design basis | Jurisdiction, edition, amendments, method, and source references |
| Inputs | Fixture classification, topology, dimensions, operating conditions, and explicit units |
| Independent expectation | Hand calculation or independently established result, reviewer, and rationale |
| Comparison policy | Absolute/relative tolerance where appropriate; exact checks for categorical and table selections |
| Outcome | Actual result, governing checks, discrepancies, and review disposition |
| Reproduction | Engine, rule, dataset, and project versions |

Tolerance must be justified by the method. It must not be widened merely to make a failing implementation pass.

## Definition of phase completion

A phase is complete when its agreed deliverables exist, its acceptance evidence passes, documentation states implemented scope and limitations accurately, and the owner approves the phase result. Proposed functionality must remain labeled as proposed until those conditions are met.
