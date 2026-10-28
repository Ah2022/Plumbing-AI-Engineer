# Phase 5: scoped plumbing engineering modules

The **Engineering Modules** workspace covers the twelve requested priorities through the existing general-pressure solver and scoped calculation tools. This guide covers the original thirteen tools. Eight additional methods (22 registered scopes including general pressure) are documented in [extended methods and medical gases](ADVANCED_PLUMBING.md). It shows the selected tool's calculation scope, required source data, validation status and unevaluated requirements **before** its inputs or calculation controls. All outputs retain `REVIEW_REQUIRED`, partial coverage and code compliance `NOT_EVALUATED`.

This is an implementation of the explicitly listed calculation scopes below. It does not claim complete engineering/code coverage for every subject. Wet/circuit/AAV rules, trap-pressure protection and transient behavior require particular care: the implemented screens are deliberately distinguished from a complete code-arrangement checker or a coupled air/water/transient solver.

## Prioritized scope register

| Priority | Implemented calculation | Source data required | Explicit remaining scope |
| --- | --- | --- | --- |
| 1 | Existing general graph/EPANET boundary: loops, pumps, tanks, valves, PDA, EPS and seven scenarios | Reviewed hydraulic model, demands, heads, curves and controls; configured toolkit | Independent project/code acceptance, thermal/gravity/transient coupling |
| 2 | Pump/system curve operating intersection using tabular H-Q interpolation and `H = Hstatic + R Q²` | Manufacturer H-Q data; reviewed static head and resistance in m/(L/s)² | Looped-system curve extraction, active control, pump trim and complete equipment acceptance |
| 3 | No-draw thermal circulation flow, selected return temperatures, individual loop heads and balancing deficits | Complete parallel-loop supply/return length and W/m losses, density/cp, bores, Darcy factors, K and temperature criteria | Shared-trunk losses, mixing/control dynamics, hygiene and commissioning |
| 4 | Fixture nominal connection, design-flow and residual-pressure checks | Referenced fixture/code/manufacturer minimums, nominal designation mapping and simultaneous hydraulic results | Fixture listing, full supply-network adequacy and code adoption |
| 5 | Circular-pipe Manning capacity, normal depth, wetted area/perimeter, hydraulic radius and velocity | Actual bore, energy/bed slope under uniform-flow assumptions, Manning n, independent design L/s and fill/velocity criteria | DFU-to-L/s inference, unsteady/surcharged/backwater network and solids transport |
| 6 | Constant evaporation seal budget, measured/modelled air-pressure criterion check and hydrostatic equivalence | Seal/exposure/evaporation data, independently measured/validated pressure peaks and explicit limits | Trap geometry, oscillation, siphonage, two-phase air-pressure prediction and seal-break certification |
| 7 | Wet, circuit and AAV supplied applicability/count/DFU/nominal rules and attributed geometry/listing/relief conditions | Applicable code criteria and manufacturer listing/capacity/clearance; fixture floors/types/loads; geometry assertions | Complete Chapter 9/other-code exceptions, automatic CAD geometry review, stack sizing and authority approval |
| 8 | Static backwater HGL/protection and flood-rim screen; free-weir or fully wetted orifice capacity | Common-datum levels, downstream HGL, reviewed device requirement, dimensions and outlet coefficients | Valve reliability/closure, sewer transients, submerged weirs and partially wetted/submerged openings |
| 9 | Modified Puls single level-pool storage routing with mass balance and dry/storage-range limits | Independent inflow hydrograph and monotone level/storage/outflow rating over the whole event | Rainfall-runoff calibration, distributed sewer routing, downstream coupling and extrapolated overflow |
| 10 | Supplied simultaneous fire-duty margins, storage allocation and directional separation paths | Reviewed hydraulic fire case and criteria; classified layout/device direction; usable volume and dedicated reserves | NFPA/local authority certification, actual device testing/listing and physical reserve drawdown/interlocks |
| 11 | Pump/tank catalogue candidate filtering by duty/curve, fluid, pressure/temperature rating, NPSH or usable storage | Imported source-bound model rows, manufacturer/document/revision/page, duty-specific efficiency/NPSHr or usable capacity | Purchasing/endorsement, trim/preferred operating region, viscosity corrections and certified final selection |
| 12 | Velocity/noise-risk and matching measured acoustic criterion; simple single-line surge; water/pipe expansion and ideal vessel acceptance | Reviewed acoustic criteria/metrics, wave speed/closure/fluid/pressure data, densities/alpha/temperatures and vessel pressures | dBA prediction, room/support acoustics, network MOC/column separation, arrestor sizing, restrained-pipe stress and manufacturer vessel acceptance |

