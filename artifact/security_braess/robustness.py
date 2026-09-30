"""Randomized, nonlinear, and trace-calibrated robustness experiments."""

from __future__ import annotations

from collections import Counter
import gzip
from math import sqrt
from pathlib import Path
from random import Random
from statistics import mean, stdev
from time import perf_counter

from .metrics import paradox_penalty
from .multicommodity import solve_multicommodity_equilibrium, solve_nonlinear_equilibrium
from .topology import all_topologies, nsfnet
from .topology_sfc import (
    _cap_fraction,
    _search_gateway_caps,
    build_topology_sfc_model,
    gateway_share,
    load_hhi,
    maximum_normalized_resource_load,
    normalized_load_entropy,
    single_resource_removal_loss,
)


def run_monte_carlo(instances: int = 1000, seed: int = 20260711, max_penalty: float = 0.02):
    """Generate reproducible heterogeneous SFC instances and retain raw rows."""

    rng = Random(seed)
    topologies = all_topologies()
    rows: list[dict[str, object]] = []
    for instance_id in range(instances):
        topology = topologies[instance_id % len(topologies)]
        request_count = rng.randint(4, min(30, max(8, len(topology.nodes))))
        demands = tuple(rng.uniform(0.45, 1.8) for _ in range(request_count))
        params = {
            "request_count": request_count,
            "demands": demands,
            "gateway_delay": rng.uniform(0.0, 0.55),
            "gateway_slope": rng.uniform(0.02, 0.75),
            "gateway_capacity_factor": rng.uniform(0.65, 1.8),
            "shared_slope_factor": rng.uniform(0.25, 2.25),
            "gateway_risk": rng.uniform(0.1, 0.65),
            "gateway_exposure": rng.uniform(1.0, 3.0),
            "gateway_site_index": rng.randrange(max(1, len(topology.central_nodes()))),
            "vnf_site_offset": rng.randrange(max(1, len(topology.central_nodes()))),
            "distributed_delay": rng.uniform(0.75, 1.35),
            "link_delay_factor": rng.uniform(0.015, 0.04),
            "link_slope_factor": rng.uniform(0.008, 0.05),
            "link_capacity_factor": rng.uniform(0.7, 1.5),
        }
        baseline_model = build_topology_sfc_model(topology, include_gateway=False, **params)
        expanded_model = build_topology_sfc_model(topology, include_gateway=True, **params)
        baseline = solve_multicommodity_equilibrium(baseline_model, tolerance=2e-5)
        naive = solve_multicommodity_equilibrium(expanded_model, tolerance=2e-5)
        start = perf_counter()
        caps = _search_gateway_caps(baseline, expanded_model, max_penalty)
        aware = solve_multicommodity_equilibrium(expanded_model, caps, tolerance=2e-5)
        runtime_ms = 1000.0 * (perf_counter() - start)
        naive_penalty = paradox_penalty(baseline, naive)
        aware_penalty = paradox_penalty(baseline, aware)
        paradox = naive_penalty > 0.0
        rows.append({
            "instance": instance_id,
            "seed": seed,
            "topology": topology.name,
            "requests": request_count,
            "total_demand": sum(demands),
            "demand_min": min(demands),
            "demand_max": max(demands),
            "gateway_delay": params["gateway_delay"],
            "gateway_slope": params["gateway_slope"],
            "gateway_capacity_factor": params["gateway_capacity_factor"],
            "shared_slope_factor": params["shared_slope_factor"],
            "gateway_risk": params["gateway_risk"],
            "gateway_exposure": params["gateway_exposure"],
            "gateway_site_index": params["gateway_site_index"],
            "vnf_site_offset": params["vnf_site_offset"],
            "distributed_delay": params["distributed_delay"],
            "link_delay_factor": params["link_delay_factor"],
            "link_slope_factor": params["link_slope_factor"],
            "link_capacity_factor": params["link_capacity_factor"],
            "paradox": paradox,
            "naive_penalty": naive_penalty,
            "aware_penalty": aware_penalty,
            "mitigated": (not paradox) or aware_penalty <= max_penalty + 1e-6,
            "cap_fraction": _cap_fraction(expanded_model, caps),
            "screen_runtime_ms": runtime_ms,
            "naive_gateway_share": gateway_share(expanded_model, naive),
            "aware_gateway_share": gateway_share(expanded_model, aware),
            "naive_hhi": load_hhi(expanded_model, naive),
            "aware_hhi": load_hhi(expanded_model, aware),
            "naive_entropy": normalized_load_entropy(expanded_model, naive),
            "aware_entropy": normalized_load_entropy(expanded_model, aware),
            "naive_max_normalized_resource_load": maximum_normalized_resource_load(expanded_model, naive),
            "aware_max_normalized_resource_load": maximum_normalized_resource_load(expanded_model, aware),
            "naive_removal_loss": single_resource_removal_loss(expanded_model, naive),
            "aware_removal_loss": single_resource_removal_loss(expanded_model, aware),
            "screen_equilibrium_solves": next(
                index for index, fraction in enumerate(
                    (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.0), start=1
                ) if abs(fraction - float(_cap_fraction(expanded_model, caps))) < 1e-9
            ),
            "baseline_converged": baseline.converged,
            "naive_converged": naive.converged,
            "aware_converged": aware.converged,
        })
    return rows


