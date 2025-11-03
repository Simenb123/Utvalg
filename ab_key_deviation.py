"""
ab_key_deviation.py
-------------------
Nøkler basert på (normalisert) faktura/dok.nr. Brukes både for
"likt fakturanr" og for avviksrapporter (beløp/dato) og for
"duplikate faktura per part".
"""

from __future__ import annotations
import re
import numpy as np
import pandas as pd
from models import Columns


def normalize_invoice_series(s: pd.Series,
                             drop_non_alnum: bool = True,
                             strip_leading_zeros: bool = True) -> pd.Series:
    """Normaliser faktura/dok.nr (fjerner whitespace/ikke-alfanumerisk, upper, ledernuller)."""
    s = s.fillna("").astype(str).str.strip()
    s = s.str.replace(r"[^0-9A-Za-z]", "", regex=True) if drop_non_alnum else s.str.replace(r"\s+", "", regex=True)
    s = s.str.upper()
    if strip_leading_zeros:
        s = s.map(lambda z: re.sub(r"^0+", "", z) if z.isdigit() else z)
    return s


def _prep(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["Part"] = df[c.part] if (c.part and c.part in df.columns) else ""
    out["Bilag"] = df[c.bilag] if (c.bilag in df.columns) else ""
    out["Belop"] = df[c.belop].astype(float)
    out["Dato"] = df[c.dato] if (c.dato and c.dato in df.columns) else pd.NaT
    try:
        out["Dato"] = pd.to_datetime(out["Dato"], errors="coerce")
    except Exception:
        out["Dato"] = pd.NaT
    return out


def match_invoice_equal(dfA: pd.DataFrame, cA: Columns,
                        dfB: pd.DataFrame, cB: Columns,
                        days_tol: int = 3, require_same_party: bool = False,
                        drop_non_alnum: bool = True, strip_leading_zeros: bool = True,
                        unique: bool = False) -> pd.DataFrame:
    """
    A ↔ B likt fakturanr (normalisert). Valgfritt: ± dager og samme Part.
    unique=True gir 1-til-1 på beste kandidat (laveste |beløpsavvik| og dager).
    """
    if cA.bilag not in dfA.columns or cB.bilag not in dfB.columns:
        return pd.DataFrame(columns=["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Dager_diff","Lik_faktura"])

    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["Bilag_norm"] = normalize_invoice_series(A["Bilag"], drop_non_alnum, strip_leading_zeros)
    B["Bilag_norm"] = normalize_invoice_series(B["Bilag"], drop_non_alnum, strip_leading_zeros)

    merged = A.merge(B, how="inner", left_on="Bilag_norm", right_on="Bilag_norm", suffixes=("_A","_B"))
    if require_same_party:
        merged = merged[(merged["Part_A"].astype(str) == merged["Part_B"].astype(str))]

    if days_tol is not None:
        mask = pd.notna(merged["Dato_A"]) & pd.notna(merged["Dato_B"])
        merged.loc[mask, "Dager_diff"] = (merged.loc[mask, "Dato_B"] - merged.loc[mask, "Dato_A"]).abs().dt.days
        merged.loc[~mask, "Dager_diff"] = np.nan
        merged = merged[(merged["Dager_diff"] <= int(days_tol)) | merged["Dager_diff"].isna()]
    else:
        merged["Dager_diff"] = np.nan

    out = merged.rename(columns={
        "Part_A": "A_Part", "Bilag_A": "A_Bilag", "Dato_A": "A_Dato", "Belop_A": "A_Belop",
        "Part_B": "B_Part", "Bilag_B": "B_Bilag", "Dato_B": "B_Dato", "Belop_B": "B_Belop"
    })[["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Dager_diff"]]
    out["Lik_faktura"] = True

    if unique and not out.empty:
        out["Beløpsavvik"] = (out["B_Belop"] - out["A_Belop"]).abs().astype(float)
        # enkel greedy: behold én beste B pr A og én A pr B
        used_a, used_b, picked = set(), set(), []
        for _, row in out.sort_values(["Beløpsavvik", "Dager_diff"]).iterrows():
            a = (row["A_Part"], row["A_Bilag"], row["A_Dato"], row["A_Belop"])
            b = (row["B_Part"], row["B_Bilag"], row["B_Dato"], row["B_Belop"])
            if a in used_a or b in used_b:
                continue
            used_a.add(a); used_b.add(b); picked.append(row)
        out = pd.DataFrame(picked)[["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Dager_diff","Lik_faktura"]]
    return out


def duplicates_invoice_per_party(dfA: pd.DataFrame, cA: Columns,
                                 dfB: pd.DataFrame, cB: Columns,
                                 drop_non_alnum: bool = True, strip_leading_zeros: bool = True) -> pd.DataFrame:
    """Tell forekomster av normalisert faktura pr. Part i A og/eller B; vis duplikater og kryssforekomster."""
    def _tab(df: pd.DataFrame, c: Columns, label: str) -> pd.DataFrame:
        if c.bilag not in df.columns:
            return pd.DataFrame(columns=["Part","Bilag_norm",f"Antall_{label}"])
        part = df[c.part] if (c.part and c.part in df.columns) else ""
        bil = normalize_invoice_series(df[c.bilag], drop_non_alnum, strip_leading_zeros)
        g = pd.DataFrame({"Part": part, "Bilag_norm": bil})
        tab = g.groupby(["Part","Bilag_norm"]).size().reset_index(name=f"Antall_{label}")
        return tab

    tA = _tab(dfA, cA, "A")
    tB = _tab(dfB, cB, "B")
    merged = tA.merge(tB, how="outer", on=["Part","Bilag_norm"]).fillna(0)
    merged["Antall_A"] = merged["Antall_A"].astype(int)
    merged["Antall_B"] = merged["Antall_B"].astype(int)
    out = merged[(merged["Antall_A"] >= 2) | (merged["Antall_B"] >= 2) | ((merged["Antall_A"] >= 1) & (merged["Antall_B"] >= 1))]
    return out.sort_values(["Part","Bilag_norm"])


def key_amount_deviation(dfA: pd.DataFrame, cA: Columns,
                         dfB: pd.DataFrame, cB: Columns, *,
                         require_same_party: bool = False,
                         drop_non_alnum: bool = True,
                         strip_leading_zeros: bool = True,
                         min_abs_diff: float = 1.0) -> pd.DataFrame:
    """Match på fakturanøkkel; rapportér rader der |B−A| ≥ min_abs_diff."""
    if cA.bilag not in dfA.columns or cB.bilag not in dfB.columns:
        return pd.DataFrame(columns=["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Beløpsavvik"])

    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["Bilag_norm"] = normalize_invoice_series(A["Bilag"], drop_non_alnum, strip_leading_zeros)
    B["Bilag_norm"] = normalize_invoice_series(B["Bilag"], drop_non_alnum, strip_leading_zeros)

    merged = A.merge(B, how="inner", left_on="Bilag_norm", right_on="Bilag_norm", suffixes=("_A","_B"))
    if require_same_party:
        merged = merged[(merged["Part_A"].astype(str) == merged["Part_B"].astype(str))]

    merged["Beløpsavvik"] = (merged["Belop_B"] - merged["Belop_A"]).astype(float)
    out = merged[merged["Beløpsavvik"].abs() >= float(min_abs_diff)].copy()
    out = out.rename(columns={
        "Part_A":"A_Part","Bilag_A":"A_Bilag","Dato_A":"A_Dato","Belop_A":"A_Belop",
        "Part_B":"B_Part","Bilag_B":"B_Bilag","Dato_B":"B_Dato","Belop_B":"B_Belop"
    })[["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Beløpsavvik"]]
    return out.sort_values("Beløpsavvik", key=lambda s: s.abs(), ascending=False)


def key_date_deviation(dfA: pd.DataFrame, cA: Columns,
                       dfB: pd.DataFrame, cB: Columns, *,
                       require_same_party: bool = False,
                       drop_non_alnum: bool = True,
                       strip_leading_zeros: bool = True,
                       min_days_diff: int = 7) -> pd.DataFrame:
    """Match på fakturanøkkel; rapportér rader der datoavvik > min_days_diff."""
    if cA.bilag not in dfA.columns or cB.bilag not in dfB.columns:
        return pd.DataFrame(columns=["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Dager_avvik"])

    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["Bilag_norm"] = normalize_invoice_series(A["Bilag"], drop_non_alnum, strip_leading_zeros)
    B["Bilag_norm"] = normalize_invoice_series(B["Bilag"], drop_non_alnum, strip_leading_zeros)

    merged = A.merge(B, how="inner", left_on="Bilag_norm", right_on="Bilag_norm", suffixes=("_A","_B"))
    if require_same_party:
        merged = merged[(merged["Part_A"].astype(str) == merged["Part_B"].astype(str))]

    mask = pd.notna(merged["Dato_A"]) & pd.notna(merged["Dato_B"])
    merged = merged[mask].copy()
    merged["Dager_avvik"] = (merged["Dato_B"] - merged["Dato_A"]).abs().dt.days.astype("Int64")

    out = merged[merged["Dager_avvik"] > int(min_days_diff)].copy()
    out = out.rename(columns={
        "Part_A":"A_Part","Bilag_A":"A_Bilag","Dato_A":"A_Dato","Belop_A":"A_Belop",
        "Part_B":"B_Part","Bilag_B":"B_Bilag","Dato_B":"B_Dato","Belop_B":"B_Belop"
    })[["A_Part","A_Bilag","A_Dato","A_Belop","B_Part","B_Bilag","B_Dato","B_Belop","Dager_avvik"]]
    return out.sort_values("Dager_avvik", ascending=False)
