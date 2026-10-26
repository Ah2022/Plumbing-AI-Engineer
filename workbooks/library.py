"""Register reference calculations separately from adopted/verified code tables."""
from pathlib import Path
from zipfile import ZipFile
from collections import Counter
import hashlib
import json
import re
import math

from workbooks.reader import read_workbook,MAX_FILE
from workbooks.formulas import Evaluator,FormulaError,UnsupportedFormula,SUPPORTED

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'database'/'workbook_catalog.json'
LOCAL=ROOT/'local_sources'/'calculation_sheets'
FAMILIES={
 'IPC':r'\bIPC\b|Int(?:ern|en)ational Plumbing Code',
 'UPC':r'\bUPC\b|Uniform Plumbing Code',
 'NSPC':r'\bNSPC\b|National Standard Plumbing Code',
 'ASHRAE':r'ASHRAE', 'ASPE':r'\bASPE\b|American Society Of Plumbing Engineers',
 'EGYPT_301':r'Egyptian|EGY\.CODE',
 'QATAR_KAHRAMAA':r'Kahramaa', 'QATAR_ASHGHAL':r'Ashghal',
 'NFPA_54':r'NFPA\s*[-–]?\s*54\b','NFPA_58':r'NFPA\s*[-–]?\s*58\b',
 'NFPA_101':r'NFPA\s*[-–]?\s*101\b',
 'HTM_02':r'HTM\s*[-–]?\s*02', 'HTM_22_LEGACY':r'HTM\s*22',
 'BRITISH_GUIDANCE':r'British Standard|Insti[tu]+te Of Plumbing|BS\s*1387',
 'STEEL_TEXTBOOK':r'Engineered Plumbing|Dr[. ]+Steel|Dr[. ]+Alf|Alfared Steel',
 'MANUFACTURER':r'Manufacturer|Catalogue|Wessel|Watts',
}


def bases(text):return [key for key,pattern in FAMILIES.items() if re.search(pattern,text,re.I)]


def describe(book,filename,archive=''):
    evidence=[];sheets=[]
    for name,sheet in book['sheets'].items():
        auxiliary=name.lower().startswith(('data','reference','000','instruction'))
        texts=[]
        for addr,c in sheet['cells'].items():
            value=c['value']
            if isinstance(value,str) and bases(value):
                texts.append(value)
                # Reference claims only: avoid copying numeric tables or full prose.
                if len(value)<240:evidence.append(dict(sheet=name,cell=addr,text=value,kind='cached_reference_label' if c['formula'] else 'reference_label'))
            if c['formula']:
                texts.extend(re.findall(r'"((?:[^"]|"")*)"',c['formula']))
        formula_count=sum(c['formula'] is not None for c in sheet['cells'].values())
        sheets.append(dict(name=name,state=sheet['state'],auxiliary=auxiliary,cells=len(sheet['cells']),
                           formulas=formula_count,declared_bases=sorted(set(b for t in texts for b in bases(t)))))
    primary=sorted(set(b for s in sheets if not s['auxiliary'] for b in s['declared_bases']))
    all_bases=sorted(set(b for s in sheets for b in s['declared_bases']))
    warnings=[]
    if book['cached_errors']:warnings.append(f"{len(book['cached_errors'])} saved formula errors; cached values are not fresh results")
    if book['external_links']:warnings.append('External workbook link present; linked data is unavailable to recalculation')
    unsupported=sorted(set(book['functions'])-SUPPORTED)
    if unsupported:warnings.append('Unsupported functions: '+', '.join(unsupported))
    if not primary:warnings.append('No primary code/standard identified in cell text; inspect source references before use')
    if book['macros']:warnings.append('VBA is present and is never executed by this engine')
    # A code number/table citation alone does not identify its edition.
    return dict(workbook_id=book['sha256'][:16],filename=filename,archive=archive,
                sha256=book['sha256'],primary_bases=primary,all_bases=all_bases,
                verification_status='UNVERIFIED_REFERENCE',edition_status='PER_REFERENCE_ONLY',
                sheets=sheets,reference_evidence=evidence,warnings=warnings,
                cached_errors=book['cached_errors'],functions=book['functions'],
                macros=book['macros'],external_links=book['external_links'])


def catalog(path=None):
    p=Path(path) if path else CATALOG
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else dict(schema_version='1.0',workbooks=[])


