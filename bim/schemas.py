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
    if payload.get('units', 'SI') != 'SI': errors.append('Extract units must be explicit SI')
    if payload.get('schema_version', '1.0') != '1.0': errors.append('Unsupported extract schema version')
    for key in ('revit_model_name','extracted_at'):
        if not isinstance(payload.get(key),str) or not payload[key].strip(): errors.append(f"Missing/invalid '{key}'")
    if 'revit_model_id' in payload and (not isinstance(payload['revit_model_id'],str) or not payload['revit_model_id'].strip()):
        errors.append('Invalid revit_model_id')
    seen=set(); unique_ids=set(); count=0
    definitions=[('pipes',REQUIRED_PIPE_FIELDS),('fixtures',REQUIRED_FIXTURE_FIELDS),('tanks',REQUIRED_TANK_FIELDS),('pumps',REQUIRED_PUMP_FIELDS),('valves',REQUIRED_PUMP_FIELDS)]
    for group,required in definitions:
        items=payload.get(group,[])
        if not isinstance(items,list): errors.append(f'{group} must be an array');continue
        count += len(items)
        for i,item in enumerate(items):
            label=f'{group}[{i}]'
            if not isinstance(item,dict): errors.append(label+' must be an object');continue
            missing=required-set(item)
            if missing: errors.append(label+f': missing required field(s) {sorted(missing)}');continue
            eid=item.get('revit_element_id')
            if not isinstance(eid,str) or not eid.strip(): errors.append(label+': invalid element ID')
            elif eid in seen: errors.append(label+': duplicate element ID')
            else: seen.add(eid)
            unique_id=item.get('revit_unique_id')
            if unique_id is not None:
                if not isinstance(unique_id,str) or not unique_id.strip(): errors.append(label+': invalid Revit UniqueId')
                elif unique_id in unique_ids: errors.append(label+': duplicate Revit UniqueId')
                else: unique_ids.add(unique_id)
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
    if count > 10000: errors.append('Partition extracts larger than 10000 objects; no silent truncation is supported')
    if 'inventory' in payload:
        try:
            inventory=payload['inventory']
            if not isinstance(inventory,dict) or not isinstance(inventory.get('objects'),list) or not isinstance(inventory.get('connections'),list):
                raise ValueError('Inventory requires objects and connections arrays')
            if len(inventory['objects'])>10000:raise ValueError('Inventory exceeds 10000 objects')
            by_id={};port_ids=set();element_ids=set()
            for obj in inventory['objects']:
                uid=obj['source_id'];eid=obj['element_id']
                if not isinstance(uid,str) or not uid or uid in by_id or not isinstance(eid,str) or not eid or eid in element_ids:
                    raise ValueError('Duplicate/invalid inventory stable or element IDs')
                by_id[uid]=obj;element_ids.add(eid)
                if obj['kind'] not in ('pipe','fitting','fixture','pump','tank','valve'):raise ValueError('Unsupported inventory kind')
                for key in ('nominal_mm','internal_mm','length_m'):
                    if obj.get(key) is not None:finite(key,obj[key],positive=True)
                for key in ('flow_lps','elevation_m','horizontal_run_m'):
                    if obj.get(key) is not None:finite(key,obj[key])
                for key in ('start_xyz_m','end_xyz_m'):
                    if obj.get(key) is not None:
                        if len(obj[key])!=3:raise ValueError('Source endpoint must have three SI coordinates')
                        for value in obj[key]:finite(key,value)
                for port in obj['ports']:
                    port_id=port['source_id']
                    if not isinstance(port_id,str) or not port_id or port_id in port_ids:raise ValueError('Duplicate/invalid inventory port ID')
                    port_ids.add(port_id)
                    if port.get('origin_xyz_m') is not None:
                        if len(port['origin_xyz_m'])!=3:raise ValueError('Port origin needs three SI coordinates')
                        for value in port['origin_xyz_m']:finite('port coordinate',value)
            for group,_ in definitions:
                for item in payload.get(group,[]):
                    obj=by_id.get(item.get('revit_unique_id'))
                    if obj is None or obj['element_id']!=item['revit_element_id']:
                        raise ValueError('Linked extraction rows do not match inventory identities')
                    if item.get('source_facts') is not None:
                        from bim.revit_extract import source_facts
                        if item['source_facts']!=source_facts(obj):
                            raise ValueError('Linked source facts differ from physical inventory')
            for link in inventory['connections']:
                if not all(isinstance(link.get(k),str) and link[k] for k in ('from_port','to_port')):
                    raise ValueError('Connection requires explicit port identities')
        except (ValueError,KeyError,TypeError) as error:
            errors.append('Invalid physical inventory: '+str(error))
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
    "PLM_Technical_Status", "PLM_Review_Status", "PLM_Source_SHA256",
    "PLM_Required_Available", "PLM_Selected_Available", "PLM_Result_Available",
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
