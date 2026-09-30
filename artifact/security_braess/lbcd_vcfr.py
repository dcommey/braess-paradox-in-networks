"""Finite-column VCFR optimizer and LBCD community allocation.

Each column specifies an entire feasible replica placement/routing decision.
The optimizer retains binary replica assignment, per-function shared storage,
compute/link capacities and the utilization/OPEX objective. Exactness applies
to the supplied feasible column set. See revision/literature/comparator-mapping.md.
"""
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix, vstack, csr_matrix

@dataclass(frozen=True)
class Column:
    name: str
    request: str
    compute: dict
    bandwidth: dict
    storage: frozenset
    delay: float = 0.0

def solve_vcfr(columns, requests, compute_capacity, bandwidth_capacity,
               storage_sizes=None, storage_capacity=None, compute_price=None,
               storage_price=None, alpha=1.0, opex_scale=1.0, delay_limits=None, priorities=None):
    """One column per replica, no admission rejection, shared deployment binaries."""
    storage_sizes = storage_sizes or {}
    storage_capacity = storage_capacity or {}
    compute_price, storage_price = compute_price or {}, storage_price or {}
    delay_limits = delay_limits or {}
    if not 0 <= alpha <= 1 or opex_scale <= 0: raise ValueError('Invalid objective weights')
    columns = [c for c in columns if c.delay <= delay_limits.get(c.request, np.inf)]
    if any(set(c.compute)-set(compute_capacity) or set(c.bandwidth)-set(bandwidth_capacity) for c in columns):
        raise ValueError('A column uses a resource without a capacity')
    if any(not any(c.request == r for c in columns) for r in requests):
        raise ValueError('No feasible column for at least one replica')
    pairs = sorted(set().union(*(c.storage for c in columns)))
    storage_index = {key:len(columns)+i for i,key in enumerate(pairs)}
    eta = len(columns)+len(pairs)
    n = eta+1
    objective = np.zeros(n)
    for i,c in enumerate(columns):
        objective[i] = (1-alpha)*sum(compute_price.get(r,0)*v for r,v in c.compute.items())/opex_scale
    for key,i in storage_index.items():
        objective[i] = (1-alpha)*storage_sizes.get(key,1)*storage_price.get(key[0],0)/opex_scale
    objective[eta] = alpha
    rows, lows, highs = [], [], []
    def add(row, low=-np.inf, high=np.inf):
        rows.append(row); lows.append(low); highs.append(high)
    for request in requests:
        add({i:1 for i,c in enumerate(columns) if c.request==request},1,1)
    for resource,cap in compute_capacity.items():
        if cap <= 0: raise ValueError('Capacity must be positive')
        row={i:c.compute.get(resource,0)/cap for i,c in enumerate(columns)}
        row[eta]=-1
        add(row,high=0)
    for resource,cap in bandwidth_capacity.items():
        add({i:c.bandwidth.get(resource,0) for i,c in enumerate(columns)},high=cap)
    for i,c in enumerate(columns):
        for key in c.storage: add({i:1,storage_index[key]:-1},high=0)
    for key,j in storage_index.items():
        row={i:-1 for i,c in enumerate(columns) if key in c.storage}
        row[j]=1
        add(row,high=0)
    for node,cap in storage_capacity.items():
        add({j:storage_sizes.get(key,1) for key,j in storage_index.items() if key[0]==node},high=cap)
    matrix=lil_matrix((len(rows),n))
    for r, values in enumerate(rows):
        for i,v in values.items(): matrix[r,i]=v
    result=milp(objective, integrality=np.array([1]*eta+[0]), bounds=Bounds(np.zeros(n),np.ones(n)),
                constraints=LinearConstraint(matrix.tocsr(),lows,highs),
                options={'time_limit':60,'mip_rel_gap':1e-9})
    if not result.success: raise RuntimeError(f'VCFR failed: {result.message}')
    feasible_point=np.array([round(x) for x in result.x[:eta]]+[0.0])
    feasible_point[eta]=max((sum(c.compute.get(r,0)*feasible_point[i] for i,c in enumerate(columns))/cap
                            for r,cap in compute_capacity.items()),default=0)
    primary_value=float(objective @ feasible_point)
    max_gap=float(result.mip_gap)
    # Preserve a deterministic allocation among primary optima. This prevents
    # added unused columns from changing decisions solely through solver order.
    constrained=vstack([matrix.tocsr(),csr_matrix(objective.reshape(1,-1))]).tocsr()
    lower=np.zeros(n); upper=np.ones(n)
    for request in sorted(requests):
        previous_solution=result.x.copy()
        indices=[i for i,c in enumerate(columns) if c.request==request]
        indices.sort(key=lambda i: ((priorities or {}).get(columns[i].name,0),columns[i].name))
        secondary=np.zeros(n)
        for rank,i in enumerate(indices):secondary[i]=rank
        result=milp(secondary,integrality=np.array([1]*eta+[0]),bounds=Bounds(lower,upper),
            constraints=LinearConstraint(constrained,list(lows)+[-np.inf],list(highs)+[primary_value+1e-7]),
            options={'time_limit':60,'mip_rel_gap':1e-9,'presolve':False})
        if not result.success:
            raise RuntimeError(f'Tie resolution failed at {request}, primary={primary_value}, '
                f'previous={previous_solution.tolist()}, fixed_lower={lower.tolist()}, '
                f'fixed_upper={upper.tolist()}: '+result.message)
        max_gap=max(max_gap,float(result.mip_gap))
        for i in indices:lower[i]=upper[i]=round(result.x[i])
    selected=[c for i,c in enumerate(columns) if result.x[i]>.5]
    if len(selected)!=len(requests): raise AssertionError('Incomplete assignment')
    # Verify capacities independently from the solver's internal residuals.
    for r,cap in compute_capacity.items():
        assert sum(c.compute.get(r,0) for c in selected) <= cap+1e-7
    for r,cap in bandwidth_capacity.items():
        assert sum(c.bandwidth.get(r,0) for c in selected) <= cap+1e-7
    active=set().union(*(c.storage for c in selected))
    for node,cap in storage_capacity.items():
        assert sum(storage_sizes.get(key,1) for key in active if key[0]==node)<=cap+1e-7
    actual_eta=max((sum(c.compute.get(r,0) for c in selected)/cap for r,cap in compute_capacity.items()),default=0)
    actual_opex=sum(sum(compute_price.get(r,0)*v for r,v in c.compute.items()) for c in selected)
    actual_opex+=sum(storage_sizes.get(key,1)*storage_price.get(key[0],0) for key in active)
    actual_objective=alpha*actual_eta+(1-alpha)*actual_opex/opex_scale
    assert actual_objective <= primary_value+2e-7
    return {'selected':selected,'objective':actual_objective,'maximum_utilization':actual_eta,
            'active_storage':active,'mip_gap':max_gap}

