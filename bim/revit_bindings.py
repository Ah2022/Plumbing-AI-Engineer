"""Validate the actual shared definition and instance/category binding before writing."""
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def shared_parameter_guids():
    path = Path(__file__).parent / 'revit' / 'PLM_shared_parameters.txt'
    return {parts[2]: parts[1].lower() for line in path.read_text(encoding='utf-8-sig').splitlines()
            if (parts := line.split('\t'))[0] == 'PARAM'}


def validate_result_binding(doc, DB, element, name, parameter):
    """Fail closed for name collisions, non-shared, wrong GUID, type or category bindings."""
    expected = shared_parameter_guids().get(name)
    try:
        if len(list(element.GetParameters(name))) != 1:
            return 'ambiguous parameter name'
        if not parameter.IsShared or str(parameter.GUID).lower() != expected:
            return 'shared parameter GUID does not match PLM manifest'
        binding = doc.ParameterBindings.get_Item(parameter.Definition)
        if not isinstance(binding, DB.InstanceBinding):
            return 'PLM parameter requires an instance binding'
        if element.Category is None or not binding.Categories.Contains(element.Category):
            return 'PLM instance binding does not include target category'
    except Exception as error:
        return 'shared parameter binding cannot be validated: ' + str(error)
    return None
