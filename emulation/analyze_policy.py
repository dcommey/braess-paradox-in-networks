"""Audit SFC ordering, serial service, per-tenant caps and packet accounting."""
import json
import math
from pathlib import Path
import statistics
import sys
import gzip

CHAINS = [['A', 'D'], ['C', 'B'], ['A', 'B']]
root = Path(sys.argv[1])
assert (root / 'COMPLETE').exists()
def read(p):
    if p.exists(): return [json.loads(s) for s in p.read_text().splitlines()]
    with gzip.open(str(p)+'.gz','rt') as f: return [json.loads(s) for s in f]
records = read(root / 'packets.jsonl')
config = records[0]
sent = {r['id']: r for r in records if r['event'] == 'send'}
received = {r['id']: r for r in records if r['event'] == 'receive'}
assert len(sent) == sum(r['event'] == 'send' for r in records)
assert len(received) == sum(r['event'] == 'receive' for r in records)
assert set(received) <= set(sent)
served, dropped = {}, set()
for name in ['A', 'B', 'C', 'D']:
    assert not (root / f'stderr-{name}.txt').read_text()
    rows = read(root / f'stage-{name}.jsonl')
    service = [r for r in rows if r['event'] == 'service']
    assert len(service) == len({r['id'] for r in service})
    served[name] = {r['id']: r for r in service}
    for row in rows:
        assert row['id'] in sent
        assert name in CHAINS[sent[row['id']]['route']]
        if row['event'] == 'drop': dropped.add(row['id'])
    assert all(a['end_ns'] <= b['start_ns'] for a, b in zip(service, service[1:]))
counts = [[0, 0] for _ in range(20)]
for row in sent.values():
    when = (row['scheduled_ns'] - config['origin_ns']) / 1e9
    if row['kind'] == 'data':
        t = row['tenant']
        if when >= config['activate']:
            counts[t][0] += 1
            counts[t][1] += row['route'] == 2
        else: assert row['route'] != 2
        assert counts[t] == [row['eligible_count'], row['gateway_count']]
        assert counts[t][1] <= math.floor(config['cap'] * counts[t][0] + 1e-9)
    if config['cap'] == 0: assert row['route'] != 2
for ident, row in received.items():
    assert [r[0] for r in row['trace']] == CHAINS[row['route']]
    assert row['route'] == sent[ident]['route'] and row['kind'] == sent[ident]['kind']
    previous = sent[ident]['sent_ns']
    for name, arrived, start, end in row['trace']:
        assert previous <= arrived <= start <= end <= row['received_ns']
        assert [arrived, start, end] == [served[name][ident][k] for k in ['arrived_ns','start_ns','end_ns']]
        previous = end
assert not set(received) & dropped
unaccounted = set(sent) - set(received) - dropped
quantile = lambda vals, q: sorted(vals)[max(0, math.ceil(len(vals)*q)-1)] if vals else None
windows = []
for second in range(math.ceil(config['seconds'])):
    cohort = [r for r in sent.values() if r['kind'] == 'data' and second <= (r['scheduled_ns']-config['origin_ns'])/1e9 < second+1]
    latency = [(received[r['id']]['received_ns']-r['sent_ns'])/1e6 for r in cohort if r['id'] in received]
    windows.append({'second': second, 'offered': len(cohort), 'completed': len(latency),
        'gateway': sum(r['route']==2 for r in cohort),
        'routes': [sum(r['route']==j for r in cohort) for j in range(3)],
        'mean_ms': statistics.mean(latency) if latency else None,
        'p95_ms': quantile(latency,.95), 'p99_ms': quantile(latency,.99),
        'send_lateness_p95_ms': quantile([(r['sent_ns']-r['scheduled_ns'])/1e6 for r in cohort],.95)})
cpu = json.loads((root/'cpu.json').read_text())
parse = lambda s:dict((k,int(v)) for k,v in (line.split() for line in s.splitlines()))
a,b = parse(cpu['before']),parse(cpu['after'])
summary = {'offered_total':len(sent), 'completed_total':len(received), 'queue_dropped':len(dropped),
    'unaccounted':len(unaccounted), 'unaccounted_ids':sorted(unaccounted),
    'tenant_counters':counts, 'stage_counts':{name:len(rows) for name,rows in served.items()},
    'preference_switches':sum(r['event']=='update' and r['preferred']!=r['previous'] for r in records),
    'throttled_usec':b['throttled_usec']-a['throttled_usec'],
    'probe_offered':sum(r['kind']=='probe' for r in sent.values()), 'windows':windows}
(root/'audit.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='windows'},indent=2))
