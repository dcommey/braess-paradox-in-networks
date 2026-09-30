"""Reconcile every offered packet and stage event before summarizing latency."""
import json
import math
from pathlib import Path
import statistics
import sys

root = Path(sys.argv[1])
assert (root / 'COMPLETE').exists(), 'Incomplete experiment'
protocol = json.loads((root / 'protocol.json').read_text())
read = lambda p: [json.loads(line) for line in p.read_text().splitlines()]
quantile = lambda values, q: sorted(values)[max(0, math.ceil(len(values) * q) - 1)]
summary = []
for i, (rep, rate) in enumerate(protocol['schedule']):
    probes = read(root / f'probe-{i:02d}.jsonl')
    stage = read(root / f'stage-{i:02d}.jsonl')
    meta = json.loads((root / f'meta-{i:02d}.json').read_text())
    assert not (root / f'stderr-{i:02d}.txt').read_text()
    sent = {r['id']: r for r in probes if r['event'] == 'send'}
    received = {r['id']: r for r in probes if r['event'] == 'receive'}
    served = {r['id']: r for r in stage if r['event'] == 'service'}
    dropped = {r['id'] for r in stage if r['event'] == 'drop'}
    assert len(sent) == sum(r['event'] == 'send' for r in probes)
    assert len(received) == sum(r['event'] == 'receive' for r in probes)
    assert set(received) <= set(served) <= set(sent)
    assert not set(served) & dropped
    assert not dropped - set(sent)
    for ident, row in received.items():
        assert len(row['trace']) == 1
        name, arrived, start, end = row['trace'][0]
        assert sent[ident]['sent_ns'] <= arrived <= start <= end <= row['received_ns']
        assert [arrived, start, end] == [served[ident][k] for k in ['arrived_ns', 'start_ns', 'end_ns']]
    ordered = sorted(served.values(), key=lambda r: r['start_ns'])
    assert all(a['end_ns'] <= b['start_ns'] for a, b in zip(ordered, ordered[1:])), 'Service overlap'
    service = [(r['end_ns'] - r['start_ns']) / 1e6 for r in served.values()]
    queue = [(r['start_ns'] - r['arrived_ns']) / 1e6 for r in served.values()]
    latency = [(r['received_ns'] - sent[ident]['sent_ns']) / 1e6 for ident, r in received.items()]
    lateness = [(r['sent_ns'] - r['scheduled_ns']) / 1e6 for r in sent.values()]
    cpu = lambda s: dict((k, int(v)) for k, v in (l.split() for l in s.splitlines()))
    a, b = cpu(meta['cpu_before']), cpu(meta['cpu_after'])
    summary.append({'index': i, 'repeat': rep, 'offered_rate_pps': rate,
        'offered': len(sent), 'received': len(received), 'queue_dropped': len(dropped),
        'unaccounted': len(set(sent) - set(received) - dropped),
        'service_mean_ms': statistics.mean(service), 'service_p95_ms': quantile(service, .95),
        'queue_mean_ms': statistics.mean(queue), 'latency_mean_ms': statistics.mean(latency),
        'latency_p95_ms': quantile(latency, .95), 'send_lateness_p95_ms': quantile(lateness, .95),
        'throttled_usec': b['throttled_usec'] - a['throttled_usec']})
    if all('compute_cpu_ns' in r for r in served.values()):
        summary[-1].update({
            'compute_cpu_mean_ms': statistics.mean(r['compute_cpu_ns'] / 1e6 for r in served.values()),
            'compute_wall_mean_ms': statistics.mean(r['compute_wall_ns'] / 1e6 for r in served.values())})
(root / 'audit.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
