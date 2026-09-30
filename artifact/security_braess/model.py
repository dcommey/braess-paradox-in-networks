"""Shared resource primitives for SFC/NFV experiments."""

from __future__ import annotations

from dataclasses import dataclass


EPSILON = 1e-12


@dataclass(frozen=True)
class Resource:
    """A link, VNF, gateway, or security plane with affine delay."""

    name: str
    base_delay: float
    slope: float = 0.0
    capacity: float = 1.0
    risk: float = 0.0
    exposure: float = 1.0
    kind: str = "link"

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError(f"resource {self.name!r} must have positive capacity")
        if self.base_delay < 0 or self.slope < 0:
            raise ValueError(f"resource {self.name!r} delays must be non-negative")
        if self.risk < 0 or self.exposure < 0:
            raise ValueError(f"resource {self.name!r} risk/exposure must be non-negative")

    def delay(self, load: float) -> float:
        return self.base_delay + self.slope * load / self.capacity

    def potential(self, load: float) -> float:
        return self.base_delay * load + 0.5 * self.slope * load * load / self.capacity
