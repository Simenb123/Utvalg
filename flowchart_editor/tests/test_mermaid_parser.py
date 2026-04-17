"""Tester for mermaid_parser.py."""

from __future__ import annotations

from pathlib import Path

from flowchart_editor.mermaid_parser import parse_mermaid


def test_parse_flowchart_direction() -> None:
    r = parse_mermaid("flowchart LR")
    assert r.diagram.direction == "LR"


def test_parse_td_is_normalized_to_tb() -> None:
    r = parse_mermaid("flowchart TD\nA --> B\n")
    assert r.diagram.direction == "TB"


def test_parse_simple_nodes_and_edge() -> None:
    text = """
    flowchart TB
        A[Start]
        B[Slutt]
        A --> B
    """
    r = parse_mermaid(text)
    assert "A" in r.diagram.nodes
    assert "B" in r.diagram.nodes
    assert r.diagram.nodes["A"].label == "Start"
    assert len(r.diagram.edges) == 1
    assert r.diagram.edges[0].from_id == "A"
    assert r.diagram.edges[0].to_id == "B"


def test_parse_node_shapes() -> None:
    text = """
    flowchart TB
        A[Rekt]
        B(Rund)
        C{Rombe}
        D[[Subrutine]]
    """
    r = parse_mermaid(text)
    assert r.diagram.nodes["A"].shape == "rect"
    assert r.diagram.nodes["B"].shape == "round"
    assert r.diagram.nodes["C"].shape == "rhombus"
    assert r.diagram.nodes["D"].shape == "subroutine"


def test_parse_chained_edges() -> None:
    r = parse_mermaid("flowchart TB\nA --> B --> C\n")
    assert {n for n in r.diagram.nodes} == {"A", "B", "C"}
    assert len(r.diagram.edges) == 2


def test_parse_edge_arrow_styles() -> None:
    text = """
    flowchart TB
        A --> B
        A --- B
        A -.-> B
        A ==> B
    """
    r = parse_mermaid(text)
    arrows = sorted(e.arrow for e in r.diagram.edges)
    assert arrows == sorted(["-->", "---", "-.->", "==>"])


def test_parse_edge_with_label() -> None:
    r = parse_mermaid("flowchart TB\nA --gå--> B\n")
    assert r.diagram.edges[0].label == "gå"


def test_parse_edge_with_spaced_label() -> None:
    r = parse_mermaid("flowchart TB\nA -- til neste -- > B\n")
    # "-- til neste -- >" er ikke standard; bruker standard-varianten
    r = parse_mermaid("flowchart TB\nA -- til neste --> B\n")
    assert r.diagram.edges[0].label == "til neste"


def test_parse_edge_pipe_label() -> None:
    r = parse_mermaid("flowchart TB\nA -->|valg| B\n")
    assert r.diagram.edges[0].label == "valg"


def test_parse_subgraph_with_members() -> None:
    text = """
    flowchart TB
        subgraph P1["Planlegging"]
            direction TB
            A[Start]
            B[Neste]
            A --> B
        end
    """
    r = parse_mermaid(text)
    assert "P1" in r.diagram.subgraphs
    assert r.diagram.subgraphs["P1"].label == "Planlegging"
    assert r.diagram.subgraphs["P1"].direction == "TB"
    assert r.diagram.nodes["A"].subgraph_id == "P1"
    assert r.diagram.nodes["B"].subgraph_id == "P1"


def test_parse_style_line() -> None:
    text = """
    flowchart TB
        A[x]
        style A fill:#E6F1FB,stroke:#378ADD,color:#101010
    """
    r = parse_mermaid(text)
    assert r.diagram.nodes["A"].fill == "#E6F1FB"
    assert r.diagram.nodes["A"].stroke == "#378ADD"
    assert r.diagram.nodes["A"].text_color == "#101010"


def test_parse_br_becomes_newline_in_label() -> None:
    r = parse_mermaid("flowchart TB\nA[Linje 1<br/>Linje 2]\n")
    assert r.diagram.nodes["A"].label == "Linje 1\nLinje 2"


def test_parse_comments_and_blank_lines_ignored() -> None:
    text = """
    %% dette er en kommentar
    flowchart TB

    %% en til
    A --> B
    """
    r = parse_mermaid(text)
    assert len(r.diagram.edges) == 1
    assert not any("kommentar" in w for w in r.warnings)


def test_parse_unknown_line_produces_warning() -> None:
    r = parse_mermaid("flowchart TB\nbogus linje 123\n")
    assert any("bogus" in w for w in r.warnings)


def test_parse_revisjonsprosess_full_file() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "doc" / "files" / "Revisjonsprosess_Mermaid_for_Miro.md"
    )
    if not path.exists():
        return  # Hopp over hvis doc-filen ikke er med
    content = path.read_text(encoding="utf-8")
    # Trekk ut første ```mermaid-blokk
    start = content.find("```mermaid")
    assert start >= 0, "Fant ikke mermaid-blokk i doc-filen"
    body_start = content.find("\n", start) + 1
    end = content.find("```", body_start)
    mermaid_text = content[body_start:end]
    r = parse_mermaid(mermaid_text)
    # Forvent minst 4 subgraphs (P1-P4) og mange noder
    assert len(r.diagram.subgraphs) >= 4
    assert "P1" in r.diagram.subgraphs
    assert "P4" in r.diagram.subgraphs
    assert len(r.diagram.nodes) >= 40
    # Og et respektabelt antall kanter
    assert len(r.diagram.edges) >= 30
