"""
bim/schemas.py  —  Phase 7
--------------------------------
The JSON exchange contract between the Revit side (bim/pyrevit/, running
inside Revit's process) and the engine side (bim/exchange.py, running
standalone — per spec Section 27: "Revit is never responsible for the
core engineering math"). Both sides of that boundary import this module,
so the shape can't drift between what the extractor writes and what the
engine reads.

Two payload directions:
  EXTRACT  (Revit -> Engine): what the pyRevit extractor script emits —
           pipes/fixtures/tanks/pumps as they exist in the model right now.
  RESULTS  (Engine -> Revit): calc_id/status/required/selected/reference
           per Revit element, keyed by revit_element_id, for the pyRevit
           writer script to push back onto PLM_* shared parameters.

Field names and units here are fixed points -- if a field is renamed here,
both the extractor script and the writer script must be updated together,
which is exactly why this module exists as the single shared contract
instead of two hand-synced JSON shapes.
"""

from __future__ import annotations

REQUIRED_PIPE_FIELDS = {"revit_element_id", "system", "length_m", "nominal_diameter_mm"}
REQUIRED_FIXTURE_FIELDS = {"revit_element_id", "family", "type_name"}
REQUIRED_TANK_FIELDS = {"revit_element_id", "tank_type"}
REQUIRED_PUMP_FIELDS = {"revit_element_id"}

VALID_PIPE_SYSTEMS = {"cold_water", "hot_water", "drainage", "vent", "storm"}


def validate_extract_payload(payload: dict) -> list[str]:
    import json
    from calculations.validation import finite
    errors=[]
    if not isinstance(payload,dict): return ['Payload must be an object']
    for key in ('revit_model_name','extracted_at'):
        if not isinstance(payload.get(key),str) or not payload[key].strip(): errors.append(f"Missing/invalid '{key}'")
    if 'revit_model_id' in payload and (not isinstance(payload['revit_model_id'],str) or not payload['revit_model_id'].strip()):
        errors.append('Invalid revit_model_id')
    seen=set()
    definitions=[('pipes',REQUIRED_PIPE_FIELDS),('fixtures',REQUIRED_FIXTURE_FIELDS),('tanks',REQUIRED_TANK_FIELDS),('pumps',REQUIRED_PUMP_FIELDS)]
    for group,required in definitions:
        items=payload.get(group,[])
        if not isinstance(items,list): errors.append(f'{group} must be an array');continue
        for i,item in enumerate(items):
            label=f'{group}[{i}]'
            if not isinstance(item,dict): errors.append(label+' must be an object');continue
            missing=required-set(item)
            if missing: errors.append(label+f': missing required field(s) {sorted(missing)}');continue
            eid=item.get('revit_element_id')
            if not isinstance(eid,str) or not eid.strip(): errors.append(label+': invalid element ID')
            elif eid in seen: errors.append(label+': duplicate element ID')
            else: seen.add(eid)
            if 'parameters' in item and not isinstance(item['parameters'],dict): errors.append(label+': parameters must be an object')
            for key in ('from_node','to_node','level'):
                if item.get(key) is not None and (not isinstance(item[key],str) or not item[key].strip()): errors.append(label+': invalid '+key)
            if group=='pipes':
                if not isinstance(item.get('system'),str) or item['system'] not in VALID_PIPE_SYSTEMS: errors.append(label+': system not one of supported systems')
                for key in ('length_m','nominal_diameter_mm'):
                    try: finite(key,item[key],positive=True)
                    except ValueError as e: errors.append(label+': '+str(e))
                for key in ('flow_lps','elevation_diff_m','slope_percent'):
                    if item.get(key) is not None:
                        try: finite(key,item[key],minimum=0 if key=='flow_lps' else None)
                        except ValueError as e: errors.append(label+': '+str(e))
            for key in required-{'revit_element_id','length_m','nominal_diameter_mm'}:
                if not isinstance(item[key],str) or not item[key].strip(): errors.append(label+': invalid '+key)
    try: json.dumps(payload,allow_nan=False)
    except (TypeError,ValueError): errors.append('Payload must contain finite JSON-compatible data')
    return errors


def empty_extract_payload(revit_model_name: str, extracted_at: str) -> dict:
    """Skeleton payload shape -- what the pyRevit extractor script builds up."""
    return {
        "revit_model_name": revit_model_name,
        "extracted_at": extracted_at,
        "pipes": [],
        "fixtures": [],
        "tanks": [],
        "pumps": [],
    }


# PLM_* shared parameter names the Results payload maps onto. Must match
# bim/revit/PLM_shared_parameters.txt exactly -- that file is the Revit-side
# registration of these same names/GUIDs.
PLM_PARAMETER_NAMES = [
    "PLM_Calc_ID", "PLM_Code_Status", "PLM_Required_Value", "PLM_Selected_Value",
    "PLM_Result_Value", "PLM_Result_Unit", "PLM_Reference",
]

# Status -> Revit OverrideGraphicSettings color (RGB), matching the
# STATUS_COLOR badge convention already used in app/db_helpers.py.
STATUS_OVERRIDE_COLOR_RGB = {
    "PASS": (0, 170, 0),
    "FAIL": (200, 0, 0),
    "WARNING": (230, 140, 0),
    "ASSUMED": (210, 190, 0),
    "MISSING_DATA": (150, 150, 150),
    "CALCULATED_NOT_APPROVED": (0, 110, 200),
}
