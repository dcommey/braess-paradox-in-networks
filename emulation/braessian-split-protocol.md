# Splittable-routing follow-up — protocol fixed before implementation and runs

Written 2026-09-24, after the analysis of `results/braessian-001` and before any code for this follow-up. That experiment remains reported in full. Its main divergence from the model came from indivisible tenant routing: a single preference change moved 5% of demand on a steep delay curve. The equilibrium model assumes nonatomic, splittable demand. This follow-up tests the same frozen prediction with tenant routing that matches that assumption.

## Fixed elements (unchanged from braessian-protocol.md)

- Testbed, timed service (shared 2 ms, replicas 0.2 ms), 5 ms replica links, probes, EWMA weight 0.3, timeout score and cumulative quota enforcement are unchanged.
- The calibration and the frozen prediction are reused without change: `results/braessian-prediction/prediction.json` (SHA-256 fd9d68f0…). Base rate is 273 requests/s, the demand step is 1.15, and caps are {0, 0.25, 0.5, 1}. κ = 0.5 is the model-screened cap.

## Routing change

- Each tenant keeps split weights over eligible chains, starting at (0.5, 0.5, 0). Each data request samples its chain from the weights using a per-tenant RNG separate from the arrival RNG, so paired arrival schedules are preserved.
- Once per second, in staggered or synchronized phase as before, the tenant finds the cheapest eligible chain b by estimated cost. Each other eligible chain r with c_r > 1.05·c_b transfers β·w_r·(c_r − c_b)/c_r of its weight to b, with β = 0.2 fixed here.
- The gateway weight is clipped at κ, and any excess moves to the cheaper original chain. Cumulative quota enforcement per packet is unchanged.

## Design and analysis

- Seeds 7201–7205, both update modes, four caps: 40 runs. Order is randomized with seed 7199.
- Runs last 90 s. The gateway is activated at 20 s and demand steps up at 60 s, which gives the proportional dynamics time to approach equilibrium.
- Windows: pre-activation [10,20), expanded [45,60) and post-step [75,90).
- Primary outcome, validity reporting and stability criterion are the same as in braessian-protocol.md (stability searched within the 40 s and 30 s intervals after each change). Every run is retained, nothing is excluded or repeated, and a crash invalidates and reruns the whole batch.
- Both experiments are reported in the manuscript.

## Pipeline smoke test (before the held-out batch)

One 30 s run at seed 9001 (not an analysis seed), cap 0.25, staggered, split_step 0.2, to verify the splittable-routing code path. Only the packet/quota audit result was inspected: it passed. It is not part of the analysis.

## Frozen before the held-out batch

    b2c105a93c80cc722c4942364691b586b23b3f6e33f5a1487b2fa2f45a3e1cb9  braessian-split-manifest.json
    a2e7511eaf068e6fd5c4521873a338f848dbca6071b8516bdcf3a424b99c2d2a  route_client.py
    d560a2b77482c9890c570893bf06ac2ce14baea0a8551ba679e63060b9e5b720  run_policy.py
    f4ca24034fdcc95f65e3d5888db1fc07bd553095cc53de213e2934ce66236055  make_split_manifest.py
    fd9d68f0cf3db684af9c130e99497c37fb1641bfce69d9b9aa402f027c7f1d8d  results/braessian-prediction/prediction.json

## Outcome (recorded after analysis; all 40 runs retained)

No drops, no unaccounted requests and no throttling. Pre-activation latency was 17.6–19.5 ms (model 19.7). Seconds 45–60 relative to cap 0 (staggered / synchronized): cap 0.25 −5.2% / −3.9% (model −5.7%); cap 0.5 −6.4% / +0.6% (model −6.3%); unrestricted +5.8% [−12.4, 24.0] / +24.1% [7.0, 41.3] (model +41.7%), with gateway share levelling off at 0.76 / 0.67 (model 0.92). Seconds 75–90 after the demand step: unrestricted +57.5% [8.1, 106.9] / +50.4% [37.0, 63.8] (model +39.1%); cap 0.5 +11.3% [−5.4, 28.0] / +40.9% [31.5, 50.3] (model +7.5%); cap 0.25 −1.9% / +0.7% (model −2.4%).
