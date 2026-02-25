"""page_analyse_filters_live.py

Filtrering + live oppdatering (debounce) for Analyse-fanen.

Denne modulen inneholder logikken som tidligere lå i page_analyse.py:
- reset av filtre
- safe parsing av min/maks beløp
- live filtering med debounce via Tk.after
- apply filter + oppdater pivot/transaksjoner

Design:
- Unngå sirkulære imports: funksjonene tar inn et "page"-objekt (AnalysePage)
  og bruker attributter/methods som allerede finnes der.
- Robust i headless/CI: ingen exceptions skal boble opp ved manglende Tk.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import pandas as pd

from analysis_filters import filter_dataset
from konto_utils import konto_to_str


def safe_float(s: str) -> Optional[float]:
    """Parse tall fra norsk/internasjonalt input.

    - Tillater tusenskiller (mellomrom)
    - Tillater desimalskille ','
    """
    try:
        s2 = (s or "").strip()
        if not s2:
            return None
        return float(s2.replace(" ", "").replace(",", "."))
    except Exception:
        return None


def reset_filters(*, page: Any, dir_options: Sequence[Any]) -> None:
    """Nullstill filterfeltene og trigger umiddelbar oppdatering."""
    if not getattr(page, "_tk_ok", False):
        return

    # Unngå at trace/debounce trigges flere ganger under reset
    page._suspend_live_filter = True
    try:
        page._var_search.set("")
        page._var_direction.set(dir_options[0].label)
        page._var_min.set("")
        page._var_max.set("")
        page._var_max_rows.set(200)
        for v in page._series_vars:
            v.set(0)
    finally:
        page._suspend_live_filter = False

    apply_filters_now(page=page)


def schedule_apply_filters(*, page: Any) -> None:
    """Debounce: planlegg filter-oppdatering litt frem i tid."""
    if not getattr(page, "_tk_ok", False):
        return
    if getattr(page, "_suspend_live_filter", False):
        return

    # Avbryt forrige planlagte oppdatering
    if getattr(page, "_filter_after_id", None):
        try:
            page.after_cancel(page._filter_after_id)
        except Exception:
            pass
        page._filter_after_id = None

    try:
        page._filter_after_id = page.after(page.LIVE_FILTER_DEBOUNCE_MS, page._apply_filters_and_refresh)
    except Exception:
        # Fallback: oppdater umiddelbart
        try:
            page._apply_filters_and_refresh()
        except Exception:
            pass


def apply_filters_now(*, page: Any) -> None:
    """Kjør filter-oppdatering umiddelbart (og avbryt evt. debounce)."""
    if not getattr(page, "_tk_ok", False):
        return

    if getattr(page, "_filter_after_id", None):
        try:
            page.after_cancel(page._filter_after_id)
        except Exception:
            pass
        page._filter_after_id = None

    page._apply_filters_and_refresh()


def apply_filters_and_refresh(*, page: Any, dir_options: Sequence[Any]) -> None:
    """Filtrer datasettet og oppdater pivot + transaksjoner."""
    # Headless: just keep dataset pointer updated.
    if not getattr(page, "_tk_ok", False):
        return

    dataset = getattr(page, "dataset", None)

    if dataset is None or not isinstance(dataset, pd.DataFrame):
        page._df_filtered = None
        try:
            page._clear_tree(page._pivot_tree)
            page._clear_tree(page._tx_tree)
        except Exception:
            pass
        if getattr(page, "_lbl_tx_summary", None) is not None:
            try:
                page._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            except Exception:
                pass
        return

    search = (page._var_search.get() or "").strip()
    direction_label = page._var_direction.get()
    direction = next((o.value for o in dir_options if o.label == direction_label), None)
    min_amount = safe_float(page._var_min.get())
    max_amount = safe_float(page._var_max.get())

    # kontoserier: if none selected => no kontoserie-filter
    kontoserier = [i for i, v in enumerate(page._series_vars) if v.get()]
    kontoserier_arg = kontoserier if kontoserier else None

    df_f = filter_dataset(
        dataset,
        search=search,
        direction=direction,
        min_amount=min_amount,
        max_amount=max_amount,
        abs_amount=False,
        kontoserier=kontoserier_arg,
    )

    # Normalise Konto for safe selection/filtering.
    if "Konto" in df_f.columns:
        df_f = df_f.copy()
        df_f["Konto"] = df_f["Konto"].map(konto_to_str)

    page._df_filtered = df_f

    # Oppdater visning
    page._refresh_pivot()
    page._refresh_transactions_view()
