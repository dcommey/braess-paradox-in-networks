# Security-Induced Braess Paradoxes in SFC Orchestration

Reproducible experiment artifact for studying security-induced Braess effects
in service function chain orchestration.

## Contents

- `security_braess/`: Python model for SFC equilibrium, screening, and metrics.
- `scripts/run_experiments.py`: regenerates CSV/JSON results and optional publication-ready tables and figures.
- `experiments/results/`: generated experiment outputs.
- `experiments/data/`: public Abilene X01 traffic matrices and provenance readme.
- `tests/`: regression tests for the core experiment behavior.

## Reproduce

```sh
python3 -m unittest discover -s tests
PYTHONPATH=. python3 scripts/run_experiments.py
```

The default experiment run evaluates 1,000 fixed-seed randomized instances and
also writes true nonlinear-equilibrium, resilience-metric, and
Abilene-demand-calibrated artifacts. When used with a separate manuscript
workspace, the driver can also generate publication-ready LaTeX tables and PDF
figures.
