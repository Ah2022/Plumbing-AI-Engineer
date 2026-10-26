# Supplied calculation sheets: code attribution and integration

The source audit below records the initial integration. The current UI uses portable `.plmcalc` forms; see [Interactive calculations](INTERACTIVE_CALCULATIONS.md).

Reviewed 26 October 2026. The two supplied ZIPs contain **48 distinct calculation workbooks** after excluding temporary `~$` lock files. The originals are retained byte-for-byte in the local source library. No workbook instructions or VBA were executed.

These files are a mixed reference collection, not a single IPC 2024 package. Attribution below records claims in worksheet labels, formula-generated labels and supporting data sheets. It does not certify table values, identify an unstated edition or establish adoption for a project. Embedded images and drawings have not been exhaustively verified.

| Group | Files | Identified basis |
| --- | ---: | --- |
| Water supply | 14 | IPC Appendix E, ASHRAE 2011, Steel's *Engineered Plumbing Design*, Qatar Kahramaa, and manufacturer/catalogue methods |
| Drainage and stormwater | 19 | IPC 709/710 and 1106; UPC Appendix H / Table 1014.3.6; NSPC including 2009; ASPE; British guidance; Egyptian 301/1; Qatar Kahramaa / Ashghal; some unidentified methods |
| Pools and water features | 6 | Selectable ASPE, Egyptian Code 301 Part 3, and manufacturer methods; exact editions are not established |
| Fuel gas | 3 | Natural gas explicitly cites NFPA 54 **2018**; LPG tank cites ASPE **2013** and NFPA 58 without an NFPA edition; LPG pipe publisher/edition remains unidentified |
| Fuel oil / petrol | 2 | ASPE **2001**, Volume 3, Chapter 7, with supporting handbook/textbook references |
| Medical gas | 4 | HTM-02 Part A, Chapters 3/4 and Appendix G; pipe data also contains legacy HTM 22 labels |

ASHRAE/ASPE handbooks, engineering textbooks and manufacturer catalogues are design references. They do not by themselves establish the project's governing code. The user's IPC 2024 verification target remains unchanged; none of these sheets was silently merged into its approved rules or numeric tables.

## Edition and applicability findings