def solve_partitioned(columns, requests, groups, compute_capacity, bandwidth_capacity,
                      storage_sizes=None, storage_capacity=None, compute_price=None,
                      storage_price=None, alpha=1.0, opex_scale=1.0, priorities=None):
    """Allocate resources shared across groups in proportion to their demand.

    Group-local resources retain their capacity. Shared resources use overall
    community demand fractions, preserving the sum of all resource budgets.
    """
    total=sum(requests.values())
    groups=[set(g) for g in groups if g]
    if set().union(*groups)!=set(requests) or sum(map(len,groups))!=len(requests):
        raise ValueError('Request groups must be a partition')
    def budgets(capacities, attribute):
        users={r:{i for i,g in enumerate(groups) if any(c.request in g and r in getattr(c,attribute) for c in columns)} for r in capacities}
        return [{r:cap*(sum(requests[q] for q in g)/total if len(users[r])>1 else 1)
                 for r,cap in capacities.items() if i in users[r]} for i,g in enumerate(groups)]
    cc,bc=budgets(compute_capacity,'compute'),budgets(bandwidth_capacity,'bandwidth')
    results=[]
    for i,g in enumerate(groups):
        local=[c for c in columns if c.request in g]
        # Storage on a shared node follows the same upper-tier resource partition.
        sc={}
        for node,cap in (storage_capacity or {}).items():
            users={j for j,h in enumerate(groups) if any(c.request in h and any(k[0]==node for k in c.storage) for c in columns)}
            if i in users: sc[node]=cap*(sum(requests[q] for q in g)/total if len(users)>1 else 1)
        results.append(solve_vcfr(local,sorted(g),cc[i],bc[i],storage_sizes,sc,compute_price,storage_price,alpha,opex_scale,priorities=priorities))
    selected=[c for r in results for c in r['selected']]
    active=set().union(*(c.storage for c in selected))
    # Set union implements storage deduplication across virtual upper-tier copies.
    utilization=max((sum(c.compute.get(r,0) for c in selected)/cap for r,cap in compute_capacity.items()),default=0)
    return {'selected':selected,'active_storage':active,'maximum_utilization':utilization,
            'local_objectives':[r['objective'] for r in results], 'mip_gap':max(r['mip_gap'] for r in results),
            'community_count':len(groups)}
