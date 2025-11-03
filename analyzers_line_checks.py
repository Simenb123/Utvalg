"""
analyzers_line_checks.py
------------------------
Enkelt-datasett analyser:
- Duplikat (dok.nr + konto)
- Runde beløp (enkeltlinjer)
- Dato utenfor periode
"""

from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd
from models import Columns


def _select_cols(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    cols = [x for x in [c.konto, c.kontonavn, c.bilag, c.belop, c.dato, c.tekst, c.part] if x and x in df.columns]
    return df[cols].copy()


def duplicates_doc_account(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    """Finn kombinasjoner (dok.nr, konto) med forekomster >= 2."""
    if c.bilag not in df.columns or c.konto not in df.columns:
        return pd.DataFrame(columns=["Bilag", "Konto", "Kontonavn", "Forekomster", "Sum"])
    grp = (
        df.groupby([c.bilag, c.konto], dropna=False)[c.belop]
          .agg(Forekomster="count", Sum="sum")
          .reset_index()
    )
    res = grp[grp["Forekomster"] >= 2].copy()
    if c.kontonavn in df.columns:
        names = df[[c.konto, c.kontonavn]].drop_duplicates()
        res = res.merge(names, left_on=c.konto, right_on=c.konto, how="left")
        res = res[[c.bilag, c.konto, c.kontonavn, "Forekomster", "Sum"]]
        res.columns = ["Bilag", "Konto", "Kontonavn", "Forekomster", "Sum"]
    else:
        res.columns = ["Bilag", "Konto", "Forekomster", "Sum"]
    return res.sort_values(["Forekomster", "Sum"], ascending=[False, False])


def round_amounts(df: pd.DataFrame, c: Columns, bases: Iterable[int], tol: float = 0.0) -> pd.DataFrame:
    """
    Flag rader der |beløp| ≈ n * base for minst én base.
    Returnerer kolonnene: Konto, Kontonavn, Bilag, Beløp, Base, Avvik.
    """
    if c.belop not in df.columns:
        return pd.DataFrame(columns=["Konto", "Kontonavn", "Bilag", "Beløp", "Base", "Avvik"])

    out_rows = []
    s = df[c.belop].astype(float).abs()
    for b in bases:
        if b <= 0:
            continue
        nearest = (np.round(s / b) * b).astype(float)
        delta = (s - nearest).abs()
        mask = delta <= float(tol)
        if mask.any():
            sub = _select_cols(df.loc[mask], c).copy()
            sub["Base"] = b
            sub["Avvik"] = delta.loc[mask].values
            sub.rename(columns={c.konto: "Konto", c.kontonavn: "Kontonavn", c.bilag: "Bilag", c.belop: "Beløp"}, inplace=True)
            out_rows.append(sub[["Konto", "Kontonavn", "Bilag", "Beløp", "Base", "Avvik"]])
    if not out_rows:
        return pd.DataFrame(columns=["Konto", "Kontonavn", "Bilag", "Beløp", "Base", "Avvik"])
    return pd.concat(out_rows, ignore_index=True).sort_values(["Base", "Avvik"])


def out_of_period(df: pd.DataFrame, c: Columns, date_from: str | None, date_to: str | None) -> pd.DataFrame:
    """Rader med dato utenfor [date_from, date_to]. Krever datokolonne i df."""
    if not c.dato or c.dato not in df.columns or (date_from is None and date_to is None):
        return pd.DataFrame(columns=["Konto", "Kontonavn", "Bilag", "Beløp", "Dato", "Notat"])

    d = df.copy()
    mask = pd.Series(False, index=d.index)
    if date_from is not None:
        mask |= d[c.dato] < pd.to_datetime(date_from)
    if date_to is not None:
        mask |= d[c.dato] > pd.to_datetime(date_to)

    out = _select_cols(d.loc[mask], c)
    out.rename(columns={c.konto: "Konto", c.kontonavn: "Kontonavn", c.bilag: "Bilag", c.belop: "Beløp", c.dato: "Dato"}, inplace=True)
    out["Notat"] = f"Utenfor periode [{date_from or '---'} → {date_to or '---'}]"
    return out
