#! python3
# -*- coding: utf-8 -*-
"""Read-only SI extract with stable identities and explicit classification evidence."""
import datetime
import json
from pyrevit import revit, DB, script, forms
import plm_config
from bim.revit_handoff import model_identity, pipe_facts
from bim.schemas import validate_extract_payload


def element_id(element):
    return str(element.Id.Value if hasattr(element.Id, 'Value') else element.Id.IntegerValue)


def classification(pipe):
    parameter = pipe.get_Parameter(DB.BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM)
    return parameter.AsString() or parameter.AsValueString() if parameter and parameter.HasValue else None


def type_identity(element):
    typed = revit.doc.GetElement(element.GetTypeId())
    return typed.UniqueId if typed else None


def main():
    doc = revit.doc
    scope = forms.CommandSwitchWindow.show(['Entire model', 'Current selection'], message='Choose explicit extract scope')
    if not scope:
        return
    selected = {str(i.Value if hasattr(i,'Value') else i.IntegerValue) for i in revit.uidoc.Selection.GetElementIds()} if scope=='Current selection' else None
    if selected is not None and not selected:
        forms.alert('Select the intended model partition before extracting.'); return
    payload = dict(extractor_version='phase67-1', revit_version=doc.Application.VersionNumber, extract_scope=scope, schema_version='1.0', units='SI', revit_model_name=doc.Title,
        revit_model_id=model_identity(doc), extracted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        pipes=[], fixtures=[], tanks=[], pumps=[], skipped=[])
    for pipe in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_PipeCurves).WhereElementIsNotElementType():
        if selected is not None and element_id(pipe) not in selected:
            continue
        label = classification(pipe)
        system = plm_config.classify_system(label)
        if system is None:
            payload['skipped'].append(dict(element_id=element_id(pipe), reason='Unmapped system classification', source_classification=label))
            continue
        try:
            facts = pipe_facts(pipe, DB)
        except (AttributeError,ValueError,TypeError) as error:
            payload['skipped'].append(dict(element_id=element_id(pipe),reason=str(error))); continue
        facts.update(revit_element_id=element_id(pipe), revit_unique_id=pipe.UniqueId,
                     type_unique_id=type_identity(pipe), system=system)
        payload['pipes'].append(facts)
    for fixture in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_PlumbingFixtures).WhereElementIsNotElementType():
        if selected is not None and element_id(fixture) not in selected:
            continue
        symbol = fixture.Symbol
        payload['fixtures'].append(dict(revit_element_id=element_id(fixture), revit_unique_id=fixture.UniqueId,
            type_unique_id=type_identity(fixture), family=symbol.Family.Name,
            type_name=DB.Element.Name.__get__(symbol)))
    for category in (DB.BuiltInCategory.OST_MechanicalEquipment, DB.BuiltInCategory.OST_GenericModel):
        for element in DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
            if selected is not None and element_id(element) not in selected:
                continue
            marker = element.LookupParameter('PLM_Equipment_Class')
            label = marker.AsString().strip().lower() if marker and marker.HasValue and marker.AsString() else None
            if label not in ('tank', 'pump'):
                continue  # Equipment is opt-in; a family name is not an engineering classification.
            item = dict(revit_element_id=element_id(element), revit_unique_id=element.UniqueId,
                        type_unique_id=type_identity(element))
            if label == 'tank':
                tank_type = element.LookupParameter('PLM_Tank_Type')
                if tank_type is None or not tank_type.HasValue or not tank_type.AsString():
                    payload['skipped'].append(dict(element_id=element_id(element), reason='Tank needs explicit PLM_Tank_Type'))
                    continue
                item['tank_type'] = tank_type.AsString()
            payload[label+'s'].append(item)
    errors = validate_extract_payload(payload)
    if errors:
        forms.alert('Extract rejected: ' + '; '.join(errors)); return
    path = forms.save_file(file_ext='json', default_name=doc.Title+'_plm_extract.json')
    if path:
        with open(path, 'w', encoding='utf-8') as target:
            json.dump(payload, target, indent=2, allow_nan=False)
        script.get_output().print_md('Read-only extract saved. Pipes: {}; fixtures: {}; skipped: {}. Review mapping and completeness before calculation.'.format(len(payload['pipes']),len(payload['fixtures']),len(payload['skipped'])))


main()
