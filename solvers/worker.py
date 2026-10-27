"""Isolated native-library process; invoked by solvers.service only."""
import json
import sys
from solvers.graph import normalize_graph
from solvers.epanet_native import simulate


def main():
    source,target,library=sys.argv[1:4]
    try:
        with open(source,encoding='utf-8') as stream:model=json.load(stream)
        normalized,_=normalize_graph(model);result=simulate(normalized,library)
    except Exception as error:
        result=dict(solver_status='NOT_CONVERGED',complete=False,snapshots=[],diagnostics=[dict(code='BACKEND_ERROR',severity='ERROR',
            message=str(error),action='Check the model, supported toolkit version and EPANET report; correct invalid definitions before rerunning.')])
    with open(target,'w',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)


if __name__=='__main__':main()
