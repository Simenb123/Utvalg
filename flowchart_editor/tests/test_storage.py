"""Tester for storage.py — JSON lagre/laste."""

from __future__ import annotations

from pathlib import Path

from flowchart_editor.model import Diagram, Edge, Node, Subgraph
from flowchart_editor.storage import load_diagram, save_diagram


def _sample_diagram() -> Diagram:
    d = Diagram(direction="TB")
    d.add_subgraph(Subgraph(id="P1", label="Planlegging"))
    d.add_node(Node(id="A", label="Start", x=50, y=50, subgraph_id="P1"))
    d.add_node(Node(id="B", label="Neste", shape="round", x=50, y=200))
    d.add_edge(Edge(from_id="A", to_id="B", label="gå", arrow="==>"))
    return d


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    d = _sample_diagram()
    path = tmp_path / "test.fcjson"
    save_diagram(d, path)
    assert path.exists()
    d2 = load_diagram(path)
    assert d2.to_dict() == d.to_dict()


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    d = Diagram()
    d.add_node(Node(id="A"))
    path = tmp_path / "nested" / "deeper" / "test.fcjson"
    save_diagram(d, path)
    assert path.exists()


def test_file_is_utf8_with_norwegian_chars(tmp_path: Path) -> None:
    d = Diagram()
    d.add_node(Node(id="A", label="Vurdér æøå — Nærstående"))
    path = tmp_path / "test.fcjson"
    save_diagram(d, path)
    text = path.read_text(encoding="utf-8")
    assert "æøå" in text
    assert "Nærstående" in text