def source_path(entry,directory=None):
    root=Path(directory) if directory else LOCAL
    if not re.fullmatch('[0-9a-f]{64}',entry['sha256']):raise ValueError('Invalid workbook identity')
    return root/(entry['sha256'][:12]+'-'+Path(entry['filename']).name)


def load_source(entry,directory=None):
    p=source_path(entry,directory)
    if not p.is_file():raise FileNotFoundError('Original workbook is not installed locally. Import its supplied ZIP first.')
    data=p.read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Source workbook fingerprint changed; reimport it as a new revision')
    return read_workbook(data)


def install_archives(paths,*,directory=None,catalog_path=None):
    """Only original workbook packages are copied, using hash-based names. No VBA runs."""
    dest=Path(directory) if directory else LOCAL;dest.mkdir(parents=True,exist_ok=True)
    entries={};skipped=[]
    for path in paths:
        path=Path(path)
        with ZipFile(path) as outer:
            for info in outer.infolist():
                name=Path(info.filename.replace('\\','/')).name
                if info.is_dir() or name.startswith('~$') or not name.lower().endswith(('.xlsm','.xlsx')):
                    skipped.append(info.filename);continue
                if info.file_size>MAX_FILE:raise ValueError('Workbook exceeds intake limit: '+name)
                data=outer.read(info);book=read_workbook(data)
                entry=describe(book,info.filename,path.name)
                p=source_path(entry,dest)
                if not p.exists():p.write_bytes(data)
                elif hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Existing local source has changed')
                entries[entry['workbook_id']]=entry
                if len(entries)>100:raise ValueError('Import at most 100 workbooks per operation')
    current=catalog(catalog_path);merged={e['workbook_id']:e for e in current['workbooks']}
    for wid,e in entries.items():
        if wid in merged and 'review_notes' in merged[wid]:e['review_notes']=merged[wid]['review_notes']
    merged.update(entries)
    output=dict(schema_version='1.0',workbooks=sorted(merged.values(),key=lambda e:e['filename']))
    target=Path(catalog_path) if catalog_path else CATALOG
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dict(imported=len(entries),skipped=skipped,catalog=str(target))


def run_scenario(book,outputs,overrides=None):
    if not isinstance(outputs,list) or not outputs or len(outputs)>100 or any(not isinstance(x,str) for x in outputs):
        raise ValueError('Select 1–100 output cell addresses')
    if not isinstance(overrides or {},dict):raise ValueError('Input overrides must be a JSON object')
    evaluator=Evaluator(book,overrides);results=[]
    for key in dict.fromkeys(outputs):
        try:
            sh,addr=evaluator.address(key)
            if addr not in book['sheets'][sh]['cells']:raise FormulaError('Output cell is empty or unavailable')
            value=evaluator.cell(sh,addr)
            saved=book['sheets'][sh]['cells'][addr]['value']
            same=(math.isclose(value,saved,rel_tol=1e-8,abs_tol=1e-8) if isinstance(value,(int,float)) and isinstance(saved,(int,float)) else value==saved)
            results.append(dict(cell=key,value=value,status='CALCULATED_NOT_APPROVED',
                                source_saved_value=saved,matches_saved_value=same,
                                formula=book['sheets'][sh]['cells'][addr]['formula']))
        except UnsupportedFormula as e:results.append(dict(cell=key,value=None,status='NOT_EVALUATED',reason=str(e)))
        except (FormulaError,RecursionError) as e:results.append(dict(cell=key,value=None,status='MISSING_DATA',reason=str(e)))
    request=dict(source_sha256=book['sha256'],outputs=outputs,overrides=overrides or {})
    return dict(source_sha256=book['sha256'],input_sha256=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest(),
                technical_status='CALCULATED_NOT_APPROVED' if all(x['status']=='CALCULATED_NOT_APPROVED' for x in results) else 'WARNING',
                review_status='REVIEW_REQUIRED',results=results,overrides=overrides or {},trace=evaluator.trace,
                limitations=['Reference-sheet formula reproduction only; source equations, catalogue data and code applicability are unverified.',
                             'Source units and rounding are retained. No implicit SI conversion, VBA, external-link fetch or cached-result fallback.',
                             'Embedded images, drawings, controls and macro-driven input changes are not evaluated.'])


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Import calculation workbooks locally; never execute macros or merge their tables into code profiles.')
    parser.add_argument('archives',nargs='+',type=Path)
    args=parser.parse_args();print(json.dumps(install_archives(args.archives),indent=2))


if __name__=='__main__':main()
