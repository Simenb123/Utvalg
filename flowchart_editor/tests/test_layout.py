"""Tester for layout.py."""

from __future__ import annotations

from flowchart_editor.layout import auto_layout, fit_node_height
from flowchart_editor.model import Diagram, Edge, Node, Subgraph


def test_fit_node_height_single_line() -> None:
    node = Node(id="A", label="Enkel")
    fit_node_height(node)
    assert node.height == 60.0


def test_fit_node_height_multi_line_grows() -> None:
    node = Node(id="A", label="Linje 1\nLinje 2\nLinje 3\nLinje 4")
    fit_node_height(node)
    assert node.height > 60.0


def test_fit_node_height_empty_label_uses_min() -> None:
    node = Node(id="A", label="")
    fit_node_height(node)
    assert node.height == 60.0


def test_grid_layout_14_nodes_unique_positions() -> None:
    diagram = Diagram()
    diagram.add_subgraph(Subgraph(id="P1", label="Fase 1"))
    for i in range(14):
        diagram.add_node(Node(id=f"N{i}", label=f"Node {i}", subgraph_id="P1"))
    # Kjede dem
    for i in range(13):
        diagram.add_edge(Edge(from_id=f"N{i}", to_id=f"N{i+1}"))

    auto_layout(diagram)

    positions = {(n.x, n.y) for n in diagram.nodes.values()}
    assert len(positions) == 14, "Alle noder må ha unike posisjoner"


def test_subgraphs_laid_out_side_by_side() -> None:
    diagram = Diagram()
    diagram.add_subgraph(Subgraph(id="A"))
    diagram.add_subgraph(Subgraph(id="B"))
    for i in range(4):
        diagram.add_node(Node(id=f"a{i}", subgraph_id="A"))
        diagram.add_node(Node(id=f"b{i}", subgraph_id="B"))

    auto_layout(diagram)

    a_members = [n for n in diagram.nodes.values() if n.subgraph_id == "A"]
    b_members = [n for n in diagram.nodes.values() if n.subgraph_id == "B"]
    a_right = max(n.x + n.width / 2 for n in a_members)
    b_left = min(n.x - n.width / 2 for n in b_members)
    assert b_left > a_right, "Subgraph B skal ligge til høyre for subgraph A"


def test_auto_layout_empty_diagram_noop() -> None:
    diagram = Diagram()
    auto_layout(diagram)  # skal ikke kræsje
    assert diagram.nodes == {}


def test_auto_layout_updates_node_heights() -> None:
    diagram = Diagram()
    diagram.add_node(Node(id="A", label="L1\nL2\nL3\nL4"))
    auto_layout(diagram)
    assert diagram.nodes["A"].height > 60.0
