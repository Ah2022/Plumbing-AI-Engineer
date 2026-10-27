# Interactive calculations and profile workflow

The former Calculation Sheets page showed a worksheet dump and required cell-address JSON. It also depended on XLSM files installed on the server. The replacement uses native, labelled forms backed by portable **`.plmcalc`** calculation packages.

## Use the calculation library

1. Open or create a project, then open **Calculation Sheets**.
2. Select a calculation and its method. Enter values in named fields and dropdowns. Long numeric schedules use an editable table. Conditional labels and applicable fields follow the selected method/shape where the source provides those formulas.
3. Click **Calculate and save**. Read labelled results and any missing-data or unsupported-method findings. Changing a draft input visibly marks the saved result as needing recalculation.
4. Open **References, source issues and portable calculation** to inspect references or download that calculation as `.plmcalc`. Source cells and formula traces remain available in the downloaded calculation report rather than in the normal input flow.

The supplied collection has been converted locally: **48 packages containing 103 forms**. Conversion retains formulas, named references, lookup data, input choices, labels, units and source identity. Original Excel files, formatting/images and VBA are not required to run a converted package. The format is structured JSON, not an executable browser extension or a renamed XLSM file.

## Use another computer or a deployed app

Open **Add Excel sheets or an interactive library**, select the converted library ZIP, and click **Import and convert**. Individual `.plmcalc`, `.xlsx`, `.xlsm` files and ZIPs of supported files are accepted. Excel uploads are converted within the app. Temporary Excel lock files are ignored. No terminal command or manual server-file installation is required.

Imports are saved in the active project's database and survive closing/reopening that database. They are isolated from other projects. Hosting that discards its SQLite database on restart will also discard those imports; retain the library ZIP and use persistent database storage for a durable deployment.

The public checkout includes a working synthetic flow/duration demonstration, so the UI remains usable without private workbooks. Actual converted libraries contain the supplied standards/catalogue data and are kept local or imported by the user; they are not published in this public repository. The private library can be exported from **Download a portable library**.

## Profile and review status fixes

The raw dictionaries containing `review_status`, `profile`, `basis_revision` and `adoption_status` have been removed from both normal page views. Native profile/revision summaries and readable adoption/review messages replace them. No SVG/HTML status renderer is used.

The profile picker now refreshes its edition reference before saving. Form state is scoped to the project, saved revision and selected profile, preventing edits/reviewer fields from leaking between projects. Existing running sessions receive the additive package-table migration without recreating their projects or calculations.

The adoption sequence is:

- Select the code profile, complete the project design-basis criteria and save the draft.
- Record the adoption reviewer, supporting evidence and explicit review confirmation.
- Approve project adoption. The recorded adoption state changes to approved; it persists on rerun.
- Editing the saved criteria creates a new revision, returns adoption to draft and invalidates prior current results. Saving identical criteria preserves the revision.

`DRAFT` was a real saved state, not a verification result. It must not be changed to approved merely to remove a message. Likewise, engineering review remains pending while dataset applicability, rules, benchmarks or independent engineering acceptance remain unresolved. The UI now explains this distinction and lists the missing design-basis fields and outstanding review reasons.

## Package integrity and limits

### Older converted libraries

Layout compiler version 2 automatically upgrades older checksum-valid packages. Earlier builds compared saved generated forms with the current inferred layout byte-for-byte and could reject intact calculations. The loader now verifies the original checksum and source/control structure, then regenerates an older layout using the current deterministic compiler. Source values, formulas, named references and original workbook identity are retained. The upgraded package records its prior package identity and receives a new checksum; exports can be reopened without another upgrade.

Blank-input discovery is ordered and its row index is rebuilt before labels are inferred, keeping compilation idempotent and stable across Python processes. Cache keys include the layout compiler version. Existing project packages can open in place without re-upload, and supported draft inputs carry forward. Calculations with identical titles receive distinct display labels so a project copy cannot silently switch to an example or installed copy.

Current-version altered form controls, modified source data with a stale checksum, and unsupported future layout versions still fail validation. A layout upgrade does not grant engineering approval.

Packages are versioned, size-bounded and checked against their content checksum. Input controls are regenerated/validated against the calculation cells. Only declared input fields can be changed; formulas/reference tables cannot be overwritten through the form. Package identity and input identity are saved with the result, alongside the project's governance snapshot. These checks detect corruption and bind results to their actual calculation package; they are not a publisher signature or engineering certification.

The existing bounded formula interpreter remains responsible for calculations. VBA, external workbook links, unknown functions, unsupported arrays and inconsistent source lookups are not replaced with saved cache values. Source units/rounding and known source issues are retained. Generated labels/controls are an interpretation of the supplied layout and still require engineering review before production use.

Every converted form was exercised with its supplied sample state, without reading an Excel file: [INTERACTIVE_FORM_CHECK.json](INTERACTIVE_FORM_CHECK.json). This is execution/reproduction evidence, not independent approval of the engineering methods. The source attribution and original-sheet issues remain in [CALCULATION_SHEETS_REVIEW.md](CALCULATION_SHEETS_REVIEW.md).

## Verification

The final local engine/UI suite passed **322 tests**. All 103 converted forms were also evaluated from their portable packages: 7,670 result cells calculated, 72 retained explicit missing/inconsistent-source findings and four retained unsupported-method findings. These counts are execution evidence, not engineering approval. The real filter and medical-gas terminal forms and Code Profiles were additionally loaded against a disposable copy of the three existing review projects, without a raw JSON renderer. The live additive migration retained all three projects and their saved code bases.

Compatibility fix verified on 27 October 2026: all 48 current packages and 125 archived package copies opened and round-tripped successfully. Seven added regression cases cover older layout upgrades, source integrity, draft/result identity, idempotent compilation and independent Python hash seeds. The live gray-water calculation was reopened in the browser after restarting the stale application process.
