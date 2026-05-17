"""Topology-derived SFC/NFV experiment construction and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from .metrics import paradox_penalty, security_braess_ratio
from .model import Resource
from .multicommodity import (
    MCEquilibriumResult,
    MCPath,
    MultiServiceModel,
    Request,
    solve_multicommodity_equilibrium,
    solve_system_optimum,
    solve_weighted_equilibrium,
)
from .topology import Topology, all_topologies, edge_key


@dataclass(frozen=True)
class PolicyEvaluation:
    topology: str
    policy: str
    model: MultiServiceModel
    result: MCEquilibriumResult
    baseline: MCEquilibriumResult
    path_caps: dict[str, float]

    @property
    def penalty(self) -> float:
        return paradox_penalty(self.baseline, self.result)

    @property
    def sbr(self) -> float:
        return security_braess_ratio(self.baseline, self.result)


def build_topology_sfc_model(
    topology: Topology,
    *,
    include_gateway: bool,
    request_count: int | None = None,
    gateway_delay: float = 0.04,
    gateway_capacity_factor: float = 1.0,
    shared_slope_factor: float = 1.0,
    gateway_risk: float = 0.42,
    gateway_exposure: float = 2.4,
) -> MultiServiceModel:
    """Build a multi-tenant security-service-chain model on a topology.

    The construction embeds the Braess mechanism into realistic SFC resources:
    distributed FW/IDS/WAF chains are available before intervention, while the
    defensive expansion exposes a shared zero-trust inspection gateway. Link
    resources, endpoints, and auxiliary VNF sites are selected from the supplied
    topology.
    """

    nodes = list(topology.nodes)
    central = topology.central_nodes()
    peripheral = topology.peripheral_nodes()
    if request_count is None:
        request_count = min(8, max(4, len(nodes) // 5))

    requests: list[Request] = []
    for idx in range(request_count):
        source = peripheral[idx % len(peripheral)]
        destination = peripheral[-(idx % len(peripheral)) - 1]
        if source == destination:
            destination = peripheral[-((idx + 1) % len(peripheral)) - 1]
        requests.append(
            Request(
                name=f"tenant_{idx+1}",
                demand=1.0,
                source=source,
                destination=destination,
            )
        )

    total_demand = sum(request.demand for request in requests)
    resources: dict[str, Resource] = {}
    paths: list[MCPath] = []

    resources["shared_ingress_security_plane"] = Resource(
        "shared_ingress_security_plane",
        base_delay=0.0,
        slope=1.0 * shared_slope_factor,
        capacity=total_demand,
        risk=0.08,
        exposure=1.1,
        kind="security_vnf",
    )
    resources["shared_egress_security_plane"] = Resource(
        "shared_egress_security_plane",
        base_delay=0.0,
        slope=1.0 * shared_slope_factor,
        capacity=total_demand,
        risk=0.08,
        exposure=1.1,
        kind="security_vnf",
    )
    resources["central_zero_trust_gateway"] = Resource(
        "central_zero_trust_gateway",
        base_delay=gateway_delay,
        slope=0.0,
        capacity=total_demand * gateway_capacity_factor,
        risk=gateway_risk,
        exposure=gateway_exposure,
        kind="security_vnf",
    )

    for idx, request in enumerate(requests):
        left_site = central[(2 * idx + 1) % len(central)]
        right_site = central[(2 * idx + 2) % len(central)]
        gateway_site = central[0]

        left_links = _route_resources(topology, request.source, left_site, resources)
        left_links += _route_resources(topology, left_site, request.destination, resources)
        right_links = _route_resources(topology, request.source, right_site, resources)
        right_links += _route_resources(topology, right_site, request.destination, resources)
        gateway_links = _route_resources(topology, request.source, gateway_site, resources)
        gateway_links += _route_resources(topology, gateway_site, request.destination, resources)

        left_constant = f"distributed_ids_left:{request.name}"
        right_constant = f"distributed_ids_right:{request.name}"
        resources[left_constant] = Resource(
            left_constant,
            base_delay=1.04 + 0.01 * (idx % 3),
            slope=0.0,
            capacity=2.0,
            risk=0.045,
            exposure=0.8,
            kind="security_vnf",
        )
        resources[right_constant] = Resource(
            right_constant,
            base_delay=1.04 + 0.012 * (idx % 4),
            slope=0.0,
            capacity=2.0,
            risk=0.045,
            exposure=0.8,
            kind="security_vnf",
        )

        paths.append(
            MCPath(
                name=f"{request.name}:distributed_left",
                request=request.name,
                resources=tuple(
                    ["shared_ingress_security_plane", left_constant] + left_links
                ),
                tag="baseline",
            )
        )
        paths.append(
            MCPath(
                name=f"{request.name}:distributed_right",
                request=request.name,
                resources=tuple(
                    [right_constant, "shared_egress_security_plane"] + right_links
                ),
                tag="baseline",
            )
        )
        if include_gateway:
            paths.append(
                MCPath(
                    name=f"{request.name}:central_gateway",
                    request=request.name,
                    resources=tuple(
                        [
                            "shared_ingress_security_plane",
                            "central_zero_trust_gateway",
                            "shared_egress_security_plane",
                        ]
                        + gateway_links
                    ),
                    tag="defensive_expansion",
                )
            )

    return MultiServiceModel(
        name=f"{topology.name}_{'expanded' if include_gateway else 'baseline'}",
        resources=resources,
        requests=tuple(requests),
        paths=tuple(paths),
        metadata={
            "topology": topology.name,
            "nodes": len(topology.nodes),
            "edges": len(topology.edges),
            "requests": len(requests),
        },
    )


def evaluate_topology_suite(max_penalty: float = 0.02) -> list[PolicyEvaluation]:
    evaluations: list[PolicyEvaluation] = []
    for topology in all_topologies():
        baseline_model = build_topology_sfc_model(topology, include_gateway=False)
        expanded_model = build_topology_sfc_model(topology, include_gateway=True)
        baseline = solve_multicommodity_equilibrium(baseline_model)

        policies = [
            ("baseline", baseline_model, {}),
            ("naive_expansion", expanded_model, {}),
            ("load_aware_cap_0.50", expanded_model, _gateway_caps(expanded_model, 0.50)),
            ("risk_aware_surcharge", expanded_model, {}),
            ("minmax_utilization_cap", expanded_model, _minmax_utilization_caps(expanded_model)),
            ("system_optimum_expansion", expanded_model, {}),
            ("paradox_aware", expanded_model, _search_gateway_caps(baseline, expanded_model, max_penalty)),
        ]
        for name, model, caps in policies:
            if name == "baseline":
                result = baseline
            elif name == "system_optimum_expansion":
                result = solve_system_optimum(model, caps)
            elif name == "risk_aware_surcharge":
                result = solve_weighted_equilibrium(model, risk_weight=1.0, exposure_weight=0.0)
            else:
                result = solve_multicommodity_equilibrium(model, caps)
            evaluations.append(
                PolicyEvaluation(
                    topology=topology.name,
                    policy=name,
                    model=model,
                    result=result,
                    baseline=baseline,
                    path_caps=dict(caps),
                )
            )
    return evaluations


def risk_concentration_index(model: MultiServiceModel, result: MCEquilibriumResult) -> float:
    weights = []
    for name, resource in model.resources.items():
        load = result.loads.get(name, 0.0)
        weight = load * resource.risk * resource.exposure
        if weight > 0:
            weights.append(weight)
    total = sum(weights)
    if total <= 0:
        return 0.0
    return sum((weight / total) ** 2 for weight in weights)


def expected_attack_loss(model: MultiServiceModel, result: MCEquilibriumResult) -> float:
    losses = []
    for name, resource in model.resources.items():
        load = result.loads.get(name, 0.0)
        share = load / model.total_demand
        overload = max(0.0, load / resource.capacity - 1.0)
        losses.append(
            resource.risk
            * resource.exposure
            * share
            * share
            * model.total_demand
            * (1.0 + overload)
        )
    return max(losses, default=0.0)


def worst_ddos_loss(model: MultiServiceModel, result: MCEquilibriumResult) -> tuple[str, float, float]:
    target, resource = max(
        model.resources.items(),
        key=lambda item: (
            result.loads.get(item[0], 0.0) / item[1].capacity,
            result.loads.get(item[0], 0.0),
            item[1].exposure,
        ),
    )
    load = result.loads.get(target, 0.0)
    share = load / model.total_demand
    overload = max(0.0, load / resource.capacity - 1.0)
    service_loss = 1.25 * share * (1.0 + overload) * (1.0 + resource.risk * resource.exposure)
    return target, share, service_loss


def summarize_evaluations(evaluations: list[PolicyEvaluation]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for evaluation in evaluations:
        target, affected_share, ddos_loss = worst_ddos_loss(evaluation.model, evaluation.result)
        rows.append(
            {
                "topology": evaluation.topology,
                "policy": evaluation.policy,
                "nodes": evaluation.model.metadata["nodes"],
                "edges": evaluation.model.metadata["edges"],
                "requests": evaluation.model.metadata["requests"],
                "average_cost": evaluation.result.average_cost,
                "paradox_penalty": evaluation.penalty,
                "security_braess_ratio": evaluation.sbr,
                "risk_concentration": risk_concentration_index(evaluation.model, evaluation.result),
                "expected_attack_loss": expected_attack_loss(evaluation.model, evaluation.result),
                "ddos_target": target,
                "ddos_affected_share": affected_share,
                "ddos_service_loss": ddos_loss,
                "max_utilization": max_utilization(evaluation.model, evaluation.result),
                "gateway_share": gateway_share(evaluation.model, evaluation.result),
                "queueing_curve_cost": queueing_curve_cost(evaluation.model, evaluation.result),
                "converged": evaluation.result.converged,
                "iterations": evaluation.result.iterations,
            }
        )
    return rows


def queueing_curve_cost(model: MultiServiceModel, result: MCEquilibriumResult) -> float:
    """Evaluate a flow under a convex queueing-style delay curve.

    This is a robustness check rather than a second equilibrium solve. It asks
    whether the policy-induced flow remains harmful when affine delays are
    replaced by a steeper M/M/1-like service curve.
    """

    total = 0.0
    for path in model.paths:
        flow = result.flows.get(path.name, 0.0)
        if flow <= 0:
            continue
        cost = 0.0
        for resource_name in path.resources:
            resource = model.resources[resource_name]
            load = result.loads.get(resource_name, 0.0)
            utilization = min(0.98, load / resource.capacity)
            cost += resource.base_delay + resource.slope * utilization / max(1e-6, 1.0 - utilization)
        total += flow * cost
    return total / model.total_demand


def run_sensitivity_suite(max_penalty: float = 0.02) -> list[dict[str, object]]:
    """One-factor sensitivity sweeps on the NSFNET-style topology."""

    topology = next(topo for topo in all_topologies() if topo.name == "nsfnet")
    rows: list[dict[str, object]] = []
    sweeps: list[tuple[str, list[float]]] = [
        ("gateway_delay", [0.0, 0.04, 0.12, 0.24]),
        ("gateway_capacity_factor", [0.5, 0.75, 1.0, 1.5]),
        ("shared_slope_factor", [0.5, 1.0, 1.5, 2.0]),
        ("tau", [0.0, 0.01, 0.02, 0.05]),
        ("gateway_risk_exposure_scale", [0.5, 1.0, 1.5, 2.0]),
    ]
    defaults = {
        "gateway_delay": 0.04,
        "gateway_capacity_factor": 1.0,
        "shared_slope_factor": 1.0,
        "gateway_risk": 0.42,
        "gateway_exposure": 2.4,
    }
    for parameter, values in sweeps:
        for value in values:
            params = dict(defaults)
            tau = max_penalty
            if parameter == "tau":
                tau = value
            elif parameter == "gateway_risk_exposure_scale":
                params["gateway_risk"] = defaults["gateway_risk"] * value
                params["gateway_exposure"] = defaults["gateway_exposure"] * value
            else:
                params[parameter] = value
            baseline_model = build_topology_sfc_model(topology, include_gateway=False, **params)
            expanded_model = build_topology_sfc_model(topology, include_gateway=True, **params)
            baseline = solve_multicommodity_equilibrium(baseline_model)
            naive = solve_multicommodity_equilibrium(expanded_model)
            caps = _search_gateway_caps(baseline, expanded_model, tau)
            aware = solve_multicommodity_equilibrium(expanded_model, caps)
            rows.append(
                {
                    "parameter": parameter,
                    "value": value,
                    "tau": tau,
                    "naive_penalty": paradox_penalty(baseline, naive),
                    "aware_penalty": paradox_penalty(baseline, aware),
                    "aware_gain": (naive.average_cost - aware.average_cost) / naive.average_cost,
                    "naive_attack_loss": expected_attack_loss(expanded_model, naive),
                    "aware_attack_loss": expected_attack_loss(expanded_model, aware),
                    "cap_fraction": _cap_fraction(expanded_model, caps),
                }
            )
    return rows


def aggregate_claims(rows: list[dict[str, object]]) -> dict[str, float]:
    by_topology: dict[str, dict[str, dict[str, object]]] = {}
    for row in rows:
        by_topology.setdefault(str(row["topology"]), {})[str(row["policy"])] = row
    naive_penalties = [
        float(group["naive_expansion"]["paradox_penalty"])
        for group in by_topology.values()
    ]
    paradox_reductions = []
    attack_reductions = []
    for group in by_topology.values():
        naive_cost = float(group["naive_expansion"]["average_cost"])
        aware_cost = float(group["paradox_aware"]["average_cost"])
        paradox_reductions.append((naive_cost - aware_cost) / naive_cost)
        naive_attack = float(group["naive_expansion"]["expected_attack_loss"])
        aware_attack = float(group["paradox_aware"]["expected_attack_loss"])
        attack_reductions.append((naive_attack - aware_attack) / naive_attack)
    return {
        "mean_naive_penalty": mean(naive_penalties),
        "min_naive_penalty": min(naive_penalties),
        "max_naive_penalty": max(naive_penalties),
        "mean_paradox_aware_reduction": mean(paradox_reductions),
        "mean_attack_loss_reduction": mean(attack_reductions),
    }


def experiment_parameters() -> list[dict[str, object]]:
    return [
        {"parameter": "Tenant demand $d_r$", "value": "1.0 for every request"},
        {"parameter": "Gateway free-flow delay $b_g$", "value": "0.04"},
        {"parameter": "Gateway capacity factor", "value": "1.0 times total demand"},
        {"parameter": "Shared security-plane slope", "value": "1.0"},
        {"parameter": "Distributed IDS delay", "value": "1.04--1.076"},
        {"parameter": "Link base delay", "value": "$0.025\\times$ topology latency"},
        {"parameter": "Link load slope", "value": "$0.02\\times$ topology latency"},
        {"parameter": "Gateway risk/exposure", "value": "$\\rho_g=0.42$, $\\chi_g=2.4$"},
        {"parameter": "Shared-plane risk/exposure", "value": "$\\rho=0.08$, $\\chi=1.1$"},
        {"parameter": "Penalty threshold $\\tau$", "value": "0.02"},
        {"parameter": "Risk-aware surcharge weight", "value": "1.0"},
        {"parameter": "Cap grid $\\mathcal{K}$", "value": "1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.0"},
        {"parameter": "Frank--Wolfe tolerance", "value": "$10^{-5}$ relative gap"},
    ]


def max_utilization(model: MultiServiceModel, result: MCEquilibriumResult) -> float:
    return max(
        result.loads.get(name, 0.0) / resource.capacity
        for name, resource in model.resources.items()
    )


def gateway_share(model: MultiServiceModel, result: MCEquilibriumResult) -> float:
    gateway_paths = [path.name for path in model.paths if path.tag == "defensive_expansion"]
    if not gateway_paths:
        return 0.0
    return sum(result.flows.get(path, 0.0) for path in gateway_paths) / model.total_demand


def _gateway_caps(model: MultiServiceModel, fraction: float) -> dict[str, float]:
    caps: dict[str, float] = {}
    request_demands = {request.name: request.demand for request in model.requests}
    for path in model.paths:
        if path.tag == "defensive_expansion":
            caps[path.name] = request_demands[path.request] * fraction
    return caps


def _cap_fraction(model: MultiServiceModel, caps: dict[str, float]) -> float:
    fractions = []
    demands = {request.name: request.demand for request in model.requests}
    for path in model.paths:
        if path.tag == "defensive_expansion":
            fractions.append(caps.get(path.name, demands[path.request]) / demands[path.request])
    return min(fractions) if fractions else 0.0


def _minmax_utilization_caps(expanded_model: MultiServiceModel) -> dict[str, float]:
    best_caps = _gateway_caps(expanded_model, 0.0)
    best_score: tuple[float, float] | None = None
    for fraction in (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.0):
        caps = _gateway_caps(expanded_model, fraction)
        result = solve_multicommodity_equilibrium(expanded_model, caps)
        score = (max_utilization(expanded_model, result), result.average_cost)
        if best_score is None or score < best_score:
            best_score = score
            best_caps = caps
    return best_caps


def _search_gateway_caps(
    baseline: MCEquilibriumResult,
    expanded_model: MultiServiceModel,
    max_penalty: float,
) -> dict[str, float]:
    best_caps = _gateway_caps(expanded_model, 0.0)
    for fraction in (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.0):
        caps = _gateway_caps(expanded_model, fraction)
        result = solve_multicommodity_equilibrium(expanded_model, caps)
        if paradox_penalty(baseline, result) <= max_penalty:
            return caps
        best_caps = caps
    return best_caps


def _route_resources(
    topology: Topology,
    source: str,
    target: str,
    resources: dict[str, Resource],
) -> list[str]:
    path = topology.shortest_path(source, target)
    names: list[str] = []
    for u, v in zip(path, path[1:]):
        edge = topology.edge_between(u, v)
        name = edge_key(u, v)
        if name not in resources:
            resources[name] = Resource(
                name,
                base_delay=0.025 * edge.latency,
                slope=0.02 * edge.latency,
                capacity=edge.capacity,
                risk=edge.risk,
                exposure=edge.exposure,
                kind="link",
            )
        names.append(name)
    return names
