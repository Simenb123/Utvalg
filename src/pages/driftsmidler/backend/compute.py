"""Driftsmidler — beregningskjerne (backend, ingen tkinter).

Inneholder:
- ``get_konto_ranges`` — slå opp kontorange for et regnskapslinje-nr
- ``classify_dm_transactions`` — kategoriser DM-transaksjoner via motpostlogikk
- ``build_dm_reconciliation`` — bygg avstemming for varige driftsmidler
- ``safe_float`` — defensiv tall-konvertering

All input er rene DataFrames + dicts. Funksjonene returnerer DataFrames
eller dicts. Ingen GUI-objekter passerer grensa.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanter — kontorange-definisjoner
# ---------------------------------------------------------------------------

_LEVERANDOR_RANGES = [(2400, 2499)]
_BANK_RANGES = [(1900, 1999)]
_SALG_RANGES = [(3000, 3999)]
_GEVINST_TAP_RANGES = [(8000, 8199)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_konto_ranges(
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    regnr: int,
) -> list[tuple[int, int]]:
    """Hent kontorange for et regnr fra intervall-tabellen.

    Hvis ``regnr`` er en sumpost (har underliggende leaf-regnr i
    ``regnskapslinjer``), ekspanderes alle leaf-regnr og rangene fra
    alle kombineres.

    Returnerer tom liste hvis input mangler eller ingen rader matcher.
    """
    if intervals is None or (hasattr(intervals, "empty") and intervals.empty):
        return []

    leaf_set: set[int] = {regnr}
    if regnskapslinjer is not None and not (
        hasattr(regnskapslinjer, "empty") and regnskapslinjer.empty
    ):
        try:
            from src.shared.regnskap.mapping import (
                expand_regnskapslinje_selection,
                normalize_regnskapslinjer,
            )
            regn = normalize_regnskapslinjer(regnskapslinjer)
            if bool(regn.loc[regn["regnr"].astype(int) == regnr, "sumpost"].any()):
                expanded = expand_regnskapslinje_selection(
                    regnskapslinjer=regnskapslinjer, selected_regnr=[regnr]
                )
                if expanded:
                    leaf_set = set(expanded)
        except Exception as exc:
            log.warning("get_konto_ranges: %s", exc)

    ranges: list[tuple[int, int]] = []
    try:
        for _, row in intervals.iterrows():
            if int(row["regnr"]) in leaf_set:
                ranges.append((int(row["fra"]), int(row["til"])))
    except Exception as exc:
        log.warning("get_konto_ranges loop: %s", exc)
    return ranges


def safe_float(val: Any) -> float:
    """Defensiv konvertering til float — returnerer 0.0 ved feil."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def classify_dm_transactions(
    df_all: pd.DataFrame,
    dm_ranges: list[tuple[int, int]],
    avskr_ranges: list[tuple[int, int]],
) -> pd.DataFrame:
    """Klassifiser DM-transaksjoner basert på motpost (vektorisert).

    Returnerer DataFrame med DM-transaksjonene pluss kolonner:
      ``_konto_num, _bilag, _belop, _motpost_konto, _motpost_navn, dm_kategori``
    """
    if df_all is None or df_all.empty or "Konto" not in df_all.columns:
        return pd.DataFrame()

    df = df_all.copy()
    df["_konto_num"] = pd.to_numeric(df["Konto"], errors="coerce")
    df["_bilag"] = df["Bilag"].astype(str).str.strip()
    df["_belop"] = pd.to_numeric(df.get("Beløp", 0), errors="coerce").fillna(0.0)

    # Identifiser DM-rader (vektorisert)
    dm_mask = _build_range_mask(df["_konto_num"], dm_ranges)
    dm_df = df.loc[dm_mask].copy()
    if dm_df.empty:
        return pd.DataFrame()

    # Finn alle rader på bilag som inneholder DM-transaksjoner
    dm_bilags = dm_df["_bilag"].unique()
    all_on_bilags = df[df["_bilag"].isin(dm_bilags)].copy()

    # Filtrer ut DM-rader selv → bare motposter
    non_dm = all_on_bilags[
        ~_build_range_mask(all_on_bilags["_konto_num"], dm_ranges)
    ].copy()

    if non_dm.empty:
        dm_df["dm_kategori"] = "Ukjent"
        dm_df["_motpost_konto"] = ""
        dm_df["_motpost_navn"] = ""
        return dm_df

    # Klassifiser motposter vektorisert
    non_dm["_mp_avskr"] = _build_range_mask(non_dm["_konto_num"], avskr_ranges)
    non_dm["_mp_salg"] = _build_range_mask(
        non_dm["_konto_num"], _SALG_RANGES + _GEVINST_TAP_RANGES
    )
    non_dm["_mp_lev_bank"] = _build_range_mask(
        non_dm["_konto_num"], _LEVERANDOR_RANGES + _BANK_RANGES
    )
    non_dm["_mp_dm"] = _build_range_mask(non_dm["_konto_num"], dm_ranges)

    # Per bilag: aggreger motpost-flagg + ta første motpost-konto for visning
    bilag_flags = non_dm.groupby("_bilag", sort=False).agg(
        has_avskr=("_mp_avskr", "any"),
        has_salg=("_mp_salg", "any"),
        has_lev_bank=("_mp_lev_bank", "any"),
        has_dm=("_mp_dm", "any"),
        first_konto=("_konto_num", "first"),
        first_navn=("Kontonavn", "first"),
    )

    # Join flagg til DM-transaksjoner
    dm_df = dm_df.join(bilag_flags, on="_bilag", how="left")

    # Fyll NaN for bilag uten motposter
    for col in ("has_avskr", "has_salg", "has_lev_bank", "has_dm"):
        dm_df[col] = dm_df[col].fillna(False)

    # Vektorisert klassifisering med prioritet
    dm_df["dm_kategori"] = "Ukjent"
    dm_df.loc[dm_df["has_dm"], "dm_kategori"] = "Omklassifisering"
    # Lev/bank: Tilgang eller Avgang basert på fortegn
    lev_bank_mask = dm_df["has_lev_bank"]
    dm_df.loc[lev_bank_mask & (dm_df["_belop"] > 0), "dm_kategori"] = "Tilgang"
    dm_df.loc[lev_bank_mask & (dm_df["_belop"] <= 0), "dm_kategori"] = "Avgang"
    dm_df.loc[dm_df["has_salg"], "dm_kategori"] = "Avgang"
    dm_df.loc[dm_df["has_avskr"], "dm_kategori"] = "Avskrivning"

    # Motpost for visning
    dm_df["_motpost_konto"] = dm_df["first_konto"].apply(
        lambda v: str(int(v)) if pd.notna(v) else ""
    )
    dm_df["_motpost_navn"] = dm_df["first_navn"].fillna("")

    # Rydd opp hjelpekolonner
    dm_df.drop(
        columns=[
            "has_avskr", "has_salg", "has_lev_bank", "has_dm",
            "first_konto", "first_navn",
        ],
        inplace=True,
        errors="ignore",
    )
    return dm_df


