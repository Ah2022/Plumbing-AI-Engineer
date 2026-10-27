"""python -m tools.engineering_validation --output outputs/validation.json

Optional --epanet-library PATH reruns the pinned external 2.2 solver.
No command updates golden references or grants engineering acceptance.
"""
import argparse
import json
from pathlib import Path
from validation.suite import run_validation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--epanet-library',type=Path)
    args=parser.parse_args()
    root=(Path(__file__).resolve().parents[1]/'validation/phase1a').resolve()
    if args.output.resolve().is_relative_to(root):parser.error('Result exports cannot overwrite reference evidence')
    result=run_validation(epanet_library=args.epanet_library)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(software_status=result['software_status'],release_label=result['engineering_gate']['release_label'],
                         methods=len(result['methods']),projects=len(result['projects']))))
    raise SystemExit(0 if result['software_status']=='PASS' else 1)


if __name__=='__main__':main()
