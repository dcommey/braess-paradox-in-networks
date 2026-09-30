import json
from pathlib import Path
import statistics
from scipy.stats import t

root=Path(__file__).resolve().parents[1]
folder=root/'artifact/revision_results/published_comparison'
assert (folder/'COMPLETE').exists()
rows=json.loads((folder/'summary.json').read_text())
assert len(rows)==336 and all(r['offered_demand']==r['admitted_demand'] for r in rows)
assert all(r['max_compute_util']<=1+1e-7 and r['max_link_util']<=1+1e-7 for r in rows)
names={'fat_tree_k4':'Fat-tree','nsfnet':'NSFNET','geant':'GEANT','edge_fog':'Edge/fog'}
lines=[r'\begin{table}[t]',r'\centering\color{blue}',
 r'\caption{Controlled allocations with fixed placements. $J_1$ and $U_{\max}$ are nominal expanded cost and compute utilization. The last column gives the mean own-baseline penalty and 95\% interval across 20 demand realizations, in percentage points. Nominal gateway shares and own-baseline penalties are zero.}',
 r'\label{tab:published-comparison}',r'\scriptsize',r'\begin{tabular}{llrrr}',r'\toprule',
 r'Substrate & Method & $J_1$ & $U_{\max}$ & Random $\Pi$ (\%) \\',r'\midrule']
for name,label in names.items():
 for method,short in [('global_vcfr_fixed_placement','Global VCFR'),('lbcd_fixed_placement','LBCD adaptation')]:
    pair=[r for r in rows if r['topology']==name and r['method']==method and r['expanded']]
    nominal=next(r for r in pair if r['seed']==0)
    values=[100*r['own_penalty'] for r in pair if r['seed']]
    mean=statistics.mean(values); half=t.ppf(.975,19)*statistics.stdev(values)/len(values)**.5
    lines.append(f'{label} & {short} & {nominal["average_cost"]:.3f} & {nominal["max_compute_util"]:.2f} & ${mean:.2f}\\pm{half:.2f}$ '+r'\\')
lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
(root/'manuscript/tables/published_comparison.tex').write_text('\n'.join(lines)+'\n')
print('Verified and wrote 8-row comparator table')
