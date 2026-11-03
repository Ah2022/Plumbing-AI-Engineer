# Public benchmark candidates

Public repositories extend software coverage. They do **not** supply a professionally signed, adopted-code plumbing design or unlock engineering acceptance. This registry is separate from `validation/phase1a` and the 55 internal engineering reference candidates.

Use **Release Readiness → Public benchmark candidates**. The source register lists six exact repository commits. Case cards state scope, source terms, pinned bytes and limitations. Install missing pinned bytes through the card, run an installed candidate explicitly, and download its findings. Application runs save results under private `.review/public_benchmarks/`; the CLI can export to a chosen results directory. Project calculations and approval records are not created by these runs.

Every result has:

```text
PUBLIC_BENCHMARK
SOFTWARE_REFERENCE_ONLY
ENGINEERING_REVIEW_REQUIRED
acceptance_eligible = false
code_compliance_status = NOT_EVALUATED
```

`REAL_OPEN_DATA_UNCALIBRATED` additionally identifies a real-data candidate where applicable. It is not assigned to a synthetic/regression fixture merely because its repository also contains municipal data. Changing an approval label cannot promote public-tagged records through the engineering acceptance gate.

## Source screen

| Source | Installed/registered use | Provenance and terms |
| --- | --- | --- |
| [SWMMCanada](https://github.com/Zhonghao1995/SWMMCanada) | A small DWF test fixture is installed. Graham Creek is registered separately as an unreproduced real-open-data study. | MIT source notice retained. Generated models are described upstream as first-pass/uncalibrated; underlying municipal and observation data need per-source review. The test fixture is software-only. |
| [KIOS EPANET Benchmarks](https://github.com/KIOS-Research/EPANET-Benchmarks) | Hanoi steady-state H-W/LPS mapping comparison; raw input is retained **locally only**. | No repository-level licence was identified in the inspected metadata/tree. Raw models are not redistributed here; file-specific terms and attribution need review. |
| [OWA EPANET examples](https://github.com/OpenWaterAnalytics/epanet-example-networks) | Pinned source register; no bundled model or executed comparison is claimed. | No repository-level licence was identified. Some examples also require explicit US-unit, pump, tank/control or quality mapping beyond this first comparison adapter. |
| [1729 SWMM5 Models](https://github.com/SWMMEnablement/1729-SWMM5-Models) | One screened EPA-folder linear-links model is installed. | Root Unlicense retained. Upstream explicitly cautions that contributed folders such as Greenville, Simon_EPA and Special need separate provenance review. A root notice is not blanket approval of every folder. |
| [CoordProof OpenBIM MEP](https://github.com/Taz33m/coordproof-openbim-mep) | Mechanical-room IFC and semantic inventory CSV are installed for adapter comparison. | Apache-2.0 licence and NOTICE retained. Coordination/identity/unit evidence is distinct from hydraulic design validation. No upstream scripts are executed. |
| [GIS-to-SWMM5](https://github.com/AaltoUrbanWater/GisToSWMM5) | Pinned reproducible-generation workflow register. | MIT code notice identified; external DEM/land-use/rainfall rights remain separate. No generated catchment model or calibration is claimed in this increment. |

All commits, Git blob IDs, raw SHA-256 values, source paths, case limits and redistribution decisions are in `validation/public_benchmarks/catalogue.json`. Source files were checked against the pinned Git blob IDs before installation. A commit/checksum establishes source-byte identity, not professional source authentication or numerical correctness.

## Implemented comparisons

**SWMMCanada DWF fixture.** Runs the pinned source model through the installed native SWMM toolkit, checks declared node/link counts and routing conservation, and reports original-unit to SI conversion. This is not a municipal-network calibration or a reproduction of the Graham Creek study.

**EPA linear links.** Retains the original model parameters and event. Declared constant 0.5 CFS inflow supplies an independent steady outfall-flow check. In the executed SWMM 5.2.4 run, the model reaches that flow but fails the 1% routing-continuity criterion: approximately **3.3983% error and 48 nonconverged node-steps**. It is intentionally reported **FAIL**. The adapter does not loosen limits, tune the source or turn that run green.

For both SWMM cases, the execution copy appends explicit node/link/subcatchment reporting directives because an upstream input may omit output selection. This reporting-only change, the derived execution-input checksum and the original source checksum are recorded separately. Hydraulics, event, timestep and boundary parameters remain unchanged. These are native model checks, not automatic equivalence with every `dynamic_drainage` calculation or a validated `storm_storage` case.

**Hanoi mapping.** Original native EPANET input is compared with an explicitly normalized engine graph. It currently supports steady H-W/LPS sources/junctions/pipes with constant patterns. Numeric identifiers are mapped reversibly. Unsupported pumps, tanks, valves, controls, nonconstant patterns, check valves, external files and nondefault fluid assumptions are rejected instead of discarded. Node pressures/demands and link flows are compared with an explicit absolute tolerance. Both paths use EPANET 2.2: this is a same-backend mapping regression, **not an independent physical or engineering reference**. Native warnings/version/library checksum are retained. Raw Hanoi input is excluded from public Git under `local_sources/`.

**CoordProof IFC.** Upstream semantic CSV names/classes are compared with the plumbing objects extracted by the existing IFC adapter. Multiplicity, stable identity and millimetre-to-metre conversion are checked. Declared port counts, cross-scope unresolved relations and missing axis geometry are reported. Unsupported MEP classes and hydraulic connectivity remain unevaluated; no complete authoring-tool round trip or plumbing sizing approval is implied.

The executed pinned IFC yielded **12 supported plumbing objects and 12 declared port relations**, with **zero axes measurable by this adapter** and **two cross-scope relations**. Its semantic comparison passes; geometry and complete hydraulic connectivity do not. These gaps are displayed with the result instead of being hidden by its software PASS.

Three actual execution reports are bundled under `validation/public_benchmarks/recorded_results/` and shown in the UI before a fresh run. They include the original source/case/runner checksums and execution time. These are recorded observations, not independent golden engineering targets; source/runner changes hide stale results. The retained EPA failure is included. Local-only Hanoi data and reports are not bundled.

**Registered only.** Graham Creek, OWA examples and GIS generation return `SOURCE_REGISTERED_ONLY` and have no run button until a reviewed, complete pinned input bundle and comparison are added. Published plots, reported bias or a reproduction script are not an executed comparison in this engine. No observed rainfall/gauge series has been imported, calibrated or compared here.

## Reproduction

Install the optional native/model dependencies as required:

```bash
python -m pip install -r requirements-hydraulics.txt -r requirements-models.txt
python -m tools.public_benchmarks --list
python -m tools.public_benchmarks --case swmmcanada-dwf-fixture --run --output outputs/canada-dwf.json
python -m tools.public_benchmarks --case swmm-epa-linear-links --run --output outputs/epa-linear.json
python -m tools.public_benchmarks --case coordproof-ifc-semantic --run --output outputs/coordproof.json
```

The EPA command exits nonzero for its retained failed checks. Missing native libraries or inputs are reported separately from `PASS`. Tests verify the failure remains a failure; a passing test of failure handling does not approve the failed model.

For local-only Hanoi, establish applicable source terms, then import the **exact pinned source bytes** or explicitly fetch the catalogue URL for local evaluation:

```bash
python -m tools.public_benchmarks --case epanet-hanoi-local --import-file path/to/Hanoi.inp
# Or, an explicit local-only fetch from the pinned upstream URL:
python -m tools.public_benchmarks --case epanet-hanoi-local --fetch
python -m tools.public_benchmarks --case epanet-hanoi-local --run --epanet-library path/to/epanet2.dll --output outputs/hanoi.json
```

Fetch is never automatic during page rendering or tests. It permits only the catalogue's repository/commit/path, refuses redirects, caps source bytes and verifies SHA-256 before installing. The importer never executes upstream Python/R/build scripts. Native INP external file/save interfaces and path-like references are rejected; workers have bounded model/output sizes and a 60-second timeout. Arbitrary URLs, archives and unreviewed input substitutions are not accepted.

## Curating additional evidence

Add a case only after checking that specific folder/file's origin and terms, pinning all model/data dependencies and retaining notices. Define the supported adapter scope, units, independent comparison target, tolerances, expected warnings and calibration status. Keep original source bytes and any deliberate execution transformations separate. Do not manufacture expected hydraulic values by copying engine outputs; same-backend reruns must be labelled as such.

Stormwater observations, field calibration and complete municipal model generation need additional pinned input/observation bundles. Pump curves/ratings, clinical medical-gas criteria, code fixture sizing, recirculation, acoustics, stress, water hammer and vessel acceptance still need appropriate manufacturer, authority, specialist or independently reviewed project evidence. Public candidates never fill those acceptance gaps automatically.
