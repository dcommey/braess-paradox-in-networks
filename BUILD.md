# Reproducing the experiments

Run these commands from the repository root. Release `tnsm-artifact-2026-09-29` includes `TNSM_reproducibility.zip`, containing the complete retained data and packet traces. Extract it into the repository root to populate trace files omitted from Git. The archive includes per-file SHA-256 hashes in `MANIFEST.json`. Code and numerical summaries are tracked directly in this repository.

## Analytical artifact

Use Python 3.12 and a fresh environment:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r artifact/requirements-revision.txt
cd artifact
../.venv/bin/python -m unittest discover -s tests
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python run_revision_checks.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python run_published_comparison.py
```

The two experiment drivers write to their fixed `revision_results` directories; preserve the supplied results before rerunning them. `revision_results/published_comparison/` is the completed 336-allocation comparison. Its fixed-placement restrictions and mapping to the source algorithm are documented in `literature/comparator-mapping.md`. The Monte Carlo data include all 1,000 attempted simulations and their convergence audit.

## Packet emulation

Docker must support Linux namespaces and NET_ADMIN/SYS_ADMIN inside the isolated container. The original runs used Docker on an Apple M5 host, Linux aarch64, four CPU quota units and 4 GiB container memory. The container has no external network and no host mounts. Synthetic processing workload and calibration are described in `emulation/policy-protocol.md` and the manuscript. Host scheduling and processor behavior can change timing results across machines.

```sh
docker build -t braess-emulation:local emulation
docker run --name braess-reproduction --network none --cpus 4 --memory 4g --pids-limit 512 --cap-add NET_ADMIN --cap-add SYS_ADMIN braess-emulation:local timeout 4200 python3 /experiment/run_batch.py /experiment/final-manifest.json /experiment/final-batch
mkdir -p emulation/results/reproduction
docker cp braess-reproduction:/experiment/final-batch/. emulation/results/reproduction/
.venv/bin/python emulation/summarize_final.py emulation/results/reproduction
```

The initial manifest specifies 72 sequential runs and takes approximately 45 minutes. That batch encountered resource limitations documented in the manuscript. To reproduce the separate conservative-load replication, run a new container with `conservative-manifest.json` and a fresh output directory in place of the two final-batch paths. It specifies 24 runs at 214 requests/s using fresh seeds and takes approximately 14 minutes. Retained final results are in `emulation/results/final-001/`. The summary script requires all completion markers and verifies paired arrival schedules. Each run includes compressed packet/stage traces, configuration, resource counters and its audit. Calibration and pilot results are stored separately. Policy selection uses the pilot seed; final seeds are held out. The empirical pilot screen and equilibrium-model screen have distinct cost estimators.

### Calibrated congestion experiment

The protocol, amendments and frozen prediction digests are in `emulation/braessian-protocol.md`. Shared instances use timed single-server service (`--shared-service-ms 2`), and replicas use `--replica-service-ms 0.2`.

```sh
docker build -t braess-emulation:timed emulation
docker run --name braess-cal --network none --cpus 4 --memory 4g --pids-limit 512 --cap-add NET_ADMIN --cap-add SYS_ADMIN braess-emulation:timed python3 /experiment/calibrate_timed.py /experiment/timed-calibration
docker run --name braess-cal2 --network none --cpus 4 --memory 4g --pids-limit 512 --cap-add NET_ADMIN --cap-add SYS_ADMIN braess-emulation:timed python3 /experiment/calibrate_timed.py /experiment/timed-calibration --seed 8101 --no-routes --rates 150 225 250 265 280 290
.venv/bin/python emulation/predict_braessian.py emulation/results/braessian-prediction emulation/results/timed-calibration-001/calibration.json emulation/results/timed-calibration-002/calibration.json
docker run --name braess-heldout --network none --cpus 4 --memory 4g --pids-limit 512 --cap-add NET_ADMIN --cap-add SYS_ADMIN braess-emulation:timed python3 /experiment/run_batch.py /experiment/braessian-manifest.json /experiment/braessian-batch
.venv/bin/python emulation/summarize_braessian.py emulation/results/braessian-001 emulation/results/braessian-prediction/prediction.json
.venv/bin/python emulation/write_braessian_results.py emulation/results/braessian-001 emulation/results/braessian-prediction/prediction.json
```

The splittable-routing experiment (`emulation/braessian-split-protocol.md`) reuses the calibration and frozen prediction:

```sh
python3 emulation/make_split_manifest.py
docker build -t braess-emulation:split emulation
docker run --name braess-split --network none --cpus 4 --memory 4g --pids-limit 512 --cap-add NET_ADMIN --cap-add SYS_ADMIN braess-emulation:split python3 /experiment/run_batch.py /experiment/braessian-split-manifest.json /experiment/split-batch
.venv/bin/python emulation/summarize_braessian.py emulation/results/braessian-split-001 emulation/results/braessian-prediction/prediction.json
.venv/bin/python emulation/write_braessian_results.py emulation/results/braessian-split-001 emulation/results/braessian-prediction/prediction.json _split
```

Copy each container's output directory out with `docker cp` before the next step. The indivisible batch takes about 45 minutes and the splittable batch about 70 minutes. Retained results are in `emulation/results/timed-calibration-00{1,2}/`, `emulation/results/braessian-prediction/` and `emulation/results/braessian-001/`.

The release archive contains a SHA-256 file manifest. `checksums.json` records its archive hash. Generated numerical summaries retain full precision; tables round only for presentation.

Analytical tables and packet figures are written under `generated/`; the numerical outputs remain in the documented result directories.
