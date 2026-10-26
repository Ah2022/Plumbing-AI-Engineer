# -*- coding: utf-8 -*-
__title__ = "Extract"
__author__ = "Ahmed"
__doc__ = (
    "Walks plumbing Pipe and PlumbingFixture elements in the active model "
    "and writes a JSON extract matching bim/schemas.py's EXTRACT contract, "
    "for import into the plumbing-design-engine's SQLite project DB via "
    "bim/exchange.import_revit_extract(). This script only READS the "
    "model -- it makes no changes and needs no transaction."
)

import datetime
import json

from pyrevit import revit, DB, script, forms

import plm_config  # PlumbingEngine.extension/lib/plm_config.py

output = script.get_output()
doc = revit.doc


def pipe_length_m(pipe):
    loc = pipe.Location
    if not isinstance(loc, DB.LocationCurve):
        return None
    return DB.UnitUtils.ConvertFromInternalUnits(loc.Curve.Length, DB.UnitTypeId.Meters)


def pipe_diameter_mm(pipe):
    param = pipe.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
    if param is None or not param.HasValue:
        return None
    return DB.UnitUtils.ConvertFromInternalUnits(param.AsDouble(), DB.UnitTypeId.Millimeters)


def pipe_system_type_name(pipe):
    try:
        mep_system = pipe.MEPSystem
        if mep_system is not None:
            return mep_system.SystemType.ToString() if hasattr(mep_system, "SystemType") else mep_system.Name
    except Exception:
        pass
    param = pipe.get_Parameter(DB.BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM)
    return param.AsValueString() if param and param.HasValue else None


def level_name(element):
    try:
        level_param = element.get_Parameter(DB.BuiltInParameter.RBS_START_LEVEL_PARAM)
        if level_param and level_param.HasValue:
            level = doc.GetElement(level_param.AsElementId())
            return level.Name if level else None
    except Exception:
        pass
    return None


def collect_pipes():
    pipes = []
    skipped_unclassified = []
    collector = DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_PipeCurves).WhereElementIsNotElementType()
    for pipe in collector:
        system_name = pipe_system_type_name(pipe)
        engine_system = plm_config.classify_system(system_name)
        length_m = pipe_length_m(pipe)
        diameter_mm = pipe_diameter_mm(pipe)
        if engine_system is None:
            skipped_unclassified.append("{} (system type: {})".format(pipe.Id, system_name))
            continue
        if length_m is None or diameter_mm is None:
            continue
        pipes.append({
            "revit_element_id": str(pipe.Id.IntegerValue) if hasattr(pipe.Id, "IntegerValue") else str(pipe.Id.Value),
            "system": engine_system,
            "length_m": round(length_m, 3),
            "nominal_diameter_mm": round(diameter_mm, 1),
            "level": level_name(pipe),
        })
    return pipes, skipped_unclassified


def collect_fixtures():
    fixtures = []
    collector = DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_PlumbingFixtures).WhereElementIsNotElementType()
    for fx in collector:
        fx_type = doc.GetElement(fx.GetTypeId())
        family_name = fx_type.FamilyName if fx_type else None
        type_name = DB.Element.Name.__get__(fx_type) if fx_type else None
        mark_param = fx.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        fixtures.append({
            "revit_element_id": str(fx.Id.IntegerValue) if hasattr(fx.Id, "IntegerValue") else str(fx.Id.Value),
            "family": family_name or "Unknown",
            "type_name": type_name or "Unknown",
            "level": level_name(fx),
            "parameters": {"Mark": mark_param.AsString() if mark_param and mark_param.HasValue else None},
        })
    return fixtures


def main():
    pipes, skipped = collect_pipes()
    fixtures = collect_fixtures()

    payload = {
        "revit_model_name": doc.Title,
        "extracted_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "pipes": pipes,
        "fixtures": fixtures,
        "tanks": [],  # tanks/pumps are typically generic models/equipment --
        "pumps": [],  # extend collect_* the same way once your family naming is known
    }

    save_path = forms.save_file(file_ext="json", default_name="{}_extract.json".format(doc.Title))
    if not save_path:
        script.exit()
    with open(save_path, "w") as f:
        json.dump(payload, f, indent=2)

    output.print_md("### Extract complete")
    output.print_md("- Pipes extracted: **{}**".format(len(pipes)))
    output.print_md("- Fixtures extracted: **{}**".format(len(fixtures)))
    if skipped:
        output.print_md("- **{} pipe(s) skipped** (system type didn't match "
                         "plm_config.SYSTEM_NAME_KEYWORDS -- edit that list):".format(len(skipped)))
        for s in skipped[:25]:
            output.print_md("  - {}".format(s))
    output.print_md("- Saved to: `{}`".format(save_path))
    output.print_md("\nNext: import this file in the plumbing-design-engine "
                     "(`bim.exchange.import_revit_extract`) or run `Run Analysis` "
                     "after calculations have been performed there.")


main()
