"""Audit receiver accounting and summarize exploratory kernel calibration."""
import json
from pathlib import Path
import re
import statistics

root = Path(__file__).parent / 'results/calibration-001'
files = sorted(root.glob('run-*.json'))
assert len(files) == 18 and (root / 'COMPLETE').exists()
rows = []
for path in files:
    d = json.loads(path.read_text())
    receiver = d['server']['end']['sum_received']
    sender = d['client']['end']['sum_sent']
    assert d['returncodes'] == [0, 0, 0] and not any(d['stderr'])
    assert receiver['bytes'] > 0 and receiver['seconds'] > 0
    assert abs(receiver['bytes'] * 8 / receiver['seconds'] - receiver['bits_per_second']) < 1
    assert d['client']['end']['sum_received']['bytes'] == receiver['bytes']
    rtt = [float(x) for x in re.findall(r'time=([\d.]+) ms', d['ping'])]
    cpu = lambda s: dict((k, int(v)) for k, v in (l.split() for l in s.splitlines()))
    a, b = cpu(d['cpu_before']), cpu(d['cpu_after'])
    rows.append({'file': path.name, 'rate': d['offered_mbps'],
                 'sent_mbps': sender['bits_per_second'] / 1e6,
                 'received_mbps': receiver['bits_per_second'] / 1e6,
                 'loss_pct': receiver['lost_percent'], 'rtt_ms': statistics.mean(rtt),
                 'samples': len(rtt), 'throttled_usec': b['throttled_usec'] - a['throttled_usec']})
(root / 'audit.json').write_text(json.dumps(rows, indent=2))
summary = []
for rate in sorted({r['rate'] for r in rows}):
    runs = [r for r in rows if r['rate'] == rate]
    summary.append({key: statistics.mean(r[key] for r in runs)
                    for key in ['rate', 'sent_mbps', 'received_mbps', 'loss_pct', 'rtt_ms', 'throttled_usec']})
(root / 'summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
