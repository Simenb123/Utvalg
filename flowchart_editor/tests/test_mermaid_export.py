"""Tester for mermaid_export.py."""

from __future__ import annotations

from flowchart_editor.mermaid_export import export_mermaid
from flowchart_editor.model import Diagram, Edge, Node, Subgraph


def test_export_empty_diagram() -> None:
    out = export_mermaid(Diagram(direction="TB"))
    assert out.strip() == "flowchart TB"


def test_export_nodes_with_shapes() -> None:
    d = Diagram()
    d.add_node(Node(id="A", label="Rekt"))
    d.add_node(Node(id="B", label="Rund", shape="round"))
    d.add_node(Node(id="C", label="Rombe", shape="rhombus"))
    d.add_node(Node(id="D", label="Subrutine", shape="subroutine"))
    out = export_mermaid(d)
    assert 'A["Rekt"]' in out
    assert 'B("Rund")' in out
    assert 'C{"Rombe"}' in out
    assert 'D[["Subrutine"]]' in out


def test_export_edges_with_arrow_styles() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    d.add_node(Node(id="B"))
    d.add_edge(Edge(from_id="A", to_id="B"))
    d.add_edge(Edge(from_id="A", to_id="B", arrow="---"))
    d.add_edge(Edge(from_id="A", to_id="B", arrow="-.->"))
    d.add_edge(Edge(from_id="A", to_id="B", arrow="==>"))
    out = export_mermaid(d)
    assert "A --> B" in out
    assert "A --- B" in out
    assert "A -.-> B" in out
    assert "A ==> B" in out


def test_export_edge_with_label() -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    d.add_node(Node(id="B"))
    d.add_edge(Edge(from_id="A", to_id="B", label="gå"))
    out = export_mermaid(d)
    assert "A --gå--> B" in out


def test_export_subgraph_with_members() -> None:
    d = Diagram()
    d.add_subgraph(Subgraph(id="P1", label="Planlegging"))
    d.add_node(Node(id="A", label="Start", subgraph_id="P1"))
    d.add_node(Node(id="B", label="Fri"))
    out = export_mermaid(d)
    assert 'subgraph P1 ["Planlegging"]' in out
    assert "end" in out
    # A skal være inne i subgraphen, B utenfor
    sub_idx = out.index("subgraph P1")
    end_idx = out.index("end", sub_idx)
    assert 'A["Start"]' in out[sub_idx:end_idx]
    assert 'B["Fri"]' in out[end_idx:]


def test_export_style_line_for_custom_fill() -> None:
    d = Diagram()
    d.add_node(Node(id="A", fill="#E6F1FB", stroke="#378ADD"))
    d.add_node(Node(id="B"))  # default-farger
    out = export_mermaid(d)
    assert "style A fill:#E6F1FB,stroke:#378ADD" in out
    assert "style B" not in out


def test_export_subgraph_direction_emitted_when_different() -> None:
    d = Diagram(direction="TB")
    d.add_subgraph(Subgraph(id="P1", label="P", direction="LR"))
    d.add_node(Node(id="A", subgraph_id="P1"))
    out = export_mermaid(d)
    assert "direction LR" in out


def test_export_norwegian_chars_preserved() -> None:
    d = Diagram()
    d.add_node(Node(id="A", label="Nærstående æøå"))
    out = export_mermaid(d)
    assert "Nærstående æøå" in out


def test_export_multiline_label_uses_br() -> None:
    d = Diagram()
    d.add_node(Node(id="A", label="Linje 1\nLinje 2"))
    out = export_mermaid(d)
    assert "Linje 1<br/>Linje 2" in out
