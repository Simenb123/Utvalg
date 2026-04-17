"""model.py — Dataclasses for Diagram, Node, Edge, Subgraph.

Diagram er single source of truth. Canvas rendrer det, sidepanel redigerer det,
parsers/storage leser/skriver det.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional


Shape = Literal["rect", "round", "rhombus", "subroutine"]
Direction = Literal["TB", "LR", "BT", "RL"]
Arrow = Literal["-->", "---", "-.->", "==>"]


@dataclass
class Node:
    id: str
    label: str = ""
    shape: Shape = "rect"
    x: float = 0.0
    y: float = 0.0
    width: float = 160.0
    height: float = 60.0
    fill: str = "#FFFFFF"
    stroke: str = "#D0D5DD"
    text_color: str = "#101828"
    subgraph_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        return cls(
            id=str(data["id"]),
            label=str(data.get("label", "")),
            shape=data.get("shape", "rect"),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            width=float(data.get("width", 160.0)),
            height=float(data.get("height", 60.0)),
            fill=str(data.get("fill", "#FFFFFF")),
            stroke=str(data.get("stroke", "#D0D5DD")),
            text_color=str(data.get("text_color", "#101828")),
            subgraph_id=data.get("subgraph_id"),
        )


@dataclass
class Edge:
    from_id: str
    to_id: str
    label: str = ""
    arrow: Arrow = "-->"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        return cls(
            from_id=str(data["from_id"]),
            to_id=str(data["to_id"]),
            label=str(data.get("label", "")),
            arrow=data.get("arrow", "-->"),
        )


@dataclass
class Subgraph:
    id: str
    label: str = ""
    direction: Direction = "TB"
    fill: str = "#F9FAFB"
    stroke: str = "#98A2B3"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Subgraph":
        return cls(
            id=str(data["id"]),
            label=str(data.get("label", "")),
            direction=data.get("direction", "TB"),
            fill=str(data.get("fill", "#F9FAFB")),
            stroke=str(data.get("stroke", "#98A2B3")),
        )


@dataclass
class Diagram:
    direction: Direction = "TB"
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: dict[str, Subgraph] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Node-ID {node.id!r} finnes allerede")
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.edges = [e for e in self.edges if e.from_id != node_id and e.to_id != node_id]

    def add_edge(self, edge: Edge) -> None:
        if edge.from_id not in self.nodes:
            raise ValueError(f"Ukjent from_id: {edge.from_id!r}")
        if edge.to_id not in self.nodes:
            raise ValueError(f"Ukjent to_id: {edge.to_id!r}")
        self.edges.append(edge)

    def remove_edge(self, edge: Edge) -> None:
        try:
            self.edges.remove(edge)
        except ValueError:
            pass

    def add_subgraph(self, subgraph: Subgraph) -> None:
        if subgraph.id in self.subgraphs:
            raise ValueError(f"Subgraph-ID {subgraph.id!r} finnes allerede")
        self.subgraphs[subgraph.id] = subgraph

    def remove_subgraph(self, subgraph_id: str, *, remove_members: bool = False) -> None:
        self.subgraphs.pop(subgraph_id, None)
        if remove_members:
            member_ids = [nid for nid, n in self.nodes.items() if n.subgraph_id == subgraph_id]
            for nid in member_ids:
                self.remove_node(nid)
        else:
            for node in self.nodes.values():
                if node.subgraph_id == subgraph_id:
                    node.subgraph_id = None

    def rename_node(self, old_id: str, new_id: str) -> None:
        if old_id == new_id:
            return
        if new_id in self.nodes:
            raise ValueError(f"Node-ID {new_id!r} finnes allerede")
        node = self.nodes.pop(old_id)
        node.id = new_id
        self.nodes[new_id] = node
        for edge in self.edges:
            if edge.from_id == old_id:
                edge.from_id = new_id
            if edge.to_id == old_id:
                edge.to_id = new_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "direction": self.direction,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "subgraphs": {sid: s.to_dict() for sid, s in self.subgraphs.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Diagram":
        diag = cls(direction=data.get("direction", "TB"))
        for nid, ndata in (data.get("nodes") or {}).items():
            diag.nodes[str(nid)] = Node.from_dict(ndata)
        for edata in data.get("edges") or []:
            diag.edges.append(Edge.from_dict(edata))
        for sid, sdata in (data.get("subgraphs") or {}).items():
            diag.subgraphs[str(sid)] = Subgraph.from_dict(sdata)
        return diag
