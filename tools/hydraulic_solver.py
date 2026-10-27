"""Local hydraulic boundary: python -m tools.hydraulic_solver model.json --output result.json."""
import argparse
import json
from pathlib import Path
from solvers.service import solve_network,run_scenarios,compare_tree


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--backend',choices=['auto','tree','epanet'],default='auto');p.add_argument('--library',type=Path)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--scenarios',action='store_true');mode.add_argument('--compare-tree',action='store_true')
    args=p.parse_args()
    if args.model.resolve()==args.output.resolve():p.error('Output must not overwrite the input model')
    model=json.loads(args.model.read_text(encoding='utf-8-sig'))
    if args.scenarios:result=run_scenarios(model,library=args.library)
    elif args.compare_tree:result=compare_tree(model,library=args.library)
    else:result=solve_network(model,backend=args.backend,library=args.library)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    completed=result.get('complete',result.get('backend')=='tree')
    if args.scenarios:completed=bool(result['scenarios']) and all(r['result']['complete'] for r in result['scenarios'])
    if args.compare_tree:completed=result['epanet']['complete'] and all(r['comparison_status']=='MATCH_WITH_DOCUMENTED_CONVENTIONS' for r in result['comparison'])
    print(json.dumps(dict(completed=completed,code_compliance='NOT_EVALUATED',output=str(args.output))))
    raise SystemExit(0 if completed else 2)


if __name__=='__main__':main()
