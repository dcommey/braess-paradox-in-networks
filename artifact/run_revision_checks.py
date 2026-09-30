"""Reproduce analytical screening, sensitivity, and Monte Carlo audit results.

Run from any directory: python3 artifact/run_revision_checks.py
Only the Python standard library and the adjacent security_braess copy are used.
"""
from pathlib import Path
from collections import Counter
import csv
import json
from time import perf_counter

from security_braess.topology import all_topologies
from security_braess.topology_sfc import (
    build_topology_sfc_model, _gateway_caps, gateway_share,
    evaluate_topology_suite, summarize_evaluations,
)
from security_braess.multicommodity import solve_multicommodity_equilibrium
from scripts.run_experiments import _write_policy_table, _write_attack_table

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'revision_results'
TABLES = ROOT.parent / 'generated' / 'tables'
TABLES.mkdir(parents=True, exist_ok=True)
COARSE = (0, .1, .15, .25, .35, .5, .75, 1)
THRESHOLDS = (0, .005, .01, .02, .05, .1)


def csv_write(name, rows):
    with (OUT / name).open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def table(name, caption, label, header, rows, columns):
    body = '\n'.join(' & '.join(row) + r' \\' for row in rows)
    text = (r'\begin{table}[!ht]' + '\n' + r'\centering\color{blue}\scriptsize' + '\n'
            + r'\caption{' + caption + '}\n' + r'\label{' + label + '}\n'
            + r'\begin{tabular}{' + columns + '}\n' + r'\toprule' + '\n'
            + ' & '.join(header) + r' \\\midrule' + '\n' + body + '\n'
            + r'\bottomrule\end{tabular}' + '\n' + r'\end{table}' + '\n')
    (TABLES / name).write_text(text)


def penalty_text(value):
    if value == 0:
        return '0.0000'
    if abs(value) < .0001:
        return f'{value:.1e}'
    return f'{value:.4f}'


