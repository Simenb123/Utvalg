"""page_analyse.py

Analyse-fanen: konto-pivot (venstre) + transaksjonsliste (høyre).

Denne modulen er bevisst holdt liten (~<400 linjer) og delegerer
størstedelen av logikken til egne moduler:
- page_analyse_ui.py (widget-bygging/layout)
- page_analyse_filters_live.py (filtrering + debounce)
- page_analyse_pivot.py (pivot-tree)
- page_analyse_transactions.py (transaksjonsliste)
- page_analyse_actions_impl.py (handlinger: motpost, overstyring, drill)
- page_analyse_export.py (DataFrame-bygging for Excel-eksport)

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

import analyse_columns
import preferences
import ui_hotkeys

import session

import page_analyse_actions_impl
import page_analyse_export
import page_analyse_filters_live
import page_analyse_pivot
import page_analyse_transactions
import page_analyse_ui

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


@dataclass
class _DirectionOpt:
    label: str
    value: Optional[str]  # None | "debet" | "kredit"


_DIR_OPTIONS: List[_DirectionOpt] = [
    _DirectionOpt("Alle", None),
    _DirectionOpt("Debet", "debet"),
    _DirectionOpt("Kredit", "kredit"),
]


class AnalysePage(ttk.Frame):  # type: ignore[misc]
    """GUI-side for analyse."""

    PIVOT_COLS = ("Konto", "Kontonavn", "Sum", "Antall")

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

    def __init__(self, master=None):
        # Live filter debounce / scheduling
        self._filter_after_id: Optional[str] = None
        self._suspend_live_filter: bool = False

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
            self._init_error = e
            return

        # --- state ---
        self.dataset: Optional[pd.DataFrame] = None
        self._df_filtered: Optional[pd.DataFrame] = None
        self._utvalg_callback: Optional[Callable[[List[str]], None]] = None

        # --- vars ---
        self._var_search = tk.StringVar(value="")
        self._var_direction = tk.StringVar(value=_DIR_OPTIONS[0].label)
        self._var_min = tk.StringVar(value="")
        self._var_max = tk.StringVar(value="")
        self._var_max_rows = tk.IntVar(value=200)
        self._series_vars = [tk.IntVar(value=0) for _ in range(10)]

        # --- kolonner (transaksjonsliste) ---
        # Lagres per bruker via preferences (best-effort; aldri krasj GUI)
        self._tx_cols_order: List[str] = list(self.TX_COLS_DEFAULT)
        self._load_tx_columns_from_preferences()

        # --- UI refs ---
        self._pivot_tree = None
        self._tx_tree = None
        self._lbl_tx_summary = None
        self._ent_search: Optional[object] = None

        self._build_ui()

    # -----------------------------------------------------------------
    # Public API expected by ui_main/tests
    # -----------------------------------------------------------------

    def set_utvalg_callback(self, callback: Callable[[List[str]], None]) -> None:
        self._utvalg_callback = callback

    def refresh_from_session(self, sess: object = session) -> None:
        """Reload data from session and refresh UI.

        Viktig: Vi beholder råverdien i self.dataset (ikke bare DataFrame),
        slik at headless-tester kan sette dummy-verdier og verifisere at
        metoden faktisk oppdaterer feltet.
        """
        df = getattr(sess, "dataset", None)
        self.dataset = df  # type: ignore[assignment]
        self._apply_filters_and_refresh()

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
    # TX-kolonner (visning)
    # -----------------------------------------------------------------

    def _load_tx_columns_from_preferences(self) -> None:
        '''Best-effort: last inn kolonneoppsett for transaksjonslisten.

        Dette gjelder kun visning i Analyse-fanen (transaksjonslisten).
        Vi filtrerer ikke bort "ukjente" kolonner her, slik at bruker kan
        ha lagret visning av ekstra kolonner som finnes i noen filer.
        '''
        try:
            stored_order = preferences.get("analyse.tx_cols.order", None)
            stored_visible = preferences.get("analyse.tx_cols.visible", None)
        except Exception:
            stored_order = None
            stored_visible = None

        order = stored_order if isinstance(stored_order, list) else list(self.TX_COLS_DEFAULT)
        visible = stored_visible if isinstance(stored_visible, list) else list(self.TX_COLS_DEFAULT)

        order_clean, visible_order = analyse_columns.normalize_tx_column_config(
            order=order,
            visible=visible,
            all_cols=None,
            pinned=self.PINNED_TX_COLS,
            required=self.REQUIRED_TX_COLS,
        )

        self._tx_cols_order = list(order_clean)
        self._tx_cols_visible = list(visible_order)
        # Instance-attributt: kan overstyre klassekonstanten.
        self.TX_COLS = tuple(visible_order)

    def _persist_tx_columns_to_preferences(self) -> None:
        '''Lagres som best-effort. Feil skal ikke stoppe GUI.'''
        try:
            preferences.set("analyse.tx_cols.order", list(self._tx_cols_order))
            preferences.set("analyse.tx_cols.visible", list(self.TX_COLS))
        except Exception:
            pass

    def _get_all_tx_columns_for_chooser(self) -> List[str]:
        cols: List[str] = []

        # Start med det vi allerede kjenner (inkl. skjulte fra tidligere)
        cols.extend(getattr(self, "_tx_cols_order", []))
        cols.extend(list(self.TX_COLS_DEFAULT))

        # Legg til kolonner fra aktivt datasett (hvis lastet)
        df = self._df_filtered if isinstance(self._df_filtered, pd.DataFrame) else self._dataset
        if isinstance(df, pd.DataFrame):
            for c in df.columns:
                try:
                    name = str(c)
                except Exception:
                    continue
                if not name or name.startswith("_"):
                    continue
                cols.append(name)

        return analyse_columns.unique_preserve(cols)

    def _apply_tx_column_config(self, order: List[str], visible: List[str], *, all_cols: Optional[List[str]] = None) -> None:
        all_cols = all_cols or self._get_all_tx_columns_for_chooser()

        order_clean, visible_order = analyse_columns.normalize_tx_column_config(
            order=order,
            visible=visible,
            all_cols=all_cols,
            pinned=self.PINNED_TX_COLS,
            required=self.REQUIRED_TX_COLS,
        )

        self._tx_cols_order = list(order_clean)
        self._tx_cols_visible = list(visible_order)
        self.TX_COLS = tuple(visible_order)

        self._persist_tx_columns_to_preferences()

        # Oppdater tree (hvis GUI)
        self._configure_tx_tree_columns()
        self._refresh_transactions_view()

    def _open_tx_column_chooser(self) -> None:
        if not self._tk_ok:
            return

        try:
            from views_column_chooser import open_column_chooser
        except Exception:
            return

        all_cols = self._get_all_tx_columns_for_chooser()
        current_visible = list(getattr(self, "TX_COLS", self.TX_COLS_DEFAULT))
        initial_order = list(getattr(self, "_tx_cols_order", all_cols))

        res = open_column_chooser(self, all_cols=all_cols, visible_cols=current_visible, initial_order=initial_order)
        if not res:
            return

        order, visible = res
        if not isinstance(order, list) or not isinstance(visible, list):
            return

        self._apply_tx_column_config(order=order, visible=visible, all_cols=all_cols)

    def _reset_tx_columns_to_default(self) -> None:
        # Reset til programstandard
        self._apply_tx_column_config(order=list(self.TX_COLS_DEFAULT), visible=list(self.TX_COLS_DEFAULT))

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

    def _configure_tx_tree_columns(self) -> None:
        if not self._tk_ok:
            return

        tree = getattr(self, "_tx_tree", None)
        if tree is None:
            return

        cols = tuple(getattr(self, "TX_COLS", self.TX_COLS_DEFAULT))

        # Bredder/justeringer. Nye/ukjente kolonner får en konservativ default.
        col_widths = {
            "Konto": 80,
            "Kontonavn": 220,
            "Dato": 90,
            "Bilag": 90,
            "Tekst": 260,
            "Beløp": 90,
            "Kunder": 140,
            "MVA-kode": 80,
            "MVA-beløp": 90,
            "MVA-prosent": 80,
            "Valuta": 70,
            "Valutabeløp": 90,
            "Debet": 90,
            "Kredit": 90,
        }
        numeric_cols = {
            "Beløp",
            "MVA-beløp",
            "Valutabeløp",
            "MVA-prosent",
            "Debet",
            "Kredit",
        }

        try:
            tree.configure(columns=cols)
            tree["displaycolumns"] = cols
        except Exception:
            return

        for c in cols:
            try:
                tree.heading(c, text=c)
            except Exception:
                pass

            width = int(col_widths.get(c, 120))
            anchor = "e" if c in numeric_cols else "w"
            try:
                tree.column(c, width=width, anchor=anchor, stretch=True)
            except Exception:
                pass

        # Gjeninstaller sortering (header-klikk)
        self._enable_tx_sorting()


    def _enable_tx_sorting(self) -> None:
        """Aktiver klikk-for-sortering på transaksjonslisten hvis tilgjengelig."""
        if not getattr(self, "_tk_ok", False):
            return
        if getattr(self, "_tx_tree", None) is None:
            return
        if _enable_treeview_sorting is None:
            return
        try:
            _enable_treeview_sorting(self._tx_tree, columns=self.TX_COLS)  # type: ignore[arg-type]
        except Exception:
            # Sorting er "nice to have" – aldri krasj GUI hvis det feiler.
            pass


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
        ent_min,
        ent_max,
        cmb_dir=None,
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
                ent_min,
                ent_max,
                cmb_dir,
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
            self._refresh_transactions_view()
        except Exception:
            # Skal aldri krasje GUI på event-binding.
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
        page_analyse_pivot.refresh_pivot(page=self)

    def _select_all_accounts(self) -> None:
        page_analyse_pivot.select_all_accounts(page=self)

    def _get_selected_accounts(self) -> List[str]:
        return page_analyse_pivot.get_selected_accounts(page=self)

    def _refresh_transactions_view(self) -> None:
        page_analyse_transactions.refresh_transactions_view(page=self)

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
