# Packet-level emulation

The Docker/Mininet testbed executes UDP applications through ordered two-stage chains with per-tenant gateway quotas. `../BUILD.md` gives reproduction commands.

- `braessian-protocol.md`: timed-service calibration, frozen model prediction, and indivisible-routing experiment.
- `braessian-split-protocol.md`: splittable-routing experiment using the same frozen prediction.
- `policy-protocol.md`: processor-bound workload, high-load experiment, and conservative-load configuration.
- `results/`: run configurations, completion/accounting audits, compact summaries, and seed-level trajectories.

The tagged repository release supplies all retained packet and stage traces. Extract the data archive into the repository root before rerunning trace-based summaries. Figure/table writers save regenerated output under `generated/`.

Each policy comparison uses paired arrival schedules. Resource-limited runs remain in the data; protocols describe calibration, load selection, update rules, and the recorded predictions.
