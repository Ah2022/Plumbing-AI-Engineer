# Phase 1 A: engineering validation package

The package separates **software agreement**, **independent mathematical references**, and **authoritative engineering acceptance**. The designated reviewer is **BIM MANAGER**, as requested. Their individual identity, plumbing-engineering qualifications, independence and signed review have not been supplied. No engineer approval is claimed.

## Current acceptance

| Requested criterion | Evidence delivered | Acceptance state |
| --- | --- | --- |
| Five reference projects | Residential, office, hotel, hospital and mixed-use/commercial, each with model, frozen expected outputs, worked calculations, actual EPANET 2.2 output and a review form | Five fully specified **illustrative regression envelopes**; approved real building reference designs remain pending |
| Every supported calculation independently referenced | 26 native method cases plus five water/drainage project cases; all 29 public calculation entry points registered, including structural tree validation | Mathematical/lookup candidates exist for native scope; independent engineer/source authentication is pending |
| Converted calculation sheets | All 103 forms individually registered with package hash and worksheet name | **Independent expected engineering results missing**; existing formula-execution evidence is not counted as engineering validation |
| Every discrepancy explained | Ten terminal-pressure differences reconciled numerically to published EPANET conventions; hospital negative-pressure warning recorded separately | Explanations are prepared for engineering review; any new unexplained difference fails the golden comparison |
| No verified release from synthetic tests | Release evidence and interface explicitly show `ENGINEERING_VALIDATION_PENDING`; authored candidates cannot satisfy the real-reference gate | Enforced and regression-tested |

**Authoritative Phase 1 A acceptance is not complete.** Filling all missing cases and obtaining a qualified independent engineer's review are necessary. Creating files, successful formula evaluation, a software PASS, a job title or a checksum cannot establish those facts.

## Review the five projects