def summarize_monte_carlo(rows: list[dict[str, object]]) -> dict[str, object]:
    attempted = len(rows)
    failed = [row for row in rows if not all(bool(row[key]) for key in
              ("baseline_converged", "naive_converged", "aware_converged"))]
    rows = [row for row in rows if row not in failed]
    n = len(rows)
    paradox_rows = [row for row in rows if bool(row["paradox"])]
    mitigated = [row for row in paradox_rows if bool(row["mitigated"])]
    prevalence = len(paradox_rows) / n if n else 0.0
    success = len(mitigated) / len(paradox_rows) if paradox_rows else 0.0
    runtimes = [float(row["screen_runtime_ms"]) for row in rows]
    penalties = [float(row["naive_penalty"]) for row in rows]
    paradox_caps = [float(row["cap_fraction"]) for row in paradox_rows]
    paradox_shares = [float(row["aware_gateway_share"]) for row in paradox_rows]
    positive_caps = [value for value in paradox_caps if value > 0.0]
    reductions = [
        float(row["naive_penalty"]) - float(row["aware_penalty"])
        for row in paradox_rows
    ]
    solves = [int(row["screen_equilibrium_solves"]) for row in rows]
    return {
        "instances_attempted": attempted,
        "instances": n,
        "excluded_nonconverged": len(failed),
        "excluded_instance_ids": [int(row["instance"]) for row in failed],
        "paradox_instances": len(paradox_rows),
        "paradox_prevalence": prevalence,
        "paradox_prevalence_ci95": _wilson(len(paradox_rows), n),
        "mitigation_success": success,
        "mitigation_success_ci95": _wilson(len(mitigated), len(paradox_rows)),
        "positive_cap_instances": len(positive_caps),
        "positive_cap_rate": len(positive_caps) / len(paradox_rows) if paradox_rows else 0.0,
        "zero_cap_instances": len(paradox_caps) - len(positive_caps),
        "zero_cap_rate": 1.0 - len(positive_caps) / len(paradox_rows) if paradox_rows else 0.0,
        "mean_selected_cap": mean(paradox_caps) if paradox_caps else 0.0,
        "median_selected_cap": sorted(paradox_caps)[len(paradox_caps) // 2] if paradox_caps else 0.0,
        "mean_selected_gateway_share": mean(paradox_shares) if paradox_shares else 0.0,
        "median_selected_gateway_share": sorted(paradox_shares)[len(paradox_shares) // 2] if paradox_shares else 0.0,
        "mean_penalty_reduction": mean(reductions) if reductions else 0.0,
        "mean_screen_equilibrium_solves": mean(solves) if solves else 0.0,
        "mean_naive_penalty": mean(penalties) if penalties else 0.0,
        "mean_naive_penalty_ci95": _mean_ci(penalties),
        "mean_screen_runtime_ms": mean(runtimes) if runtimes else 0.0,
        "mean_screen_runtime_ci95": _mean_ci(runtimes),
        "median_screen_runtime_ms": sorted(runtimes)[n // 2] if n else 0.0,
        "cap_distribution": dict(sorted(Counter(f"{value:.2f}" for value in paradox_caps).items())),
        "convergence_rate": n / attempted if attempted else 0.0,
    }


def run_nonlinear_suite(max_penalty: float = 0.02):
    """Recompute baseline, naive, and screened equilibria under affine-plus-quintic delays."""

    rows = []
    for topology in all_topologies():
        params = {"gateway_slope": 0.25}
        baseline_model = build_topology_sfc_model(topology, include_gateway=False, **params)
        expanded_model = build_topology_sfc_model(topology, include_gateway=True, **params)
        baseline = solve_nonlinear_equilibrium(baseline_model)
        naive = solve_nonlinear_equilibrium(expanded_model)
        best_caps = None
        aware = None
        for fraction in (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.0):
            from .topology_sfc import _gateway_caps
            caps = _gateway_caps(expanded_model, fraction)
            candidate = solve_nonlinear_equilibrium(expanded_model, caps)
            if paradox_penalty(baseline, candidate) <= max_penalty:
                best_caps, aware = caps, candidate
                break
        assert best_caps is not None and aware is not None
        rows.append({
            "topology": topology.name,
            "gateway_slope": 0.25,
            "baseline_cost": baseline.average_cost,
            "naive_cost": naive.average_cost,
            "aware_cost": aware.average_cost,
            "naive_penalty": paradox_penalty(baseline, naive),
            "aware_penalty": paradox_penalty(baseline, aware),
            "cap_fraction": _cap_fraction(expanded_model, best_caps),
            "baseline_iterations": baseline.iterations,
            "naive_iterations": naive.iterations,
            "aware_iterations": aware.iterations,
            "all_converged": baseline.converged and naive.converged and aware.converged,
        })
    return rows


def run_trace_calibrated_case(max_penalty: float = 0.02):
    """Abilene-demand-inspired case using the public 11-node backbone scale.

    The repository's NSFNET graph supplies routing geometry; demand magnitudes
    follow the normalized heavy-tailed scale commonly seen in the public
    Abilene traffic-matrix archive.  The result is therefore trace-calibrated,
    not a packet-level replay of the original backbone.
    """

    topology = nsfnet()
    trace = Path(__file__).resolve().parents[1] / "experiments" / "data" / "abilene_X01.gz"
    demands = _abilene_source_profile(trace)
    params = dict(request_count=len(demands), demands=demands, gateway_slope=0.2,
                  gateway_capacity_factor=1.25, shared_slope_factor=0.9,
                  gateway_delay=0.08, distributed_delay=1.02)
    baseline_model = build_topology_sfc_model(topology, include_gateway=False, **params)
    expanded_model = build_topology_sfc_model(topology, include_gateway=True, **params)
    baseline = solve_multicommodity_equilibrium(baseline_model)
    naive = solve_multicommodity_equilibrium(expanded_model)
    caps = _search_gateway_caps(baseline, expanded_model, max_penalty)
    aware = solve_multicommodity_equilibrium(expanded_model, caps)
    return [{
        "case": "Abilene-X01-trace-calibrated",
        "trace_file": str(trace.relative_to(Path(__file__).resolve().parents[1])),
        "requests": len(demands),
        "total_demand": sum(demands),
        "gateway_slope": 0.2,
        "baseline_cost": baseline.average_cost,
        "naive_cost": naive.average_cost,
        "aware_cost": aware.average_cost,
        "naive_penalty": paradox_penalty(baseline, naive),
        "aware_penalty": paradox_penalty(baseline, aware),
        "cap_fraction": _cap_fraction(expanded_model, caps),
        "all_converged": baseline.converged and naive.converged and aware.converged,
    }]


def _abilene_source_profile(path: Path) -> tuple[float, ...]:
    """Return normalized mean outbound demands from the 12x12 real-OD TMs."""

    if not path.exists():
        raise FileNotFoundError(f"missing public Abilene trace: {path}")
    totals = [0.0] * 12
    samples = 0
    with gzip.open(path, "rt", encoding="ascii") as handle:
        for line in handle:
            values = [float(value) for value in line.split()]
            if len(values) != 720:
                raise ValueError("Abilene X01 row must contain 144x5 values")
            real_od = values[0::5]
            for source in range(12):
                totals[source] += sum(
                    real_od[source * 12 + destination]
                    for destination in range(12) if destination != source
                )
            samples += 1
    means = [value / samples for value in totals]
    scale = sum(means) / len(means)
    return tuple(value / scale for value in means)


def _wilson(successes: int, trials: int) -> list[float]:
    if trials <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    half = z * sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _mean_ci(values: list[float]) -> list[float]:
    if not values:
        return [0.0, 0.0]
    center = mean(values)
    if len(values) == 1:
        return [center, center]
    half = 1.959963984540054 * stdev(values) / sqrt(len(values))
    return [center - half, center + half]
