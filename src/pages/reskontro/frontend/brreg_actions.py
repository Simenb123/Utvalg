"""reskontro_brreg_actions.py — BRREG-sjekk og etterfølgende-periode-lasting.

Modulfunksjoner som tar `page` (ReskontroPage) som første argument.
"""

from __future__ import annotations

import logging
import threading

import pandas as pd

from ..backend.brreg_helpers import _brreg_has_risk
from .tree_helpers import _LOWER_VIEW_BRREG

log = logging.getLogger(__name__)


def open_subsequent_period(page) -> None:
    """Last inn SAF-T for etterfølgende periode."""
    try:
        from tkinter import filedialog
    except Exception:
        return

    path = filedialog.askopenfilename(
        parent=page,
        title="Velg SAF-T for etterfølgende periode (zip/xml)",
        filetypes=[
            ("SAF-T filer", "*.zip *.xml"),
            ("Alle filer",  "*.*"),
        ],
    )
    if not path:
        return

    try:
        page._load_subseq_btn.configure(state="disabled", text="Laster\u2026")
    except Exception:
        pass

    def _load() -> None:
        try:
            import src.shared.saft.reader as _sr
            df2 = _sr.read_saft_ledger(path)
            import os
            label = os.path.basename(path)
            page.after(0, lambda: page._on_subseq_loaded(df2, label))
        except Exception as exc:
            log.exception("Etterfølgende SAF-T lasting feilet: %s", exc)
            def _fail(e: Exception = exc) -> None:
                try:
                    page._load_subseq_btn.configure(
                        state="normal",
                        text="Last inn etterfølgende periode\u2026")
                except Exception:
                    pass
                page._status_lbl.configure(text=f"Feil ved lasting: {e}")
            page.after(0, _fail)

    threading.Thread(target=_load, daemon=True).start()


def on_subseq_loaded(page, df2: pd.DataFrame, label: str) -> None:
    page._subsequent_df    = df2
    page._subsequent_label = label
    try:
        page._load_subseq_btn.configure(
            state="normal",
            text="Last inn etterfølgende periode\u2026")
    except Exception:
        pass
    page._status_lbl.configure(
        text=f"Etterfølgende periode lastet: {label}")
    # Refresh nedre panel — viser matching/transaksjoner om valgt visning
    # trenger det. Ingen automatisk popup lenger.
    page._refresh_lower_panel()


def auto_brreg_all(page) -> None:
    """Auto-start BRREG-sjekk for alle orgnr som ikke allerede er hentet."""
    if page._master_df is None or page._master_df.empty:
        return
    # Sjekk om det finnes uhentede orgnr
    missing = [
        orgnr for orgnr in page._orgnr_map.values()
        if orgnr and len(orgnr) == 9 and orgnr.isdigit()
        and orgnr not in page._brreg_data
    ]
    if missing:
        page._start_brreg_sjekk()


def start_brreg_sjekk(page) -> None:
    """Start bakgrunnstråd som henter BRREG-data for alle synlige poster."""
    if page._master_df is None or page._master_df.empty:
        return

    orgnrs = [
        orgnr for orgnr in page._orgnr_map.values()
        if orgnr and len(orgnr) == 9 and orgnr.isdigit()
    ]
    if not orgnrs:
        page._status_lbl.configure(
            text="Ingen gyldige orgnumre i data. "
                 "Krever SAF-T-fil med RegistrationNumber.")
        return

    page._brreg_btn.configure(state="disabled", text="Henter\u2026")
    total = len(set(orgnrs))
    page._status_lbl.configure(
        text=f"BRREG: henter 0\u202f/\u202f{total}\u2026")

    def _progress(done: int, tot: int) -> None:
        page.after(0, lambda d=done, t=tot: page._status_lbl.configure(
            text=f"BRREG: henter {d}\u202f/\u202f{t}\u2026"))

    def _run() -> None:
        try:
            import src.shared.brreg.client as _brreg
            results = _brreg.fetch_many(
                list(set(orgnrs)),
                progress_cb=_progress,
                include_regnskap=True,
            )
            page.after(0, lambda r=results: page._on_brreg_done(r))
        except Exception as exc:
            log.exception("BRREG-sjekk feilet: %s", exc)
            page.after(0, lambda: (
                page._brreg_btn.configure(
                    state="normal", text="BRREG-sjekk\u2026"),
                page._status_lbl.configure(
                    text=f"BRREG feilet: {exc}"),
            ))

    threading.Thread(target=_run, daemon=True).start()


def on_brreg_done(page, results: dict) -> None:
    """Kalles fra main-tråden når BRREG-henting er ferdig."""
    page._brreg_data.update(results)
    page._apply_filter()
    page._brreg_btn.configure(state="normal", text="BRREG-sjekk\u2026")

    n_ok    = sum(1 for v in results.values() if v.get("enhet"))
    n_total = len(results)
    n_warn  = sum(
        1 for v in results.values()
        if _brreg_has_risk(v.get("enhet") or {}))
    n_no_mva = sum(
        1 for v in results.values()
        if v.get("enhet")
        and not (v["enhet"] or {}).get("registrertIMvaregisteret"))

    parts = [f"BRREG: {n_ok}/{n_total} hentet"]
    if n_warn:
        parts.append(f"\u26a0 {n_warn} med risiko")
    if n_no_mva:
        parts.append(f"\u2717 {n_no_mva} ikke MVA-reg.")
    page._status_lbl.configure(text="  \u2022  ".join(parts))

    # Oppdater BRREG-panelet for valgt rad hvis den visningen er aktiv
    if (page._selected_nr
            and page._lower_view_var.get() == _LOWER_VIEW_BRREG):
        orgnr = page._orgnr_map.get(page._selected_nr, "")
        if orgnr:
            page._update_brreg_panel(orgnr)
