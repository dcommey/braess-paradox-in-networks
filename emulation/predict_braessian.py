"""Calibrated equilibrium prediction, screened cap and held-out manifest (see braessian-protocol.md)."""
import json
import math
from pathlib import Path
import random
import sys
import numpy as np
from scipy.optimize import least_squares, minimize

GRID = [1, .75, .5, .35, .25, .15, .10, 0]
TAU, PROBES, STEP = .02, 20., 1.15
CHAINS = [['A', 'D'], ['C', 'B'], ['A', 'B']]

# usage: predict_braessian.py OUTPUT_DIR CALIBRATION_JSON [CALIBRATION_JSON ...]
out = Path(sys.argv[1])
cal = {'runs': [r for f in sys.argv[2:] for r in json.loads(Path(f).read_text())['runs']]}
# Stationary points only: saturated runs have no steady-state sojourn time.
curve = [r for r in cal['runs'] if r['kind'] == 'curve' and r['drops'] == 0 and r['completed'] == r['offered']]
lam = np.array([r['A_served_per_s'] for r in curve])
soj = np.array([r['stage_sojourn_ms']['A'] for r in curve])

def w_model(p, x):
    s, k, mu = p
    rho = x / mu
    return s + k * rho / (1 - rho)
fit = least_squares(lambda p: w_model(p, lam) - soj, x0=[2., 1., 520.],
                    bounds=([0, 0, lam.max() * 1.001], [20, 50, 5000]))
s, k, mu = fit.x
W = lambda x: w_model(fit.x, x)
Wint = lambda x: s * x + k * (-x - mu * math.log(1 - x / mu))  # integral of W from 0 to x

low = min(curve, key=lambda r: r['rate'])
mu_hat = 1000 / low['A_service_ms']
rate = math.floor(.9 * mu_hat)
route = {r['route']: r for r in cal['runs'] if r['kind'] == 'route'}
# Fixed per-chain overhead: low-load end-to-end cost minus the measured shared-stage sojourns in the same run
# (replica service, link propagation and forwarding remain in the overhead).
overhead = [route[j]['end_to_end_ms'] - sum(route[j]['stage_sojourn_ms'][x] for x in chain if x in 'AB')
            for j, chain in enumerate(CHAINS)]

def solve(total, cap):
    eligible = 3 if cap > 0 else 2
    probe = PROBES / eligible
    def loads(x):
        a = x[0] + x[2] + probe * (1 + (eligible == 3))
        b = x[1] + x[2] + probe * (1 + (eligible == 3))
        return a, b
    def potential(x):
        a, b = loads(x)
        if a >= mu or b >= mu: return 1e12
        return sum(h * v for h, v in zip(overhead, x)) + Wint(a) + Wint(b)
    upper = cap * total
    best = None
    for start in ([total / 2, total / 2, 0], [total * .45, total * .45, upper * .9], [(total - upper) / 2, (total - upper) / 2, upper]):
        r = minimize(potential, start, method='SLSQP', bounds=[(0, total)] * 2 + [(0, upper)],
                     constraints=[{'type': 'eq', 'fun': lambda x: x.sum() - total}],
                     options={'ftol': 1e-12, 'maxiter': 500})
        if r.success and (best is None or r.fun < best.fun): best = r
    x = np.clip(best.x, 0, None)
    a, b = loads(x)
    cost = [overhead[0] + W(a), overhead[1] + W(b), overhead[2] + W(a) + W(b)]
    mean = float(sum(c * v for c, v in zip(cost, x)) / total)
    return {'cap': cap, 'flows': x.tolist(), 'gateway_share': float(x[2] / total),
            'shared_loads': [a, b], 'chain_costs_ms': cost, 'mean_cost_ms': mean}

prediction = {'fit': {'s_ms': s, 'k_ms': k, 'mu_per_s': mu, 'rmse_ms': float(np.sqrt(np.mean(fit.fun ** 2)))},
              'mu_hat_per_s': mu_hat, 'rate': rate, 'overhead_ms': overhead, 'tau': TAU}
for label, total in [('base', rate), ('step', rate * STEP)]:
    rows = [solve(total, cap) for cap in GRID]
    base = next(r for r in rows if r['cap'] == 0)['mean_cost_ms']
    for r in rows: r['penalty'] = r['mean_cost_ms'] / base - 1
    prediction[label] = rows
screened = next(r['cap'] for r in prediction['base'] if r['penalty'] <= TAU)
prediction['screened_cap'] = screened
caps = sorted({0, .25, screened, 1})
runs = [{'rate': rate, 'seed': seed, 'cap': cap, 'seconds': 60, 'activate': 20, 'step_at': 40,
         'step_factor': STEP, 'phasing': mode, 'shared_service_ms': 2.0, 'replica_service_ms': 0.2,
         'replica_delay_ms': 5}
        for seed in range(7101, 7106) for mode in ['staggered', 'synchronized'] for cap in caps]
random.Random(7099).shuffle(runs)
manifest = {'purpose': 'Braessian-regime held-out experiment; protocol in braessian-protocol.md',
            'order_seed': 7099, 'rate_rule': 'floor(0.9 * 1000 / shared service ms at 50 requests/s)',
            'screened_cap_model': screened, 'caps': caps, 'runs': runs}
out.mkdir(parents=True, exist_ok=True)
(out / 'prediction.json').write_text(json.dumps(prediction, indent=2))
(Path(__file__).resolve().parent / 'braessian-manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({k: v for k, v in prediction.items() if k not in ('base', 'step')}, indent=2))
for label in ['base', 'step']:
    for r in prediction[label]:
        print(label, r['cap'], round(r['gateway_share'], 3), round(r['mean_cost_ms'], 3), f"{100 * r['penalty']:.1f}%")
print('screened cap', screened, 'held-out caps', caps, 'runs', len(runs))
