"""page_analyse_rl.py

Regnskapslinje-pivot for Analyse-fanen.

Ansvar:
- Laste intervall-mapping og regnskapslinjer fra regnskap_config
- Laste aktiv saldobalanse (SB) for gjeldende klient/år
- Bygge pivot på regnskapslinje-nivå med IB, UB (fra SB) og Netto/Antall (fra HB)
- Hente kontoer tilhørende valgte regnskapslinjer (for å filtrere tx-listen)

Kolonner i RL-pivot:
  regnr | Regnskapslinje | IB | UB | Antall

Datakilder:
  - IB, UB: aktiv SB-versjon for klient/år (via client_store + trial_balance_reader)
  - Antall:  sum av HB-transaksjoner (df_filtered)
  - Netto:   UB - IB (fra SB), eller sum av Beløp (HB) om SB mangler

Visningsregel:
  - Med SB:   vis RL der |UB| > 0 ELLER Antall > 0  (skjul rent tomme linjer)
  - Uten SB:  vis kun RL der Antall > 0
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

import formatting

log = logging.getLogger("app")

# Kolonnenavn brukt i treeview (vises som headings i RL-modus)
RL_PIVOT_HEADINGS = ("Nr", "Regnskapslinje", "IB", "Endring", "UB", "Antall", "UB i fjor", "Endring (fjor)", "Endring %")
# Standard konto-modus headings (for å tilbakestille)
KONTO_PIVOT_HEADINGS = ("Konto", "Kontonavn", "", "", "Sum", "Antall", "", "", "")


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
        import regnskap_client_overrides
        return regnskap_client_overrides.load_account_overrides(
            str(client), year=str(year) if year else None)
    except Exception as exc:
        log.debug("Klientoverstyringer ikke tilgjengelig: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Config-lasting
# ---------------------------------------------------------------------------

def load_rl_config() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Last intervall-mapping og regnskapslinjer fra datamappen.

    Returnerer (intervals_df, regnskapslinjer_df). Begge kan være None
    dersom filene ikke er importert ennå.
    """
    try:
        import regnskap_config
        intervals = regnskap_config.load_kontoplan_mapping()
    except Exception as exc:
        log.debug("Intervall-mapping ikke tilgjengelig: %s", exc)
        intervals = None

    try:
        import regnskap_config
        regnskapslinjer = regnskap_config.load_regnskapslinjer()
    except Exception as exc:
        log.debug("Regnskapslinjer ikke tilgjengelig: %s", exc)
        regnskapslinjer = None

    return intervals, regnskapslinjer


def load_sb_for_session() -> Optional[pd.DataFrame]:
    """Last aktiv SB-versjon for gjeldende klient/år.

    Bruker session.client og session.year (satt av ui_main ved datalasting).
    Returnerer normalisert DataFrame med kolonnene konto, kontonavn, ib, ub, netto.
    Returnerer None ved manglende konfig eller feil.
    """
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
        import client_store
        version = client_store.get_active_version(client, year=str(year), dtype="sb")
        if version is None:
            log.debug("Ingen aktiv SB-versjon for %s/%s", client, year)
            return None

        sb_path = Path(version.path)
        if not sb_path.exists():
            log.warning("SB-versjon-fil finnes ikke på disk: %s", sb_path)
            return None

        from trial_balance_reader import read_trial_balance
        df = read_trial_balance(sb_path)

        # Auto-reparasjon: tom SB fra gammel parser-bug → re-ekstraher fra SAF-T
        if (df is None or df.empty) and version.meta:
            df = _try_repair_empty_sb(client, str(year), version)

        if df is not None and not df.empty:
            log.info("SB lastet: %s (%d kontoer)", sb_path.name, len(df))
        return df

    except Exception as exc:
        log.warning("load_sb_for_session: %s", exc)
        return None


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
        import client_store
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


# ---------------------------------------------------------------------------
# Pivot-bygging
# ---------------------------------------------------------------------------

