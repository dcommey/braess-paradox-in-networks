"""Figure and table for the held-out Braessian-regime experiment; every run is plotted."""
import json
import sys
from pathlib import Path
import numpy as np
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root, prediction_path = Path(sys.argv[1]), Path(sys.argv[2])
suffix = sys.argv[3] if len(sys.argv) > 3 else ''  # '' for braessian-001, e.g. '_split' for the follow-up
manifest = json.loads((root / 'manifest.json').read_text())
spec0 = manifest['runs'][0]
T, ACT, STEP_AT = int(spec0['seconds']), spec0['activate'], spec0['step_at']
W = {k: manifest.get('windows', {}).get(k, d) for k, d in [('expanded', [30, 40]), ('step', [50, 60])]}
m = Path(__file__).resolve().parents[1] / 'generated'
(m/'tables').mkdir(parents=True, exist_ok=True)
(m/'figures').mkdir(parents=True, exist_ok=True)
validity = json.loads((root / 'validity.json').read_text())
assert validity['runs'] == 40 and validity['paired_schedules_verified']
trajectories = json.loads((root / 'trajectories.json').read_text())
comparisons = json.loads((root / 'paired_comparisons.json').read_text())
prediction = json.loads(prediction_path.read_text())
CAPS = [(0, '#444444', 'Original chains'), (.25, '#009E73', '25% quota'),
        (.5, '#D55E00', '50% quota (model screen)'), (1, '#0072B2', 'Unrestricted')]
plt.rcParams.update({'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42})
fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.8), layout='constrained', sharey=True)
for ax, mode in zip(axes, ['staggered', 'synchronized']):
    for cap, color, label in CAPS:
        curves = np.array([[w['mean_ms'] for w in r['windows']] for r in trajectories
                           if r['spec']['cap'] == cap and r['spec']['phasing'] == mode], dtype=float)
        assert curves.shape == (5, T)
        x = np.arange(T) + .5
        for curve in curves: ax.plot(x, curve, color=color, linewidth=.4, alpha=.25)
        ax.plot(x, np.median(curves, axis=0), color=color, linewidth=1.1, label=label)
        for key, left, right in [('base', ACT, STEP_AT), ('step', STEP_AT, T)]:
            level = next(r for r in prediction[key] if r['cap'] == cap)['mean_cost_ms']
            ax.hlines(level, left, right, colors=color, linestyles='--', linewidth=.7)
    for when in (ACT, STEP_AT): ax.axvline(when, color='#777777', linestyle=':', linewidth=.7)
    ax.set(title=mode.capitalize() + ' updates', xlabel='Time (s)', xlim=(0, T), yscale='log', ylim=(12, 300))
    ax.set_yticks([15, 20, 30, 50, 100, 200], labels=['15', '20', '30', '50', '100', '200'])
    ax.grid(axis='y', alpha=.15)
axes[0].set_ylabel('Mean request latency (ms)')
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='outside upper center', ncol=4, fontsize=8, frameon=False)
fig.savefig(m / f'figures/emulation_braessian{suffix}.pdf'); fig.savefig(m / f'figures/emulation_braessian{suffix}.png', dpi=200)

def cell(row):
    half = (row['ci_high_pct'] - row['ci_low_pct']) / 2
    return f"${row['paired_change_pct']:+.1f}\\pm{half:.1f}$ & ${row['predicted_change_pct']:+.1f}$"
lines = [r'\begin{table}[t]', r'\centering\color{blue}\scriptsize',
         r'\caption{Held-out packet experiment with ' + ('splittable' if suffix else 'indivisible') + r' tenant routing at the calibrated Braessian load. Mean latency and gateway share in seconds ' + f"{W['expanded'][0]}--{W['expanded'][1]}" + r' (measured/model); paired percent change in mean latency relative to original chains in the same window and, after the 15\% demand step, in seconds ' + f"{W['step'][0]}--{W['step'][1]}" + r' (measured mean $\pm$ 95\% interval over five seeds, and model prediction).}',
         r'\label{tab:emulation-' + ('split' if suffix else 'braessian') + '}', r'\setlength{\tabcolsep}{2pt}',
         r'\begin{tabular}{lrrrrrr}', r'\toprule',
         r'& & & \multicolumn{2}{c}{Change, ' + f"{W['expanded'][0]}--{W['expanded'][1]}" + r' s (\%)} & \multicolumn{2}{c}{Change, ' + f"{W['step'][0]}--{W['step'][1]}" + r' s (\%)} \\',
         r'\cmidrule(lr){4-5}\cmidrule(lr){6-7}',
         r'Cap & Lat. (ms) & Share & Meas. & Model & Meas. & Model \\']
for mode in ['staggered', 'synchronized']:
    lines += [r'\midrule', r'\multicolumn{7}{l}{\emph{' + mode.capitalize() + r' updates}} \\']
    for cap, _, _ in CAPS:
        e = next(r for r in comparisons if r['phasing'] == mode and r['cap'] == cap and r['window'] == 'expanded')
        s = next(r for r in comparisons if r['phasing'] == mode and r['cap'] == cap and r['window'] == 'step')
        changes = '--- & --- & --- & ---' if cap == 0 else cell(e) + ' & ' + cell(s)
        lines.append(f"{cap:g} & {e['mean_latency_ms']:.1f}/{e['predicted_cost_ms']:.1f} & "
                     f"{e['gateway_share']:.2f}/{e['predicted_gateway_share']:.2f} & {changes} " + r'\\')
lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
(m / f'tables/emulation_braessian{suffix}.tex').write_text('\n'.join(lines) + '\n')
print('Braessian-regime figure/table generated')
