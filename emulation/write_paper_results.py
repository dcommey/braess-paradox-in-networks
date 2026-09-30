"""Archive descriptive plots for the resource-limited original batch."""
import json
from pathlib import Path
import statistics
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

folder=Path(sys.argv[1]); manuscript=Path(__file__).resolve().parents[1]/'generated'
(manuscript/'tables').mkdir(parents=True, exist_ok=True)
(manuscript/'figures').mkdir(parents=True, exist_ok=True)
validity=json.loads((folder/'validity.json').read_text())
assert validity['runs']==72 and validity['paired_schedules_verified']
metrics=json.loads((folder/'run_metrics.json').read_text())
comparisons=json.loads((folder/'paired_comparisons.json').read_text())
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,
                     'pdf.fonttype':42,'ps.fonttype':42})
fig,axes=plt.subplots(1,2,figsize=(7.1,3.1),layout='constrained')
rates=[632,884,1137]
for ax,window,title in zip(axes,['expanded','step'],['(a) After gateway activation','(b) After the demand increase']):
    for offset,(cap,mode) in enumerate([(1,'staggered'),(1,'synchronized'),(.25,'staggered'),(.25,'synchronized')]):
        points=[next(r for r in comparisons if r['rate']==rate and r['phasing']==mode and r['cap']==cap and r['window']==window) for rate in rates]
        values=[r['mean_paired_penalty_pct'] for r in points]
        errors=[(r['ci_high_pct']-r['ci_low_pct'])/2 for r in points]
        label=('Unrestricted' if cap==1 else '25% quota')+', '+('staggered' if mode=='staggered' else 'synchronized')
        ax.errorbar(np.arange(3)+(offset-1.5)*.075,values,yerr=errors,
                    color='#0072B2' if cap==1 else '#D55E00',marker='o' if mode=='staggered' else '^',
                    linestyle='-' if mode=='staggered' else '--',markersize=4,capsize=2,label=label,linewidth=1)
    ax.axhline(0,color='#555555',linewidth=.7)
    ax.axhline(2,color='#999999',linewidth=.7,linestyle=':')
    ax.set_xticks(range(3),[str(r) for r in rates]);ax.set_xlabel('Base request rate (requests/s)')
    ax.set_ylabel('Mean paired latency change (%)');ax.set_title(title,fontsize=9)
    ax.grid(axis='y',alpha=.15)
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='outside upper center',ncol=2,fontsize=7.5,frameon=False)
fig.savefig(folder/'emulation_penalties.pdf')
fig.savefig(folder/'emulation_penalties.png',dpi=200)
plt.close(fig)
lines=[r'\begin{table}[t]',r'\centering\color{blue}\scriptsize',
 r'\caption{Mean request latency (ms) after activation, and paired unrestricted latency change after the demand step (mean $\pm$ 95\% interval, percentage points). Each entry uses four held-out seeds. Stag. and Sync. denote update phases.}',
 r'\label{tab:emulation}',r'\setlength{\tabcolsep}{3pt}',r'\begin{tabular}{rlrrr}',r'\toprule',
 r'Rate & Mode & Baseline & Unrestricted & Step change (\%) \\',r'\midrule']
for rate in rates:
 for mode in ['staggered','synchronized']:
    mean=lambda cap:statistics.mean(r['expanded_mean_ms'] for r in metrics if r['rate']==rate and r['phasing']==mode and r['cap']==cap)
    row=next(r for r in comparisons if r['rate']==rate and r['phasing']==mode and r['cap']==1 and r['window']=='step')
    half=(row['ci_high_pct']-row['ci_low_pct'])/2
    lines.append(f'{rate} & {"Stag." if mode=="staggered" else "Sync."} & {mean(0):.2f} & {mean(1):.2f} & ${row["mean_paired_penalty_pct"]:.1f}\\pm{half:.1f}$ '+r'\\')
lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
(folder/'emulation_initial.tex').write_text('\n'.join(lines)+'\n')
print('Descriptive figure and table archived for the original 72-run batch')
