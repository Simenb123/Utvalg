from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Callable, Mapping, Optional, Sequence, Set

import tkinter as tk
from tkinter import ttk

import pandas as pd

from bilag_drilldialog import BilagDrillDialog
from .combinations import build_bilag_to_motkonto_combo
from formatting import fmt_amount, fmt_date
from .combinations_popup_helpers import build_bilag_rows, format_combo_df_for_display, truncate_text
from .combo_comment_workflow import edit_comment_for_focus, edit_comment_for_tree_item
from .expected_rules import (
    ExpectedRuleSet,
    empty_rule_set,
    load_rule_set,
    save_rule_set,
)
from .expected_rules_dialog import choose_expected_rules, format_rule_summary

from .combo_workflow import (
    STATUS_EXPECTED,
    STATUS_NEUTRAL,
    STATUS_OUTLIER,
    DIAG_EXPECTED,
    DIAG_NO_RULES,
    account_display_name_for_mode,
    apply_combo_status,
    combo_display_name,
    combo_display_name_for_mode,
    diagnose_combos_against_rule_set,
    find_expected_combos_by_rule_set,
    normalize_combo_status,
    normalize_direction,
    status_label,
    compute_selected_net_sum_by_combo,
)
from .utils import _bilag_str, _clean_name, _konto_str, _safe_float
from ui_treeview_sort import enable_treeview_sorting