def main():
    OUT.mkdir(exist_ok=True)
    rows = summarize_evaluations(evaluate_topology_suite())
    csv_write('policy_comparison.csv', rows)
    _write_policy_table(TABLES / 'policy_comparison.tex', rows)
    _write_attack_table(TABLES / 'attack_stress_summary.tex', rows)
    p = TABLES / 'policy_comparison.tex'
    p.write_text(p.read_text().replace(r'\begin{table*}[t]', r'\begin{table*}[!t]').replace('-0.000', r'\textcolor{blue}{0.000}'))

    gains = []
    for topology in all_topologies():
        group = {r['policy']: r for r in rows if r['topology'] == topology.name}
        j0 = group['baseline']['average_cost']
        jn = group['naive_expansion']['average_cost']
        ja = group['paradox_aware']['average_cost']
        gains.append(dict(topology=topology.name, baseline_cost=j0, naive_cost=jn,
                          aware_cost=ja, relative_cost_reduction=(jn-ja)/jn,
                          induced_penalty_removed=(jn-ja)/(jn-j0)))
    csv_write('penalty_removal.csv', gains)
    names = dict(zip([t.name for t in all_topologies()], ['Fat-tree','NSFNET','GEANT','Edge/fog']))
    table('penalty_removal.tex', 'Relative cost reduction and fraction of induced penalty removed; computed from unrounded costs.',
          'tab:penalty-removal', ['Topology', '$100G_A$', '$100R_{\\Pi}$'],
          [[names[r['topology']], f"{100*r['relative_cost_reduction']:.2f}", f"{100*r['induced_penalty_removed']:.2f}"] for r in gains], 'lrr')

    curve, selections = [], []
    for topology in all_topologies():
        baseline_model = build_topology_sfc_model(topology, include_gateway=False)
        model = build_topology_sfc_model(topology, include_gateway=True)
        baseline = solve_multicommodity_equilibrium(baseline_model, tolerance=1e-5, max_iter=20000)
        assert baseline.gap / max(1., baseline.total_cost) <= 1.01e-5
        available = []
        for n in range(101):
            kappa = n / 100
            start = perf_counter()
            result = solve_multicommodity_equilibrium(model, _gateway_caps(model, kappa), tolerance=1e-5, max_iter=20000)
            elapsed = perf_counter()-start
            relative_gap = result.gap / max(1., result.total_cost)
            assert relative_gap <= 1.01e-5, (topology.name, kappa, relative_gap)
            # Treat only sub-numerical differences as zero; preserve all raw costs.
            penalty = (result.average_cost-baseline.average_cost)/baseline.average_cost
            row = dict(topology=topology.name, kappa=kappa, baseline_cost=baseline.average_cost,
                       cost=result.average_cost, penalty=penalty, gateway_share=gateway_share(model,result),
                       relative_gap=relative_gap, iterations=result.iterations, seconds=elapsed)
            curve.append(row)
            available.append(row)
        for grid_name, grid in [('original',COARSE), ('fine_0.01',tuple(n/100 for n in range(101)))]:
            grid_rows = [r for r in available if r['kappa'] in grid]
            for tau in THRESHOLDS:
                feasible = [r for r in grid_rows if r['penalty'] <= tau + 1e-9]
                assert feasible
                selected = max(feasible, key=lambda r:r['kappa'])
                larger = [r for r in grid_rows if r['kappa'] > selected['kappa']]
                next_row = min(larger, key=lambda r:r['kappa']) if larger else None
                selections.append(dict(topology=topology.name, grid=grid_name, tau=tau,
                    selected_cap=selected['kappa'], gateway_share=selected['gateway_share'],
                    cost=selected['cost'], penalty=selected['penalty'], slack=tau-selected['penalty'],
                    next_cap=next_row['kappa'] if next_row else '',
                    next_penalty=next_row['penalty'] if next_row else ''))
        print(f"Verified 101 cap equilibria: {topology.name}",flush=True)
    csv_write('cap_curves.csv',curve)
    csv_write('threshold_grid_sensitivity.csv',selections)
    selected = [r for r in selections if r['topology']=='nsfnet']
    table('threshold_grid_sensitivity.tex', 'NSFNET threshold and cap-grid sensitivity. Share denotes the realized gateway traffic fraction; next penalty corresponds to the next larger tested cap. Costs use normalized delay units.',
          'tab:threshold-grid', ['$\\tau$', 'Grid', '$\\kappa$', 'Share', 'Cost', '$\\Pi$', 'Next $\\Pi$'],
          [[f"{r['tau']:.3f}", 'coarse' if r['grid']=='original' else '.01', f"{r['selected_cap']:.2f}",
            f"{r['gateway_share']:.3f}", f"{r['cost']:.3f}", penalty_text(r['penalty']),
            penalty_text(r['next_penalty']) if r['next_penalty']!='' else '--'] for r in selected], 'rlrrrrr')

    with (ROOT/'original_results/monte_carlo_instances.csv').open() as f:
        mc = list(csv.DictReader(f))
    converged = [r for r in mc if all(r[k]=='True' for k in ('baseline_converged','naive_converged','aware_converged'))]
    paradox = [r for r in converged if r['paradox']=='True']
    nonparadox = [r for r in converged if r['paradox']=='False']
    audit = dict(attempted=len(mc), converged=len(converged), braessian=len(paradox), non_braessian=len(nonparadox),
                 excluded_ids=[int(r['instance']) for r in mc if r not in converged],
                 braessian_caps=dict(Counter(f"{float(r['cap_fraction']):.2f}" for r in paradox)),
                 non_braessian_caps=dict(Counter(f"{float(r['cap_fraction']):.2f}" for r in nonparadox)),
                 all_converged_caps=dict(Counter(f"{float(r['cap_fraction']):.2f}" for r in converged)),
                 positive_but_below_threshold=sum(0<float(r['naive_penalty'])<=.02 for r in paradox),
                 cap_solves=len(curve), maximum_relative_gap=max(r['relative_gap'] for r in curve),
                 normalization='DDoS scalar eta_D=1 in artifact copy; original expected attack loss unchanged')
    assert len(converged)==998 and len(paradox)==715 and len(nonparadox)==283
    assert all(float(r['cap_fraction'])==1 for r in nonparadox)
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':
    main()