- The ASHRAE heater worksheets explicitly name **2011**, Table 10, page 50.20. The mixed-use file cites that source on `Data-1!A3`, rather than on its main calculation sheet.
- The Steel heater file mixes sources: its electric/gas/boiler worksheets cite chapter 16, but its solar worksheet cites ASHRAE 2011.
- Condensate drainage cites **NSPC 2009**, Chapter 9. Septic sizing cites **NSPC 2009**, Chapter 16. Sand interception cites NSPC 6.4.2 without an edition.
- The oil-interceptor reference sheet explicitly labels **UPC 2015**; this does not establish the edition of every other UPC workbook.
- Gray/non-potable tank worksheets offer different jurisdiction/method choices. Their population guide cites **NFPA 101 2018**, which is an occupancy basis and not evidence that NFPA 101 is their plumbing sizing code.
- Medical-gas sheets abbreviate their reference as HTM-02. NHS publishes the related medical-gas guidance as **HTM 02-01 Part A**; the workbook's edition and HTM 22 data lineage still require review. [NHS guidance](https://www.england.nhs.uk/publication/health-technical-memorandum-02-01-medical-gas-pipeline-systems/).
- IPC section/table numbers establish a code family, not a unique edition. These workbooks cannot be labelled IPC 2024 solely from those numbers. [ICC sanitary-drainage chapter](https://codes.iccsafe.org/content/IPCSP2024P1/capitulo-7-drenaje-sanitario).
- UPC Table 1014.3.6 is titled **Gravity Grease Interceptor Sizing**. The hydromechanical workbook's Method-2 cites it, so its applicability needs explicit review. [IAPMO 2015 contents](https://codes.iapmo.org/docs/2015/UPC/2015%20UPC%20Table%20of%20Contents.pdf).
- NSPC is a separate code family from IPC and UPC. [IAPMO NSPC](https://iapmo.org/codes-standards-development/code-development/national-standard-plumbing-code). NFPA 54 is the National Fuel Gas Code; the workbook's stated 2018 edition is retained rather than relabelled as the current publication. [NFPA 54](https://www.nfpa.org/codes-and-standards/5/4/nfpa-54).

## Source defects and evaluation limits

The medical-gas source note at `SA7!A45` pairs the same psi value with two different kPa values; it requires source review. The water-supply pipe file contains twelve saved `#N/A` results in `Calculations!AE47/AG47/AI47`, rows 49, 51 and 52. The mixed-use heater file contains an external workbook link. Medical-gas pipe formulas include `WEIGHT2SUM`, which has no supported implementation here. Several source approximate-lookup ranges are unsorted, some LOOKUP vectors have unequal extents, and the roof-gutter file requires unsupported array/implicit-intersection behavior.

These conditions are exposed as missing/unsupported calculations, without substituting saved caches or a largest catalogue size. The medical-gas custom function may lie in an inactive IF branch for the supplied sample; a matching sample cache does not prove that branch works after changed inputs. No guidance for clinical use is established by this formula reproduction.

Fresh-versus-cache comparison evidence is in [WORKBOOK_REPRODUCTION.json](WORKBOOK_REPRODUCTION.json). The supplied sample states contain 10,018 formulas: 9,940 matched their saved values, one numeric result differed, 72 were unavailable and five required unsupported behavior. Counts describe supplied sample states only. An unresolved numeric rounding difference occurs in the gray-water tank's `ASPE!T39`; fresh reproduction and saved cache are both shown for selected results. Neither is automatically treated as an independent benchmark.

## What is added to the engine

The **Calculation Sheets** page provides system/workbook/worksheet selection, exact source identity, cell-level reference labels, source warnings and source cell/formula inspection. With a project open, select output cells and supply JSON overrides to existing non-formula cells in the selected calculation sheet. Recalculation preserves source units/rounding and saves the full formula trace, input overrides, original source hash and project governance snapshot. Results can be downloaded as JSON.

The interpreter handles an explicitly bounded subset including arithmetic, IF, SUM, lookup/index functions, rounding, INDIRECT ranges and named references. It never invokes VBA, Python `eval`, Excel automation, network links or external workbook fetches. Unknown functions, circular references, oversized ranges, malformed inputs and broken references fail explicitly. Results are `CALCULATED_NOT_APPROVED` / `REVIEW_REQUIRED`; this is a reference-workbook scenario feature, not conversion of all 48 methods into independently verified native engineering modules. Cached source values remain clearly distinct from fresh results.

Source packages are installed locally and ignored by Git. The public repository contains the reader, evaluator, metadata catalogue, tests and attribution/reproduction evidence. A public clone can inspect the catalogue; it needs the supplied originals to recalculate their formulas. Original source files and embedded standards/catalogue data have not been published.

```bash
# Run from the engine root; copy originals locally and register their hashes
python -m workbooks.library PATH_TO_FIRST_ZIP PATH_TO_SECOND_ZIP

# Reproduce the cache comparison after import; this does not verify engineering
python -m tools.check_workbook_reproduction --output comparison.json
```

Source revisions get distinct hash identities. Re-importing an unchanged source retains its identity and review notes. Changing the catalogue or evaluator changes governed engine fingerprints, requiring recalculation of prior project results. Original application databases were not altered by this review.

## Workbook-by-workbook attribution

The table below is generated from the inspected metadata. “Primary” refers to references found on calculation worksheets; “all references” additionally includes supporting tables and reference sheets. Manufacturer labels and auxiliary references do not imply a governing code.

| Workbook | Primary method labels | All reference families |
| --- | --- | --- |
| 01-Water Supply System/Boiler Hot Water Circulation Pump.xlsm | ASHRAE | ASHRAE |
| 01-Water Supply System/Central EWH Mixed Use.xlsm | MANUFACTURER | ASHRAE, MANUFACTURER |
| 01-Water Supply System/Central Water Heater Sizing - ASHRAE Method.xlsm | ASHRAE, MANUFACTURER | ASHRAE, MANUFACTURER |
| 01-Water Supply System/Central Water Heater Sizing - Dr. Steel Method.xlsm | ASHRAE, MANUFACTURER, STEEL_TEXTBOOK | ASHRAE, MANUFACTURER, STEEL_TEXTBOOK |
| 01-Water Supply System/Drinking Chilled Water Sizing.xlsm | IPC, STEEL_TEXTBOOK | IPC, STEEL_TEXTBOOK |
| 01-Water Supply System/Hot Water Circulation Pump.xlsm | IPC, STEEL_TEXTBOOK | ASHRAE, IPC, STEEL_TEXTBOOK |
| 01-Water Supply System/Individual Storage Water Heater Sizing.xlsm | ASHRAE | ASHRAE |
| 01-Water Supply System/Instantaneous Water Heater Sizing.xlsm | IPC, STEEL_TEXTBOOK | IPC, STEEL_TEXTBOOK |
| 01-Water Supply System/Thermal Expansion Tank Sizing.xlsm | MANUFACTURER | MANUFACTURER |
| 01-Water Supply System/Water Meter Sizing For Qatar.xlsm | QATAR_KAHRAMAA | ASPE, EGYPT_301, IPC, QATAR_KAHRAMAA |
| 01-Water Supply System/Water Supply Booster Pump.xlsm | IPC | IPC |
| 01-Water Supply System/Water Supply Filter.xlsm | UNIDENTIFIED | MANUFACTURER |
| 01-Water Supply System/Water Supply Pipes Sizing.xlsm | IPC | IPC |
| 01-Water Supply System/Water Supply Softener Sizing.xlsm | MANUFACTURER | MANUFACTURER |
| 02-Drainage System/Condensate Drain Pipe Sizing.xlsm | NSPC | NSPC |
| 02-Drainage System/Gravity Grease Interceptor Sizing.xlsm | UPC | MANUFACTURER, UPC |
| 02-Drainage System/Gray Water Tank Sizing.xlsm | ASPE, EGYPT_301, IPC, NFPA_101, QATAR_KAHRAMAA | ASPE, EGYPT_301, IPC, NFPA_101, QATAR_KAHRAMAA |
| 02-Drainage System/Hydromechanical Grease Interceptor Sizing.xlsm | BRITISH_GUIDANCE, MANUFACTURER, STEEL_TEXTBOOK, UPC | BRITISH_GUIDANCE, MANUFACTURER, STEEL_TEXTBOOK, UPC |
| 02-Drainage System/Lint Interceptor Sizing.xlsm | MANUFACTURER, UPC | MANUFACTURER, UPC |
| 02-Drainage System/Neutralization Tank Sizing.xlsm | ASPE, MANUFACTURER | ASPE, MANUFACTURER |
| 02-Drainage System/Non Potable Water Tank Sizing.xlsm | ASPE, EGYPT_301, IPC, NFPA_101, QATAR_KAHRAMAA | ASPE, EGYPT_301, IPC, NFPA_101, QATAR_KAHRAMAA |
| 02-Drainage System/Oil Interceptor Sizing.xlsm | BRITISH_GUIDANCE, MANUFACTURER, NSPC, UPC | BRITISH_GUIDANCE, MANUFACTURER, NSPC, UPC |
| 02-Drainage System/Sand Interceptor Sizing.xlsm | NSPC | NSPC |
| 02-Drainage System/Sanitary Drainage - Tie In.xlsm | BRITISH_GUIDANCE, IPC | BRITISH_GUIDANCE, IPC |
| 02-Drainage System/Sanitary Drainage Pipe Sizing.xlsm | IPC | IPC |
| 02-Drainage System/Septic Tank Sizing.xlsm | NSPC | NSPC |
| 02-Drainage System/Soakaway Sizing.xlsm | QATAR_ASHGHAL | QATAR_ASHGHAL |
| 02-Drainage System/Storm Catch Basin Sizing.xlsm | UNIDENTIFIED | IPC |
| 02-Drainage System/Storm Drainage - Tie In.xlsm | IPC | IPC |
| 02-Drainage System/Storm Drainage Pipe Sizing.xlsm | IPC | IPC |
| 02-Drainage System/Storm Roof Gutter Sizing.xlsm | STEEL_TEXTBOOK | STEEL_TEXTBOOK |
| 02-Drainage System/Storm Tank Sizing.xlsm | IPC, QATAR_ASHGHAL | IPC, QATAR_ASHGHAL |
| 02-Drainage System/Sump Pit Sizing.xlsm | UNIDENTIFIED | UNIDENTIFIED |
| 03-Pools & Water Features/Fountain Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, EGYPT_301, MANUFACTURER |
| 03-Pools & Water Features/Jacuzzi Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, BRITISH_GUIDANCE, EGYPT_301, MANUFACTURER |
| 03-Pools & Water Features/Lake Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, EGYPT_301, MANUFACTURER |
| 03-Pools & Water Features/Lazy River Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, EGYPT_301, MANUFACTURER |
| 03-Pools & Water Features/Swimming Pool Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, EGYPT_301, MANUFACTURER |
| 03-Pools & Water Features/Waterslide Sizing.xlsm | ASPE, EGYPT_301, MANUFACTURER | ASPE, EGYPT_301, MANUFACTURER |
| 05-Gas System/LPG Pipe Sizing.xlsm | UNIDENTIFIED | UNIDENTIFIED |
| 05-Gas System/LPG Tank Sizing.xlsm | ASPE, NFPA_58 | ASPE, MANUFACTURER, NFPA_58 |
| 05-Gas System/Natural Gas Pipe Sizing.xlsm | NFPA_54 | NFPA_54 |
| 06-Fuel System/Fuel Equipment Sizing.xlsm | ASPE | ASHRAE, ASPE, STEEL_TEXTBOOK |
| 06-Fuel System/Petrol Station Sizing.xlsm | ASPE | ASHRAE, ASPE, STEEL_TEXTBOOK |
| 07-Medical Gas System/Medical Gas Flow Rate.xlsm | HTM_02 | HTM_02 |
| 07-Medical Gas System/Medical Gas Pipe Sizing.xlsm | HTM_02 | HTM_02, HTM_22_LEGACY |
| 07-Medical Gas System/Medical Gas Source Sizing.xlsm | HTM_02 | HTM_02 |
| 07-Medical Gas System/Medical Gas Terminal Units.xlsm | HTM_02 | HTM_02 |

## Software verification

The complete local engine/UI suite passed **288 tests** with no expected failures. Forty-six new tests cover independently calculated spreadsheet semantics, archive intake, shared-formula expansion, invalid inputs, source hashing, unsupported formulas and project scenario persistence. Cache comparison is additional reproduction evidence and is not included in that test count.
