"""Deterministic topology generators used by the SFC experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush


@dataclass(frozen=True)
class Edge:
    u: str
    v: str
    latency: float
    capacity: float
    risk: float = 0.02
    exposure: float = 1.0


@dataclass
class Topology:
    name: str
    edges: list[Edge] = field(default_factory=list)

    def add_edge(
        self,
        u: str,
        v: str,
        *,
        latency: float,
        capacity: float,
        risk: float = 0.02,
        exposure: float = 1.0,
    ) -> None:
        self.edges.append(Edge(u, v, latency, capacity, risk, exposure))

    @property
    def nodes(self) -> tuple[str, ...]:
        values = sorted({edge.u for edge in self.edges} | {edge.v for edge in self.edges})
        return tuple(values)

    def neighbors(self, node: str) -> list[tuple[str, Edge]]:
        out = []
        for edge in self.edges:
            if edge.u == node:
                out.append((edge.v, edge))
            elif edge.v == node:
                out.append((edge.u, edge))
        return out

    def degree(self, node: str) -> int:
        return len(self.neighbors(node))

    def shortest_path(self, source: str, target: str) -> list[str]:
        queue: list[tuple[float, str, list[str]]] = [(0.0, source, [source])]
        best = {source: 0.0}
        while queue:
            distance, node, path = heappop(queue)
            if node == target:
                return path
            if distance > best.get(node, float("inf")):
                continue
            for neighbor, edge in self.neighbors(node):
                candidate = distance + edge.latency
                if candidate + 1e-12 < best.get(neighbor, float("inf")):
                    best[neighbor] = candidate
                    heappush(queue, (candidate, neighbor, path + [neighbor]))
        raise ValueError(f"no path between {source!r} and {target!r}")

    def edge_between(self, u: str, v: str) -> Edge:
        for edge in self.edges:
            if {edge.u, edge.v} == {u, v}:
                return edge
        raise KeyError(f"no edge between {u!r} and {v!r}")

    def betweenness(self) -> dict[str, float]:
        nodes = list(self.nodes)
        centrality = {node: 0.0 for node in nodes}
        for idx, source in enumerate(nodes):
            for target in nodes[idx + 1 :]:
                path = self.shortest_path(source, target)
                for node in path[1:-1]:
                    centrality[node] += 1.0
        max_value = max(centrality.values(), default=1.0)
        if max_value <= 0:
            return centrality
        return {node: value / max_value for node, value in centrality.items()}

    def peripheral_nodes(self) -> list[str]:
        centrality = self.betweenness()
        return sorted(self.nodes, key=lambda node: (self.degree(node), centrality[node], node))

    def central_nodes(self) -> list[str]:
        centrality = self.betweenness()
        return sorted(self.nodes, key=lambda node: (-centrality[node], -self.degree(node), node))


def edge_key(u: str, v: str) -> str:
    a, b = sorted((u, v))
    return f"link:{a}:{b}"


def fat_tree(k: int = 4) -> Topology:
    if k % 2 != 0 or k < 4:
        raise ValueError("fat-tree k must be an even integer >= 4")
    topo = Topology(f"fat_tree_k{k}")
    pods = range(k)
    edge_per_pod = k // 2
    agg_per_pod = k // 2
    core_count = (k // 2) ** 2
    cores = [f"core{c}" for c in range(core_count)]

    for pod in pods:
        edges = [f"p{pod}_edge{e}" for e in range(edge_per_pod)]
        aggs = [f"p{pod}_agg{a}" for a in range(agg_per_pod)]
        hosts = [f"p{pod}_h{h}" for h in range((k // 2) ** 2)]
        for edge_idx, edge_switch in enumerate(edges):
            for host in hosts[edge_idx * (k // 2) : (edge_idx + 1) * (k // 2)]:
                topo.add_edge(host, edge_switch, latency=0.12, capacity=16.0, risk=0.015)
            for agg in aggs:
                topo.add_edge(edge_switch, agg, latency=0.18, capacity=24.0, risk=0.02)
        for agg_idx, agg in enumerate(aggs):
            for offset in range(k // 2):
                core = cores[agg_idx * (k // 2) + offset]
                topo.add_edge(agg, core, latency=0.22, capacity=32.0, risk=0.025)
    return topo


def nsfnet() -> Topology:
    topo = Topology("nsfnet")
    edges = [
        (0, 1), (0, 2), (0, 3), (1, 2), (1, 7), (2, 5), (3, 4),
        (3, 9), (4, 5), (4, 6), (5, 12), (6, 7), (7, 8), (8, 10),
        (9, 10), (9, 11), (10, 12), (11, 13), (12, 13),
    ]
    for idx, (u, v) in enumerate(edges):
        topo.add_edge(f"n{u}", f"n{v}", latency=0.35 + 0.03 * (idx % 5), capacity=12.0, risk=0.03)
    return topo


def geant() -> Topology:
    topo = Topology("geant")
    edges = [
        (0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6), (3, 4),
        (3, 7), (4, 8), (5, 6), (5, 9), (6, 10), (7, 8), (7, 11),
        (8, 12), (9, 10), (9, 13), (10, 14), (11, 12), (11, 15),
        (12, 16), (13, 14), (13, 17), (14, 18), (15, 16), (15, 19),
        (16, 20), (17, 18), (18, 21), (19, 20), (20, 21), (4, 12),
        (6, 14), (8, 16), (10, 18),
    ]
    for idx, (u, v) in enumerate(edges):
        topo.add_edge(f"g{u}", f"g{v}", latency=0.28 + 0.025 * (idx % 7), capacity=14.0, risk=0.028)
    return topo


def edge_fog(regions: int = 6) -> Topology:
    topo = Topology("edge_fog")
    for region in range(regions):
        user = f"r{region}_user"
        edge = f"r{region}_edge"
        fog = f"r{region}_fog"
        regional = f"r{region}_regional"
        topo.add_edge(user, edge, latency=0.08, capacity=9.0, risk=0.025, exposure=1.2)
        topo.add_edge(edge, fog, latency=0.10, capacity=10.0, risk=0.03, exposure=1.3)
        topo.add_edge(fog, regional, latency=0.16, capacity=12.0, risk=0.035, exposure=1.4)
        topo.add_edge(regional, "cloud_core", latency=0.25, capacity=18.0, risk=0.04, exposure=1.6)
        nxt = f"r{(region + 1) % regions}_regional"
        topo.add_edge(regional, nxt, latency=0.22, capacity=12.0, risk=0.035, exposure=1.3)
    return topo


def all_topologies() -> tuple[Topology, ...]:
    return (fat_tree(4), nsfnet(), geant(), edge_fog())

