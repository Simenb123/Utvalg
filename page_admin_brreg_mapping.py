"""page_admin_brreg_mapping.py — admin-editor for BRREG-linje → regnr.

Split-view UI:
- Venstre: søkbar liste over egne regnskapslinjer (regnr — navn).
- Høyre: tabell over alle kanoniske BRREG-linjer fra ``brreg_rl_comparison``.

Workflow:
1. Marker en BRREG-linje i høyre tabell.
2. Søk/scroll i venstre liste, dobbeltklikk en RL → mapping settes.
3. Marker BRREG-linje → "Tøm mapping" eller Delete for å fjerne.
4. "Foreslå fra alias" pre-fyller umappede rader basert på alias-matching.

Mappingen persisteres via ``brreg_mapping_config``. BRREG-tall fyller så raden
for det regnr brukeren har valgt i Analyse-fanen, uavhengig av alias-matching
(som beholdes som fall-back).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import brreg_mapping_config
import brreg_rl_comparison


_TITLE = "BRREG-mapping"
_BRREG_COLUMNS = ("brreg_key", "description", "availability", "regnr", "rl_name")
_BRREG_HEADINGS = {
    "brreg_key": "BRREG-nøkkel",
    "description": "Beskrivelse",
    "availability": "Kilde",
    "regnr": "Mappet regnr",
    "rl_name": "RL-navn",
}
_BRREG_WIDTHS = {
    "brreg_key": 170,
    "description": 170,
    "availability": 70,
    "regnr": 90,
    "rl_name": 200,
}
_AVAILABILITY_TEXT = {
    "sum": "Sum",
    "detail": "Detalj",
}


def _load_regnskapslinjer() -> tuple[list[tuple[int, str]], pd.DataFrame | None]:
    """Returner ``([(regnr, navn), ...], full_df)`` sortert på regnr."""
    try:
        import regnskapslinje_mapping_service as svc
        _intervals, regnskapslinjer_df = svc.load_rl_config_dataframes()
    except Exception:
        return [], None
    if not isinstance(regnskapslinjer_df, pd.DataFrame) or regnskapslinjer_df.empty:
        return [], regnskapslinjer_df
    cols = {str(c).strip().lower(): c for c in regnskapslinjer_df.columns}
    nr_col = cols.get("regnr") or cols.get("nr")
    navn_col = cols.get("regnskapslinje") or cols.get("navn")
    if not nr_col or not navn_col:
        return [], regnskapslinjer_df
    out: list[tuple[int, str]] = []
    for _, row in regnskapslinjer_df.iterrows():
        try:
            regnr = int(row.get(nr_col))
        except (TypeError, ValueError):
            continue
        navn = str(row.get(navn_col) or "").strip()
        if navn:
            out.append((regnr, navn))
    out.sort(key=lambda pair: pair[0])
    return out, regnskapslinjer_df


class _BrregMappingEditor(ttk.Frame):  # type: ignore[misc]
    """Admin-fane for å mappe BRREG-linjer til egne regnr."""

    def __init__(self, master: Any, *, title: str = _TITLE) -> None:
        super().__init__(master)
        self._title = title
        self._mapping: dict[str, int] = {}
        self._brreg_keys: list[tuple[str, str]] = []
        self._regnskapslinjer: list[tuple[int, str]] = []
        self._regnskapslinjer_df: pd.DataFrame | None = None
        self._regnr_to_navn: dict[int, str] = {}
        self._selected_brreg_key: str = ""
        self._rl_rows_in_tree: list[tuple[int, str]] = []
        self._rl_sort: tuple[str, bool] = ("regnr", False)
        self._brreg_sort: tuple[str, bool] = ("brreg_key", False)

        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        self._rl_search_var = tk.StringVar(value="") if tk is not None else None
        # Detalj-nøkler er sjelden populert i BRREG's åpne API — skjul som
        # standard slik at editoren matcher hva revisor faktisk får ut.
        self._show_detail_var = tk.BooleanVar(value=False) if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()

        if self._rl_search_var is not None:
            try:
                self._rl_search_var.trace_add("write", lambda *_a: self._refresh_rl_tree())
            except Exception:
                pass
        if self._show_detail_var is not None:
            try:
                self._show_detail_var.trace_add("write", lambda *_a: self._refresh_brreg_tree())
            except Exception:
                pass

        self.reload()

    # ------------------------------------------------------------------
    # Oppbygging av widgets
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=self._title, style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        if self._path_var is not None:
            ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(
                row=1, column=0, sticky="w", pady=(4, 0)
            )
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(
            row=0, column=1, rowspan=2, padx=(8, 0)
        )
        ttk.Button(header, text="Foreslå fra alias", command=self._suggest_from_aliases).grid(
            row=0, column=2, rowspan=2, padx=(8, 0)
        )
        ttk.Button(header, text="Forhåndsvis", command=self._show_preview).grid(
            row=0, column=3, rowspan=2, padx=(8, 0)
        )
        ttk.Button(header, text="Lagre", command=self.save).grid(
            row=0, column=4, rowspan=2, padx=(8, 0)
        )
        ttk.Label(
            self,
            text=(
                "Kilde: BRREG Regnskapsregisteret (data.brreg.no) — åpent API. "
                "Sum-nivå er alltid populert. Detalj-nøkler er optional og blir ofte "
                "tomme i API-svaret — mappingen lagres uansett, men raden forblir blank "
                "til selskapet rapporterer feltet."
            ),
            style="Muted.TLabel",
            padding=(8, 0, 8, 6),
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, sticky="ew")

    def _build_body(self) -> None:
        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=2, uniform="cols")
        body.columnconfigure(1, weight=3, uniform="cols")
        body.rowconfigure(0, weight=1)

        # Venstre: RL-liste med søk
        left = ttk.LabelFrame(body, text="Regnskapslinjer (dine)")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        search_row = ttk.Frame(left, padding=(6, 6, 6, 4))
        search_row.grid(row=0, column=0, sticky="ew")
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Søk:").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(search_row, textvariable=self._rl_search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._rl_search_entry = entry

        rl_tree_frame = ttk.Frame(left, padding=(6, 0, 6, 6))
        rl_tree_frame.grid(row=2, column=0, sticky="nsew")
        rl_tree_frame.columnconfigure(0, weight=1)
        rl_tree_frame.rowconfigure(0, weight=1)
        rl_tree = ttk.Treeview(
            rl_tree_frame,
            columns=("regnr", "navn"),
            show="headings",
            selectmode="browse",
        )
        rl_tree.grid(row=0, column=0, sticky="nsew")
        rl_tree.heading("regnr", text="Regnr", command=lambda: self._on_rl_sort("regnr"))
        rl_tree.heading("navn", text="Regnskapslinje", command=lambda: self._on_rl_sort("navn"))
        rl_tree.column("regnr", width=70, anchor="w", stretch=False)
        rl_tree.column("navn", width=220, anchor="w")
        rl_yscroll = ttk.Scrollbar(rl_tree_frame, orient="vertical", command=rl_tree.yview)
        rl_yscroll.grid(row=0, column=1, sticky="ns")
        rl_tree.configure(yscrollcommand=rl_yscroll.set)
        try:
            rl_tree.bind("<Double-1>", lambda _e: self._on_rl_activate(), add="+")
            rl_tree.bind("<Return>", lambda _e: self._on_rl_activate(), add="+")
        except Exception:
            pass
        self._rl_tree = rl_tree

        hint = ttk.Label(
            left,
            text="Dobbeltklikk (eller Enter) = mapping til valgt BRREG-linje.",
            style="Muted.TLabel",
            padding=(6, 0, 6, 6),
            wraplength=300,
            justify="left",
        )
        hint.grid(row=3, column=0, sticky="ew")

        # Høyre: BRREG-tabell
        right = ttk.LabelFrame(body, text="BRREG-linjer")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(right, padding=(6, 6, 6, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        self._count_var = tk.StringVar(value="") if tk is not None else None
        if self._count_var is not None:
            ttk.Label(toolbar, textvariable=self._count_var, style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
        if self._show_detail_var is not None:
            ttk.Checkbutton(
                toolbar,
                text="Vis detalj-nøkler",
                variable=self._show_detail_var,
            ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Button(toolbar, text="Tøm mapping", command=self._clear_selected).grid(
            row=0, column=2, sticky="e"
        )

        brreg_tree_frame = ttk.Frame(right, padding=(6, 0, 6, 6))
        brreg_tree_frame.grid(row=1, column=0, sticky="nsew")
        brreg_tree_frame.columnconfigure(0, weight=1)
        brreg_tree_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            brreg_tree_frame,
            columns=_BRREG_COLUMNS,
            show="headings",
            selectmode="browse",
        )
        tree.grid(row=0, column=0, sticky="nsew")
        for col in _BRREG_COLUMNS:
            tree.heading(
                col,
                text=_BRREG_HEADINGS[col],
                command=lambda c=col: self._on_brreg_sort(c),
            )
            tree.column(col, width=_BRREG_WIDTHS[col], anchor="w")
        try:
            tree.tag_configure("mapped", background="#e8f5e9")
            # Diskret grå for detalj-rader — signaliserer at BRREG's åpne API
            # sjelden har verdi her uten å skrike i UI.
            tree.tag_configure("detail", foreground="#808080")
        except Exception:
            pass
        yscroll = ttk.Scrollbar(brreg_tree_frame, orient="vertical", command=tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=yscroll.set)
        try:
            tree.bind("<<TreeviewSelect>>", lambda _e: self._on_brreg_select(), add="+")
            tree.bind("<Delete>", lambda _e: self._clear_selected(), add="+")
            tree.bind("<BackSpace>", lambda _e: self._clear_selected(), add="+")
        except Exception:
            pass
        self._tree = tree

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, padding=(8, 4, 8, 8))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        if self._status_var is not None:
            ttk.Label(footer, textvariable=self._status_var, style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )

    # ------------------------------------------------------------------
    # Datalogikk
    # ------------------------------------------------------------------
    def _rebuild_regnr_index(self) -> None:
        self._regnr_to_navn = {regnr: navn for regnr, navn in self._regnskapslinjer}

    def _refresh_rl_tree(self) -> None:
        tree = getattr(self, "_rl_tree", None)
        if tree is None:
            return
        query = ""
        if self._rl_search_var is not None:
            query = str(self._rl_search_var.get() or "").strip().lower()
        try:
            for item in tree.get_children(""):
                tree.delete(item)
        except Exception:
            pass
        rows: list[tuple[int, str]] = []
        for regnr, navn in self._regnskapslinjer:
            if query:
                if query not in str(regnr) and query not in navn.lower():
                    continue
            rows.append((regnr, navn))
        col, desc = self._rl_sort
        if col == "navn":
            rows.sort(key=lambda r: r[1].lower(), reverse=desc)
        else:
            rows.sort(key=lambda r: r[0], reverse=desc)
        for regnr, navn in rows:
            try:
                tree.insert("", "end", iid=f"rl:{regnr}", values=(regnr, navn))
            except Exception:
                continue
        self._rl_rows_in_tree = rows
        self._update_rl_heading_arrows()

    def _refresh_brreg_tree(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        selected = self._selected_brreg_key
        try:
            for item in tree.get_children(""):
                tree.delete(item)
        except Exception:
            pass
        show_detail = (
            bool(self._show_detail_var.get())
            if self._show_detail_var is not None else False
        )
        mapped_count = 0
        visible_total = 0
        hidden_mapped_detail = 0
        rows: list[tuple[str, str, str, str, str, int | None, tuple[str, ...]]] = []
        for key, description in self._brreg_keys:
            avail = brreg_rl_comparison.availability(key)
            regnr = self._mapping.get(key)
            if avail == "detail" and not show_detail:
                # Tell skjulte detalj-mappinger så brukeren ikke "mister" dem
                # fra bevisstheten — mapping lagres fortsatt ved save().
                if regnr is not None:
                    hidden_mapped_detail += 1
                continue
            visible_total += 1
            regnr_txt = str(regnr) if regnr is not None else ""
            rl_name = self._regnr_to_navn.get(regnr, "") if regnr is not None else ""
            avail_txt = _AVAILABILITY_TEXT.get(avail, avail)
            tags: tuple[str, ...] = ()
            if regnr is not None:
                tags = tags + ("mapped",)
                mapped_count += 1
            if avail == "detail":
                tags = tags + ("detail",)
            rows.append((key, description, avail_txt, regnr_txt, rl_name, regnr, tags))
        col, desc = self._brreg_sort

        def _sort_key(item: tuple[str, str, str, str, str, int | None, tuple[str, ...]]):
            key, description, avail_txt, regnr_txt, rl_name, regnr, _ = item
            if col == "regnr":
                # Umappede (None) til slutt ved ascending, først ved descending
                return (regnr is None, regnr if regnr is not None else 0)
            if col == "description":
                return description.lower()
            if col == "rl_name":
                return (rl_name == "", rl_name.lower())
            if col == "availability":
                # Sum før Detalj ved ascending
                return (avail_txt, key.lower())
            return key.lower()

        rows.sort(key=_sort_key, reverse=desc)
        for key, description, avail_txt, regnr_txt, rl_name, _regnr, tags in rows:
            try:
                tree.insert(
                    "", "end", iid=key,
                    values=(key, description, avail_txt, regnr_txt, rl_name),
                    tags=tags,
                )
            except Exception:
                continue
        if self._count_var is not None:
            if show_detail:
                text = f"{mapped_count} av {visible_total} mappet"
            else:
                text = f"{mapped_count} av {visible_total} sum-nøkler mappet"
                if hidden_mapped_detail:
                    text += f" (+{hidden_mapped_detail} skjult detalj)"
            self._count_var.set(text)
        self._update_brreg_heading_arrows()
        if selected and tree.exists(selected):
            try:
                tree.selection_set(selected)
                tree.focus(selected)
                tree.see(selected)
            except Exception:
                pass
        else:
            children = tree.get_children("")
            if children:
                first = str(children[0])
                self._selected_brreg_key = first
                try:
                    tree.selection_set(first)
                    tree.focus(first)
                except Exception:
                    pass

    def _update_brreg_row(self, brreg_key: str) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        if not tree.exists(brreg_key):
            # Raden er skjult (detalj-nøkkel, detaljer av); oppdater likevel
            # counter slik at bulk-endringer vises riktig.
            self._refresh_counter()
            return
        regnr = self._mapping.get(brreg_key)
        regnr_txt = str(regnr) if regnr is not None else ""
        rl_name = self._regnr_to_navn.get(regnr, "") if regnr is not None else ""
        description = next(
            (desc for key, desc in self._brreg_keys if key == brreg_key),
            "",
        )
        avail = brreg_rl_comparison.availability(brreg_key)
        avail_txt = _AVAILABILITY_TEXT.get(avail, avail)
        tags: tuple[str, ...] = ()
        if regnr is not None:
            tags = tags + ("mapped",)
        if avail == "detail":
            tags = tags + ("detail",)
        try:
            tree.item(
                brreg_key,
                values=(brreg_key, description, avail_txt, regnr_txt, rl_name),
                tags=tags,
            )
        except Exception:
            pass
        self._refresh_counter()

    def _refresh_counter(self) -> None:
        if self._count_var is None:
            return
        show_detail = (
            bool(self._show_detail_var.get())
            if self._show_detail_var is not None else False
        )
        visible_total = 0
        mapped_count = 0
        hidden_mapped_detail = 0
        for key, _ in self._brreg_keys:
            avail = brreg_rl_comparison.availability(key)
            is_mapped = key in self._mapping
            if avail == "detail" and not show_detail:
                if is_mapped:
                    hidden_mapped_detail += 1
                continue
            visible_total += 1
            if is_mapped:
                mapped_count += 1
        if show_detail:
            text = f"{mapped_count} av {visible_total} mappet"
        else:
            text = f"{mapped_count} av {visible_total} sum-nøkler mappet"
            if hidden_mapped_detail:
                text += f" (+{hidden_mapped_detail} skjult detalj)"
        self._count_var.set(text)

    def _update_rl_heading_arrows(self) -> None:
        tree = getattr(self, "_rl_tree", None)
        if tree is None:
            return
        col, desc = self._rl_sort
        arrow = " ▼" if desc else " ▲"
        headings = {"regnr": "Regnr", "navn": "Regnskapslinje"}
        for c, base in headings.items():
            try:
                tree.heading(c, text=base + (arrow if c == col else ""))
            except Exception:
                pass

    def _update_brreg_heading_arrows(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        col, desc = self._brreg_sort
        arrow = " ▼" if desc else " ▲"
        for c in _BRREG_COLUMNS:
            base = _BRREG_HEADINGS[c]
            try:
                tree.heading(c, text=base + (arrow if c == col else ""))
            except Exception:
                pass

    def _on_rl_sort(self, column: str) -> None:
        current_col, current_desc = self._rl_sort
        if current_col == column:
            self._rl_sort = (column, not current_desc)
        else:
            self._rl_sort = (column, False)
        self._refresh_rl_tree()

    def _on_brreg_sort(self, column: str) -> None:
        current_col, current_desc = self._brreg_sort
        if current_col == column:
            self._brreg_sort = (column, not current_desc)
        else:
            self._brreg_sort = (column, False)
        self._refresh_brreg_tree()

    # ------------------------------------------------------------------
    # Event-handlers
    # ------------------------------------------------------------------
    def _on_brreg_select(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        self._selected_brreg_key = str(selection[0])

    def _on_rl_activate(self) -> None:
        if not self._selected_brreg_key:
            if self._status_var is not None:
                self._status_var.set("Marker en BRREG-linje til høyre først.")
            return
        tree = getattr(self, "_rl_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        iid = str(selection[0])
        if not iid.startswith("rl:"):
            return
        try:
            regnr = int(iid[3:])
        except ValueError:
            return
        brreg_key = self._selected_brreg_key
        self._mapping[brreg_key] = regnr
        self._update_brreg_row(brreg_key)
        if self._status_var is not None:
            navn = self._regnr_to_navn.get(regnr, "")
            self._status_var.set(f"{brreg_key} → {regnr} {navn} (ikke lagret)")
        # Hopp videre til neste umappede BRREG-linje for rask bulk-mapping
        self._focus_next_unmapped_brreg()

    def _focus_next_unmapped_brreg(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        children = list(tree.get_children(""))
        if not children:
            return
        try:
            idx = children.index(self._selected_brreg_key)
        except ValueError:
            idx = -1
        for offset in range(1, len(children) + 1):
            nxt = children[(idx + offset) % len(children)]
            key = str(nxt)
            if key == self._selected_brreg_key:
                break
            if key not in self._mapping:
                self._selected_brreg_key = key
                try:
                    tree.selection_set(key)
                    tree.focus(key)
                    tree.see(key)
                except Exception:
                    pass
                return

    def _clear_selected(self) -> None:
        if not self._selected_brreg_key:
            return
        if self._selected_brreg_key not in self._mapping:
            return
        self._mapping.pop(self._selected_brreg_key, None)
        self._update_brreg_row(self._selected_brreg_key)
        if self._status_var is not None:
            self._status_var.set(
                f"Fjernet mapping for {self._selected_brreg_key} (ikke lagret)"
            )

    def _suggest_from_aliases(self) -> None:
        if self._regnskapslinjer_df is None:
            if self._status_var is not None:
                self._status_var.set("Fant ingen RL-struktur å foreslå fra.")
            return
        suggestions = brreg_mapping_config.suggest_mapping_from_aliases(
            self._regnskapslinjer_df
        )
        added = 0
        for key, regnr in suggestions.items():
            if key in self._mapping:
                continue
            self._mapping[key] = int(regnr)
            added += 1
            self._update_brreg_row(key)
        if self._status_var is not None:
            if added == 0:
                self._status_var.set(
                    "Ingen nye forslag — alle alias-treff er allerede mappet."
                )
            else:
                self._status_var.set(
                    f"Pre-fylte {added} mapping(er) fra alias-match (ikke lagret)."
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reload(self) -> None:
        self._mapping = brreg_mapping_config.load_brreg_rl_mapping()
        self._brreg_keys = brreg_mapping_config.list_brreg_keys()
        self._regnskapslinjer, self._regnskapslinjer_df = _load_regnskapslinjer()
        self._rebuild_regnr_index()
        if self._path_var is not None:
            self._path_var.set(str(brreg_mapping_config.resolve_brreg_mapping_path()))
        if self._status_var is not None:
            self._status_var.set("")
        if self._rl_search_var is not None:
            self._rl_search_var.set("")
        self._refresh_rl_tree()
        self._refresh_brreg_tree()

    def save(self) -> None:
        try:
            saved_path = brreg_mapping_config.save_brreg_rl_mapping(self._mapping)
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(str(saved_path))
        if self._status_var is not None:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._status_var.set(f"Lagret {ts} til {saved_path}.")

    # ------------------------------------------------------------------
    # Forhåndsvisning
    # ------------------------------------------------------------------
    def _show_preview(self) -> None:
        if tk is None or ttk is None:
            return
        mapped = [
            (
                key,
                desc,
                _AVAILABILITY_TEXT.get(
                    brreg_rl_comparison.availability(key),
                    brreg_rl_comparison.availability(key),
                ),
                self._mapping[key],
                self._regnr_to_navn.get(self._mapping[key], ""),
            )
            for key, desc in self._brreg_keys
            if key in self._mapping
        ]
        unmapped = [
            (
                key,
                desc,
                _AVAILABILITY_TEXT.get(
                    brreg_rl_comparison.availability(key),
                    brreg_rl_comparison.availability(key),
                ),
            )
            for key, desc in self._brreg_keys
            if key not in self._mapping
        ]
        try:
            top = tk.Toplevel(self)
            top.title("BRREG-mapping: forhåndsvisning")
            top.geometry("760x520")
        except Exception:
            return
        container = ttk.Frame(top, padding=8)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=f"{len(mapped)} mappet · {len(unmapped)} uten mapping",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        tab_mapped = ttk.Frame(notebook, padding=4)
        tab_unmapped = ttk.Frame(notebook, padding=4)
        notebook.add(tab_mapped, text=f"Mappet ({len(mapped)})")
        notebook.add(tab_unmapped, text=f"Uten mapping ({len(unmapped)})")

        for target, cols, rows in (
            (
                tab_mapped,
                ("BRREG-nøkkel", "Beskrivelse", "Kilde", "Regnr", "RL-navn"),
                [(k, d, a, str(r), n) for k, d, a, r, n in mapped],
            ),
            (
                tab_unmapped,
                ("BRREG-nøkkel", "Beskrivelse", "Kilde"),
                [(k, d, a) for k, d, a in unmapped],
            ),
        ):
            tree = ttk.Treeview(target, columns=cols, show="headings", height=16)
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=180, anchor="w")
            for row in rows:
                try:
                    tree.insert("", "end", values=row)
                except Exception:
                    continue
            yscroll = ttk.Scrollbar(target, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=yscroll.set)
            tree.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")

        ttk.Button(container, text="Lukk", command=top.destroy).pack(
            side="right", pady=(6, 0)
        )
