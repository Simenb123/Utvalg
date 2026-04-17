"""sidepanel.py — PropertiesPanel: dynamisk redigeringsskjema.

Skjemaet bygges opp på nytt hver gang seleksjonen endres. Endringer i
widgets skriver direkte til Diagram-objektet og kaller en
`on_diagram_changed`-callback slik at EditorApp kan re-rendre canvas og
markere diagrammet som "dirty".
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable, Optional

from . import style
from .canvas_widget import Selection
from .layout import fit_node_height
from .model import Diagram, Edge, Node, Subgraph


SHAPE_LABELS = [
    ("rect", "Rektangel []"),
    ("round", "Avrundet ()"),
    ("rhombus", "Rombe {}"),
    ("subroutine", "Subrutine [[]]"),
]
ARROW_LABELS = [
    ("-->", "Pil   -->"),
    ("---", "Linje ---"),
    ("-.->", "Stiplet -.->"),
    ("==>", "Tykk  ==>"),
]
DIRECTION_LABELS = [
    ("TB", "Ovenfra og ned (TB)"),
    ("LR", "Venstre mot høyre (LR)"),
    ("BT", "Nedenfra og opp (BT)"),
    ("RL", "Høyre mot venstre (RL)"),
]


class PropertiesPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=(8, 8))

        self._diagram: Diagram = Diagram()
        self._selection: Selection = None

        # Callbacks som settes av EditorApp
        self.on_diagram_changed: Optional[Callable[[], None]] = None
        self.on_delete_selection: Optional[Callable[[], None]] = None
        self.on_selection_replaced: Optional[Callable[[Selection], None]] = None

        self._body = ttk.Frame(self)
        self._body.pack(fill="both", expand=True)
        self._build_empty()

    # ── Offentlig API ───────────────────────────────────────────────────
    def set_diagram(self, diagram: Diagram) -> None:
        self._diagram = diagram
        self._rebuild()

    def set_selection(self, selection: Selection) -> None:
        self._selection = selection
        self._rebuild()

    # ── Oppbygging ──────────────────────────────────────────────────────
    def _rebuild(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        sel = self._selection
        if isinstance(sel, Node):
            self._build_node_form(sel)
        elif isinstance(sel, Edge):
            self._build_edge_form(sel)
        elif isinstance(sel, Subgraph):
            self._build_subgraph_form(sel)
        else:
            self._build_empty()

    def _header(self, parent: tk.Misc, text: str) -> None:
        ttk.Label(parent, text=text, font=style.FONT_TITLE).pack(fill="x", pady=(0, 6))

    def _row(self, parent: tk.Misc, label: str) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=2)
        ttk.Label(frame, text=label, width=12).pack(side="left")
        return frame

    # ── Tom seleksjon: Diagram-nivå ────────────────────────────────────
    def _build_empty(self) -> None:
        self._header(self._body, "Diagram")

        row = self._row(self._body, "Retning")
        direction_var = tk.StringVar(value=self._diagram.direction)
        combo = ttk.Combobox(
            row,
            textvariable=direction_var,
            values=[label for _, label in DIRECTION_LABELS],
            state="readonly",
        )
        combo.set(dict(DIRECTION_LABELS)[self._diagram.direction])
        combo.pack(side="left", fill="x", expand=True)

        def on_change(_evt=None) -> None:
            label_to_value = {label: value for value, label in DIRECTION_LABELS}
            self._diagram.direction = label_to_value[combo.get()]  # type: ignore[assignment]
            self._notify_changed()

        combo.bind("<<ComboboxSelected>>", on_change)

        stats = (
            f"Noder: {len(self._diagram.nodes)}\n"
            f"Kanter: {len(self._diagram.edges)}\n"
            f"Subgraphs: {len(self._diagram.subgraphs)}"
        )
        ttk.Label(self._body, text=stats, justify="left").pack(fill="x", pady=(12, 0))

        ttk.Label(
            self._body,
            text="Tips: Klikk en node, kant eller subgraph\npå lerretet for å redigere.",
            foreground=style.SUBGRAPH_LABEL,
            justify="left",
        ).pack(fill="x", pady=(16, 0))

    # ── Node-skjema ─────────────────────────────────────────────────────
    def _build_node_form(self, node: Node) -> None:
        self._header(self._body, f"Node: {node.id}")

        # ID
        row = self._row(self._body, "ID")
        id_var = tk.StringVar(value=node.id)
        id_entry = ttk.Entry(row, textvariable=id_var)
        id_entry.pack(side="left", fill="x", expand=True)

        def commit_id(_evt=None) -> None:
            new_id = id_var.get().strip()
            if not new_id or new_id == node.id:
                id_var.set(node.id)
                return
            try:
                self._diagram.rename_node(node.id, new_id)
            except ValueError as exc:
                messagebox.showerror("Ugyldig ID", str(exc))
                id_var.set(node.id)
                return
            self._selection = self._diagram.nodes[new_id]
            if self.on_selection_replaced:
                self.on_selection_replaced(self._selection)
            self._notify_changed()
            self._rebuild()

        id_entry.bind("<FocusOut>", commit_id)
        id_entry.bind("<Return>", commit_id)

        # Label (flerlinjig)
        ttk.Label(self._body, text="Label").pack(anchor="w", pady=(6, 0))
        label_text = tk.Text(self._body, height=3, wrap="word", font=style.FONT_BODY)
        label_text.insert("1.0", node.label)
        label_text.pack(fill="x")

        def commit_label(_evt=None) -> None:
            new_label = label_text.get("1.0", "end-1c")
            if new_label != node.label:
                node.label = new_label
                fit_node_height(node)
                self._notify_changed()

        label_text.bind("<FocusOut>", commit_label)

        # Shape
        row = self._row(self._body, "Form")
        shape_combo = ttk.Combobox(
            row,
            values=[label for _, label in SHAPE_LABELS],
            state="readonly",
        )
        shape_combo.set(dict(SHAPE_LABELS)[node.shape])
        shape_combo.pack(side="left", fill="x", expand=True)

        def on_shape(_evt=None) -> None:
            label_to_value = {label: value for value, label in SHAPE_LABELS}
            node.shape = label_to_value[shape_combo.get()]  # type: ignore[assignment]
            self._notify_changed()

        shape_combo.bind("<<ComboboxSelected>>", on_shape)

        # Farger
        self._color_row(self._body, "Fyll", node, "fill")
        self._color_row(self._body, "Strek", node, "stroke")
        self._color_row(self._body, "Tekstfarge", node, "text_color")

        # Subgraph-tilhørighet
        row = self._row(self._body, "Subgraph")
        subgraph_options = ["(ingen)"] + list(self._diagram.subgraphs.keys())
        sg_combo = ttk.Combobox(row, values=subgraph_options, state="readonly")
        sg_combo.set(node.subgraph_id if node.subgraph_id else "(ingen)")
        sg_combo.pack(side="left", fill="x", expand=True)

        def on_subgraph(_evt=None) -> None:
            val = sg_combo.get()
            node.subgraph_id = None if val == "(ingen)" else val
            self._notify_changed()

        sg_combo.bind("<<ComboboxSelected>>", on_subgraph)

        self._delete_button("Slett node")

    # ── Kant-skjema ─────────────────────────────────────────────────────
    def _build_edge_form(self, edge: Edge) -> None:
        self._header(self._body, "Kant")

        node_ids = list(self._diagram.nodes.keys())

        row = self._row(self._body, "Fra")
        from_combo = ttk.Combobox(row, values=node_ids, state="readonly")
        from_combo.set(edge.from_id)
        from_combo.pack(side="left", fill="x", expand=True)

        def on_from(_evt=None) -> None:
            new = from_combo.get()
            if new in self._diagram.nodes:
                edge.from_id = new
                self._notify_changed()

        from_combo.bind("<<ComboboxSelected>>", on_from)

        row = self._row(self._body, "Til")
        to_combo = ttk.Combobox(row, values=node_ids, state="readonly")
        to_combo.set(edge.to_id)
        to_combo.pack(side="left", fill="x", expand=True)

        def on_to(_evt=None) -> None:
            new = to_combo.get()
            if new in self._diagram.nodes:
                edge.to_id = new
                self._notify_changed()

        to_combo.bind("<<ComboboxSelected>>", on_to)

        row = self._row(self._body, "Label")
        label_var = tk.StringVar(value=edge.label)
        label_entry = ttk.Entry(row, textvariable=label_var)
        label_entry.pack(side="left", fill="x", expand=True)

        def commit_label(_evt=None) -> None:
            new = label_var.get()
            if new != edge.label:
                edge.label = new
                self._notify_changed()

        label_entry.bind("<FocusOut>", commit_label)
        label_entry.bind("<Return>", commit_label)

        row = self._row(self._body, "Stil")
        arrow_combo = ttk.Combobox(
            row,
            values=[label for _, label in ARROW_LABELS],
            state="readonly",
        )
        arrow_combo.set(dict(ARROW_LABELS)[edge.arrow])
        arrow_combo.pack(side="left", fill="x", expand=True)

        def on_arrow(_evt=None) -> None:
            label_to_value = {label: value for value, label in ARROW_LABELS}
            edge.arrow = label_to_value[arrow_combo.get()]  # type: ignore[assignment]
            self._notify_changed()

        arrow_combo.bind("<<ComboboxSelected>>", on_arrow)

        self._delete_button("Slett kant")

    # ── Subgraph-skjema ─────────────────────────────────────────────────
    def _build_subgraph_form(self, sg: Subgraph) -> None:
        self._header(self._body, f"Subgraph: {sg.id}")

        row = self._row(self._body, "ID")
        id_var = tk.StringVar(value=sg.id)
        id_entry = ttk.Entry(row, textvariable=id_var)
        id_entry.pack(side="left", fill="x", expand=True)

        def commit_id(_evt=None) -> None:
            new_id = id_var.get().strip()
            if not new_id or new_id == sg.id:
                id_var.set(sg.id)
                return
            if new_id in self._diagram.subgraphs:
                messagebox.showerror("Ugyldig ID", f"Subgraph {new_id!r} finnes allerede")
                id_var.set(sg.id)
                return
            # Bytt nøkkel og oppdater medlemskap
            self._diagram.subgraphs.pop(sg.id)
            for node in self._diagram.nodes.values():
                if node.subgraph_id == sg.id:
                    node.subgraph_id = new_id
            sg.id = new_id
            self._diagram.subgraphs[new_id] = sg
            if self.on_selection_replaced:
                self.on_selection_replaced(sg)
            self._notify_changed()
            self._rebuild()

        id_entry.bind("<FocusOut>", commit_id)
        id_entry.bind("<Return>", commit_id)

        row = self._row(self._body, "Label")
        label_var = tk.StringVar(value=sg.label)
        label_entry = ttk.Entry(row, textvariable=label_var)
        label_entry.pack(side="left", fill="x", expand=True)

        def commit_label(_evt=None) -> None:
            new = label_var.get()
            if new != sg.label:
                sg.label = new
                self._notify_changed()

        label_entry.bind("<FocusOut>", commit_label)
        label_entry.bind("<Return>", commit_label)

        row = self._row(self._body, "Retning")
        dir_combo = ttk.Combobox(
            row,
            values=[label for _, label in DIRECTION_LABELS],
            state="readonly",
        )
        dir_combo.set(dict(DIRECTION_LABELS)[sg.direction])
        dir_combo.pack(side="left", fill="x", expand=True)

        def on_direction(_evt=None) -> None:
            label_to_value = {label: value for value, label in DIRECTION_LABELS}
            sg.direction = label_to_value[dir_combo.get()]  # type: ignore[assignment]
            self._notify_changed()

        dir_combo.bind("<<ComboboxSelected>>", on_direction)

        self._color_row(self._body, "Fyll", sg, "fill")
        self._color_row(self._body, "Strek", sg, "stroke")

        self._delete_button("Slett subgraph")

    # ── Felles hjelpere ─────────────────────────────────────────────────
    def _color_row(self, parent: tk.Misc, label: str, obj: object, attr: str) -> None:
        row = self._row(parent, label)
        current = getattr(obj, attr)
        swatch = tk.Label(row, text="   ", background=current, relief="groove", width=3)
        swatch.pack(side="left", padx=(0, 6))
        value_var = tk.StringVar(value=current)
        entry = ttk.Entry(row, textvariable=value_var, width=10)
        entry.pack(side="left")

        def pick() -> None:
            color = colorchooser.askcolor(color=getattr(obj, attr), title=label)
            hex_value = color[1] if color else None
            if not hex_value:
                return
            setattr(obj, attr, hex_value)
            value_var.set(hex_value)
            swatch.configure(background=hex_value)
            self._notify_changed()

        def commit(_evt=None) -> None:
            val = value_var.get().strip()
            if val and val.startswith("#"):
                try:
                    swatch.configure(background=val)
                except tk.TclError:
                    value_var.set(getattr(obj, attr))
                    return
                setattr(obj, attr, val)
                self._notify_changed()

        ttk.Button(row, text="Velg…", command=pick).pack(side="left", padx=(6, 0))
        entry.bind("<FocusOut>", commit)
        entry.bind("<Return>", commit)

    def _delete_button(self, text: str) -> None:
        ttk.Separator(self._body).pack(fill="x", pady=(12, 6))
        ttk.Button(
            self._body,
            text=text,
            command=lambda: self.on_delete_selection and self.on_delete_selection(),
        ).pack(fill="x")

    def _notify_changed(self) -> None:
        if self.on_diagram_changed:
            self.on_diagram_changed()
