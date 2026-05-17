"""Multi-tenant SFC equilibrium model for topology-derived experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf, isfinite
from typing import Mapping

from .model import EPSILON, Resource


@dataclass(frozen=True)
class Request:
    """A tenant or service class with fixed demand."""

    name: str
    demand: float
    source: str
    destination: str

    def __post_init__(self) -> None:
        if self.demand <= 0:
            raise ValueError("request demand must be positive")


@dataclass(frozen=True)
class MCPath:
    """A feasible service-chain route for a specific request."""

    name: str
    request: str
    resources: tuple[str, ...]
    tag: str = "baseline"

    def __post_init__(self) -> None:
        if not self.resources:
            raise ValueError(f"path {self.name!r} must contain at least one resource")


@dataclass(frozen=True)
class MultiServiceModel:
    """Multi-request SFC model with shared resources."""

    name: str
    resources: Mapping[str, Resource]
    requests: tuple[Request, ...]
    paths: tuple[MCPath, ...]
    metadata: Mapping[str, str | int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        request_names = {request.name for request in self.requests}
        if len(request_names) != len(self.requests):
            raise ValueError("request names must be unique")
        path_names = [path.name for path in self.paths]
        if len(path_names) != len(set(path_names)):
            raise ValueError("path names must be unique")
        for path in self.paths:
            if path.request not in request_names:
                raise ValueError(f"path {path.name!r} references unknown request")
            for resource in path.resources:
                if resource not in self.resources:
                    raise ValueError(f"path {path.name!r} references unknown resource {resource!r}")
        for request in self.requests:
            if not any(path.request == request.name for path in self.paths):
                raise ValueError(f"request {request.name!r} has no feasible paths")

    @property
    def path_names(self) -> tuple[str, ...]:
        return tuple(path.name for path in self.paths)

    @property
    def total_demand(self) -> float:
        return sum(request.demand for request in self.requests)

    def paths_for_request(self, request_name: str) -> tuple[MCPath, ...]:
        return tuple(path for path in self.paths if path.request == request_name)

    def resource_loads(self, flows: Mapping[str, float]) -> dict[str, float]:
        loads = {name: 0.0 for name in self.resources}
        for path in self.paths:
            flow = flows.get(path.name, 0.0)
            for resource_name in path.resources:
                loads[resource_name] += flow
        return loads

    def path_costs(self, flows: Mapping[str, float]) -> dict[str, float]:
        loads = self.resource_loads(flows)
        return {
            path.name: sum(
                self.resources[resource_name].delay(loads[resource_name])
                for resource_name in path.resources
            )
            for path in self.paths
        }

    def potential(self, flows: Mapping[str, float]) -> float:
        loads = self.resource_loads(flows)
        return sum(
            resource.potential(loads[name])
            for name, resource in self.resources.items()
        )


@dataclass(frozen=True)
class MCEquilibriumResult:
    model_name: str
    flows: dict[str, float]
    loads: dict[str, float]
    path_costs: dict[str, float]
    request_average_costs: dict[str, float]
    total_cost: float
    average_cost: float
    potential: float
    iterations: int
    converged: bool
    gap: float


def solve_multicommodity_equilibrium(
    model: MultiServiceModel,
    path_caps: Mapping[str, float] | None = None,
    *,
    max_iter: int = 5_000,
    tolerance: float = 1e-5,
) -> MCEquilibriumResult:
    caps = _normalize_caps(model, path_caps)
    flows = _all_or_nothing(model, None, caps)
    converged = False
    gap = inf

    for iteration in range(1, max_iter + 1):
        costs = model.path_costs(flows)
        search = _all_or_nothing(model, costs, caps)
        direction = {name: search[name] - flows[name] for name in model.path_names}
        gap = sum((flows[name] - search[name]) * costs[name] for name in model.path_names)
        scale = max(1.0, sum(flows[name] * costs[name] for name in model.path_names))
        if gap <= tolerance * scale:
            converged = True
            break
        step = _affine_line_search(model, flows, direction)
        if step <= EPSILON:
            converged = True
            break
        flows = {
            name: _clean_float(flows[name] + step * direction[name])
            for name in model.path_names
        }
    else:
        iteration = max_iter

    return _make_result(model, flows, iterations=iteration, converged=converged, gap=gap)


def solve_system_optimum(
    model: MultiServiceModel,
    path_caps: Mapping[str, float] | None = None,
    *,
    max_iter: int = 5_000,
    tolerance: float = 1e-5,
) -> MCEquilibriumResult:
    """Compute the system-optimum flow for affine resource delay.

    For affine delay ``b + a y/u``, minimizing total delay
    ``sum_e y_e * l_e(y_e)`` has marginal delay ``b + 2 a y/u``. Therefore
    the system optimum is the Wardrop equilibrium of an auxiliary model whose
    slopes are doubled, evaluated back on the original model.
    """

    doubled_resources = {
        name: Resource(
            name=resource.name,
            base_delay=resource.base_delay,
            slope=2.0 * resource.slope,
            capacity=resource.capacity,
            risk=resource.risk,
            exposure=resource.exposure,
            kind=resource.kind,
        )
        for name, resource in model.resources.items()
    }
    auxiliary = MultiServiceModel(
        name=f"{model.name}_system_optimum_aux",
        resources=doubled_resources,
        requests=model.requests,
        paths=model.paths,
        metadata=model.metadata,
    )
    aux_result = solve_multicommodity_equilibrium(
        auxiliary,
        path_caps=path_caps,
        max_iter=max_iter,
        tolerance=tolerance,
    )
    return _make_result(
        model,
        aux_result.flows,
        iterations=aux_result.iterations,
        converged=aux_result.converged,
        gap=aux_result.gap,
    )


def solve_weighted_equilibrium(
    model: MultiServiceModel,
    *,
    risk_weight: float = 0.0,
    exposure_weight: float = 0.0,
    path_caps: Mapping[str, float] | None = None,
    max_iter: int = 5_000,
    tolerance: float = 1e-5,
) -> MCEquilibriumResult:
    """Solve an auxiliary equilibrium with static risk/exposure surcharges.

    This models a common security-aware orchestrator that treats risk and
    exposure as additive path scores, then evaluates the selected flow under
    the original service-delay and attack-loss model.
    """

    scored_resources = {
        name: Resource(
            name=resource.name,
            base_delay=(
                resource.base_delay
                + risk_weight * resource.risk * resource.exposure
                + exposure_weight * resource.exposure
            ),
            slope=resource.slope,
            capacity=resource.capacity,
            risk=resource.risk,
            exposure=resource.exposure,
            kind=resource.kind,
        )
        for name, resource in model.resources.items()
    }
    auxiliary = MultiServiceModel(
        name=f"{model.name}_weighted_aux",
        resources=scored_resources,
        requests=model.requests,
        paths=model.paths,
        metadata=model.metadata,
    )
    aux_result = solve_multicommodity_equilibrium(
        auxiliary,
        path_caps=path_caps,
        max_iter=max_iter,
        tolerance=tolerance,
    )
    return _make_result(
        model,
        aux_result.flows,
        iterations=aux_result.iterations,
        converged=aux_result.converged,
        gap=aux_result.gap,
    )


def _normalize_caps(
    model: MultiServiceModel, path_caps: Mapping[str, float] | None
) -> dict[str, float]:
    caps = {path.name: model.total_demand for path in model.paths}
    if path_caps:
        unknown = set(path_caps) - set(caps)
        if unknown:
            raise ValueError(f"unknown capped paths: {sorted(unknown)}")
        for name, cap in path_caps.items():
            if cap < 0:
                raise ValueError(f"path cap for {name!r} must be non-negative")
            caps[name] = cap

    for request in model.requests:
        request_capacity = sum(caps[path.name] for path in model.paths_for_request(request.name))
        if request_capacity + 1e-9 < request.demand:
            raise ValueError(f"path caps do not leave enough capacity for {request.name}")
    return caps


def _all_or_nothing(
    model: MultiServiceModel,
    costs: Mapping[str, float] | None,
    caps: Mapping[str, float],
) -> dict[str, float]:
    flows = {name: 0.0 for name in model.path_names}
    if costs is None:
        costs = _free_flow_costs(model)
    for request in model.requests:
        remaining = request.demand
        request_paths = sorted(
            model.paths_for_request(request.name),
            key=lambda path: (costs[path.name], path.name),
        )
        for path in request_paths:
            if remaining <= EPSILON:
                break
            amount = min(caps[path.name], remaining)
            flows[path.name] = amount
            remaining -= amount
        if remaining > 1e-9:
            raise ValueError(f"could not allocate demand for {request.name}")
    return flows


def _free_flow_costs(model: MultiServiceModel) -> dict[str, float]:
    zero = {name: 0.0 for name in model.path_names}
    return model.path_costs(zero)


def _affine_line_search(
    model: MultiServiceModel,
    flows: Mapping[str, float],
    direction: Mapping[str, float],
) -> float:
    loads = model.resource_loads(flows)
    load_direction = {name: 0.0 for name in model.resources}
    for path in model.paths:
        delta = direction[path.name]
        for resource_name in path.resources:
            load_direction[resource_name] += delta

    numerator = 0.0
    denominator = 0.0
    for name, resource in model.resources.items():
        d_load = load_direction[name]
        if abs(d_load) <= EPSILON:
            continue
        numerator += resource.delay(loads[name]) * d_load
        denominator += (resource.slope / resource.capacity) * d_load * d_load

    if denominator <= EPSILON:
        return 1.0 if numerator < 0 else 0.0
    return min(1.0, max(0.0, -numerator / denominator))


def _make_result(
    model: MultiServiceModel,
    flows: Mapping[str, float],
    *,
    iterations: int,
    converged: bool,
    gap: float,
) -> MCEquilibriumResult:
    loads = model.resource_loads(flows)
    path_costs = model.path_costs(flows)
    total_cost = sum(flows[name] * path_costs[name] for name in model.path_names)
    request_average_costs: dict[str, float] = {}
    for request in model.requests:
        request_cost = sum(
            flows[path.name] * path_costs[path.name]
            for path in model.paths_for_request(request.name)
        )
        request_average_costs[request.name] = request_cost / request.demand
    return MCEquilibriumResult(
        model_name=model.name,
        flows={name: _clean_float(value) for name, value in flows.items()},
        loads={name: _clean_float(value) for name, value in loads.items()},
        path_costs={name: _clean_float(value) for name, value in path_costs.items()},
        request_average_costs={
            name: _clean_float(value) for name, value in request_average_costs.items()
        },
        total_cost=_clean_float(total_cost),
        average_cost=_clean_float(total_cost / model.total_demand),
        potential=_clean_float(model.potential(flows)),
        iterations=iterations,
        converged=converged,
        gap=_clean_float(gap),
    )


def _clean_float(value: float) -> float:
    if not isfinite(value):
        return value
    if abs(value) < 1e-10:
        return 0.0
    return float(value)
