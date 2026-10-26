"""Convert installed originals into portable .plmcalc forms and a ZIP library."""
from pathlib import Path
import json
from workbooks.library import catalog,load_source
from workbooks.interactive import LOCAL,build_package,decode_package,encode_package,bundle


def convert(output):
    LOCAL.mkdir(parents=True,exist_ok=True);packages=[];summary=[]
    for entry in catalog()['workbooks']:
        book=load_source(entry)
        p=build_package(book,entry['filename'],entry)
        data=encode_package(p);decode_package(data)
        (LOCAL/(p['package_sha256']+'.plmcalc')).write_bytes(data)
        packages.append(p)
        summary.append(dict(filename=entry['filename'],forms=len(p['forms']),inputs=sum(len(f['inputs']) for f in p['forms'].values()),
                            outputs=sum(len(f['outputs']) for f in p['forms'].values()),bytes=len(data)))
    Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_bytes(bundle(packages))
    return summary


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    summary=convert(args.output)
    print(json.dumps(dict(packages=len(summary),forms=sum(s['forms'] for s in summary),inputs=sum(s['inputs'] for s in summary),
                          outputs=sum(s['outputs'] for s in summary),details=summary),indent=2))
