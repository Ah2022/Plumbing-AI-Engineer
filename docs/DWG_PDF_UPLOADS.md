# DWG and PDF drawing uploads

The **CAD / IFC Checks** upload accepts **IFC, DXF, DWG and PDF**, up to **20 MB per file**. Processing stays local. Install the optional parsers with `python -m pip install -r requirements-models.txt` and restart Streamlit after updating dependencies.

## PDF

Inspect a PDF to see a page selector, rendered preview, extracted page text and source-file fingerprint. The intake supports up to 50 pages, caps text extraction at 100,000 characters per page and 500,000 overall, and bounds preview dimensions to 1,400 pixels. Text truncation and pages without readable text are identified explicitly. No OCR is performed.

Record a drawing-review note and its reviewer/evidence reference, then save or download the note. This is a document review, not an automatic plumbing calculation. Saved records retain `NOT_EVALUATED` technical/coverage status inside their report, a warning in the calculation register, and `REVIEW_REQUIRED` regardless of the project's code-adoption status.

PDF page sizes are in PDF points. They are not measured pipe lengths or verified drawing scale. Printed labels, centreline drawings, symbols and apparent crossings do not automatically establish internal bore, fixture units, hydraulic connectivity or invert levels. Use the existing IFC/DXF mapping workflow for numerical model checks.

## DWG

A DWG can be uploaded directly. The intake records its original hash and recognizable version signature. Header recognition alone is explicitly **not** validation of the drawing contents.

Geometry becomes available through either:

1. **A companion DXF export:** attach a DXF from the same DWG revision and confirm the pairing, then inspect again. Both original and DXF hashes are retained. Correspondence is a user-confirmed assertion, not an automated drawing-equivalence test.
2. **A locally installed ODA File Converter:** the app looks for a configured executable, the installed `ODAFileConverter` command, or the standard Windows ODA installation directory. Deployment administrators can set `PLUMBING_ODA_CONVERTER` to the executable's absolute path. The application never accepts an executable from the upload form and does not install the converter or send drawings to a cloud service.

Conversion uses isolated temporary input/output directories, fixed filenames and argument arrays with no shell, a 60-second timeout and a 20 MB DXF-output limit. The converter window is hidden on Windows. Output then enters the same unit, linework and mapping checks as a DXF upload. Exported handles are source evidence requiring review; they are not asserted to be original DWG object IDs.

**This workstation does not currently have ODA File Converter installed.** DWG metadata intake and the companion-DXF path are usable; direct native conversion requires that optional installation/configuration. Without conversion, the page shows **DWG conversion required**, offers drawing-review notes and prevents numerical model checks. Conversion failure likewise remains an actionable incomplete intake, not a pass.

The configured ODA invocation is covered by an isolated command/output/timeout contract test. Actual ODA conversion of an independently authored DWG remains unvalidated until that converter and a project drawing are available. The companion DXF parser is exercised with real synthetic DXF data.

## Verification

**Results:** 353 full local regressions passed. The source-only build passed all 23 model/drawing tests and 15 page-navigation checks without private workbooks. The synthetic PDF preview was rendered and visually checked.

Regression cases cover searchable and text-free PDFs, real PDF rendering, page limits and invalid headers; all four upload extensions and the size limit; DWG header-only readiness; confirmed/unconfirmed DXF pairing and both file hashes; isolated converter invocation and timeout; document-review persistence and non-certification; and unchanged IFC/DXF model checks.

Source semantics: [ODA conversion via ezdxf](https://ezdxf.readthedocs.io/en/stable/addons/odafc.html), [pypdfium2 support API](https://pypdfium2.readthedocs.io/en/stable/python_api.html). PDF text and raster previews are evidence for review, not design-code decisions.
