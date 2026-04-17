"""Tester for model.py — Diagram, Node, Edge, Subgraph."""

from __future__ import annotations

import pytest

from flowchart_editor.model import Diagram, Edge, Node, Subgraph


def test_node_roundtrip() -> None:
    n = Node(id="A", label="Test", shape="round", x=10, y=20, fill="#FFEECC")
    data = n.to_dict()
    n2 = Node.from_dict(data)
    assert n2 == n


def test_edge_roundtrip() -> None:
    e = Edge(from_id="A", to_id="B", label="label", arrow="-.->")
    assert Edge.from_dict(e.to_dict()) == e


def test_subgraph_roundtrip() -> None:
    s = Subgraph(id="P1", label="Fase 1", direction="LR", fill="#E6F1FB")
    assert Subgraph.from_dict(s.to_dict()) == s


def test_diagram_add_node_duplicate_raises() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    with pytest.raises(ValueError):
        d.add_node(Node(id="A"))


def test_diagram_add_edge_unknown_node_raises() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    with pytest.raises(ValueError):
        d.add_edge(Edge(from_id="A", to_id="X"))


def test_diagram_remove_node_removes_related_edges() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    d.add_node(Node(id="B"))
    d.add_node(Node(id="C"))
    d.add_edge(Edge(from_id="A", to_id="B"))
    d.add_edge(Edge(from_id="B", to_id="C"))
    d.add_edge(Edge(from_id="A", to_id="C"))
    d.remove_node("B")
    assert "B" not in d.nodes
    assert len(d.edges) == 1
    assert d.edges[0] == Edge(from_id="A", to_id="C")


def test_diagram_rename_node_updates_edges() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    d.add_node(Node(id="B"))
    d.add_edge(Edge(from_id="A", to_id="B"))
    d.rename_node("A", "START")
    assert "A" not in d.nodes
    assert "START" in d.nodes
    assert d.edges[0].from_id == "START"


def test_diagram_rename_node_collision_raises() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    d.add_node(Node(id="B"))
    with pytest.raises(ValueError):
        d.rename_node("A", "B")


def test_diagram_remove_subgraph_clears_membership() -> None:
    d = Diagram()
    d.add_subgraph(Subgraph(id="S1"))
    d.add_node(Node(id="A", subgraph_id="S1"))
    d.add_node(Node(id="B", subgraph_id="S1"))
    d.remove_subgraph("S1")
    assert "S1" not in d.subgraphs
    assert d.nodes["A"].subgraph_id is None
    assert d.nodes["B"].subgraph_id is None


def test_diagram_remove_subgraph_with_members() -> None:
    d = Diagram()
    d.add_subgraph(Subgraph(id="S1"))
    d.add_node(Node(id="A", subgraph_id="S1"))
    d.add_node(Node(id="B", subgraph_id="S1"))
    d.add_node(Node(id="C"))
    d.remove_subgraph("S1", remove_members=True)
    assert "A" not in d.nodes
    assert "B" not in d.nodes
    assert "C" in d.nodes


def test_diagram_full_roundtrip() -> None:
    d = Diagram(direction="LR")
    d.add_subgraph(Subgraph(id="P1", label="Planlegging"))
    d.add_node(Node(id="A", label="Start", subgraph_id="P1", x=10, y=20))
    d.add_node(Node(id="B", label="Slutt", shape="rhombus"))
    d.add_edge(Edge(from_id="A", to_id="B", label="neste"))

    d2 = Diagram.from_dict(d.to_dict())
    assert d2.direction == "LR"
    assert d2.nodes["A"].label == "Start"
    assert d2.nodes["A"].subgraph_id == "P1"
    assert d2.nodes["B"].shape == "rhombus"
    assert d2.edges[0].label == "neste"
    assert d2.subgraphs["P1"].label == "Planlegging"
