from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass
class CheckResult:
    """
    Resultat fra en overstyrings-kontroll.

    - summary_df: én rad per bilag (aggregert)
    - lines_df: linjer som hører til bilagene (ofte hele bilaget, evt. subset)
    - meta: ekstra info (parametre, kolonne-mapping, osv.)
    """

    check_id: str
    title: str
    summary_df: pd.DataFrame
    lines_df: pd.DataFrame
    meta: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return self.summary_df.empty


def resolve_core_columns(
    df: pd.DataFrame,
    cols: Any | None = None,
    strict: bool = False,
) -> tuple[dict[str, str], list[str]]:
    """
    Finn sentrale kolonner i et transaksjons-datasett.

    Returnerer:
        (colmap, missing)

    colmap nøkler:
        bilag, belop, konto, dato, tekst, dokumentnr, debet, kredit

    - Hvis belop ikke finnes men debet + kredit finnes, settes belop til '__computed_amount__'
      (belop = debet - kredit).
    - Hvis strict=True og påkrevde kolonner mangler, kastes ValueError.

    cols kan være en eksisterende "Columns"-dataklasse fra repoet (har felter som bilag/belop/konto/dato/tekst).
    """

    def _get_attr(name: str) -> str:
        if cols is None:
            return ""
        val = getattr(cols, name, "")  # Columns fra repoet har typisk disse feltene
        return str(val) if val else ""

    def _first_existing(candidates: Sequence[str]) -> str:
        for c in candidates:
            if c and c in df.columns:
                return c
        return ""

    # Bilag
    bilag = _first_existing(
        [
            _get_attr("bilag"),
            "Bilag",
            "Voucher",
            "VoucherNo",
            "Voucher No",
            "Document",
            "DocumentNo",
            "Document No",
            "Bilagsnr",
        ]
    )

    # Konto
    konto = _first_existing(
        [
            _get_attr("konto"),
            "Konto",
            "Account",
            "AccountNo",
            "Account No",
            "GLAccount",
            "GL Account",
        ]
    )

    # Beløp / Amount
    belop = _first_existing(
        [
            _get_attr("belop"),
            "Beløp",
            "Beloep",
            "Belop",
            "Amount",
            "Value",
            "Netto",
            "Sum",
        ]
    )

    # Debet/Kredit (fallback hvis beløp ikke finnes)
    debet = _first_existing(["Debet", "Debit", "DebitAmount", "Debit Amount", "Dr"])
    kredit = _first_existing(["Kredit", "Credit", "CreditAmount", "Credit Amount", "Cr"])

    # Dato
    dato = _first_existing(
        [
            _get_attr("dato"),
            "Dato",
            "Date",
            "PostingDate",
            "Posting Date",
            "VoucherDate",
            "Voucher Date",
        ]
    )

    # Tekst
    tekst = _first_existing(
        [
            _get_attr("tekst"),
            "Tekst",
            "Text",
            "Description",
            "Beskrivelse",
            "Narrative",
        ]
    )

    # Dokumentnr
    dokumentnr = _first_existing(
        [
            "Dokumentnr",
            "DokumentNr",
            "Doknr",
            "DokNr",
            "DocumentNo",
            "Document No",
            "InvoiceNo",
            "Invoice No",
            "Fakturanr",
            "FakturaNr",
        ]
    )

    # Dersom vi ikke har beløp, men har debet+kredit: bruk beregnet beløp
    if not belop and debet and kredit:
        belop = "__computed_amount__"

    colmap: dict[str, str] = {
        "bilag": bilag,
        "konto": konto,
        "belop": belop,
        "dato": dato,
        "tekst": tekst,
        "dokumentnr": dokumentnr,
        "debet": debet,
        "kredit": kredit,
    }

    missing: list[str] = []
    for req in ("bilag", "konto", "belop"):
        if not colmap.get(req):
            missing.append(req)

    if strict and missing:
        raise ValueError(f"Mangler påkrevde kolonner: {missing}")

    return colmap, missing


