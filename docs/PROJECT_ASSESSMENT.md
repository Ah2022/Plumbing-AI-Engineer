# Project assessment

**Review date:** 26 October 2026  
**Repository:** [Ah2022/Plumbing-AI-Engineer](https://github.com/Ah2022/Plumbing-AI-Engineer)  
**Baseline commit:** `de5f67c1f1524cd237df1c9d2de61809420e9157`  
**Review type:** repository readiness and proposed engineering requirements; source-level audit pending.

## Finding

The supplied repository does not contain the plumbing engine described in the project brief. The local tracked tree contains only `README.md` and `LICENSE`. The baseline README consists of the project title. The license is MIT, attributed to Ahmed Hisham. GitHub branch discovery returned only `main`; the local `work` branch points to the initial commit.

No application source or project archive was found in the workspace's shared, library, or scratch locations during this review.

The owner subsequently confirmed a separate local engine folder, and the desktop project registry identifies a project named Plumbing AI Engineer with folder name `plumbing_engine_v0.6.2`. Its Windows filesystem is not mounted in the cloud workspace, so registration metadata does not provide its source contents. The owner also confirmed that projects use IPC, Egyptian, or Saudi code according to the project; exact editions are still unspecified.

This establishes a documentation and source-availability gap in the supplied GitHub/cloud baseline. It does not establish that the engine is defective, that particular formulas are missing from an existing product, or that no implementation exists elsewhere.

## Evidence and assessment limits

| Review area | Observed evidence | Conclusion |
| --- | --- | --- |
| Source and architecture | No application files or dependency manifests in the supplied tree | Cannot assess implementation quality or select a refactoring strategy |
| Plumbing calculations | No formulas, tables, rule packages, or sample outputs | Cannot verify demand conversion, hydraulics, drainage, or vent calculations |
| Code coverage | Owner requires IPC, Egyptian, and Saudi profiles; no editions, amendments, or rule inventory supplied | No compliance claim can be substantiated |
| Test coverage | No test files or executable test configuration | Numerical accuracy and regressions are unassessed |
| Interface and workflow | No interface source or runnable application | Usability and design-input completeness are unassessed |
| Data and security | No storage, authentication, or deployment configuration | Security and operational behavior are unassessed |
| Documentation | Title-only README and MIT license | Purpose, setup, capabilities, and limits need documentation |
| GitHub | Existing public repository; authenticated account has push access | Documentation can be published to a review branch |

The review inspected tracked files, local history and branches, the remote configuration, GitHub metadata and branch discovery, and workspace file locations. No plumbing calculations, software builds, or execution tests were possible. No authoritative code text was supplied or checked, and no numeric code requirements have been asserted in this assessment.

## Engineering review framework

The following are audit questions for the implementation when it becomes available, rather than reported defects.

### 1. Governing code and traceability

- Does every project declare the jurisdiction, adopted edition, amendments, and intended occupancy?
- Does each implemented rule include its clause or table identifier, applicability, units, limits, exceptions, and reviewed source?
- Are mandatory requirements separated from engineering guidance and user-selected criteria?
- Are alternative methods kept distinct, with the applicable method explicitly selected?
- Are rules reviewed against authoritative, permitted sources rather than generated from memory?

### 2. Domestic water supply

- Are water-supply fixture units, fixture flow rates, and drainage fixture units represented separately?
- Do fixture classifications capture public/private use, supply type, and the relevant code-specific distinctions?
- Is the diversity or demand conversion method applicable to the selected code, occupancy, and fixture population?
- Are hot and cold demand allocations explicit, with no automatic double counting?
- Are actual internal pipe diameters used for the selected material and dimensional standard?
- Does the pressure calculation include elevation, pipe friction, fittings, meters, backflow devices, valves, equipment, and required outlet pressure under stated operating conditions?
- Does the engine identify the hydraulically governing path, detect insufficient source pressure, and report when no available size satisfies all constraints?
- Are model assumptions and any limits on looped networks, pressure zones, or pumping explicit?

### 3. Sanitary drainage and venting

- Are fixture loading and minimum connections derived from the selected code and fixture classification?
- Are horizontal branches, stacks, offsets, building drains, and sewers checked using the correct categories and conditions?
- Are slope, branch intervals, cumulative loading, and applicable connection restrictions represented?
- Are vent arrangement, size, developed length, trap-arm constraints, and applicable special venting methods evaluated?
- Are unsupported geometries blocked or explicitly marked unevaluated?
- Are drainage fixture units kept separate from hydraulic discharge-flow models and from water-supply fixture units?

### 4. Additional systems

- Are hot-water generation, storage, recovery, distribution, recirculation, temperature control, and expansion addressed as distinct checks?
- Does stormwater sizing use a sourced rainfall basis, effective tributary area, roof geometry, and applicable primary and secondary drainage requirements?
- Are specialist systems, such as grease waste, pumped drainage, or medical gas, excluded unless their own design basis and validation exist?

### 5. Numerical reliability and software design

- Are units explicit at entry, calculation, storage, and export?
- Are invalid values, impossible topology, missing references, and out-of-range lookups rejected?
- Are rounding, interpolation permissions, pipe-size selection, and iteration tolerances documented?
- Can a calculation be reproduced from saved inputs and exact engine, rule, and dataset versions?
- Are calculations independent of interface state and AI-generated prose?
- Do tests include independently derived expected results, boundaries, failure cases, and representative networks?

## Priority and recommended sequence

1. **P0 — Obtain the implementation and confirm the design basis.** A source audit and code-selection decision are prerequisites to specific changes.
2. **P0 — Establish verified engineering behavior.** Document methods and independently checked benchmarks before numerical refactoring.
3. **P1 — Establish traceable calculations and validation.** Make units, applicability, pressure accounting, rule versions, and incomplete checks visible.
4. **P1 — Deliver the first approved system module.** Domestic water is a provisional starting point; the owner can prioritize drainage and venting instead.
5. **P2 — Improve reporting, workflow, and supported system coverage.** Expand after engineering acceptance of the initial module.
6. **P3 — Add optional AI and integrations.** Keep them dependent on the verified calculation core.

The detailed [improvement plan](IMPROVEMENT_PLAN.md) defines the proposed phase gates. Engineering defects and implementation estimates must be added after the source becomes available.

## Decisions needed from the owner

- Location and version of the actual engine source.
- Required IPC, Egyptian, and Saudi editions, adoption details, and local amendments; select the first profile for verification.
- Initial system module and building/use types.
- Intended users, input/output workflow, unit systems, and deployment environment.
- Availability of authoritative reference material and independently checked example projects.

The local source folder has been identified, but its contents still need to be made available to the review environment. Source access and initial design scope need immediate resolution. Architecture and tooling decisions should follow the source review.