def build_rl_pivot(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    sb_df: Optional[pd.DataFrame] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Bygg regnskapslinje-pivot.

    Args:
        df_hb:          Filtrert HB-DataFrame med kolonnene "Konto" og "Beløp".
        intervals:      Intervall-mapping (fra, til, regnr).
        regnskapslinjer: Regnskapslinjer-definisjoner.
        sb_df:          Normalisert SB-DataFrame (konto, ib, ub, netto).
                        Hvis None brukes HB-sum som UB (fallback).

    Returnerer DataFrame med kolonnene:
        regnr (int), regnskapslinje (str), IB (float), Endring (float),
        UB (float), Antall (int)

    Visningsregel:
        Med SB:   vis RL der |UB| > 1e-9 ELLER Antall > 0
        Uten SB:  vis kun RL der Antall > 0
    """
    from regnskap_mapping import (
        apply_account_overrides,
        apply_interval_mapping,
        compute_sumlinjer,
        normalize_regnskapslinjer,
    )

    if df_hb is None or df_hb.empty:
        return _empty_pivot()
    if "Konto" not in df_hb.columns:
        return _empty_pivot()

    # --- Antall fra HB ---
    df_work = df_hb[["Konto"]].copy()
    df_work["Konto"] = df_work["Konto"].astype(str)
    df_work["_cnt"] = 1
    konto_cnt = df_work.groupby("Konto", as_index=False)["_cnt"].sum()
    konto_cnt.rename(columns={"Konto": "konto"}, inplace=True)

    # Map konto → regnr for HB
    try:
        cnt_mapped = apply_interval_mapping(konto_cnt, intervals, konto_col="konto").mapped
        cnt_mapped = apply_account_overrides(cnt_mapped, account_overrides, konto_col="konto")
    except Exception as exc:
        log.warning("RL-pivot: konto-mapping feilet: %s", exc)
        return _empty_pivot()

    antall_per_regnr = (
        cnt_mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)["_cnt"]
        .sum()
        .rename(columns={"_cnt": "Antall"})
    )
    antall_per_regnr["regnr"] = antall_per_regnr["regnr"].astype(int)

    # --- IB og UB ---
    if sb_df is not None and not sb_df.empty and "konto" in sb_df.columns:
        ib_ub = _aggregate_sb_to_regnr(sb_df, intervals, account_overrides=account_overrides)
    else:
        # Fallback: bruk HB Beløp som UB
        ib_ub = _aggregate_hb_to_regnr(df_hb, intervals, account_overrides=account_overrides)

    # --- Merge med regnskapslinjer ---
    try:
        regn = normalize_regnskapslinjer(regnskapslinjer)
        leaf = regn.loc[~regn["sumpost"]][["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    except Exception as exc:
        log.warning("RL-pivot: normalize_regnskapslinjer feilet: %s", exc)
        return _empty_pivot()

    merged = leaf.merge(ib_ub, how="left", on="regnr")
    merged = merged.merge(antall_per_regnr, how="left", on="regnr")

    merged["IB"] = merged["IB"].fillna(0.0)
    merged["UB"] = merged["UB"].fillna(0.0)
    merged["Endring"] = merged["UB"] - merged["IB"]
    merged["Antall"] = merged["Antall"].fillna(0).astype(int)

    all_lines = regn[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    if bool(all_lines["sumpost"].any()):
        base_ib = {int(r): float(v) for r, v in zip(merged["regnr"], merged["IB"])}
        base_ub = {int(r): float(v) for r, v in zip(merged["regnr"], merged["UB"])}
        base_endring = {int(r): float(v) for r, v in zip(merged["regnr"], merged["Endring"])}
        base_antall = {int(r): float(v) for r, v in zip(merged["regnr"], merged["Antall"])}

        try:
            ib_values = compute_sumlinjer(base_values=base_ib, regnskapslinjer=regn)
            ub_values = compute_sumlinjer(base_values=base_ub, regnskapslinjer=regn)
            endring_values = compute_sumlinjer(base_values=base_endring, regnskapslinjer=regn)
            antall_values = compute_sumlinjer(base_values=base_antall, regnskapslinjer=regn)
        except Exception as exc:
            log.warning("RL-pivot: kunne ikke beregne sumposter: %s", exc)
            ib_values = base_ib
            ub_values = base_ub
            endring_values = base_endring
            antall_values = base_antall

        all_lines["IB"] = all_lines["regnr"].map(lambda r: float(ib_values.get(int(r), 0.0)))
        all_lines["UB"] = all_lines["regnr"].map(lambda r: float(ub_values.get(int(r), 0.0)))
        all_lines["Endring"] = all_lines["regnr"].map(lambda r: float(endring_values.get(int(r), 0.0)))
        all_lines["Antall"] = (
            all_lines["regnr"]
            .map(lambda r: int(round(float(antall_values.get(int(r), 0.0)))))
            .astype(int)
        )
    else:
        all_lines = all_lines.merge(
            merged[["regnr", "IB", "Endring", "UB", "Antall"]],
            how="left",
            on="regnr",
        )
        all_lines["IB"] = all_lines["IB"].fillna(0.0)
        all_lines["UB"] = all_lines["UB"].fillna(0.0)
        all_lines["Endring"] = all_lines["Endring"].fillna(0.0)
        all_lines["Antall"] = all_lines["Antall"].fillna(0).astype(int)

    # --- Filtrer tomme linjer ---
    if sb_df is not None and not sb_df.empty:
        mask = (all_lines["UB"].abs() > 1e-9) | (all_lines["Antall"] > 0)
    else:
        mask = all_lines["Antall"] > 0

    merged = all_lines.loc[mask].sort_values("regnr").reset_index(drop=True)

    return merged[["regnr", "regnskapslinje", "IB", "Endring", "UB", "Antall"]]


def _aggregate_sb_to_regnr(
    sb_df: pd.DataFrame,
    intervals: pd.DataFrame,
    *,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Aggreger SB (IB/UB) per regnr via intervall-mapping."""
    from regnskap_mapping import apply_account_overrides, apply_interval_mapping

    work = sb_df[["konto", "ib", "ub"]].copy()
    work["ib"] = pd.to_numeric(work["ib"], errors="coerce").fillna(0.0)
    work["ub"] = pd.to_numeric(work["ub"], errors="coerce").fillna(0.0)

    try:
        mapped = apply_interval_mapping(work, intervals, konto_col="konto").mapped
        mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
    except Exception as exc:
        log.warning("_aggregate_sb_to_regnr: mapping feilet: %s", exc)
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    agg = (
        mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)
        .agg(IB=("ib", "sum"), UB=("ub", "sum"))
    )
    agg["regnr"] = agg["regnr"].astype(int)
    return agg