def _normalize_key(series: pd.Series) -> pd.Series:
    """
    Normaliserer "nøkler" (bilag/konto) til string:

    - Stripper whitespace
    - Gjør tom/None/nan til NA
    - Konverterer heltallige tall til 'Int64' string (f.eks 1.0 -> '1')
    """
    s = series.astype("string").str.strip()

    # Normaliser noen vanlige "tom"-verdier
    s = s.replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})

    num = pd.to_numeric(s, errors="coerce")
    mask_int = num.notna() & np.isclose(num % 1, 0)
    if mask_int.any():
        s = s.copy()
        s.loc[mask_int] = num.loc[mask_int].astype("Int64").astype("string")
    return s


def _to_float_series(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return s.astype("float64")


def _amount_from_cols(df: pd.DataFrame, colmap: dict[str, str]) -> pd.Series:
    amt_col = colmap.get("belop", "")
    if amt_col == "__computed_amount__":
        deb_col = colmap.get("debet", "")
        cre_col = colmap.get("kredit", "")
        deb = _to_float_series(df[deb_col]) if deb_col and deb_col in df.columns else pd.Series(0.0, index=df.index)
        cre = _to_float_series(df[cre_col]) if cre_col and cre_col in df.columns else pd.Series(0.0, index=df.index)
        return deb - cre

    if not amt_col or amt_col not in df.columns:
        return pd.Series(0.0, index=df.index)

    return _to_float_series(df[amt_col])


def _safe_to_datetime(series: pd.Series) -> pd.Series:
    """
    Robust dato-parsing med enkel heuristikk for å unngå unødvendige warnings:

    - Hvis vi ser "." eller "/" i sampleverdier antar vi ofte norsk format (dd.mm.yyyy / dd/mm/yyyy) => dayfirst=True
    - Ellers antar vi ISO / entydige formater => dayfirst=False
    """
    s = series.astype("string")
    sample = s.dropna().astype(str).head(50).tolist()
    dayfirst = any(("/" in v) or ("." in v) for v in sample)
    return pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)


