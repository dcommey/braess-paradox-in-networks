"""Held-out Braessian-regime analysis (braessian-protocol.md): paired latency changes and model comparison."""
import csv
import gzip
import json
from pathlib import Path
import statistics
import sys
import numpy as np
from scipy.stats import t

root, prediction_path = Path(sys.argv[1]), Path(sys.argv[2])
assert (root / 'COMPLETE').exists()
manifest = json.loads((root / 'manifest.json').read_text())
prediction = json.loads(prediction_path.read_text())
runs = manifest['runs']
caps, seeds = sorted({r['cap'] for r in runs}), sorted({r['seed'] for r in runs})
modes = ['staggered', 'synchronized']
assert len(runs) == len(caps) * len(seeds) * len(modes)
spec0 = runs[0]
# Windows and stability-search lengths come from the manifest; defaults reproduce braessian-001.
WINDOWS = [(k, *manifest.get('windows', {}).get(k, d)) for k, d in
           [('before', [10, 20]), ('expanded', [30, 40]), ('step', [50, 60])]]
SEARCH = manifest.get('settle_search', [20, 20])

def settling(windows, start, length):
    """First five-bin stable block within the change interval (block must end by start+length)."""
    for first in range(start, start + length - 4):
        block = windows[first:first + 5]
        values = [w['mean_ms'] for w in block]
        if len(block) < 5 or any(v is None for v in values): continue
        center = statistics.mean(values)
        shares = np.array([np.array(w['routes']) / w['offered'] for w in block])
        if max(abs(v - center) for v in values) <= max(2, .1 * center) and \
                np.max(np.abs(shares - shares.mean(axis=0)).sum(axis=1)) <= .1:
            return first - start
    return None

metrics, schedules, trajectories = [], {}, []
for i, spec in enumerate(runs):
    folder = root / f'run-{i:03d}'
    assert (folder / 'COMPLETE').exists()
    audit = json.loads((folder / 'audit.json').read_text())
    config = json.loads((folder / 'configuration.json').read_text())
    assert all(config[k] == v for k, v in spec.items())
    with gzip.open(folder / 'packets.jsonl.gz', 'rt') as f: rows = [json.loads(line) for line in f]
    origin = rows[0]['origin_ns']
    sent = {r['id']: r for r in rows if r['event'] == 'send'}
    received = {r['id']: r for r in rows if r['event'] == 'receive'}
    data_schedule = [(r['tenant'], r['scheduled_ns'] - origin) for r in sent.values() if r['kind'] == 'data']
    key = spec['seed']
    if key in schedules:
        expected = schedules[key]
        assert len(expected) == len(data_schedule), 'Paired schedule length mismatch'
        assert all(a[0] == b[0] and abs(a[1] - b[1]) <= 1000 for a, b in zip(expected, data_schedule)), 'Paired schedule mismatch'
    else: schedules[key] = data_schedule
    trajectories.append({'spec': spec, 'windows': audit['windows']})
    row = {**{k: spec[k] for k in ['seed', 'cap', 'phasing', 'rate']},
           'total_offered': audit['offered_total'], 'total_completed': audit['completed_total'],
           'queue_dropped': audit['queue_dropped'], 'unaccounted': audit['unaccounted'],
           'throttled_usec': audit['throttled_usec'], 'preference_switches': audit['preference_switches'],
           'activation_settle_s': settling(audit['windows'], spec['activate'], SEARCH[0]),
           'step_settle_s': settling(audit['windows'], spec['step_at'], SEARCH[1])}
    for label, left, right in WINDOWS:
        cohort = [r for r in sent.values() if r['kind'] == 'data' and left <= (r['scheduled_ns'] - origin) / 1e9 < right]
        latency = [(received[r['id']]['received_ns'] - r['sent_ns']) / 1e6 for r in cohort if r['id'] in received]
        row[label + '_mean_ms'] = statistics.mean(latency)
        row[label + '_p95_ms'] = float(np.quantile(latency, .95, method='inverted_cdf'))
        row[label + '_offered'], row[label + '_completed'] = len(cohort), len(latency)
        row[label + '_gateway_share'] = sum(r['route'] == 2 for r in cohort) / len(cohort)
        row[label + '_send_lateness_p95_ms'] = float(np.quantile([(r['sent_ns'] - r['scheduled_ns']) / 1e6 for r in cohort], .95, method='inverted_cdf'))
    metrics.append(row)

def pick(seed, mode, cap): return next(r for r in metrics if r['seed'] == seed and r['phasing'] == mode and r['cap'] == cap)
predicted = {(label, r['cap']): r for label in ['base', 'step'] for r in prediction[label]}
comparisons = []
for mode in modes:
    for cap in caps:
        for window, label in [('expanded', 'base'), ('step', 'step')]:
            pct = [100 * (pick(s, mode, cap)[window + '_mean_ms'] / pick(s, mode, 0)[window + '_mean_ms'] - 1) for s in seeds]
            mean = statistics.mean(pct)
            half = float(t.ppf(.975, len(seeds) - 1) * statistics.stdev(pct) / len(seeds) ** .5) if cap else 0.
            model = predicted[(label, cap)]
            comparisons.append({'phasing': mode, 'cap': cap, 'window': window,
                'mean_latency_ms': statistics.mean(pick(s, mode, cap)[window + '_mean_ms'] for s in seeds),
                'mean_p95_ms': statistics.mean(pick(s, mode, cap)[window + '_p95_ms'] for s in seeds),
                'gateway_share': statistics.mean(pick(s, mode, cap)[window + '_gateway_share'] for s in seeds),
                'paired_change_pct': mean, 'ci_low_pct': mean - half, 'ci_high_pct': mean + half,
                'predicted_cost_ms': model['mean_cost_ms'], 'predicted_change_pct': 100 * model['penalty'],
                'predicted_gateway_share': model['gateway_share']})
for name, rows in [('run_metrics', metrics), ('paired_comparisons', comparisons)]:
    (root / f'{name}.json').write_text(json.dumps(rows, indent=2))
    with (root / f'{name}.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
(root / 'trajectories.json').write_text(json.dumps(trajectories))
validity = {'runs': len(metrics), 'paired_schedules_verified': True,
    'offered_including_probes': sum(r['total_offered'] for r in metrics),
    'completed_including_probes': sum(r['total_completed'] for r in metrics),
    'queue_dropped': sum(r['queue_dropped'] for r in metrics), 'unaccounted': sum(r['unaccounted'] for r in metrics),
    'throttled_runs': sum(r['throttled_usec'] > 0 for r in metrics),
    'max_cohort_send_lateness_p95_ms': max(r[w + '_send_lateness_p95_ms'] for r in metrics for w, _, _ in WINDOWS),
    'before_window_mean_range_ms': [min(r['before_mean_ms'] for r in metrics), max(r['before_mean_ms'] for r in metrics)],
    'activation_settled': sum(r['activation_settle_s'] is not None for r in metrics),
    'step_settled': sum(r['step_settle_s'] is not None for r in metrics)}
(root / 'validity.json').write_text(json.dumps(validity, indent=2))
print(json.dumps(validity, indent=2))
for c in comparisons:
    print(f"{c['phasing']:12s} cap={c['cap']:<4} {c['window']:8s} lat={c['mean_latency_ms']:6.2f} share={c['gateway_share']:.2f} "
          f"change={c['paired_change_pct']:+6.1f}% [{c['ci_low_pct']:+.1f},{c['ci_high_pct']:+.1f}]  model={c['predicted_cost_ms']:.2f}ms {c['predicted_change_pct']:+.1f}% share={c['predicted_gateway_share']:.2f}")
