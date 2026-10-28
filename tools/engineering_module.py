"""Run a scoped source-bound engineering package locally; never grants code approval."""
import argparse,json
from pathlib import Path
from engineering.service import run_module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();references=(Path(__file__).resolve().parents[1]/'validation').resolve()
    if args.input.resolve()==args.output.resolve() or args.output.resolve().is_relative_to(references):parser.error('Output must not overwrite the input or validation references')
    if args.input.stat().st_size>10000000:parser.error('Input exceeds10MB')
    package=json.loads(args.input.read_text(encoding='utf-8-sig'));report=run_module(package)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(module=report['module'],technical_status=report['technical_status'],review_status=report['review_status'],code_compliance=report['code_compliance_status'])))


if __name__=='__main__':main()