def _aggregate_hb_to_regnr(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    *,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Fallback: bruk sum av HB Beløp som UB (ingen IB tilgjengelig)."""
    from regnskap_mapping import apply_account_overrides, apply_interval_mapping

    if "Beløp" not in df_hb.columns:
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    work = df_hb[["Konto", "Beløp"]].copy()
    work["Konto"] = work["Konto"].astype(str)
    work["_bel"] = pd.to_numeric(work["Beløp"], errors="coerce").fillna(0.0)
    konto_agg = work.groupby("Konto", as_index=False)["_bel"].sum()
    konto_agg.rename(columns={"Konto": "konto"}, inplace=True)

    try:
        mapped = apply_interval_mapping(konto_agg, intervals, konto_col="konto").mapped
        mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
    except Exception as exc:
        log.warning("_aggregate_hb_to_regnr: mapping feilet: %s", exc)
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    agg = (
        mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)["_bel"]
        .sum()
        .rename(columns={"_bel": "UB"})
    )
    agg["IB"] = 0.0
    agg["regnr"] = agg["regnr"].astype(int)
    return agg[["regnr", "IB", "UB"]]


def _empty_pivot() -> pd.DataFrame:
    return pd.DataFrame(columns=["regnr", "regnskapslinje", "IB", "Endring", "UB", "Antall"])


def get_unmapped_rl_accounts(
    df_hb: Optional[pd.DataFrame],
    intervals: Optional[pd.DataFrame],
    *,
    account_overrides: Optional[dict[str, int]] = None,
) -> List[str]:
    """Returner kontoer i HB-scope som ikke treffer RL-intervall-mapping."""
    from regnskap_mapping import apply_account_overrides, apply_interval_mapping

    if df_hb is None or intervals is None or df_hb.empty or "Konto" not in df_hb.columns:
        return []

    kontos = df_hb["Konto"].dropna().astype(str).unique().tolist()
    if not kontos:
        return []

    probe = pd.DataFrame({"konto": kontos})
    try:
        mapped = apply_interval_mapping(probe, intervals, konto_col="konto").mapped
        mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
        return mapped.loc[mapped["regnr"].isna(), "konto"].astype(str).unique().tolist()
    except Exception as exc:
        log.warning("get_unmapped_rl_accounts: mapping feilet: %s", exc)
        return []


def _format_mapping_warning(unmapped_accounts: List[str]) -> str:
    if not unmapped_accounts:
        return ""

    count = len(unmapped_accounts)
    sample = ", ".join(unmapped_accounts[:5])
    if count > 5:
        sample += ", ..."

    noun = "konto" if count == 1 else "kontoer"
    return f"Mappingavvik: {count} {noun} uten regnskapslinje-mapping ({sample})"


def _expand_selected_regnskapslinjer(
    regnskapslinjer: Optional[pd.DataFrame],
    regnr_values: List[int],
) -> List[int]:
    if not regnr_values:
        return []
    if regnskapslinjer is None or regnskapslinjer.empty:
        return regnr_values

    try:
        from regnskap_mapping import expand_regnskapslinje_selection
        return expand_regnskapslinje_selection(
            regnskapslinjer=regnskapslinjer,
            selected_regnr=regnr_values,
        )
    except Exception as exc:
        log.warning("Kunne ikke utvide regnskapslinjevalg: %s", exc)
        return regnr_values


def get_selected_rl_rows(*, page: Any) -> List[tuple[int, str]]:
    """Returner valgte regnskapslinjer fra pivoten som (regnr, navn)."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

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

    rows: List[tuple[int, str]] = []
    for item in selected:
        try:
            regnr = int(str(tree.set(item, "Konto") or "").strip())
        except Exception:
            continue
        try:
            navn = str(tree.set(item, "Kontonavn") or "").strip()
        except Exception:
            navn = ""
        rows.append((regnr, navn))
    return rows


def build_rl_account_drilldown(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    sb_df: Optional[pd.DataFrame] = None,
    regnr_filter: Optional[List[int]] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Bygg kontooversikt under valgt(e) regnskapslinjer."""
    from regnskap_mapping import apply_account_overrides, apply_interval_mapping, normalize_regnskapslinjer

    if df_hb is None or df_hb.empty or "Konto" not in df_hb.columns:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    work = pd.DataFrame()
    work["konto"] = df_hb["Konto"].astype(str)
    if "Kontonavn" in df_hb.columns:
        work["kontonavn"] = df_hb["Kontonavn"].fillna("").astype(str)
    else:
        work["kontonavn"] = ""
    work["_cnt"] = 1
    if "Beløp" in df_hb.columns:
        work["_hb_sum"] = pd.to_numeric(df_hb["Beløp"], errors="coerce").fillna(0.0)
    else:
        work["_hb_sum"] = 0.0

    konto_agg = (
        work.groupby(["konto", "kontonavn"], as_index=False)
        .agg(Antall=("_cnt", "sum"), HB_sum=("_hb_sum", "sum"))
    )

    try:
        mapped = apply_interval_mapping(konto_agg, intervals, konto_col="konto").mapped
        mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception as exc:
        log.warning("build_rl_account_drilldown: %s", exc)
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    expanded_regnr = _expand_selected_regnskapslinjer(regnskapslinjer, regnr_filter or [])

    if expanded_regnr:
        mapped = mapped.loc[mapped["regnr"].isin(expanded_regnr)].copy()
    else:
        mapped = mapped.loc[mapped["regnr"].notna()].copy()

    if mapped.empty:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    rl_names = regn[["regnr", "regnskapslinje"]].copy()
    rl_names["regnr"] = rl_names["regnr"].astype(int)
    mapped["regnr"] = mapped["regnr"].astype(int)
    mapped = mapped.merge(rl_names, how="left", on="regnr")

    if sb_df is not None and not sb_df.empty and "konto" in sb_df.columns:
        sb_work = sb_df.copy()
        sb_work["konto"] = sb_work["konto"].astype(str)
        if "kontonavn" not in sb_work.columns:
            sb_work["kontonavn"] = ""
        sb_work["kontonavn"] = sb_work["kontonavn"].fillna("").astype(str)
        sb_work["ib"] = pd.to_numeric(sb_work.get("ib"), errors="coerce").fillna(0.0)
        sb_work["ub"] = pd.to_numeric(sb_work.get("ub"), errors="coerce").fillna(0.0)
        sb_acc = (
            sb_work.groupby("konto", as_index=False)
            .agg(
                kontonavn_sb=("kontonavn", "first"),
                IB=("ib", "sum"),
                UB=("ub", "sum"),
            )
        )
        out = mapped.merge(sb_acc, how="left", on="konto")
        out["IB"] = out["IB"].fillna(0.0)
        out["UB"] = out["UB"].fillna(0.0)
        out["Endring"] = out["UB"] - out["IB"]
        out["Kontonavn"] = out["kontonavn"].where(out["kontonavn"].astype(str).str.strip() != "", out["kontonavn_sb"])
    else:
        out = mapped.copy()
        out["IB"] = 0.0
        out["UB"] = pd.to_numeric(out["HB_sum"], errors="coerce").fillna(0.0)
        out["Endring"] = out["UB"]
        out["Kontonavn"] = out["kontonavn"]

    out["Kontonavn"] = out["Kontonavn"].fillna("").astype(str)
    out["Antall"] = pd.to_numeric(out["Antall"], errors="coerce").fillna(0).astype(int)
    out["Nr"] = out["regnr"].astype(int)
    out["Regnskapslinje"] = out["regnskapslinje"].fillna("").astype(str)
    out["Konto"] = out["konto"].astype(str)

    out = out.sort_values(["Nr", "Konto"]).reset_index(drop=True)
    return out[["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]]


def build_selected_rl_account_drilldown(*, page: Any) -> tuple[pd.DataFrame, List[tuple[int, str]]]:
    """Bygg drilldown-data for valgte regnskapslinjer i Analyse."""
    selected_rows = get_selected_rl_rows(page=page)
    regnr_filter = [regnr for regnr, _ in selected_rows]

    df_filtered = getattr(page, "_df_filtered", None)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = getattr(page, "_rl_sb_df", None)
    account_overrides = _load_current_client_account_overrides()

    if not isinstance(df_filtered, pd.DataFrame) or intervals is None or regnskapslinjer is None:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]), selected_rows

    return (
        build_rl_account_drilldown(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=sb_df,
            regnr_filter=regnr_filter,
            account_overrides=account_overrides,
        ),
        selected_rows,
    )


def build_selected_rl_detail_context(*, page: Any) -> dict[str, Any]:
    """Bygg rikere detaljkontekst for valgte regnskapslinjer i Analyse."""
    drill_df, selected_rows = build_selected_rl_account_drilldown(page=page)
    if drill_df is None or not isinstance(drill_df, pd.DataFrame):
        drill_df = pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame):
        df_filtered = pd.DataFrame()

    selected_accounts = [str(value).strip() for value in drill_df.get("Konto", pd.Series(dtype=str)).astype(str).tolist() if str(value).strip()]
    selected_set = set(selected_accounts)
    if not df_filtered.empty and "Konto" in df_filtered.columns and selected_set:
        tx_df = df_filtered.loc[df_filtered["Konto"].astype(str).str.strip().isin(selected_set)].copy()
    else:
        tx_df = pd.DataFrame(columns=df_filtered.columns if isinstance(df_filtered, pd.DataFrame) else [])

    scope_parts = [f"{int(regnr)} {str(name or '').strip()}".strip() for regnr, name in selected_rows]
    scope_text = ", ".join(scope_parts) if scope_parts else "Ingen regnskapslinje valgt"

    ib_sum = float(pd.to_numeric(drill_df.get("IB", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0
    endring_sum = float(pd.to_numeric(drill_df.get("Endring", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0
    ub_sum = float(pd.to_numeric(drill_df.get("UB", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0

    summary = (
        f"Regnskapslinjer: {scope_text} | "
        f"Kontoer: {len(selected_accounts)} | "
        f"Transaksjoner: {len(tx_df.index)} | "
        f"IB: {formatting.fmt_amount(ib_sum)} | "
        f"Endring: {formatting.fmt_amount(endring_sum)} | "
        f"UB: {formatting.fmt_amount(ub_sum)}"
    )

    return {
        "accounts_df": drill_df,
        "summary": summary,
        "selected_rows": selected_rows,
        "selected_accounts": selected_accounts,
        "transactions_df": tx_df,
        "mapping_warning": str(getattr(page, "_rl_mapping_warning", "") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Pivot-headings
# ---------------------------------------------------------------------------

def update_pivot_headings(*, page: Any, mode: str) -> None:
    """Oppdater kolonneoverskrifter i pivot_tree basert på modus.

    mode = "Regnskapslinje" → RL_PIVOT_HEADINGS
    mode = "Konto"          → KONTO_PIVOT_HEADINGS
    """
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    headings = RL_PIVOT_HEADINGS if mode == "Regnskapslinje" else KONTO_PIVOT_HEADINGS
    cols = ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall",
            "UB_fjor", "Endring_fjor", "Endring_pct")  # interne kolonne-IDer

    for col_id, heading in zip(cols, headings):
        try:
            tree.heading(col_id, text=heading)
        except Exception:
            pass

    # Sjekk om fjorårsdata er tilgjengelig
    has_prev = bool(getattr(page, "_rl_sb_prev_df", None) is not None)

    # Juster bredder for RL-modus (defaults – auto-fit kjøres etter data er fylt)
    if mode == "Regnskapslinje":
        try:
            # Nr-kolonnen er smal — bare et 2-5-sifret RL-nummer
            tree.column("Konto",    width=44,  minwidth=34,  stretch=False, anchor="e")
            # Regnskapslinje-navn trenger bredde
            tree.column("Kontonavn", width=290, minwidth=160, stretch=True,  anchor="w")
            tree.column("IB",       width=110, minwidth=75,  stretch=False, anchor="e")
            tree.column("Endring",  width=110, minwidth=75,  stretch=False, anchor="e")
            tree.column("Sum",      width=115, minwidth=80,  stretch=False, anchor="e")
            # Antall trenger ikke mye plass
            tree.column("Antall",   width=48,  minwidth=38,  stretch=False, anchor="e")
        except Exception:
            pass
        # Fjorårskolonner: vis/skjul basert på tilgjengelige data
        if has_prev:
            try:
                tree.column("UB_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_fjor", width=115, minwidth=80, anchor="e")
                tree.column("Endring_pct", width=80, minwidth=60, anchor="e")
            except Exception:
                pass
        else:
            try:
                tree.column("UB_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_fjor", width=0, minwidth=0, stretch=False)
                tree.column("Endring_pct", width=0, minwidth=0, stretch=False)
            except Exception:
                pass
    else:
        try:
            tree.column("Konto", width=80, minwidth=50, stretch=False, anchor="w")
            tree.column("Kontonavn", width=220, minwidth=120, stretch=True, anchor="w")
            tree.column("IB", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Endring", width=0, minwidth=0, stretch=False, anchor="e")
            tree.column("Sum", width=115, minwidth=80, stretch=False, anchor="e")
            tree.column("Antall", width=70, minwidth=50, stretch=False, anchor="e")
            tree.column("UB_fjor", width=0, minwidth=0, stretch=False)
            tree.column("Endring_fjor", width=0, minwidth=0, stretch=False)
            tree.column("Endring_pct", width=0, minwidth=0, stretch=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GUI-refresh
# ---------------------------------------------------------------------------

def refresh_rl_pivot(*, page: Any) -> None:
    """Fyll pivot_tree med regnskapslinjer (IB, UB, Antall)."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    selected_regnr = [regnr for regnr, _ in get_selected_rl_rows(page=page)]

    # Oppdater headings
    update_pivot_headings(page=page, mode="Regnskapslinje")

    try:
        page._clear_tree(tree)
    except Exception:
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        return

    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    try:
        page._rl_mapping_warning = ""
    except Exception:
        pass

    if intervals is None or regnskapslinjer is None:
        try:
            page._rl_mapping_warning = "Regnskapslinje-mapping ikke konfigurert."
        except Exception:
            pass
        _show_rl_not_configured(tree)
        return

    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = getattr(page, "_rl_sb_df", None)

    account_overrides = _load_current_client_account_overrides()
    try:
        from regnskap_mapping import normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
        sumline_regnr = {int(v) for v in regn.loc[regn["sumpost"], "regnr"].astype(int).tolist()}
        # Klassifiser sumposter etter nivå: høyt sumnivå = hovedsum
        _sumnivaa_map: dict[int, int] = {}
        if "sumnivaa" in regn.columns:
            for _, r in regn.loc[regn["sumpost"]].iterrows():
                try:
                    _sumnivaa_map[int(r["regnr"])] = int(r["sumnivaa"]) if r["sumnivaa"] is not None else 1
                except Exception:
                    pass
    except Exception:
        sumline_regnr = set()
        _sumnivaa_map = {}
    unmapped_accounts = get_unmapped_rl_accounts(df_filtered, intervals, account_overrides=account_overrides)
    try:
        page._rl_mapping_warning = _format_mapping_warning(unmapped_accounts)
    except Exception:
        pass

    try:
        pivot_df = build_rl_pivot(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=sb_df,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        log.warning("refresh_rl_pivot: feil ved bygging: %s", exc)
        return

    # --- Fjorårsdata ---
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if sb_prev is None:
        try:
            import previous_year_comparison
            import session as _session
            _client = getattr(_session, "client", None)
            _year = getattr(_session, "year", None)
            if _client and _year:
                sb_prev = previous_year_comparison.load_previous_year_sb(_client, _year)
                page._rl_sb_prev_df = sb_prev
        except Exception:
            sb_prev = None

    has_prev = sb_prev is not None and not sb_prev.empty
    if has_prev:
        try:
            import previous_year_comparison
            import regnskap_client_overrides as _rco
            import session as _sess
            _cl = getattr(_sess, "client", None) or ""
            _yr = getattr(_sess, "year", None) or ""
            prior_overrides = _rco.load_prior_year_overrides(_cl, _yr) if _cl and _yr else None
            pivot_df = previous_year_comparison.add_previous_year_columns(
                pivot_df, sb_prev, intervals, regnskapslinjer,
                account_overrides=account_overrides,
                prior_year_overrides=prior_overrides,
            )
        except Exception as exc:
            log.warning("refresh_rl_pivot: fjorårskolonner feilet: %s", exc)
            has_prev = False

    try:
        page._pivot_df_last = pivot_df.copy()
    except Exception:
        pass

    has_sb = sb_df is not None and not sb_df.empty

    # Sjekk om sumposter skal skjules
    _hide_sum = False
    try:
        _hsv = getattr(page, "_var_hide_sumposter", None)
        if _hsv is not None:
            _hide_sum = bool(_hsv.get())
    except Exception:
        pass

    # Last RL-kommentarer
    _rl_comments: dict[str, str] = {}
    try:
        import regnskap_client_overrides as _rco
        import session as _sess
        _cl = getattr(_sess, "client", None) or ""
        if _cl:
            _rl_comments = _rco.load_comments(_cl).get("rl", {})
    except Exception:
        pass

    for _, row in pivot_df.iterrows():
        regnr_int = int(row["regnr"])
        regnr = str(regnr_int)
        navn = str(row.get("regnskapslinje", "") or "")
        tags = ()
        if regnr_int in sumline_regnr:
            if _hide_sum:
                continue
            sumnivaa = _sumnivaa_map.get(regnr_int, 1)
            if sumnivaa >= 2:
                navn = f"Σ {navn}".strip()
                tags = ("sumline_major",)
            else:
                navn = f"Σ {navn}".strip()
                tags = ("sumline",)
        ib_val = float(row.get("IB", 0.0))
        endring_val = float(row.get("Endring", 0.0))
        ub_val = float(row.get("UB", 0.0))
        cnt_val = int(row.get("Antall", 0))

        if has_sb:
            ib_txt = formatting.fmt_amount(ib_val)
            endring_txt = formatting.fmt_amount(endring_val)
            ub_txt = formatting.fmt_amount(ub_val)
        else:
            ib_txt = ""
            endring_txt = formatting.fmt_amount(endring_val) + " *"
            ub_txt = formatting.fmt_amount(ub_val) + " *"

        cnt_txt = formatting.format_int_no(cnt_val)

        # Fjorårskolonner
        if has_prev:
            ub_fjor_val = row.get("UB_fjor")
            endring_fjor_val = row.get("Endring_fjor")
            endring_pct_val = row.get("Endring_pct")
            ub_fjor_txt = formatting.fmt_amount(float(ub_fjor_val)) if ub_fjor_val is not None and ub_fjor_val == ub_fjor_val else ""
            endring_fjor_txt = formatting.fmt_amount(float(endring_fjor_val)) if endring_fjor_val is not None and endring_fjor_val == endring_fjor_val else ""
            endring_pct_txt = f"{float(endring_pct_val):.1f} %" if endring_pct_val is not None and endring_pct_val == endring_pct_val else ""
        else:
            ub_fjor_txt = ""
            endring_fjor_txt = ""
            endring_pct_txt = ""

        # Legg til kommentar-markering
        _comment = _rl_comments.get(regnr, "")
        if _comment and regnr_int not in sumline_regnr:
            navn = f"\u270e {navn}  \u2014 {_comment}"
            tags = tags + ("commented",) if tags else ("commented",)

        try:
            tree.insert("", "end", values=(regnr, navn, ib_txt, endring_txt, ub_txt, cnt_txt,
                                           ub_fjor_txt, endring_fjor_txt, endring_pct_txt), tags=tags)
        except Exception:
            continue

    # Auto-juster kolonnene dersom fjorårsdata akkurat ble lastet
    try:
        import page_analyse_columns as _pac
        _pac.update_pivot_columns_for_prev_year(page=page)
    except Exception:
        pass

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
        except Exception:
            pass

    if selected_regnr:
        try:
            page._restore_rl_pivot_selection(selected_regnr)
        except Exception:
            pass


def _show_rl_not_configured(tree: Any) -> None:
    try:
        tree.insert(
            "", "end",
            values=("-", "Regnskapslinjer/mapping ikke konfigurert (Innstillinger)", "", "", "", ""),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Kontooppslag for RL-valg
# ---------------------------------------------------------------------------

def get_selected_rl_accounts(*, page: Any) -> List[str]:
    """Returner kontoer (str) tilhørende valgte regnskapslinjer i pivot_tree."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

    selected_regnr: List[int] = []
    try:
        selected = tree.selection()
        if not selected:
            selected = tree.get_children()
        for item in selected:
            try:
                regnr_str = tree.set(item, "Konto")
                selected_regnr.append(int(regnr_str))
            except (ValueError, TypeError, Exception):
                pass
    except Exception:
        return []

    if not selected_regnr:
        return []

    intervals = getattr(page, "_rl_intervals", None)
    df_filtered = getattr(page, "_df_filtered", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    if intervals is None or df_filtered is None or not isinstance(df_filtered, pd.DataFrame):
        return []

    if "Konto" not in df_filtered.columns:
        return []

    kontos_in_hb = df_filtered["Konto"].dropna().astype(str).unique().tolist()
    if not kontos_in_hb:
        return []

    expanded_regnr = _expand_selected_regnskapslinjer(regnskapslinjer, selected_regnr)
    if not expanded_regnr:
        return []

    try:
        from regnskap_mapping import apply_account_overrides, apply_interval_mapping
        account_overrides = _load_current_client_account_overrides()
        temp = pd.DataFrame({"konto": kontos_in_hb, "ub": [0.0] * len(kontos_in_hb)})
        result = apply_interval_mapping(temp, intervals)
        mapped = apply_account_overrides(result.mapped, account_overrides, konto_col="konto")
        matching = (
            mapped
            .loc[mapped["regnr"].isin(expanded_regnr), "konto"]
            .tolist()
        )
        deduped: List[str] = []
        seen: set[str] = set()
        for konto in matching:
            konto_s = str(konto or "").strip()
            if not konto_s or konto_s in seen:
                continue
            deduped.append(konto_s)
            seen.add(konto_s)
        return deduped
    except Exception as exc:
        log.warning("get_selected_rl_accounts: feil ved konto-oppslag: %s", exc)
        return []
