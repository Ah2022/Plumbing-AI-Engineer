# Plumbing AI Engineer

A plumbing engineering project intended to help plumbing designers develop, check, and document building plumbing systems against a selected code edition and local requirements.

**Review status:** source inspection pending. As of 26 October 2026, the supplied GitHub baseline contains a README and MIT license. The owner identified a separate local engine folder, but its files are not available in the cloud workspace. The capabilities below are proposed review/improvement targets; existing implementation status is unverified.

## Purpose

Plumbing design requires more than choosing pipe diameters. Engineers must establish the governing requirements, select an applicable sizing method, validate inputs, check system constraints, and explain each result.

The proposed engine will bring these steps into a reproducible workflow. Calculation outputs should show the inputs, units, assumptions, equations or lookup rules, governing references, and checks needed for engineering review.

## Proposed scope

| Area | Intended capability | Current status |
| --- | --- | --- |
| Design basis | Record jurisdiction, adopted code and edition, amendments, occupancy, units, and design criteria | Proposed |
| Domestic water | Fixture demand, demand conversion, pipe selection, pressure losses, residual pressure, and velocity checks | Proposed |
| Sanitary drainage | Drainage fixture loading and applicable branch, stack, and building-drain sizing checks | Proposed |
| Venting | Applicable vent sizing, developed-length, trap-arm, and arrangement checks | Proposed |
| Hot water and stormwater | Separate modules with their own approved design basis and verification | Later scope |
| Engineering reports | Reproducible calculation records and schedules with rule references and review status | Proposed |
| AI assistance | Explain verified results and help prepare structured inputs for engineer confirmation | Proposed |

**Required code families:** IPC, Egyptian plumbing code, and Saudi plumbing code, selected according to the project. Exact editions, adoption, local amendments, and system coverage must be confirmed for each project. Each family needs a separately verified rule package; a shared interface must not silently mix their fixture values, sizing methods, or exceptions. Implementation and compliance coverage remain unverified.

## Intended design workflow

1. Select and approve the project design basis.
2. Define fixtures, pipe segments, elevations, equipment, operating conditions, and network connections.
3. Validate the model and identify missing or unsupported information.
4. Run a deterministic calculation using the approved rule set.
5. Review sizing constraints, pressure checks, exceptions, and references.
6. Export a calculation report and record the engineer's review.

Results should distinguish **pass**, **fail**, **not evaluated**, and **not applicable** for each check. An incomplete or unsupported model must not receive an overall compliance pass.

## Proposed architecture

The architecture remains subject to review of the actual source code and owner approval.

| Component | Responsibility |
| --- | --- |
| Project model and unit layer | Store explicit units, fixture classifications, network topology, elevations, and design conditions |
| Versioned rule packages | Store code applicability, references, approved table data, exceptions, amendments, and validation status |
| Calculation kernel | Apply deterministic demand, hydraulic, sizing, and constraint calculations |
| Validation layer | Check inputs, topology, applicability, calculation bounds, and unresolved requirements |
| Report generator | Preserve inputs, assumptions, rule versions, results, limitations, and reviewer decisions |
| Interface and optional AI layer | Collect inputs and explain results through the validated engine |

AI-generated text should not define authoritative rules, invent table values, or bypass calculation validation. Rule data and numerical calculations need explicit versions and independent verification.

## Getting started

The supplied GitHub baseline has no runnable application. Setup for the owner's local engine cannot be documented until its files are available. To review the documentation:

```bash
git clone https://github.com/Ah2022/Plumbing-AI-Engineer.git
cd Plumbing-AI-Engineer
```

- Read the [project assessment](docs/PROJECT_ASSESSMENT.md) for the verified repository baseline and audit limits.
- Review the [phased improvement plan](docs/IMPROVEMENT_PLAN.md) for deliverables, dependencies, approval gates, and acceptance criteria.
- Provide the engine source repository, branch, or files so the provisional plan can be revised against the real implementation.

Build commands, dependencies, configuration, and examples will be documented once the implementation is available and verified.

## Development and validation

The first implementation milestone should establish a reproducible development environment and independent engineering benchmarks. Proposed validation includes:

- Hand-checked reference calculations tied to the selected code edition.
- Tests for table boundaries, unit conversion, invalid inputs, and unsupported arrangements.
- Network examples covering critical pressure paths, drainage loading, and vent constraints.
- Reproducible report checks and automated regression checks for each supported rule package.

No calculation or application tests were run: the supplied GitHub baseline has no implementation or test suite, and the local engine files are unavailable to this review.

## Change approval

The assessment, roadmap, and this README are documentation deliverables. Implementation phases require owner approval before work begins. Approval of one phase does not authorize subsequent phases or changes to the governing code, engineering methods, or application architecture.

## Contributing

Propose a scoped change with its engineering basis, affected code edition, expected behavior, and validation evidence. Cite code clauses or table identifiers where applicable, and distinguish mandatory provisions from engineering recommendations. Keep licensed code content and project data out of public contributions unless redistribution is permitted.

## Engineering use

The planned tool supports engineering analysis. Project applicability, local amendments, installation conditions, and final design acceptance require review by the responsible engineer and relevant authority.

## License

This repository is licensed under the [MIT License](LICENSE). Third-party standards and reference data may have separate usage and redistribution terms.
