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
    """
    Validates a pyRevit extractor payload before it's trusted for import.
    Returns a list of human-readable errors; empty list = valid. Never
    raises -- the caller (bim/exchange.py) decides what to do with a
    non-empty error list (reject the whole import, per spec Section 30's
    "stop and report" philosophy -- a partially-valid Revit export is not
    silently partially imported).
    """
    errors: list[str] = []

    if "revit_model_name" not in payload:
        errors.append("Missing 'revit_model_name' (which Revit file this export came from).")
    if "extracted_at" not in payload:
        errors.append("Missing 'extracted_at' timestamp.")

    for i, pipe in enumerate(payload.get("pipes", [])):
        missing = REQUIRED_PIPE_FIELDS - set(pipe.keys())
        if missing:
            errors.append(f"pipes[{i}]: missing required field(s) {sorted(missing)}")
        elif pipe.get("system") not in VALID_PIPE_SYSTEMS:
            errors.append(f"pipes[{i}] (element {pipe.get('revit_element_id')}): "
                           f"system='{pipe.get('system')}' not one of {sorted(VALID_PIPE_SYSTEMS)}")

    for i, fx in enumerate(payload.get("fixtures", [])):
        missing = REQUIRED_FIXTURE_FIELDS - set(fx.keys())
        if missing:
            errors.append(f"fixtures[{i}]: missing required field(s) {sorted(missing)}")

    for i, tk in enumerate(payload.get("tanks", [])):
        missing = REQUIRED_TANK_FIELDS - set(tk.keys())
        if missing:
            errors.append(f"tanks[{i}]: missing required field(s) {sorted(missing)}")

    for i, pm in enumerate(payload.get("pumps", [])):
        missing = REQUIRED_PUMP_FIELDS - set(pm.keys())
        if missing:
            errors.append(f"pumps[{i}]: missing required field(s) {sorted(missing)}")

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
