"""
LEGACY-FIL (analyselogikk)

Dette var en tidligere versjon av analyselogikken.
Ny logikk skal ligge i analysis_pkg.py.

Filen beholdes midlertidig som referanse/backup.
"""



# analysis_pack.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import numpy as np
import pandas as pd

from models import Columns, AnalysisConfig  # bruker dine modeller  :contentReference[oaicite:4]{index=4}

# ----------------------------- Hjelpere ---------------------------------

def _apply_basic_filter(df: pd.DataFrame, c: Columns,
                        direction: str = "Alle",
                        min_amount: Optional[float] = None,
                        max_amount: Optional[float] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df
    d = (direction or "Alle").lower()
    if d.startswith("debet"):
        out = out[out[c.belop] > 0]
    elif d.startswith("kredit"):
        out = out[out[c.belop] < 0]
    if min_amount is not None:
        out = out[out[c.belop] >= float(min_amount)]
    if max_amount is not None:
        out = out[out[c.belop] <= float(max_amount)]
    return out

def _month_col(df: pd.DataFrame, date_col: Optional[str]) -> pd.Series:
    if not date_col or date_col not in df.columns:
        return pd.Series([""] * len(df))
    s = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    return s.dt.to_period("M").astype(str).fillna("")

# --------------------------- Runde beløp --------------------------------

def round_flags(df: pd.DataFrame, c: Columns,
                bases: Tuple[int, ...] = (1000, 500, 100),
                tolerance: float = 0.0,
                basis: str = "abs") -> pd.DataFrame:
    """
    Flagger transaksjoner som er (nær) hele multipler av basisverdier.
    basis: 'abs' => bruk |beløp|, 'signed' => bruk signert beløp.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    v = df[c.belop].abs() if (basis or "abs").lower().startswith("abs") else df[c.belop]
    v = v.astype(float)

    bases = tuple(int(b) for b in bases if int(b) > 0)
    if not bases:
        return pd.DataFrame()

    best_base = np.full(len(v), np.nan)
    best_dist = np.full(len(v), np.inf)

    for b in bases:
        rem = np.mod(v, b)
        dist = np.minimum(rem, np.maximum(b - rem, 0))
        upd = dist < best_dist
        best_dist = np.where(upd, dist, best_dist)
        best_base = np.where(upd, b, best_base)

    ok = best_dist <= float(tolerance)
    out = df.loc[ok].copy()
    if out.empty:
        return out

    out["__RoundBase__"] = best_base[ok]
    out["__RoundDist__"] = best_dist[ok]
    # Standardiser ut‑kolonner
    cols_out = [c.konto, c.kontonavn, c.bilag]
    if getattr(c, "dato", "") and c.dato in out.columns:
        cols_out.append(c.dato)
    if getattr(c, "tekst", "") and c.tekst in out.columns:
        cols_out.append(c.tekst)
    if getattr(c, "part", "") and c.part in out.columns:
        cols_out.append(c.part)
    cols_out += [c.belop, "__RoundBase__", "__RoundDist__"]
    return out[cols_out]

def round_share_by_group(df: pd.DataFrame, c: Columns,
                         flags_df: pd.DataFrame,
                         group_by: str = "Konto",
                         min_rows: int = 20,
                         threshold: float = 0.30) -> pd.DataFrame:
    """
    Andel runde beløp per valgt gruppe: 'Konto' | 'Part' | 'Måned'.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    valid = df.copy()
    valid["__is_round__"] = False
    if flags_df is not None and not flags_df.empty:
        # Bygg en nøkkel på rad-nivå: (bilag, konto, beløp, ev. dato)
        key_cols = [c.bilag, c.konto, c.belop]
        if getattr(c, "dato", "") and c.dato in df.columns:
            key_cols.append(c.dato)
        keys_all = valid[key_cols].astype(str).agg("|".join, axis=1)
        keys_round = flags_df[key_cols].astype(str).agg("|".join, axis=1)
        valid["__is_round__"] = keys_all.isin(set(keys_round.tolist()))

    if group_by.lower().startswith("konto"):
        grp_key = df[c.konto].astype("Int64").astype(str)
        grp_label = df[c.kontonavn].astype(str)
        valid["__group__"] = grp_key + " – " + grp_label
    elif group_by.lower().startswith("part"):
        if not getattr(c, "part", "") or c.part not in df.columns:
            return pd.DataFrame()
        valid["__group__"] = df[c.part].astype(str)
    else:  # Måned
        m = _month_col(df, getattr(c, "dato", None))
        if (m == "").all():
            return pd.DataFrame()
        valid["__group__"] = m

    tab = (valid.groupby("__group__", dropna=False)
                 ["__is_round__"]
                 .agg(Total="count", Runde="sum")
                 .reset_index())
    if tab.empty:
        return tab
    tab["Andel_runde"] = tab["Runde"] / tab["Total"]
    tab = tab[tab["Total"] >= int(min_rows)].sort_values("Andel_runde", ascending=False)
    tab["Flagg"] = tab["Andel_runde"] >= float(threshold)
    tab = tab.rename(columns={"__group__": "Gruppe"})
    return tab

# ----------------------------- Duplikater -------------------------------

def duplicates_doc_account(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    """Duplikate dok.nr innen samme konto."""
    if df is None or df.empty:
        return pd.DataFrame()
    g = df.groupby([c.konto, c.bilag]).size().reset_index(name="Antall")
    dupe_keys = g[g["Antall"] > 1][[c.konto, c.bilag]]
    if dupe_keys.empty:
        return pd.DataFrame()
    key = df[[c.konto, c.bilag]].merge(dupe_keys, on=[c.konto, c.bilag], how="inner")
    out = df.loc[key.index].copy()
    out = out.sort_values([c.konto, c.bilag])
    # Standardiser ut‑kolonner
    cols_out = [c.konto, c.kontonavn, c.bilag]
    if getattr(c, "dato", "") and c.dato in out.columns:
        cols_out.append(c.dato)
    if getattr(c, "tekst", "") and c.tekst in out.columns:
        cols_out.append(c.tekst)
    if getattr(c, "part", "") and c.part in out.columns:
        cols_out.append(c.part)
    cols_out += [c.belop]
    return out[cols_out]

def duplicates_amount_date_party(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    """
    Potensiell dobbeltføring: duplikate (Part, Dato, Beløp).
    Faller tilbake til tilgjengelige nøkler hvis Part/Dato mangler.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # Normaliser beløp til 2 desimaler for stabil gruppering
    amt = df[c.belop].round(2)

    keys: List[str] = []
    if getattr(c, "part", "") and c.part in df.columns:
        keys.append(c.part)
    if getattr(c, "dato", "") and c.dato in df.columns:
        keys.append(c.dato)
    keys.append("__AMT__")
    base = df.copy()
    base["__AMT__"] = amt

    g = base.groupby(keys).size().reset_index(name="Antall")
    dupe_keys = g[g["Antall"] > 1][keys]
    if dupe_keys.empty:
        return pd.DataFrame()
    idx = base.merge(dupe_keys, on=keys, how="inner").index
    out = df.loc[idx].copy()
    # Standardiser kolonner
    cols_out = [c.konto, c.kontonavn, c.bilag]
    if getattr(c, "dato", "") and c.dato in out.columns:
        cols_out.append(c.dato)
    if getattr(c, "tekst", "") and c.tekst in out.columns:
        cols_out.append(c.tekst)
    if getattr(c, "part", "") and c.part in out.columns:
        cols_out.append(c.part)
    cols_out += [c.belop]
    return out[cols_out]

# ------------------------------- Outliers -------------------------------

def outliers(df: pd.DataFrame, c: Columns, *,
             method: str = "MAD",
             threshold: float = 3.5,
             group_by: str = "Konto",
             min_group_size: int = 20,
             basis: str = "abs") -> pd.DataFrame:
    """
    Outliers via robust statistikk.
    method: 'MAD' (|x-med|/MAD) eller 'IQR' (x > Q3 + k*IQR).
    group_by: 'Global' | 'Konto' | 'Part' | 'Konto+Part' | 'Måned'
    basis: 'abs' eller 'signed'
    """
    if df is None or df.empty:
        return pd.DataFrame()

    s = df[c.belop].abs() if basis.lower().startswith("abs") else df[c.belop]
    s = s.astype(float)

    # Lag gruppe‑nøkkel
    if group_by.lower().startswith("global"):
        grp = pd.Series(["GLOBAL"] * len(df))
        add_cols: List[str] = []
    elif group_by.lower().startswith("konto+part"):
        if not getattr(c, "part", "") or c.part not in df.columns:
            return pd.DataFrame()
        grp = df[c.konto].astype("Int64").astype(str) + "|" + df[c.part].astype(str)
        add_cols = [c.part]
    elif group_by.lower().startswith("konto"):
        grp = df[c.konto].astype("Int64").astype(str)
        add_cols = []
    elif group_by.lower().startswith("part"):
        if not getattr(c, "part", "") or c.part not in df.columns:
            return pd.DataFrame()
        grp = df[c.part].astype(str)
        add_cols = [c.part]
    else:  # Måned
        m = _month_col(df, getattr(c, "dato", None))
        if (m == "").all():
            return pd.DataFrame()
        grp = m
        add_cols = []

    data = df.copy()
    data["__group__"] = grp
    data["__val__"] = s

    out_rows = []

    for gname, sub in data.groupby("__group__", dropna=False):
        if len(sub) < int(min_group_size):
            continue
        vals = sub["__val__"].astype(float).values

        if method.upper().startswith("MAD"):
            med = np.median(vals)
            mad = np.median(np.abs(vals - med))
            if mad == 0:
                continue
            z = 0.6745 * np.abs(vals - med) / mad
            mask = z > float(threshold)
            sel = sub.loc[mask].copy()
            sel["__Center__"] = med
            sel["__Scale__"] = mad
            sel["__Score__"] = z[mask]
            sel["__Method__"] = "MAD"
        else:
            q1 = np.quantile(vals, 0.25)
            q3 = np.quantile(vals, 0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            k = float(threshold)
            upper = q3 + k * iqr
            if basis.lower().startswith("abs"):
                mask = vals > upper  # ensidig når abs brukes
            else:
                lower = q1 - k * iqr
                mask = (vals < lower) | (vals > upper)
            sel = sub.loc[mask].copy()
            sel["__Center__"] = (q1 + q3) / 2.0
            sel["__Scale__"] = iqr
            sel["__Score__"] = (sel["__val__"] - q3) / iqr
            sel["__Method__"] = "IQR"

        if not sel.empty:
            out_rows.append(sel)

    if not out_rows:
        return pd.DataFrame()

    res = pd.concat(out_rows, ignore_index=True)
    # Gjør om til transaksjons‑visning
    base_cols = [c.konto, c.kontonavn, c.bilag]
    if getattr(c, "dato", "") and c.dato in df.columns:
        base_cols.append(c.dato)
    if getattr(c, "tekst", "") and c.tekst in df.columns:
        base_cols.append(c.tekst)
    if getattr(c, "part", "") and c.part in df.columns and c.part in add_cols:
        base_cols.append(c.part)
    base_cols += [c.belop]
    out_tx = df.loc[res.index, base_cols].copy()
    out_tx["__Group__"] = res["__group__"].values
    out_tx["__Method__"] = res["__Method__"].values
    out_tx["__Center__"] = res["__Center__"].values
    out_tx["__Scale__"] = res["__Scale__"].values
    out_tx["__Score__"] = res["__Score__"].values
    return out_tx

# ----------------------------- Periodeavvik -----------------------------

def out_of_period(df: pd.DataFrame, c: Columns,
                  date_from: Optional[pd.Timestamp],
                  date_to: Optional[pd.Timestamp]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if not getattr(c, "dato", "") or c.dato not in df.columns:
        return pd.DataFrame()
    s = pd.to_datetime(df[c.dato], errors="coerce", dayfirst=True)
    mask = pd.Series([False] * len(df))
    if date_from is not None:
        mask |= s < date_from
    if date_to is not None:
        mask |= s > date_to
    out = df.loc[mask].copy()
    if out.empty:
        return out
    cols_out = [c.konto, c.kontonavn, c.bilag, c.dato]
    if getattr(c, "tekst", "") and c.tekst in out.columns:
        cols_out.append(c.tekst)
    if getattr(c, "part", "") and c.part in out.columns:
        cols_out.append(c.part)
    cols_out += [c.belop]
    return out[cols_out]

# ----------------------------- Orkestrering -----------------------------

@dataclass
class AnalysisResult:
    round_tx: pd.DataFrame
    round_share: pd.DataFrame
    dup_doc_account: pd.DataFrame
    dup_amt_date_part: pd.DataFrame
    outliers: pd.DataFrame
    out_of_period: pd.DataFrame

def run_all(df: pd.DataFrame, c: Columns,
            cfg: AnalysisConfig,
            *, direction: str = "Alle",
            min_amount: Optional[float] = None,
            max_amount: Optional[float] = None,
            date_from: Optional[pd.Timestamp] = None,
            date_to: Optional[pd.Timestamp] = None) -> AnalysisResult:
    base = _apply_basic_filter(df, c, direction, min_amount, max_amount)

    # Runde beløp
    round_tx = pd.DataFrame()
    round_share = pd.DataFrame()
    if cfg.include_round_amounts:
        round_tx = round_flags(base, c, cfg.round_bases, cfg.round_tolerance, basis="abs")
        if cfg.include_round_share_by_group:
            round_share = round_share_by_group(base, c, round_tx, cfg.round_share_group_by,
                                              cfg.round_share_min_rows, cfg.round_share_threshold)

    # Duplikater
    dup_doc = pd.DataFrame()
    dup_adp = pd.DataFrame()
    if cfg.include_duplicates_doc_account:
        dup_doc = duplicates_doc_account(base, c)
        dup_adp = duplicates_amount_date_party(base, c)

    # Outliers
    out_tx = pd.DataFrame()
    if cfg.include_outliers:
        out_tx = outliers(base, c, method=cfg.outlier_method,
                          threshold=cfg.outlier_threshold,
                          group_by=cfg.outlier_group_by,
                          min_group_size=cfg.outlier_min_group_size,
                          basis=cfg.outlier_basis)

    # Periode
    ooper = pd.DataFrame()
    if cfg.include_out_of_period and (date_from is not None or date_to is not None):
        ooper = out_of_period(base, c, date_from, date_to)

    return AnalysisResult(
        round_tx=round_tx,
        round_share=round_share,
        dup_doc_account=dup_doc,
        dup_amt_date_part=dup_adp,
        outliers=out_tx,
        out_of_period=ooper,
    )
