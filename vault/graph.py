"""Typed evidence dependency graph (stored as Delta node/edge tables; no graph database).

Edge direction: `from_node` DEPENDS ON `to_node`. Upstream = what a node rests on;
downstream = what would be affected if a node changed.

Edge types and meaning:
  DERIVED_FROM        factual derivation (data -> result). Must be acyclic.
  ASSUMES             a result uses a planning assumption (hypothetical input)
  SUPPORTS            argument support (a claim backs a decision); not derivation
  CONTRADICTS         a claim argues against another claim
  CHALLENGES          a council claim disputes an assumption / investment
  VERIFIED_BY         a claim's verification record
  INVALIDATED_BY      a claim retracted / invalidated by another record
  USED_IN_SCENARIO    a scenario varies an assumption
  USED_BY_OPTIMIZER   an optimiser run / portfolio used a candidate
  AFFECTS_DECISION    a reversal / model result bears on a portfolio
  DISPLAYED_BY_METRIC a serving metric displays a record
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

EDGE_TYPES = {"DERIVED_FROM", "ASSUMES", "SUPPORTS", "CONTRADICTS", "CHALLENGES",
              "VERIFIED_BY", "INVALIDATED_BY", "USED_IN_SCENARIO", "USED_BY_OPTIMIZER",
              "AFFECTS_DECISION", "DISPLAYED_BY_METRIC"}
DERIVATION = {"DERIVED_FROM", "ASSUMES", "USED_IN_SCENARIO", "USED_BY_OPTIMIZER"}
# edges through which an invalidation propagates as "directly affected"
DIRECT = {"DERIVED_FROM", "ASSUMES", "USED_IN_SCENARIO", "USED_BY_OPTIMIZER"}
# edges through which it propagates only as "possibly affected" (argument / decision level)
INDIRECT = {"SUPPORTS", "AFFECTS_DECISION", "CHALLENGES", "DISPLAYED_BY_METRIC"}


@dataclass
class Node:
    node_id: str
    node_type: str
    label: str
    owner_step: str
    source_ref: str
    version: str


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[tuple[str, str, str]] = field(default_factory=set)  # (from, to, type)

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.node_id, node)

    def add_edge(self, frm: str, to: str, etype: str) -> None:
        if etype not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {etype}")
        if frm == to:
            raise ValueError("self edge")
        self.edges.add((frm, to, etype))

    def dangling(self) -> list[tuple[str, str, str]]:
        return sorted(e for e in self.edges if e[0] not in self.nodes or e[1] not in self.nodes)

    def derivation_cycles(self) -> list[list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        for f, t, k in self.edges:
            if k in DERIVATION:
                adj[f].append(t)
        color: dict[str, int] = {}
        cycles: list[list[str]] = []

        def dfs(u: str, path: list[str]) -> None:
            color[u] = 1
            path.append(u)
            for v in sorted(adj[u]):
                if color.get(v) == 1:
                    cycles.append(path[path.index(v):] + [v])
                elif color.get(v) is None:
                    dfs(v, path)
            path.pop()
            color[u] = 2

        for n in sorted(adj):
            if color.get(n) is None:
                dfs(n, [])
        return cycles

    def upstream(self, node: str) -> set[str]:
        adj: dict[str, list[str]] = defaultdict(list)
        for f, t, _ in self.edges:
            adj[f].append(t)
        return _bfs(node, adj)

    def downstream(self, node: str, kinds: set[str] | None = None) -> set[str]:
        rev: dict[str, list[str]] = defaultdict(list)
        for f, t, k in self.edges:
            if kinds is None or k in kinds:
                rev[t].append(f)
        return _bfs(node, rev)

    def impact(self, node: str) -> dict[str, set[str]]:
        """Directly affected = reachable through derivation/assumption edges.
        Possibly affected = additionally reachable through argument/decision edges."""
        direct = self.downstream(node, DIRECT)
        everything = set()
        frontier = {node} | direct
        rev: dict[str, list[str]] = defaultdict(list)
        for f, t, k in self.edges:
            if k in DIRECT | INDIRECT:
                rev[t].append(f)
        for n in frontier:
            everything |= _bfs(n, rev)
        return {"direct": direct, "possible": everything - direct - {node}}


def _bfs(start: str, adj: dict[str, list[str]]) -> set[str]:
    seen, q = set(), deque([start])
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if v not in seen:
                seen.add(v)
                q.append(v)
    seen.discard(start)
    return seen
