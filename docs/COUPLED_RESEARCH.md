# Coupled engineering extension — first research increment

The engine now has **eight experimental methods** addressing the next seven development areas. They are numerical/evidence prototypes with fixed analytical candidates and regression checks. They are **not** complete building-drainage CFD, full code piping-stress analysis, a medical-gas certificate, or accepted real-project validation.

Open [the local app](http://localhost:8504/) → **Engineering Modules**. Research tools display an experimental warning, required sources, validation status and omitted scope before the calculation inputs. Every result/export carries `EXPERIMENTAL_RESEARCH_ENGINEERING_PENDING`, `REVIEW_REQUIRED`, partial coverage and code compliance `NOT_EVALUATED`. The original methods and tree evaluator remain separate.

| Requested development | Implemented first increment | Required next validation/scope |
| --- | --- | --- |
| Coupled drainage two-phase flow | Conservative chamber liquid storage/inertial filled links, compressible air, vents/AAVs and trap-displacement feedback. Liquid head includes computed air pressure; liquid/trap displacement changes the air pocket. | Measured rig comparisons; free-surface/annular/slug transitions, vertical entrainment and distributed air-wave propagation. |
| Solids and full vent behavior | Advected dilute suspended mass, empirical deposition/resuspension, conservative reservoir/vent exchange and positive/negative-pressure AAV behavior in the coupled model. | Discrete solids/rags, in-pipe beds, blockage, full stack geometry and comprehensive code vent arrangements. Existing wet/circuit/dry-vent/trap-arm/interval checks remain distinct. |
| Piping flexibility and structure-borne acoustics | Linear 3D six-DOF pipe frame; thermal strain, gravity, forces/moments, prescribed supports and springs. Harmonic mobility plus supplied inertia/damping/radiation data produces a structure-borne receiver estimate. | Elbow ovalization/flexibility, pressure thrust/Poisson displacement, support contact nonlinearity, fatigue, shell/building flanking paths and measured vibration/acoustic validation. |
| Hot-water hygiene, scald protection, draws and storage | Stratified tank and hot-line cells, makeup/draw advection, inversion mixing, heater hysteresis, TMV response and cold-loss shutoff, modeled mean water age, temperature-band exposure and hot dwell. | Actual TMV tests, draw/temperature measurements, hydraulic capacity, microbial/clinical evidence and project water-safety acceptance. |
| Medical-gas quality, AGSS, liquid sources and commissioning | Dedicated AGSS interface checks; liquid inventory/vaporizer N+1 and reserve; declared commissioning test matrix with uncertainty, methods/locations, calibration, revision and signoffs. | Real complete adopted-standard test scope, gas assays and authorized evidence. Certification remains `NOT_ISSUED`. No two-phase liquid-gas pipe solver or patient-circuit certification. |
| Manufacturer source authentication | Exact document/data checksums and detached Ed25519 signatures checked against independently enrolled server public keys; role, expiry and revocation checks. | Real manufacturer/reviewer keys and evidence. No fabricated trust, automatic vendor identity enrollment, PDF-signature parsing or claim that a signature proves numerical correctness. |
| Pressure-zone/PDA engineering | Model-hash-matched hydraulic report audit, zone pressure/service envelopes, boundary type/direction and demand-curve consistency. Native EPANET report regeneration is available. | Field-calibrated criteria, min/max-source and failure cases; heterogeneous zone PDA requires another backend/validated representation. No flow patching after solution. |

## Coupled drainage model

Each chamber holds incompressible liquid and an isothermal ideal-gas air pocket. Liquid level and air pressure form its hydraulic head. Fully flooded connecting pipes have inertial momentum and Darcy/minor losses:

```text
air volume = chamber volume - liquid volume + trap-leg area * displacement
p_air = air mass * R_specific * T / air volume
H = invert + liquid volume / chamber area + (p_air - p_atmosphere)/(rho_liquid*g)
dQ/dt = g*A/L * (H_from-H_to) - (f*L/D+K)*Q*abs(Q)/(2*L*A)
```

Vents use supplied linear volumetric resistance and upstream gas density. Open vents can exchange air in either direction; an atmospheric AAV admits air but cannot release positive pressure. An optional equal-leg U-trap oscillator changes the chamber air volume, which feeds back into its forcing pressure.

Solids are a **dilute well-mixed tracer**: liquid transfer transports donor concentration; supplied first-order deposition/resuspension exchanges suspended and bed mass. The bed is a chamber inventory, not a predicted pipe obstruction. The output checks separate water, air and total-solids mass balances, including reservoirs and external inflows. Conservative Heun integration reduces steps when positivity would be lost; pocket collapse, loss of liquid submergence, trap breach or supplied domain limits stops/rejects the calculation.

This reduced-order implementation does not reproduce established distributed drainage-transient methods. [Heriot-Watt's research](https://researchportal.hw.ac.uk/en/publications/numerical-modelling-of-air-pressure-transient-propagation-in-buil/) provides the context for distributed unsteady air modeling and mechanical boundaries. Comparisons with those methods and laboratory measurements are future acceptance work, not a validation claim for this prototype.

## Pipe-frame and structure-borne models

The flexibility model assembles Euler–Bernoulli straight circular elements with axial, torsional and biaxial bending stiffness in global 3D coordinates. Constraints are prescribed `ux/uy/uz` in metres and `rx/ry/rz` in radians. Springs use N/m for translations and N·m/rad for rotations. Temperature strains generate equivalent element loads. Pipe/fluid gravity and supplied nodal forces/moments are included. Unsupported mechanisms and ill-conditioned restraint systems are rejected.

Reported displacements, end forces and physical reactions are checked against supplied limits. A membrane-pressure/end-force/bending/torsion stress screen is also reported; pressure membrane stress is **not** a pressure-thrust or Poisson displacement load. Do not double-count externally supplied pressure loads. The model excludes elbow flexibility/ovalization, nonlinear contacts, fatigue and ASME stress-category certification. [COMSOL's pipe-mechanics theory](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_theory.06.163.html) explains why pipe mechanics requires additional pressure/fluid effects beyond a beam frame.

Structure-borne response solves `(K - omega² M + i omega C) u = F`, with coherent RMS force/moment phasors per frequency and explicit positive lumped inertia on every free DOF. Rayleigh damping and radiator parameters require reviewed measurements. Pipe, fluid and equipment masses must be represented consistently in those supplied inertias; they are not automatically added twice. Radiated power uses `sigma * rho_air * c * area * v_normal_RMS²`, then the supplied direct/diffuse room transfer and A weighting. This is one modeled vibration/radiation path, not a full building-acoustic simulation.

## Hot-water validation model

Layers are ordered **bottom to top** with individual volume, initial temperature/mean age, UA and heater power. Tank draw introduces cold makeup at the bottom. Hot water leaves the top for separate fixture-line cells. Interlayer conduction and conservative inversion mixing preserve energy. An energy residual covers tank plus all modeled hot lines, heaters, ambient losses, makeup enthalpy and withdrawn hot enthalpy.

Fixture events specify mixed demand, start/end and cold availability. Overlapping events at the same fixture are rejected. TMVs use either ideal mixing or a supplied first-order hot-fraction response, plus an explicit cold-loss closing delay. A closed valve can prevent scald exposure **and still fail the demand-service check**. The model does not certify a valve's response, supply pressure or capacity.

Temperature-band volume-time, modeled mean water age and per-layer hot dwell support investigations. They do not predict bacterial counts or certify thermal disinfection. Applicable storage/delivery/scald criteria must be selected from the project basis; the examples are fictional. [HSE guidance](https://www.hse.gov.uk/legionnaires/hot-and-cold.htm) distinguishes Legionella controls and scald protection, while [EnergyPlus's engineering reference](https://energyplus.net/assets/nrel_custom/pdfs/pdfs_v24.1.0/EngineeringReference.pdf) documents layered tank energy modeling. Neither is substituted for project-specific engineering/clinical acceptance.

## Medical systems and evidence

**AGSS** has a dedicated method. It requires explicit AGSS/vacuum service, reference flows, plant/source pressure and interface-specific flow/suction/listing/exhaust references. The shared isothermal network mathematics does not import medical-vacuum terminal criteria. Generic medical-gas calculations continue to reject AGSS, N2O and CO2 as unsupported services for that generic method. The AGSS prototype does not model patient breathing circuits, room dispersion or capture/exposure performance.

**Liquefied-gas source inventory** uses supplied service-specific density/latent heat, tank fill/unusable stock, demand and condition-rated vaporizer mass/heat capacity. Usable mass and reference gas, peak duty, N+1 capacity, conservative unrecovered boiloff and reserve duration are calculated. It is not a phase-equilibrium, icing/de-rating, two-phase pipe, relief or reactive-gas safety model. Real supplier authorization and plant approval remain necessary.

**Commissioning evidence** is a declared test matrix, not an automatically complete standards checklist. Measurements must match units, method, physical location and system revision. The entire uncertainty interval must fit the supplied limit; stale calibration, missing tests or role records fail completeness. Records can cover identity, cross-connections, pressure/leakage, particles, gas quality, alarms, plant, AGSS and liquid-source tests. Source assertions and names cannot authenticate test execution, appointments, professional competence or clinical authority. Even complete reported evidence returns `certification_status = NOT_ISSUED`. Use the adopted [HTM reference and authorized commissioning process](https://www.england.nhs.uk/publication/health-technical-memorandum-02-01-medical-gas-pipeline-systems/).

## Source authentication setup

Install `python -m pip install -r requirements-source-authentication.txt`. Configure `PLUMBING_SOURCE_TRUST_STORE` to a private server-owned JSON file. **Do not enroll a key merely because it accompanies an upload.** Independently establish the issuer identity, role and key fingerprint through an authorized channel. No private signing key is handled by the app.

```json
{
  "schema_version": "source-trust-1",
  "keys": [{
    "key_id": "INDEPENDENTLY-ENROLLED-KEY-ID",
    "issuer": "Verified organization or reviewer",
    "role": "MANUFACTURER",
    "public_key_base64": "BASE64_OF_32_BYTE_ED25519_PUBLIC_KEY",
    "identity_evidence": "Out-of-band identity/key verification record",
    "not_before": "2026-01-01",
    "not_after": "2027-01-01",
    "revoked": false
  }]
}
```

The example above is a schema template with an invalid placeholder, **not a trust anchor**. Keep real trust records and documents private. `ENGINEERING_REVIEWER` is a distinct role; it cannot masquerade as a manufacturer release.

In equipment, relief or liquid-source tools, download the **exact source/data signing payload** after entering the final source record and numerical rows. The external signer supplies an attestation with `source_id`, a `manifest`, and `signature_base64`. Upload the exact source document separately. The manifest contains:

```text
schema_version: source-attestation-1
key_id, issuer, subject
data_sha256: SHA256(canonical downloaded payload)
document_sha256: SHA256(exact document bytes)
issued_on, expires_on: ISO dates
purpose: MANUFACTURER_DATA_RELEASE or ENGINEERING_SOURCE_REVIEW
```

Signing bytes are the manifest serialized as sorted-key compact JSON, ASCII escapes enabled, no nonfinite numbers and no trailing newline. Payload hashing uses the same canonical serialization; document hashing uses raw bytes. The detached Ed25519 signature signs those manifest bytes. Numerical/source revisions, different bytes, wrong purpose/issuer, unknown/revoked keys and invalid dates invalidate verification. Documents are limited to 2 MB in this increment.

Valid results distinguish `SIGNATURE_AND_CONTENT_VERIFIED` from `REVIEWED_AS_REPORTED`. Only listed source IDs are covered; no other input is promoted. Identity still depends on trusted enrollment and the local offline revocation snapshot. [NIST's signature standard](https://csrc.nist.gov/pubs/fips/186-5/final) and [the library's Ed25519 interface](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) describe signatures; a verified signature does not establish numerical correctness, certification or product fitness. PDF/PAdES, X.509 chain validation and vendor API retrieval are not implemented.

## Pressure-zone engineering

Assign every network node to exactly one zone and identify every cross-zone link with reviewed direction and PRV/PSV/booster/open treatment. Define pressure envelopes, minimum delivered fraction and calibrated PDA parameters. The report's normalized network and input hash must match the current model. After edits, use **Solve current model with EPANET for zone review**; the bundled report is a fictional hand reference.

Every snapshot is checked for pressure and demand service. The PDA curve at the reported pressure is a **consistency check**, not a replacement flow calculation. EPANET 2.2 has one global PDA profile: differing zone profiles are flagged as unrepresented and cannot pass acceptance. No node flow is patched after hydraulic solution. DDA/zero-demand cases do not establish actual pressure-dependent capacity. Field calibration and peak, minimum-source, static maximum-pressure and control-failure scenarios remain required. See [EPANET](https://www.epa.gov/water-research/epanet) and the original solver guide.

## Verification and release boundary

The original 41 frozen candidates are preserved; 14 analytical/condition-action candidates were appended. They cover sealed-air compression, solids conservation/settling, beam deflection/rotation, thermal restraint, forced harmonic mobility, hot draw/mixing, cold-loss protection/service failure, AGSS, inventory, commissioning gaps and PDA service. Signature tamper/role/trust tests use fictional keys and documents generated in test directories. Native EPANET comparisons and timestep/coordinate-invariance checks supplement these candidates.

Run `python -m tools.validate_engineering` after reviewed implementation changes, then `python -m pytest tests/ -q`. Evidence fingerprints now include `engineering/*.py` and `solvers/*.py`. Stale evidence hides module controls. Passing candidates do not constitute independent engineering validation; real-source/rig/vendor/clinical comparisons and signed qualified review remain pending.
