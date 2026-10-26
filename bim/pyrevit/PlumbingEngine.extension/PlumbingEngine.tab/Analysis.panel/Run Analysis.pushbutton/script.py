# -*- coding: utf-8 -*-
__title__ = "Run\nAnalysis"
__author__ = "Ahmed"
__doc__ = (
    "Pulls the latest saved calculation results for this project from the "
    "plumbing-design-engine's SQLite DB (bim.exchange.export_results_for_revit "
    "-- the engine itself already ran; this script never re-derives a number, "
    "it only reads back what was calculated) and writes them onto PLM_* "
    "shared parameters on the matching Revit elements, then color-codes each "
    "element by status via a graphic override in the active view. "
    "Elements with no saved calculation are left untouched, not cleared."
)

from pyrevit import revit, DB, script, forms

import plm_config  # PlumbingEngine.extension/lib/plm_config.py

output = script.get_output()
doc = revit.doc
view = doc.ActiveView


def get_project_id():
    """The engine DB can hold multiple projects; ask which one this model
    corresponds to (matched by project_name) rather than assuming project_id=1."""
    conn = plm_config.get_engine_db_connection()
    rows = conn.execute("SELECT project_id, project_name FROM projects ORDER BY project_id").fetchall()
    conn.close()
    if not rows:
        forms.alert("No projects found in the engine DB ({}). Create one in the "
                     "Streamlit app first.".format(plm_config.ENGINE_DB_PATH), exitscript=True)
    choice = forms.SelectFromList.show(
        ["{} - {}".format(r["project_id"], r["project_name"]) for r in rows],
        title="Select engine project", multiselect=False,
    )
    if not choice:
        script.exit()
    return int(choice.split(" - ")[0])


def find_element(element_id_str):
    try:
        eid = DB.ElementId(int(element_id_str))
    except Exception:
        return None
    el = doc.GetElement(eid)
    return el


def override_color(status):
    from bim.schemas import STATUS_OVERRIDE_COLOR_RGB  # engine repo is on sys.path via plm_config
    rgb = STATUS_OVERRIDE_COLOR_RGB.get(status, (150, 150, 150))
    ogs = DB.OverrideGraphicSettings()
    color = DB.Color(rgb[0], rgb[1], rgb[2])
    ogs.SetProjectionLineColor(color)
    solid_fill = next((p for p in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement)
                        if p.GetFillPattern().IsSolidFill), None)
    if solid_fill:
        ogs.SetSurfaceForegroundPatternColor(color)
        ogs.SetSurfaceForegroundPatternId(solid_fill.Id)
    return ogs


def set_text_param(element, name, value):
    p = element.LookupParameter(name)
    if p is None or value is None:
        return False
    if p.StorageType == DB.StorageType.String:
        p.Set(str(value))
    elif p.StorageType == DB.StorageType.Double:
        try:
            p.Set(float(value))
        except (TypeError, ValueError):
            return False
    return True


def main():
    from bim.exchange import export_results_for_revit  # engine repo on sys.path via plm_config

    project_id = get_project_id()
    conn = plm_config.get_engine_db_connection()
    payload = export_results_for_revit(conn, project_id)
    conn.close()

    results = payload["results"]
    if not results:
        forms.alert("No saved calculations with Revit links found for this project. "
                     "Run calculations in the Streamlit app first, on elements imported "
                     "via the Extract Data button.", exitscript=True)

    written, missing_in_model, missing_params = 0, [], []

    with revit.Transaction("PLM: write calc results + color-code by status"):
        for element_id_str, r in results.items():
            element = find_element(element_id_str)
            if element is None:
                missing_in_model.append(element_id_str)
                continue

            ok = True
            ok &= set_text_param(element, "PLM_Calc_ID", r["calc_id"])
            ok &= set_text_param(element, "PLM_Code_Status", r["status"])
            ok &= set_text_param(element, "PLM_Required_Value", r["required_value"])
            ok &= set_text_param(element, "PLM_Selected_Value", r["selected_value"])
            ok &= set_text_param(element, "PLM_Result_Value", r["result_value"])
            ok &= set_text_param(element, "PLM_Result_Unit", r["result_unit"])
            ok &= set_text_param(element, "PLM_Reference", r["reference"])
            if not ok:
                missing_params.append(element_id_str)

            try:
                view.SetElementOverrides(element.Id, override_color(r["status"]))
            except Exception:
                pass  # some categories/views don't support per-element overrides -- params still get written

            written += 1

    output.print_md("### Run Analysis complete")
    output.print_md("- Elements updated: **{}**".format(written))
    if missing_in_model:
        output.print_md("- **{} element(s) in the engine DB no longer found in this model** "
                         "(deleted/renumbered since last extract): {}".format(
                             len(missing_in_model), ", ".join(missing_in_model[:20])))
    if missing_params:
        output.print_md("- **{} element(s) are missing one or more PLM_* shared parameters** "
                         "-- bind them first, see bim/revit/PLM_shared_parameters.txt: {}".format(
                             len(missing_params), ", ".join(missing_params[:20])))


main()
