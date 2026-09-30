# Braessian-regime packet experiment — protocol fixed before calibration results

Written 2026-09-24 before the timed-service calibration finished and before any policy run with timed service. The earlier batches (`final-001`, `conservative-001`) remain unchanged and are reported as they are.

## Motivation

In the earlier emulation, CPU-bound PBKDF2 stages ran at roughly 20% utilization in the conservative replication. The distributed chains carry a fixed 10 ms round-trip link delay, so the shortcut was faster at every load that did not saturate the host CPU. The equilibrium model predicts no paradox at that operating point. For two symmetric chains with fixed cost c and a shared-stage sojourn time W(λ) at aggregate demand Λ, a harmful expansion equilibrium exists when W(Λ/2) < c. The expanded equilibrium cost is then min(2W(Λ), 2c), compared with the baseline cost W(Λ/2) + c. This experiment places the testbed in that regime using a rule fixed in advance. It then checks whether the measured latency behaves as the calibrated equilibrium model predicts.

## Testbed changes

- Shared instances A and B are single-consumer FIFO servers with a fixed 2 ms timed service. The consumer thread sleeps until the service deadline, so service consumes no CPU and does not depend on host CPU frequency or throttling. Queue limit stays at 512 packets.
- Replica instances C and D use 0.2 ms timed service and keep the 5 ms per-direction link delay. This represents distributed inspection with ample capacity and fixed propagation cost.
- Route selection, EWMA weight 0.3, 5% hysteresis, probes, timeouts and cumulative quotas are unchanged from the earlier experiment.

## Calibration (fixed-route traffic only)

`calibrate_timed.py` sends fixed-route Poisson traffic with no adaptation and no probes. It measures the shared-stage sojourn time on chain A→D at 50–475 requests/s. It also measures low-load (20 requests/s) end-to-end cost on each chain, which gives the per-chain fixed overhead. No policy is run during calibration.

## Rules fixed now

1. Sojourn model: fit W(λ) = s + k·ρ/(1−ρ), with ρ = λ/μ, to the measured shared-stage curve, using least squares on (s, k, μ).
2. Base data rate: Λ = floor(0.9 · μ̂), where μ̂ = 1000 / (mean measured shared-stage service time in ms at 50 requests/s). The demand step multiplies Λ by 1.15.
3. Equilibrium prediction: nonatomic Wardrop equilibrium on the three chains. Chain costs are measured overheads plus W at the shared-stage loads, including probe load (20 probes/s cycling over eligible chains). Each cap κ is solved as a Beckmann program with x_gateway ≤ κΛ.
4. Screened cap: Algorithm 1 on the calibrated model with τ = 0.02 and grid 𝒦 = {1, .75, .5, .35, .25, .15, .10, 0}, evaluated at the base rate.
5. Held-out design: caps {0, 0.25, κ_model, 1} (κ_model counted once if it coincides), both update-phase modes and five fresh seeds 7101–7105. Run order is randomized with seed 7099. Each run lasts 60 s, with gateway activation at 20 s and the demand step at 40 s.
6. Windows: request cohorts [10,20) pre-activation, [30,40) expanded and [50,60) post-step.
7. Primary outcome: paired per-seed percent change in mean completed data-request latency relative to cap 0 in the same seed and mode, with a t interval (4 df). Secondary outcomes: gateway share, p95 latency, measured versus predicted mean cost per cap, and operational stability (same criterion as before, searched within 20 s after each change).
8. Validity: report queue drops, unaccounted requests, cgroup throttling and generator lateness. Every run is retained. No run is excluded or repeated because of its outcome. A crash invalidates the whole batch, which is then rerun in full, and the failure is reported.
9. Model parameters, rate, caps and seeds are not changed after policy results are seen.

## Amendment before prediction (calibration only, no policy runs yet)

The measured shared-stage service time was 3.29 ms at 50 requests/s, compared with the nominal 2 ms. Timer and thread-dispatch overhead inside the Docker VM accounts for the difference. Measured capacity is therefore about 320 requests/s, and the preset curve saturates above 300 requests/s. Rule 2 already uses the measured service time, so it is unchanged. Two calibration-only changes were made:

- A supplementary fixed-route curve at 150, 225, 250, 265, 280 and 290 requests/s (seed 8101) adds points in the relevant utilization range.
- The sojourn fit uses only curve points with no drops and completed equal to offered, because saturated points have no stationary sojourn time.

Both calibration sets are retained.
- Per-chain fixed overhead is the low-load end-to-end cost minus the *measured* shared-stage sojourn in the same run. The first draft subtracted fitted sojourns and produced a physically impossible negative overhead (−0.45 ms) on the shortcut, because the fit is biased at low load. This correction was made before any policy run.

## Frozen before policy runs

Prediction and manifest SHA-256, recorded before the first held-out run:

    fd9d68f0cf3db684af9c130e99497c37fb1641bfce69d9b9aa402f027c7f1d8d  results/braessian-prediction/prediction.json
    75bdd91156c758835a9ce624a2dce5d49c682065cc7cbf344d7bcbcea26f602a  braessian-manifest.json
    4a46a9d7b136f6bd848df836e2dc04b10c22e29886d3118c3819fa83956f66de  predict_braessian.py

## Outcome (recorded after analysis; all 40 runs retained)

See `results/braessian-001/validity.json` and `paired_comparisons.json`. There were no drops and no unaccounted requests, and one run was CPU-throttled. Staggered, seconds 50–60, relative to cap 0: unrestricted +19.2% [10.0, 28.5] (model +39.1%); cap 0.5 +20.8% [10.1, 31.6] (model +7.5%); cap 0.25 +8.1% [−2.2, 18.4] (model −2.4%). Unrestricted gateway share in seconds 30–40 was 0.35 (staggered) and 0.47 (synchronized), against a predicted 0.92. Synchronized comparisons have intervals that include zero, and the original chains oscillated after the demand step in two seeds. Plot presentation was changed to seed medians and per-run lines on a log axis because mean ± t bands crossed zero; the prespecified mean-based intervals are reported unchanged in the table.
