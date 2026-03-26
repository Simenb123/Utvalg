"""Motpostanalyse (GUI).

Tkinter-visning for motpostanalyse.

Historikk:
    Denne modulen har vokst over tid og inneholdt både:
        - UI-bygging
        - rendering (Treeview-populering)
        - actions/callbacks
        - Treeview-hjelpefunksjoner

    For bedre vedlikeholdbarhet er den nå refaktorert til en "thin facade" som
    delegerer til mindre moduler i :mod:`motpost`-pakken.

Viktig:
    Flere tester (og kallere) monkeypatcher navn i dette modulen. Derfor
    beholder vi:
        - samme klasse/entrypoint-navn
        - re-exports av kjernefunksjoner og helpers
        - metodenavn på MotpostKontoView
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import session
import regnskap_client_overrides

from motpost.view_konto_actions import (
    clear_outliers,
    drilldown,
    export_excel,
    mark_outlier,
    on_select_motkonto,
    open_bilag_drilldown,
    show_combinations,
)
from motpost.view_konto_render import refresh_details, render_summary
from motpost.view_konto_tree import (
    configure_bilag_details_tree,
    treeview_first_selected_value,
    treeview_value_from_iid,
)
from motpost.view_konto_ui import (
    bind_entry_select_all,
    build_motpost_header_metrics_text,
    build_motpost_expected_label,
    build_motpost_expected_value,
    build_motpost_selected_accounts_label,
    build_motpost_selected_accounts_value,
    build_motpost_scope_label,
    build_motpost_scope_value,
    build_ui,
)

from motpost_combinations_popup import show_motkonto_combinations_popup
from motpost_combinations import (
    build_motkonto_combinations,
    build_motkonto_combinations_per_selected_account,
)
from motpost_konto_core import (
    MotpostData,
    build_bilag_details,
    build_motpost_data,
    build_motpost_excel_workbook,
    _konto_str,
)

from ui_treeview_sort import enable_treeview_sorting


_REGNSKAPSLINJE_REGNR_RE = re.compile(r"^\s*(\d+)")


def _parse_regnskapslinje_regnr(value: object) -> int | None:
    match = _REGNSKAPSLINJE_REGNR_RE.match(str(value or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _sort_regnskapslinje_label(value: object) -> tuple[int, int | str]:
    regnr = _parse_regnskapslinje_regnr(value)
    if regnr is not None:
        return (0, regnr)
    return (1, str(value or "").strip().lower())


def _build_regnskapslinje_label_map(
    scope_items: Sequence[str] | None,
    konto_regnskapslinje_map: Mapping[str, str] | None,
) -> dict[int, str]:
    labels: dict[int, str] = {}
    for raw in list(scope_items or ()) + list((konto_regnskapslinje_map or {}).values()):
        text = str(raw or "").strip()
        regnr = _parse_regnskapslinje_regnr(text)
        if regnr is None or not text:
            continue
        labels.setdefault(regnr, text)
    return labels


def _restore_expected_regnskapslinjer_for_view(
    *,
    client: str | None,
    scope_mode: str,
    scope_items: Sequence[str] | None,
    konto_regnskapslinje_map: Mapping[str, str] | None,
    selected_direction: str | None,
) -> tuple[str, ...]:
    if not str(scope_mode or "").strip().lower().startswith("regn"):
        return ()

    scope_regnr: list[int] = []
    for label in scope_items or ():
        regnr = _parse_regnskapslinje_regnr(label)
        if regnr is None or regnr in scope_regnr:
            continue
        scope_regnr.append(regnr)

    if not client or not scope_regnr:
        return ()

    label_map = _build_regnskapslinje_label_map(scope_items, konto_regnskapslinje_map)
    try:
        expected_regnr = regnskap_client_overrides.load_expected_regnskapslinjer(
            client,
            scope_regnr=scope_regnr,
            selected_direction=selected_direction,
        )
    except Exception:
        return ()

    restored: list[str] = []
    seen: set[str] = set()
    for regnr in expected_regnr:
        label = str(label_map.get(int(regnr), int(regnr))).strip()
        if not label or label in seen:
            continue
        restored.append(label)
        seen.add(label)

    return tuple(sorted(restored, key=_sort_regnskapslinje_label))


class MotpostKontoView(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        df_transactions: pd.DataFrame,
        konto_list: list[str] | set[str] | tuple[str, ...],
        konto_name_map: dict[str, str] | None = None,
        *,
        selected_direction: str = "Alle",
        scope_mode: str = "konto",
        scope_items: list[str] | tuple[str, ...] | set[str] | None = None,
        konto_regnskapslinje_map: dict[str, str] | None = None,
    ):
        super().__init__(master)
        self.title("Motpostanalyse")
        self.geometry("1100x700")

        self._df_all = df_transactions
        self._selected_accounts = {_konto_str(k) for k in konto_list}
        self._selected_direction = selected_direction
        self._konto_name_map: dict[str, str] = dict(konto_name_map or {})
        self._scope_mode = "regnskapslinje" if str(scope_mode or "").strip().lower().startswith("regn") else "konto"
        self._scope_items = tuple(str(x).strip() for x in (scope_items or []) if str(x).strip())
        self._konto_regnskapslinje_map: dict[str, str] = {
            _konto_str(k): str(v).strip()
            for k, v in (konto_regnskapslinje_map or {}).items()
            if _konto_str(k) and str(v).strip()
        }
        self._expected_regnskapslinjer = _restore_expected_regnskapslinjer_for_view(
            client=getattr(session, "client", None),
            scope_mode=self._scope_mode,
            scope_items=self._scope_items,
            konto_regnskapslinje_map=self._konto_regnskapslinje_map,
            selected_direction=self._selected_direction,
        )
        self._data = build_motpost_data(
            self._df_all,
            self._selected_accounts,
            selected_direction=self._selected_direction,
        )

        self._outliers: set[str] = set()
        # Outliers på kombinasjonsnivå ("1500, 2700" osv.).
        # Muteres fra kombinasjons-popup (settet deles som referanse).
        self._outlier_combinations: set[str] = set()
        self._selected_motkonto: Optional[str] = None

        self._details_limit_var = tk.IntVar(value=200)
        self._details_mva_code_values = ["Alle"]
        self._details_mva_code_var = tk.StringVar(value="Alle")
        self._details_mva_mode_values = [
            "Alle",
            "Med MVA-kode",
            "Uten MVA-kode",
            "Treffer forventet",
            "Avvik fra forventet",
        ]
        self._details_mva_mode_var = tk.StringVar(value="Alle")
        self._details_expected_mva_values = ["25", "15", "12", "0"]
        self._details_expected_mva_var = tk.StringVar(value="25")

        self._build_ui()
        self._render_summary()

    # --- UI bygging ---
    def _build_ui(self) -> None:
        build_ui(
            self,
            enable_treeview_sorting_fn=enable_treeview_sorting,
            configure_bilag_details_tree_fn=configure_bilag_details_tree,
        )

    # --- Rendering ---
    def _render_summary(self) -> None:
        render_summary(self)

    def _refresh_details(self) -> None:
        # Viktig: testene monkeypatcher build_bilag_details i *dette* modulen.
        refresh_details(self, build_bilag_details_fn=build_bilag_details)

    # --- Events / actions ---
    def _on_select_motkonto(self, _event=None) -> None:
        on_select_motkonto(self, konto_str_fn=_konto_str)

    def _mark_outlier(self) -> None:
        mark_outlier(self, messagebox_mod=messagebox, konto_str_fn=_konto_str)

    def _clear_outliers(self) -> None:
        clear_outliers(self)

    def _show_combinations(self) -> None:
        # Viktig: testene monkeypatcher build_motkonto_combinations / show_motkonto_combinations_popup
        show_combinations(
            self,
            build_motkonto_combinations_fn=build_motkonto_combinations,
            build_motkonto_combinations_per_selected_account_fn=build_motkonto_combinations_per_selected_account,
            show_popup_fn=show_motkonto_combinations_popup,
            messagebox_mod=messagebox,
        )

    def _export_excel(
        self,
        combo_status_map: object | None = None,
        combo_comment_map: object | None = None,
    ) -> None:
        """Eksporter til Excel.

        Backwards compatible:
        - Eldre kallere sendte kun `outlier_combinations: set[str]`.
        - Kombinasjons-popup (2026+) sender (status_map: dict, comment_map: dict).
        """
        outlier_combinations: set[str] | None = None
        status_map: dict[str, str] | None = None
        comment_map: dict[str, str] | None = None

        if isinstance(combo_status_map, dict):
            status_map = {str(k): str(v) for k, v in combo_status_map.items()}
            if isinstance(combo_comment_map, dict):
                comment_map = {str(k): ("" if v is None else str(v)) for k, v in combo_comment_map.items()}
            else:
                comment_map = {}
        elif isinstance(combo_status_map, set):
            # Legacy: første argument var outlier-sett
            outlier_combinations = {str(x) for x in combo_status_map}
        else:
            outlier_combinations = None

        export_excel(
            self,
            filedialog_mod=filedialog,
            messagebox_mod=messagebox,
            build_motpost_excel_workbook_fn=build_motpost_excel_workbook,
            outlier_combinations=outlier_combinations,
            combo_status_map=status_map,
            combo_comment_map=comment_map,
        )

    def _open_bilag_drilldown(self, bilag: str) -> None:
        open_bilag_drilldown(self, bilag, konto_str_fn=_konto_str, messagebox_mod=messagebox)

    def _drilldown(self) -> None:
        drilldown(
            self,
            treeview_first_selected_value_fn=treeview_first_selected_value,
            konto_str_fn=_konto_str,
            messagebox_mod=messagebox,
        )


def show_motpost_konto(
    master: tk.Misc,
    df_transactions: pd.DataFrame | None = None,
    konto_list: list[str] | set[str] | tuple[str, ...] | None = None,
    konto_name_map: dict[str, str] | None = None,
    *,
    # Nye/alternative signaturer brukt av enkelte kallere
    df_all: pd.DataFrame | None = None,
    selected_accounts: list[str] | set[str] | tuple[str, ...] | None = None,
    selected_kontoer: list[str] | set[str] | tuple[str, ...] | None = None,
    accounts: list[str] | set[str] | tuple[str, ...] | None = None,
    # Retning (for sum av valgte kontoer)
    selected_direction: str = "Alle",
    direction: str | None = None,
    retning: str | None = None,
    scope_mode: str | None = None,
    scope_items: list[str] | tuple[str, ...] | set[str] | None = None,
    konto_regnskapslinje_map: dict[str, str] | None = None,
    **_: Any,
) -> None:
    """Entry-point brukt fra Analyse-fanen.

    Backwards compatible:
        - Noen kallere bruker (master, df, konto_list)
        - Noen bruker keywords: df_all=..., selected_accounts=..., konto_name_map=...
    """

    df = df_transactions if df_transactions is not None else df_all
    if df is None:
        raise TypeError("show_motpost_konto: mangler dataframe (df_transactions/df_all)")

    selected = konto_list or selected_accounts or selected_kontoer or accounts
    if not selected:
        # Typisk feiltilfelle: kalles uten kontoer -> ikke åpne vindu
        return

    konto_norm = [_konto_str(k) for k in selected]

    dir_value = direction or retning or selected_direction or "Alle"

    # MotpostKontoView kan ha litt ulik signatur i forskjellige versjoner.
    # Prøv å sende med så mye som mulig, men fall tilbake dersom den ikke støtter argumentene.
    try:
        MotpostKontoView(
            master,
            df,
            konto_norm,
            konto_name_map,
            selected_direction=dir_value,
            scope_mode=scope_mode or "konto",
            scope_items=scope_items,
            konto_regnskapslinje_map=konto_regnskapslinje_map,
        )
        return
    except TypeError:
        pass

    try:
        MotpostKontoView(master, df, konto_norm, konto_name_map=konto_name_map, selected_direction=dir_value)
        return
    except TypeError:
        pass

    try:
        MotpostKontoView(master, df, konto_norm, konto_name_map=konto_name_map)
        return
    except TypeError:
        pass

    try:
        MotpostKontoView(master, df, konto_norm, selected_direction=dir_value)
        return
    except TypeError:
        pass

    MotpostKontoView(master, df, konto_norm)


# Bakoverkompatibilitet (noen steder kan ha importert underscorenavnet)
_show_motpost_konto = show_motpost_konto


__all__ = [
    "MotpostKontoView",
    "show_motpost_konto",
    "_show_motpost_konto",
    # Re-exports brukt av tester/andre moduler
    "MotpostData",
    "build_motpost_data",
    "build_motpost_excel_workbook",
    "build_bilag_details",
    "_konto_str",
    "build_motkonto_combinations",
    "build_motkonto_combinations_per_selected_account",
    "show_motkonto_combinations_popup",
    # Tree helpers
    "configure_bilag_details_tree",
    "treeview_first_selected_value",
    "treeview_value_from_iid",
    # UI helpers (nyttig for tester og gjenbruk)
    "build_motpost_header_metrics_text",
    "build_motpost_expected_label",
    "build_motpost_expected_value",
    "build_motpost_selected_accounts_label",
    "build_motpost_selected_accounts_value",
    "build_motpost_scope_label",
    "build_motpost_scope_value",
    "bind_entry_select_all",
]
