"""MVA-kontroller (K1–K6).

Ren datamodul uten GUI-avhengigheter. Utvider de eksisterende K1–K3 fra
``mva_avstemming.build_mva_kontroller`` med tre nye kontroller:

- K4: Korreksjoner/stornoer i MVA-kontoer (negative MVA-beløp).
- K5: Forsinkelsesrente på MVA-krav (fra Skatteetaten kontoutskrift).
- K6: Konsistens mellom konto-klassifisering og MVA-kode.

Hver kontroll returnerer et ``KontrollResult`` med treff, beløp og status.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

import mva_codes
from mva_avstemming import build_mva_kontroller, SkatteetatenData

log = logging.getLogger(__name__)


@dataclass
class KontrollResult:
    id: str
    label: str
    status: str  # "OK" | "AVVIK" | "MERK" | "MANGLER"
    treff: int = 0
    beløp: float = 0.0
    kommentar: str = ""
    detaljer: Optional[pd.DataFrame] = None


@dataclass
class AlleKontrollerResult:
    results: list[KontrollResult] = field(default_factory=list)


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str:
    lower_map = {str(c).lower(): str(c) for c in df.columns}
    for cand in candidates:
        actual = lower_map.get(cand.lower())
        if actual:
            return actual
    return ""


def run_k4_korreksjoner(df: pd.DataFrame) -> KontrollResult:
    """K4: Transaksjoner med MVA-beløp som går motsatt vei av kode-retning.

    Eksempel: utgående MVA-kode med positivt MVA-beløp (typisk storno).
    """
    empty = KontrollResult(id="K4", label="Korreksjoner/stornoer i MVA", status="OK")
    if df is None or df.empty:
        return empty

    mva_code_col = _find_col(df, ["MVA-kode", "mva-kode", "Mva-kode"])
    mva_amount_col = _find_col(df, ["MVA-beløp", "mva-beløp", "Mva-beløp"])
    if not mva_code_col or not mva_amount_col:
        return empty

    work = df[[c for c in df.columns]].copy()
    work["_code"] = work[mva_code_col].astype(str).str.strip()
    work["_mva_amt"] = pd.to_numeric(work[mva_amount_col], errors="coerce").fillna(0.0)

    def _retning(code: str) -> str:
        info = mva_codes.get_code_info(code)
        return str(info.get("direction", "") if info else "")

    work["_dir"] = work["_code"].apply(_retning)

    # Utgående MVA er normalt kredit → MVA-beløp < 0. Positivt = korreksjon.
    mask_utg = (work["_dir"] == "utgående") & (work["_mva_amt"] > 0)
    # Inngående MVA er normalt debet → MVA-beløp > 0. Negativt = korreksjon.
    mask_inn = (work["_dir"] == "inngående") & (work["_mva_amt"] < 0)
    mask = mask_utg | mask_inn

    hits = work[mask]
    if hits.empty:
        empty.kommentar = "Ingen korreksjoner/stornoer i MVA-beløpene."
        return empty

    drop_cols = [c for c in ("_code", "_mva_amt", "_dir") if c in hits.columns]
    detaljer = hits.drop(columns=drop_cols, errors="ignore")

    return KontrollResult(
        id="K4",
        label="Korreksjoner/stornoer i MVA",
        status="MERK",
        treff=len(hits),
        beløp=float(hits["_mva_amt"].sum()),
        kommentar=(
            f"{len(hits)} transaksjoner med MVA-beløp motsatt retning av kode."
        ),
        detaljer=detaljer,
    )


def run_k5_forsinkelsesrente(skatteetaten: Optional[SkatteetatenData]) -> KontrollResult:
    """K5: Påløpt forsinkelsesrente på MVA-krav (fra Skatteetaten)."""
    empty = KontrollResult(
        id="K5",
        label="Forsinkelsesrente på MVA-krav",
        status="MANGLER",
        kommentar="Importer Skatteetaten kontoutskrift for å aktivere kontrollen.",
    )
    if skatteetaten is None:
        return empty
    krav = skatteetaten.raw_krav
    if krav is None or krav.empty:
        return empty

    rente_col = _find_col(krav, ["Påløpte renter", "Paalopte renter", "Renter"])
    kravgruppe_col = _find_col(krav, ["Kravgruppe"])
    if not rente_col or not kravgruppe_col:
        return KontrollResult(
            id="K5",
            label="Forsinkelsesrente på MVA-krav",
            status="MANGLER",
            kommentar="Fant ikke rente-/kravgruppe-kolonner i Krav-arket.",
        )

    mva_rows = krav[krav[kravgruppe_col].astype(str).str.strip() == "Merverdiavgift"]
    if mva_rows.empty:
        return KontrollResult(
            id="K5",
            label="Forsinkelsesrente på MVA-krav",
            status="OK",
            kommentar="Ingen MVA-krav i Skatteetaten-dataene.",
        )

    renter = pd.to_numeric(mva_rows[rente_col], errors="coerce").fillna(0.0)
    sum_renter = float(renter.abs().sum())
    if sum_renter < 1.0:
        return KontrollResult(
            id="K5",
            label="Forsinkelsesrente på MVA-krav",
            status="OK",
            kommentar="Ingen forsinkelsesrente påløpt.",
        )

    hits_mask = renter.abs() >= 1.0
    detaljer = mva_rows[hits_mask].copy() if hits_mask.any() else None

    return KontrollResult(
        id="K5",
        label="Forsinkelsesrente på MVA-krav",
        status="MERK",
        treff=int(hits_mask.sum()),
        beløp=sum_renter,
        kommentar=(
            f"Forsinkelsesrente på {int(hits_mask.sum())} MVA-krav "
            f"(sum {sum_renter:.0f} kr)."
        ),
        detaljer=detaljer,
    )


def run_k6_klassifisering_vs_kode(
    df: pd.DataFrame,
    gruppe_mapping: dict[str, str],
) -> KontrollResult:
    """K6: Konto klassifisert "Inngående MVA" men bilag har utgående kode (eller omvendt)."""
    empty = KontrollResult(
        id="K6",
        label="Klassifisering vs MVA-kode",
        status="OK",
        kommentar="Ingen konflikter mellom klassifisering og MVA-kode.",
    )
    if df is None or df.empty or not gruppe_mapping:
        empty.status = "MANGLER" if not gruppe_mapping else "OK"
        empty.kommentar = (
            "Ingen konto-klassifisering funnet — kontrollen er ikke aktiv."
            if not gruppe_mapping else empty.kommentar
        )
        return empty

    konto_col = _find_col(df, ["Konto", "konto"])
    mva_code_col = _find_col(df, ["MVA-kode", "mva-kode", "Mva-kode"])
    if not konto_col or not mva_code_col:
        return empty

    # Kun kontoer i klassifiserings-gruppe som inneholder "mva"
    mva_kontoer = {
        k: v for k, v in gruppe_mapping.items() if "mva" in str(v).lower()
    }
    if not mva_kontoer:
        return empty

    def _forventet_retning(gruppe: str) -> str:
        g = gruppe.lower()
        if "utgående" in g or "utg" in g:
            return "utgående"
        if "inngående" in g or "inn" in g:
            return "inngående"
        return ""

    work = df.copy()
    work["_konto"] = work[konto_col].astype(str).str.strip()
    work["_code"] = work[mva_code_col].astype(str).str.strip()

    def _code_retning(code: str) -> str:
        info = mva_codes.get_code_info(code)
        return str(info.get("direction", "") if info else "")

    work["_code_dir"] = work["_code"].apply(_code_retning)
    work["_klassifisering"] = work["_konto"].map(mva_kontoer).fillna("")
    work["_forventet_dir"] = work["_klassifisering"].apply(_forventet_retning)

    mask = (
        (work["_forventet_dir"] != "")
        & (work["_code_dir"] != "")
        & (work["_forventet_dir"] != work["_code_dir"])
    )
    hits = work[mask]
    if hits.empty:
        return empty

    drop_cols = [
        c for c in ("_konto", "_code", "_code_dir", "_klassifisering", "_forventet_dir")
        if c in hits.columns
    ]
    detaljer = hits.drop(columns=drop_cols, errors="ignore")

    return KontrollResult(
        id="K6",
        label="Klassifisering vs MVA-kode",
        status="AVVIK",
        treff=len(hits),
        beløp=0.0,
        kommentar=(
            f"{len(hits)} transaksjoner der MVA-kode og kontoklassifisering "
            "peker i motsatt retning."
        ),
        detaljer=detaljer,
    )


def run_all_controls(
    df: pd.DataFrame,
    *,
    skatteetaten: Optional[SkatteetatenData] = None,
    gruppe_mapping: Optional[dict[str, str]] = None,
) -> AlleKontrollerResult:
    """Kjør K1–K6 og returner samlet resultat."""
    out = AlleKontrollerResult()

    legacy = build_mva_kontroller(df)
    legacy_extras: dict[str, tuple[int, Optional[pd.DataFrame]]] = {
        "K1": (
            int(len(legacy.salg_vs_grunnlag) - 1) if not legacy.salg_vs_grunnlag.empty else 0,
            legacy.salg_vs_grunnlag if not legacy.salg_vs_grunnlag.empty else None,
        ),
        "K2": (
            int(len(legacy.salg_uten_mva)),
            legacy.salg_uten_mva if not legacy.salg_uten_mva.empty else None,
        ),
        "K3": (
            int(len(legacy.andre_med_utg_mva)),
            legacy.andre_med_utg_mva if not legacy.andre_med_utg_mva.empty else None,
        ),
    }
    for s in legacy.summary:
        kid = s["Kontroll"].split(":")[0].strip()
        treff, detaljer = legacy_extras.get(kid, (0, None))
        out.results.append(KontrollResult(
            id=kid,
            label=s["Kontroll"],
            status=s["Status"],
            treff=treff,
            beløp=float(s.get("Differanse", 0.0) or 0.0),
            kommentar=str(s.get("Kommentar", "")),
            detaljer=detaljer,
        ))

    out.results.append(run_k4_korreksjoner(df))
    out.results.append(run_k5_forsinkelsesrente(skatteetaten))
    out.results.append(run_k6_klassifisering_vs_kode(
        df, gruppe_mapping or {},
    ))

    return out
