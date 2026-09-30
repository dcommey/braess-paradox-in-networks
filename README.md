# Braess-Aware Security-Service Chain Orchestration

Experiment code and retained results for the routing-game analysis, gateway-exposure screening, fixed-placement load-aware comparison, and packet-level emulation.

## Contents

- `artifact/`: analytical solvers, comparator implementations, pinned dependencies, tests, experiment drivers, and numerical results.
- `emulation/`: Docker/Mininet testbed, calibration and policy protocols, configuration manifests, run audits, and numerical summaries.
- `literature/comparator-mapping.md`: mapping and restrictions of the fixed-placement LBCD-Heu comparison.
- `BUILD.md`: reproduction commands.

## Code and data

Release [`tnsm-artifact-2026-09-29`](https://github.com/dcommey/braess-paradox-in-networks/releases/tag/tnsm-artifact-2026-09-29) includes the complete reproducibility archive with packet/stage traces, calibration data, seeds, resource counters, and per-file SHA-256 hashes. Code and compact results are tracked here; large traces are supplied with the same release. See `BUILD.md` for extraction and reproduction commands.

Packet evaluation covers timed single-server processing with indivisible and splittable tenant routing and a processor-bound cryptographic workload at high and conservative loads. Retained data include resource-limited runs and their audits.

## Quick check

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r artifact/requirements-revision.txt
cd artifact
../.venv/bin/python -m unittest discover -s tests
```

The top-level analytical interface is preserved. The complete paper experiment workflow is documented in `BUILD.md`.
