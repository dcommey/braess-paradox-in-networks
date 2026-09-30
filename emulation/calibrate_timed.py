"""Timed-service calibration: shared-stage sojourn curve and per-chain fixed costs.

Uses fixed-route traffic only (no adaptation, no probes, no gateway policy), so it
is independent of every policy outcome. Writes calibration.json in the output root.
"""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import statistics
import subprocess

p = argparse.ArgumentParser()
p.add_argument('output')
p.add_argument('--shared-service-ms', type=float, default=2.0)
p.add_argument('--replica-service-ms', type=float, default=0.2)
p.add_argument('--replica-delay-ms', type=float, default=5)
p.add_argument('--seed', type=int, default=8001)
p.add_argument('--rates', type=int, nargs='*', default=[50, 100, 200, 300, 350, 400, 425, 450, 475])
p.add_argument('--no-routes', action='store_true', help='curve points only')
args = p.parse_args()
root = Path(args.output)
root.mkdir(parents=True, exist_ok=False)
WARMUP = 5
plan = [('curve', 0, r, 20) for r in args.rates] + ([] if args.no_routes else [('route', route, 20, 15) for route in (0, 1, 2)])

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

results = []
for i, (kind, route, rate, seconds) in enumerate(plan):
    out = root / f'cal-{i:02d}'
    command = ['python3', '/experiment/run_policy.py', '--output', str(out), '--rate', str(rate),
               '--seed', str(args.seed + i), '--cap', '0', '--seconds', str(seconds),
               '--activate', str(seconds + 1), '--fixed-route', str(route),
               '--shared-service-ms', str(args.shared_service_ms),
               '--replica-service-ms', str(args.replica_service_ms),
               '--replica-delay-ms', str(args.replica_delay_ms)]
    with (root / f'cal-{i:02d}.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 60)
    packets = read(out / 'packets.jsonl')
    origin = packets[0]['origin_ns']
    sent = {r['id']: r for r in packets if r['event'] == 'send'}
    received = {r['id']: r for r in packets if r['event'] == 'receive'}
    keep = {i for i, r in sent.items() if (r['scheduled_ns'] - origin) / 1e9 >= WARMUP}
    row = {'kind': kind, 'route': route, 'rate': rate, 'seconds': seconds,
           'offered': len(keep), 'completed': len(keep & set(received))}
    row['end_to_end_ms'] = statistics.mean((received[i]['received_ns'] - sent[i]['sent_ns']) / 1e6 for i in keep & set(received))
    stage_sojourn = {}
    for name in 'ABCD':
        rows = [r for r in read(out / f'stage-{name}.jsonl') if r['event'] == 'service' and r['id'] in keep]
        if rows:
            stage_sojourn[name] = statistics.mean((r['end_ns'] - r['arrived_ns']) / 1e6 for r in rows)
            row[f'{name}_service_ms'] = statistics.mean((r['end_ns'] - r['start_ns']) / 1e6 for r in rows)
            row[f'{name}_served_per_s'] = len(rows) / (seconds - WARMUP)
    row['stage_sojourn_ms'] = stage_sojourn
    row['overhead_ms'] = row['end_to_end_ms'] - sum(stage_sojourn.values())
    cpu = json.loads((out / 'cpu.json').read_text())
    parse = lambda s: dict((k, int(v)) for k, v in (line.split() for line in s.splitlines()))
    row['throttled_usec'] = parse(cpu['after'])['throttled_usec'] - parse(cpu['before'])['throttled_usec']
    row['drops'] = sum('"drop"' in line for name in 'ABCD' for line in (out / f'stage-{name}.jsonl').read_text().splitlines())
    results.append(row)
    for path in out.glob('*.jsonl'):
        with path.open('rb') as source, gzip.open(str(path) + '.gz', 'wb') as target:
            shutil.copyfileobj(source, target)
        path.unlink()
    print(json.dumps(row), flush=True)
(root / 'calibration.json').write_text(json.dumps({'config': vars(args), 'warmup_s': WARMUP, 'runs': results}, indent=2))
(root / 'COMPLETE').write_text('Calibration complete.\n')
