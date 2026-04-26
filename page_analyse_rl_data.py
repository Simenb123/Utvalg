"""page_analyse_rl_data.py

Data-lasting for RL-pivot (intervall-mapping, regnskapslinjer, SB, fjorårs-SB,
klientoverstyringer, SB-reparasjon).

Utskilt fra page_analyse_rl.py. Re-eksportert via page_analyse_rl som
fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

log = logging.getLogger("app")


def _load_current_client_account_overrides() -> dict[str, int]:
    try:
        import session as _session
        client = getattr(_session, "client", None)
        year = getattr(_session, "year", None)
    except Exception:
        client = None
        year = None

    if not client:
        return {}

    try:
        import src.shared.regnskap.client_overrides as regnskap_client_overrides
        return regnskap_client_overrides.load_account_overrides(
            str(client), year=str(year) if year else None)
    except Exception as exc:
        log.debug("Klientoverstyringer ikke tilgjengelig: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Service-baserte konto -> regnr-helpere
# ---------------------------------------------------------------------------


def _resolve_regnr_for_accounts(
    accounts: List[str],
    *,
    intervals: Optional[pd.DataFrame],
    regnskapslinjer: Optional[pd.DataFrame],
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Returner DataFrame[konto, regnr (Int64)] via den kanoniske RL-servicen.

    Bygger en ad-hoc ``RLMappingContext`` rundt de injiserte tabellene
    slik at Analyse, Saldobalanse og Admin alltid bruker samme
    konto -> regnr-resolusjon. ``regnr`` er ``pd.NA`` for kontoer som
    ikke treffer baseline-intervall og ikke har klient-override.
    """
    import regnskapslinje_mapping_service as _rl_svc

    context = _rl_svc.load_rl_mapping_context(
        intervals=intervals,
        regnskapslinjer=regnskapslinjer,
        account_overrides=account_overrides or {},
    )
    resolved = _rl_svc.resolve_accounts_to_rl(accounts, context=context)
    if resolved.empty:
        return pd.DataFrame({"konto": pd.Series(dtype=str), "regnr": pd.Series(dtype="Int64")})
    return resolved[["konto", "regnr"]].copy()


# ---------------------------------------------------------------------------
# Config-lasting
# ---------------------------------------------------------------------------

def load_rl_config() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Last intervall-mapping og regnskapslinjer fra datamappen.

    Returnerer (intervals_df, regnskapslinjer_df). Begge kan være None
    dersom filene ikke er importert ennå. Delegerer til den kanoniske
    RL-servicen slik at Analyse, Admin og Saldobalanse alle leser fra
    samme kilde.
    """
    try:
        import regnskapslinje_mapping_service as _rl_svc

        intervals, regnskapslinjer = _rl_svc.load_rl_config_dataframes()
    except Exception as exc:
        log.debug("RL-config-lasting feilet: %s", exc)
        intervals = None
        regnskapslinjer = None

    return intervals, regnskapslinjer


# Modul-nivå cache for SB-lasting. Profil viste 700-900ms pr kall — kallet
# skjer i hver Analyse-refresh. SB endres bare når brukeren importerer ny
# versjon, så vi cacher pr (klient, år, versjon-path, mtime).
_SB_CACHE: tuple[tuple[str, str, str, float], pd.DataFrame] | None = None


def _invalidate_sb_cache() -> None:
    """Tving re-lesing av SB neste gang. Brukes av tester eller etter
    eksplisitt SB-re-import."""
    global _SB_CACHE
    _SB_CACHE = None


def load_sb_for_session() -> Optional[pd.DataFrame]:
    """Last aktiv SB-versjon for gjeldende klient/år.

    Bruker session.client og session.year (satt av ui_main ved datalasting).
    Returnerer normalisert DataFrame med kolonnene konto, kontonavn, ib, ub, netto.
    Returnerer None ved manglende konfig eller feil.

    Caches pr (klient, år, versjon-path, mtime). Mtime-sjekken sikrer at
    cachen invalideres automatisk hvis filen erstattes på disk.
    """
    global _SB_CACHE
    try:
        import session as _session
        client = getattr(_session, "client", None)
        year = getattr(_session, "year", None)
    except Exception:
        return None

    if not client or not year:
        log.debug("load_sb_for_session: client/year ikke satt i session")
        return None

    try:
        import src.shared.client_store.store as client_store
        version = client_store.get_active_version(client, year=str(year), dtype="sb")
        if version is None:
            log.debug("Ingen aktiv SB-versjon for %s/%s", client, year)
            return None

        sb_path = Path(version.path)
        if not sb_path.exists():
            log.warning("SB-versjon-fil finnes ikke på disk: %s", sb_path)
            return None

        try:
            mtime = sb_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        cache_key = (str(client), str(year), str(sb_path), mtime)

        cached = _SB_CACHE
        if cached is not None and cached[0] == cache_key:
            return cached[1].copy()

        from trial_balance_reader import read_trial_balance
        df = read_trial_balance(sb_path)

        # Auto-reparasjon: tom SB fra gammel parser-bug → re-ekstraher fra SAF-T
        if (df is None or df.empty) and version.meta:
            df = _try_repair_empty_sb(client, str(year), version)

        if df is not None and not df.empty:
            log.info("SB lastet: %s (%d kontoer)", sb_path.name, len(df))
            _SB_CACHE = (cache_key, df)
            return df.copy()
        return df

    except Exception as exc:
        log.warning("load_sb_for_session: %s", exc)
        return None


def load_rl_amounts() -> dict[int, float]:
    """Returner ``{regnr: UB}`` aggregert fra aktiv SB for gjeldende session.

    Tom dict hvis SB eller RL-config mangler. Brukes av andre faner som
    bare trenger beløp per regnskapslinje (f.eks. Handlinger) og ikke vil
    bygge full pivot.
    """
    sb_df = load_sb_for_session()
    if sb_df is None or sb_df.empty:
        return {}
    intervals, regnskapslinjer = load_rl_config()
    if intervals is None or regnskapslinjer is None:
        return {}
    try:
        from page_analyse_rl_pivot import _aggregate_sb_to_regnr
        agg = _aggregate_sb_to_regnr(sb_df, intervals, regnskapslinjer=regnskapslinjer)
    except Exception as exc:
        log.debug("load_rl_amounts: aggregering feilet: %s", exc)
        return {}
    if agg is None or agg.empty or "regnr" not in agg.columns or "UB" not in agg.columns:
        return {}
    out: dict[int, float] = {}
    for _, row in agg.iterrows():
        try:
            out[int(row["regnr"])] = float(row["UB"])
        except Exception:
            continue
    return out


def _resolve_analysis_sb_views(*, page: Any) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Returner (grunnlag, AO-justert, effektiv) SB for Analyse."""
    base_sb_df = getattr(page, "_rl_sb_df", None)
    adjusted_sb_df = base_sb_df

    try:
        include_ao = bool(page._include_ao_enabled())
    except Exception:
        include_ao = False

    if not isinstance(base_sb_df, pd.DataFrame) or base_sb_df.empty:
        effective_sb_df = adjusted_sb_df if include_ao else base_sb_df
        return base_sb_df, adjusted_sb_df, effective_sb_df

    try:
        import session as _session
        import src.shared.regnskap.client_overrides as _rco
        import tilleggsposteringer as _tillegg

        client = getattr(_session, "client", None) or ""
        year = str(getattr(_session, "year", None) or "")
        if client and year:
            ao_entries = _rco.load_supplementary_entries(client, year)
            if ao_entries:
                adjusted_sb_df = _tillegg.apply_to_sb(base_sb_df, ao_entries)
    except Exception as exc:
        log.debug("_resolve_analysis_sb_views: AO-justering feilet: %s", exc)
        adjusted_sb_df = base_sb_df

    effective_sb_df = adjusted_sb_df if include_ao else base_sb_df
    return base_sb_df, adjusted_sb_df, effective_sb_df