def build_voucher_summary(df: pd.DataFrame, cols: Any | None = None) -> pd.DataFrame:
    """
    Bygger et bilags-sammendrag som kan brukes av flere kontroller.

    Returnerer DataFrame med kolonner:
      Bilag, AntallLinjer, SumDebet, SumKredit, SumDebetAbs, SumKreditAbs,
      SumAbs, Netto, NettoAbs, Max line abs, DatoMin, DatoMax,
      KontoNunique, TekstNunique, DokumentnrNunique

    NB: Funksjonen er "best effort" – mangler i kolonner gir tomt resultat eller NA-felt,
    men skal ikke krasje.
    """
    colmap, _missing = resolve_core_columns(df, cols=cols, strict=False)

    bilag_col = colmap.get("bilag", "")
    if not bilag_col or bilag_col not in df.columns:
        # Uten bilag kan vi ikke aggregere.
        return pd.DataFrame(
            columns=[
                "Bilag",
                "AntallLinjer",
                "SumDebet",
                "SumKredit",
                "SumDebetAbs",
                "SumKreditAbs",
                "SumAbs",
                "Netto",
                "NettoAbs",
                "Max line abs",
                "DatoMin",
                "DatoMax",
                "KontoNunique",
                "TekstNunique",
                "DokumentnrNunique",
            ]
        )

    bilag_key = _normalize_key(df[bilag_col])

    # Minimal "tmp" for aggregasjoner
    tmp = pd.DataFrame(index=df.index)
    tmp["__bilag__"] = bilag_key

    amt = _amount_from_cols(df, colmap)
    tmp["__amount__"] = amt
    tmp["__amount_abs__"] = amt.abs()

    # Debet/Kredit: bruk eksplisitte kolonner hvis de finnes, ellers derivert fra fortegn
    deb_col = colmap.get("debet", "")
    cre_col = colmap.get("kredit", "")

    if deb_col and deb_col in df.columns:
        deb = _to_float_series(df[deb_col])
    else:
        deb = amt.where(amt > 0, 0.0)

    if cre_col and cre_col in df.columns:
        cre = _to_float_series(df[cre_col])
        # noen datasett har kredit som positiv – dersom det ser slik ut, konverter til negativ
        if (cre >= 0).all() and (amt < 0).any():
            # heuristikk: la oss ikke snu hvis alt ser "konsistent" ut; her velger vi å ikke gjøre noe.
            pass
    else:
        cre = amt.where(amt < 0, 0.0)

    tmp["__debet__"] = deb
    tmp["__kredit__"] = cre

    # Konto/Tekst/Dok (for nunique)
    konto_col = colmap.get("konto", "")
    if konto_col and konto_col in df.columns:
        tmp["__konto__"] = _normalize_key(df[konto_col])
    else:
        tmp["__konto__"] = pd.NA

    tekst_col = colmap.get("tekst", "")
    if tekst_col and tekst_col in df.columns:
        tmp["__tekst__"] = df[tekst_col].astype("string").str.strip().str.lower().fillna("")
    else:
        tmp["__tekst__"] = ""

    doc_col = colmap.get("dokumentnr", "")
    if doc_col and doc_col in df.columns:
        tmp["__doc__"] = df[doc_col].astype("string").str.strip().fillna("")
    else:
        tmp["__doc__"] = ""

    dato_col = colmap.get("dato", "")
    if dato_col and dato_col in df.columns:
        tmp["__date__"] = _safe_to_datetime(df[dato_col])
    else:
        tmp["__date__"] = pd.NaT

    # Gruppér
    g = tmp.groupby("__bilag__", dropna=True, sort=False)

    agg = g.agg(
        AntallLinjer=("__amount__", "size"),
        SumDebet=("__debet__", "sum"),
        SumKredit=("__kredit__", "sum"),
        SumAbs=("__amount_abs__", "sum"),
        Netto=("__amount__", "sum"),
        MaxLineAbs=("__amount_abs__", "max"),
        DatoMin=("__date__", "min"),
        DatoMax=("__date__", "max"),
        KontoNunique=("__konto__", "nunique"),
        TekstNunique=("__tekst__", "nunique"),
        DokumentnrNunique=("__doc__", "nunique"),
    ).reset_index(names="Bilag")

    # Normaliser Bilag til string
    agg["Bilag"] = agg["Bilag"].astype("string")

    # Deriverte felt
    agg["SumDebetAbs"] = agg["SumDebet"].abs()
    agg["SumKreditAbs"] = agg["SumKredit"].abs()
    agg["NettoAbs"] = agg["Netto"].abs()
    agg["Max line abs"] = agg["MaxLineAbs"]

    # Kolonne-rekkefølge (for lesbarhet + stabilitet)
    out = agg[
        [
            "Bilag",
            "AntallLinjer",
            "SumDebet",
            "SumKredit",
            "SumDebetAbs",
            "SumKreditAbs",
            "SumAbs",
            "Netto",
            "NettoAbs",
            "Max line abs",
            "DatoMin",
            "DatoMax",
            "KontoNunique",
            "TekstNunique",
            "DokumentnrNunique",
        ]
    ].copy()

    out = out.sort_values(["Max line abs", "SumAbs"], ascending=[False, False], kind="mergesort").reset_index(drop=True)
    return out


def filter_accounts(df: pd.DataFrame, konto_col: str, include: Iterable[str] | None, exclude: Iterable[str] | None) -> pd.DataFrame:
    """
    Enkel hjelpefunksjon for å filtrere df på konto.

    include: bare disse kontoene (hvis satt)
    exclude: fjern disse kontoene (hvis satt)
    """
    if not konto_col or konto_col not in df.columns:
        return df

    out = df
    if include:
        include_set = {str(x).strip() for x in include if str(x).strip()}
        if include_set:
            out = out[out[konto_col].astype("string").str.strip().isin(include_set)]

    if exclude:
        exclude_set = {str(x).strip() for x in exclude if str(x).strip()}
        if exclude_set:
            out = out[~out[konto_col].astype("string").str.strip().isin(exclude_set)]

    return out
