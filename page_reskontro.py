"""page_reskontro.py — Reskontro fane.

Viser kunde- og leverandørtransaksjoner fra SAF-T / HB-data,
med integrert BRREG-sjekk (Enhetsregisteret + Regnskapsregisteret).

Layout:
  - Toolbar: toggle Kunder / Leverandører, søkefelt, BRREG-knapp, eksport
  - Venstre panel: liste med IB/Bevegelse/UB + MVA-reg, Status, Bransje
  - Høyre panel (øverst): transaksjoner for valgt post
  - Høyre panel (nederst): BRREG-detaljer for valgt post
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk  # noqa: F401
    from tkinter import ttk  # noqa: F401
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import reskontro_brreg_actions  # noqa: E402
import reskontro_brreg_panel  # noqa: E402
import reskontro_export  # noqa: E402
import reskontro_popups  # noqa: E402
import reskontro_selection  # noqa: E402
import reskontro_ui_build  # noqa: E402
from reskontro_tree_helpers import (  # noqa: E402
    _DETAIL_COLS,
    _has_reskontro_data,
)

# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------

class ReskontroPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, master: Any = None) -> None:
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            return

        self._df: pd.DataFrame | None = None
        self._master_df: pd.DataFrame | None = None
        self._mode: str = "kunder"
        self._selected_nr: str = ""
        self._filter_var: Any = None

        # BRREG: {orgnr: {"enhet": dict|None, "regnskap": dict|None}}
        self._brreg_data: dict[str, dict] = {}
        # intern_nr → orgnr
        self._orgnr_map: dict[str, str] = {}
        # Etterfølgende periode SAF-T (lastet inn av bruker for matching)
        self._subsequent_df: pd.DataFrame | None = None
        self._subsequent_label: str = ""

        if tk is None:
            return

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def refresh_from_session(self, session: Any = None) -> None:
        import session as _session
        df = getattr(_session, "dataset", None)
        self._df = df if _has_reskontro_data(df) else None
        self._refresh_all()
        # Auto-start BRREG-sjekk i bakgrunn etter kort forsinkelse
        if self._df is not None and self._orgnr_map:
            self.after(500, self._auto_brreg_all)

    # ------------------------------------------------------------------
    # UI-bygging
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        reskontro_ui_build.build_ui(self)

    def _detail_decimals(self) -> int:
        """Returnerer antall desimaler for detaljvisning basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _master_decimals(self) -> int:
        """Returnerer antall desimaler for master-listen basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _on_detail_double_click(self, event: Any) -> None:
        """Dobbeltklikk på transaksjon → vis alle linjer for samme bilag.

        Leser fra treet dobbeltklikket skjedde i (``event.widget``), og
        slår opp Bilag-kolonnen dynamisk — kolonneindeksen er ulik i
        flat transaksjonsliste og i åpne-poster-visningen.
        """
        tree = getattr(event, "widget", None) or self._detail_tree
        item = tree.identify_row(event.y)
        if not item:
            return
        try:
            cols = list(tree["columns"])
        except Exception:
            cols = list(_DETAIL_COLS)
        try:
            bilag_idx = cols.index("Bilag")
        except ValueError:
            return
        vals = tree.item(item, "values")
        if not vals or bilag_idx >= len(vals):
            return
        bilag = str(vals[bilag_idx]).strip()
        if not bilag:
            return
        self._open_bilag_popup(bilag)

    def _open_bilag_popup(self, bilag: str) -> None:
        reskontro_popups.open_bilag_popup(self, bilag)

    def _build_brreg_panel(self) -> None:
        reskontro_brreg_panel.build_brreg_panel(self, parent=self._brreg_frame)

    def _brreg_write(self, *parts: tuple[str, str]) -> None:
        reskontro_brreg_panel.brreg_write(self, *parts)

    def _clear_brreg_panel(self) -> None:
        reskontro_brreg_panel.clear_brreg_panel(self)

    def _update_brreg_panel(self, orgnr: str) -> None:
        reskontro_brreg_panel.update_brreg_panel(self, orgnr)

    # ------------------------------------------------------------------
    # Refresh / seleksjon / populering — delegater til reskontro_selection
    # ------------------------------------------------------------------

    def _on_decimals_toggle(self) -> None:
        reskontro_selection.on_decimals_toggle(self)

    def _on_mode_change(self) -> None:
        reskontro_selection.on_mode_change(self)

    def _refresh_all(self) -> None:
        reskontro_selection.refresh_all(self)

    def _apply_filter(self) -> None:
        reskontro_selection.apply_filter(self)

    def _on_master_select(self, _event: Any = None) -> None:
        reskontro_selection.on_master_select(self, _event)

    def _auto_fetch_brreg_single(self, orgnr: str) -> None:
        reskontro_selection.auto_fetch_brreg_single(self, orgnr)

    def _on_single_brreg_done(self, orgnr: str, result: dict) -> None:
        reskontro_selection.on_single_brreg_done(self, orgnr, result)

    def _on_detail_select(self, _event: Any = None) -> None:
        reskontro_selection.on_detail_select(self, _event)

    def _on_detail_right_click(self, event: Any) -> None:
        reskontro_selection.on_detail_right_click(self, event)

    def _populate_detail(self, nr: str) -> None:
        reskontro_selection.populate_detail(self, nr)

    def _update_detail_header(self, nr: str, *, n_tx: int, total: float) -> None:
        reskontro_selection.update_detail_header(self, nr, n_tx=n_tx, total=total)

    def _on_upper_view_change(self) -> None:
        reskontro_selection.on_upper_view_change(self)

    def _on_lower_view_change(self) -> None:
        reskontro_selection.on_lower_view_change(self)

    def _refresh_upper_panel(self) -> None:
        reskontro_selection.refresh_upper_panel(self)

    def _refresh_lower_panel(self) -> None:
        reskontro_selection.refresh_lower_panel(self)

    def _populate_open_items_inline(self, nr: str) -> None:
        reskontro_selection.populate_open_items_inline(self, nr)

    def _populate_subseq_tree(self, nr: str) -> None:
        reskontro_selection.populate_subseq_tree(self, nr)

    def _populate_payments_tree(self, nr: str) -> None:
        reskontro_selection.populate_payments_tree(self, nr)

    def _navn_for_nr(self, nr: str) -> str:
        return reskontro_selection.navn_for_nr(self, nr)


    def _show_open_items_popup(self) -> None:
        reskontro_popups.show_open_items_popup(self)

    def _show_saldoliste_popup(self) -> None:
        reskontro_popups.show_saldoliste_popup(self)

    def _open_subsequent_period(self) -> None:
        reskontro_brreg_actions.open_subsequent_period(self)

    def _on_subseq_loaded(self, df2: pd.DataFrame, label: str) -> None:
        reskontro_brreg_actions.on_subseq_loaded(self, df2, label)

    def _show_subsequent_match_popup(self) -> None:
        reskontro_popups.show_subsequent_match_popup(self)

    # ------------------------------------------------------------------
    # BRREG-sjekk
    # ------------------------------------------------------------------

    def _auto_brreg_all(self) -> None:
        reskontro_brreg_actions.auto_brreg_all(self)

    def _start_brreg_sjekk(self) -> None:
        reskontro_brreg_actions.start_brreg_sjekk(self)

    def _on_brreg_done(self, results: dict) -> None:
        reskontro_brreg_actions.on_brreg_done(self, results)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_excel(self) -> None:
        reskontro_export.export_excel(self)

    def _export_pdf_report(self) -> None:
        reskontro_export.export_pdf_report(self)
