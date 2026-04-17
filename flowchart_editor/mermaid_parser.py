"""mermaid_parser.py — Parser for Mermaid flowchart-subset.

Strategi: linje-for-linje state machine med en subgraph-stack.

Støttet subset:
    flowchart TB|LR|BT|RL
    subgraph ID|"Label"|ID["Label"]|ID [Label]
      direction TB|LR|BT|RL
    end

    # Nodedeklarasjoner (definerer form og eventuelt label):
    A[Label]            rect
    A["Label"]          rect med fnutter
    A(Label)            round
    A{Label}            rhombus
    A[[Label]]          subroutine

    # Kanter:
    A --> B
    A --- B
    A -.-> B
    A ==> B
    A --label--> B      # labeled
    A -- label --> B    # labeled med mellomrom
    A ==label==> B
    A -.label.-> B
    A ---|label| B      # pipe-label
    A --> B --> C       # kjedet

    style NODE fill:#xxx,stroke:#xxx,color:#xxx

Ikke forståtte linjer logges i `ParseResult.warnings`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Diagram, Edge, Node, Shape, Subgraph


@dataclass
class ParseResult:
    diagram: Diagram
    warnings: list[str] = field(default_factory=list)


# ── Regex-er ──────────────────────────────────────────────────────────────

_RE_FLOWCHART = re.compile(r"^\s*(?:flowchart|graph)\s+(TB|TD|LR|BT|RL)\s*$", re.IGNORECASE)
_RE_SUBGRAPH = re.compile(
    r"""^\s*subgraph\s+
        (?P<id>[A-Za-z_][\w-]*)       # ID
        (?:\s*\[\s*"?(?P<label>[^"\]]*)"?\s*\])?  # valgfri [Label] eller ["Label"]
        \s*$""",
    re.VERBOSE,
)
_RE_END = re.compile(r"^\s*end\s*$", re.IGNORECASE)
_RE_DIRECTION = re.compile(r"^\s*direction\s+(TB|TD|LR|BT|RL)\s*$", re.IGNORECASE)
_RE_STYLE = re.compile(
    r"""^\s*style\s+(?P<id>[A-Za-z_][\w-]*)\s+(?P<props>.+?)\s*$"""
)
_RE_COMMENT = re.compile(r"^\s*%%.*$")

# Node-deklarasjon alene på en linje: A[...], A(...), A{...}, A[[...]]
_SHAPE_SPECS: list[tuple[Shape, str, str]] = [
    ("subroutine", r"\[\[", r"\]\]"),
    ("rect", r"\[", r"\]"),
    ("round", r"\(", r"\)"),
    ("rhombus", r"\{", r"\}"),
]

_RE_NODE_DECL = re.compile(
    r"""^\s*
        (?P<id>[A-Za-z_][\w-]*)
        (?P<open>\[\[|\[|\(|\{)
        \s*"?(?P<label>.*?)"?\s*
        (?P<close>\]\]|\]|\)|\})
        \s*$""",
    re.VERBOSE,
)

# Kant: fanger opp kilde, pil m/label, mål; brukes for å splitte én kjedet
# kant-linje i atomiske (A, arrow, B)-tupler. Den fulle strengen parses i
# `_parse_edges`-loopen fordi Python-regex ikke har \G-posisjon like enkelt.
_RE_ARROW = re.compile(
    r"""(?P<arrow>
        -->\|[^|]*\|                    # -->|label|
      | ---\|[^|]*\|                    # ---|label|
      | --(?!>)[^-]+?-->                # --label--> (label ikke startende med '>')
      | -\.(?!->)[^.]+?\.->             # -.label.->
      | ==(?![=>])[^=]+?==>             # ==label==>
      | ==>                             # ==>
      | -\.->                           # -.->
      | -->                             # -->
      | ---                             # ---
    )""",
    re.VERBOSE,
)

# Identer — samme regel som subgraph/node
_RE_TOKEN = re.compile(r"[A-Za-z_][\w-]*")


# ── Offentlig API ─────────────────────────────────────────────────────────

def parse_mermaid(text: str) -> ParseResult:
    diagram = Diagram()
    warnings: list[str] = []
    subgraph_stack: list[str] = []

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        if not line or _RE_COMMENT.match(line):
            continue

        if m := _RE_FLOWCHART.match(line):
            direction = _norm_direction(m.group(1))
            diagram.direction = direction  # type: ignore[assignment]
            continue

        if m := _RE_SUBGRAPH.match(line):
            sid = m.group("id")
            label = (m.group("label") or sid).strip()
            if sid not in diagram.subgraphs:
                diagram.add_subgraph(Subgraph(id=sid, label=_clean_label(label)))
            subgraph_stack.append(sid)
            continue

        if _RE_END.match(line):
            if subgraph_stack:
                subgraph_stack.pop()
            else:
                warnings.append(f"Linje {i}: 'end' uten matchende 'subgraph'")
            continue

        if m := _RE_DIRECTION.match(line):
            if subgraph_stack:
                sid = subgraph_stack[-1]
                diagram.subgraphs[sid].direction = _norm_direction(m.group(1))  # type: ignore[assignment]
            else:
                diagram.direction = _norm_direction(m.group(1))  # type: ignore[assignment]
            continue

        if m := _RE_STYLE.match(line):
            _apply_style(diagram, m.group("id"), m.group("props"), warnings, i)
            continue

        if _RE_NODE_DECL.match(line):
            _ensure_node_from_decl(
                diagram, line, subgraph_stack[-1] if subgraph_stack else None
            )
            continue

        # Prøv å parse som én eller flere kjedede kanter
        if _looks_like_edge(line):
            if _parse_edges(
                diagram, line, subgraph_stack[-1] if subgraph_stack else None, warnings, i
            ):
                continue

        warnings.append(f"Linje {i}: ikke forstått — '{raw}'")

    if subgraph_stack:
        warnings.append(
            f"Manglende 'end' for {len(subgraph_stack)} åpen(e) subgraph-blokk(er)"
        )

    return ParseResult(diagram=diagram, warnings=warnings)


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────

def _norm_direction(raw: str) -> str:
    raw = raw.upper()
    return "TB" if raw == "TD" else raw


def _clean_label(label: str) -> str:
    # <br/> og <br> → nylinje; behold annet uendret
    out = re.sub(r"<br\s*/?>", "\n", label, flags=re.IGNORECASE)
    return out.strip()


def _ensure_node(
    diagram: Diagram,
    node_id: str,
    *,
    label: str | None = None,
    shape: Shape | None = None,
    subgraph_id: str | None = None,
) -> Node:
    if node_id in diagram.nodes:
        node = diagram.nodes[node_id]
        if label is not None and (not node.label or node.label == node.id):
            node.label = label
        if shape is not None:
            node.shape = shape
        if subgraph_id is not None and node.subgraph_id is None:
            node.subgraph_id = subgraph_id
        return node
    node = Node(
        id=node_id,
        label=label if label is not None else node_id,
        shape=shape or "rect",
        subgraph_id=subgraph_id,
    )
    diagram.add_node(node)
    return node


def _ensure_node_from_decl(diagram: Diagram, line: str, subgraph_id: str | None) -> None:
    m = _RE_NODE_DECL.match(line)
    if not m:
        return
    open_tok = m.group("open")
    close_tok = m.group("close")
    shape: Shape
    if open_tok == "[[" and close_tok == "]]":
        shape = "subroutine"
    elif open_tok == "[" and close_tok == "]":
        shape = "rect"
    elif open_tok == "(" and close_tok == ")":
        shape = "round"
    elif open_tok == "{" and close_tok == "}":
        shape = "rhombus"
    else:
        return  # mismatched brackets
    label = _clean_label(m.group("label"))
    _ensure_node(
        diagram, m.group("id"),
        label=label or m.group("id"),
        shape=shape,
        subgraph_id=subgraph_id,
    )


def _apply_style(
    diagram: Diagram, node_id: str, props: str, warnings: list[str], line_no: int
) -> None:
    node = diagram.nodes.get(node_id)
    if node is None:
        node = _ensure_node(diagram, node_id)
    for part in props.split(","):
        if ":" not in part:
            continue
        key, value = (p.strip() for p in part.split(":", 1))
        key = key.lower()
        if key == "fill":
            node.fill = value
        elif key == "stroke":
            node.stroke = value
        elif key == "color":
            node.text_color = value
        else:
            warnings.append(f"Linje {line_no}: ukjent style-egenskap '{key}'")


def _looks_like_edge(line: str) -> bool:
    return bool(_RE_ARROW.search(line))


def _parse_edges(
    diagram: Diagram, line: str, subgraph_id: str | None, warnings: list[str], line_no: int
) -> bool:
    """Parser en linje som kan inneholde én eller flere kjedede kanter.

    Strategi: finn alle pil-segmenter i rekkefølge. Mellom (og rundt)
    pilene skal det stå enten en ren node-ID eller en node-deklarasjon.
    """
    matches = list(_RE_ARROW.finditer(line))
    if not matches:
        return False

    segments: list[str] = []
    arrows: list[str] = []
    last = 0
    for m in matches:
        segments.append(line[last:m.start()].strip())
        arrows.append(m.group("arrow"))
        last = m.end()
    segments.append(line[last:].strip())

    if any(not seg for seg in segments):
        warnings.append(f"Linje {line_no}: tom node-referanse i kant-kjede")
        return False

    node_ids: list[str] = []
    for seg in segments:
        nid = _take_node_reference(diagram, seg, subgraph_id)
        if not nid:
            warnings.append(f"Linje {line_no}: kunne ikke tolke node-referanse '{seg}'")
            return False
        node_ids.append(nid)

    for idx, arrow in enumerate(arrows):
        from_id = node_ids[idx]
        to_id = node_ids[idx + 1]
        arrow_type, label = _classify_arrow(arrow)
        try:
            diagram.add_edge(Edge(from_id=from_id, to_id=to_id, label=label, arrow=arrow_type))
        except ValueError as exc:
            warnings.append(f"Linje {line_no}: {exc}")
    return True


def _take_node_reference(
    diagram: Diagram, segment: str, subgraph_id: str | None
) -> str | None:
    """Tolk et segment som enten ren ID eller en node-deklarasjon."""
    segment = segment.strip()
    if not segment:
        return None
    if _RE_NODE_DECL.match(segment):
        _ensure_node_from_decl(diagram, segment, subgraph_id)
        m = _RE_TOKEN.match(segment)
        return m.group(0) if m else None
    if _RE_TOKEN.fullmatch(segment):
        _ensure_node(diagram, segment, subgraph_id=subgraph_id)
        return segment
    return None


def _classify_arrow(arrow: str) -> tuple[str, str]:
    """Returner (arrow_type, label). arrow_type er en av -->, ---, -.->, ==>."""
    arrow = arrow.strip()
    # Pipe-label: A ---|x| B eller A -->|x| B
    if m := re.match(r"^(---|-->)\|([^|]*)\|$", arrow):
        return (m.group(1), m.group(2).strip())
    # ==label==>
    if m := re.match(r"^==\s*(.*?)\s*==>$", arrow):
        label = m.group(1)
        return ("==>", label.strip())
    # -.label.->
    if m := re.match(r"^-\.\s*(.*?)\s*\.->$", arrow):
        return ("-.->", m.group(1).strip())
    # --label--> (inkludert "-- label --")
    if m := re.match(r"^--\s*(.+?)\s*-->$", arrow):
        return ("-->", m.group(1).strip())
    # Rene piler
    if arrow == "-->":
        return ("-->", "")
    if arrow == "---":
        return ("---", "")
    if arrow == "-.->":
        return ("-.->", "")
    if arrow == "==>":
        return ("==>", "")
    # Ukjent — fall tilbake til -->
    return ("-->", "")