def build_dm_reconciliation(
    sb_df: pd.DataFrame,
    classified_df: pd.DataFrame,
    dm_ranges: list[tuple[int, int]],
    regnr_555_ub: float | None = None,
) -> dict[str, Any]:
    """Bygg avstemming for varige driftsmidler.

    Returnerer en dict med følgende felt:
      kostpris_ib, tilgang, avgang, kostpris_ub_beregnet, kostpris_ub_sb,
      kostpris_avvik, avskr_ib, avskr_aar, avskr_ub_beregnet, avskr_ub_sb,
      avskr_avvik, bokfort_verdi, regnr_555_ub, ukjente_tx, omklassifisering,
      tilgang_tx, avgang_tx, avskr_tx, kontoer (DataFrame).
    """
    result: dict[str, Any] = {
        "kostpris_ib": 0.0, "tilgang": 0.0, "avgang": 0.0,
        "kostpris_ub_beregnet": 0.0, "kostpris_ub_sb": 0.0, "kostpris_avvik": 0.0,
        "avskr_ib": 0.0, "avskr_aar": 0.0,
        "avskr_ub_beregnet": 0.0, "avskr_ub_sb": 0.0, "avskr_avvik": 0.0,
        "bokfort_verdi": 0.0, "regnr_555_ub": regnr_555_ub,
        "ukjente_tx": 0, "omklassifisering": 0.0,
        "tilgang_tx": 0, "avgang_tx": 0, "avskr_tx": 0,
        "kontoer": pd.DataFrame(),
    }

    dm_sb = _filter_sb(sb_df, dm_ranges)
    if dm_sb.empty:
        return result

    # Skille kostpris vs akk. avskrivning basert på UB-fortegn
    dm_sb["_ub"] = dm_sb["ub"].apply(safe_float)
    dm_sb["_ib"] = dm_sb["ib"].apply(safe_float)
    # Kostpriskonti: positiv UB (eller IB hvis UB=0)
    # Akk.avskr.konti: negativ UB
    dm_sb["_type"] = dm_sb.apply(
        lambda r: "Akk. avskr."
        if r["_ub"] < -0.01 or (abs(r["_ub"]) < 0.01 and r["_ib"] < -0.01)
        else "Kostpris",
        axis=1,
    )

    kostpris_sb = dm_sb[dm_sb["_type"] == "Kostpris"]
    avskr_sb = dm_sb[dm_sb["_type"] == "Akk. avskr."]

    result["kostpris_ib"] = kostpris_sb["_ib"].sum()
    result["kostpris_ub_sb"] = kostpris_sb["_ub"].sum()
    result["avskr_ib"] = avskr_sb["_ib"].sum()
    result["avskr_ub_sb"] = avskr_sb["_ub"].sum()

    # Summér klassifiserte transaksjoner
    if classified_df is not None and not classified_df.empty:
        for kat in ("Tilgang", "Avgang", "Avskrivning", "Omklassifisering", "Ukjent"):
            mask = classified_df["dm_kategori"] == kat
            s = classified_df.loc[mask, "_belop"].sum()
            cnt = int(mask.sum())
            if kat == "Tilgang":
                result["tilgang"] = s
                result["tilgang_tx"] = cnt
            elif kat == "Avgang":
                result["avgang"] = s
                result["avgang_tx"] = cnt
            elif kat == "Avskrivning":
                result["avskr_aar"] = s
                result["avskr_tx"] = cnt
            elif kat == "Omklassifisering":
                result["omklassifisering"] = s
            elif kat == "Ukjent":
                result["ukjente_tx"] = cnt

    result["kostpris_ub_beregnet"] = (
        result["kostpris_ib"] + result["tilgang"] + result["avgang"]
    )
    result["kostpris_avvik"] = result["kostpris_ub_beregnet"] - result["kostpris_ub_sb"]

    result["avskr_ub_beregnet"] = result["avskr_ib"] + result["avskr_aar"]
    result["avskr_avvik"] = result["avskr_ub_beregnet"] - result["avskr_ub_sb"]

    result["bokfort_verdi"] = result["kostpris_ub_sb"] + result["avskr_ub_sb"]

    # Konto-oversikt for tab
    dm_sb_out = dm_sb[["konto", "ib", "ub", "_type"]].copy()
    if "kontonavn" in dm_sb.columns:
        dm_sb_out.insert(1, "kontonavn", dm_sb["kontonavn"])
    dm_sb_out["bevegelse"] = (
        dm_sb_out["ub"].apply(safe_float) - dm_sb_out["ib"].apply(safe_float)
    )
    result["kontoer"] = dm_sb_out

    return result


