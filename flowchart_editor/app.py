"""app.py — EditorApp: hovedvinduet for flowchart-editoren.

Oppsett:
    Tk root
    └── EditorApp (ttk.Frame fyller root)
        ├── Toolbar (øverst)
        ├── PanedWindow (venstre: canvas, høyre: sidepanel-plassholder)
        └── Statuslinje (nederst)

Mermaid-import/eksport og sidepanel kommer i senere milepæler (M4–M6).
Toolbar-knappene for disse viser en "ikke implementert"-melding inntil videre.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# Gjør filen kjørbar både som `python -m flowchart_editor` OG direkte
# (F5 i VS Code / `python flowchart_editor/app.py`). Ved direktekjøring
# er __package__ tomt, så relative imports feiler — vi legger til forelder
# i sys.path og bytter til absolutte imports.
if __package__:
    from .canvas_widget import FlowchartCanvas, Selection
    from .layout import auto_layout
    from .mermaid_export import export_mermaid
    from .mermaid_parser import parse_mermaid
    from .model import Diagram, Edge, Node, Subgraph
    from .sidepanel import PropertiesPanel
    from .storage import load_diagram, save_diagram
    from .toolbar import Toolbar
else:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from flowchart_editor.canvas_widget import FlowchartCanvas, Selection
    from flowchart_editor.layout import auto_layout
    from flowchart_editor.mermaid_export import export_mermaid
    from flowchart_editor.mermaid_parser import parse_mermaid
    from flowchart_editor.model import Diagram, Edge, Node, Subgraph
    from flowchart_editor.sidepanel import PropertiesPanel
    from flowchart_editor.storage import load_diagram, save_diagram
    from flowchart_editor.toolbar import Toolbar


DIAGRAMS_DIR = Path(__file__).resolve().parent / "diagrams"
FILE_EXTENSION = ".fcjson"
FILE_TYPES = [("Flowchart JSON", f"*{FILE_EXTENSION}"), ("Alle filer", "*.*")]


def _extract_mermaid_block(raw: str) -> str:
    """Hent ut ```mermaid ... ```-blokk hvis filen er Markdown, ellers returner raw."""
    start_marker = "```mermaid"
    i = raw.find(start_marker)
    if i < 0:
        return raw
    body_start = raw.find("\n", i) + 1
    end = raw.find("```", body_start)
    if end < 0:
        return raw[body_start:]
    return raw[body_start:end]


class EditorApp(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=0)
        self.root = root
        self.pack(fill="both", expand=True)

        # Tilstand
        self.diagram: Diagram = Diagram()
        self.current_path: Optional[Path] = None
        self.dirty: bool = False
        # "Legg til kant"-modus: ventende første node når brukeren skal
        # klikke to noder for å lage en kant
        self._edge_mode: bool = False
        self._edge_first_node: Optional[str] = None

        self._build_ui()
        self._wire_callbacks()
        self._update_title()
        self._update_status()

    # ── Oppbygging ─────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self._build_menu()
        self.toolbar = Toolbar(self)
        self.toolbar.pack(side="top", fill="x")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(side="top", fill="both", expand=True)

        self.canvas = FlowchartCanvas(body)
        body.add(self.canvas, weight=3)

        self.sidepanel = PropertiesPanel(body)
        body.add(self.sidepanel, weight=1)

        self.status = ttk.Label(self, text="", anchor="w", padding=(8, 2))
        self.status.pack(side="bottom", fill="x")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Ny", accelerator="Ctrl+N", command=lambda: self.cmd_new())
        file_menu.add_command(label="Åpne…", accelerator="Ctrl+O", command=lambda: self.cmd_open())
        file_menu.add_command(label="Lagre", accelerator="Ctrl+S", command=lambda: self.cmd_save())
        file_menu.add_command(
            label="Lagre som…", accelerator="Ctrl+Shift+S", command=lambda: self.cmd_save_as()
        )
        file_menu.add_separator()
        file_menu.add_command(label="Importer Mermaid…", command=lambda: self.cmd_import_mermaid())
        file_menu.add_command(label="Eksporter Mermaid…", command=lambda: self.cmd_export_mermaid())
        file_menu.add_separator()
        file_menu.add_command(label="Avslutt", command=self.root.destroy)
        menubar.add_cascade(label="Fil", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Legg til node", command=lambda: self.cmd_add_node())
        edit_menu.add_command(label="Legg til subgraph", command=lambda: self.cmd_add_subgraph())
        edit_menu.add_command(label="Legg til kant…", command=lambda: self.cmd_begin_add_edge())
        edit_menu.add_separator()
        edit_menu.add_command(label="Slett valgt", accelerator="Del", command=lambda: self.cmd_delete_selection())
        menubar.add_cascade(label="Rediger", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Zoom inn", command=lambda: self.canvas.zoom_in())
        view_menu.add_command(label="Zoom ut", command=lambda: self.canvas.zoom_out())
        view_menu.add_command(label="100 %", command=lambda: self.canvas.zoom_reset())
        view_menu.add_command(label="Tilpass til innhold", command=lambda: self.canvas.fit_to_content())
        menubar.add_cascade(label="Vis", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Om flowchart-editor…", command=self._show_about)
        menubar.add_cascade(label="Hjelp", menu=help_menu)

        self.root.configure(menu=menubar)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "Om flowchart-editor",
            "Flowchart-editor for Utvalg-1\n"
            "Enkel Tkinter-editor for flowcharts med Mermaid-import/eksport.\n\n"
            "Tastatur:\n"
            "  Ctrl+N  Ny\n"
            "  Ctrl+O  Åpne\n"
            "  Ctrl+S  Lagre\n"
            "  Ctrl+Shift+S  Lagre som\n"
            "  Del     Slett valgt\n"
            "  Esc     Avbryt kant-modus",
        )

    def _wire_callbacks(self) -> None:
        tb = self.toolbar
        tb.on_new = self.cmd_new
        tb.on_open = self.cmd_open
        tb.on_save = self.cmd_save
        tb.on_save_as = self.cmd_save_as
        tb.on_import_mermaid = self.cmd_import_mermaid
        tb.on_export_mermaid = self.cmd_export_mermaid
        tb.on_add_node = self.cmd_add_node
        tb.on_add_edge = self.cmd_begin_add_edge
        tb.on_delete = self.cmd_delete_selection
        tb.on_zoom_in = self.canvas.zoom_in
        tb.on_zoom_out = self.canvas.zoom_out
        tb.on_zoom_reset = self.canvas.zoom_reset
        tb.on_fit = self.canvas.fit_to_content

        self.canvas.on_selection_changed = self._on_selection_changed
        self.canvas.on_node_moved = self._on_node_moved

        self.sidepanel.set_diagram(self.diagram)
        self.sidepanel.on_diagram_changed = self._on_sidepanel_changed
        self.sidepanel.on_delete_selection = self.cmd_delete_selection
        self.sidepanel.on_selection_replaced = self._on_selection_replaced

        # Keyboard shortcuts
        self.root.bind("<Control-n>", lambda _e: self.cmd_new())
        self.root.bind("<Control-o>", lambda _e: self.cmd_open())
        self.root.bind("<Control-s>", lambda _e: self.cmd_save())
        self.root.bind("<Control-Shift-S>", lambda _e: self.cmd_save_as())
        self.root.bind("<Delete>", lambda _e: self.cmd_delete_selection())

    # ── Fil-kommandoer ────────────────────────────────────────────────
    def cmd_new(self) -> None:
        if not self._confirm_discard_changes():
            return
        self.diagram = Diagram()
        self.current_path = None
        self._set_dirty(False)
        self.canvas.set_diagram(self.diagram)
        self.sidepanel.set_diagram(self.diagram)
        self.sidepanel.set_selection(None)
        self._update_status()

    def cmd_open(self) -> None:
        if not self._confirm_discard_changes():
            return
        DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path_str = filedialog.askopenfilename(
            title="Åpne diagram",
            initialdir=str(DIAGRAMS_DIR),
            filetypes=FILE_TYPES,
        )
        if not path_str:
            return
        try:
            self.diagram = load_diagram(path_str)
        except Exception as exc:
            messagebox.showerror("Kunne ikke åpne fil", str(exc))
            return
        self.current_path = Path(path_str)
        self._set_dirty(False)
        self.canvas.set_diagram(self.diagram)
        self.sidepanel.set_diagram(self.diagram)
        self.sidepanel.set_selection(None)
        self._update_status()

    def cmd_save(self) -> None:
        if self.current_path is None:
            self.cmd_save_as()
            return
        try:
            save_diagram(self.diagram, self.current_path)
        except Exception as exc:
            messagebox.showerror("Kunne ikke lagre fil", str(exc))
            return
        self._set_dirty(False)
        self._update_status()

    def cmd_save_as(self) -> None:
        DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path_str = filedialog.asksaveasfilename(
            title="Lagre diagram",
            initialdir=str(DIAGRAMS_DIR),
            defaultextension=FILE_EXTENSION,
            filetypes=FILE_TYPES,
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            save_diagram(self.diagram, path)
        except Exception as exc:
            messagebox.showerror("Kunne ikke lagre fil", str(exc))
            return
        self.current_path = path
        self._set_dirty(False)
        self._update_status()

    def cmd_import_mermaid(self) -> None:
        if not self._confirm_discard_changes():
            return
        DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path_str = filedialog.askopenfilename(
            title="Importer Mermaid",
            initialdir=str(DIAGRAMS_DIR),
            filetypes=[("Mermaid / Markdown", "*.mermaid *.mmd *.md"), ("Alle filer", "*.*")],
        )
        if not path_str:
            return
        try:
            raw = Path(path_str).read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Kunne ikke åpne fil", str(exc))
            return
        mermaid_text = _extract_mermaid_block(raw)
        result = parse_mermaid(mermaid_text)
        auto_layout(result.diagram)
        self.diagram = result.diagram
        self.current_path = None
        self._set_dirty(True)
        self.canvas.set_diagram(self.diagram)
        self.sidepanel.set_diagram(self.diagram)
        self.sidepanel.set_selection(None)
        self.canvas.fit_to_content()
        self._update_status()
        if result.warnings:
            preview = "\n".join(result.warnings[:20])
            more = f"\n\n(+ {len(result.warnings) - 20} flere)" if len(result.warnings) > 20 else ""
            messagebox.showwarning(
                "Import-rapport",
                f"Importen fullført med advarsler:\n\n{preview}{more}",
            )

    def cmd_export_mermaid(self) -> None:
        DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path_str = filedialog.asksaveasfilename(
            title="Eksporter til Mermaid",
            initialdir=str(DIAGRAMS_DIR),
            defaultextension=".mermaid",
            filetypes=[("Mermaid", "*.mermaid *.mmd"), ("Alle filer", "*.*")],
        )
        if not path_str:
            return
        try:
            Path(path_str).write_text(export_mermaid(self.diagram), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Kunne ikke eksportere", str(exc))
            return
        messagebox.showinfo("Eksport fullført", f"Skrev {path_str}")

    # ── Redigering ─────────────────────────────────────────────────────
    def cmd_add_node(self) -> None:
        node_id = self._next_node_id()
        node = Node(id=node_id, label=node_id, x=120.0, y=120.0)
        self.diagram.add_node(node)
        self._set_dirty(True)
        self.canvas.refresh()
        self.canvas.set_selection(node)
        self._update_status()

    def cmd_begin_add_edge(self) -> None:
        if len(self.diagram.nodes) < 2:
            messagebox.showinfo(
                "Legg til kant",
                "Du må ha minst to noder før du kan lage en kant.",
            )
            return
        self._edge_mode = True
        self._edge_first_node = None
        self.status.configure(
            text="Legg-til-kant: klikk første node (Esc for å avbryte)"
        )
        self.root.bind("<Escape>", self._cancel_edge_mode)

    def _cancel_edge_mode(self, _evt=None) -> None:
        self._edge_mode = False
        self._edge_first_node = None
        self.root.unbind("<Escape>")
        self._update_status()

    def cmd_delete_selection(self) -> None:
        sel = self.canvas.get_selection()
        if sel is None:
            return
        if isinstance(sel, Node):
            self.diagram.remove_node(sel.id)
        elif isinstance(sel, Edge):
            self.diagram.remove_edge(sel)
        elif isinstance(sel, Subgraph):
            self.diagram.remove_subgraph(sel.id, remove_members=False)
        self.canvas.set_selection(None)
        self.sidepanel.set_selection(None)
        self._set_dirty(True)
        self.canvas.refresh()
        self._update_status()

    def cmd_add_subgraph(self) -> None:
        sg_id = self._next_subgraph_id()
        self.diagram.add_subgraph(Subgraph(id=sg_id, label=sg_id))
        self._set_dirty(True)
        self.canvas.refresh()
        self._update_status()

    # ── Canvas-callbacks ───────────────────────────────────────────────
    def _on_selection_changed(self, sel: Selection) -> None:
        if self._edge_mode and isinstance(sel, Node):
            self._handle_edge_mode_click(sel)
            return
        self.sidepanel.set_selection(sel)
        self._update_status()

    def _handle_edge_mode_click(self, node: Node) -> None:
        if self._edge_first_node is None:
            self._edge_first_node = node.id
            self.status.configure(
                text=f"Legg-til-kant: første node = {node.id}. Klikk mål-node."
            )
            return
        if node.id == self._edge_first_node:
            self.status.configure(
                text="Mål-node må være forskjellig fra kildenoden. Klikk en annen."
            )
            return
        try:
            self.diagram.add_edge(Edge(from_id=self._edge_first_node, to_id=node.id))
        except ValueError as exc:
            messagebox.showerror("Kunne ikke legge til kant", str(exc))
            self._cancel_edge_mode()
            return
        self._cancel_edge_mode()
        self._set_dirty(True)
        self.canvas.refresh()
        self._update_status()

    def _on_node_moved(self, _node: Node) -> None:
        self._set_dirty(True)
        self._update_status()

    def _on_sidepanel_changed(self) -> None:
        self._set_dirty(True)
        self.canvas.refresh()
        self._update_status()

    def _on_selection_replaced(self, sel: Selection) -> None:
        # Sidepanel har endret ID (f.eks. rename_node) → oppdater canvas-seleksjon
        self.canvas.set_selection(sel)

    # ── Hjelpere ────────────────────────────────────────────────────────
    def _next_node_id(self) -> str:
        existing = set(self.diagram.nodes.keys())
        i = len(existing) + 1
        while True:
            candidate = f"N{i}"
            if candidate not in existing:
                return candidate
            i += 1

    def _next_subgraph_id(self) -> str:
        existing = set(self.diagram.subgraphs.keys())
        i = len(existing) + 1
        while True:
            candidate = f"S{i}"
            if candidate not in existing:
                return candidate
            i += 1

    def _set_dirty(self, flag: bool) -> None:
        self.dirty = flag
        self._update_title()

    def _update_title(self) -> None:
        name = self.current_path.name if self.current_path else "(uten navn)"
        marker = " *" if self.dirty else ""
        self.root.title(f"Flowchart-editor — {name}{marker}")

    def _update_status(self) -> None:
        d = self.diagram
        sel = self.canvas.get_selection()
        if isinstance(sel, Node):
            sel_text = f"Node: {sel.id}"
        elif isinstance(sel, Edge):
            sel_text = f"Kant: {sel.from_id} → {sel.to_id}"
        elif isinstance(sel, Subgraph):
            sel_text = f"Subgraph: {sel.id}"
        else:
            sel_text = "Ingen seleksjon"
        zoom_pct = int(round(self.canvas.get_zoom() * 100))
        self.status.configure(
            text=(
                f"{sel_text}   │   "
                f"Noder: {len(d.nodes)}  Kanter: {len(d.edges)}  Subgraphs: {len(d.subgraphs)}"
                f"   │   Zoom: {zoom_pct} %"
            )
        )

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Ulagrede endringer",
            "Du har ulagrede endringer. Vil du lagre først?",
        )
        if answer is None:
            return False
        if answer:
            self.cmd_save()
            return not self.dirty
        return True


def main() -> None:
    root = tk.Tk()
    root.geometry("1200x780")
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from theme import apply_theme

        apply_theme(root)
    except Exception:
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
    EditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
