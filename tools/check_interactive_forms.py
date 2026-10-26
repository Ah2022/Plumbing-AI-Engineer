"""Exercise every converted form without any original Excel file dependency."""
from collections import Counter
from pathlib import Path
import json
from workbooks.interactive import LOCAL,decode_package,run_package


def check():
    rows=[];totals=Counter()
    for path in sorted(LOCAL.glob('*.plmcalc')):
        p=decode_package(path.read_bytes());counts=Counter();forms=[]
        for name,form in p['forms'].items():
            values={field['cell']:p['workbook']['sheets'][name]['cells'][field['cell']]['value'] for field in form['inputs']}
            report=run_package(p,name,values)
            status=Counter(r['status'] for r in report['results']);counts.update(status)
            forms.append(dict(worksheet=name,inputs=len(values),outputs=len(report['results']),statuses=dict(status)))
        totals.update(counts);rows.append(dict(title=p['title'],package_sha256=p['package_sha256'],forms=forms,statuses=dict(counts)))
    return dict(method='Every converted form evaluated with supplied sample inputs, using .plmcalc only; no Excel/VBA runtime or engineering certification',
                packages=len(rows),forms=sum(len(r['forms']) for r in rows),totals=dict(totals),calculations=rows)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    report=check();args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='calculations'},indent=2))