def ensure_sb_prev_loaded(*, page: Any) -> Optional[pd.DataFrame]:
    """Last fjorårs-SB inn på ``page._rl_sb_prev_df`` idempotent.

    Returnerer df (kan være ``None`` hvis fjorårsdata mangler). Tidligere
    ble dette kun gjort i ``refresh_rl_pivot`` — utvidet hit slik at
    SB-konto-pivot og høyre SB-tre også får fjorårs-UB uten å måtte
    innom Regnskapslinje-modus først.
    """
    existing = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(existing, pd.DataFrame):
        return existing
    try:
        import previous_year_comparison
        import session as _session
        _client = getattr(_session, "client", None)
        _year = getattr(_session, "year", None)
        if not _client or _year is None:
            return None
        sb_prev = previous_year_comparison.load_previous_year_sb(_client, _year)
    except Exception as exc:
        log.debug("ensure_sb_prev_loaded: %s", exc)
        return None
    try:
        page._rl_sb_prev_df = sb_prev
    except Exception:
        pass
    return sb_prev


def _try_repair_empty_sb(
    client: str, year: str, version
) -> Optional[pd.DataFrame]:
    """Forsøk å reparere en tom SB-versjon ved å re-ekstrahere fra SAF-T-kildefilen."""
    try:
        source_path_str = (version.meta or {}).get("source_path", "")
        if not source_path_str:
            return None

        source = Path(source_path_str)
        # source_path peker på den midlertidige xlsx-filen, men vi trenger SAF-T-filen.
        # Sjekk om det finnes en aktiv HB-versjon med SAF-T-kilde i metadata.
        import src.shared.client_store.store as client_store
        hb_version = client_store.get_active_version(client, year=year, dtype="hb")
        saft_source = None
        if hb_version and hb_version.meta:
            hb_src = (hb_version.meta or {}).get("source_path", "")
            if hb_src:
                hb_p = Path(hb_src)
                if hb_p.exists() and hb_p.suffix.lower() in (".zip", ".xml"):
                    saft_source = hb_p

        # Sjekk også build-metadata for SAF-T-kilde
        if saft_source is None and hb_version and hb_version.meta:
            cache = (hb_version.meta or {}).get("dataset_cache", {})
            build = cache.get("build", {}) if isinstance(cache, dict) else {}
            build_file = build.get("file", "") if isinstance(build, dict) else ""
            if build_file:
                bf_p = Path(build_file)
                if bf_p.exists() and bf_p.suffix.lower() in (".zip", ".xml"):
                    saft_source = bf_p

        if saft_source is None:
            log.debug("Kan ikke reparere tom SB: ingen SAF-T-kilde funnet")
            return None

        from saft_trial_balance import extract_trial_balance_df_from_saft
        df = extract_trial_balance_df_from_saft(saft_source)
        if df is None or df.empty:
            return None

        # Oppdater SB-filen på disk
        sb_path = Path(version.path)
        df.to_excel(sb_path, index=False)
        log.info("Auto-reparert tom SB fra SAF-T: %s (%d kontoer)", saft_source.name, len(df))

        # Normaliser for retur
        from trial_balance_reader import read_trial_balance
        return read_trial_balance(sb_path)

    except Exception as exc:
        log.debug("_try_repair_empty_sb feilet: %s", exc)
        return None