logger = logging.getLogger(__name__)

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
        scope_mode: str | None = None,
        scope_items: Sequence[str] | None = None,
        konto_regnskapslinje_map: Mapping[str, str] | None = None,
        outlier_motkonto: Optional[Set[str]] = None,
        selected_direction: Optional[str] = None,
        outlier_combinations: Optional[Set[str]] = None,
        combo_status_map: Optional[dict[str, str]] = None,
        combo_comment_map: Optional[dict[str, str]] = None,
        on_outlier_changed: Optional[Callable[[Set[str]], None]] = None,
        on_export_excel: Optional[Callable[..., None]] = None,
    ):
        super().__init__(parent)

        self.title(title)
        self._summary = (summary or "").strip()

        # Normalize / cache inputs
        self._konto_navn_map = {str(k): _clean_name(v) for k, v in (konto_navn_map or {}).items()}
        self._konto_regnskapslinje_map = {
            str(k): str(v).strip()
            for k, v in (konto_regnskapslinje_map or {}).items()
            if str(k).strip() and str(v).strip()
        }
        self._selected_accounts = [_konto_str(a) for a in (selected_accounts or []) if _konto_str(a)]
        self._selected_accounts_set = set(self._selected_accounts)
        self._scope_mode = str(scope_mode or "konto").strip().lower()
        self._scope_items = [str(x).strip() for x in (scope_items or []) if str(x).strip()]
        display_default = "Regnskapslinje" if self._scope_mode.startswith("regn") and self._konto_regnskapslinje_map else "Konto"
        self._display_mode_var = tk.StringVar(value=display_default)
        self._selected_direction = normalize_direction(selected_direction)
        if self._selected_direction == "kredit":
            self._net_heading, self._net_label = "Netto kredit (valgte kontoer)", "Netto kredit"
        elif self._selected_direction == "debet":
            self._net_heading, self._net_label = "Netto debet (valgte kontoer)", "Netto debet"
        else:
            self._net_heading, self._net_label = "Netto valgte kontoer", "Netto"

        self._df_scope = df_scope if isinstance(df_scope, pd.DataFrame) else pd.DataFrame()
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
        self._combo_comment_map: dict[str, str] = combo_comment_map if combo_comment_map is not None else {}

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
        self._df_combos_raw = df_combos if isinstance(df_combos, pd.DataFrame) else pd.DataFrame()
        self._df_per_selected_raw = df_per_selected if isinstance(df_per_selected, pd.DataFrame) else pd.DataFrame()
        self._display_rows_cache: dict[str, tuple[list[dict[str, object]], list[dict[str, object]]]] = {}
        self._drilldown_cache: dict[tuple[str, str], dict[str, object]] = {}
        self._regnskapslinje_label_map = self._build_regnskapslinje_label_map()
        self._auto_expected_combos: set[str] = set()
        self._combo_diagnosis_map: dict[str, str] = {}
        self._rule_set: ExpectedRuleSet = self._load_initial_rule_set()

        # UI vars
        self._vis_var = tk.IntVar(value=200)

        # UI state: "utvid" (toggle maximize) – lagrer geometri for å kunne gå tilbake.
        self._is_zoomed: bool = False
        self._prev_geometry: str | None = None

        # Cache for summering i tabeller (ikke parse formaterte strenger fra treeview)
        self._combo_sum_map: dict[str, float] = {}
        self._combo_net_sum_map: dict[str, float] = {}
        self._combo_bilag_count_map: dict[str, int] = {}
        self._combo_total_sum: float = 0.0
        self._combo_total_net_sum: float = 0.0

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
        if self._scope_mode.startswith("regn") and self._scope_items:
            scope_text = "Valgte regnskapslinjer: " + ", ".join(self._scope_items)
            ttk.Label(container, text=scope_text, anchor="w", justify="left").pack(fill=tk.X, padx=2, pady=(0, 8))
        if self._konto_regnskapslinje_map:
            self._lbl_expected_regnskapslinjer = ttk.Label(container, text="", anchor="w", justify="left")
            self._lbl_expected_regnskapslinjer.pack(fill=tk.X, padx=2, pady=(0, 8))
            self._update_expected_regnskapslinjer_label()

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
        rules_bar = ttk.Frame(frame_all)
        rules_bar.pack(fill=tk.X, padx=4, pady=(6, 0))

        ttk.Label(top_bar, text="Status:").pack(side=tk.LEFT)

        if self._konto_regnskapslinje_map:
            ttk.Label(rules_bar, text="Visning:").pack(side=tk.LEFT)
            cmb_display = ttk.Combobox(
                rules_bar,
                textvariable=self._display_mode_var,
                values=["Konto", "Regnskapslinje"],
                width=16,
                state="readonly",
            )
            cmb_display.pack(side=tk.LEFT, padx=(4, 8))
            cmb_display.bind("<<ComboboxSelected>>", lambda _e=None: self._refresh_display_mode())

        can_edit_rules = self._single_source_regnr() is not None
        self._btn_edit_rules = ttk.Button(
            rules_bar,
            text="Rediger regler…",
            command=self._edit_rules,
            state=(tk.NORMAL if can_edit_rules else tk.DISABLED),
        )
        self._btn_edit_rules.pack(side=tk.LEFT, padx=(0, 8))

        # Fargede knapper (bruk tk.Button for å sikre bakgrunnsfarge i Windows TTK-tema)
        btn_expected = tk.Button(
            top_bar,
            text="Marker forventet",
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
            text="Nullstill",
            command=lambda: self._set_status_selected(STATUS_NEUTRAL),
        )
        btn_reset.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(
            rules_bar,
            text="Ctrl+E forventet  |  Ctrl+O outlier  |  Ctrl+0 nullstill",
        ).pack(side=tk.RIGHT)

        btn_close = ttk.Button(top_bar, text="Lukk", command=self.destroy)
        btn_close.pack(side=tk.RIGHT)

        btn_export = ttk.Button(top_bar, text="Eksporter Excel", command=self._export_excel)
        btn_export.pack(side=tk.RIGHT, padx=(0, 6))

        self._tree_all_columns_all = (
            "Kombinasjon #",
            "Kombinasjon",
            "Kombinasjon (navn)",
            "Antall bilag",
            "Sum valgte kontoer",
            "Netto valgte kontoer",
            "% andel bilag",
            "Outlier",
            "Status",
            "Forventet-grunn",
            "Kommentar",
        )
        self._tree_all_columns_default = tuple(
            c for c in self._tree_all_columns_all if c != "Forventet-grunn"
        )
        self._tree_all = ttk.Treeview(
            frame_all,
            columns=self._tree_all_columns_all,
            displaycolumns=self._tree_all_columns_default,
            show="headings",
            selectmode="extended",
        )
        for c in self._tree_all["columns"]:
            heading_text = self._net_heading if c == "Netto valgte kontoer" else c
            self._tree_all.heading(c, text=heading_text)
            if c == "Kombinasjon":
                w, anchor = 180, tk.W
            elif c == "Kombinasjon (navn)":
                w, anchor = 420, tk.W
            elif c == "Status":
                w, anchor = 110, tk.W
            elif c == "Forventet-grunn":
                w, anchor = 220, tk.W
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
            self._combo_net_sum_map = compute_selected_net_sum_by_combo(self._df_scope, self._selected_accounts, bilag_to_combo=self._bilag_to_combo, selected_direction=self._selected_direction)
            self._combo_total_net_sum = float(sum(self._combo_net_sum_map.values())) if self._combo_net_sum_map else 0.0
        except Exception:
            self._combo_total_sum = 0.0
            self._combo_net_sum_map = {}
            self._combo_total_net_sum = 0.0

        self._populate_all_tree()

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

        self._populate_per_tree()
        self._apply_expected_regnskapslinjer()

        self._tree_per.bind("<<TreeviewSelect>>", self._on_per_selected_selected)
        self._tree_per.bind("<Double-1>", self._on_per_selected_doubleclick)

        # Drilldown area (bottom of container, outside notebook)
        drill_container = ttk.Frame(container)
        drill_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(6, 0))

        self._lbl_combo = ttk.Label(drill_container, text="Velg en kombinasjon for drilldown")
        self._lbl_combo.pack(fill=tk.X, pady=(0, 2))

        self._lbl_combo_comment = ttk.Label(
            drill_container, text="", foreground="#555555",
            wraplength=800, justify="left",
        )
        self._lbl_combo_comment.pack(fill=tk.X, pady=(0, 4))

        paned = ttk.PanedWindow(drill_container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: distributions (motposts + selected accounts) in a notebook
        frame_left = ttk.LabelFrame(paned, text="Fordeling (sum)")
        paned.add(frame_left, weight=1)

        dist_toolbar = ttk.Frame(frame_left)
        dist_toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Label(dist_toolbar, text="Vis som:").pack(side=tk.LEFT)
        dist_mode_values = ["Konto"]
        if self._konto_regnskapslinje_map:
            dist_mode_values.append("Regnskapslinje")
        self._distribution_mode_var = tk.StringVar(value=dist_mode_values[0])
        self._cmb_distribution_mode = ttk.Combobox(
            dist_toolbar,
            textvariable=self._distribution_mode_var,
            values=dist_mode_values,
            width=16,
            state="readonly",
        )
        self._cmb_distribution_mode.pack(side=tk.LEFT, padx=(4, 0))
        self._cmb_distribution_mode.bind("<<ComboboxSelected>>", lambda _e=None: self._refresh_distribution_view())

        left_nb = ttk.Notebook(frame_left)
        left_nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tab_mot = ttk.Frame(left_nb)
        tab_sel = ttk.Frame(left_nb)
        left_nb.add(tab_mot, text="Motposter")
        left_nb.add(tab_sel, text="Valgte kontoer")
        self._left_nb = left_nb
        self._tab_mot = tab_mot
        self._tab_sel = tab_sel

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
        self._configure_distribution_tree_columns()

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

    def _display_mode(self) -> str:
        try:
            return str(self._display_mode_var.get() or "Konto").strip()
        except Exception:
            return "Konto"

    def _base_display_rows(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        mode = self._display_mode()
        cached = self._display_rows_cache.get(mode)
        if cached is not None:
            return cached

        started = perf_counter()

        combo_rows: list[dict[str, object]] = []
        df_disp = format_combo_df_for_display(self._df_combos_raw)
        for _, r in df_disp.iterrows():
            combo = str(r.get("Kombinasjon", "") or "").strip()
            combo_name = (
                combo_display_name_for_mode(
                    combo,
                    display_mode=mode,
                    konto_navn_map=self._konto_navn_map,
                    konto_regnskapslinje_map=self._konto_regnskapslinje_map,
                )
                if combo
                else ""
            )
            combo_rows.append(
                {
                    **r.to_dict(),
                    "Kombinasjon (navn)": combo_name,
                    "Netto valgte kontoer": fmt_amount(float(self._combo_net_sum_map.get(combo, 0.0) or 0.0)),
                }
            )

        per_rows: list[dict[str, object]] = []
        for _, r in self._df_per_selected_raw.iterrows():
            combo = str(r.get("Kombinasjon", "") or "").strip()
            combo_name = (
                combo_display_name_for_mode(
                    combo,
                    display_mode=mode,
                    konto_navn_map=self._konto_navn_map,
                    konto_regnskapslinje_map=self._konto_regnskapslinje_map,
                )
                if combo
                else ""
            )
            selected_value = account_display_name_for_mode(
                str(r.get("Valgt konto", "") or ""),
                display_mode=mode,
                konto_navn_map=self._konto_navn_map,
                konto_regnskapslinje_map=self._konto_regnskapslinje_map,
            )
            per_rows.append({**r.to_dict(), "Valgt konto": selected_value, "Kombinasjon (navn)": combo_name})

        payload = (combo_rows, per_rows)
        self._display_rows_cache[mode] = payload
        _duration = perf_counter() - started
        logger.debug(
            "Motpost kombinasjoner: bygget display-cache mode=%s rows=%s/%s på %.3fs",
            mode,
            len(combo_rows),
            len(per_rows),
            _duration,
        )
        try:
            from src.monitoring.perf import record_event as _record_event
            _record_event(
                "motpost.combinations.display_cache",
                _duration * 1000.0,
                meta={"mode": mode, "combo_rows": len(combo_rows), "per_rows": len(per_rows)},
            )
        except Exception:
            pass
        return payload

    def _get_drilldown_payload(self, combo_key: str) -> dict[str, object]:
        mode = self._distribution_mode()
        cache_key = (str(combo_key or ""), mode)
        cached = self._drilldown_cache.get(cache_key)
        if cached is not None:
            return cached

        started = perf_counter()
        bilag_list = list(self._combo_to_bilag.get(str(combo_key or ""), []) or [])
        if not bilag_list:
            payload = {
                "bilag_list": [],
                "sum_sel": 0.0,
                "sum_mot": 0.0,
                "kontroll": 0.0,
                "df_sel": pd.DataFrame(),
                "df_mot": pd.DataFrame(),
                "bilag_rows": pd.DataFrame(),
            }
            self._drilldown_cache[cache_key] = payload
            return payload

        df_combo = self._df_scope.loc[self._df_scope["Bilag_str"].isin(bilag_list)]

        sel_mask = df_combo["Konto_str"].isin(self._selected_accounts_set)
        dir_norm = normalize_direction(self._selected_direction)
        if dir_norm == "kredit":
            sel_mask = sel_mask & (df_combo["Beløp_num"] < 0)
        elif dir_norm == "debet":
            sel_mask = sel_mask & (df_combo["Beløp_num"] > 0)

        df_sel = df_combo.loc[sel_mask].copy()
        df_mot = df_combo.loc[~sel_mask].copy()
        sum_sel = float(df_sel["Beløp_num"].sum()) if not df_sel.empty else 0.0
        sum_mot = float(df_mot["Beløp_num"].sum()) if not df_mot.empty else 0.0
        payload = {
            "bilag_list": bilag_list,
            "sum_sel": sum_sel,
            "sum_mot": sum_mot,
            "kontroll": sum_sel + sum_mot,
            "df_sel": df_sel,
            "df_mot": df_mot,
            "bilag_rows": build_bilag_rows(df_combo, df_sel, df_mot),
        }
        self._drilldown_cache[cache_key] = payload
        _duration = perf_counter() - started
        logger.debug(
            "Motpost kombinasjoner: bygget drilldown-cache combo=%s mode=%s bilag=%s på %.3fs",
            combo_key,
            mode,
            len(bilag_list),
            _duration,
        )
        try:
            from src.monitoring.perf import record_event as _record_event
            _record_event(
                "motpost.combinations.drilldown_cache",
                _duration * 1000.0,
                meta={"combo": str(combo_key), "mode": mode, "bilag": len(bilag_list)},
            )
        except Exception:
            pass
        return payload

    def _refresh_display_mode(self) -> None:
        heading = "Kombinasjon (regnskapslinje)" if self._display_mode().lower().startswith("regn") else "Kombinasjon (navn)"
        try:
            self._tree_all.heading("Kombinasjon (navn)", text=heading)
        except Exception:
            pass
        try:
            self._tree_per.heading("Valgt konto", text="Valgt regnskapslinje" if self._display_mode().lower().startswith("regn") else "Valgt konto")
            self._tree_per.heading("Kombinasjon (navn)", text=heading)
        except Exception:
            pass
        self._populate_all_tree()
        self._populate_per_tree()

    @staticmethod
    def _sort_regnskapslinje_label(value: str) -> tuple[int, int | str, str]:
        text = str(value or "").strip()
        if not text:
            return (2, "", "")
        head = text.split(" ", 1)[0].strip()
        try:
            return (0, int(head), text.lower())
        except Exception:
            return (1, text.lower(), text.lower())

    @staticmethod
    def _parse_regnskapslinje_regnr(value: object) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        head = text.split(" ", 1)[0].strip()
        try:
            return int(head)
        except Exception:
            return None

    def _build_regnskapslinje_label_map(self) -> dict[int, str]:
        label_map: dict[int, str] = {}

        def _add(label: object) -> None:
            text = str(label or "").strip()
            if not text:
                return
            regnr = self._parse_regnskapslinje_regnr(text)
            if regnr is None or regnr in label_map:
                return
            label_map[regnr] = text

        for label in self._scope_items:
            _add(label)
        for label in self._konto_regnskapslinje_map.values():
            _add(label)

        try:
            import regnskap_config
            from regnskap_mapping import normalize_regnskapslinjer

            regn = normalize_regnskapslinjer(regnskap_config.load_regnskapslinjer())
            for row in regn[["regnr", "regnskapslinje"]].itertuples(index=False):
                try:
                    regnr = int(row.regnr)
                except Exception:
                    continue
                if regnr in label_map:
                    continue
                navn = str(row.regnskapslinje or "").strip()
                label_map[regnr] = f"{regnr} {navn}".strip()
        except Exception:
            pass

        return label_map

    def _current_scope_regnr(self) -> list[int]:
        regnr_values: list[int] = []
        for label in self._scope_items:
            regnr = self._parse_regnskapslinje_regnr(label)
            if regnr is None or regnr in regnr_values:
                continue
            regnr_values.append(regnr)
        return regnr_values

    def _current_client(self) -> str | None:
        try:
            import session as _session
            client = getattr(_session, "client", None)
        except Exception:
            client = None
        client_str = str(client or "").strip()
        return client_str or None

    def _single_source_regnr(self) -> int | None:
        regnr_list = self._current_scope_regnr()
        if len(regnr_list) == 1:
            return regnr_list[0]
        return None

    def _source_regnr_label(self, regnr: int) -> str:
        return str(self._regnskapslinje_label_map.get(int(regnr), str(regnr))).strip() or str(regnr)

    def _load_initial_rule_set(self) -> ExpectedRuleSet:
        regnr = self._single_source_regnr()
        client = self._current_client()
        if regnr is None:
            return empty_rule_set(regnr or 0, self._selected_direction)
        if not client:
            return empty_rule_set(regnr, self._selected_direction)
        try:
            return load_rule_set(
                client,
                source_regnr=regnr,
                selected_direction=self._selected_direction,
            )
        except Exception:
            return empty_rule_set(regnr, self._selected_direction)

    def _update_expected_regnskapslinjer_label(self) -> None:
        if not hasattr(self, "_lbl_expected_regnskapslinjer"):
            return
        rule_set = self._rule_set
        if rule_set is None or rule_set.is_empty():
            text = "Forventningsregler: ingen (definer via hovedvinduet)"
        else:
            parts = [
                format_rule_summary(rule, regnr_to_label=self._regnskapslinje_label_map)
                for rule in rule_set.rules
            ]
            text = f"Forventningsregler ({len(rule_set.rules)}): " + "  •  ".join(parts)
        try:
            self._lbl_expected_regnskapslinjer.config(text=text)
        except Exception:
            pass

    def _apply_expected_regnskapslinjer(self) -> None:
        previous_auto_expected = set(self._auto_expected_combos)
        self._auto_expected_combos = set()
        self._combo_diagnosis_map = {}
        if previous_auto_expected:
            clearable = [
                combo
                for combo in previous_auto_expected
                if normalize_combo_status(self._combo_status_map.get(combo, "")) == STATUS_EXPECTED
            ]
            if clearable:
                apply_combo_status(self._combo_status_map, clearable, STATUS_NEUTRAL)

        rule_set = self._rule_set
        has_rules = rule_set is not None and not rule_set.is_empty()
        if not has_rules or self._df_combos_raw is None or self._df_combos_raw.empty:
            self._update_diagnosis_column_visibility()
            self._populate_all_tree()
            return

        try:
            combo_values = [
                str(v).strip()
                for v in self._df_combos_raw.get("Kombinasjon", pd.Series(dtype=object)).tolist()
                if str(v).strip()
            ]
        except Exception:
            combo_values = []

        diagnosis = diagnose_combos_against_rule_set(
            combo_values,
            rule_set=rule_set,
            df_scope=self._df_scope,
            selected_accounts=self._selected_accounts,
            konto_regnskapslinje_map=self._konto_regnskapslinje_map,
            selected_direction=self._selected_direction,
        )

        expected_combos = [
            combo
            for combo in combo_values
            if diagnosis.get(combo) is not None and diagnosis[combo].status == DIAG_EXPECTED
        ]
        self._combo_diagnosis_map = {
            combo: diag.reason
            for combo, diag in diagnosis.items()
            if diag.status not in (DIAG_EXPECTED, DIAG_NO_RULES) and diag.reason
        }

        combos_to_mark = [
            combo
            for combo in expected_combos
            if normalize_combo_status(self._combo_status_map.get(combo, "")) != STATUS_OUTLIER
        ]
        if combos_to_mark:
            apply_combo_status(self._combo_status_map, combos_to_mark, STATUS_EXPECTED)
            self._auto_expected_combos = set(combos_to_mark)

        self._update_diagnosis_column_visibility()
        self._populate_all_tree()

    def _update_diagnosis_column_visibility(self) -> None:
        """Vis ``Forventet-grunn``-kolonnen kun når minst én rad har en grunn."""
        has_any = bool(self._combo_diagnosis_map)
        try:
            if has_any:
                self._tree_all.configure(displaycolumns=self._tree_all_columns_all)
            else:
                self._tree_all.configure(displaycolumns=self._tree_all_columns_default)
        except Exception:
            pass

    def _edit_rules(self) -> None:
        regnr = self._single_source_regnr()
        if regnr is None:
            return
        client = self._current_client()
        source_label = self._source_regnr_label(regnr)
        try:
            updated = choose_expected_rules(
                self,
                client=client,
                source_regnr=int(regnr),
                source_label=source_label,
                selected_direction=self._selected_direction,
                konto_regnskapslinje_map=self._konto_regnskapslinje_map,
                konto_navn_map=self._konto_navn_map,
                initial_rule_set=self._rule_set,
                motpost_konto_set=set(self._konto_regnskapslinje_map.keys()) or None,
            )
        except Exception:
            logger.exception("Klarte ikke å åpne forventningsregel-dialogen")
            return
        if updated is None:
            return
        self._rule_set = updated
        if client:
            try:
                save_rule_set(client, updated)
            except Exception:
                logger.exception("Klarte ikke å lagre forventningsregler")
        self._update_expected_regnskapslinjer_label()
        self._apply_expected_regnskapslinjer()

    def _populate_all_tree(self) -> None:
        self._clear_tree(self._tree_all)
        combo_rows, _ = self._base_display_rows()
        for r in combo_rows:
            combo = str(r.get("Kombinasjon", "") or "").strip()
            status_code = normalize_combo_status(self._combo_status_map.get(combo, ""))
            status_txt = status_label(status_code)
            comment_full = str(self._combo_comment_map.get(combo, "") or "").strip()
            comment_disp = truncate_text(comment_full, max_len=80) if comment_full else ""
            reason = self._combo_diagnosis_map.get(combo, "") if status_code != STATUS_EXPECTED else ""
            row_dict = {
                **r,
                "Status": status_txt,
                "Forventet-grunn": reason,
                "Kommentar": comment_disp,
            }
            vals = [row_dict.get(c, "") for c in self._tree_all["columns"]]
            tags = ()
            if status_code == STATUS_EXPECTED:
                tags = ("expected",)
            elif status_code == STATUS_OUTLIER:
                tags = ("outlier",)
            self._tree_all.insert("", tk.END, values=vals, tags=tags)
        self._update_combo_selection_summary()

    def _populate_per_tree(self) -> None:
        self._clear_tree(self._tree_per)
        _, per_rows = self._base_display_rows()
        for row_dict in per_rows:
            vals = [row_dict.get(c, "") for c in self._tree_per["columns"]]
            self._tree_per.insert("", tk.END, values=vals)

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
        sum_marked_net = float(sum(self._combo_net_sum_map.get(c, 0.0) for c in combos)) if combos else 0.0

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
        total_net = float(self._combo_total_net_sum or 0.0)

        base = f"Markert: {n} rader | Sum valgte kontoer (markert): {fmt_amount(sum_marked)} | {self._net_label} (markert): {fmt_amount(sum_marked_net)} | Total: {fmt_amount(total)} | {self._net_label} total: {fmt_amount(total_net)}"
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
        payload_status = dict(self._combo_status_map)
        payload_comments = dict(self._combo_comment_map)
        try:
            self._on_export_excel(payload_status, payload_comments)
        except TypeError:
            try:
                self._on_export_excel(payload_status)
            except TypeError:
                # Legacy: kun outlier-sett
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

    def _on_combo_doubleclick(self, event=None):
        # Dobbeltklikk: åpne kommentar-dialog for raden under musepekeren.
        item = None
        try:
            if event is not None:
                item = self._tree_all.identify_row(getattr(event, 'y', 0))
        except Exception:
            item = None

        if item:
            try:
                self._tree_all.focus(item)
                sel = set(self._tree_all.selection())
                if item not in sel:
                    self._tree_all.selection_set(item)
            except Exception:
                pass

        # Oppdater drilldown (som før)
        self._on_combo_selected()

        # Åpne kommentarfelt for klikket rad
        if item:
            edit_comment_for_tree_item(self, self._tree_all, item, comment_map=self._combo_comment_map)
            self._refresh_drilldown_comment()


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

    def _refresh_drilldown_comment(self) -> None:
        """Oppdater kommentar-label i drilldown basert paa current selection."""
        sel = self._current_selection
        combo_key = sel.combo if sel else ""
        comment = str(self._combo_comment_map.get(combo_key, "") or "").strip()
        try:
            self._lbl_combo_comment.config(
                text=f"Kommentar: {comment}" if comment else "",
            )
        except Exception:
            pass

    # ---- Drilldown calculations ----

    def _distribution_mode(self) -> str:
        try:
            return str(self._distribution_mode_var.get() or "Konto").strip()
        except Exception:
            return "Konto"

    @staticmethod
    def _split_regnskapslinje_label(label: str) -> tuple[str, str]:
        text = str(label or "").strip()
        if not text:
            return ("", "")
        parts = text.split(" ", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            return (parts[0].strip(), parts[1].strip())
        return ("", text)

    def _configure_distribution_tree_columns(self) -> None:
        mode = self._distribution_mode()
        if mode.startswith("Regn"):
            col1, col2 = "Nr", "Regnskapslinje"
            mot_title, sel_title = "Motposter per RL", "Valgte RL"
        else:
            col1, col2 = "Konto", "Kontonavn"
            mot_title, sel_title = "Motposter", "Valgte kontoer"

        for tree in (self._tree_mot, self._tree_sel):
            try:
                tree.heading("Konto", text=col1)
                tree.heading("Kontonavn", text=col2)
                tree.column("Konto", width=(70 if mode.startswith("Regn") else 80), anchor=tk.W, stretch=False)
                tree.column("Kontonavn", width=280, anchor=tk.W)
            except Exception:
                continue
        try:
            self._left_nb.tab(self._tab_mot, text=mot_title)
            self._left_nb.tab(self._tab_sel, text=sel_title)
        except Exception:
            pass

    def _refresh_distribution_view(self) -> None:
        self._configure_distribution_tree_columns()
        if self._current_selection is not None:
            self._update_drilldown(self._current_selection)

    def _populate_account_sum_tree(
        self,
        tree: ttk.Treeview,
        df_lines: pd.DataFrame,
        base_sum: Optional[float] = None,
    ) -> None:
        """Fyller fordelingstabell paa konto- eller regnskapslinjenivaa."""
        self._clear_tree(tree)
        if df_lines is None or df_lines.empty:
            return

        show_regnskapslinje = self._distribution_mode().startswith("Regn") and bool(self._konto_regnskapslinje_map)
        grouped = df_lines.copy()

        if show_regnskapslinje:
            grouped["_dist_key"] = grouped["Konto_str"].map(
                lambda konto: str(self._konto_regnskapslinje_map.get(str(konto), "") or "").strip() or "(ikke mappet)"
            )
            opposite_keys = {
                str(label).strip() or "(ikke mappet)"
                for label in grouped.loc[grouped["Konto_str"].isin(self._selected_accounts_set), "_dist_key"].tolist()
                if str(label).strip()
            }
        else:
            grouped["_dist_key"] = grouped["Konto_str"].astype(str)
            opposite_keys = {
                str(konto).strip()
                for konto in grouped.loc[grouped["Konto_str"].isin(self._selected_accounts_set), "_dist_key"].tolist()
                if str(konto).strip()
            }

        # Sikre numerisk beloepskolonne
        if "Beløp_num" not in grouped.columns:
            if "Beløp" in grouped.columns:
                grouped["Beløp_num"] = grouped["Beløp"].map(_safe_float)
            else:
                grouped["Beløp_num"] = 0.0

        by_key = grouped.groupby("_dist_key", dropna=False)["Beløp_num"].sum()
        by_key = by_key.reindex(by_key.abs().sort_values(ascending=False).index)

        name_map = {}
        if not show_regnskapslinje and "Kontonavn" in grouped.columns:
            for konto, s in grouped.groupby("_dist_key", dropna=False)["Kontonavn"]:
                name = ""
                for value in s.tolist():
                    if value is None:
                        continue
                    try:
                        if pd.isna(value):
                            continue
                    except Exception:
                        pass
                    text = str(value).strip()
                    if text and text.lower() != "nan":
                        name = text
                        break
                if name:
                    name_map[str(konto)] = name

        show_pct = base_sum is not None and abs(float(base_sum)) > 1e-12

        for key, belop in by_key.items():
            row_key = str(key)
            if show_regnskapslinje:
                display_key, name = self._split_regnskapslinje_label(row_key)
                if not display_key:
                    display_key = row_key
            else:
                display_key = row_key
                name = name_map.get(row_key) or self._konto_navn_map.get(row_key, "")

            tags = ()
            if tree is self._tree_mot and row_key in opposite_keys:
                tags = ("valgt_motsatt",)
                if name:
                    name = f"{name} (valgt, motsatt)"
                else:
                    name = "(valgt, motsatt)"

            pct_txt = ""
            if show_pct:
                pct = (abs(float(belop)) / abs(float(base_sum))) * 100.0
                pct_txt = fmt_amount(pct, decimals=2)

            tree.insert("", tk.END, values=(display_key, name, fmt_amount(belop), pct_txt), tags=tags)

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



def _popup_refresh_display_mode(self: _MotkontoCombinationsPopup) -> None:
    heading = "Kombinasjon (regnskapslinje)" if self._display_mode().lower().startswith("regn") else "Kombinasjon (navn)"
    try:
        self._tree_all.heading("Kombinasjon (navn)", text=heading)
    except Exception:
        pass
    try:
        self._tree_per.heading(
            "Valgt konto",
            text="Valgt regnskapslinje" if self._display_mode().lower().startswith("regn") else "Valgt konto",
        )
        self._tree_per.heading("Kombinasjon (navn)", text=heading)
    except Exception:
        pass
    self._populate_all_tree()
    self._populate_per_tree()


def _popup_populate_all_tree(self: _MotkontoCombinationsPopup) -> None:
    self._clear_tree(self._tree_all)
    combo_rows, _ = self._base_display_rows()
    for row in combo_rows:
        combo = str(row.get("Kombinasjon", "") or "").strip()
        status_code = normalize_combo_status(self._combo_status_map.get(combo, ""))
        status_txt = status_label(status_code)
        comment_full = str(self._combo_comment_map.get(combo, "") or "").strip()
        comment_disp = truncate_text(comment_full, max_len=80) if comment_full else ""
        reason = self._combo_diagnosis_map.get(combo, "") if status_code != STATUS_EXPECTED else ""
        values = {
            **row,
            "Status": status_txt,
            "Forventet-grunn": reason,
            "Kommentar": comment_disp,
        }
        tags = ()
        if status_code == STATUS_EXPECTED:
            tags = ("expected",)
        elif status_code == STATUS_OUTLIER:
            tags = ("outlier",)
        self._tree_all.insert("", tk.END, values=[values.get(c, "") for c in self._tree_all["columns"]], tags=tags)
    self._update_combo_selection_summary()


def _popup_populate_per_tree(self: _MotkontoCombinationsPopup) -> None:
    self._clear_tree(self._tree_per)
    _, per_rows = self._base_display_rows()
    for row in per_rows:
        self._tree_per.insert("", tk.END, values=[row.get(c, "") for c in self._tree_per["columns"]])


def _popup_update_drilldown(self: _MotkontoCombinationsPopup, selection: _ComboSelection) -> None:
    self._current_selection = selection
    combo_key = selection.combo

    payload = self._get_drilldown_payload(combo_key)
    bilag_list = list(payload.get("bilag_list", []) or [])
    # Vis kommentar for valgt kombinasjon
    comment = str(self._combo_comment_map.get(combo_key, "") or "").strip()
    try:
        self._lbl_combo_comment.config(
            text=f"Kommentar: {comment}" if comment else "",
        )
    except Exception:
        pass

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

    df_sel = payload.get("df_sel")
    df_mot = payload.get("df_mot")
    sum_sel = float(payload.get("sum_sel", 0.0) or 0.0)
    sum_mot = float(payload.get("sum_mot", 0.0) or 0.0)
    kontroll = float(payload.get("kontroll", 0.0) or 0.0)

    try:
        self._lbl_sel_total.config(text=f"Sum valgte kontoer: {fmt_amount(sum_sel)}")
        self._lbl_mot_total.config(text=f"Sum motposter: {fmt_amount(sum_mot)} | Kontroll: {fmt_amount(kontroll)}")
    except Exception:
        pass

    dir_txt = self._selected_direction if self._selected_direction != "alle" else "netto"
    extra = f" | Per valgt konto: {selection.selected_account}" if selection.selected_account else ""
    self._lbl_combo.config(
        text=(
            f"Kombinasjon: {combo_key}{extra}\n"
            f"Bilag: {len(bilag_list)} | Sum valgte kontoer ({dir_txt}): {fmt_amount(sum_sel)}"
            f" | Sum motposter: {fmt_amount(sum_mot)} | Kontroll (valgt + mot): {fmt_amount(kontroll)}"
        )
    )

    self._populate_account_sum_tree(self._tree_sel, df_sel, base_sum=sum_sel)
    self._populate_account_sum_tree(self._tree_mot, df_mot, base_sum=sum_sel)
    self._bilag_rows_cache = payload.get("bilag_rows")
    self._apply_bilag_limit()


_MotkontoCombinationsPopup._refresh_display_mode = _popup_refresh_display_mode
_MotkontoCombinationsPopup._populate_all_tree = _popup_populate_all_tree
_MotkontoCombinationsPopup._populate_per_tree = _popup_populate_per_tree
_MotkontoCombinationsPopup._update_drilldown = _popup_update_drilldown


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
    scope_mode: str | None = None,
    scope_items: Sequence[str] | None = None,
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
    outlier_motkonto: Optional[Set[str]] = None,
    selected_direction: Optional[str] = None,
    outlier_combinations: Optional[Set[str]] = None,
    combo_status_map: Optional[dict[str, str]] = None,
    combo_comment_map: Optional[dict[str, str]] = None,
    on_outlier_changed: Optional[Callable[[Set[str]], None]] = None,
    on_export_excel: Optional[Callable[..., None]] = None,
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
        scope_mode=scope_mode,
        scope_items=scope_items,
        konto_regnskapslinje_map=konto_regnskapslinje_map,
        outlier_motkonto=outlier_motkonto,
        selected_direction=selected_direction,
        outlier_combinations=outlier_combinations,
        combo_status_map=combo_status_map,
        combo_comment_map=combo_comment_map,
        on_outlier_changed=on_outlier_changed,
        on_export_excel=on_export_excel,
    )
    win.grab_set()
    win.focus_set()
    return win
