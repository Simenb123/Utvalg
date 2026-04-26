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
import page_analyse_refresh
import page_analyse_sb
import page_analyse_transactions
import page_analyse_ui
import analyse_drilldown
import analyse_mapping_ui
import analyse_workpaper_export

log = logging.getLogger(__name__)

try:
    from ui_treeview_sort import enable_treeview_sorting as _enable_treeview_sorting
except Exception:  # pragma: no cover
    _enable_treeview_sorting = None  # type: ignore

try:
    from selection_studio.drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
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



from page_analyse_nokkeltall_render import (  # noqa: E402,F401
    _BS_BRREG_MAP,
    _PL_BRREG_MAP,
    _fmt_amount,
    _nk_insert_brreg_bs_comparison,
    _nk_insert_brreg_pl_comparison,
    _nk_render,
    _nk_write,
)



class AnalysePage(ttk.Frame):  # type: ignore[misc]
    """GUI-side for analyse."""

    PIVOT_COLS = (
        "Konto",
        "Kontonavn",
        "OK",
        "IB",
        "Endring",
        "Sum",
        "AO_belop",
        "UB_for_ao",
        "UB_etter_ao",
        "Antall",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "BRREG",
        "Avvik_brreg",
        "Avvik_brreg_pct",
    )

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
            self._sb_col_widths = {}
            self._sb_cols_order = list(page_analyse_columns.SB_PINNED_COLS)
            self._sb_cols_visible = list(page_analyse_columns.SB_PINNED_COLS)
            self._pivot_visible_cols = list(self.PIVOT_COLS_DEFAULT_VISIBLE)
            self._var_tx_view_mode = None
            self._sb_tree = None
            self._sb_frame = None
            self._tx_frame = None
            self._tx_header_drag = None
            self._pivot_balance_after_id = None
            self._mapping_warning_var = None
            self._mapping_banner_frame = None
            self._var_data_level = None
            self._detail_selected_account = ""
            self._detail_selected_account_explicit = False
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
        self._detail_selected_account_explicit: bool = False
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
        self._var_hide_zero = tk.BooleanVar(value=True)
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
        self._sb_col_widths = self._load_saved_column_widths("analyse.sb_cols.widths")
        self._sb_cols_order: List[str] = list(page_analyse_columns.SB_PINNED_COLS)
        self._sb_cols_visible: List[str] = list(page_analyse_columns.SB_PINNED_COLS)
        page_analyse_columns.load_sb_columns_from_preferences(page=self)
        self._pivot_visible_cols: List[str] = list(self.PIVOT_COLS_DEFAULT_VISIBLE)
        self._load_pivot_visible_columns()
        self._pivot_first_load = True
        self._tx_first_load = True

        # --- SB/transaksjonsvisning toggle ---
        self._var_tx_view_mode = tk.StringVar(value="Saldobalanse")
        try:
            self._var_tx_view_mode.trace_add(
                "write",
                lambda *_a: self._on_tx_view_mode_changed(),
            )
        except Exception:
            pass
        # Tall vises uten desimaler som standard — brukerne ønsket
        # rundere, mindre støyete tall ved første visning. De kan slå
        # på via Visning ▾ → Desimaler. Gjelder både venstre pivot og
        # høyre TX/SB/MVA-visninger.
        self._var_decimals = tk.BooleanVar(value=False)

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
        page_analyse_refresh.refresh_from_session(self, sess, defer_heavy=defer_heavy)

    def _run_full_refresh(self) -> None:
        page_analyse_refresh.run_full_refresh(self)

    def _schedule_heavy_refresh(self) -> None:
        page_analyse_refresh.schedule_heavy_refresh(self)

    def _run_heavy_refresh_staged(self, generation: int | None = None) -> None:
        page_analyse_refresh.run_heavy_refresh_staged(
            self, generation, dir_options=_DIR_OPTIONS,
        )

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
        """Bytt mellom Saldobalanse og Regnskapslinje."""
        # Migrer legacy-verdier (Konto, SB-konto, HB-konto, MVA-kode) til "Saldobalanse"
        # slik at eldre prefs/kode som setter dem eksternt fortsatt virker.
        try:
            if self._var_aggregering is not None:
                raw = str(self._var_aggregering.get() or "").strip()
                if raw in ("Konto", "SB-konto", "HB-konto", "MVA-kode"):
                    self._var_aggregering.set("Saldobalanse")
        except Exception:
            pass
        # Bytt KUN visning — ikke kjør hele filter-rørledningen på nytt.
        # _apply_filters_and_refresh ville bygd _df_filtered fra scratch (nytt
        # DataFrame-objekt), noe som invaliderte alle id()-baserte cacher i
        # mapping_issues og rl_pivot. Mode-bytte trenger ikke ny filtrering;
        # bare ny pivot-visning + transaksjonsoppdatering.
        try:
            self._refresh_pivot()
        except Exception:
            pass
        try:
            self._refresh_transactions_view()
        except Exception:
            pass
        # Tilpass synlige kolonner etter pivot-refresh (headings er nå oppdatert)
        self._adapt_pivot_columns_for_mode()
        # Sortering: aktiver i konto-moduser, deaktiver i RL-modus
        self._refresh_pivot_sorting()

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
    # HB-konto: ren HB-pivot (ingen komparative kolonner)
    PIVOT_COLS_DEFAULT_HB_KONTO = ("Konto", "Kontonavn", "Sum", "Antall")
    # SB-konto: komparativ, samme layout som RL-modus per konto
    PIVOT_COLS_DEFAULT_SB_KONTO = (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )
    # Legacy alias (tidligere "Konto"-modus) – bevart for bakoverkompatibilitet.
    PIVOT_COLS_DEFAULT_KONTO = PIVOT_COLS_DEFAULT_HB_KONTO
    PIVOT_COLS_DEFAULT_RL = (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )
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

    # -----------------------------------------------------------------
    # SB-kolonner (Saldobalansekontoer-visning)
    # -----------------------------------------------------------------

    def _open_sb_column_chooser(self) -> None:
        page_analyse_columns.open_sb_column_chooser(page=self)

    def _reset_sb_columns_to_default(self) -> None:
        page_analyse_columns.reset_sb_columns_to_default(page=self)

    def _configure_sb_tree_columns(self) -> None:
        page_analyse_columns.configure_sb_tree_columns(page=self)

    def _open_column_chooser(self) -> None:
        """Dispatcher: \u00e5pner riktig kolonnevelger basert p\u00e5 aktiv visning."""
        from page_analyse_columns import normalize_view_mode

        mode = ""
        try:
            mode = normalize_view_mode(self._var_tx_view_mode.get())
        except Exception:
            pass
        if mode == "Saldobalansekontoer":
            self._open_sb_column_chooser()
        else:
            self._open_tx_column_chooser()

    def _open_advanced_filters(self) -> None:
        """Popup-dialog for sjelden brukte filtre: MVA-kode, Min/Maks beløp.

        StringVars deles med toolbaren — endringer i dialogen propageres
        automatisk til filter-logikken via eksisterende StringVar-trace.
        """
        if not getattr(self, "_tk_ok", False):
            return

        existing = getattr(self, "_advanced_filters_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_set()
                    return
            except Exception:
                pass

        try:
            dlg = tk.Toplevel(self)
        except Exception:
            return

        dlg.title("Mer filter")
        try:
            dlg.transient(self.winfo_toplevel())
        except Exception:
            pass
        dlg.resizable(False, False)

        body = ttk.Frame(dlg, padding=(12, 10, 12, 10))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        var_mva_code = getattr(self, "_var_mva_code", None)
        mva_code_values = list(
            getattr(self, "_mva_code_values", [])
            or [getattr(self, "MVA_CODE_ALL_LABEL", "Alle")]
        )
        ttk.Label(body, text="MVA-kode:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        cmb_mva_code = ttk.Combobox(
            body,
            textvariable=var_mva_code,
            values=mva_code_values,
            width=18,
            state="readonly",
        )
        cmb_mva_code.grid(row=0, column=1, sticky="we", padx=(8, 0), pady=(0, 6))

        var_min = getattr(self, "_var_min", None)
        ttk.Label(body, text="Min beløp:").grid(row=1, column=0, sticky="w", pady=(0, 6))
        ent_min = ttk.Entry(body, textvariable=var_min, width=20)
        ent_min.grid(row=1, column=1, sticky="we", padx=(8, 0), pady=(0, 6))

        var_max = getattr(self, "_var_max", None)
        ttk.Label(body, text="Maks beløp:").grid(row=2, column=0, sticky="w", pady=(0, 6))
        ent_max = ttk.Entry(body, textvariable=var_max, width=20)
        ent_max.grid(row=2, column=1, sticky="we", padx=(8, 0), pady=(0, 6))

        button_row = ttk.Frame(dlg, padding=(12, 0, 12, 10))
        button_row.grid(row=1, column=0, sticky="ew")
        button_row.columnconfigure(0, weight=1)

        def _on_close() -> None:
            self._advanced_filters_dialog = None
            self._cmb_mva_code = None
            try:
                dlg.destroy()
            except Exception:
                pass

        ttk.Button(button_row, text="Lukk", command=_on_close).grid(row=0, column=1, sticky="e")
        dlg.protocol("WM_DELETE_WINDOW", _on_close)
        dlg.bind("<Escape>", lambda _e: _on_close())
        dlg.bind("<Return>", lambda _e: _on_close())

        # La refresh_mva_codes oppdatere comboen mens dialogen er åpen.
        self._cmb_mva_code = cmb_mva_code
        self._advanced_filters_dialog = dlg

        try:
            dlg.update_idletasks()
            x = self.winfo_rootx() + 80
            y = self.winfo_rooty() + 80
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass

        try:
            ent_min.focus_set()
        except Exception:
            pass

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

    def _on_pivot_tree_mouse_press(self, event=None):
        page_analyse_columns.on_pivot_tree_mouse_press(page=self, event=event)

    def _on_pivot_tree_mouse_drag(self, event=None):
        page_analyse_columns.on_pivot_tree_mouse_drag(page=self, event=event)

    def _refresh_pivot_sorting(self) -> None:
        page_analyse_columns.refresh_pivot_sorting(
            page=self, enable_fn=_enable_treeview_sorting)

    def _reset_pivot_column_widths(self) -> None:
        page_analyse_columns.reset_pivot_column_widths(page=self)

    def _reset_all_column_widths(self) -> None:
        page_analyse_columns.reset_pivot_column_widths(page=self)
        page_analyse_columns.reset_tx_column_widths(page=self)

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
    def _on_pivot_search(self, query: str) -> None:
        """Søk og hopp til konto i pivottreet."""
        tree = getattr(self, "_pivot_tree", None)
        if tree is None:
            return
        if not query:
            return

        query = query.lower()
        for iid in tree.get_children(""):
            try:
                vals = tree.item(iid, "values")
                # Søk i alle kolonneverdier (konto, kontonavn, etc.)
                row_text = " ".join(str(v).lower() for v in vals)
                if query in row_text:
                    tree.selection_set(iid)
                    tree.see(iid)
                    tree.focus(iid)
                    return
            except Exception:
                continue

    def _on_pivot_select(self, _event=None) -> None:
        """Når bruker velger konto(er) i pivotlisten, oppdater transaksjonslisten.

        UI (page_analyse_ui) binder <<TreeviewSelect>> til denne hooken.
        """
        # Per-fase stoppeklokker — vi logger til monitoren så vi ser hvilken
        # del som er treg når bruker bytter mellom regnskapslinjer.
        import time as _time
        try:
            from src.monitoring.perf import record_event as _record_event
        except Exception:
            _record_event = None  # type: ignore[assignment]

        def _tick(label: str, fn) -> None:
            t0 = _time.perf_counter()
            try:
                fn()
            except Exception:
                pass
            if _record_event is not None:
                try:
                    _record_event(
                        f"analyse.pivot_select.{label}",
                        (_time.perf_counter() - t0) * 1000.0,
                    )
                except Exception:
                    pass

        t_total = _time.perf_counter()

        def _reset_detail() -> None:
            import page_analyse_detail_panel
            page_analyse_detail_panel.reset_detail_selection(self)

        _tick("reset_detail", _reset_detail)
        _tick("mapping_banner", self._update_mapping_warning_banner)
        _tick("transactions_view", self._refresh_transactions_view)
        _tick("detail_panel", self._refresh_detail_panel)

        if _record_event is not None:
            try:
                _record_event(
                    "analyse.pivot_select.total",
                    (_time.perf_counter() - t_total) * 1000.0,
                )
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
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
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
        try:
            self._refresh_nokkeltall_view()
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
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
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
        # Profile-blokken bryter ned _refresh_pivot pr underkalle slik at
        # vi vet om treghet ligger i mapping-issues, refresh_pivot, AO-label
        # eller mapping-warning.
        #
        # Timing-events sendes til src.monitoring.perf. Sett UTVALG_PROFILE=analyse
        # (eller bakoverkompat UTVALG_PROFILE_REFRESH=1) for å se dem på stderr.
        import time as _time
        try:
            from src.monitoring.perf import record_event as _record_event
        except Exception:
            _record_event = None  # type: ignore[assignment]

        def _step(label: str, fn) -> None:
            t0 = _time.perf_counter()
            try:
                fn()
            except Exception:
                pass
            duration_ms = (_time.perf_counter() - t0) * 1000.0
            if _record_event is not None:
                try:
                    _record_event(f"analyse.refresh.{label}", duration_ms)
                except Exception:
                    pass

        # Vis pivot FØRST så bruker ser data raskt. mapping_issues og banner
        # bruker ~1 sekund å bygge og er ikke nødvendig for pivot — defererres
        # til etter at pivoten er på skjermen.
        _step("refresh_pivot_dispatch", lambda: page_analyse_pivot.refresh_pivot(page=self))
        _step("update_ao_count_label", self._update_ao_count_label)

        # Deferert kjøring av mapping_issues + banner.
        # Bruker after(100, ...) i stedet for after_idle for å unngå at
        # update_idletasks() i andre kallere trigger jobben synkront.
        # Brukeren ser pivoten umiddelbart; banner/varsler dukker opp ~1 sek
        # senere når mapping-issues er ferdig.
        def _deferred_mapping_work() -> None:
            t0 = _time.perf_counter()
            try:
                self._refresh_mapping_issues()
            except Exception:
                pass
            try:
                self._update_mapping_warning_banner()
            except Exception:
                pass
            if _record_event is not None:
                try:
                    _record_event(
                        "analyse.refresh.mapping_issues_deferred",
                        (_time.perf_counter() - t0) * 1000.0,
                    )
                except Exception:
                    pass

        try:
            if hasattr(self, "after") and callable(getattr(self, "after", None)):
                self.after(50, _deferred_mapping_work)
            else:
                _deferred_mapping_work()
        except Exception:
            _deferred_mapping_work()

    def _refresh_mapping_issues(self) -> None:
        analyse_mapping_ui.refresh_mapping_issues(page=self)

    def _update_mapping_warning_banner(self, *, problem_count: Optional[int] = None) -> None:
        analyse_mapping_ui.update_mapping_warning_banner(page=self, problem_count=problem_count)

    def _get_selected_problem_account_rows(self) -> List[tuple[str, str]]:
        return analyse_mapping_ui.get_selected_problem_account_rows(page=self)

    def _focus_problem_account(self, konto: str) -> None:
        analyse_mapping_ui.focus_problem_account(page=self, konto=konto)

    def _show_only_unmapped_accounts(self) -> None:
        analyse_mapping_ui.show_only_unmapped_accounts(page=self)

    def _on_show_only_unmapped_changed(self, _event=None) -> None:
        analyse_mapping_ui.on_show_only_unmapped_changed(page=self, _event=_event)

    def _map_selected_problem_account(self) -> None:
        analyse_mapping_ui.map_selected_problem_account(page=self)

    def _bulk_map_selected_problem_accounts(self) -> None:
        analyse_mapping_ui.bulk_map_selected_problem_accounts(page=self)

    def _show_mapping_drift_dialog(self) -> None:
        analyse_mapping_ui.show_mapping_drift_dialog(page=self)

    def _update_ao_count_label(self) -> None:
        """Vis antall tilleggsposteringer ved ÅO-checkboxen."""
        lbl = getattr(self, "_ao_count_label", None)
        if lbl is None:
            return
        try:
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
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
        var_data_level = getattr(self, "_var_data_level", None)
        if var_data_level is not None:
            try:
                var_data_level.set(level)
            except Exception:
                pass

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
                            self._var_tx_view_mode.set("Saldobalanse")
                        except Exception:
                            pass
            except Exception:
                pass

    def _select_all_accounts(self) -> None:
        page_analyse_pivot.select_all_accounts(page=self)

    def _get_selected_accounts(self) -> List[str]:
        return page_analyse_pivot.get_selected_accounts(page=self)

    def _on_tx_view_mode_changed(self, _event=None) -> None:
        """Bruker bytter mellom Saldobalanse og Hovedbok."""
        try:
            self._refresh_transactions_view()
        except Exception as exc:
            import logging
            logging.getLogger("app").error("_on_tx_view_mode_changed error: %s", exc, exc_info=True)

    def _refresh_transactions_view(self) -> None:
        """Dispatcher for h\u00f8yre-panelet.

        St\u00f8ttede moduser i dropdown: ``Saldobalanse``, ``Hovedbok``,
        ``N\u00f8kkeltall``, ``Motposter``, ``Motposter (kontoniv\u00e5)``.
        Ukjente verdier faller tilbake til Saldobalanse.
        """
        from page_analyse_columns import normalize_view_mode

        raw_mode = ""
        try:
            raw_mode = str(self._var_tx_view_mode.get()) if self._var_tx_view_mode else ""
        except Exception:
            pass

        # Sjekk N\u00f8kkeltall/Motposter f\u00f8rst — disse b\u00f8r ikke g\u00e5 via
        # normalize_view_mode som kollapser alt til SB/Hovedbok.
        if self._dispatch_legacy_tx_view(raw_mode=raw_mode):
            return

        mode = normalize_view_mode(raw_mode)

        # Prim\u00e6r brukerflate: Saldobalanse (SB-tree)
        if mode == "Saldobalansekontoer":
            page_analyse_sb.show_sb_tree(page=self)
            page_analyse_sb.refresh_sb_view(page=self)
            return

        # Prim\u00e6r brukerflate: Hovedbok (TX-tree)
        page_analyse_sb.show_tx_tree(page=self)
        self._configure_tx_tree_columns()
        page_analyse_transactions.refresh_transactions_view(page=self)

    def _dispatch_legacy_tx_view(self, *, raw_mode: str) -> bool:
        """H\u00e5ndter legacy view-moduser som ikke lenger er i dropdown.

        Returnerer True hvis en legacy-modus ble h\u00e5ndtert, ellers False.
        Beholdes slik at eldre prefs/ekstern `.set("N\u00f8kkeltall")` etc.
        fortsatt fungerer uten krasj.
        """
        if raw_mode == "Nøkkeltall":
            page_analyse_sb.show_nk_view(page=self)
            self._refresh_nokkeltall_view()
            return True
        if raw_mode == "Motposter":
            page_analyse_sb.show_mp_tree(page=self)
            page_analyse_sb.refresh_mp_view(page=self)
            return True
        if raw_mode == "Motposter (kontonivå)":
            page_analyse_sb.show_mp_account_tree(page=self)
            page_analyse_sb.refresh_mp_account_view(page=self)
            return True
        return False

    def _refresh_nokkeltall_view(self) -> None:
        analyse_drilldown.refresh_nokkeltall_view(self)

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
        analyse_drilldown.restore_rl_pivot_selection(self, regnr_values)

    def _reload_rl_drilldown_df(self, regnr_filter: List[int]) -> pd.DataFrame:
        return analyse_drilldown.reload_rl_drilldown_df(self, regnr_filter)

    def _open_rl_drilldown_from_pivot_selection(self) -> None:
        analyse_drilldown.open_rl_drilldown_from_pivot_selection(
            self,
            messagebox=messagebox,
            session=session,
            _open_rl_account_drilldown=_open_rl_account_drilldown,
        )

    def _open_handlinger_for_selected_rl(self) -> None:
        """Bytt til Handlinger-fanen og filtrer på valgt regnskapslinje."""
        try:
            import page_analyse_rl as _rl
            rows = _rl.get_selected_rl_rows(page=self)
        except Exception:
            rows = []
        regnr = rows[0][0] if rows else None

        try:
            root = self.winfo_toplevel()
        except Exception:
            root = None
        page = getattr(root, "page_revisjonshandlinger", None)
        nb = getattr(root, "nb", None)
        if page is None or nb is None:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Handlinger", "Handlinger-fanen er ikke tilgjengelig.")
                except Exception:
                    pass
            return
        try:
            nb.select(page)
        except Exception:
            pass
        try:
            page.filter_by_regnr(regnr)
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

    def _get_export_initialdir(self, client: str, year: str) -> str | None:
        """Returner exports_dir for nåværende klient/år, eller None hvis ukjent."""
        try:
            if client and year:
                import client_store as _cs
                return str(_cs.exports_dir(client, year=year))
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Export / workpaper wrappers — delegated to analyse_workpaper_export
    # ------------------------------------------------------------------

    def _export_regnskapsoppstilling_excel(self) -> None:
        analyse_workpaper_export.export_regnskapsoppstilling_excel(self)

    def _export_active_view_excel(self) -> None:
        """Eksporter den aktive høyre-visningen (TX, SB, Motposter, etc.) til Excel."""
        analyse_workpaper_export.export_active_view_excel(self)

    def _export_nokkeltall_html(self) -> None:
        analyse_workpaper_export.export_nokkeltall_html(self)

    def _export_nokkeltall_pdf(self) -> None:
        analyse_workpaper_export.export_nokkeltall_pdf(self)

    def _build_konto_to_rl(self) -> dict | None:
        """Bygg mapping konto_str -> (regnr, rl_name) fra sidens RL-intervaller."""
        return analyse_workpaper_export.build_konto_to_rl(self)

    def _export_motpost_flowchart_html(self) -> None:
        """Eksporter motpost-flytdiagram som HTML for valgte kontoer."""
        analyse_workpaper_export.export_motpost_flowchart_html(self)

    def _export_motpost_flowchart_pdf(self) -> None:
        """Eksporter motpost-flytdiagram som PDF for valgte kontoer."""
        analyse_workpaper_export.export_motpost_flowchart_pdf(self)

    def _export_ib_ub_control(self) -> None:
        analyse_workpaper_export.export_ib_ub_control(self)

    def _export_ib_ub_continuity(self) -> None:
        """Eksporter IB/UB-kontinuitetskontroll: sjekk at IB(i år) == UB(fjor)."""
        analyse_workpaper_export.export_ib_ub_continuity(self)

    def _export_hb_version_diff(self) -> None:
        """Sammenlign gjeldende HB med en tidligere versjon og eksporter diff."""
        analyse_workpaper_export.export_hb_version_diff(self)

    def _export_klientinfo_workpaper(self) -> None:
        """Eksporter klientinfo/roller/eierskap-arbeidspapir (BRREG + aksjonærregister)."""
        analyse_workpaper_export.export_klientinfo_workpaper(self)

    def _pick_hb_version(self, versions, active_id) -> Optional[str]:
        """Enkel dialog for å velge en HB-versjon å sammenligne med."""
        return analyse_workpaper_export.pick_hb_version(self, versions, active_id)

    def _load_hb_version_df(self, client: str, year: str, version_id: str) -> Optional[pd.DataFrame]:
        """Last en HB-versjon som DataFrame."""
        return analyse_workpaper_export.load_hb_version_df(self, client, year, version_id)
