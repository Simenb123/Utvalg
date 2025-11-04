from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from models import Columns

def duplicates_doc_account(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Duplikate kombinasjoner av (dok/bilag, konto)."""
    c = cols
    if any(col not in df.columns for col in [c.bilag, c.konto]):
        return pd.DataFrame(columns=[c.bilag, c.konto, "Antall"])
    g = df.groupby([c.bilag, c.konto]).size().reset_index(name="Antall")
    g = g[g["Antall"] > 1]
    if g.empty: return g
    sums = df.groupby([c.bilag, c.konto])[c.belop].sum().reset_index(name="Sum")
    out = g.merge(sums, on=[c.bilag, c.konto], how="left")
    return out.sort_values([c.bilag, c.konto])

def duplicates_doc_account_amount(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Duplikate (bilag, konto, beløp)."""
    c = cols
    if any(col not in df.columns for col in [c.bilag, c.konto, c.belop]):
        return pd.DataFrame(columns=[c.bilag, c.konto, c.belop, "Antall"])
    d = df.copy()
    d["__belop_r2"] = d[c.belop].astype(float).round(2)
    g = d.groupby([c.bilag, c.konto, "__belop_r2"]).size().reset_index(name="Antall")
    g = g[g["Antall"] > 1]
    if g.empty: return g
    g = g.rename(columns={"__belop_r2": "Beløp"})
    return g.sort_values([c.bilag, c.konto, "Beløp"])

def duplicates_identical_rows(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Helt identiske rader (på tvers av kjernefelter som finnes)."""
    c = cols
    core: List[str] = [c.konto, c.kontonavn, c.bilag, c.belop]
    opt = [c.dato, c.tekst, c.part]
    for o in opt:
        if o and o in df.columns: core.append(o)
    present = [col for col in core if col in df.columns]
    if not present: return pd.DataFrame()
    d = df.copy()
    for col in present:
        if col == c.belop:
            d[col] = d[col].astype(float).round(2)
        else:
            d[col] = d[col].astype(str).str.strip().str.upper()
    g = d.groupby(present).size().reset_index(name="Antall")
    g = g[g["Antall"] > 1]
    return g

def duplicates_amount_date_per_party(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Duplikate (part, beløp, dato)."""
    c = cols
    if getattr(c, "part", None) not in df.columns or getattr(c, "dato", None) not in df.columns:
        return pd.DataFrame(columns=[c.part or "Part", c.dato or "Dato", c.belop or "Beløp", "Antall"])
    d = df.copy()
    d["__belop_r2"] = d[c.belop].astype(float).round(2)
    d["__dato"] = pd.to_datetime(d[c.dato], errors="coerce").dt.date
    g = d.groupby([c.part, "__dato", "__belop_r2"]).size().reset_index(name="Antall")
    g = g[g["Antall"] > 1]
    if g.empty: return g
    g = g.rename(columns={"__dato":"Dato", "__belop_r2":"Beløp"})
    return g.sort_values([c.part, "Dato", "Beløp"])

def period_out_of_scope(df: pd.DataFrame, cols: Columns, date_from=None, date_to=None) -> pd.DataFrame:
    c = cols
    if (date_from is None and date_to is None) or getattr(c, "dato", None) not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["Periode_avvik"])
    d = df.copy()
    d["__dato"] = pd.to_datetime(d[c.dato], errors="coerce")
    mask = pd.Series(False, index=d.index)
    if date_from is not None:
        mask |= (d["__dato"] < pd.to_datetime(date_from))
    if date_to is not None:
        mask |= (d["__dato"] > pd.to_datetime(date_to))
    out = d[mask].copy()
    if out.empty: return pd.DataFrame(columns=list(df.columns) + ["Periode_avvik"])
    out["Periode_avvik"] = out["__dato"].dt.strftime("%Y-%m-%d")
    out = out.drop(columns=["__dato"])
    return out

def due_date_before_docdate(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Forfallsdato < Dato (krever begge)."""
    c = cols
    if not c.due or c.due not in df.columns or not c.dato or c.dato not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["Avvik"])
    d = df.copy()
    d["__due"] = pd.to_datetime(d[c.due], errors="coerce")
    d["__dato"] = pd.to_datetime(d[c.dato], errors="coerce")
    out = d[(~d["__due"].isna()) & (~d["__dato"].isna()) & (d["__due"] < d["__dato"])].copy()
    if out.empty: return pd.DataFrame(columns=list(df.columns) + ["Avvik"])
    out["Avvik"] = "Forfall før dato"
    return out.drop(columns=["__due","__dato"])

def date_outside_row_period(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    """Dato utenfor radens egne periodegrenser (periodestart/periodeslutt)."""
    c = cols
    if not c.periodestart or c.periodestart not in df.columns or not c.periodeslutt or c.periodeslutt not in df.columns or not c.dato or c.dato not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["Periode_avvik"])
    d = df.copy()
    d["__dato"] = pd.to_datetime(d[c.dato], errors="coerce")
    d["__ps"] = pd.to_datetime(d[c.periodestart], errors="coerce")
    d["__pe"] = pd.to_datetime(d[c.periodeslutt], errors="coerce")
    out = d[(~d["__dato"].isna()) & ((~d["__ps"].isna()) & (d["__dato"] < d["__ps"]) | (~d["__pe"].isna()) & (d["__dato"] > d["__pe"]))].copy()
    if out.empty: return pd.DataFrame(columns=list(df.columns) + ["Periode_avvik"])
    out["Periode_avvik"] = "Dato utenfor radens perioder"
    return out.drop(columns=["__dato","__ps","__pe"])
