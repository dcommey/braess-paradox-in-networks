"""Small generic metrics used by the experiment suite."""

from __future__ import annotations

from typing import Protocol


class CostResult(Protocol):
    average_cost: float


def paradox_penalty(baseline: CostResult, candidate: CostResult) -> float:
    """Relative increase in average service cost."""

    return (candidate.average_cost - baseline.average_cost) / baseline.average_cost


def security_braess_ratio(
    baseline: CostResult, candidate: CostResult
) -> float:
    """Post-intervention cost divided by pre-intervention cost."""

    return candidate.average_cost / baseline.average_cost
