# IFC / DXF design-check pilot

Implemented 27 October 2026. Open **CAD / IFC Checks** in the [local engine](http://localhost:8504/).
**Update:** DWG and PDF uploads are now available through their distinct [conversion/drawing-review paths](DWG_PDF_UPLOADS.md).

This is an initial, local model-intake and per-pipe checking milestone. It does not certify whole-model code compliance.

## Install and use

```bash
python -m pip install -r requirements.txt -r requirements-models.txt
python -m streamlit run app/streamlit_app.py --server.port 8504
```

1. Open a project and its governing code profile. Select **CAD / IFC Checks**.
2. Upload IFC, DXF, DWG or PDF, or load a bundled IFC/DXF example. DWG geometry requires a confirmed companion DXF or a configured local converter; PDF opens a drawing-review path. There is no external translation service.
3. Inspect the source evidence: file hash, model identity, schema, original unit declaration and conversion, stable source IDs, system/layer, centreline dimensions, available property sets and explicit IFC port connections.
4. Keep a stable model identifier across revisions. Include the intended pipe objects; DXF linework is initially excluded because an architectural line is not inherently a pipe. Record reasons for exclusions.
5. Map cold water, hot water or drainage. Enter actual internal bore and design flow for water. For drainage, enter nominal size and independently reviewed start/end invert elevations, then confirm upstream-to-downstream direction. Reference each element's engineering inputs.
6. Enter the water velocity criterion and its source where applicable. Name the mapping reviewer/evidence, confirm the reviewed mapping, then **Run and save model checks**.
7. Inspect per-object findings and download JSON/CSV. Each saved calculation retains source objects, units, file hash, mapping hash, input references and project governance. Rechecking the same project/model supersedes its previous current model check while preserving history.

The supplied examples contain deliberately synthetic geometry and no licensed code-table data. For the synthetic water pipe, a test assignment of **1 L/s** through an actual **25 mm** internal bore gives approximately **2.037 m/s**. These are benchmark inputs to enter and review, not a project-design recommendation. The synthetic DXF drain has a **10 m** horizontal run; independent test inverts of **4.0 m** and **3.7 m** yield **3%**, deliberately different from its centreline slope. This proves the checker does not substitute centreline Z for invert levels; it also produces an explicit warning about the differing falls for review.

## Implemented boundary

| Area | Implemented | Explicit gaps |
| --- | --- | --- |
| IFC | Pipe/fitting/sanitary-terminal/pump/tank identities, type identity where available, system assignments, property sets, explicit port relationships, nested/rotated local placements and polyline Axis dimensions | No tessellated-body reconstruction, swept/mapped/trimmed-curve measurement, georeferencing, inferred connections or automatic property acceptance |
| DXF | Modelspace LINE, open straight LWPOLYLINE, open 3D POLYLINE, WCS coordinates and drawing-unit conversion with recorded override | Blocks/INSERTs, xrefs, paperspace, arcs, closed/curved polylines and arbitrary annotations are not interpreted; ignored entity counts remain visible |
| Water | Per-pipe `Q / actual internal area` against a referenced project velocity limit | Source pressure, complete topology, fitting/equipment losses, diversified fixture demand and terminal pressure require further network mapping |
| Drainage | Individual straight segment, confirmed direction, reviewed invert fall / extracted horizontal run; active-code minimum-slope lookup with no cross-code fallback | Connected DFU/capacity, stack intervals, intermediate grades within multi-segment polylines, vents and traps remain unevaluated |
| Governance | Project/basis-scoped intake state, stable model check target, retained calculation history, partial coverage and engineering-review status | No automatic code adoption, engineering approval or blanket compliance label |

Nominal, outside and internal diameters remain separate. Original IFC properties are evidence to review, not automatically converted engineering inputs. No proximity/crossing join is accepted as a hydraulic connection. Missing units reject import; missing engineering data produces findings rather than a pass. Negative drainage fall fails when a source minimum is available. Flagged slope-table rows remain warnings even when the numerical comparison passes.

The pilot accepts up to **20 MB** and **500 supported objects** per import. Larger models must be partitioned explicitly. Results always retain `PARTIAL` coverage and `REVIEW_REQUIRED`; individual checks may pass, fail, warn, or remain missing/unevaluated/unsupported. Unsupported geometry and excluded scope cannot be hidden by a later individual pass. An import is an unsaved draft until a check is saved; only that saved check supersedes the prior review of the same model identifier.

## Verification and next milestones

**Initial IFC/DXF pilot validation:** 346 full local regression tests passed; the final public build passed 271 tests (one source-dependent skip) and all 15 page-navigation checks without private workbooks. The model-specific suite contains 16 passing checks.

Real-parser synthetic tests cover millimetres, inches with explicit unit override, nested rotation, IFC systems/properties/ports, disconnected DXF crossings, measured plan run, missing units/axes, malformed files, missing bore, independent velocity and slope calculations, adverse fall, flagged/missing code data, multi-segment slope exclusions, mapping confirmation and project/model history isolation.

Next: agreed property/fixture mapping profiles; a reviewed IFC port-to-network graph with fittings and flow direction; transfer into the existing tree-network checks; independent authoring-model comparisons; then model highlighting and BCF exchange. Native DWG integration and full code-rule coverage remain separate work.

Parser references: [IfcOpenShell placements](https://docs.ifcopenshell.org/autoapi/ifcopenshell/util/placement/index.html), [IFC units](https://docs.ifcopenshell.org/autoapi/ifcopenshell/util/unit/index.html), [systems and ports](https://docs.ifcopenshell.org/autoapi/ifcopenshell/util/system/index.html), and [ezdxf polyline/WCS semantics](https://ezdxf.readthedocs.io/en/stable/tutorials/lwpolyline.html).
