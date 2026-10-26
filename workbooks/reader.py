"""Read XLSX/XLSM facts without opening Excel, executing VBA or following links."""
from collections import Counter
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import hashlib
import math
import posixpath
import re
import xml.etree.ElementTree as ET

from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles.numbers import BUILTIN_FORMATS
from openpyxl.utils.cell import range_boundaries,coordinate_to_tuple

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
MAX_FILE=30_000_000
MAX_XML=80_000_000


def read_workbook(source):
    data=source if isinstance(source,bytes) else Path(source).read_bytes()
    if len(data)>MAX_FILE: raise ValueError('Workbook exceeds 30 MB intake limit')
    result=dict(sha256=hashlib.sha256(data).hexdigest(),sheets={},names={},macros=False,
                external_links=0,cached_errors=[],functions={})
    with ZipFile(BytesIO(data)) as z:
        parts=z.namelist()
        if len(parts)!=len(set(parts)): raise ValueError('Duplicate workbook package members')
        xml_parts=[i for i in z.infolist() if i.filename.endswith(('.xml','.rels'))]
        if sum(i.file_size for i in xml_parts)>MAX_XML: raise ValueError('Workbook XML exceeds intake limit')
        def xml(name): return ET.fromstring(z.read(name))
        styles=[]
        if 'xl/styles.xml' in parts:
            style_xml=xml('xl/styles.xml')
            formats=dict(BUILTIN_FORMATS)
            formats.update({int(n.attrib['numFmtId']):n.attrib['formatCode'] for n in style_xml.findall('s:numFmts/s:numFmt',NS)})
            for xf in style_xml.findall('s:cellXfs/s:xf',NS):
                protection=xf.find('s:protection',NS)
                styles.append(dict(editable_hint=int(xf.attrib.get('fillId','0'))>1 or protection is not None and protection.attrib.get('locked')=='0',
                                   number_format=formats.get(int(xf.attrib.get('numFmtId','0')),'General')))
        strings=[]
        if 'xl/sharedStrings.xml' in parts:
            strings=[''.join(x.itertext()) for x in xml('xl/sharedStrings.xml')]
        rels={x.attrib['Id']:x.attrib['Target'] for x in xml('xl/_rels/workbook.xml.rels')
              if x.attrib.get('TargetMode')!='External'}
        wb=xml('xl/workbook.xml');functions=Counter()
        result['macros']='xl/vbaProject.bin' in parts
        result['external_links']=len([p for p in parts if re.fullmatch(r'xl/externalLinks/externalLink\d+\.xml',p)])
        sheets=wb.findall('s:sheets/s:sheet',NS)
        for i,sh in enumerate(sheets):
            target=rels.get(sh.attrib[RID],'')
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if not target.startswith('xl/worksheets/'): raise ValueError('Unsupported worksheet target')
            sheet=dict(state=sh.attrib.get('state','visible'),cells={})
            tree=xml(target);shared={}
            sheet['merges']=[m.attrib['ref'] for m in tree.findall('s:mergeCells/s:mergeCell',NS)]
            for cell in tree.findall('.//s:sheetData/s:row/s:c',NS):
                addr=cell.attrib['r'];typ=cell.attrib.get('t');v=cell.find('s:v',NS)
                value=v.text if v is not None else None
                if typ=='s': value=strings[int(value)] if value is not None else None
                elif typ=='inlineStr': value=''.join(cell.find('s:is',NS).itertext())
                elif typ=='b': value=value=='1'
                elif typ=='str' and value is None:value=''
                elif typ not in ('str','e') and value is not None:
                    value=float(value)
                    if not math.isfinite(value):raise ValueError('Non-finite workbook number at '+addr)
                f=cell.find('s:f',NS);formula=None
                if f is not None:
                    formula=f.text
                    if f.attrib.get('t')=='shared':
                        sid=f.attrib['si']
                        if formula:shared[sid]=(addr,formula)
                        elif sid in shared:
                            origin,base=shared[sid];formula=Translator('='+base,origin=origin).translate_formula(addr)[1:]
                        else:raise ValueError('Shared formula has no preceding definition')
                    if f.attrib.get('t') not in (None,'normal','shared'): formula='UNSUPPORTED_ARRAY_OR_TABLE()'
                    if formula is None: formula='UNSUPPORTED_EMPTY_FORMULA()'
                    try:
                        functions.update(t.value[:-1].upper() for t in Tokenizer('='+formula).items if t.type=='FUNC' and t.subtype=='OPEN')
                    except Exception: functions['UNPARSEABLE']+=1
                if value is not None or formula is not None:
                    sheet['cells'][addr]=dict(value=value,formula=formula,error=typ=='e')
                    si=int(cell.attrib.get('s','0'))
                    if si<len(styles):sheet['cells'][addr].update(styles[si])
                if typ=='e':result['cached_errors'].append(dict(sheet=sh.attrib['name'],cell=addr,error=value))
            for dv in tree.findall('s:dataValidations/s:dataValidation',NS):
                if dv.attrib.get('type')!='list':continue
                bounds=[]
                for area in dv.attrib.get('sqref','').split():
                    try:bounds.append(range_boundaries(area))
                    except ValueError:continue
                for addr,c in sheet['cells'].items():
                    if c['formula'] is not None:continue
                    row,col=coordinate_to_tuple(addr)
                    if any(c1<=col<=c2 and r1<=row<=r2 for c1,r1,c2,r2 in bounds):
                        c['validation']=dict(type='list',formula1=dv.findtext('s:formula1',default='',namespaces=NS))
            result['sheets'][sh.attrib['name']]=sheet
        for n in wb.findall('s:definedNames/s:definedName',NS):
            scope=sheets[int(n.attrib['localSheetId'])].attrib['name'] if 'localSheetId' in n.attrib else ''
            result['names'][scope+'!'+n.attrib['name'].upper()]=n.text
        result['functions']=dict(functions)
    return result
