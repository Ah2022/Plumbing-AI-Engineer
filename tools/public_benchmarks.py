"""Pinned public software candidates: list, import, fetch explicitly, run or export."""
import argparse,json
from pathlib import Path
from validation.public_benchmarks import catalogue,case,fetch_case,import_bytes,run_case,save_result,DATA,LOCAL


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--list',action='store_true');p.add_argument('--case')
    p.add_argument('--fetch',action='store_true');p.add_argument('--import-file',type=Path);p.add_argument('--role',default='model')
    p.add_argument('--run',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--epanet-library',type=Path)
    args=p.parse_args()
    if args.list:print(json.dumps(catalogue(),indent=2));return
    if not args.case:p.error('--case is required unless --list is selected')
    case(args.case)
    if args.import_file:print(json.dumps(import_bytes(args.case,args.role,args.import_file.read_bytes())))
    if args.fetch:print(json.dumps(fetch_case(args.case)))
    if args.run:
        report=run_case(args.case,library=args.epanet_library)
        if args.output:
            target=args.output.resolve()
            if target.is_relative_to(DATA.resolve()) or target.is_relative_to(LOCAL.resolve()):p.error('Run output must not overwrite benchmark inputs/catalogue')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        else:save_result(report)
        print(json.dumps(dict(case=args.case,software_status=report['software_status'],engineering_status=report['engineering_status'])))
        raise SystemExit(0 if report['software_status']=='PASS' else 1)


if __name__=='__main__':main()
