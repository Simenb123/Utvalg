"""page_analyse_refresh.py — refresh-pipeline for AnalysePage.

Utskilt fra page_analyse.py. Funksjonene tar `page` som første argument.
AnalysePage beholder tynne delegat-metoder for bakoverkompatibilitet, slik
at tester kan kalle `page_analyse.AnalysePage.refresh_from_session(page, ...)`
og monkey-patche `page._reload_rl_config` etc.
"""

from __future__ import annotations

import logging
from typing import Any

import session as _session_default

import page_analyse_filters_live

log = logging.getLogger(__name__)


def refresh_from_session(
    page: Any,
    sess: object = _session_default,
    *,
    defer_heavy: bool = False,
) -> None:
    """Reload data from session and refresh UI.

    Viktig: Vi beholder råverdien i page.dataset (ikke bare DataFrame),
    slik at headless-tester kan sette dummy-verdier og verifisere at
    metoden faktisk oppdaterer feltet.
    """
    df = getattr(sess, "dataset", None)
    page.dataset = df
    try:
        cur_key = (getattr(sess, "client", None), getattr(sess, "year", None))
    except Exception:
        cur_key = (None, None)
    prev_key = getattr(page, "_session_cache_key", None)
    if prev_key != cur_key:
        page._rl_sb_prev_df = None
        try:
            setattr(page, "_nk_brreg_data", None)
        except Exception:
            pass
        try:
            import page_analyse_columns as _pac
            _pac.clear_pivot_columns_for_brreg(page=page)
        except Exception:
            pass
        page._session_cache_key = cur_key
    page._refresh_mva_code_choices()
    page._update_data_level()
    if defer_heavy:
        page._schedule_heavy_refresh()
        return
    page._run_full_refresh()


def run_full_refresh(page: Any) -> None:
    page._reload_rl_config()
    page._apply_filters_and_refresh()
    page._adapt_pivot_columns_for_mode()
    page._update_data_level()


def schedule_heavy_refresh(page: Any) -> None:
    """Planlegg én tung refresh etter at GUI har fått tilbake kontroll."""
    page._heavy_refresh_generation += 1
    generation = page._heavy_refresh_generation

    pending = getattr(page, "_heavy_refresh_after_id", None)
    if pending:
        try:
            page.after_cancel(pending)
        except Exception:
            pass
        page._heavy_refresh_after_id = None

    if not getattr(page, "_tk_ok", False):
        page._run_full_refresh()
        return

    def _start() -> None:
        if generation != page._heavy_refresh_generation:
            return
        page._heavy_refresh_after_id = None
        page._run_heavy_refresh_staged(generation)

    try:
        page._heavy_refresh_after_id = page.after_idle(_start)
    except Exception:
        page._heavy_refresh_after_id = None
        page._run_full_refresh()


def run_heavy_refresh_staged(
    page: Any,
    generation: int | None = None,
    *,
    dir_options: Any = None,
) -> None:
    """Kjør første Analyse-render i små steg for å unngå GUI-heng."""
    token = page._heavy_refresh_generation if generation is None else generation

    def _is_stale() -> bool:
        return token != page._heavy_refresh_generation

    def _run_next(step_index: int = 0) -> None:
        if _is_stale():
            return

        if step_index == 0:
            try:
                page._reload_rl_config()
            except Exception:
                log.exception("Analyse staged refresh: reload RL config failed")
        elif step_index == 1:
            try:
                df_filtered = page_analyse_filters_live.build_filtered_df(
                    page=page, dir_options=dir_options,
                )
                page._df_filtered = df_filtered
                if df_filtered is None:
                    page_analyse_filters_live._clear_views_for_missing_dataset(page=page)
            except Exception:
                log.exception("Analyse staged refresh: build filtered df failed")
                page._df_filtered = None
                try:
                    page_analyse_filters_live._clear_views_for_missing_dataset(page=page)
                except Exception:
                    pass
        elif step_index == 2:
            if page._df_filtered is not None:
                try:
                    page._refresh_pivot()
                except Exception:
                    log.exception("Analyse staged refresh: pivot refresh failed")
        elif step_index == 3:
            if page._df_filtered is not None:
                try:
                    page._refresh_transactions_view()
                except Exception:
                    log.exception("Analyse staged refresh: transactions refresh failed")
        elif step_index == 4:
            if page._df_filtered is not None:
                try:
                    page._refresh_detail_panel()
                except Exception:
                    log.exception("Analyse staged refresh: detail refresh failed")
        elif step_index == 5:
            try:
                page._adapt_pivot_columns_for_mode()
            except Exception:
                log.exception("Analyse staged refresh: adapt pivot columns failed")
            try:
                page._update_data_level()
            except Exception:
                log.exception("Analyse staged refresh: update data level failed")
            return

        try:
            page.after(10, lambda: _run_next(step_index + 1))
        except Exception:
            _run_next(step_index + 1)

    _run_next()
