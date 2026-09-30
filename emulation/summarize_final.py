"""Held-out emulation analysis with run-level pairing and validity checks."""
import csv
import gzip
import json
from pathlib import Path
import statistics
import sys
import numpy as np
from scipy.stats import t

root=Path(sys.argv[1])
assert (root/'COMPLETE').exists()
manifest=json.loads((root/'manifest.json').read_text())
assert len(manifest['runs']) in (72,24)
rates=sorted({r['rate'] for r in manifest['runs']})
seeds=sorted({r['seed'] for r in manifest['runs']})
assert len(seeds)==4
assert len(manifest['runs'])==len(rates)*len(seeds)*2*3
metrics=[]
schedules={}
trajectories=[]
def load_packets(folder):
    with gzip.open(folder/'packets.jsonl.gz','rt') as f:return [json.loads(line) for line in f]
def settling(windows,start):
    for first in range(start,start+6):
        block=windows[first:first+5]
        values=[w['mean_ms'] for w in block]
        if any(v is None for v in values):continue
        center=statistics.mean(values)
        shares=np.array([np.array(w['routes'])/w['offered'] for w in block])
        if max(abs(v-center) for v in values)<=max(2,.1*center) and np.max(np.abs(shares-shares.mean(axis=0)).sum(axis=1))<=.1:
            return first-start
    return None
for i, spec in enumerate(manifest['runs']):
    folder=root/f'run-{i:03d}'
    assert (folder/'COMPLETE').exists()
    audit=json.loads((folder/'audit.json').read_text())
    config=json.loads((folder/'configuration.json').read_text())
    assert all(config[k]==v for k,v in spec.items())
    rows=load_packets(folder)
    origin=rows[0]['origin_ns']
    sent={r['id']:r for r in rows if r['event']=='send'}
    received={r['id']:r for r in rows if r['event']=='receive'}
    schedule=[(r['tenant'],r['kind'],r['scheduled_ns']-origin) for r in sent.values()]
    key=(spec['rate'],spec['seed'])
    if key in schedules:
        expected=schedules[key]
        assert len(expected)==len(schedule)
        assert all(a[:2]==b[:2] and abs(a[2]-b[2])<=1000 for a,b in zip(expected,schedule)), 'Paired schedule mismatch'
    else:schedules[key]=schedule
    assert audit['probe_offered']==600
    trajectories.append({'spec':spec,'windows':audit['windows']})
    row={**spec,'total_offered':audit['offered_total'],'total_completed':audit['completed_total'],
         'queue_dropped':audit['queue_dropped'],'unaccounted':audit['unaccounted'],
         'throttled_usec':audit['throttled_usec'],
         'activation_settle_s':settling(audit['windows'],10),
         'step_settle_s':settling(audit['windows'],20),
         'activation_peak_1s_mean_ms':max(w['mean_ms'] for w in audit['windows'][10:20] if w['mean_ms'] is not None),
         'step_peak_1s_mean_ms':max(w['mean_ms'] for w in audit['windows'][20:30] if w['mean_ms'] is not None)}
    for label,left,right in [('before',5,10),('expanded',15,20),('step',25,30)]:
        cohort=[r for r in sent.values() if r['kind']=='data' and left <= (r['scheduled_ns']-origin)/1e9 < right]
        latency=[(received[r['id']]['received_ns']-r['sent_ns'])/1e6 for r in cohort if r['id'] in received]
        row[label+'_mean_ms']=statistics.mean(latency)
        row[label+'_p95_ms']=float(np.quantile(latency,.95,method='inverted_cdf'))
        row[label+'_offered']=len(cohort)
        row[label+'_completed']=len(latency)
        row[label+'_gateway_share']=sum(r['route']==2 for r in cohort)/len(cohort)
        row[label+'_send_lateness_p95_ms']=float(np.quantile([(r['sent_ns']-r['scheduled_ns'])/1e6 for r in cohort],.95,method='inverted_cdf'))
    metrics.append(row)
comparisons=[]
for rate in rates:
 for mode in ['staggered','synchronized']:
  for cap in [.25,1]:
   for window in ['expanded','step']:
    differences=[];ratio=[]
    for seed in seeds:
        select=lambda c:next(r for r in metrics if r['rate']==rate and r['phasing']==mode and r['cap']==c and r['seed']==seed)
        control,candidate=select(0),select(cap)
        differences.append(candidate[window+'_mean_ms']-control[window+'_mean_ms'])
        ratio.append(100*(candidate[window+'_mean_ms']/control[window+'_mean_ms']-1))
    mean=statistics.mean(ratio);half=float(t.ppf(.975,3)*statistics.stdev(ratio)/2)
    comparisons.append({'rate':rate,'phasing':mode,'cap':cap,'window':window,
        'mean_paired_penalty_pct':mean,'ci_low_pct':mean-half,'ci_high_pct':mean+half,
        'mean_paired_difference_ms':statistics.mean(differences)})
for name,rows in [('run_metrics',metrics),('paired_comparisons',comparisons)]:
    (root/f'{name}.json').write_text(json.dumps(rows,indent=2))
    with (root/f'{name}.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(root/'trajectories.json').write_text(json.dumps(trajectories,indent=2))
validity={'runs':len(metrics),'paired_schedules_verified':True,
          'offered_including_probes':sum(r['total_offered'] for r in metrics),
          'completed_including_probes':sum(r['total_completed'] for r in metrics),
          'queue_dropped':sum(r['queue_dropped'] for r in metrics),
          'unaccounted':sum(r['unaccounted'] for r in metrics),
          'throttled_runs':sum(r['throttled_usec']>0 for r in metrics),
          'max_cohort_send_lateness_p95_ms':max(r[w+'_send_lateness_p95_ms'] for r in metrics for w in ['before','expanded','step'])}
(root/'validity.json').write_text(json.dumps(validity,indent=2))
print(json.dumps(validity,indent=2))
print(json.dumps([r for r in comparisons if r['cap']==1],indent=2))
