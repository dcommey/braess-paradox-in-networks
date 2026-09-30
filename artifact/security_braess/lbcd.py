"""Community-detection component of Tian et al., DOI 10.1109/TNSM.2023.3332509.

Implements the score in equations (12),(15) and multilevel local moves.
This module alone is not LBCD-Heu: resource partitioning and VCFR MILPs are
separate required stages of the published procedure.
"""
from math import fsum

def partition_score(edges, loads, communities, beta=0.5, gamma=1.0):
    """Undirected unweighted edge graph; loads retain original vertex identity."""
    vertices = set(loads)
    communities = [set(c) for c in communities]
    flattened = [v for c in communities for v in c]
    if set(flattened) != vertices or len(flattened) != len(vertices):
        raise ValueError('Communities must partition every vertex exactly once')
    if not 0 <= beta <= 1 or gamma <= 0 or any(v < 0 for v in loads.values()):
        raise ValueError('Invalid score parameters or load')
    links = {frozenset((u, v)) for u, v in edges}
    if any(len(e) != 2 or not e <= vertices for e in links):
        raise ValueError('Expected loop-free edges on known vertices')
    if not links: raise ValueError('Modularity requires at least one edge')
    degree = {v: sum(v in e for e in links) for v in vertices}
    m = len(links)
    q = fsum(sum(e <= c for e in links) / m - gamma * (sum(degree[v] for v in c) / (2*m))**2 for c in communities)
    mean = fsum(loads.values()) / len(vertices)
    total = fsum((x-mean)**2 for x in loads.values())
    within = fsum(fsum((loads[v]-fsum(loads[w] for w in c)/len(c))**2 for v in c) for c in communities)
    # The source ratio is undefined for uniform loads. H=0 makes the term
    # partition-independent, preserving modularity optimization in that case.
    h = within / total if total else 0.0
    return beta*q + (1-beta)*h, q, h

def detect_communities(edges, loads, beta=0.5, gamma=1.0):
    """Deterministic multilevel greedy moves; strictly positive gains only.

    Original vertices and loads are retained when groups are compressed, so
    the score evaluates the exact original graph at every level.
    """
    edges = list(edges)
    order = sorted(loads)
    atoms = [set([v]) for v in order]
    partition_score(edges, loads, atoms, beta, gamma)
    history = []
    while True:
        communities = [set(a) for a in atoms]
        score = partition_score(edges, loads, communities, beta, gamma)[0]
        moved = True
        while moved:
            moved = False
            for atom in atoms:
                source = next(i for i,c in enumerate(communities) if atom <= c)
                neighbours = {v if u in atom else u for u,v in edges if (u in atom) != (v in atom)}
                candidates = [i for i,c in enumerate(communities) if i != source and c & neighbours]
                best_score, best_partition = score, None
                for target in candidates:
                    trial = [set(c) for c in communities]
                    trial[source] -= atom
                    trial[target] |= atom
                    trial = [c for c in trial if c]
                    value = partition_score(edges, loads, trial, beta, gamma)[0]
                    if value > best_score + 1e-12:
                        best_score, best_partition = value, trial
                if best_partition is not None:
                    communities, score = best_partition, best_score
                    history.append(score)
                    moved = True
        if len(communities) == len(atoms):
            return communities, history
        atoms = communities
