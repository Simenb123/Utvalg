"""page_analyse.py

Analyse-fanen: konto-pivot (venstre) + transaksjonsliste (høyre).

Delegerer størstedelen av logikken til egne moduler:
- page_analyse_ui.py         (widget-bygging/layout)
- page_analyse_filters_live.py (filtrering + debounce)
- page_analyse_pivot.py       (pivot-tree)
- page_analyse_transactions.py (transaksjonsliste)
- page_analyse_columns.py     (kolonnehåndtering, auto-fit, breddepersistens)
- page_analyse_sb.py           (saldobalansevisning med eget treeview)
- page_analyse_actions_impl.py (handlinger: motpost, nr.-serie, overstyring, drill)
- page_analyse_export.py       (DataFrame-bygging for Excel-eksport)

Viktige prinsipper:
- GUI skal være effektiv (live filtering), men robust: ingen krasj ved
  manglende moduler eller uventede signaturer.
- Headless/CI: Hvis ttk.Frame-init feiler, bygges en "headless" variant
  som fortsatt tilfredsstiller enhetstestene.

NB: Flere tester monkeypatcher navn i *denne* modulen (f.eks.
_open_bilag_drill_dialog, messagebox, _enable_treeview_sorting). Derfor
beholdes disse som modul-variabler, og sendes eksplisitt inn til helper-
funksjonene ved kall.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import pandas as pd

import formatting
import preferences
import ui_hotkeys

import session

import page_analyse_actions_impl
import page_analyse_columns
import page_analyse_detail_panel
import page_analyse_export
import page_analyse_filters_live
import page_analyse_pivot
import page_analyse_sb
import page_analyse_transactions
import page_analyse_ui

log = logging.getLogger(__name__)

try:
    from ui_treeview_sort import enable_treeview_sorting as _enable_treeview_sorting
except Exception:  # pragma: no cover
    _enable_treeview_sorting = None  # type: ignore

try:
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None  # type: ignore

try:
    from views_motpost_konto import show_motpost_konto as _show_motpost_konto
except Exception:  # pragma: no cover
    _show_motpost_konto = None  # type: ignore

try:
    from views_nr_series import show_nr_series_control as _show_nr_series_control
except Exception:  # pragma: no cover
    _show_nr_series_control = None  # type: ignore

try:
    from views_rl_account_drill import open_rl_account_drilldown as _open_rl_account_drilldown
except Exception:  # pragma: no cover
    _open_rl_account_drilldown = None  # type: ignore

try:
    from mva_config_dialog import open_mva_config as _open_mva_config_dialog
except Exception:  # pragma: no cover
    _open_mva_config_dialog = None  # type: ignore


@dataclass
class _DirectionOpt:
    label: str
    value: Optional[str]  # None | "debet" | "kredit"


_DIR_OPTIONS: List[_DirectionOpt] = [
    _DirectionOpt("Alle", None),
    _DirectionOpt("Debet", "debet"),
    _DirectionOpt("Kredit", "kredit"),
]

_MVA_FILTER_OPTIONS: List[str] = [
    "Alle",
    "Med MVA-kode",
    "Uten MVA-kode",
    "Med MVA-beløp",
    "Uten MVA-beløp",
    "MVA-avvik",
]


# ---------------------------------------------------------------------------
# Nøkkeltall inline rendering helpers
# ---------------------------------------------------------------------------

def _nk_write(widget, msg: str) -> None:
    """Skriv enkel tekstmelding til nk_text-widgeten."""
    try:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", msg)
        widget.configure(state="disabled")
    except Exception:
        pass


def _nk_render(widget, result) -> None:  # noqa: ANN001
    """Rendrer NokkeltallResult til nk_text-widgeten med formattering."""
    try:
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        # Sett opp tags
        widget.tag_configure("title", font=("TkDefaultFont", 13, "bold"), spacing3=6)
        widget.tag_configure("section", font=("TkDefaultFont", 11, "bold"), spacing1=12, spacing3=4)
        widget.tag_configure("sep", foreground="#CCCCCC")
        widget.tag_configure("label", font=("TkDefaultFont", 10))
        widget.tag_configure("val", font=("TkFixedFont", 10), foreground="#1A237E")
        widget.tag_configure("val_prev", font=("TkFixedFont", 10), foreground="#888888")
        widget.tag_configure("bold_label", font=("TkDefaultFont", 10, "bold"))
        widget.tag_configure("bold_val", font=("TkFixedFont", 10, "bold"), foreground="#1A237E")
        widget.tag_configure("pos_chg", font=("TkFixedFont", 9), foreground="#2E7D32")
        widget.tag_configure("neg_chg", font=("TkFixedFont", 9), foreground="#C62828")
        widget.tag_configure("na", font=("TkDefaultFont", 10), foreground="#AAAAAA")

        # Tittel
        title = "Nøkkeltall"
        if result.client:
            title += f"  —  {result.client}"
        if result.year:
            title += f"  {result.year}"
        widget.insert("end", title + "\n", "title")
        widget.insert("end", "─" * 60 + "\n\n", "sep")

        # --- KPI-nøkkeltall ---
        widget.insert("end", "Sentrale nøkkeltall\n", "section")
        widget.insert("end", "─" * 40 + "\n", "sep")
        has_kpi = False
        for card in result.kpi_cards:
            has_kpi = True
            label = str(card.get("label", ""))
            formatted = str(card.get("formatted", "–"))
            chg = card.get("change_pct")
            widget.insert("end", f"  {label:<32}", "label")
            widget.insert("end", f"{formatted:>12}", "val")
            if chg is not None:
                chg_str = f"  ({chg:+.1f} %)"
                tag = "pos_chg" if chg >= 0 else "neg_chg"
                widget.insert("end", chg_str, tag)
            widget.insert("end", "\n")
        if not has_kpi:
            widget.insert("end", "  – (ingen data) –\n", "na")

        # --- Nøkkeltall-tabell (Lønnsomhet, Likviditet, Soliditet, Effektivitet) ---
        categories = {}
        for m in result.metrics:
            categories.setdefault(m.category, []).append(m)

        for cat, items in categories.items():
            any_data = any(m.value is not None for m in items)
            if not any_data:
                continue
            widget.insert("end", f"\n{cat}\n", "section")
            widget.insert("end", "─" * 40 + "\n", "sep")
            for m in items:
                if m.value is None:
                    continue
                label = m.label
                val_str = m.formatted
                widget.insert("end", f"  {label:<38}", "label")
                widget.insert("end", f"{val_str:>12}", "val")
                if result.has_prev_year and m.prev_value is not None:
                    prev_str = m.formatted_prev
                    widget.insert("end", f"   fjor: {prev_str}", "val_prev")
                    chg = m.change_pct
                    if chg is not None:
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"  ({chg:+.1f} %)", tag)
                widget.insert("end", "\n")

        # --- Resultatregnskap ---
        if result.pl_summary:
            widget.insert("end", "\nResultatregnskap\n", "section")
            widget.insert("end", "─" * 60 + "\n", "sep")
            header = f"  {'':38}{'I år':>14}"
            if result.has_prev_year:
                header += f"{'Fjor':>14}{'Endring':>12}"
            widget.insert("end", header + "\n", "val_prev")
            for row in result.pl_summary:
                is_sum = row.get("is_sum", False)
                label_tag = "bold_label" if is_sum else "label"
                val_tag = "bold_val" if is_sum else "val"
                name = str(row.get("name", ""))
                formatted = str(row.get("formatted", "–"))
                widget.insert("end", f"  {name:<38}", label_tag)
                widget.insert("end", f"{formatted:>14}", val_tag)
                if result.has_prev_year:
                    prev_fmt = row.get("prev_formatted") or "–"
                    widget.insert("end", f"{prev_fmt:>14}", "val_prev")
                    chg_amt = row.get("change_amount_formatted")
                    if chg_amt:
                        chg = row.get("change_amount", 0) or 0
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"{chg_amt:>12}", tag)
                widget.insert("end", "\n")

        # --- Balanse ---
        if result.bs_summary:
            widget.insert("end", "\nBalanse\n", "section")
            widget.insert("end", "─" * 60 + "\n", "sep")
            header = f"  {'':38}{'I år':>14}"
            if result.has_prev_year:
                header += f"{'Fjor':>14}{'Endring':>12}"
            widget.insert("end", header + "\n", "val_prev")
            for row in result.bs_summary:
                is_sum = row.get("is_sum", False)
                label_tag = "bold_label" if is_sum else "label"
                val_tag = "bold_val" if is_sum else "val"
                name = str(row.get("name", ""))
                formatted = str(row.get("formatted", "–"))
                widget.insert("end", f"  {name:<38}", label_tag)
                widget.insert("end", f"{formatted:>14}", val_tag)
                if result.has_prev_year:
                    prev_fmt = row.get("prev_formatted") or "–"
                    widget.insert("end", f"{prev_fmt:>14}", "val_prev")
                    chg_amt = row.get("change_amount_formatted")
                    if chg_amt:
                        chg = row.get("change_amount", 0) or 0
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"{chg_amt:>12}", tag)
                widget.insert("end", "\n")

        widget.configure(state="disabled")
    except Exception as exc:
        try:
            widget.configure(state="disabled")
        except Exception:
            pass
        log.warning("_nk_render error: %s", exc)


class AnalysePage(ttk.Frame):  # type: ignore[misc]
    """GUI-side for analyse."""

    PIVOT_COLS = ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall", "UB_fjor", "Endring_fjor", "Endring_pct")

    # Standard kolonner i transaksjonslisten.
    TX_COLS_DEFAULT = (
        "Konto",
        "Kontonavn",
        "Dato",
        "Bilag",
        "Tekst",
        "Beløp",
        "Kunder",
        "MVA-kode",
        "MVA-beløp",
        "MVA-prosent",
        "Valuta",
        "Valutabeløp",
    )

    # "Pinned" kolonner vi alltid ønsker helt til venstre
    PINNED_TX_COLS = ("Konto", "Kontonavn")

    # Kolonner vi tvinger synlige for å ikke bryte nøkkelfunksjonalitet
    REQUIRED_TX_COLS = ("Bilag",)

    # Aktiv konfigurasjon (kan overskygges per instans via preferences)
    TX_COLS = TX_COLS_DEFAULT

    # Live filtering (debounce) – gir effektiv GUI uten "Bruk filtre"
    LIVE_FILTER_DEBOUNCE_MS = 350
    MVA_FILTER_OPTIONS = tuple(_MVA_FILTER_OPTIONS)
    MVA_CODE_ALL_LABEL = "Alle"

    def __init__(self, master=None):
        # Live filter debounce / scheduling
        self._filter_after_id: Optional[str] = None
        self._suspend_live_filter: bool = False
        self._heavy_refresh_after_id: Optional[str] = None
        self._heavy_refresh_generation: int = 0

        # --- headless-friendly init ---
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception as e:  # TclError or other Tk init problems
            # Fall back to a minimal object for test/CI.
            self._tk_ok = False
            self.dataset: Optional[pd.DataFrame] = None
            self._df_filtered: Optional[pd.DataFrame] = None
            self._utvalg_callback: Optional[Callable[[List[str]], None]] = None
            self._var_aggregering = None
            self._rl_intervals = None
            self._rl_regnskapslinjer = None
            self._rl_sb_df = None
            self._rl_mapping_warning = ""
            self._mapping_warning = ""
            self._mapping_issues = []
            self._mapping_problem_accounts = []
            self._var_hide_sumposter = None
            self._var_include_ao = None
            self._var_show_only_unmapped = None
            self._tx_col_widths = {}
            self._pivot_col_widths = {}
            self._pivot_visible_cols = list(self.PIVOT_COLS_DEFAULT_VISIBLE)
            self._var_tx_view_mode = None
            self._sb_tree = None
            self._sb_frame = None
            self._tx_frame = None
            self._tx_header_drag = None
            self._pivot_balance_after_id = None
            self._mapping_warning_var = None
            self._mapping_banner_frame = None
            self._detail_selected_account = ""
            self._detail_accounts_df = None
            self._detail_suggestions_by_account = {}
            self._detail_profiles_by_account = {}
            self._detail_context = {}
            self._heavy_refresh_after_id = None
            self._heavy_refresh_generation = 0
            self._init_error = e
            return

        # --- state ---
        self.dataset: Optional[pd.DataFrame] = None
        self._df_filtered: Optional[pd.DataFrame] = None
        self._utvalg_callback: Optional[Callable[[List[str]], None]] = None

        # --- vars ---
        self._var_search = tk.StringVar(value="")
        self._var_direction = tk.StringVar(value=_DIR_OPTIONS[0].label)
        self._var_bilag = tk.StringVar(value="")
        self._var_motpart = tk.StringVar(value="")
        self._var_date_from = tk.StringVar(value="")
        self._var_date_to = tk.StringVar(value="")
        self._var_min = tk.StringVar(value="")
        self._var_max = tk.StringVar(value="")
        self._var_mva_code = tk.StringVar(value=self.MVA_CODE_ALL_LABEL)
        self._var_mva_mode = tk.StringVar(value=self.MVA_FILTER_OPTIONS[0])
        self._var_max_rows = tk.IntVar(value=200)
        self._var_aggregering = tk.StringVar(value="Regnskapslinje")
        self._series_vars = [tk.IntVar(value=0) for _ in range(10)]
        self._mva_code_values: List[str] = [self.MVA_CODE_ALL_LABEL]
        self._rl_mapping_warning: str = ""
        self._mapping_warning: str = ""
        self._mapping_issues: List[object] = []
        self._mapping_problem_accounts: List[str] = []
        self._detail_selected_account: str = ""
        self._detail_accounts_df: Optional[pd.DataFrame] = None
        self._detail_suggestions_by_account: dict[str, object] = {}
        self._detail_profiles_by_account: dict[str, object] = {}
        self._detail_context: dict[str, object] = {}
        self._detail_only_flagged_var = tk.BooleanVar(value=False)
        self._detail_summary_var = tk.StringVar(value="Velg en konto eller regnskapslinje for å se detaljer.")
        self._detail_status_var = tk.StringVar(value="Forslag og avvik vises her når en konto er valgt.")

        # --- Display options ---
        self._var_hide_sumposter = tk.BooleanVar(value=False)
        self._var_include_ao = tk.BooleanVar(value=False)
        self._var_hide_zero = tk.BooleanVar(value=False)
        self._var_show_only_unmapped = tk.BooleanVar(value=False)
        self._var_data_level = tk.StringVar(value="")
        self._mapping_warning_var = tk.StringVar(value="")

        # --- RL config cache ---
        self._rl_intervals = None
        self._rl_regnskapslinjer = None
        self._rl_sb_df = None

        # --- kolonner (transaksjonsliste) ---
        # Lagres per bruker via preferences (best-effort; aldri krasj GUI)
        self._tx_cols_order: List[str] = list(self.TX_COLS_DEFAULT)
        self._load_tx_columns_from_preferences()
        self._tx_col_widths = self._load_saved_column_widths("analyse.tx_cols.widths")
        self._pivot_col_widths = self._load_saved_column_widths("analyse.pivot.widths")
        self._pivot_visible_cols: List[str] = list(self.PIVOT_COLS_DEFAULT_VISIBLE)
        self._load_pivot_visible_columns()
        self._pivot_first_load = True
        self._tx_first_load = True

        # --- SB/transaksjonsvisning toggle ---
        self._var_tx_view_mode = tk.StringVar(value="Saldobalansekontoer")

        # --- UI refs ---
        self._pivot_tree = None
        self._tx_tree = None
        self._sb_tree = None
        self._sb_frame = None
        self._tx_frame = None
        self._tx_header_drag = None
        self._pivot_balance_after_id = None
        self._lbl_tx_summary = None
        self._mapping_banner_frame = None
        self._detail_panel = None
        self._detail_accounts_tree = None
        self._detail_suggestion_tree = None
        self._detail_split = None
        self._ent_search: Optional[object] = None

        self._build_ui()

    # -----------------------------------------------------------------
    # Public API expected by ui_main/tests
    # -----------------------------------------------------------------

    def set_utvalg_callback(self, callback: Callable[[List[str]], None]) -> None:
        self._utvalg_callback = callback

    def refresh_from_session(self, sess: object = session, *, defer_heavy: bool = False) -> None:
        """Reload data from session and refresh UI.

        Viktig: Vi beholder råverdien i self.dataset (ikke bare DataFrame),
        slik at headless-tester kan sette dummy-verdier og verifisere at
        metoden faktisk oppdaterer feltet.
        """
        df = getattr(sess, "dataset", None)
        self.dataset = df  # type: ignore[assignment]
        self._refresh_mva_code_choices()
        self._update_data_level()
        if defer_heavy:
            self._schedule_heavy_refresh()
            return
        self._run_full_refresh()

    def _run_full_refresh(self) -> None:
        self._reload_rl_config()
        self._apply_filters_and_refresh()
        self._adapt_pivot_columns_for_mode()
        self._update_data_level()

    def _schedule_heavy_refresh(self) -> None:
        """Planlegg én tung refresh etter at GUI har fått tilbake kontroll."""
        self._heavy_refresh_generation += 1
        generation = self._heavy_refresh_generation

        pending = getattr(self, "_heavy_refresh_after_id", None)
        if pending:
            try:
                self.after_cancel(pending)
            except Exception:
                pass
            self._heavy_refresh_after_id = None

        if not getattr(self, "_tk_ok", False):
            self._run_full_refresh()
            return

        def _start() -> None:
            if generation != self._heavy_refresh_generation:
                return
            self._heavy_refresh_after_id = None
            self._run_heavy_refresh_staged(generation)

        try:
            self._heavy_refresh_after_id = self.after_idle(_start)
        except Exception:
            self._heavy_refresh_after_id = None
            self._run_full_refresh()

    def _run_heavy_refresh_staged(self, generation: int | None = None) -> None:
        """Kjør første Analyse-render i små steg for å unngå GUI-heng."""
        token = self._heavy_refresh_generation if generation is None else generation

        def _is_stale() -> bool:
            return token != self._heavy_refresh_generation

        def _run_next(step_index: int = 0) -> None:
            if _is_stale():
                return

            if step_index == 0:
                try:
                    self._reload_rl_config()
                except Exception:
                    log.exception("Analyse staged refresh: reload RL config failed")
            elif step_index == 1:
                try:
                    df_filtered = page_analyse_filters_live.build_filtered_df(page=self, dir_options=_DIR_OPTIONS)
                    self._df_filtered = df_filtered
                    if df_filtered is None:
                        page_analyse_filters_live._clear_views_for_missing_dataset(page=self)
                except Exception:
                    log.exception("Analyse staged refresh: build filtered df failed")
                    self._df_filtered = None
                    try:
                        page_analyse_filters_live._clear_views_for_missing_dataset(page=self)
                    except Exception:
                        pass
            elif step_index == 2:
                if self._df_filtered is not None:
                    try:
                        self._refresh_pivot()
                    except Exception:
                        log.exception("Analyse staged refresh: pivot refresh failed")
            elif step_index == 3:
                if self._df_filtered is not None:
                    try:
                        self._refresh_transactions_view()
                    except Exception:
                        log.exception("Analyse staged refresh: transactions refresh failed")
            elif step_index == 4:
                if self._df_filtered is not None:
                    try:
                        self._refresh_detail_panel()
                    except Exception:
                        log.exception("Analyse staged refresh: detail refresh failed")
            elif step_index == 5:
                try:
                    self._adapt_pivot_columns_for_mode()
                except Exception:
                    log.exception("Analyse staged refresh: adapt pivot columns failed")
                try:
                    self._update_data_level()
                except Exception:
                    log.exception("Analyse staged refresh: update data level failed")
                return

            try:
                self.after(10, lambda: _run_next(step_index + 1))
            except Exception:
                _run_next(step_index + 1)

        _run_next()

    def _reload_rl_config(self) -> None:
        """Last intervall-mapping, regnskapslinjer og aktiv SB on-demand (best-effort)."""
        try:
            import page_analyse_rl
            intervals, regnskapslinjer = page_analyse_rl.load_rl_config()
            self._rl_intervals = intervals
            self._rl_regnskapslinjer = regnskapslinjer
            self._rl_sb_df = page_analyse_rl.load_sb_for_session()
        except Exception:
            pass

    def _on_aggregering_changed(self, _event=None) -> None:
        """Bytt mellom Konto- og Regnskapslinje-modus."""
        self._apply_filters_and_refresh()
        # Tilpass synlige kolonner etter pivot-refresh (headings er nå oppdatert)
        self._adapt_pivot_columns_for_mode()

    def _normalize_mva_code_value(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in {"nan", "none", "<na>"}:
            return ""
        try:
            num = float(text.replace(",", "."))
        except Exception:
            return text.upper()
        if abs(num - round(num)) < 1e-9:
            return str(int(round(num)))
        return text.upper()

    def _sort_mva_code_value(self, value: str) -> tuple[int, int | str]:
        try:
            return (0, int(value))
        except Exception:
            return (1, value)

    def _refresh_mva_code_choices(self) -> None:
        df = self.dataset if isinstance(self.dataset, pd.DataFrame) else None
        values = [self.MVA_CODE_ALL_LABEL]

        if isinstance(df, pd.DataFrame):
            col = next((c for c in ("MVA-kode", "mva-kode", "Mva", "mva") if c in df.columns), None)
            if col is not None:
                codes = {
                    self._normalize_mva_code_value(v)
                    for v in df[col].tolist()
                }
                codes.discard("")
                values.extend(sorted(codes, key=self._sort_mva_code_value))

        self._mva_code_values = values

        cmb = getattr(self, "_cmb_mva_code", None)
        if cmb is not None:
            try:
                cmb.configure(values=values)
            except Exception:
                pass

        try:
            current = str(self._var_mva_code.get() or "")
        except Exception:
            current = ""
        if current not in values:
            try:
                self._var_mva_code.set(self.MVA_CODE_ALL_LABEL)
            except Exception:
                pass

    # -----------------------------------------------------------------
    # UI build + shortcuts
    # -----------------------------------------------------------------

    def _build_ui(self) -> None:
        page_analyse_ui.build_ui(page=self, tk=tk, ttk=ttk, dir_options=_DIR_OPTIONS)

    def _enable_pivot_sorting(self) -> None:
        """Aktiver klikk-for-sortering på pivotlisten hvis tilgjengelig."""
        if not getattr(self, "_tk_ok", False):
            return
        if getattr(self, "_pivot_tree", None) is None:
            return
        if _enable_treeview_sorting is None:
            return
        try:
            _enable_treeview_sorting(self._pivot_tree, columns=self.PIVOT_COLS)  # type: ignore[arg-type]
        except Exception:
            # Sorting er "nice to have" – aldri krasj GUI hvis det feiler.
            pass


    # -----------------------------------------------------------------
    # Pivot-kolonner (delegert til page_analyse_columns)
    # -----------------------------------------------------------------

    PIVOT_COLS_DEFAULT_VISIBLE = ("Konto", "Kontonavn", "Endring", "Sum", "Antall")
    PIVOT_COLS_DEFAULT_KONTO = ("Konto", "Kontonavn", "Sum", "Antall")
    PIVOT_COLS_DEFAULT_RL = ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall")
    PIVOT_COLS_PINNED = ("Konto", "Kontonavn")

    def _load_pivot_visible_columns(self) -> None:
        page_analyse_columns.load_pivot_visible_columns(page=self)

    def _apply_pivot_visible_columns(self) -> None:
        page_analyse_columns.apply_pivot_visible_columns(page=self)

    def _show_pivot_column_menu(self, event=None) -> None:
        page_analyse_columns.show_pivot_column_menu(page=self, event=event)

    def _reset_pivot_columns(self) -> None:
        page_analyse_columns.reset_pivot_columns(page=self)

    def _adapt_pivot_columns_for_mode(self) -> None:
        page_analyse_columns.adapt_pivot_columns_for_mode(page=self)

    # -----------------------------------------------------------------
    # TX-kolonner (delegert til page_analyse_columns)
    # -----------------------------------------------------------------

    def _load_tx_columns_from_preferences(self) -> None:
        page_analyse_columns.load_tx_columns_from_preferences(page=self)

    def _get_all_tx_columns_for_chooser(self) -> List[str]:
        return page_analyse_columns.get_all_tx_columns_for_chooser(page=self)

    def _open_tx_column_chooser(self) -> None:
        page_analyse_columns.open_tx_column_chooser(page=self)

    def _reset_tx_columns_to_default(self) -> None:
        page_analyse_columns.reset_tx_columns_to_default(page=self)

    def _copy_selected_tx_rows_to_clipboard(self) -> None:
        if not self._tk_ok:
            return
        tree = getattr(self, "_tx_tree", None)
        if tree is None:
            return
        txt = ui_hotkeys.treeview_selection_to_tsv(tree)
        if not txt.strip():
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(txt)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Auto-fit & kolonnbredder (delegert til page_analyse_columns)
    # -----------------------------------------------------------------

    @staticmethod
    def _load_saved_column_widths(pref_key: str) -> dict[str, int]:
        return page_analyse_columns.load_saved_column_widths(pref_key)

    def _maybe_auto_fit_tx_tree(self) -> None:
        page_analyse_columns.maybe_auto_fit_tx_tree(page=self)

    def _maybe_auto_fit_pivot_tree(self) -> None:
        page_analyse_columns.maybe_auto_fit_pivot_tree(page=self)

    def _schedule_balance_pivot_tree(self) -> None:
        page_analyse_columns.schedule_balance_pivot_tree(page=self)

    def _auto_fit_analyse_columns(self) -> None:
        page_analyse_columns.auto_fit_analyse_columns(page=self)

    def _on_tx_tree_double_click(self, event=None):
        return page_analyse_columns.on_tx_tree_double_click(page=self, event=event)

    def _on_tx_tree_mouse_press(self, event=None):
        page_analyse_columns.on_tx_tree_mouse_press(page=self, event=event)

    def _on_tx_tree_mouse_drag(self, event=None):
        page_analyse_columns.on_tx_tree_mouse_drag(page=self, event=event)

    def _on_pivot_tree_double_click(self, event=None):
        return page_analyse_columns.on_pivot_tree_double_click(page=self, event=event)

    def _on_tx_tree_mouse_release(self, event=None):
        page_analyse_columns.on_tx_tree_mouse_release(page=self, event=event)

    def _on_pivot_tree_mouse_release(self, event=None):
        page_analyse_columns.on_pivot_tree_mouse_release(page=self, event=event)

    def _configure_tx_tree_columns(self) -> None:
        page_analyse_columns.configure_tx_tree_columns(page=self)

    def _enable_tx_sorting(self) -> None:
        page_analyse_columns.enable_tx_sorting(page=self, enable_fn=_enable_treeview_sorting)


    def _bind_entry_select_all(self, entry) -> None:
        """Bind Ctrl+A (and Cmd+A on macOS) to select all text in an Entry.

        Be defensive: never raise if the widget does not support the expected API.
        """

        if entry is None:
            return

        def _select_all(_event=None):
            try:
                if hasattr(entry, "select_range"):
                    entry.select_range(0, "end")
                elif hasattr(entry, "selection_range"):
                    entry.selection_range(0, "end")
                if hasattr(entry, "icursor"):
                    entry.icursor("end")
            except Exception:
                pass
            return "break"

        try:
            entry.bind("<Control-a>", _select_all)
            entry.bind("<Control-A>", _select_all)
            # macOS
            entry.bind("<Command-a>", _select_all)
            entry.bind("<Command-A>", _select_all)
        except Exception:
            pass


    def _bind_shortcuts(
        self,
        ent_search,
        ent_bilag=None,
        ent_motpart=None,
        ent_date_from=None,
        ent_date_to=None,
        ent_min=None,
        ent_max=None,
        ent_mva=None,
        cmb_dir=None,
        cmb_mva=None,
        spn_max=None,
        spn_rows=None,
        **_kwargs,
    ) -> None:
        """Bind snarveier på de viktigste widgetene i Analyse-fanen.

        Kalles fra ``page_analyse_ui.build_ui``. UI-builderen kan over tid sende
        inn flere widgets (f.eks. ``cmb_dir`` / ``spn_max``). For å unngå at
        AnalysePage-init knekker ved signaturendringer, aksepterer vi derfor
        ekstra parametre og ignorerer ukjente kwargs.
        """
        max_widget = spn_max or spn_rows
        widgets = [
            w
            for w in [
                getattr(self, "_pivot_tree", None),
                getattr(self, "_tx_tree", None),
                ent_search,
                ent_bilag,
                ent_motpart,
                ent_date_from,
                ent_date_to,
                ent_min,
                ent_max,
                ent_mva,
                cmb_dir,
                cmb_mva,
                max_widget,
            ]
            if w is not None
        ]
        for w in widgets:
            try:
                w.bind("<Control-f>", self._on_ctrl_f)
                w.bind("<Control-F>", self._on_ctrl_f)
                w.bind("<Escape>", self._on_escape)
            except Exception:
                continue

    def _focus_search_entry(self) -> None:
        ent = getattr(self, "_ent_search", None)
        if ent is None:
            return
        try:
            ent.focus_set()
            try:
                ent.selection_range(0, "end")
                ent.icursor("end")
            except Exception:
                pass
        except Exception:
            pass

    def _on_ctrl_f(self, _event=None):
        """Ctrl+F: fokuser søkefeltet og marker teksten."""
        self._focus_search_entry()
        return "break"

    def _on_escape(self, _event=None):
        """Esc: nullstill filtre (samme som "Nullstill"-knappen).

        Skal være defensiv og aldri kaste fra event-binding.
        """
        try:
            self._reset_filters()
        except Exception:
            pass
        return "break"
    def _on_pivot_select(self, _event=None) -> None:
        """Når bruker velger konto(er) i pivotlisten, oppdater transaksjonslisten.

        UI (page_analyse_ui) binder <<TreeviewSelect>> til denne hooken.
        """
        try:
            self._update_mapping_warning_banner()
        except Exception:
            pass
        try:
            self._refresh_transactions_view()
        except Exception:
            # Skal aldri krasje GUI på event-binding.
            pass
        try:
            self._refresh_detail_panel()
        except Exception:
            pass

    def _on_tx_select(self, _event=None) -> None:
        """Hook for evt. fremtidig logikk ved valg i transaksjonslisten.

        Vi har denne metoden fordi UI kan binde <<TreeviewSelect>> til den.
        Skal være en no-op og aldri kaste.
        """
        return None

    # -----------------------------------------------------------------
    # Events + live filter
    # -----------------------------------------------------------------

    def _on_direction_changed(self, _event=None) -> None:
        self._apply_filters_now()

    def _on_hide_sumposter_changed(self, _event=None) -> None:
        """Toggle synlighet for Σ-sumposter i pivot-treet."""
        try:
            self._refresh_analysis_views_after_adjustment_change()
        except Exception:
            pass

    def _on_hide_zero_changed(self, _event=None) -> None:
        """Toggle synlighet for kontoer med saldo = 0 i pivot-treet."""
        try:
            self._refresh_pivot()
            self._refresh_transactions_view()
        except Exception:
            pass

    def _on_include_ao_changed(self, _event=None) -> None:
        """Toggle tilleggsposteringer (ÅO) i pivot og SB-visning."""
        try:
            self._refresh_analysis_views_after_adjustment_change()
        except Exception:
            pass

    def _include_ao_enabled(self) -> bool:
        try:
            return bool(self._var_include_ao.get()) if self._var_include_ao is not None else False
        except Exception:
            return False

    def _get_effective_sb_df(self):
        sb_df = getattr(self, "_rl_sb_df", None)
        if sb_df is None:
            return None
        if not self._include_ao_enabled():
            return sb_df
        try:
            import session as _session
            import regnskap_client_overrides
            import tilleggsposteringer

            client = getattr(_session, "client", None) or ""
            year = getattr(_session, "year", None) or ""
            if not client or not year:
                return sb_df
            ao_entries = regnskap_client_overrides.load_supplementary_entries(client, year)
            if not ao_entries:
                return sb_df
            return tilleggsposteringer.apply_to_sb(sb_df, ao_entries)
        except Exception:
            return sb_df

    def _refresh_analysis_views_after_adjustment_change(self) -> None:
        try:
            self._refresh_pivot()
        except Exception:
            pass
        try:
            self._refresh_detail_panel()
        except Exception:
            pass
        try:
            self._refresh_transactions_view()
        except Exception:
            pass

    def _open_tilleggsposteringer(self) -> None:
        """Åpne dialog for tilleggsposteringer."""
        try:
            import session as _session
            import tilleggsposteringer
            client = getattr(_session, "client", None) or ""
            year = getattr(_session, "year", None) or ""
            if not client or not year:
                from tkinter import messagebox
                messagebox.showinfo("Tilleggsposteringer",
                                    "Ingen aktiv klient/år.", parent=self)
                return
            tilleggsposteringer.open_dialog(
                self, client=client, year=year,
                on_changed=lambda: self._refresh_analysis_views_after_adjustment_change(),
            )
        except Exception as exc:
            import logging
            logging.getLogger("app").error("Tilleggsposteringer error: %s", exc)

    def _open_disponering_via_ao(self) -> None:
        """Open a simple disposition helper backed by supplementary entries."""
        try:
            import session as _session
            from tkinter import messagebox

            import analyse_disponering_dialog
            import regnskap_client_overrides
            import tilleggsposteringer

            client = getattr(_session, "client", None) or ""
            year = getattr(_session, "year", None) or ""
            if not client or not year:
                messagebox.showinfo("Disponering via AO", "Ingen aktiv klient/ar.", parent=self)
                return

            self._reload_rl_config()
            intervals = getattr(self, "_rl_intervals", None)
            regnskapslinjer = getattr(self, "_rl_regnskapslinjer", None)
            sb_df = getattr(self, "_rl_sb_df", None)
            if intervals is None or regnskapslinjer is None or sb_df is None:
                messagebox.showwarning(
                    "Disponering via AO",
                    "Manglende mapping- eller saldobalansegrunnlag for a apne disponeringshjelpen.",
                    parent=self,
                )
                return

            ao_entries = regnskap_client_overrides.load_supplementary_entries(client, year)
            effective_sb = tilleggsposteringer.apply_to_sb(sb_df, ao_entries)
            overrides = regnskap_client_overrides.load_account_overrides(client, year=str(year))

            def _after_changed() -> None:
                try:
                    if getattr(self, "_var_include_ao", None) is not None:
                        self._var_include_ao.set(True)
                except Exception:
                    pass
                self._refresh_analysis_views_after_adjustment_change()

            analyse_disponering_dialog.open_dialog(
                self,
                client=client,
                year=str(year),
                hb_df=getattr(self, "dataset", None),
                effective_sb_df=effective_sb,
                intervals=intervals,
                regnskapslinjer=regnskapslinjer,
                account_overrides=overrides,
                on_changed=_after_changed,
            )
        except Exception as exc:
            import logging
            logging.getLogger("app").error("Disponering via AO error: %s", exc)

    def _on_max_rows_changed(self, _event=None) -> None:
        """Endring i "Vis" skal oppdatere transaksjonslisten.

        UI kan trigge denne flere veier (Spinbox command, FocusOut/Return,
        og via trace_add på variabelen). For å unngå dobbel refresh på samme
        verdi bruker vi en enkel 'last value'-cache.
        """
        try:
            var = getattr(self, "_var_max_rows", None)
            cur = int(var.get()) if var is not None else None
        except Exception:
            cur = None

        last = getattr(self, "_last_max_rows_value", object())
        if cur is not None and last == cur:
            return
        self._last_max_rows_value = cur
        self._refresh_transactions_view()

    def _on_live_filter_var_changed(self) -> None:
        self._schedule_apply_filters()

    def _schedule_apply_filters(self) -> None:
        page_analyse_filters_live.schedule_apply_filters(page=self)

    def _apply_filters_now(self, _event=None) -> None:
        page_analyse_filters_live.apply_filters_now(page=self)

    # -----------------------------------------------------------------
    # Filtering / refresh
    # -----------------------------------------------------------------

    def _reset_filters(self) -> None:
        page_analyse_filters_live.reset_filters(page=self, dir_options=_DIR_OPTIONS)

    def _apply_filters_and_refresh(self) -> None:
        page_analyse_filters_live.apply_filters_and_refresh(page=self, dir_options=_DIR_OPTIONS)

    @staticmethod
    def _safe_float(s: str) -> Optional[float]:
        return page_analyse_filters_live.safe_float(s)

    @staticmethod
    def _clear_tree(tree) -> None:
        if tree is None:
            return
        try:
            items = tree.get_children("")
        except Exception:
            items = ()
        for item in items:
            try:
                tree.delete(item)
            except Exception:
                continue

    # -----------------------------------------------------------------
    # Pivot + transactions
    # -----------------------------------------------------------------

    def _refresh_pivot(self) -> None:
        try:
            self._refresh_mapping_issues()
        except Exception:
            pass
        page_analyse_pivot.refresh_pivot(page=self)
        self._update_ao_count_label()
        try:
            self._update_mapping_warning_banner()
        except Exception:
            pass

    def _refresh_mapping_issues(self) -> None:
        try:
            import analyse_mapping_service
            issues = analyse_mapping_service.build_page_mapping_issues(self)
            problems = analyse_mapping_service.problem_mapping_issues(issues)
            summary = analyse_mapping_service.summarize_mapping_issues(issues)
            accounts = analyse_mapping_service.get_problem_accounts(issues)
        except Exception:
            issues = []
            problems = []
            summary = ""
            accounts = []
        self._mapping_issues = list(issues)
        self._mapping_problem_accounts = list(accounts)
        self._mapping_warning = str(summary or "")
        if getattr(self, "_mapping_warning_var", None) is not None:
            try:
                self._mapping_warning_var.set(self._mapping_warning)
            except Exception:
                pass
        self._update_mapping_warning_banner(problem_count=len(problems))

    def _update_mapping_warning_banner(self, *, problem_count: Optional[int] = None) -> None:
        frame = getattr(self, "_mapping_banner_frame", None)
        if frame is None:
            return
        summary = str(getattr(self, "_mapping_warning", "") or "").strip()
        if problem_count is None:
            try:
                import analyse_mapping_service
                problem_count = len(
                    analyse_mapping_service.problem_mapping_issues(
                        getattr(self, "_mapping_issues", []) or []
                    )
                )
            except Exception:
                problem_count = 0
        try:
            if summary:
                frame.grid()
            else:
                frame.grid_remove()
        except Exception:
            pass

        selected_rows = self._get_selected_problem_account_rows()
        try:
            btn_show = getattr(self, "_btn_show_only_unmapped", None)
            if btn_show is not None:
                if problem_count:
                    btn_show.state(["!disabled"])
                else:
                    btn_show.state(["disabled"])
            btn_map = getattr(self, "_btn_map_selected_problem", None)
            if btn_map is not None:
                if selected_rows:
                    btn_map.state(["!disabled"])
                else:
                    btn_map.state(["disabled"])
            btn_bulk = getattr(self, "_btn_bulk_map_problem", None)
            if btn_bulk is not None:
                if selected_rows:
                    btn_bulk.state(["!disabled"])
                else:
                    btn_bulk.state(["disabled"])
        except Exception:
            pass

    def _get_selected_problem_account_rows(self) -> List[tuple[str, str]]:
        rows: List[tuple[str, str]] = []
        wanted = {str(v).strip() for v in getattr(self, "_mapping_problem_accounts", []) if str(v).strip()}
        if not wanted:
            return rows
        tree = getattr(self, "_pivot_tree", None)
        if tree is None:
            return rows
        try:
            selected = list(tree.selection())
        except Exception:
            selected = []
        if not selected:
            try:
                focused = tree.focus()
            except Exception:
                focused = ""
            if focused:
                selected = [focused]
        for item in selected:
            try:
                konto = str(tree.set(item, "Konto") or "").strip()
            except Exception:
                konto = ""
            if not konto or konto not in wanted:
                continue
            try:
                kontonavn = str(tree.set(item, "Kontonavn") or "").strip()
            except Exception:
                kontonavn = ""
            rows.append((konto, kontonavn))
        return rows

    def _focus_problem_account(self, konto: str) -> None:
        tree = getattr(self, "_pivot_tree", None)
        if tree is None:
            return
        target = str(konto or "").strip()
        if not target:
            return
        try:
            items = tree.get_children("")
        except Exception:
            items = ()
        for item in items:
            try:
                value = str(tree.set(item, "Konto") or "").strip()
            except Exception:
                value = ""
            if value != target:
                continue
            try:
                tree.selection_set((item,))
            except Exception:
                pass
            try:
                tree.focus(item)
            except Exception:
                pass
            try:
                tree.see(item)
            except Exception:
                pass
            break
        self._update_mapping_warning_banner()
        try:
            self._refresh_transactions_view()
        except Exception:
            pass

    def _show_only_unmapped_accounts(self) -> None:
        try:
            self._var_aggregering.set("Konto")
        except Exception:
            pass
        try:
            if self._var_tx_view_mode is not None:
                self._var_tx_view_mode.set("Saldobalansekontoer")
        except Exception:
            pass
        try:
            if self._var_show_only_unmapped is not None:
                self._var_show_only_unmapped.set(True)
        except Exception:
            pass
        try:
            self._refresh_pivot()
        except Exception:
            pass
        accounts = [str(v).strip() for v in getattr(self, "_mapping_problem_accounts", []) if str(v).strip()]
        if accounts:
            self._focus_problem_account(accounts[0])

    def _on_show_only_unmapped_changed(self, _event=None) -> None:
        try:
            if self._var_show_only_unmapped is not None and bool(self._var_show_only_unmapped.get()):
                self._var_aggregering.set("Konto")
        except Exception:
            pass
        try:
            self._refresh_pivot()
        except Exception:
            pass
        try:
            self._refresh_transactions_view()
        except Exception:
            pass

    def _map_selected_problem_account(self) -> None:
        rows = self._get_selected_problem_account_rows()
        if not rows:
            return
        import page_analyse_sb

        konto, kontonavn = rows[0]
        page_analyse_sb.remap_sb_account(page=self, konto=konto, kontonavn=kontonavn)
        try:
            self._refresh_mapping_issues()
            self._refresh_pivot()
            self._focus_problem_account(konto)
        except Exception:
            pass

    def _bulk_map_selected_problem_accounts(self) -> None:
        rows = self._get_selected_problem_account_rows()
        if not rows:
            return
        import page_analyse_sb

        page_analyse_sb._remap_multiple_sb_accounts(page=self, kontoer=rows)
        try:
            self._refresh_mapping_issues()
            self._refresh_pivot()
            if rows:
                self._focus_problem_account(rows[0][0])
        except Exception:
            pass

    def _update_ao_count_label(self) -> None:
        """Vis antall tilleggsposteringer ved ÅO-checkboxen."""
        lbl = getattr(self, "_ao_count_label", None)
        if lbl is None:
            return
        try:
            import regnskap_client_overrides
            client = getattr(session, "client", None) or ""
            year = str(getattr(session, "year", "") or "")
            if client and year:
                entries = regnskap_client_overrides.load_supplementary_entries(client, year)
                count = len(entries)
                lbl.configure(text=f"({count})" if count else "")
            else:
                lbl.configure(text="")
        except Exception:
            lbl.configure(text="")

    def _has_transactions(self) -> bool:
        """Sjekk om transaksjonsdata er tilgjengelig (ikke bare SB)."""
        df = getattr(self, "dataset", None)
        if df is None:
            return False
        if isinstance(df, pd.DataFrame) and df.empty:
            return False
        return True

    def _update_data_level(self) -> None:
        """Oppdater datanivå-indikator og aktiver/deaktiver TX-avhengige funksjoner."""
        has_tx = self._has_transactions()
        sb_df = getattr(self, "_rl_sb_df", None)
        has_sb = sb_df is not None and isinstance(sb_df, pd.DataFrame) and not sb_df.empty

        if has_tx:
            level = "Hovedbok"
        elif has_sb:
            level = "Kun saldobalanse"
        else:
            level = ""
        self._var_data_level.set(level)

        # Deaktiver TX-visning i TB-only
        tx_combo = getattr(self, "_tx_view_combo", None)
        if tx_combo is not None:
            try:
                if has_tx:
                    tx_combo.state(["!disabled"])
                else:
                    tx_combo.state(["disabled"])
                    # Tving SB-modus om transaksjoner mangler
                    if has_sb and not has_tx:
                        try:
                            self._var_tx_view_mode.set("Saldobalansekontoer")
                        except Exception:
                            pass
            except Exception:
                pass

    def _select_all_accounts(self) -> None:
        page_analyse_pivot.select_all_accounts(page=self)

    def _get_selected_accounts(self) -> List[str]:
        return page_analyse_pivot.get_selected_accounts(page=self)

    def _on_tx_view_mode_changed(self, _event=None) -> None:
        """Bruker bytter mellom Transaksjoner og Saldobalansekontoer."""
        try:
            self._refresh_transactions_view()
        except Exception as exc:
            import logging
            logging.getLogger("app").error("_on_tx_view_mode_changed error: %s", exc, exc_info=True)

    def _refresh_transactions_view(self) -> None:
        mode = ""
        try:
            mode = str(self._var_tx_view_mode.get()) if self._var_tx_view_mode else ""
        except Exception:
            pass

        if mode == "Saldobalansekontoer":
            page_analyse_sb.show_sb_tree(page=self)
            page_analyse_sb.refresh_sb_view(page=self)
            return

        if mode == "Nøkkeltall":
            page_analyse_sb.show_nk_view(page=self)
            self._refresh_nokkeltall_view()
            return

        # Bytt tilbake til TX-modus
        page_analyse_sb.show_tx_tree(page=self)
        self._configure_tx_tree_columns()
        page_analyse_transactions.refresh_transactions_view(page=self)

    def _refresh_nokkeltall_view(self) -> None:
        """Beregn og vis nøkkeltall inline i _nk_text-widgeten."""
        nk_text = getattr(self, "_nk_text", None)
        if nk_text is None:
            return

        try:
            import nokkeltall_engine
        except Exception:
            return

        # Hent rl_df via eksisterende eksport-logikk
        try:
            payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=self)
        except Exception:
            payload = {}
        rl_df = payload.get("rl_df")
        if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
            _nk_write(nk_text, "Ingen regnskapsdata tilgjengelig.\n\nLast inn HB-data og velg klient.")
            return

        # Legg til fjorårskolonner hvis tilgjengelig
        pivot_df = getattr(self, "_pivot_df_last", None)
        if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
            rl_df = rl_df.copy()
            for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
                if col in pivot_df.columns and col not in rl_df.columns:
                    merged = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                    rl_df = rl_df.merge(merged, on="regnr", how="left")

        client = str(payload.get("client") or "").strip()
        year = str(payload.get("year") or "").strip()

        try:
            result = nokkeltall_engine.compute_nokkeltall(rl_df, client=client, year=year)
        except Exception as exc:
            _nk_write(nk_text, f"Feil ved beregning av nøkkeltall:\n{exc}")
            return

        _nk_render(nk_text, result)

    def _refresh_detail_panel(self) -> None:
        page_analyse_detail_panel.refresh_detail_panel(self)

    def _on_detail_account_select(self, _event=None) -> None:
        page_analyse_detail_panel.on_detail_account_selected(self, _event)

    def _focus_detail_panel(self) -> bool:
        return page_analyse_detail_panel.focus_detail_panel(self)

    def _open_mapping_dialog_for_selected_detail_account(self) -> None:
        page_analyse_detail_panel.open_mapping_dialog_for_selected_account(self, messagebox=messagebox)

    def _remove_override_for_selected_detail_account(self) -> None:
        page_analyse_detail_panel.remove_override_for_selected_account(self, messagebox=messagebox)

    def _apply_suggestion_for_selected_detail_account(self) -> None:
        page_analyse_detail_panel.apply_suggestion_for_selected_account(self, messagebox=messagebox)

    def _reject_suggestion_for_selected_detail_account(self) -> None:
        page_analyse_detail_panel.reject_suggestion_for_selected_account(self, messagebox=messagebox)

    def _explain_selected_detail_account(self) -> None:
        page_analyse_detail_panel.explain_selected_account(self, messagebox=messagebox)

    def _jump_to_nr_series_context(self, context: dict[str, object]) -> None:
        page_analyse_detail_panel.jump_to_analysis_context(self, context)

    def _restore_rl_pivot_selection(self, regnr_values: List[int]) -> None:
        tree = getattr(self, "_pivot_tree", None)
        if tree is None:
            return

        wanted: set[int] = set()
        for value in regnr_values:
            try:
                wanted.add(int(value))
            except Exception:
                continue
        if not wanted:
            return

        items_to_select = []
        try:
            items = tree.get_children("")
        except Exception:
            items = ()

        for item in items:
            try:
                regnr = int(str(tree.set(item, "Konto") or "").strip())
            except Exception:
                continue
            if regnr in wanted:
                items_to_select.append(item)

        if not items_to_select:
            return

        try:
            tree.selection_set(items_to_select)
        except Exception:
            pass

        first = items_to_select[0]
        try:
            tree.focus(first)
        except Exception:
            pass
        try:
            tree.see(first)
        except Exception:
            pass

    def _reload_rl_drilldown_df(self, regnr_filter: List[int]) -> pd.DataFrame:
        cols = ["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]

        try:
            import page_analyse_rl
        except Exception:
            return pd.DataFrame(columns=cols)

        try:
            self._refresh_pivot()
        except Exception:
            pass
        self._restore_rl_pivot_selection(regnr_filter)
        try:
            self._refresh_transactions_view()
        except Exception:
            pass

        df_filtered = getattr(self, "_df_filtered", None)
        intervals = getattr(self, "_rl_intervals", None)
        regnskapslinjer = getattr(self, "_rl_regnskapslinjer", None)
        try:
            sb_df = self._get_effective_sb_df()
        except Exception:
            sb_df = getattr(self, "_rl_sb_df", None)

        if not isinstance(df_filtered, pd.DataFrame) or intervals is None or regnskapslinjer is None:
            return pd.DataFrame(columns=cols)

        try:
            account_overrides = page_analyse_rl._load_current_client_account_overrides()
        except Exception:
            account_overrides = None

        try:
            return page_analyse_rl.build_rl_account_drilldown(
                df_filtered,
                intervals,
                regnskapslinjer,
                sb_df=sb_df,
                regnr_filter=regnr_filter,
                account_overrides=account_overrides,
            )
        except Exception:
            return pd.DataFrame(columns=cols)

    def _open_rl_drilldown_from_pivot_selection(self) -> None:
        agg_mode = ""
        try:
            agg_mode = str(self._var_aggregering.get()) if self._var_aggregering is not None else ""
        except Exception:
            agg_mode = ""

        if agg_mode != "Regnskapslinje":
            return

        if getattr(self, "_detail_accounts_tree", None) is not None:
            try:
                if self._focus_detail_panel():
                    return
            except Exception:
                pass

        try:
            import page_analyse_rl
            drill_df, selected_rows = page_analyse_rl.build_selected_rl_account_drilldown(page=self)
        except Exception:
            drill_df = None
            selected_rows = []

        if drill_df is None or drill_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("RL-drilldown", "Velg minst én regnskapslinje med kontoer i scope.")
                except Exception:
                    pass
            return

        if _open_rl_account_drilldown is None:
            if messagebox is not None:
                try:
                    messagebox.showerror("RL-drilldown", "RL-drilldown er ikke tilgjengelig (mangler GUI-støtte).")
                except Exception:
                    pass
            return

        if len(selected_rows) == 1:
            regnr, navn = selected_rows[0]
            title = f"RL-drilldown: {regnr} {navn}".strip()
        else:
            title = f"RL-drilldown: {len(selected_rows)} regnskapslinjer"

        regnr_filter = [regnr for regnr, _ in selected_rows]

        def _reload_callback() -> pd.DataFrame:
            return self._reload_rl_drilldown_df(regnr_filter)

        try:
            _open_rl_account_drilldown(
                self,
                drill_df,
                title=title,
                client=getattr(session, "client", None),
                regnskapslinjer=getattr(self, "_rl_regnskapslinjer", None),
                reload_callback=_reload_callback,
            )
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("RL-drilldown", f"Kunne ikke åpne RL-drilldown.\n\n{exc}")
                except Exception:
                    pass

    # -----------------------------------------------------------------
    # Bilagsdrilldown (Analyse)
    # -----------------------------------------------------------------

    def _get_selected_bilag_from_tx_tree(self) -> str:
        return page_analyse_transactions.get_selected_bilag_from_tx_tree(page=self)

    def _open_bilag_drilldown_from_tx_selection(self) -> None:
        bilag = self._get_selected_bilag_from_tx_tree()
        if not bilag:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Bilagsdrill", "Velg en transaksjon i listen først.")
                except Exception:
                    pass
            return
        self._open_bilag_drilldown_for_bilag(bilag)

    def _open_bilag_drilldown_for_bilag(self, bilag_value: str) -> None:
        page_analyse_actions_impl.open_bilag_drilldown_for_bilag(
            page=self,
            bilag_value=bilag_value,
            open_bilag_drill_dialog=_open_bilag_drill_dialog,
            messagebox=messagebox,
        )

    # -----------------------------------------------------------------
    # Handlinger (Analyse)
    # -----------------------------------------------------------------

    def _send_to_utvalg(self) -> None:
        """Alias for bakoverkompatibilitet (UI).

        Noen UI-varianter refererer til ``_send_to_utvalg``.
        Den opprinnelige metoden heter ``_send_selected_to_utvalg``.
        """

        self._send_selected_to_utvalg()

    def _open_motpost_analysis(self) -> None:
        """Alias for bakoverkompatibilitet (UI).

        UI kan referere til ``_open_motpost_analysis``.
        Den interne metoden heter ``_open_motpost``.
        """

        self._open_motpost()

    def _open_motpost(self) -> None:
        page_analyse_actions_impl.open_motpost(page=self, messagebox=messagebox, show_motpost_konto=_show_motpost_konto)

    def _open_nr_series_control(self) -> None:
        page_analyse_actions_impl.open_nr_series_control(
            page=self,
            messagebox=messagebox,
            show_nr_series_control=_show_nr_series_control,
        )

    def _open_override_checks(self) -> None:
        page_analyse_actions_impl.open_override_checks(page=self, messagebox=messagebox)

    def _open_mva_config(self) -> None:
        if _open_mva_config_dialog is None:
            if messagebox is not None:
                messagebox.showwarning("MVA-oppsett", "MVA-oppsett-modulen er ikke tilgjengelig.")
            return
        client = getattr(session, "client", None)
        if not client:
            if messagebox is not None:
                messagebox.showwarning("MVA-oppsett", "Ingen klient er valgt.")
            return
        _open_mva_config_dialog(self, client)

    def _open_mva_avstemming(self) -> None:
        try:
            import mva_avstemming_dialog
            mva_avstemming_dialog.open_mva_avstemming(self, page=self)
        except Exception:
            import logging
            logging.getLogger("app").exception("MVA-avstemming feilet")
            if messagebox is not None:
                messagebox.showerror("MVA-avstemming", "Kunne ikke åpne MVA-avstemming.")

    # -----------------------------------------------------------------
    # Selection -> Utvalg
    # -----------------------------------------------------------------

    def _send_to_selection(self, accounts: List[str]) -> None:
        """Internal helper for tests + callback-based wiring."""
        if self._utvalg_callback is not None:
            self._utvalg_callback(accounts)

    def _send_selected_to_utvalg(self) -> None:
        accounts = self._get_selected_accounts()
        if not accounts:
            if getattr(self, "_lbl_tx_summary", None) is not None:
                try:
                    self._lbl_tx_summary.config(text="Ingen kontoer valgt.")
                except Exception:
                    pass
            return
        self._send_to_selection(accounts)

    # -----------------------------------------------------------------
    # Eksport (DataFrame bygging)
    # -----------------------------------------------------------------

    def _prepare_transactions_export_sheets(self) -> dict[str, pd.DataFrame]:
        return page_analyse_export.prepare_transactions_export_sheets(page=self)

    def _prepare_pivot_export_sheets(self) -> dict[str, pd.DataFrame]:
        return page_analyse_export.prepare_pivot_export_sheets(page=self)

    def _export_regnskapsoppstilling_excel(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore

        if filedialog is None:
            if messagebox is not None:
                try:
                    messagebox.showerror("Eksport", "Fil-dialog er ikke tilgjengelig i dette miljøet.")
                except Exception:
                    pass
            return

        payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=self)
        rl_df = payload.get("rl_df")
        if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Eksport", "Fant ingen regnskapsoppstilling å eksportere.")
                except Exception:
                    pass
            return

        client = str(payload.get("client") or "").strip()
        year = str(payload.get("year") or "").strip()
        base_name = "Regnskapsoppstilling"
        if client:
            safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
            if safe_client:
                base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter regnskapsoppstilling",
                defaultextension=".xlsx",
                filetypes=[("Excel workbook", "*.xlsx")],
                initialfile=base_name + ".xlsx",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            import analyse_regnskapsoppstilling_excel

            saved = analyse_regnskapsoppstilling_excel.save_regnskapsoppstilling_workbook(
                path,
                rl_df=rl_df,
                regnskapslinjer=payload.get("regnskapslinjer"),
                transactions_df=payload.get("transactions_df"),
                client=payload.get("client"),
                year=payload.get("year"),
            )
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("Eksport", f"Kunne ikke eksportere regnskapsoppstilling.\n\n{exc}")
                except Exception:
                    pass
            return

        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", f"Regnskapsoppstilling lagret til:\n{saved}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Nøkkeltallsrapport (HTML)
    # ------------------------------------------------------------------

    def _export_nokkeltall_html(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore

        if filedialog is None:
            return

        payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=self)
        rl_df = payload.get("rl_df")
        if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Eksport", "Fant ingen regnskapsdata for nøkkeltallsrapport.")
                except Exception:
                    pass
            return

        # Legg til fjorårskolonner hvis tilgjengelig
        pivot_df = getattr(self, "_pivot_df_last", None)
        if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
            rl_df = rl_df.copy()
            for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
                if col in pivot_df.columns and col not in rl_df.columns:
                    merged = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                    rl_df = rl_df.merge(merged, on="regnr", how="left")

        client = str(payload.get("client") or "").strip()
        year = str(payload.get("year") or "").strip()
        base_name = "Nokkeltall"
        if client:
            safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
            if safe_client:
                base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter nøkkeltallsrapport",
                defaultextension=".html",
                filetypes=[("HTML-rapport", "*.html"), ("Alle filer", "*.*")],
                initialfile=base_name + ".html",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            import nokkeltall_report

            saved = nokkeltall_report.save_report_html(
                path,
                rl_df=rl_df,
                transactions_df=payload.get("transactions_df"),
                client=client,
                year=year,
            )
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("Eksport", f"Kunne ikke generere nøkkeltallsrapport.\n\n{exc}")
                except Exception:
                    pass
            return

        # Åpne i browser
        try:
            import webbrowser
            from pathlib import Path
            webbrowser.open(Path(saved).as_uri())
        except Exception:
            pass

        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", f"Nøkkeltallsrapport lagret og åpnet:\n{saved}")
            except Exception:
                pass

    def _export_nokkeltall_pdf(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore

        if filedialog is None:
            return

        payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=self)
        rl_df = payload.get("rl_df")
        if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Eksport", "Fant ingen regnskapsdata for nøkkeltallsrapport.")
                except Exception:
                    pass
            return

        # Legg til fjorårskolonner hvis tilgjengelig
        pivot_df = getattr(self, "_pivot_df_last", None)
        if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
            rl_df = rl_df.copy()
            for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
                if col in pivot_df.columns and col not in rl_df.columns:
                    merged = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                    rl_df = rl_df.merge(merged, on="regnr", how="left")

        client = str(payload.get("client") or "").strip()
        year = str(payload.get("year") or "").strip()
        base_name = "Nokkeltall"
        if client:
            safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
            if safe_client:
                base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter nøkkeltallsrapport (PDF)",
                defaultextension=".pdf",
                filetypes=[("PDF-rapport", "*.pdf"), ("Alle filer", "*.*")],
                initialfile=base_name + ".pdf",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            import nokkeltall_report

            saved = nokkeltall_report.save_report_pdf(
                path,
                rl_df=rl_df,
                transactions_df=payload.get("transactions_df"),
                client=client,
                year=year,
            )
        except ImportError as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror(
                        "Mangler playwright",
                        f"PDF-eksport krever playwright.\n\nInstaller med:\n"
                        f"pip install playwright\n"
                        f"python -m playwright install chromium\n\n{exc}",
                    )
                except Exception:
                    pass
            return
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("Eksport", f"Kunne ikke generere PDF-rapport.\n\n{exc}")
                except Exception:
                    pass
            return

        # Åpne PDF
        try:
            import os
            os.startfile(saved)
        except Exception:
            pass

        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", f"Nøkkeltallsrapport (PDF) lagret:\n{saved}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Motpost-flytdiagram (HTML/PDF)
    # ------------------------------------------------------------------

    def _build_konto_to_rl(self) -> dict | None:
        """Bygg mapping konto_str → (regnr, rl_name) fra sidens RL-intervaller.

        Returnerer None dersom RL-modus ikke er aktiv eller intervaller mangler.
        Returnerer tom dict dersom mapping ikke kan bygges (fall back til kontonivå).
        """
        agg_var = getattr(self, "_var_aggregering", None)
        if agg_var is None:
            return None
        try:
            mode = str(agg_var.get())
        except Exception:
            return None
        if mode != "Regnskapslinje":
            return None

        intervals = getattr(self, "_rl_intervals", None)
        regnskapslinjer = getattr(self, "_rl_regnskapslinjer", None)
        df = getattr(self, "_df_filtered", None)

        if intervals is None or not isinstance(df, pd.DataFrame) or df.empty:
            return {}

        try:
            from regnskap_mapping import apply_interval_mapping, normalize_regnskapslinjer

            # Bygg rl_name oppslag: regnr → navn (normaliser rådata først)
            rl_name_map: dict[int, str] = {}
            if isinstance(regnskapslinjer, pd.DataFrame) and not regnskapslinjer.empty:
                try:
                    regn = normalize_regnskapslinjer(regnskapslinjer)
                    for _, row in regn.iterrows():
                        try:
                            rl_name_map[int(row["regnr"])] = str(row.get("regnskapslinje", "") or "")
                        except Exception:
                            pass
                except Exception:
                    pass

            # Hent unike kontoer fra HB
            kontos = df["Konto"].dropna().astype(str).str.strip().unique().tolist()
            probe = pd.DataFrame({"konto": kontos})
            result = apply_interval_mapping(probe, intervals, konto_col="konto")
            mapped = result.mapped.dropna(subset=["regnr"])

            konto_to_rl: dict[str, tuple[int, str]] = {}
            for _, row in mapped.iterrows():
                try:
                    regnr = int(row["regnr"])
                    rl_name = rl_name_map.get(regnr, str(regnr))
                    konto_to_rl[str(row["konto"])] = (regnr, rl_name)
                except Exception:
                    pass

            return konto_to_rl
        except Exception:
            return {}

    def _export_motpost_flowchart_html(self) -> None:
        """Eksporter motpost-flytdiagram som HTML for valgte kontoer."""
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore
        if filedialog is None:
            return

        accounts = self._get_selected_accounts()
        if not accounts:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost-flytdiagram", "Velg minst én konto i pivoten først.")
                except Exception:
                    pass
            return

        df = getattr(self, "_df_filtered", None)
        if not isinstance(df, pd.DataFrame) or df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost-flytdiagram", "Ingen transaksjonsdata tilgjengelig.")
                except Exception:
                    pass
            return

        try:
            import session
            client = str(getattr(session, "client", "") or "").strip()
            year = str(getattr(session, "year", "") or "").strip()
        except Exception:
            client, year = "", ""

        base_name = "Motpost-flytdiagram"
        if client:
            safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
            if safe_client:
                base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter motpost-flytdiagram",
                defaultextension=".html",
                filetypes=[("HTML-rapport", "*.html"), ("Alle filer", "*.*")],
                initialfile=base_name + ".html",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            from motpost_flowchart_report import save_flowchart_html

            saved = save_flowchart_html(
                path,
                df=df,
                start_accounts=accounts,
                max_depth=2,
                client=client,
                year=year,
                konto_to_rl=self._build_konto_to_rl(),
            )
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("Motpost-flytdiagram", f"Kunne ikke generere flytdiagram.\n\n{exc}")
                except Exception:
                    pass
            return

        try:
            import webbrowser
            from pathlib import Path
            webbrowser.open(Path(saved).as_uri())
        except Exception:
            pass

        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", f"Flytdiagram lagret og åpnet:\n{saved}")
            except Exception:
                pass

    def _export_motpost_flowchart_pdf(self) -> None:
        """Eksporter motpost-flytdiagram som PDF for valgte kontoer."""
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore
        if filedialog is None:
            return

        accounts = self._get_selected_accounts()
        if not accounts:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost-flytdiagram", "Velg minst én konto i pivoten først.")
                except Exception:
                    pass
            return

        df = getattr(self, "_df_filtered", None)
        if not isinstance(df, pd.DataFrame) or df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost-flytdiagram", "Ingen transaksjonsdata tilgjengelig.")
                except Exception:
                    pass
            return

        try:
            import session
            client = str(getattr(session, "client", "") or "").strip()
            year = str(getattr(session, "year", "") or "").strip()
        except Exception:
            client, year = "", ""

        base_name = "Motpost-flytdiagram"
        if client:
            safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
            if safe_client:
                base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter motpost-flytdiagram (PDF)",
                defaultextension=".pdf",
                filetypes=[("PDF-rapport", "*.pdf"), ("Alle filer", "*.*")],
                initialfile=base_name + ".pdf",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            from motpost_flowchart_report import save_flowchart_pdf

            saved = save_flowchart_pdf(
                path,
                df=df,
                start_accounts=accounts,
                max_depth=2,
                client=client,
                year=year,
                konto_to_rl=self._build_konto_to_rl(),
            )
        except ImportError as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror(
                        "Mangler playwright",
                        f"PDF-eksport krever playwright.\n\nInstaller med:\n"
                        f"pip install playwright\n"
                        f"python -m playwright install chromium\n\n{exc}",
                    )
                except Exception:
                    pass
            return
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("Motpost-flytdiagram", f"Kunne ikke generere PDF.\n\n{exc}")
                except Exception:
                    pass
            return

        try:
            import os
            os.startfile(saved)
        except Exception:
            pass

        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", f"Flytdiagram (PDF) lagret:\n{saved}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # SB/HB Avstemming (IB/UB-kontroll)
    # ------------------------------------------------------------------

    def _export_ib_ub_control(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore

        if filedialog is None:
            return

        import ib_ub_control
        import ib_ub_control_excel
        import page_analyse_rl

        # Hent SB — alltid prøv å laste fra versjon (kan ha blitt opprettet etter siste refresh)
        sb_df = None
        sb_err = ""
        try:
            sb_df = page_analyse_rl.load_sb_for_session()
        except Exception as exc:
            sb_err = str(exc)
        if sb_df is None:
            sb_df = getattr(self, "_rl_sb_df", None)

        # Siste forsøk: last direkte fra client_store
        if sb_df is None or (isinstance(sb_df, pd.DataFrame) and sb_df.empty):
            try:
                import client_store
                from trial_balance_reader import read_trial_balance
                from pathlib import Path as _Path
                _client = getattr(session, "client", None)
                _year = str(getattr(session, "year", None) or "")
                if _client and _year:
                    _v = client_store.get_active_version(_client, year=_year, dtype="sb")
                    if _v is not None:
                        _sbp = _Path(_v.path)
                        if _sbp.exists():
                            sb_df = read_trial_balance(_sbp)
                        else:
                            sb_err = f"SB-fil finnes ikke: {_sbp}"
                    else:
                        sb_err = f"Ingen aktiv SB-versjon for {_client}/{_year}"
                else:
                    sb_err = f"session.client={_client!r}, session.year={_year!r}"
            except Exception as exc:
                sb_err = str(exc)

        if sb_df is None or (isinstance(sb_df, pd.DataFrame) and sb_df.empty):
            if messagebox is not None:
                try:
                    detail = f"\n\nDetalj: {sb_err}" if sb_err else ""
                    messagebox.showinfo(
                        "SB/HB Avstemming",
                        "Ingen saldobalanse tilgjengelig.\n\n"
                        "Last inn en saldobalanse (SB) via Versjoner-dialogen for å bruke denne funksjonen."
                        + detail,
                    )
                except Exception:
                    pass
            return

        # Hent HB
        hb_df = getattr(self, "_df_filtered", None)
        if hb_df is None or not isinstance(hb_df, pd.DataFrame) or hb_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("SB/HB Avstemming", "Ingen hovedbok-data å avstemme mot.")
                except Exception:
                    pass
            return

        # RL-mapping (valgfri)
        intervals = getattr(self, "_rl_intervals", None)
        regnskapslinjer = getattr(self, "_rl_regnskapslinjer", None)

        account_overrides = None
        try:
            account_overrides = page_analyse_rl._load_current_client_account_overrides()
        except Exception:
            pass

        # Beregn
        try:
            result = ib_ub_control.reconcile(
                sb_df,
                hb_df,
                intervals=intervals,
                regnskapslinjer=regnskapslinjer,
                account_overrides=account_overrides,
            )
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("SB/HB Avstemming", f"Feil ved beregning av avstemming.\n\n{exc}")
                except Exception:
                    pass
            return

        # Filnavn
        client = getattr(session, "client", None) or ""
        year = getattr(session, "year", None) or ""
        base_name = "SB_HB_Avstemming"
        if client:
            safe = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in str(client)).strip()
            if safe:
                base_name += f" {safe}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter SB/HB-avstemming",
                defaultextension=".xlsx",
                filetypes=[("Excel workbook", "*.xlsx")],
                initialfile=base_name + ".xlsx",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            wb = ib_ub_control_excel.build_ib_ub_workpaper(
                result.account_level,
                rl_recon=result.rl_level,
                summary=result.summary,
                client=client,
                year=year,
            )
            wb.save(path)
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("SB/HB Avstemming", f"Kunne ikke lagre arbeidspapir.\n\n{exc}")
                except Exception:
                    pass
            return

        # Suksessmelding med avviksoversikt
        n_avvik = result.summary.get("antall_avvik", 0)
        total_diff = result.summary.get("total_differanse", 0)
        msg = f"Arbeidspapir lagret til:\n{path}\n\n"
        if n_avvik == 0:
            msg += "✓ Ingen avvik funnet — SB og HB stemmer overens."
        else:
            msg += f"⚠ {n_avvik} konto(er) med avvik.\nTotal differanse: {formatting.fmt_amount(total_diff)}"

        if messagebox is not None:
            try:
                messagebox.showinfo("SB/HB Avstemming", msg)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # HB Versjonsdiff
    # ------------------------------------------------------------------

    def _export_hb_version_diff(self) -> None:
        """Sammenlign gjeldende HB med en tidligere versjon og eksporter diff."""
        try:
            from tkinter import filedialog
        except Exception:
            filedialog = None  # type: ignore

        if filedialog is None:
            return

        import client_store

        client = getattr(session, "client", None) or ""
        year = str(getattr(session, "year", None) or "")

        if not client or not year:
            if messagebox is not None:
                try:
                    messagebox.showinfo("HB Versjonsdiff", "Ingen klient/år valgt.")
                except Exception:
                    pass
            return

        # Hent alle HB-versjoner
        try:
            versions = client_store.list_versions(client, year=year, dtype="hb")
        except Exception:
            versions = []

        if len(versions) < 2:
            if messagebox is not None:
                try:
                    messagebox.showinfo(
                        "HB Versjonsdiff",
                        "Du trenger minst 2 HB-versjoner for å sammenligne.\n\n"
                        "Importer en ny hovedbok via Versjoner-dialogen.",
                    )
                except Exception:
                    pass
            return

        active_id = None
        try:
            active_id = client_store.get_active_version_id(client, year=year, dtype="hb")
        except Exception:
            pass

        # Velg versjon å sammenligne med
        chosen_id = self._pick_hb_version(versions, active_id)
        if not chosen_id:
            return

        # Last gammel versjon
        old_df = self._load_hb_version_df(client, year, chosen_id)
        if old_df is None or old_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showerror("HB Versjonsdiff", "Kunne ikke laste valgt versjon.")
                except Exception:
                    pass
            return

        # Gjeldende HB
        current_df = getattr(self, "_df_filtered", None)
        if current_df is None or not isinstance(current_df, pd.DataFrame):
            current_df = getattr(self, "dataset", None)
        if current_df is None or not isinstance(current_df, pd.DataFrame) or current_df.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("HB Versjonsdiff", "Ingen aktiv hovedbok å sammenligne med.")
                except Exception:
                    pass
            return

        # Beregn diff
        import hb_version_diff
        import hb_version_diff_excel

        try:
            result = hb_version_diff.diff_hb_versions(old_df, current_df)
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("HB Versjonsdiff", f"Feil ved beregning av diff.\n\n{exc}")
                except Exception:
                    pass
            return

        # Finn versjonsnavn
        old_label = "Forrige"
        current_label = "Gjeldende"
        try:
            old_v = client_store.get_version(client, year=year, dtype="hb", version_id=chosen_id)
            if old_v:
                from pathlib import Path as _Path
                old_label = _Path(old_v.filename or old_v.path).stem
        except Exception:
            pass

        # Filnavn
        base_name = "HB_Versjonsdiff"
        safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in str(client)).strip()
        if safe_client:
            base_name += f" {safe_client}"
        if year:
            base_name += f" {year}"

        try:
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Eksporter HB versjonsdiff",
                defaultextension=".xlsx",
                filetypes=[("Excel workbook", "*.xlsx")],
                initialfile=base_name + ".xlsx",
            )
        except Exception:
            path = ""

        if not path:
            return

        try:
            wb = hb_version_diff_excel.build_hb_diff_workpaper(
                result,
                client=client,
                year=year,
                version_a_label=old_label,
                version_b_label=current_label,
            )
            wb.save(path)
        except Exception as exc:
            if messagebox is not None:
                try:
                    messagebox.showerror("HB Versjonsdiff", f"Kunne ikke lagre.\n\n{exc}")
                except Exception:
                    pass
            return

        # Suksessmelding
        s = result.summary
        msg = f"Versjonsdiff lagret til:\n{path}\n\n"
        msg += f"Nye bilag: {s.get('nye_bilag', 0)}\n"
        msg += f"Fjernede bilag: {s.get('fjernede_bilag', 0)}\n"
        msg += f"Endrede bilag: {s.get('endrede_bilag', 0)}\n"
        msg += f"Uendrede bilag: {s.get('uendrede_bilag', 0)}"

        if messagebox is not None:
            try:
                messagebox.showinfo("HB Versjonsdiff", msg)
            except Exception:
                pass

    def _pick_hb_version(self, versions, active_id) -> Optional[str]:
        """Enkel dialog for å velge en HB-versjon å sammenligne med."""
        if tk is None:
            return None

        from pathlib import Path as _Path
        from datetime import datetime as _dt

        result_var = {"id": None}

        top = tk.Toplevel(self)
        top.title("Velg HB-versjon å sammenligne med")
        top.geometry("480x320")
        top.transient(self)
        top.grab_set()

        ttk.Label(top, text="Velg en tidligere versjon å sammenligne mot gjeldende HB:").pack(
            padx=10, pady=(10, 5), anchor="w",
        )

        frame = ttk.Frame(top)
        frame.pack(fill="both", expand=True, padx=10, pady=5)

        tree = ttk.Treeview(frame, columns=("name", "date"), show="headings", selectmode="browse")
        tree.heading("name", text="Fil")
        tree.heading("date", text="Importert")
        tree.column("name", width=280)
        tree.column("date", width=150)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for v in reversed(versions):
            if v.id == active_id:
                continue
            name = _Path(v.filename or v.path).name
            try:
                ts = _dt.fromtimestamp(v.created_at).strftime("%d.%m.%Y %H:%M")
            except Exception:
                ts = ""
            tree.insert("", "end", iid=v.id, values=(name, ts))

        def on_ok():
            sel = tree.selection()
            if sel:
                result_var["id"] = sel[0]
            top.destroy()

        def on_cancel():
            top.destroy()

        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill="x", padx=10, pady=(5, 10))
        ttk.Button(btn_frame, text="Sammenlign", command=on_ok).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Avbryt", command=on_cancel).pack(side="right")

        tree.bind("<Double-1>", lambda e: on_ok())

        top.wait_window()
        return result_var["id"]

    def _load_hb_version_df(self, client: str, year: str, version_id: str) -> Optional[pd.DataFrame]:
        """Last en HB-versjon som DataFrame."""
        import client_store

        v = client_store.get_version(client, year=year, dtype="hb", version_id=version_id)
        if v is None:
            return None

        # Forsøk cache først
        try:
            dc = (v.meta or {}).get("dataset_cache", {})
            if isinstance(dc, dict) and dc.get("file"):
                from pathlib import Path as _Path
                import dataset_cache_sqlite
                ds_dir = client_store.datasets_dir(client, year=year, dtype="hb")
                db_path = ds_dir / str(dc["file"])
                if db_path.exists():
                    df, _ = dataset_cache_sqlite.load_cache(db_path)
                    if df is not None and not df.empty:
                        return df
        except Exception:
            pass

        # Fallback: bygg fra fil med lagret mapping
        try:
            from pathlib import Path as _Path
            from dataset_build_fast import build_from_file

            build_info = ((v.meta or {}).get("dataset_cache") or {}).get("build") or {}
            mapping = build_info.get("mapping")
            sheet_name = build_info.get("sheet_name")
            header_row = build_info.get("header_row", 1)

            p = _Path(v.path)
            if not p.exists():
                return None

            df = build_from_file(
                p,
                mapping=mapping,
                sheet_name=sheet_name,
                header_row=header_row,
            )
            return df
        except Exception:
            return None