# ---------------------------------------------------------------------------
# Private hjelpere
# ---------------------------------------------------------------------------

def _in_ranges(konto_num: float, ranges: list[tuple[int, int]]) -> bool:
    for fra, til in ranges:
        if fra <= konto_num <= til:
            return True
    return False


def _filter_sb(
    sb_df: pd.DataFrame, ranges: list[tuple[int, int]]
) -> pd.DataFrame:
    """Filtrer saldobalanse til kontoer innenfor gitte ranges."""
    if sb_df is None or sb_df.empty or "konto" not in sb_df.columns:
        return pd.DataFrame(columns=["konto", "kontonavn", "ib", "ub"])
    sb = sb_df.copy()
    sb["_knum"] = pd.to_numeric(sb["konto"], errors="coerce")
    mask = pd.Series(False, index=sb.index)
    for fra, til in ranges:
        mask |= (sb["_knum"] >= fra) & (sb["_knum"] <= til)
    return sb.loc[mask].drop(columns=["_knum"])


def _build_range_mask(
    series: pd.Series, ranges: list[tuple[int, int]]
) -> pd.Series:
    """Vektorisert sjekk om verdier er innenfor noen av rangene."""
    mask = pd.Series(False, index=series.index)
    for fra, til in ranges:
        mask |= (series >= fra) & (series <= til)
    return mask
