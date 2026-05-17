# Security-Induced Braess Paradoxes in SFC Orchestration

Reproducible experiment artifact for studying security-induced Braess effects
in service function chain orchestration.

## Contents

- `paper/`: LaTeX manuscript, bibliography, figures, and generated tables.
- `security_braess/`: Python model for SFC equilibrium, screening, and metrics.
- `scripts/run_experiments.py`: regenerates results, tables, and plots.
- `tests/`: regression tests for the core experiment behavior.

## Reproduce

```sh
python3 -m unittest discover -s tests
PYTHONPATH=. python3 scripts/run_experiments.py
```

Build the manuscript from `paper/` with `pdflatex`, `bibtex`, `pdflatex`,
`pdflatex`.
