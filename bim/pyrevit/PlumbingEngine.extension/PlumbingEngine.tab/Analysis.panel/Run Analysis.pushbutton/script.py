#! python3
# -*- coding: utf-8 -*-
"""Preview a model-matched engine handoff; dry run rolls back, commit needs an explicit choice."""
import json
from pyrevit import revit, DB, script, forms
import plm_config
from bim.revit_handoff import preflight_handoff, apply_handoff


def main():
    path = forms.pick_file(file_ext='json', title='Select engine Revit handoff JSON')
    if not path:
        return
    with open(path, 'r', encoding='utf-8') as source:
        packet = json.load(source)
    try:
        plan = preflight_handoff(revit.doc, DB, packet)
        output = script.get_output()
        output.print_md('## Revit handoff preflight')
        output.print_md('Elements: {}. Problems: {}.'.format(plan['element_count'], len(plan['errors'])))
        for error in plan['errors']:
            output.print_md('- ' + error)
        if not plan['can_write']:
            forms.alert('Handoff blocked. Resolve identity, source geometry and PLM binding/type issues, then re-extract and recalculate.')
            return
        choice = forms.CommandSwitchWindow.show(['Preview only', 'Dry run (roll back)', 'Commit PLM result fields'], message='Choose handoff action')
        if choice in (None, 'Preview only'):
            return
        commit = choice == 'Commit PLM result fields'
        if commit and not forms.alert('Write the previewed PLM result fields to this model? Geometry and pipe sizes will not be changed. Engineering review status remains explicit.', yes=True, no=True):
            return
        output.print_md(str(apply_handoff(revit.doc, DB, packet, commit=commit)))
    except (ValueError, TypeError, KeyError) as error:
        forms.alert('Handoff was not applied: ' + str(error))


main()
