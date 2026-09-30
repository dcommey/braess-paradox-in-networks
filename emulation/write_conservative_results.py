"""Plot all conservative replication trajectories without dropping runs."""
import json,statistics,sys
from pathlib import Path
import numpy as np
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=Path(sys.argv[1]);m=Path(__file__).resolve().parents[1]/'generated'
(m/'tables').mkdir(parents=True, exist_ok=True)
(m/'figures').mkdir(parents=True, exist_ok=True)
v=json.loads((p/'validity.json').read_text()); assert v['runs']==24 and v['paired_schedules_verified']
a=json.loads((p/'run_metrics.json').read_text());tr=json.loads((p/'trajectories.json').read_text());c=json.loads((p/'paired_comparisons.json').read_text())
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axes=plt.subplots(1,2,figsize=(7.1,2.7),layout='constrained')
for ax,mode in zip(axes,['staggered','synchronized']):
 for cap,color,label in [(0,'#444444','Original chains'),(.25,'#D55E00','25% cumulative quota'),(1,'#0072B2','Unrestricted')]:
  curves=np.array([[w['mean_ms'] for w in r['windows']] for r in tr if r['spec']['cap']==cap and r['spec']['phasing']==mode]);assert curves.shape==(4,30)
  avg=curves.mean(axis=0);half=t.ppf(.975,3)*curves.std(axis=0,ddof=1)/2
  x=np.arange(30)+.5;ax.plot(x,avg,label=label,color=color,linewidth=1);ax.fill_between(x,avg-half,avg+half,color=color,alpha=.12)
 ax.axvline(10,color='#777777',linestyle=':',linewidth=.7);ax.axvline(20,color='#777777',linestyle=':',linewidth=.7)
 ax.set(title=mode.capitalize()+' updates',xlabel='Time (s)',ylabel='Mean request latency (ms)',xlim=(0,30));ax.grid(axis='y',alpha=.15)
handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=3,fontsize=8,frameon=False)
fig.savefig(m/'figures/emulation_conservative.pdf');fig.savefig(m/'figures/emulation_conservative.png',dpi=200)
lines=[r'\begin{table}[t]',r'\centering\color{blue}\scriptsize',r'\caption{Conservative-load replication at 214 requests/s. Mean latency in seconds 15--20 (ms) and paired percent change relative to original chains in seconds 25--30, after the demand step (mean $\pm$ 95\% interval). Four fresh seeds per comparison.}',r'\label{tab:emulation}',r'\setlength{\tabcolsep}{3pt}',r'\begin{tabular}{llrr}',r'\toprule',r'Updates & Policy & Latency & Step change (\%) \\',r'\midrule']
for mode in ['staggered','synchronized']:
 for cap,label in [(0,'Original'),(.25,'25% cumulative quota'),(1,'Unrestricted')]:
  mean=statistics.mean(r['expanded_mean_ms'] for r in a if r['phasing']==mode and r['cap']==cap)
  diff='---'
  if cap:
   r=next(r for r in c if r['phasing']==mode and r['cap']==cap and r['window']=='step');half=(r['ci_high_pct']-r['ci_low_pct'])/2;diff=f'${r["mean_paired_penalty_pct"]:.1f}\\pm{half:.1f}$'
  label=label.replace('%',r'\%')
  lines.append(f'{mode.capitalize()} & {label} & {mean:.2f} & {diff} '+r'\\')
lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}'];(m/'tables/emulation.tex').write_text('\n'.join(lines)+'\n')
print('Conservative replication figure/table generated')
