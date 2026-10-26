"""Public synthetic example; no source workbooks or code table values."""
from workbooks.interactive import build_package,digest


def demo_package():
    cells={}
    for addr,value,formula in [('A10','Flow rate (L/s)',None),('G10',2.,None),('A11','Duration (minutes)',None),('G11',10.,None),
                               ('A13','Required volume (litres)',None),('G13',1200.,'G10*G11*60')]:
        cells[addr]=dict(value=value,formula=formula,error=False,editable_hint=formula is None and isinstance(value,float))
    book=dict(sha256=digest(cells),sheets={'Flow and duration':dict(state='visible',cells=cells)},names={},functions={},macros=False,external_links=0,cached_errors=[])
    return build_package(book,'Examples/Flow and duration demonstration.xlsx',
                         dict(filename='Examples/Flow and duration demonstration.xlsx',primary_bases=['Synthetic example'],
                              all_bases=['Arithmetic identity; not a code sizing method'],reference_evidence=[],warnings=[],review_notes=[]))
