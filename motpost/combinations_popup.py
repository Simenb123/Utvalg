from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Set

import tkinter as tk
from tkinter import ttk

import pandas as pd

from bilag_drilldialog import BilagDrillDialog
from motpost.combinations import build_bilag_to_motkonto_combo
from formatting import fmt_amount, fmt_date

from motpost.combo_workflow import (
    STATUS_EXPECTED,
    STATUS_NEUTRAL,
    STATUS_OUTLIER,
    apply_combo_status,
    combo_display_name,
    normalize_combo_status,
    normalize_direction,
    status_label,
)
from motpost.utils import _bilag_str, _clean_name, _konto_str, _safe_float
from ui_treeview_sort import enable_treeview_sorting

@dataclass(frozen=True)
class _ComboSelection:
    combo: str
    selected_account: str = ""


class _MotkontoCombinationsPopup(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        df_combos: pd.DataFrame,
        df_per_selected: pd.DataFrame,
        *,
        title: str,
        summary: str | None = None,
        selected_accounts: Sequence[str],
        konto_navn_map: Mapping[str, str],
        df_scope: pd.DataFrame,
        outlier_motkonto: Optional[Set[str]] = None,
        selected_direction: Optional[str] = None,
        outlier_combinations: Optional[Set[str]] = None,
        combo_status_map: Optional[dict[str, str]] = None,
        on_outlier_changed: Optional[Callable[[Set[str]], None]] = None,
        on_export_excel: Optional[Callable[[object], None]] = None,
    ):
        super().__init__(parent)

        self.title(title)
        self._summary = (summary or "").strip()
        self.transient(parent)

        # Normalize / cache inputs
        self._konto_navn_map = {str(k): _clean_name(v) for k, v in (konto_navn_map or {}).items()}
        self._selected_accounts = [_konto_str(a) for a in (selected_accounts or []) if _konto_str(a)]
        self._selected_accounts_set = set(self._selected_accounts)
        self._selected_direction = normalize_direction(selected_direction)

        self._df_scope = df_scope.copy() if df_scope is not None else pd.DataFrame()
        if "Bilag_str" not in self._df_scope.columns and "Bilag" in self._df_scope.columns:
            self._df_scope["Bilag_str"] = self._df_scope["Bilag"].map(_bilag_str)
        if "Konto_str" not in self._df_scope.columns and "Konto" in self._df_scope.columns:
            self._df_scope["Konto_str"] = self._df_scope["Konto"].map(_konto_str)
        if "Beløp_num" not in self._df_scope.columns:
            if "Beløp" in self._df_scope.columns:
                self._df_scope["Beløp_num"] = self._df_scope["Beløp"].map(_safe_float)
            else:
                self._df_scope["Beløp_num"] = 0.0

        # Auto outliers (motkonto) – shown in df_combos "Outlier" column if present.
        self._outlier_motkonto = set(str(x) for x in (outlier_motkonto or set()))

        # Status mapping (mutable, should survive refresh/sort).
        # key: combo-string (samme som i kolonnen "Kombinasjon")
        # value: '', 'expected' eller 'outlier'
        self._combo_status_map: dict[str, str] = combo_status_map if combo_status_map is not None else {}

        # Backwards compatible: a set of outlier combos. If provided, keep it in sync with status_map.
        self._outlier_combinations_ref: Set[str] = outlier_combinations if outlier_combinations is not None else set()
        for c in list(self._outlier_combinations_ref):
            # If caller has a legacy outlier set, translate to status_map (do not overwrite explicit expected).
            if normalize_combo_status(self._combo_status_map.get(c)) != STATUS_EXPECTED:
                self._combo_status_map[c] = STATUS_OUTLIER
        self._sync_legacy_outlier_set()

        self._on_outlier_changed = on_outlier_changed
        self._on_export_excel = on_export_excel

        # Bilag -> combo mapping (and reverse mapping) for quick drilldown
        self._bilag_to_combo = build_bilag_to_motkonto_combo(self._df_scope, self._selected_accounts)
        self._combo_to_bilag: dict[str, list[str]] = {}
        for b, c in self._bilag_to_combo.items():
            self._combo_to_bilag.setdefault(c, []).append(b)

        self._current_selection: Optional[_ComboSelection] = None
        self._bilag_rows_cache: Optional[pd.DataFrame] = None

        # UI vars
        self._vis_var = tk.IntVar(value=200)

        # UI state: "utvid" (toggle maximize) – lagrer geometri for å kunne gå tilbake.
        self._is_zoomed: bool = False
        self._prev_geometry: str | None = None

        # Cache for summering i tabeller (ikke parse formaterte strenger fra treeview)
        self._combo_sum_map: dict[str, float] = {}
        self._combo_bilag_count_map: dict[str, int] = {}
        self._combo_total_sum: float = 0.0

        # Layout
        self.geometry("1100x720")
        try:
            self.minsize(900, 600)
            self.resizable(True, True)
        except Exception:
            pass

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        if self._summary:
            lbl_summary = ttk.Label(container, text=self._summary, anchor="w", justify="left")
            lbl_summary.pack(fill=tk.X, padx=2, pady=(0, 8))

        # Top: notebook with combos + per-selected
        nb = ttk.Notebook(container)
        nb.pack(fill=tk.BOTH, expand=True)

        frame_all = ttk.Frame(nb)
        frame_per = ttk.Frame(nb)
        nb.add(frame_all, text="Alle valgte kontoer")
        nb.add(frame_per, text="Per valgt konto")

        # --- All combos tab ---
        top_bar = ttk.Frame(frame_all)
        top_bar.pack(fill=tk.X, padx=4, pady=(4, 0))

        ttk.Label(top_bar, text="Status:").pack(side=tk.LEFT)

        # Fargede knapper (bruk tk.Button for å sikre bakgrunnsfarge i Windows TTK-tema)
        btn_expected = tk.Button(
            top_bar,
            text="Marker som forventet",
            command=lambda: self._set_status_selected(STATUS_EXPECTED),
            bg="#C6EFCE",
            activebackground="#C6EFCE",
            relief=tk.RAISED,
            borderwidth=1,
        )
        btn_expected.pack(side=tk.LEFT, padx=(6, 0))

        btn_outlier = tk.Button(
            top_bar,
            text="Marker som outlier",
            command=lambda: self._set_status_selected(STATUS_OUTLIER),
            bg="#FFF2CC",
            activebackground="#FFF2CC",
            relief=tk.RAISED,
            borderwidth=1,
        )
        btn_outlier.pack(side=tk.LEFT, padx=(6, 0))

        btn_reset = ttk.Button(
            top_bar,
            text="Nullstill markering",
            command=lambda: self._set_status_selected(STATUS_NEUTRAL),
        )
        btn_reset.pack(side=tk.LEFT, padx=(6, 0))

        # Snarveier-hint (ikke for mye tekst, men nok til at det oppdages)
        ttk.Label(
            top_bar,
            text="Snarveier: Ctrl+E=Forventet, Ctrl+O=Outlier, Ctrl+0=Nullstill",
        ).pack(side=tk.LEFT, padx=(12, 0))

        btn_close = ttk.Button(top_bar, text="Lukk", command=self.destroy)
        btn_close.pack(side=tk.RIGHT)

        btn_expand = ttk.Button(top_bar, text="□", width=3, command=self._toggle_zoom)
        btn_expand.pack(side=tk.RIGHT, padx=(0, 6))

        btn_export = ttk.Button(top_bar, text="Eksporter Excel", command=self._export_excel)
        btn_export.pack(side=tk.RIGHT, padx=(0, 6))

        self._tree_all = ttk.Treeview(
            frame_all,
            columns=(
                "Kombinasjon #",
                "Kombinasjon",
                "Kombinasjon (navn)",
                "Antall bilag",
                "Sum valgte kontoer",
                "% andel bilag",
                "Outlier",
                "Status",
            ),
            show="headings",
            selectmode="extended",
        )
        for c in self._tree_all["columns"]:
            self._tree_all.heading(c, text=c)
            if c == "Kombinasjon":
                w, anchor = 180, tk.W
            elif c == "Kombinasjon (navn)":
                w, anchor = 420, tk.W
            elif c == "Status":
                w, anchor = 110, tk.W
            else:
                w, anchor = 120, tk.W
            self._tree_all.column(c, width=w, anchor=anchor)
        self._tree_all.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        enable_treeview_sorting(self._tree_all)

        # Summering under kombinasjonstabellen
        summary_bar = ttk.Frame(frame_all)
        summary_bar.pack(fill=tk.X, padx=4, pady=(0, 6))
        self._lbl_combo_summary = ttk.Label(summary_bar, text="")
        self._lbl_combo_summary.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Kontekstmeny (høyreklikk) for rask markering
        self._menu_status = tk.Menu(self, tearoff=False)
        self._menu_status.add_command(label="Marker som forventet", command=lambda: self._set_status_selected(STATUS_EXPECTED))
        self._menu_status.add_command(label="Marker som outlier", command=lambda: self._set_status_selected(STATUS_OUTLIER))
        self._menu_status.add_separator()
        self._menu_status.add_command(label="Nullstill markering", command=lambda: self._set_status_selected(STATUS_NEUTRAL))

        def _on_tree_right_click(event) -> None:
            try:
                iid = self._tree_all.identify_row(event.y)
                if iid:
                    # Sikre at raden under mus er med i selection før meny
                    if iid not in self._tree_all.selection():
                        self._tree_all.selection_set(iid)
                        self._tree_all.focus(iid)
                self._menu_status.tk_popup(event.x_root, event.y_root)
            finally:
                try:
                    self._menu_status.grab_release()
                except Exception:
                    pass

        self._tree_all.bind("<Button-3>", _on_tree_right_click)

        # Row tags (visuals)
        try:
            self._tree_all.tag_configure("expected", background="#C6EFCE")  # light green
            self._tree_all.tag_configure("outlier", background="#FFF2CC")  # light yellow
        except Exception:
            # Themes may block custom backgrounds (best effort)
            pass

        # Cache for summering (bruk raw df for numerikk)
        try:
            self._combo_sum_map.clear()
            self._combo_bilag_count_map.clear()
            if df_combos is not None and not getattr(df_combos, "empty", False):
                for _, r0 in df_combos.iterrows():
                    c0 = str(r0.get("Kombinasjon", "") or "").strip()
                    if not c0:
                        continue
                    try:
                        self._combo_sum_map[c0] = float(r0.get("Sum valgte kontoer", 0.0) or 0.0)
                    except Exception:
                        self._combo_sum_map[c0] = 0.0
                    try:
                        self._combo_bilag_count_map[c0] = int(r0.get("Antall bilag", 0) or 0)
                    except Exception:
                        self._combo_bilag_count_map[c0] = 0
            self._combo_total_sum = float(sum(self._combo_sum_map.values())) if self._combo_sum_map else 0.0
        except Exception:
            self._combo_total_sum = 0.0

        # Populate all combos (display)
        df_disp = _format_combo_df_for_display(df_combos)
        for _, r in df_disp.iterrows():
            combo = str(r.get("Kombinasjon", "") or "").strip()
            combo_name = combo_display_name(combo, self._konto_navn_map) if combo else ""
            status_code = normalize_combo_status(self._combo_status_map.get(combo, ""))
            status_txt = status_label(status_code)
            row_dict = {**r.to_dict(), "Kombinasjon (navn)": combo_name, "Status": status_txt}
            vals = [row_dict.get(c, "") for c in self._tree_all["columns"]]
            tags = ()
            if status_code == STATUS_EXPECTED:
                tags = ("expected",)
            elif status_code == STATUS_OUTLIER:
                tags = ("outlier",)
            self._tree_all.insert("", tk.END, values=vals, tags=tags)

        # Init summering (ingen rader markert som default)
        self._update_combo_selection_summary()

        self._tree_all.bind("<<TreeviewSelect>>", self._on_combo_selected)
        self._tree_all.bind("<Double-1>", self._on_combo_doubleclick)

        # --- Per-selected tab ---
        self._tree_per = ttk.Treeview(
            frame_per,
            columns=(
                "Valgt konto",
                "Kombinasjon",
                "Kombinasjon (navn)",
                "Antall bilag",
                "Sum valgte kontoer",
                "% andel bilag",
            ),
            show="headings",
            selectmode="browse",
        )
        for c in self._tree_per["columns"]:
            self._tree_per.heading(c, text=c)
            if c == "Kombinasjon":
                w = 180
            elif c == "Kombinasjon (navn)":
                w = 420
            else:
                w = 140
            self._tree_per.column(c, width=w, anchor=tk.W)
        self._tree_per.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        enable_treeview_sorting(self._tree_per)

        for _, r in (df_per_selected if df_per_selected is not None else pd.DataFrame()).iterrows():
            combo = str(r.get("Kombinasjon", "") or "").strip()
            combo_name = combo_display_name(combo, self._konto_navn_map) if combo else ""
            row_dict = {**r.to_dict(), "Kombinasjon (navn)": combo_name}
            vals = [row_dict.get(c, "") for c in self._tree_per["columns"]]
            self._tree_per.insert("", tk.END, values=vals)

        self._tree_per.bind("<<TreeviewSelect>>", self._on_per_selected_selected)
        self._tree_per.bind("<Double-1>", self._on_per_selected_doubleclick)

        # Drilldown area (bottom of container, outside notebook)
        drill_container = ttk.Frame(container)
        drill_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(6, 0))

        self._lbl_combo = ttk.Label(drill_container, text="Velg en kombinasjon for drilldown")
        self._lbl_combo.pack(fill=tk.X, pady=(0, 6))

        paned = ttk.PanedWindow(drill_container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: distributions (motposts + selected accounts) in a notebook
        frame_left = ttk.LabelFrame(paned, text="Fordeling (sum)")
        paned.add(frame_left, weight=1)

        left_nb = ttk.Notebook(frame_left)
        left_nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tab_mot = ttk.Frame(left_nb)
        tab_sel = ttk.Frame(left_nb)
        left_nb.add(tab_mot, text="Motposter")
        left_nb.add(tab_sel, text="Valgte kontoer")

        # Motposts sum tree
        dist_cols = ("Konto", "Kontonavn", "Sum", "Andel")
        self._tree_mot = ttk.Treeview(tab_mot, columns=dist_cols, show="headings", height=10)
        self._tree_mot.heading("Konto", text="Konto")
        self._tree_mot.heading("Kontonavn", text="Kontonavn")
        self._tree_mot.heading("Sum", text="Sum")
        self._tree_mot.heading("Andel", text="% av valgt")
        self._tree_mot.column("Konto", width=80, anchor=tk.W, stretch=False)
        self._tree_mot.column("Kontonavn", width=260, anchor=tk.W)
        self._tree_mot.column("Sum", width=120, anchor=tk.E, stretch=False)
        self._tree_mot.column("Andel", width=90, anchor=tk.E, stretch=False)
        self._tree_mot.pack(fill=tk.BOTH, expand=True)
        enable_treeview_sorting(self._tree_mot)

        # Summering under motposter-tabell
        self._lbl_mot_total = ttk.Label(tab_mot, text="")
        self._lbl_mot_total.pack(fill=tk.X, padx=2, pady=(2, 0))

        # Tag for "valgt, motsatt"
        try:
            self._tree_mot.tag_configure("valgt_motsatt", background="#FCE4D6")  # light orange
        except Exception:
            pass

        # Selected accounts sum tree
        self._tree_sel = ttk.Treeview(tab_sel, columns=dist_cols, show="headings", height=10)
        self._tree_sel.heading("Konto", text="Konto")
        self._tree_sel.heading("Kontonavn", text="Kontonavn")
        self._tree_sel.heading("Sum", text="Sum")
        self._tree_sel.heading("Andel", text="% av valgt")
        self._tree_sel.column("Konto", width=80, anchor=tk.W, stretch=False)
        self._tree_sel.column("Kontonavn", width=260, anchor=tk.W)
        self._tree_sel.column("Sum", width=120, anchor=tk.E, stretch=False)
        self._tree_sel.column("Andel", width=90, anchor=tk.E, stretch=False)
        self._tree_sel.pack(fill=tk.BOTH, expand=True)
        enable_treeview_sorting(self._tree_sel)

        # Summering under valgte-kontoer-tabell
        self._lbl_sel_total = ttk.Label(tab_sel, text="")
        self._lbl_sel_total.pack(fill=tk.X, padx=2, pady=(2, 0))

        # Help text (revisjonsforklaring)
        help_text = (
            "Forklaring: Når retning=Kredit på valgte kontoer, kan noen bilag inneholde debetlinjer på "
            "de samme valgte kontoene (korrigeringer). Disse vises som 'valgt, motsatt' i motpostfordelingen "
            "slik at bilagene kan avstemmes."
        )
        ttk.Label(frame_left, text=help_text, wraplength=360, justify="left").pack(fill=tk.X, padx=6, pady=(0, 6))

        # Right: bilag list with vis control
        frame_right = ttk.LabelFrame(paned, text="Bilag i kombinasjon")
        paned.add(frame_right, weight=3)

        right_top = ttk.Frame(frame_right)
        right_top.pack(fill=tk.X, padx=4, pady=(4, 0))

        ttk.Label(right_top, text="Vis:").pack(side=tk.LEFT)
        spn = ttk.Spinbox(
            right_top,
            from_=10,
            to=100000,
            increment=50,
            width=7,
            textvariable=self._vis_var,
            command=self._apply_bilag_limit,
        )
        spn.pack(side=tk.LEFT, padx=(4, 0))
        spn.bind("<Return>", lambda e: self._apply_bilag_limit())

        self._lbl_vis_info = ttk.Label(right_top, text="")
        self._lbl_vis_info.pack(side=tk.LEFT, padx=10)

        btn_drill = ttk.Button(right_top, text="Drilldown bilag", command=self._drilldown_bilag)
        btn_drill.pack(side=tk.RIGHT)

        self._tree_bilag = ttk.Treeview(
            frame_right,
            columns=("Bilag", "Dato", "Tekst", "Beløp (valgte kontoer)", "Motbeløp", "Kontoer i bilag"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for c in self._tree_bilag["columns"]:
            self._tree_bilag.heading(c, text=c)
            if c in ("Bilag", "Dato"):
                w, anchor = 90, tk.W
            elif c in ("Beløp (valgte kontoer)", "Motbeløp"):
                w, anchor = 140, tk.E
            elif c == "Kontoer i bilag":
                w, anchor = 110, tk.E
            else:
                w, anchor = 360, tk.W
            self._tree_bilag.column(c, width=w, anchor=anchor)
        self._tree_bilag.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        enable_treeview_sorting(self._tree_bilag)

        # Convenience: double-click / Enter opens bilagsdrill
        def _on_bilag_dbl_click(event) -> None:
            region = self._tree_bilag.identify_region(event.x, event.y)
            if region not in ("cell", "tree"):
                return
            self._drilldown_bilag()

        self._tree_bilag.bind("<Double-1>", _on_bilag_dbl_click)
        self._tree_bilag.bind("<Return>", lambda e: self._drilldown_bilag())

        # Hurtigtaster (markering + utvid)
        self._bind_hotkeys()

    # ---- Status handling ----

    def _sync_legacy_outlier_set(self) -> None:
        """Hold legacy outlier-sett i sync med status_map (kun outlier)."""
        if self._outlier_combinations_ref is None:
            return
        out = {k for k, v in self._combo_status_map.items() if normalize_combo_status(v) == STATUS_OUTLIER}
        # Muter settet (bevar referanse)
        try:
            self._outlier_combinations_ref.clear()
            self._outlier_combinations_ref.update(out)
        except Exception:
            pass

    def _set_status_selected(self, status_code: str) -> None:
        """Setter status for *alle* markerte rader i kombinasjonslisten."""
        try:
            items = list(self._tree_all.selection())
        except Exception:
            items = []

        if not items:
            # Fallback: fokusert rad
            try:
                f = self._tree_all.focus()
                if f:
                    items = [f]
            except Exception:
                items = []

        if not items:
            return

        item_combo_pairs: list[tuple[str, str]] = []
        for item in items:
            try:
                values = self._tree_all.item(item, "values")
            except Exception:
                continue
            row = {c: v for c, v in zip(self._tree_all["columns"], values)}
            combo = str(row.get("Kombinasjon", "") or "").strip()
            if combo:
                item_combo_pairs.append((item, combo))

        if not item_combo_pairs:
            return

        combos = [c for _, c in item_combo_pairs]

        # Oppdater mapping (in-place)
        apply_combo_status(self._combo_status_map, combos, status_code)

        # Sync legacy outlier set + callbacks
        self._sync_legacy_outlier_set()
        if self._on_outlier_changed:
            self._on_outlier_changed(set(self._outlier_combinations_ref))

        # Update tree rows (Status column + tag)
        for item, combo in item_combo_pairs:
            self._apply_status_to_tree_item(item, combo)

        self._update_combo_selection_summary()

    def _apply_status_to_tree_item(self, item: str, combo: str) -> None:
        status_code = normalize_combo_status(self._combo_status_map.get(combo, ""))
        status_txt = status_label(status_code)

        values = list(self._tree_all.item(item, "values"))
        try:
            idx = self._tree_all["columns"].index("Status")
            if idx < len(values):
                values[idx] = status_txt
            self._tree_all.item(item, values=values)
        except Exception:
            pass

        tags = ()
        if status_code == STATUS_EXPECTED:
            tags = ("expected",)
        elif status_code == STATUS_OUTLIER:
            tags = ("outlier",)
        try:
            self._tree_all.item(item, tags=tags)
        except Exception:
            pass

    def _update_combo_selection_summary(self) -> None:
        """Oppdaterer teksten under kombinasjonstabellen.

        Viser antall markerte rader og sum av "Sum valgte kontoer" for markeringen.
        """
        try:
            items = list(self._tree_all.selection())
        except Exception:
            items = []

        combos: list[str] = []
        for item in items:
            try:
                values = self._tree_all.item(item, "values")
            except Exception:
                continue
            row = {c: v for c, v in zip(self._tree_all["columns"], values)}
            combo = str(row.get("Kombinasjon", "") or "").strip()
            if combo:
                combos.append(combo)

        n = len(combos)
        sum_marked = float(sum(self._combo_sum_map.get(c, 0.0) for c in combos)) if combos else 0.0

        # Statusfordeling blant de markerte
        expected_cnt = 0
        outlier_cnt = 0
        for c in combos:
            s = normalize_combo_status(self._combo_status_map.get(c, ""))
            if s == STATUS_EXPECTED:
                expected_cnt += 1
            elif s == STATUS_OUTLIER:
                outlier_cnt += 1

        total = float(self._combo_total_sum or 0.0)

        base = f"Markert: {n} rader | Sum valgte kontoer (markert): {fmt_amount(sum_marked)} | Total: {fmt_amount(total)}"
        if n:
            base += f" | Forventet: {expected_cnt} | Outlier: {outlier_cnt}"

        try:
            self._lbl_combo_summary.config(text=base)
        except Exception:
            pass

    def _bind_hotkeys(self) -> None:
        """Binder hurtigtaster for rask markering og utvid."""

        def _bind(widget: tk.Misc, sequence: str, func: Callable[[], None]) -> None:
            try:
                widget.bind(sequence, lambda _e: (func(), "break")[1])
            except Exception:
                pass

        # Markering
        _bind(self, "<Control-e>", lambda: self._set_status_selected(STATUS_EXPECTED))
        _bind(self, "<Control-o>", lambda: self._set_status_selected(STATUS_OUTLIER))
        _bind(self, "<Control-0>", lambda: self._set_status_selected(STATUS_NEUTRAL))

        # Utvid (maximer/normal)
        _bind(self, "<F11>", self._toggle_zoom)

        # Praktisk: Ctrl+A markerer alle kombinasjoner (kun i kombinasjonstabellen)
        try:
            self._tree_all.bind("<Control-a>", lambda _e: (self._select_all_combos(), "break")[1])
        except Exception:
            pass

        # ESC lukker
        _bind(self, "<Escape>", lambda: self.destroy())

    def _select_all_combos(self) -> None:
        try:
            items = self._tree_all.get_children("")
            if items:
                self._tree_all.selection_set(items)
                self._tree_all.focus(items[0])
                self._tree_all.see(items[0])
        finally:
            try:
                self._update_combo_selection_summary()
            except Exception:
                pass

    def _toggle_zoom(self) -> None:
        """Toggler mellom normal størrelse og "zoomed" (Windows-maximer)."""
        try:
            if not self._is_zoomed:
                # lagre nåværende geometri slik at vi kan gå tilbake
                try:
                    self._prev_geometry = self.geometry()
                except Exception:
                    self._prev_geometry = None

                try:
                    self.state("zoomed")
                except Exception:
                    # fallback (noen Tk-builds)
                    try:
                        self.attributes("-zoomed", True)
                    except Exception:
                        pass
                self._is_zoomed = True
            else:
                try:
                    self.state("normal")
                except Exception:
                    try:
                        self.attributes("-zoomed", False)
                    except Exception:
                        pass
                if self._prev_geometry:
                    try:
                        self.geometry(self._prev_geometry)
                    except Exception:
                        pass
                self._is_zoomed = False
        finally:
            # ikke kritisk
            pass

    def _export_excel(self) -> None:
        if not self._on_export_excel:
            return
        # Prefer status_map, but fall back to legacy set if caller has old signature.
        payload = dict(self._combo_status_map)
        try:
            self._on_export_excel(payload)
        except TypeError:
            self._on_export_excel(set(self._outlier_combinations_ref))

    # ---- Event handlers ----

    def _on_combo_selected(self, _event=None):
        # Oppdater summering for multiselect
        try:
            self._update_combo_selection_summary()
        except Exception:
            pass
        item = self._tree_all.focus()
        if not item:
            return
        row = {c: v for c, v in zip(self._tree_all["columns"], self._tree_all.item(item, "values"))}
        combo = row.get("Kombinasjon", "")
        if combo:
            self._update_drilldown(_ComboSelection(combo=combo))

    def _on_combo_doubleclick(self, _event=None):
        self._on_combo_selected()

    def _on_per_selected_selected(self, _event=None):
        item = self._tree_per.focus()
        if not item:
            return
        row = {c: v for c, v in zip(self._tree_per["columns"], self._tree_per.item(item, "values"))}
        combo = row.get("Kombinasjon", "")
        konto = row.get("Valgt konto", "")
        if combo:
            self._update_drilldown(_ComboSelection(combo=combo, selected_account=konto))

    def _on_per_selected_doubleclick(self, _event=None):
        self._on_per_selected_selected()

    # ---- Drilldown calculations ----

    def _update_drilldown(self, selection: _ComboSelection) -> None:
        self._current_selection = selection
        combo_key = selection.combo

        bilag_list = self._combo_to_bilag.get(combo_key, [])
        if not bilag_list:
            self._lbl_combo.config(text=f"Kombinasjon: {combo_key} | (ingen bilag)")
            self._clear_tree(self._tree_sel)
            self._clear_tree(self._tree_mot)
            self._clear_tree(self._tree_bilag)
            self._lbl_vis_info.config(text="")
            self._bilag_rows_cache = None
            try:
                self._lbl_sel_total.config(text="")
                self._lbl_mot_total.config(text="")
            except Exception:
                pass
            return

        df_combo = self._df_scope[self._df_scope["Bilag_str"].isin(bilag_list)].copy()

        # Selection mask: selected accounts + valgt retning (kredit/debet) på disse kontoene
        sel_mask = df_combo["Konto_str"].isin(self._selected_accounts_set)
        dir_norm = normalize_direction(self._selected_direction)
        if dir_norm == "kredit":
            sel_mask = sel_mask & (df_combo["Beløp_num"] < 0)
        elif dir_norm == "debet":
            sel_mask = sel_mask & (df_combo["Beløp_num"] > 0)

        df_sel = df_combo[sel_mask].copy()
        sum_sel = float(df_sel["Beløp_num"].sum()) if not df_sel.empty else 0.0

        # Motposter = alle øvrige linjer i bilaget (inkl. poster på valgte kontoer i motsatt retning)
        df_mot = df_combo[~sel_mask].copy()
        sum_mot = float(df_mot["Beløp_num"].sum()) if not df_mot.empty else 0.0
        kontroll = sum_sel + sum_mot

        # Summering nederst i tabellene
        try:
            self._lbl_sel_total.config(text=f"Sum valgte kontoer: {fmt_amount(sum_sel)}")
            self._lbl_mot_total.config(text=f"Sum motposter: {fmt_amount(sum_mot)} | Kontroll: {fmt_amount(kontroll)}")
        except Exception:
            pass

        # Label
        dir_txt = self._selected_direction if self._selected_direction != "alle" else "netto"
        extra = f" | Per valgt konto: {selection.selected_account}" if selection.selected_account else ""
        self._lbl_combo.config(
            text=(
                f"Kombinasjon: {combo_key}{extra}\n"
                f"Bilag: {len(bilag_list)} | Sum valgte kontoer ({dir_txt}): {fmt_amount(sum_sel)}"
                f" | Sum motposter: {fmt_amount(sum_mot)} | Kontroll (valgt + mot): {fmt_amount(kontroll)}"
            )
        )

        # Populate selected accounts distribution
        self._populate_account_sum_tree(self._tree_sel, df_sel, base_sum=sum_sel)

        # Populate motposter distribution
        self._populate_account_sum_tree(self._tree_mot, df_mot, base_sum=sum_sel)

        # Bilag rows (cached) for list
        self._bilag_rows_cache = self._build_bilag_rows(df_combo, df_sel, df_mot)
        self._apply_bilag_limit()

    def _populate_account_sum_tree(
        self,
        tree: ttk.Treeview,
        df_lines: pd.DataFrame,
        base_sum: Optional[float] = None,
    ) -> None:
        """Fyller fordelingstabell (konto, kontonavn, sum, % av valgt).

        - Kontonavn hentes primært fra df (Kontonavn), ellers konto-navn-map.
        - Percent "% av valgt" beregnes som abs(Sum) / abs(base_sum) * 100 (vises med 2 desimaler).
        """
        self._clear_tree(tree)
        if df_lines is None or df_lines.empty:
            return

        # Summer per konto
        by_konto = df_lines.groupby("Konto_str", dropna=False)["Beløp_num"].sum()
        # Sorter på absoluttverdi (størst først)
        by_konto = by_konto.reindex(by_konto.abs().sort_values(ascending=False).index)

        # Kontonavn per konto (første ikke-tomme)
        name_map = {}
        if "Kontonavn" in df_lines.columns:
            for konto, s in df_lines.groupby("Konto_str", dropna=False)["Kontonavn"]:
                name = ""
                for v in s.tolist():
                    if v is None:
                        continue
                    try:
                        import pandas as _pd
                        if _pd.isna(v):
                            continue
                    except Exception:
                        pass
                    vs = str(v).strip()
                    if vs and vs.lower() != "nan":
                        name = vs
                        break
                if name:
                    name_map[str(konto)] = name

        show_pct = base_sum is not None and abs(float(base_sum)) > 1e-12

        for konto, belop in by_konto.items():
            k = str(konto)
            name = name_map.get(k) or self._konto_navn_map.get(k, "")

            tags = ()
            # Dersom vi viser "motposter" som komplementet til valgte linjer,
            # kan det dukke opp poster på valgte kontoer i motsatt retning.
            # Merk disse for å gjøre det tydelig i UI.
            if tree is self._tree_mot and k in self._selected_accounts_set:
                tags = ("valgt_motsatt",)
                if name:
                    name = f"{name} (valgt, motsatt)"
                else:
                    name = "(valgt, motsatt)"

            pct_txt = ""
            if show_pct:
                pct = (abs(float(belop)) / abs(float(base_sum))) * 100.0
                pct_txt = fmt_amount(pct, decimals=2)

            tree.insert("", tk.END, values=(k, name, fmt_amount(belop), pct_txt), tags=tags)

    def _build_bilag_rows(self, df_combo: pd.DataFrame, df_sel: pd.DataFrame, df_mot: pd.DataFrame) -> pd.DataFrame:
        """Build a per-bilag table for the current combo."""
        # Selected sum per bilag (already direction filtered)
        sel_by_bilag = df_sel.groupby("Bilag_str")["Beløp_num"].sum()

        # Mot sum per bilag (net, all directions)
        mot_by_bilag = df_mot.groupby("Bilag_str")["Beløp_num"].sum()

        # Meta
        has_date = "Dato" in df_combo.columns
        has_text = "Tekst" in df_combo.columns
        date_by_bilag = df_combo.groupby("Bilag_str")["Dato"].first() if has_date else None
        text_by_bilag = df_combo.groupby("Bilag_str")["Tekst"].first() if has_text else None
        konto_count = df_combo.groupby("Bilag_str")["Konto_str"].nunique()

        idx = sorted(df_combo["Bilag_str"].dropna().unique().tolist())
        df_rows = pd.DataFrame(index=idx)
        df_rows["Bilag"] = df_rows.index
        df_rows["Dato"] = date_by_bilag.reindex(idx) if date_by_bilag is not None else ""
        df_rows["Tekst"] = text_by_bilag.reindex(idx) if text_by_bilag is not None else ""
        df_rows["Beløp_valgt"] = sel_by_bilag.reindex(idx).fillna(0.0)
        df_rows["Motbeløp"] = mot_by_bilag.reindex(idx).fillna(0.0)
        df_rows["Kontoer"] = konto_count.reindex(idx).fillna(0).astype(int)

        # Default order: largest absolute selected amount first
        df_rows["_abs"] = df_rows["Beløp_valgt"].abs()
        df_rows = df_rows.sort_values(["_abs", "Bilag"], ascending=[False, True])
        df_rows = df_rows.drop(columns=["_abs"])
        return df_rows

    def _apply_bilag_limit(self) -> None:
        # If no current drilldown, nothing to do
        if self._bilag_rows_cache is None:
            return
        df_rows = self._bilag_rows_cache
        total = int(len(df_rows))

        try:
            limit = int(self._vis_var.get())
        except Exception:
            limit = 200

        if limit <= 0:
            limit = 200

        if limit >= total:
            df_show = df_rows
            shown = total
        else:
            df_show = df_rows.iloc[:limit]
            shown = limit

        self._lbl_vis_info.config(text=f"Viser {shown} av {total}")

        self._clear_tree(self._tree_bilag)
        for _, r in df_show.iterrows():
            self._tree_bilag.insert(
                "",
                tk.END,
                values=(
                    r["Bilag"],
                    fmt_date(r["Dato"]),
                    r["Tekst"],
                    fmt_amount(r["Beløp_valgt"]),
                    fmt_amount(r["Motbeløp"]),
                    r["Kontoer"],
                ),
            )

    def _drilldown_bilag(self):
        item = self._tree_bilag.focus()
        if not item:
            return
        values = self._tree_bilag.item(item, "values")
        if not values:
            return
        bilag = _bilag_str(values[0])
        if not bilag:
            return

        dlg = BilagDrillDialog(self, df_all=self._df_scope, title=f"Bilagsdrill - {bilag}")
        dlg.show_bilag(bilag)

    @staticmethod
    def _clear_tree(tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)


def _format_combo_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Format combo DF for display in treeview: numbers -> formatted strings."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()

    for col in ("Sum valgte kontoer",):
        if col in out.columns:
            out[col] = out[col].map(fmt_amount)

    # percentage column might be float
    if "% andel bilag" in out.columns:
        out["% andel bilag"] = out["% andel bilag"].map(
            lambda x: f"{float(x):.1f}%" if x is not None and str(x) != "" else ""
        )

    # Outlier columns: normalize
    if "Outlier" in out.columns:
        out["Outlier"] = out["Outlier"].fillna("")

    return out


def show_motkonto_combinations_popup(
    parent: tk.Misc,
    df_combos: pd.DataFrame,
    *,
    df_combo_per_selected: pd.DataFrame,
    title: str,
    summary: str | None = None,
    selected_accounts: Sequence[str],
    konto_navn_map: Mapping[str, str],
    df_scope: pd.DataFrame,
    outlier_motkonto: Optional[Set[str]] = None,
    selected_direction: Optional[str] = None,
    outlier_combinations: Optional[Set[str]] = None,
    combo_status_map: Optional[dict[str, str]] = None,
    on_outlier_changed: Optional[Callable[[Set[str]], None]] = None,
    on_export_excel: Optional[Callable[[object], None]] = None,
) -> _MotkontoCombinationsPopup:
    """Create and show the combinations popup."""
    win = _MotkontoCombinationsPopup(
        parent,
        df_combos,
        df_combo_per_selected,
        title=title,
        summary=summary,
        selected_accounts=selected_accounts,
        konto_navn_map=konto_navn_map,
        df_scope=df_scope,
        outlier_motkonto=outlier_motkonto,
        selected_direction=selected_direction,
        outlier_combinations=outlier_combinations,
        combo_status_map=combo_status_map,
        on_outlier_changed=on_outlier_changed,
        on_export_excel=on_export_excel,
    )
    win.grab_set()
    win.focus_set()
    return win
