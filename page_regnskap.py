"""page_regnskap.py — Regnskap-fane.

Viser formelt Resultatregnskap, Balanse, Kontantstrøm og strukturerte Noter
basert på regnskapslinje-pivot fra Analyse-fanen.

Kall set_analyse_page() fra ui_main etter at begge sider er bygget.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

import preferences

from regnskap_data import (
    RS_STRUCTURE,
    BS_STRUCTURE,
    NOTE_SPECS,
    NOTE_REFS,
    PRINSIPP_DEFAULT,
    ub_lookup,
    fmt_amount,
    eval_auto_row,
    build_cf_rows,
)

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

_INDENT = "    "  # Per innrykknivå


# ---------------------------------------------------------------------------
# Treeview statement helpers
# ---------------------------------------------------------------------------

def _populate_stmt_tree(
    tree: Any,
    structure: list[tuple],
    ub: dict[int, float],
    ub_prev: dict[int, float] | None,
    *,
    has_prev: bool = False,
) -> None:
    try:
        tree.delete(*tree.get_children())
    except Exception:
        return

    for idx, entry in enumerate(structure):
        regnr, label, level, is_sum, is_header = entry
        prefix = _INDENT * level

        if regnr is None:
            tree.insert("", "end", iid=f"hdr_{idx}",
                        values=(prefix + label, "", "", ""),
                        tags=("header",))
            continue

        val = ub.get(regnr)
        val_prev = ub_prev.get(regnr) if ub_prev else None

        if val is None and val_prev is None and not is_sum:
            continue

        val_str = fmt_amount(val) if val is not None else "–"
        prev_str = fmt_amount(val_prev) if (has_prev and val_prev is not None) else ("–" if has_prev else "")

        note_ref = NOTE_REFS.get(regnr)
        note_str = f"Note {note_ref[0]}" if note_ref else ""

        tag = ("major_sum" if (is_sum and level == 0) else
               "sum" if is_sum else "normal")
        if note_str:
            tag_list = (tag, "has_note")
        else:
            tag_list = (tag,)

        tree.insert("", "end", iid=f"row_{idx}_{regnr}",
                    values=(prefix + label, note_str, val_str, prev_str),
                    tags=tag_list)


# ---------------------------------------------------------------------------
# Scrollable note form helpers
# ---------------------------------------------------------------------------

def _make_scrollable(parent: Any) -> tuple[Any, Any]:
    """Returns (canvas, inner_frame) for a scrollable note form."""
    if tk is None:
        return None, None

    canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0)
    vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)

    inner = ttk.Frame(canvas, padding=(12, 8, 12, 12))
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_e: Any) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(e: Any) -> None:
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _scroll(event: Any) -> None:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _scroll))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return canvas, inner


def _build_note_form(
    parent: Any,
    spec: list[dict],
) -> tuple[Any, dict[str, Any]]:
    """
    Build a structured note form in parent.
    Returns (canvas, entry_widgets_by_key).

    Auto-rows: read-only Entry with light blue background.
    Field-rows: editable Entry, normal background.
    """
    if tk is None:
        return None, {}

    canvas, inner = _make_scrollable(parent)
    if inner is None:
        return None, {}

    inner.columnconfigure(0, weight=1, minsize=260)
    inner.columnconfigure(1, weight=0, minsize=160)

    entry_widgets: dict[str, tk.StringVar] = {}

    # Styles
    HDR_BG    = "#E3EAF4"
    AUTO_FG   = "#1A56A0"
    FIELD_BG  = "#FFFFFF"

    row_idx = 0

    for spec_row in spec:
        rtype = spec_row["type"]

        if rtype == "header":
            lbl = ttk.Label(
                inner,
                text=spec_row["label"],
                font=("TkDefaultFont", 9, "bold"),
                foreground="#1A2E5A",
                background=HDR_BG,
                anchor="w",
                padding=(6, 4),
            )
            lbl.grid(row=row_idx, column=0, columnspan=2, sticky="ew",
                     pady=(10, 2))
            row_idx += 1

        elif rtype == "sep":
            sep = ttk.Separator(inner, orient="horizontal")
            sep.grid(row=row_idx, column=0, columnspan=2, sticky="ew",
                     pady=6)
            row_idx += 1

        elif rtype == "auto":
            lbl = ttk.Label(inner, text="  " + spec_row["label"],
                             anchor="w", font=("TkDefaultFont", 10))
            lbl.grid(row=row_idx, column=0, sticky="ew", pady=1)

            svar = tk.StringVar(value="–")
            entry = ttk.Entry(inner, textvariable=svar, width=22,
                               state="readonly", justify="right",
                               font=("TkDefaultFont", 10))
            # Give auto-entries a distinct look
            try:
                style_name = f"Auto.TEntry"
                entry.configure(style=style_name)
            except Exception:
                pass
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(6, 0), pady=1)

            key = f"__auto__{spec_row.get('regnr', '')}_{spec_row.get('period', 'current')}"
            entry_widgets[key] = svar
            row_idx += 1

        elif rtype == "field":
            lbl = ttk.Label(inner, text="  " + spec_row["label"],
                             anchor="w", font=("TkDefaultFont", 10))
            lbl.grid(row=row_idx, column=0, sticky="ew", pady=1)

            key = spec_row.get("key", f"_field_{row_idx}")
            svar = tk.StringVar(value=spec_row.get("default", ""))
            entry = ttk.Entry(inner, textvariable=svar, width=22,
                               justify="right", font=("TkDefaultFont", 10))
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(6, 0), pady=1)

            entry_widgets[key] = svar
            row_idx += 1

    return canvas, entry_widgets


# ---------------------------------------------------------------------------
# RegnskapPage
# ---------------------------------------------------------------------------

class RegnskapPage(ttk.Frame):  # type: ignore[misc]
    """Regnskap-fane: Resultatregnskap, Balanse, Kontantstrøm og Noter."""

    def __init__(self, master: Any, **kw: Any) -> None:
        if ttk is None:
            return  # pragma: no cover
        super().__init__(master, **kw)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self._analyse_page: Any = None
        self._ub: dict[int, float] = {}
        self._ub_prev: dict[int, float] | None = None
        self._has_prev: bool = False
        self._client: str = ""
        self._year: str = ""

        # note entry widgets: note_id → {key → StringVar}
        self._note_vars: dict[str, dict[str, tk.StringVar]] = {}
        # free-text notes: note_id → tk.Text widget
        self._note_text_widgets: dict[str, Any] = {}

        self._build_ui()

    # ------------------------------------------------------------------
    # UI-bygging
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=4)

        self._lbl_client = ttk.Label(toolbar, text="",
                                      font=("TkDefaultFont", 10, "bold"))
        self._lbl_client.pack(side="left", padx=(0, 10))

        ttk.Button(toolbar, text="Oppdater", command=self.refresh,
                   width=10).pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=6, pady=2)

        ttk.Button(toolbar, text="Eksporter Excel", command=self._on_export_excel,
                   width=14).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Eksporter HTML", command=self._on_export_html,
                   width=14).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Eksporter PDF", command=self._on_export_pdf,
                   width=13).pack(side="left", padx=2)

        self._lbl_status = ttk.Label(toolbar, text="Ingen data",
                                      foreground="#888888")
        self._lbl_status.pack(side="left", padx=10)

        # Sub-notebook
        self._nb = ttk.Notebook(self)
        self._nb.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 4))

        self._oversikt_frame = ttk.Frame(self._nb)
        self._rs_frame   = ttk.Frame(self._nb)
        self._bs_frame   = ttk.Frame(self._nb)
        self._cf_frame   = ttk.Frame(self._nb)
        self._noter_frame = ttk.Frame(self._nb)

        self._nb.add(self._oversikt_frame, text="Oversikt")
        self._nb.add(self._rs_frame,    text="Resultatregnskap")
        self._nb.add(self._bs_frame,    text="Balanse")
        self._nb.add(self._cf_frame,    text="Kontantstrøm")
        self._nb.add(self._noter_frame, text="Noter")

        self._build_oversikt_tab(self._oversikt_frame)
        self._build_rs_tab(self._rs_frame)
        self._build_bs_tab(self._bs_frame)
        self._build_cf_tab(self._cf_frame)
        self._build_noter_tab(self._noter_frame)

    # ------------------------------------------------------------------
    # Statement trees
    # ------------------------------------------------------------------

    def _make_stmt_tree(self, parent: Any) -> Any:
        """Bygg statement-tre med Post, I år, Fjor og Note-kolonne."""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=6, pady=6)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(frame, columns=("post", "note", "iaar", "fjor"),
                             show="headings", selectmode="browse")
        tree.heading("post",  text="Post",  anchor="w")
        tree.heading("note",  text="Note",  anchor="center")
        tree.heading("iaar",  text="I år",  anchor="e")
        tree.heading("fjor",  text="Fjor",  anchor="e")
        tree.column("post",  width=350, anchor="w", stretch=True)
        tree.column("note",  width=70,  anchor="center", stretch=False)
        tree.column("iaar",  width=150, anchor="e", stretch=False)
        tree.column("fjor",  width=150, anchor="e", stretch=False)

        # Tag styles
        hdr_bg = "#EEF2F8"
        sum_bg = "#E4EBF5"
        maj_bg = "#D0DDF0"

        tree.tag_configure("header",    background=hdr_bg,
                           font=("TkDefaultFont", 9, "italic"),
                           foreground="#4472C4")
        tree.tag_configure("sum",       background=sum_bg,
                           font=("TkDefaultFont", 10, "bold"))
        tree.tag_configure("major_sum", background=maj_bg,
                           font=("TkDefaultFont", 10, "bold"),
                           foreground="#1A2E5A")
        tree.tag_configure("normal",    font=("TkDefaultFont", 10))
        tree.tag_configure("has_note",  foreground="#1A56A0")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        return tree

    # ------------------------------------------------------------------
    # Oversikt-fane: to valgbare paneler side om side
    # ------------------------------------------------------------------

    _OVERSIKT_OPTIONS = [
        "Resultatregnskap",
        "Balanse",
        "Kontantstrøm",
    ]

    def _build_oversikt_tab(self, parent: Any) -> None:
        """Splittet visning med to valgbare paneler."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        pane = ttk.PanedWindow(parent, orient="horizontal")
        pane.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self._ov_left_tree: Any  = None
        self._ov_right_tree: Any = None

        left_frame  = self._make_oversikt_panel(pane, side="left",  default="Resultatregnskap")
        right_frame = self._make_oversikt_panel(pane, side="right", default="Balanse")
        pane.add(left_frame,  weight=1)
        pane.add(right_frame, weight=1)

    def _make_oversikt_panel(self, pane: Any, *, side: str, default: str) -> Any:
        """Bygg ett panel med dropdown + statement-tre."""
        frame = ttk.Frame(pane)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Toolbar med valg
        tb = ttk.Frame(frame, padding=(4, 2))
        tb.grid(row=0, column=0, sticky="ew")
        ttk.Label(tb, text="Vis:").pack(side="left")

        var = tk.StringVar(value=default)
        cb = ttk.Combobox(tb, textvariable=var,
                           values=self._OVERSIKT_OPTIONS,
                           state="readonly", width=20)
        cb.pack(side="left", padx=(4, 0))

        # Tre-container
        tree_container = ttk.Frame(frame)
        tree_container.grid(row=1, column=0, sticky="nsew")
        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        tree = self._make_stmt_tree(tree_container)

        if side == "left":
            self._ov_left_tree = tree
            self._ov_left_var  = var
        else:
            self._ov_right_tree = tree
            self._ov_right_var  = var

        def _on_change(*_: Any) -> None:
            self._refresh_oversikt_panel(side)

        var.trace_add("write", _on_change)
        return frame

    def _refresh_oversikt_panel(self, side: str) -> None:
        """Oppdater ett oversikt-panel basert på valgt visning."""
        if side == "left":
            tree = self._ov_left_tree
            val  = getattr(self, "_ov_left_var", None)
        else:
            tree = self._ov_right_tree
            val  = getattr(self, "_ov_right_var", None)

        if tree is None or val is None:
            return

        choice = val.get()
        if choice == "Resultatregnskap":
            _populate_stmt_tree(tree, RS_STRUCTURE,
                                self._ub, self._ub_prev, has_prev=self._has_prev)
        elif choice == "Balanse":
            _populate_stmt_tree(tree, BS_STRUCTURE,
                                self._ub, self._ub_prev, has_prev=self._has_prev)
        elif choice == "Kontantstrøm":
            self._populate_cf_into(tree)

    def _populate_cf_into(self, tree: Any) -> None:
        """Fyll et statement-tre med kontantstrøm-data (to kolonner)."""
        try:
            tree.delete(*tree.get_children())
        except Exception:
            return
        if not self._has_prev:
            tree.insert("", "end", values=(
                "Kontantstrøm krever fjorårdata.", "", "", ""), tags=("header",))
            return
        for idx, (label, val, is_sum, is_hdr) in enumerate(
                build_cf_rows(self._ub, self._ub_prev)):
            tag = "header" if is_hdr else ("sum" if is_sum else "normal")
            val_str = fmt_amount(val) if val is not None else ""
            tree.insert("", "end", iid=f"cf_ov_{tree}_{idx}",
                         values=(label, "", val_str, ""), tags=(tag,))

    def _populate_oversikt(self) -> None:
        """Oppdater begge oversikt-paneler."""
        self._refresh_oversikt_panel("left")
        self._refresh_oversikt_panel("right")

    def _build_rs_tab(self, parent: Any) -> None:
        """Resultatregnskap: tre øverst, drilldown-panel under."""
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=2)
        parent.columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        self._rs_tree = self._make_stmt_tree(tree_frame)
        self._rs_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_stmt_select(self._rs_tree))

        sep = ttk.Separator(parent, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew")

        self._rs_drill_frame = ttk.Frame(parent)
        self._rs_drill_frame.grid(row=2, column=0, sticky="nsew")
        self._rs_drill_tree = self._make_drill_tree(self._rs_drill_frame)
        self._rs_drill_frame.grid_remove()  # skjult til noe er valgt

    def _build_bs_tab(self, parent: Any) -> None:
        """Balanse: tre øverst, drilldown-panel under."""
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=2)
        parent.columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        self._bs_tree = self._make_stmt_tree(tree_frame)
        self._bs_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_stmt_select(self._bs_tree))

        sep = ttk.Separator(parent, orient="horizontal")
        sep.grid(row=1, column=0, sticky="ew")

        self._bs_drill_frame = ttk.Frame(parent)
        self._bs_drill_frame.grid(row=2, column=0, sticky="nsew")
        self._bs_drill_tree = self._make_drill_tree(self._bs_drill_frame)
        self._bs_drill_frame.grid_remove()

    def _build_cf_tab(self, parent: Any) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        frame = ttk.Frame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._cf_tree = ttk.Treeview(frame, columns=("post", "belop"),
                                      show="headings", selectmode="browse")
        self._cf_tree.heading("post",  text="Post",  anchor="w")
        self._cf_tree.heading("belop", text="Beløp", anchor="e")
        self._cf_tree.column("post",  width=400, anchor="w", stretch=True)
        self._cf_tree.column("belop", width=140, anchor="e", stretch=False)

        self._cf_tree.tag_configure("header",   background="#EEF2F8",
                                     font=("TkDefaultFont", 9, "italic"),
                                     foreground="#4472C4")
        self._cf_tree.tag_configure("sum",      background="#E4EBF5",
                                     font=("TkDefaultFont", 10, "bold"))
        self._cf_tree.tag_configure("normal",   font=("TkDefaultFont", 10))
        self._cf_tree.tag_configure("blank",    font=("TkDefaultFont", 4))

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._cf_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._cf_tree.configure(yscrollcommand=vsb.set)
        self._cf_tree.grid(row=0, column=0, sticky="nsew")

        self._cf_no_data = ttk.Label(
            parent,
            text="Kontantstrøm krever fjorårstall.\nLast inn SB for to år.",
            foreground="#888888",
            justify="center",
        )

    # ------------------------------------------------------------------
    def _make_drill_tree(self, parent: Any) -> Any:
        """Bygg konto-nivå drilldown-treeview."""
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        self._drill_lbl = ttk.Label(
            parent,
            text="Kontoer som inngår i linjen:",
            font=("TkDefaultFont", 9, "bold"),
            foreground="#4472C4",
        )
        self._drill_lbl.grid(row=0, column=0, columnspan=2, sticky="w",
                             padx=8, pady=(4, 2))

        frame = ttk.Frame(parent)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 4))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(
            frame,
            columns=("konto", "kontonavn", "ib", "bevegelse", "ub", "ub_fjor"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        tree.heading("konto",     text="Konto",     anchor="w")
        tree.heading("kontonavn", text="Navn",       anchor="w")
        tree.heading("ib",        text="IB",         anchor="e")
        tree.heading("bevegelse", text="Bevegelse",  anchor="e")
        tree.heading("ub",        text="UB",         anchor="e")
        tree.heading("ub_fjor",   text="UB fjorår",  anchor="e")
        tree.column("konto",     width=80,  anchor="w", stretch=False)
        tree.column("kontonavn", width=220, anchor="w", stretch=True)
        tree.column("ib",        width=130, anchor="e", stretch=False)
        tree.column("bevegelse", width=130, anchor="e", stretch=False)
        tree.column("ub",        width=130, anchor="e", stretch=False)
        tree.column("ub_fjor",   width=130, anchor="e", stretch=False)

        tree.tag_configure("sum_row", font=("TkDefaultFont", 10, "bold"),
                           background="#E4EBF5")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        return tree

    # ------------------------------------------------------------------
    # Statement click handler
    # ------------------------------------------------------------------

    def _on_stmt_select(self, tree: Any) -> None:
        """Håndter klikk på rad i RS/BS-tre: vis notehenvisning og drilldown."""
        sel = tree.selection()
        if not sel:
            return
        item = sel[0]

        # Find the matching drill frame/tree
        if tree is self._rs_tree:
            drill_frame = self._rs_drill_frame
            drill_tree  = self._rs_drill_tree
        else:
            drill_frame = self._bs_drill_frame
            drill_tree  = self._bs_drill_tree

        # Parse regnr from iid ("row_{idx}_{regnr}" or "hdr_{idx}")
        iid = item
        regnr = None
        if iid.startswith("row_"):
            parts = iid.split("_")
            try:
                regnr = int(parts[-1])
            except (ValueError, IndexError):
                regnr = None

        if regnr is None:
            try:
                drill_frame.grid_remove()
            except Exception:
                pass
            return

        # Update drilldown label
        vals = tree.item(item, "values")
        line_name = str(vals[0]).strip() if vals else str(regnr)
        try:
            self._drill_lbl.configure(
                text=f"Kontoer som inngår i  «{line_name}»  (regnr {regnr}):"
            )
        except Exception:
            pass

        # Check for note reference — jump hint
        note_ref = NOTE_REFS.get(regnr)
        if note_ref:
            try:
                self._drill_lbl.configure(
                    text=f"Kontoer i «{line_name}»   ·   {vals[1] if len(vals) > 1 else ''}"
                         f"  →  klikk notehenvisningen for å gå til noten"
                )
            except Exception:
                pass

        # Populate drilldown
        self._populate_drill(drill_tree, regnr)
        try:
            drill_frame.grid()
        except Exception:
            pass

        # If note reference clicked: navigate to note tab
        # (user clicks the Note column cell — detect via column)
        try:
            col_id = tree.identify_column(tree.winfo_pointerx() - tree.winfo_rootx())
            # col_id is "#1", "#2", "#3", "#4" — note is column 2 = "#2"
            if col_id == "#2" and note_ref:
                self._navigate_to_note(note_ref[1])
        except Exception:
            pass

    def _navigate_to_note(self, note_id: str) -> None:
        """Bytt til Noter-fanen og velg riktig note."""
        try:
            self._nb.select(self._noter_frame)
        except Exception:
            return
        # Find the sub-tab index in _noter_nb
        for idx, (nid, _, _) in enumerate(NOTE_SPECS):
            if nid == note_id:
                try:
                    self._noter_nb.select(idx)
                except Exception:
                    pass
                break

    # ------------------------------------------------------------------
    # Drilldown data
    # ------------------------------------------------------------------

    def _populate_drill(self, drill_tree: Any, regnr: int) -> None:
        """Fyll drilldown-treet med konto-nivå data for gitt regnr."""
        try:
            drill_tree.delete(*drill_tree.get_children())
        except Exception:
            return

        rows = self._get_konto_breakdown(regnr)
        if not rows:
            drill_tree.insert("", "end", values=(
                "", "(ingen kontodata tilgjengelig — last inn SB)", "", "", "", ""),
                tags=())
            return

        sum_ib = sum_bev = sum_ub = sum_ub_prev = 0.0
        has_ub_prev = any(r.get("ub_fjor") is not None for r in rows)

        for r in rows:
            ib   = r.get("ib")
            bev  = r.get("bevegelse")
            ub   = r.get("ub")
            ubp  = r.get("ub_fjor")
            if ib  is not None: sum_ib   += ib
            if bev is not None: sum_bev  += bev
            if ub  is not None: sum_ub   += ub
            if ubp is not None: sum_ub_prev += ubp
            drill_tree.insert("", "end", values=(
                r.get("konto", ""),
                r.get("kontonavn", ""),
                fmt_amount(ib)  if ib  is not None else "–",
                fmt_amount(bev) if bev is not None else "–",
                fmt_amount(ub)  if ub  is not None else "–",
                fmt_amount(ubp) if ubp is not None else ("–" if has_ub_prev else ""),
            ), tags=())

        # Sum row
        drill_tree.insert("", "end", values=(
            "",
            "SUM",
            fmt_amount(sum_ib),
            fmt_amount(sum_bev),
            fmt_amount(sum_ub),
            fmt_amount(sum_ub_prev) if has_ub_prev else "",
        ), tags=("sum_row",))

        # Hide ub_fjor column if no prev data
        try:
            drill_tree.column("ub_fjor", width=0 if not has_ub_prev else 130,
                              minwidth=0)
        except Exception:
            pass

    def _get_konto_breakdown(self, regnr: int) -> list[dict]:
        """Hent konto-nivå data for en gitt regnskapslinje."""
        if self._analyse_page is None:
            return []
        try:
            from regnskap_mapping import apply_interval_mapping

            intervals = getattr(self._analyse_page, "_rl_intervals", None)
            if intervals is None:
                return []

            # Bygg en konto-liste fra SB-data
            sb_df = getattr(self._analyse_page, "_rl_sb_df", None)
            sb_prev_df = getattr(self._analyse_page, "_rl_sb_prev_df", None)

            if not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
                return []

            # Map konto → regnr
            work = sb_df[["konto", "ib", "ub"]].copy()
            work["ib"] = pd.to_numeric(work["ib"], errors="coerce").fillna(0.0)
            work["ub"] = pd.to_numeric(work["ub"], errors="coerce").fillna(0.0)
            mapped = apply_interval_mapping(work, intervals, konto_col="konto").mapped
            filtered = mapped[mapped["regnr"] == regnr].copy()
            if filtered.empty:
                return []

            # Get konto names from analyse page
            kontonavn_map: dict[str, str] = {}
            try:
                df_hb = getattr(self._analyse_page, "_df_filtered", None)
                if isinstance(df_hb, pd.DataFrame) and "Konto" in df_hb.columns and "Kontonavn" in df_hb.columns:
                    kontonavn_map = (
                        df_hb[["Konto", "Kontonavn"]]
                        .drop_duplicates("Konto")
                        .set_index("Konto")["Kontonavn"]
                        .astype(str)
                        .to_dict()
                    )
            except Exception:
                pass

            # Merge prev year UB if available
            prev_map: dict[str, float] = {}
            if isinstance(sb_prev_df, pd.DataFrame) and not sb_prev_df.empty:
                try:
                    wp = sb_prev_df[["konto", "ub"]].copy()
                    wp["ub"] = pd.to_numeric(wp["ub"], errors="coerce").fillna(0.0)
                    mp = apply_interval_mapping(wp, intervals, konto_col="konto").mapped
                    mp_f = mp[mp["regnr"] == regnr]
                    prev_map = mp_f.set_index("konto")["ub"].to_dict()
                except Exception:
                    pass

            rows: list[dict] = []
            for _, row in filtered.iterrows():
                konto = str(row["konto"])
                ib_raw = float(row["ib"])
                ub_raw = float(row["ub"])
                bevegelse = ub_raw - ib_raw
                ub_fjor = prev_map.get(konto)
                rows.append({
                    "konto": konto,
                    "kontonavn": kontonavn_map.get(konto, ""),
                    "ib":        ib_raw,
                    "bevegelse": bevegelse,
                    "ub":        ub_raw,
                    "ub_fjor":   ub_fjor,
                })

            rows.sort(key=lambda r: r["konto"])
            return rows

        except Exception as exc:
            log.warning("_get_konto_breakdown(%s): %s", regnr, exc)
            return []

    # ------------------------------------------------------------------
    # Note forms
    # ------------------------------------------------------------------

    def _build_noter_tab(self, parent: Any) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        noter_nb = ttk.Notebook(parent)
        noter_nb.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._noter_nb = noter_nb

        for note_id, note_label, spec in NOTE_SPECS:
            tab = ttk.Frame(noter_nb)
            noter_nb.add(tab, text=note_label)
            tab.rowconfigure(1, weight=1)
            tab.columnconfigure(0, weight=1)

            # Button bar
            btn_bar = ttk.Frame(tab)
            btn_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
            ttk.Button(btn_bar, text="Lagre note",
                       command=lambda nid=note_id: self._save_note(nid),
                       width=12).pack(side="left")
            ttk.Label(btn_bar,
                      text="  Lagres per klient. Auto-verdier hentes fra regnskapet.",
                      foreground="#888888").pack(side="left")

            # Build content frame
            content_frame = ttk.Frame(tab)
            content_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
            content_frame.rowconfigure(0, weight=1)
            content_frame.columnconfigure(0, weight=1)

            if spec is None:
                # Free text (regnskapsprinsipper)
                txt = tk.Text(content_frame, wrap="word",
                              font=("TkDefaultFont", 10),
                              relief="flat", bg="#FAFAFA", padx=10, pady=8,
                              undo=True)
                vsb = ttk.Scrollbar(content_frame, orient="vertical",
                                    command=txt.yview)
                vsb.grid(row=0, column=1, sticky="ns")
                txt.configure(yscrollcommand=vsb.set)
                txt.grid(row=0, column=0, sticky="nsew")
                txt.insert("1.0", PRINSIPP_DEFAULT)
                txt.bind("<Control-s>",
                         lambda _e, nid=note_id: self._save_note(nid) or "break")
                self._note_text_widgets[note_id] = txt
                content_frame.columnconfigure(0, weight=1)

            else:
                # Structured form
                canvas, entry_vars = _build_note_form(content_frame, spec)
                self._note_vars[note_id] = entry_vars
                entry_vars.get  # ensure dict accessible

    # ------------------------------------------------------------------
    # Data-kobling
    # ------------------------------------------------------------------

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session_obj: Any) -> None:
        try:
            self.after(250, self.refresh)
        except Exception:
            self.refresh()

    # ------------------------------------------------------------------
    # Oppdater-logikk
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        rl_df, client, year = self._fetch_rl_df()
        self._client = str(client or "")
        self._year   = str(year or "")

        if rl_df is None or rl_df.empty:
            self._set_status("Ingen data. Last inn HB og velg klient.")
            self._lbl_client.configure(text="")
            self._clear_all_trees()
            return

        # Merge UB_fjor from Analyse pivot if available
        pivot_df = getattr(self._analyse_page, "_pivot_df_last", None)
        if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
            rl_df = rl_df.copy()
            for col in ("UB_fjor",):
                if col in pivot_df.columns and col not in rl_df.columns:
                    m = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                    rl_df = rl_df.merge(m, on="regnr", how="left")

        self._ub      = ub_lookup(rl_df, "UB")
        has_prev      = "UB_fjor" in rl_df.columns
        self._ub_prev = ub_lookup(rl_df, "UB_fjor") if has_prev else None
        self._has_prev = has_prev

        title = self._client or "Regnskap"
        if self._year:
            title += f"  —  {self._year}"
        self._lbl_client.configure(text=title)

        year_prev = str(int(self._year) - 1) if self._year.isdigit() else ("Fjorår" if has_prev else "")

        # Update column headings in trees
        for tree in (self._rs_tree, self._bs_tree):
            try:
                tree.heading("iaar", text=self._year or "I år")
                tree.heading("fjor", text=year_prev if has_prev else "")
                tree.column("fjor", width=140 if has_prev else 0,
                             minwidth=0 if not has_prev else 60)
            except Exception:
                pass

        self._populate_rs()
        self._populate_bs()
        self._populate_cf()
        self._populate_oversikt()
        self._update_note_auto_values()
        self._load_all_notes()

        prev_label = f"  (med fjorår {year_prev})" if has_prev else ""
        self._set_status(f"Oppdatert{prev_label}")

    def _fetch_rl_df(self) -> tuple[pd.DataFrame | None, str | None, str | None]:
        if self._analyse_page is None:
            return None, None, None
        try:
            import page_analyse_export
            payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(
                page=self._analyse_page)
            rl_df  = payload.get("rl_df")
            client = payload.get("client")
            year   = payload.get("year")
            if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
                return None, client, year
            return rl_df, client, year
        except Exception as exc:
            log.warning("RegnskapPage._fetch_rl_df: %s", exc)
            return None, None, None

    # ------------------------------------------------------------------
    # Populate trees
    # ------------------------------------------------------------------

    def _populate_rs(self) -> None:
        _populate_stmt_tree(self._rs_tree, RS_STRUCTURE,
                            self._ub, self._ub_prev, has_prev=self._has_prev)

    def _populate_bs(self) -> None:
        _populate_stmt_tree(self._bs_tree, BS_STRUCTURE,
                            self._ub, self._ub_prev, has_prev=self._has_prev)

    def _populate_cf(self) -> None:
        try:
            self._cf_tree.delete(*self._cf_tree.get_children())
        except Exception:
            return

        if not self._has_prev:
            try:
                self._cf_no_data.place(relx=0.5, rely=0.4, anchor="center")
                self._cf_tree.place_forget()
            except Exception:
                pass
            return

        try:
            self._cf_no_data.place_forget()
        except Exception:
            pass

        for idx, (label, val, is_sum, is_hdr) in enumerate(
                build_cf_rows(self._ub, self._ub_prev)):
            if is_hdr:
                tag = "header"
            elif not label.strip():
                tag = "blank"
            elif is_sum:
                tag = "sum"
            else:
                tag = "normal"
            val_str = fmt_amount(val) if val is not None else ""
            self._cf_tree.insert("", "end", iid=f"cf_{idx}",
                                  values=(label, val_str), tags=(tag,))

    def _clear_all_trees(self) -> None:
        for tree in (getattr(self, "_rs_tree", None),
                     getattr(self, "_bs_tree", None),
                     getattr(self, "_cf_tree", None)):
            if tree is None:
                continue
            try:
                tree.delete(*tree.get_children())
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Note auto-values
    # ------------------------------------------------------------------

    def _update_note_auto_values(self) -> None:
        """Fill in all __auto__ StringVars from ub/ub_prev."""
        for note_id, vars_dict in self._note_vars.items():
            for key, svar in vars_dict.items():
                if not key.startswith("__auto__"):
                    continue
                # key format: __auto__{regnr}_{period}
                parts = key.split("__auto__", 1)[-1].split("_", 1)
                if len(parts) != 2:
                    continue
                try:
                    regnr  = int(parts[0])
                    period = parts[1]
                except ValueError:
                    continue
                lookup = self._ub_prev if (period == "prev" and self._ub_prev) else self._ub
                val = lookup.get(regnr)
                try:
                    svar.set(fmt_amount(val) if val is not None else "–")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Note persistence
    # ------------------------------------------------------------------

    def _pref_key(self, note_id: str, field_key: str) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in (self._client or "default"))
        return f"regnskap.noter.{safe}.{note_id}.{field_key}"

    def _load_all_notes(self) -> None:
        for note_id, vars_dict in self._note_vars.items():
            for key, svar in vars_dict.items():
                if key.startswith("__auto__"):
                    continue
                saved = preferences.get(self._pref_key(note_id, key))
                if saved is not None:
                    try:
                        svar.set(str(saved))
                    except Exception:
                        pass
        # Free text notes
        for note_id, txt in self._note_text_widgets.items():
            saved = preferences.get(self._pref_key(note_id, "tekst"))
            if saved and isinstance(saved, str):
                try:
                    txt.delete("1.0", "end")
                    txt.insert("1.0", saved)
                except Exception:
                    pass

    def _save_note(self, note_id: str) -> None:
        # Structured form fields
        vars_dict = self._note_vars.get(note_id) or {}
        for key, svar in vars_dict.items():
            if key.startswith("__auto__"):
                continue
            try:
                preferences.set(self._pref_key(note_id, key), svar.get())
            except Exception:
                pass
        # Free text
        txt = self._note_text_widgets.get(note_id)
        if txt is not None:
            try:
                content = txt.get("1.0", "end-1c")
                preferences.set(self._pref_key(note_id, "tekst"), content)
            except Exception:
                pass

    def _collect_notes_data(self) -> dict[str, dict[str, str]]:
        """Gather all note field values for export."""
        out: dict[str, dict[str, str]] = {}
        for note_id, vars_dict in self._note_vars.items():
            nd: dict[str, str] = {}
            for key, svar in vars_dict.items():
                if key.startswith("__auto__"):
                    continue
                try:
                    nd[key] = svar.get()
                except Exception:
                    nd[key] = ""
            out[note_id] = nd
        for note_id, txt in self._note_text_widgets.items():
            try:
                out.setdefault(note_id, {})["tekst"] = txt.get("1.0", "end-1c")
            except Exception:
                pass
        return out

    # ------------------------------------------------------------------
    # Export handlers
    # ------------------------------------------------------------------

    def _get_export_rl_df(self) -> pd.DataFrame | None:
        rl_df, _, _ = self._fetch_rl_df()
        if rl_df is None or rl_df.empty:
            return None
        # Merge UB_fjor
        pivot_df = getattr(self._analyse_page, "_pivot_df_last", None)
        if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
            rl_df = rl_df.copy()
            if "UB_fjor" not in rl_df.columns:
                m = pivot_df[["regnr", "UB_fjor"]].drop_duplicates(subset=["regnr"])
                rl_df = rl_df.merge(m, on="regnr", how="left")
        return rl_df

    def _on_export_excel(self) -> None:
        if filedialog is None:
            return
        rl_df = self._get_export_rl_df()
        if rl_df is None:
            self._msg_no_data()
            return

        base = f"Årsregnskap {self._client} {self._year}".strip()
        safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lagre Excel-årsregnskap",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx"), ("Alle filer", "*.*")],
            initialfile=safe_base + ".xlsx",
        )
        if not path:
            return

        try:
            import regnskap_report
            regnskap_report.save_report_excel(
                path, rl_df,
                notes_data=self._collect_notes_data(),
                client=self._client,
                year=self._year,
            )
        except Exception as exc:
            if messagebox:
                messagebox.showerror("Eksport", f"Kunne ikke lage Excel-rapport:\n{exc}")
            log.exception("Excel export failed")
            return

        self._set_status(f"Excel lagret: {path}")
        try:
            import os
            os.startfile(path)
        except Exception:
            pass

    def _on_export_html(self) -> None:
        if filedialog is None:
            return
        rl_df = self._get_export_rl_df()
        if rl_df is None:
            self._msg_no_data()
            return

        base = f"Årsregnskap {self._client} {self._year}".strip()
        safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lagre HTML-årsregnskap",
            defaultextension=".html",
            filetypes=[("HTML-rapport", "*.html"), ("Alle filer", "*.*")],
            initialfile=safe_base + ".html",
        )
        if not path:
            return

        try:
            import regnskap_report
            regnskap_report.save_report_html(
                path, rl_df,
                notes_data=self._collect_notes_data(),
                client=self._client,
                year=self._year,
            )
        except Exception as exc:
            if messagebox:
                messagebox.showerror("Eksport", f"Kunne ikke lage HTML-rapport:\n{exc}")
            log.exception("HTML export failed")
            return

        self._set_status(f"HTML lagret: {path}")
        try:
            import webbrowser
            from pathlib import Path
            webbrowser.open(Path(path).as_uri())
        except Exception:
            pass

    def _on_export_pdf(self) -> None:
        if filedialog is None:
            return
        rl_df = self._get_export_rl_df()
        if rl_df is None:
            self._msg_no_data()
            return

        base = f"Årsregnskap {self._client} {self._year}".strip()
        safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lagre PDF-årsregnskap",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("Alle filer", "*.*")],
            initialfile=safe_base + ".pdf",
        )
        if not path:
            return

        self._set_status("Genererer PDF…")
        try:
            self.update_idletasks()
        except Exception:
            pass

        try:
            import regnskap_report
            regnskap_report.save_report_pdf(
                path, rl_df,
                notes_data=self._collect_notes_data(),
                client=self._client,
                year=self._year,
            )
        except Exception as exc:
            if messagebox:
                messagebox.showerror("Eksport", f"Kunne ikke lage PDF:\n{exc}")
            log.exception("PDF export failed")
            self._set_status("PDF-eksport feilet")
            return

        self._set_status(f"PDF lagret: {path}")
        try:
            import os
            os.startfile(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _msg_no_data(self) -> None:
        if messagebox:
            messagebox.showinfo("Eksport",
                "Ingen regnskapsdata tilgjengelig.\n"
                "Last inn HB-data og velg klient.")

    def _set_status(self, msg: str) -> None:
        try:
            self._lbl_status.configure(text=msg)
        except Exception:
            pass