Open **Release Readiness** in the [local engine](http://localhost:8504/). Download **BIM MANAGER review package**. The ZIP contains the frozen references, input models, worked calculations, EPANET files/results, discrepancy register and independent worksheet arithmetic. It does not contain private project databases, licensed workbooks or solver binaries.

Each folder under `validation/phase1a/projects/` contains:

- `input.json`: explicit SI water tree, separate DFU drainage tree, stipulated flow/pressure/material/size criteria, equipment inputs, code-edition target, scope exclusions and a manually declared path/load schedule.
- `expected.json`: pipe nominal sizes **and separate internal bores**, flows, velocities, friction/local losses, terminal pressure margins, governing path, selected-system results, expected warning identifiers and unevaluated requirements.
- `hand-calculations.md`: equations, substituted values and numerical results that can be reproduced without importing any production calculation function.
- `epanet.inp` and `epanet-results.json`: steady-state demand-driven water model and actual external solver output, including version, input hash, library hash and warnings.
- `review.json`: pending review decision bound to the exact input and expected-output SHA-256 values.

These are intentionally small, fully specified test envelopes. Occupancy/building labels provide context; they do not infer diversity, fixture counts or code fixture units. They are not complete construction-design submissions, as-built models or approved project designs. Pipe sizes are prescribed design candidates checked against stipulated criteria; these goldens do **not** prove globally optimal automatic sizing or all greedy-upsize branches. Drainage uses a fictional lookup fixture and does not turn DFU into L/s. The hospital envelope deliberately has insufficient source pressure and must fail.

The IPC **2024** edition is the first verification target. Numeric code tables, local adoption, amendments, manufacturer bores, roughness, pressure criteria and rainfall applicability are **not authenticated by this package**. Their review targets are recorded in `sources.json`. Fictional table rows use explicit reference labels; the adapter's database confidence flag describes a controlled lookup fixture, never approval of an IPC table. The legacy hot-water functions require an IPC table key; the reference text still states that the supplied fixture is fictional. The licensed workbooks are not copied into public reference files.

## Independent reference boundary

`validation/reference_math.py` uses high-precision Decimal worksheet arithmetic and independently declared flow/path schedules. It imports no production calculation, database, application or workbook module. `expected.json` values were prepared through this separate arithmetic, not captured from engine output. `method-cases.json` records fixed expected values, inputs, derivations, units, tolerances and source status. The production adapter reads those files and reports disagreement; it never updates them.

This provides implementation independence, **not independent human authorship or professional sign-off**. An independent engineer must verify the reference inputs and equations, replace stipulated/test-only data with authenticated applicable sources, resolve all open coverage entries and sign the expected outputs. Existing private workbook cached values cannot be substituted for that work.

`coverage.json` identifies all 29 native entry points and each of the 103 supplied forms. Native numeric examples are candidate references; tree-validation behavior is covered by independently specified model/path/load constraints. All entries retain pending engineering status. User-imported calculation packages and new formulas require additional project-specific references. Extraction completeness, full compliance-rule applicability, every jurisdiction and every possible algorithm branch are outside a single example's proof.

## EPANET reconciliation

The external comparison used the official OWA **EPANET 2.2**, version **20200**, Windows 64-bit toolkit. `epanet-provenance.json` records the official release URL and SHA-256 values for both download archive and library. Solver binaries are kept outside the repository.

The engine/hand form uses SI coefficient **10.67**, diameter exponent **4.8704**, and **g = 9.80665 m/s²**. EPANET 2.2 uses **4.727** and exponent **4.871** internally in feet/cfs, its published **28.317 L/cuft** conversion, and **0.02517 K/d⁴** for local loss. The measured terminal-pressure differences are approximately **0.004–0.024 m**. A separate equation using EPANET's published conventions reproduces each external pressure within **0.000001 m**; the project checks also compare branch flow. We have not widened a generic pressure tolerance to hide the difference.

See the [official EPA manual](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10113EM.TXT), OWA source [`hydcoeffs.c`](https://github.com/OpenWaterAnalytics/EPANET/blob/v2.2/src/hydcoeffs.c), [`types.h`](https://github.com/OpenWaterAnalytics/EPANET/blob/v2.2/src/types.h) and [`input1.c`](https://github.com/OpenWaterAnalytics/EPANET/blob/v2.2/src/input1.c). The discrepancy register records each value and pending engineering decision.

Hospital EPANET warning **6** records negative pressure in the deliberately inadequate demand-driven case. Forced demand at negative pressure is a mathematical comparison, not a physically delivered fixture flow. Booster/pressure-zone and pressure-dependent demand analysis require separate engineering work. EPANET is applicable to the pressurized water envelope; it does not validate this package's gravity drainage, hot-water hygiene, tank operation, manufacturer pump curve or whole-building compliance.

## Run the checks

```powershell
python -m pytest tests/test_engineering_validation.py -q
python -m tools.engineering_validation --output outputs/phase1a-comparison.json

# Rerun the actual external solver; supply the official EPANET 2.2 library.
python -m tools.engineering_validation --epanet-library C:/path/to/epanet2.dll --output outputs/phase1a-live.json

# Include live external comparisons in pytest.
$env:EPANET_LIBRARY = 'C:/path/to/epanet2.dll'
python -m pytest tests/test_engineering_validation.py -q
```

Normal CI compares frozen, recorded actual EPANET evidence and skips only the live-library test when the optional library is absent. The Windows CI job also downloads the pinned official release, verifies the archive checksum and reruns the external comparisons. The interface button uses recorded external runs and explicitly says so. No validation command modifies project calculations, rewrites a golden file or grants approval. CLI result exports cannot target the reference directory.

## BIM MANAGER review procedure

1. Identify the individual independent plumbing engineer, relevant qualifications and independence from implementation. A BIM management role by itself does not establish plumbing-engineering qualification.
2. Review all five inputs and expected outputs, source criteria, unit conversions, hand worksheets, failure cases, warnings and omissions. Supply approved independent real-project calculation reports or authenticated design examples for authoritative acceptance.
3. Authenticate the exact code edition, table/section, amendments and applicability. Record source page/table references and edition evidence; confirm manufacturer bore/roughness and project source-pressure/rainfall criteria. Missing sources remain open requirements.
4. Provide independent references for every converted form and any additional supported calculation or algorithm branch claimed within the release scope. Record each discrepancy, explanation, correction and retest. Expected outputs must not be regenerated from the implementation under review.
5. Complete the review records against the exact input and expected-output hashes. Include the reviewer name, credentials, independence/qualification declarations, findings, signed date, source-authentication evidence and signed-report hash. A rejected or incomplete review remains blocking.
6. Keep actual signed artifacts privately under `.review/engineering_validation/`, referenced by a relative `signature_artifact_path` and matching `signature_artifact_sha256`. Do not publish signatures, private real-project inputs or licensed sources to the public repository without separate authorization. Signature authenticity and qualifications require human verification; the software checks file integrity and evidence completeness only.
7. Preserve previous frozen references and their signed reports when revisions change. Introduce a reviewed replacement version, update the evidence manifest deliberately and rerun all affected checks. There is no automatic "accept current output as golden" or "approve all" control.

The manifest detects altered/missing reference files and newly unregistered native calculations/forms. Original authored test cases remain illustrative even if someone fills in approval metadata. They cannot, by themselves, grant an engineering-accepted release label. Technical software results, project adoption, qualified review and authoritative evidence are separate gates.
