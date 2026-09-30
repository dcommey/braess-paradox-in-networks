# SFC experiment design — before policy outcomes

## Processing semantics

Each chain traverses two synthetic processing functions. Each function executes the same independently calibrated PBKDF2 workload at its shared instance and its dedicated replica. Label the workload as emulated processing throughout. Each instance has one FIFO consumer; retain arrival, service-start and service-end timestamps. There is no detection dataset or measured detection outcome.

Instantiate shared stages A and B, and replicas C (same function as A) and D (same function as B). Eligible ordered chains are A→D, C→B, and A→B. The third chain exposes both shared instances. Fixed propagation delay on C and D links represents geographic placement; use 5 ms per link direction. Verify chain traces, identical work, and shared-instance coupling before enabling adaptation.

Use separate Mininet namespaces for the traffic source, each processing instance and an IP forwarding node. The forwarding node connects isolated /24 links, with explicit routes. No traffic leaves the container. Same-clock monotonic timestamps permit request latency and processing/queue accounting. Save stage logs for all packets, including probes and drops.

## Inputs and comparisons

Estimate single-stage service capacity from the independent processing calibration after separating compute time and scheduling overhead. The first pilot showed load-dependent service elapsed time; resolve this before fixing the estimate. Before policy runs, save the estimate and calculation. Use offered aggregate rates at 0.5, 0.7 and 0.9 of that estimate. Keep propagation delay fixed across these scenarios; report the observed penalty at each rate, including its sign. No parameter search based on obtaining a paradox is authorized by this protocol.

Use 20 logical tenants with independent Poisson arrivals and independently phased measured-delay route updates. Save scheduled and actual send times to detect generator lateness. Compare original two-chain routing, unrestricted expansion, a fixed quota and a screened quota. Use shared random arrival schedules across paired policies. Include synchronized and staggered update phases and a demand step. Separate training/calibration used to screen quotas from evaluation repeats. Define the screened selector, its error tolerance, and the settling criterion explicitly before measurement.

Enforce quotas on cumulative offered application packets per tenant: a shortcut assignment must satisfy gateway_count ≤ floor(cap × offered_count). Reassign excess traffic to the best eligible original chain. Log the requested and executed route and counters. Probe traffic is separate overhead; log its complete rate and stage usage, and include it when auditing total processing load.

## Required evidence

Validate sequence uniqueness, ordered stage traces, stage service serialization, offered/received/drop reconciliation, quota inequalities and output completeness. Summarize latency among completed requests alongside completion rate and queue losses. Report independent-run paired differences and uncertainty; individual packets are correlated and cannot serve as independent statistical replicates. Keep pilot and final runs distinct. Final policy implementation and run duration, screening protocol, settling criterion and repeats remain to be specified before the first policy experiment.

## Held-out protocol fixed before evaluation

The nine constant-load pilots are calibration data. On cap grid {0, .25, 1}, select the largest cap with mean completed-request latency over seconds 20–30 at most 1.02 times the paired baseline and no completion loss. Seed 4101 selected cap 1 at all three loads. These empirical selections use one calibration replicate and require held-out assessment. The selected policy therefore shares the unrestricted execution in this evaluation; do not count duplicate observations as independent evidence. This is a measured pilot screen, with scope distinct from the analytical equilibrium solver.

The held-out manifest has 72 runs: three base rates, two update-phase modes, four independent seeds (5101–5104), and three distinct caps (0, .25, 1). Each lasts 30 seconds, with gateway activation at 10 seconds and a 15% demand increase at 20 seconds. All pairs share scheduled arrivals; the same phase RNG draw is consumed in both modes. Order is randomized with seed 5099. Summaries use request cohorts [5,10), [15,20), and [25,30); uncertainty uses per-seed paired differences, never individual packets as independent replicates. Report both loss and completed-request delay.

A post-change trajectory meets the operational stability criterion at the start of the first five consecutive one-second bins whose latency means are all within max(2 ms, 10% of their five-bin mean) of that mean and whose route-share L1 distances from the five-bin average are at most .10. Search only within each ten-second post-change interval; report unmet criteria as censored. This criterion assesses short-window stability and does not establish a Wardrop equilibrium. Keep the initial post-change bins for transient peak reporting. Retain queue drops, unaccounted packets, cgroup throttling and generator lateness as validity diagnostics.

## Conservative-load replication after the original batch

The original 72-run batch completed, but 51 runs recorded cgroup CPU throttling and the pre-activation latencies varied substantially. All original runs remain in the artifact. A separate 24-run replication fixes the base rate to floor(0.5 × 1000 / 2.3328458277571253) = 214 requests/s, using the maximum per-run mean service time in the independent processing-002 calibration. This load is fixed before the replication outcomes. The replication uses new seeds 6101–6104, both phase modes, caps 0/.25/1, the same 30-second duration and change times, and randomized order seed 6099. It compares the three caps directly; there is no fitted pilot screen at this new load. Retain every run and report CPU throttling, losses and pre-activation behavior before interpreting differences. Scope is low-load operation on this host.
