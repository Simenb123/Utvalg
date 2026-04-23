"""page_analyse_refresh.py — refresh-pipeline for AnalysePage.

Utskilt fra page_analyse.py. Funksjonene tar `page` som første argument.
AnalysePage beholder tynne delegat-metoder for bakoverkompatibilitet, slik
at tester kan kalle `page_analyse.AnalysePage.refresh_from_session(page, ...)`
og monkey-patche `page._reload_rl_config` etc.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import session as _session_default

import page_analyse_filters_live

log = logging.getLogger(__name__)

# Sett UTVALG_PROFILE_REFRESH=1 i miljøet for å få timing-rapport på
# hver Analyse-refresh. Default av — vi vil ikke spamme prod-loggen.
_PROFILE_REFRESH = os.environ.get("UTVALG_PROFILE_REFRESH", "").strip().lower() in {
    "1", "true", "yes", "on",
}


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
        try:
            import page_analyse_ui_helpers as _puh
            page.after_idle(lambda: _puh._nk_auto_fetch_brreg(page))
        except Exception:
            pass
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


_STAGE_NAMES = (
    "0_reload_rl_config",
    "1_build_filtered_df",
    "2_refresh_pivot",
    "3_refresh_transactions_view",
    "4_refresh_detail_panel",
    "5_adapt_columns+update_data_level",
)

# Brukerrettet status-tekst pr stage. Brukes til å oppdatere App-overlay
# mellom stages slik at brukeren ser tekstprogresjon selv om Tk-
# progressbaren fryser pga. tung jobb i hovedtråden.
_STAGE_STATUS_TEXT = (
    "Laster regnskapsoppsett...",
    "Filtrerer hovedbok...",
    "Bygger pivot...",
    "Bygger transaksjonsvisning...",
    "Bygger detaljpanel...",
    "Justerer kolonner...",
)


def run_heavy_refresh_staged(
    page: Any,
    generation: int | None = None,
    *,
    dir_options: Any = None,
) -> None:
    """Kjør første Analyse-render i små steg for å unngå GUI-heng.

    Hvis miljøvariabelen UTVALG_PROFILE_REFRESH=1 er satt, måles og logges
    tiden hvert steg bruker — nyttig for å diagnostisere treghet.
    """
    token = page._heavy_refresh_generation if generation is None else generation
    timings: dict[str, float] = {} if _PROFILE_REFRESH else {}
    overall_start = time.perf_counter() if _PROFILE_REFRESH else 0.0

    def _is_stale() -> bool:
        return token != page._heavy_refresh_generation

    def _run_next(step_index: int = 0) -> None:
        if _is_stale():
            return

        # Oppdater app-overlay-tekst hvis registrert. Setteren er
        # typisk LoadingOverlay.set_text fra ui_main App-overlayen.
        text_setter = getattr(page, "_loading_status_text_setter", None)
        if callable(text_setter) and 0 <= step_index < len(_STAGE_STATUS_TEXT):
            try:
                text_setter(_STAGE_STATUS_TEXT[step_index])
            except Exception:
                pass

        stage_start = time.perf_counter() if _PROFILE_REFRESH else 0.0

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

            if _PROFILE_REFRESH:
                timings[_STAGE_NAMES[step_index]] = time.perf_counter() - stage_start
                _log_refresh_timings(timings, time.perf_counter() - overall_start)

            # Kall registrerte one-shot-callbacks når staged refresh er ferdig.
            # Brukes f.eks. av ui_main for å skjule LoadingOverlay etter at
            # Analyse-fanen faktisk er klar (ikke bare når dataset er bygget).
            cbs = getattr(page, "_post_heavy_refresh_callbacks", None) or []
            page._post_heavy_refresh_callbacks = []
            for cb in cbs:
                try:
                    cb()
                except Exception:
                    log.exception("post_heavy_refresh callback failed")
            return

        if _PROFILE_REFRESH and step_index < len(_STAGE_NAMES):
            timings[_STAGE_NAMES[step_index]] = time.perf_counter() - stage_start

        try:
            page.after(10, lambda: _run_next(step_index + 1))
        except Exception:
            _run_next(step_index + 1)

    _run_next()


def _log_refresh_timings(timings: dict[str, float], total: float) -> None:
    """Log en kortfattet tidsrapport. Kalt kun når UTVALG_PROFILE_REFRESH=1."""
    parts = ["[REFRESH PROFILE]", f"total={total*1000:.0f}ms"]
    for stage in _STAGE_NAMES:
        ms = timings.get(stage, 0.0) * 1000
        parts.append(f"{stage}={ms:.0f}ms")
    log.warning(" | ".join(parts))
