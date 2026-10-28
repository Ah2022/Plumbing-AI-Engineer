#! python3
# -*- coding: utf-8 -*-
"""Read-only SI object/connector extraction; no family-name classification guesses."""
import json
from pyrevit import revit, DB, script, forms
import plm_config
from bim.revit_extract import extract_document


def main():
    scope=forms.CommandSwitchWindow.show(['Entire model','Current selection'],message='Choose explicit extract scope')
    if not scope:return
    selected={str(i.Value if hasattr(i,'Value') else i.IntegerValue) for i in revit.uidoc.Selection.GetElementIds()} if scope=='Current selection' else None
    if selected is not None and not selected:
        forms.alert('Select the intended model partition before extracting.');return
    try:
        payload=extract_document(revit.doc,DB,plm_config.classify_system,selected)
        path=forms.save_file(file_ext='json',default_name=revit.doc.Title+'_plm_extract.json')
        if path:
            with open(path,'w',encoding='utf-8') as target:json.dump(payload,target,indent=2,allow_nan=False)
            script.get_output().print_md('Read-only extraction: {} source objects, {} physical links, {} skipped. Review mappings, partition completeness and equipment classifications in Revit Exchange.'.format(
                len(payload['inventory']['objects']),len(payload['inventory']['connections']),len(payload['skipped'])))
    except (ValueError,TypeError,OverflowError) as error:forms.alert('Extraction stopped: '+str(error))


main()
