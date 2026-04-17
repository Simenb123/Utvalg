"""mermaid_export.py — Konverter Diagram til Mermaid flowchart-tekst.

Dekker samme subset som `mermaid_parser.py`:
    flowchart TB|LR|BT|RL
    subgraph ID ["Label"]
      direction …
    end
    NODE[Label]       rect
    NODE(Label)       round
    NODE{Label}       rhombus
    NODE[[Label]]     subroutine
    A --> B
    A --- B
    A -.-> B
    A ==> B
    A --label--> B
    style NODE fill:#xxx,stroke:#xxx,color:#xxx
"""

from __future__ import annotations

from typing import Iterable

from .model import Diagram, Edge, Node, Subgraph


# Default-verdier som ikke trenger `style`-linje
_DEFAULT_FILL = "#FFFFFF"
_DEFAULT_STROKE = "#D0D5DD"
_DEFAULT_TEXT = "#101828"


def export_mermaid(diagram: Diagram) -> str:
    lines: list[str] = [f"flowchart {diagram.direction}"]

    # Subgraph-grupper først (med deres noder inni), deretter "frie" noder
    used_node_ids: set[str] = set()
    for sid, sg in diagram.subgraphs.items():
        lines.append(f"    subgraph {sid} [\"{_escape_label(sg.label or sg.id)}\"]")
        if sg.direction and sg.direction != diagram.direction:
            lines.append(f"        direction {sg.direction}")
        for node in _nodes_in_subgraph(diagram, sid):
            lines.append(f"        {_node_line(node)}")
            used_node_ids.add(node.id)
        lines.append("    end")

    for node in diagram.nodes.values():
        if node.id in used_node_ids:
            continue
        lines.append(f"    {_node_line(node)}")

    # Kanter
    for edge in diagram.edges:
        lines.append(f"    {_edge_line(edge)}")

    # Style-linjer for ikke-default farger
    for node in diagram.nodes.values():
        style_parts: list[str] = []
        if node.fill and node.fill.upper() != _DEFAULT_FILL:
            style_parts.append(f"fill:{node.fill}")
        if node.stroke and node.stroke.upper() != _DEFAULT_STROKE:
            style_parts.append(f"stroke:{node.stroke}")
        if node.text_color and node.text_color.upper() != _DEFAULT_TEXT:
            style_parts.append(f"color:{node.text_color}")
        if style_parts:
            lines.append(f"    style {node.id} {','.join(style_parts)}")

    return "\n".join(lines) + "\n"


def _nodes_in_subgraph(diagram: Diagram, subgraph_id: str) -> Iterable[Node]:
    return [n for n in diagram.nodes.values() if n.subgraph_id == subgraph_id]


def _node_line(node: Node) -> str:
    label = _escape_label(node.label or node.id)
    if node.shape == "round":
        return f"{node.id}(\"{label}\")"
    if node.shape == "rhombus":
        return f"{node.id}{{\"{label}\"}}"
    if node.shape == "subroutine":
        return f"{node.id}[[\"{label}\"]]"
    return f"{node.id}[\"{label}\"]"


def _edge_line(edge: Edge) -> str:
    if edge.label:
        label = _escape_label(edge.label)
        if edge.arrow == "---":
            return f"{edge.from_id} ---|{label}| {edge.to_id}"
        if edge.arrow == "-.->":
            return f"{edge.from_id} -. {label} .-> {edge.to_id}"
        if edge.arrow == "==>":
            return f"{edge.from_id} =={label}==> {edge.to_id}"
        return f"{edge.from_id} --{label}--> {edge.to_id}"
    return f"{edge.from_id} {edge.arrow} {edge.to_id}"


def _escape_label(label: str) -> str:
    # Erstatt linjeskift med <br> (Mermaid-konvensjon) og escape doble fnutter
    return label.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "<br/>")
