"""Compare fresh formula reproduction with saved caches; caches are not engineering truth."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from workbooks.library import catalog,load_source
from workbooks.formulas import Evaluator,FormulaError,UnsupportedFormula


def check():
    reports=[]
    for entry in catalog()['workbooks']:
        book=load_source(entry);ev=Evaluator(book);counts=Counter();issues=[]
        for sh,sheet in book['sheets'].items():
            for addr,c in sheet['cells'].items():
                if c['formula'] is None:continue
                try:
                    actual=ev.cell(sh,addr);expected=c['value']
                    if c['error']:kind='source_cached_error'
                    elif isinstance(expected,(int,float)) and not isinstance(expected,bool) and isinstance(actual,(int,float)):
                        kind='matched_cache' if math.isclose(expected,actual,rel_tol=1e-8,abs_tol=1e-8) else 'cache_difference'
                    else:kind='matched_cache' if actual==expected or actual is None and expected=='' else 'cache_difference'
                except UnsupportedFormula as e:actual=None;kind='unsupported';reason=str(e)
                except (FormulaError,RecursionError,ValueError) as e:actual=None;kind='unavailable';reason=str(e)
                counts[kind]+=1
                if kind!='matched_cache':issues.append(dict(cell=sh+'!'+addr,kind=kind,reason=reason if kind in ('unsupported','unavailable') else 'Fresh value differs from saved cache'))
        reports.append(dict(workbook_id=entry['workbook_id'],filename=entry['filename'],sha256=entry['sha256'],counts=dict(counts),issues=issues))
    totals=Counter()
    for r in reports:totals.update(r['counts'])
    return dict(method='Fresh formula evaluation versus supplied saved caches; reproduction evidence, not engineering/code verification',totals=dict(totals),workbooks=reports)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=check();args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['totals'],indent=2))
