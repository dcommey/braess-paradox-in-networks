"""Evaluate explicitly restricted LBCD-Heu and global VCFR allocations directly."""
import csv
import json
from collections import Counter
from pathlib import Path
import random
import time
from security_braess.lbcd import detect_communities
from security_braess.lbcd_vcfr import Column, solve_vcfr, solve_partitioned
from security_braess.topology import all_topologies
from security_braess.topology_sfc import build_topology_sfc_model, expected_attack_loss, worst_ddos_loss
from security_braess.multicommodity import solve_multicommodity_equilibrium, _make_result

def evaluate(topology, model, method):
    demand={r.name:r.demand for r in model.requests}
    compute={k:r.capacity for k,r in model.resources.items() if r.kind!='link'}
    bandwidth={k:r.capacity for k,r in model.resources.items() if r.kind=='link'}
    columns=[]
    for path in model.paths:
        counts=Counter(path.resources)
        columns.append(Column(path.name,path.request,
            {k:count*demand[path.request] for k,count in counts.items() if k in compute},
            {k:count*demand[path.request] for k,count in counts.items() if k in bandwidth},frozenset()))
    start=time.perf_counter()
    priorities={c.name: (2 if c.name.endswith('central_gateway') else 1 if c.name.endswith('distributed_right') else 0) for c in columns}
    if method=='global_vcfr_fixed_placement':
        answer=solve_vcfr(columns,list(demand),compute,bandwidth,priorities=priorities)
        communities=1
    else:
        loads={v:0 for v in topology.nodes}
        for request in model.requests: loads[request.source]+=request.demand
        groups,_=detect_communities([(e.u,e.v) for e in topology.edges],loads,beta=.6)
        request_groups=[{r.name for r in model.requests if r.source in g} for g in groups]
        request_groups=[g for g in request_groups if g]
        answer=solve_partitioned(columns,demand,request_groups,compute,bandwidth,priorities=priorities)
        communities=len(request_groups)
    elapsed=time.perf_counter()-start
    flows={p.name:0 for p in model.paths}
    for col in answer['selected']: flows[col.name]=demand[col.request]
    result=_make_result(model,flows,iterations=0,converged=True,gap=0)
    return result,{'runtime_s':elapsed,'communities':communities,'mip_gap':answer['mip_gap'],
        'max_compute_util':max(result.loads[r]/compute[r] for r in compute),
        'max_link_util':max(result.loads[r]/bandwidth[r] for r in bandwidth)}

def main():
    rows=[]
    out=Path(__file__).parent/'revision_results/published_comparison'
    out.mkdir(exist_ok=True)
    for topo in all_topologies():
        n=len(build_topology_sfc_model(topo,include_gateway=False).requests)
        for seed in range(21):
            rng=random.Random(6200+seed)
            demands=None if seed==0 else tuple(rng.uniform(.6,1.4) for _ in range(n))
            models=[build_topology_sfc_model(topo,include_gateway=g,demands=demands) for g in [False,True]]
            wardrop=[solve_multicommodity_equilibrium(m) for m in models]
            assert all(r.converged and r.gap/max(1,r.total_cost)<=1e-5 for r in wardrop)
            for method in ['global_vcfr_fixed_placement','lbcd_fixed_placement']:
                decisions=[evaluate(topo,m,method) for m in models]
                for expanded,(model,(result,extra)) in enumerate(zip(models,decisions)):
                    baseline=decisions[0][0].average_cost
                    gateway=sum(result.flows[p.name] for p in model.paths if p.tag=='defensive_expansion')/model.total_demand
                    row={'topology':topo.name,'seed':seed,'method':method,'expanded':expanded,
                         'average_cost':result.average_cost,'own_penalty':result.average_cost/baseline-1,
                         'relative_to_wardrop_baseline':result.average_cost/wardrop[0].average_cost-1,
                         'wardrop_cost':wardrop[expanded].average_cost,'gateway_share':gateway,
                         'admitted_demand':model.total_demand,'offered_demand':model.total_demand,
                         'attack_loss':expected_attack_loss(model,result),
                         'ddos_surface':worst_ddos_loss(model,result)[2],**extra}
                    rows.append(row)
                    (out/f'{topo.name}-{seed}-{method}-{expanded}.json').write_text(json.dumps({'metrics':row,'flows':result.flows,'loads':result.loads},indent=2))
            print(topo.name,seed,flush=True)
    with (out/'summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'summary.json').write_text(json.dumps(rows,indent=2))
    (out/'COMPLETE').write_text('84 paired instances; 336 controlled allocations.\n')

if __name__=='__main__':main()