Priority 12 is offered as three tools so each has its own input/source and validation contract. The pressure-network tool opens **Network Review → General pressure network** rather than creating a second hydraulic engine.

## Use and source handling

Open [the local engine](http://localhost:8504/), select a project, then **Engineering Modules**. Select the tool in priority order. Its scope/source/validation panel is always visible. A matching executed software-evidence record is required before new calculation controls are available. Missing or stale evidence hides those controls and explains why.

The default packages are explicitly **fictional software demonstrations**, marked `SYNTHETIC` and `UNVERIFIED`. Values such as temperatures, fixture minimums, DFU limits, acoustic limits, manufacturer models and rainfall/storage data in those examples are **not normative code or authentic product data**. Replace them with reviewed project/code/manufacturer inputs. No manufacturer catalogue or copyrighted code table has been invented or silently borrowed.

Use the native fields/tables or structured-data view, or upload a complete JSON engineering input package. Download an example/current package to see the schema. Pump/storage curves, fixture schedules and recirculation loops use editable tables; complex nested catalogue records remain in structured data or an uploaded package. Source documents and their revisions/locators are editable source records.

Each input package contains:

```json
{
  "schema_version": "engineering-input-1",
  "module": "fixture_minimum",
  "code_id": "IPC",
  "code_edition": "2024",
  "basis_reference": "Project calculation basis and assumptions",
  "sources": [
    {
      "id": "PROJECT-SOURCE",
      "type": "PROJECT",
      "document": "Reviewed calculation or exact code/manufacturer source",
      "revision": "R1",
      "locator": "Page/table/curve and applicable condition",
      "verification_status": "UNVERIFIED"
    }
  ],
  "data": {
    "source_id": "PROJECT-SOURCE",
    "fixtures": []
  }
}
```

Complete executable input examples are in `examples/engineering/`. Source types are `CODE`, `MANUFACTURER`, `PROJECT`, `MEASURED`, `METHOD_REFERENCE` or `SYNTHETIC`. Every `source_id` must resolve. Real catalogue rows must bind to manufacturer source records; synthetic demonstrations are allowed only with that explicit classification. A document name can contain its public URL; a locator should identify the specific revision/page/curve and applicability. An optional lowercase `sha256` records a supplied document checksum, not document authenticity.

Source review is either `UNVERIFIED` or `REVIEWED_AS_REPORTED`; the latter requires the reviewer's name. It is an attributed assertion and cannot promote a result to verified/approved. Original code adoption and independent engineering acceptance remain separate. The page enforces the active project's code/edition, and its state is scoped to the project and basis revision. It does not silently convert a foreign-source criterion into an adopted-code requirement.

The result includes explicit units, each criterion comparison and source ID, intermediate traces, original input/source package, a canonical input checksum, software-validation status and unevaluated scope. Inputs/source edits hide previous findings until recalculated. **Save engineering review record** requires a record ID and recording reviewer. Saved results integrate with Report / Export and QA/QC and remain unapproved even if the project's basis has been verified. Calculations and source data are local to the project database; uploads/signed records are not automatically sent to GitHub.

## Mathematical definitions and boundaries

**Pump/system curves.** Pump H-Q points must have strictly increasing flow and decreasing head. Piecewise-linear pump interpolation intersects the explicitly supplied quadratic single-circuit system. Bisection stays inside the published curve range; a missing intersection is `NOT_EVALUATED`, with no extrapolated duty point. EPANET's three-point power-curve interpolation is a different method, not silently equated to the piecewise-linear catalogue method. See the [Hydraulic Institute operating-point explanation](https://datatool.pumps.org/pump-fundamentals/combined.html).

**Recirculation.** Heat loss is the supplied length times W/m loss. Required flow follows `heat / (rho cp allowable ΔT)`. Selected flow gives a calculated return temperature. Loop head uses explicit Darcy f, bore, length, fitting K and balancing loss at the selected flow. The maximum loop head governs; differences identify additional balancing head. Each record must represent a **complete parallel loop**, including supply/return heat loss and resistance. Shared headers need separate loss analysis. Elevation is not added as static lift in a closed circulation loop. Minimum temperatures are supplied criteria, not a hardcoded hygiene standard. [Caleffi's recirculation method](https://www.caleffi.com/en-us/blog/2-single-loop-recirculation-systems) describes the heat-loss/temperature-drop basis.

**Fixture minimums.** Nominal designation and actual bore are separate. A DN20/16mm-bore product is checked against its reviewed nominal minimum using20, not16. Source inches require an explicit designation mapping; the engine does not treat DN as inches converted to millimetres. Fixture flow and pressure must represent the relevant simultaneous design case. The [IPC water-supply chapter](https://codes.iccsafe.org/content/IPC2024V2.0/chapter-6-water-supply-and-distribution) is a review target; its numeric criteria must be authenticated before design acceptance.

**Gravity flow.** Circular segment area and wetted perimeter determine `R=A/P`; Manning gives `Q=A R^(2/3) sqrt(S)/n` in SI. The normal-depth solution is restricted to the increasing free-surface branch with maximum fill no greater than0.9D. This avoids ambiguous near-full solutions. Design flow above the allowed capacity produces a failed capacity check and no invented depth. Zero flow remains finite; a supplied minimum-velocity criterion can still fail. A lower-velocity screen does not certify self-cleansing. See [USACE uniform-flow guidance](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/stable-channel-design-functions/uniform-flow-computations).

**Trap/venting.** Positive and negative pressure inputs are **nonnegative peak magnitudes** from an independent measurement/air model. `|Δp|/(rho g)` is reported as water-head equivalence, not directly subtracted from trap seal or used as a dynamic seal-failure prediction. Evaporation is a separately stated constant-rate estimate. Wet/circuit/AAV limits are supplied from reviewed applicable code/listing data; geometry flags are attributed assertions, not an automatic layout proof. AAV checks require capacity, clearance, listing/orientation/accessibility and an atmospheric relief path; AAV admission does not relieve positive pressure. Alternative engineered arrangements are outside this screen. Review the [IPC vents chapter](https://codes.iccsafe.org/content/IPC2024V2.0/chapter-9-vents) and applicable jurisdiction/product evidence.

**Backwater/overflow.** The external HGL is compared with connection invert and flood rim in a common datum. A protection assertion cannot prove actual device reliability. Free rectangular-weir discharge uses a supplied dimensional coefficient; full-opening orifice flow uses a supplied Cd and effective head to the centre/tailwater. Submerged weirs and partly wetted/submerged orifices return `NOT_EVALUATED`. No universal discharge coefficient is silently chosen. These are local outlet/static screens, not a dynamically coupled sewer model.

**Storage routing.** Modified Puls uses trapezoidal continuity and the supplied storage/outflow rating. Outflow is limited by available water at dry storage. Exceeding the rating range stops the computation before that unsupported interval: the reported excess is the first unrouted requirement, not a simulated discharge/overflow hydrograph or the total excess for the remainder of the storm. Mass balance applies to the computed prefix only. The rating must begin at zero active storage/outflow, increase in storage/level and be nondecreasing in outflow. See [USACE Modified Puls equations](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/modified-puls-model).

**Fire separation.** Fire-duty inputs must come from the reviewed simultaneous hydraulic scenario, such as the existing EPANET fire-demand overlay. The `separate_systems` screen disallows connected paths under the supplied strict policy. `shared_supply_with_backflow` traces potential fire-to-domestic contamination paths with user-reviewed one-way barriers/air gaps in the given direction. It does not authenticate a device listing or model reserve drawdown/interlocks. Allocation arithmetic prevents double-counting the same usable storage. Fire authority/NFPA/local requirements remain separate review items.

**Catalogue selection.** Only supplied pump/tank products are screened. Pump head is interpolated at the required duty flow without extrapolation; pressure/temperature/fluid compatibility and duty-specific efficiency/NPSHr are explicit. Tank checks use supplied **usable** capacity. All rejected models retain reasons, and eligible models remain candidates. The engine neither purchases equipment nor endorses a brand. Actual trim, operating region, test tolerances, viscous corrections, certification and manufacturer usable acceptance must be reviewed. No real manufacturer products are bundled in the examples.

**Noise/surge/expansion.** Velocity/noise risk is compared only with a supplied criterion. Measured noise and limit must have explicitly matching metric/weighting/statistic and an operating-condition reference; the engine does not generate a dBA prediction from velocity. Surge uses `Δp=rho a |ΔV|` for rapid changes and the stated `min(1,2L/(a t))` factor for a single-line linear-velocity closure screen. It reports rating and low absolute-pressure/vapour margins; it is not a network method-of-characteristics or column-separation solver. Wave speed and pressure criteria require reviewed sources. [KSB's water-hammer guidance](https://live-resources-e2e-sales.ksb.com/resource/blob/762108/b03ed4dd6aa0139a876090d66fe3b9f2/water-hammer-data.pdf) explains the rapid-change estimate and its limitations.

Water expansion uses `Vcold*(rhoCold/rhoHot-1)` when positive; free pipe elongation uses `alpha L ΔT`. Ideal vessel gas acceptance uses **absolute** precharge/fill/maximum pressures with the supplied polytropic exponent. Precharge must not exceed cold fill, and fill must be below maximum. The result is theoretical gross volume, not a certified membrane/usable-volume or relief-system selection. See the [manufacturer discussion of absolute precharge/test pressures](https://www.varem.com/en/technical-support/sizing-heating-expansion-vessels-vessels/). Actual product acceptance, temperature/fluid properties and structural restraint require separate engineering evidence.

## Validation and exposure

`validation/engineering/reference_cases.json` holds **41 fixed author-prepared candidate references** with inputs, expected values/status/completion, units/tolerances and hand derivations. Expected outputs were prepared using independent arithmetic/conditions, not copied from implementation results. They cover successful and failed duties, unsupported outlet conditions, all three venting modes, storage saturation, catalogue rejection, source conditions and transient/expansion limits. These candidates still require independent qualified-engineer review.

`validation/engineering/software_evidence.json` records executed comparisons and hashes of the complete engineering implementation and reference-case file. `engineering.registry.exposure_status()` only enables new tools when scope/source/validation metadata is explicit, matching executed evidence passes, and that tool is covered. Missing/stale evidence hides its calculation controls. Code/source changes cannot silently retain the previous software-evidence stamp.

```powershell
# Verify fixed references and refresh the SOFTWARE evidence after reviewed code changes.
# This command never changes expected outputs and never grants engineering approval.
python -m tools.validate_engineering

# Arithmetic, source/domain/failure contracts and all interactive module examples.
python -m pytest tests/test_engineering_modules.py tests/test_engineering_modules_ui.py -q
```

CI runs the module references and interface checks on Windows and Linux without private workbooks or catalogue files. Existing pressure/tree/EPANET tests remain in place. Phase 1 A's release gate now also tracks all 22 registered module scopes: individual accepted independent reference/source/signature evidence is required before they can be included in engineering acceptance. Supplied review metadata alone, a successful software benchmark or this implementation's screens cannot label the release verified. Private signed module records belong under `.review/engineering_validation/`, not in the public repository.
