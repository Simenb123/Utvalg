# ab_analysis.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Set
import numpy as np
import pandas as pd

from models import Columns, ABAnalysisConfig  # bruker dine modeller  :contentReference[oaicite:3]{index=3}

# ---------------------- Normalisering / prepp ----------------------

def _norm_invoice(s: pd.Series, *, drop_non_alnum: bool, strip_zeros: bool) -> pd.Series:
    out = s.astype(str).str.strip().str.upper()
    if drop_non_alnum:
        out = out.str.replace(r"[^0-9A-Z]", "", regex=True)
    if strip_zeros:
        out = out.str.lstrip("0")
    return out

@dataclass
class _Prepared:
    df: pd.DataFrame
    cols: Columns
    tag: str  # "A" eller "B"

def _prep(df: pd.DataFrame, cols: Columns, tag: str, cfg: ABAnalysisConfig) -> _Prepared:
    """Lager standardiserte hjelpekolonner for matching."""
    c = cols
    out = df.copy().reset_index(drop=False).rename(columns={"index": f"{tag}_idx"})
    out[f"{tag}_amt"] = out[c.belop].astype(float).round(2)
    out[f"{tag}_amt_cents"] = (out[f"{tag}_amt"] * 100).round().astype("Int64")
    if getattr(c, "dato", "") and c.dato in out.columns:
        out[f"{tag}_date"] = pd.to_datetime(out[c.dato], errors="coerce", dayfirst=True)
    else:
        out[f"{tag}_date"] = pd.NaT
    if getattr(c, "part", "") and c.part in out.columns:
        out[f"{tag}_party"] = out[c.part].astype(str)
    else:
        out[f"{tag}_party"] = ""
    out[f"{tag}_doc_norm"] = (
        _norm_invoice(out[c.bilag].astype(str), drop_non_alnum=cfg.invoice_drop_non_alnum,
                      strip_zeros=cfg.invoice_strip_leading_zeros)
    )
    out[f"{tag}_konto"] = out[c.konto].astype("Int64")
    out[f"{tag}_bilag"] = out[c.bilag].astype(str)
    out[f"{tag}_tekst"] = out[c.tekst].astype(str) if getattr(c, "tekst", "") and c.tekst in out.columns else ""
    out[f"{tag}_navn"] = out[c.kontonavn].astype(str) if c.kontonavn in out.columns else ""
    return _Prepared(df=out, cols=c, tag=tag)

# ---------------------- Hjelpere for toleranser/unik match ----------------------

def _within_days(a: pd.Series, b: pd.Series, tol: int) -> pd.Series:
    if a.isna().all() or b.isna().all() or tol is None:
        return pd.Series([True]*len(a))
    d = (a - b).abs().dt.days
    return d <= int(tol)

def _apply_party(req_same: bool, a: pd.Series, b: pd.Series) -> pd.Series:
    if not req_same:
        return pd.Series([True]*len(a))
    return a.astype(str) == b.astype(str)

def _enforce_unique(df: pd.DataFrame, col_a: str, col_b: str,
                    score_cols: Tuple[str, ...]) -> pd.DataFrame:
    """Velg maks 1 B pr A og maks 1 A pr B; ranger på score_cols (stigende)."""
    if df.empty:
        return df
    # ranger
    df2 = df.copy()
    df2["__ord__"] = list(range(len(df2)))
    sort_cols = list(score_cols) + ["__ord__"]
    df2 = df2.sort_values(sort_cols, ascending=[True]*len(sort_cols))

    # én per A
    df2 = df2.drop_duplicates(subset=[col_a], keep="first")
    # én per B
    df2 = df2.sort_values(sort_cols, ascending=[True]*len(sort_cols))
    df2 = df2.drop_duplicates(subset=[col_b], keep="first")
    return df2

# ---------------------- Matcher ----------------------

def match_same_amount(A: _Prepared, B: _Prepared, cfg: ABAnalysisConfig) -> pd.DataFrame:
    """
    A ↔ B likt beløp (samme fortegn) innen ± amount_tolerance (kroner) og ± days_tolerance (dager).
    """
    if not cfg.same_amount:
        return pd.DataFrame()
    tol_cents = int(round(float(cfg.amount_tolerance or 0.0) * 100))
    res_rows = []
    # pre-signer
    A_df = A.df.assign(__signA=np.sign(A.df[f"{A.tag}_amt_cents"].astype("float")))
    B_df = B.df.assign(__signB=np.sign(B.df[f"{B.tag}_amt_cents"].astype("float")))
    for d in range(-tol_cents, tol_cents+1):
        A_df["__key"] = A_df[f"{A.tag}_amt_cents"]
        B_df["__key"] = B_df[f"{B.tag}_amt_cents"] + d
        m = A_df.merge(B_df, on="__key", how="inner", suffixes=("_A","_B"))
        if m.empty:
            continue
        # samme fortegn
        m = m[m["__signA"] == m["__signB"]]
        if m.empty:
            continue
        # part/tid
        ok_party = _apply_party(cfg.require_same_party, m[f"{A.tag}_party"], m[f"{B.tag}_party"])
        ok_days = _within_days(m[f"{A.tag}_date"], m[f"{B.tag}_date"], cfg.days_tolerance)
        m = m[ok_party & ok_days].copy()
        if m.empty:
            continue
        # score
        m["__delta_cents__"] = (m[f"{A.tag}_amt_cents"] - m[f"{B.tag}_amt_cents"]).abs()
        m["__days__"] = (m[f"{A.tag}_date"] - m[f"{B.tag}_date"]).abs().dt.days.fillna(0)
        res_rows.append(m)
    if not res_rows:
        return pd.DataFrame()
    allm = pd.concat(res_rows, ignore_index=True)
    if cfg.unique_match:
        allm = _enforce_unique(allm, f"{A.tag}_idx", f"{B.tag}_idx", ("__delta_cents__", "__days__"))
    return allm

def match_opposite_sign(A: _Prepared, B: _Prepared, cfg: ABAnalysisConfig) -> pd.DataFrame:
    """
    A ↔ B motsatt fortegn: A.amt ≈ −B.amt innen toleranser.
    """
    if not cfg.opposite_sign:
        return pd.DataFrame()
    tol_cents = int(round(float(cfg.amount_tolerance or 0.0) * 100))
    res_rows = []
    for d in range(-tol_cents, tol_cents+1):
        A.df["__key"] = A.df[f"{A.tag}_amt_cents"]
        B.df["__key"] = -B.df[f"{B.tag}_amt_cents"] + d
        m = A.df.merge(B.df, on="__key", how="inner", suffixes=("_A","_B"))
        if m.empty:
            continue
        ok_party = _apply_party(cfg.require_same_party, m[f"{A.tag}_party"], m[f"{B.tag}_party"])
        ok_days = _within_days(m[f"{A.tag}_date"], m[f"{B.tag}_date"], cfg.days_tolerance)
        m = m[ok_party & ok_days].copy()
        if m.empty:
            continue
        m["__delta_cents__"] = (m[f"{A.tag}_amt_cents"] + m[f"{B.tag}_amt_cents"]).abs()
        m["__days__"] = (m[f"{A.tag}_date"] - m[f"{B.tag}_date"]).abs().dt.days.fillna(0)
        res_rows.append(m)
    if not res_rows:
        return pd.DataFrame()
    allm = pd.concat(res_rows, ignore_index=True)
    if cfg.unique_match:
        allm = _enforce_unique(allm, f"{A.tag}_idx", f"{B.tag}_idx", ("__delta_cents__", "__days__"))
    return allm

def match_two_sum(A: _Prepared, B: _Prepared, cfg: ABAnalysisConfig) -> pd.DataFrame:
    """
    To B‑poster som summerer til én A‑post (eksakt øre).
    Bruker ±days_tolerance og (valgfritt) samme part.
    """
    if not cfg.two_sum:
        return pd.DataFrame()
    # Vi kjører exact cents (toleranse=0) for par-matching (robust og raskt).
    # Dager/part begrenser kandidatsettet.
    out_rows = []
    used_B: Set[Tuple[int,int]] = set()  # (B_idx1, B_idx2) reservert når unique_match
    # For ytelse: grupper etter party hvis det kreves; ellers etter måned (om dato finnes), ellers globalt
    if cfg.require_same_party and (A.df[f"{A.tag}_party"].astype(str).str.len() > 0).any():
        A_groups = A.df.groupby(f"{A.tag}_party")
    else:
        # fallback: måned hvis dato finnes, ellers én gruppe
        if A.df[f"{A.tag}_date"].notna().any():
            A_groups = A.df.groupby(A.df[f"{A.tag}_date"].dt.to_period("M"))
        else:
            A_groups = [("GLOBAL", A.df)]

    for gkey, a_sub in A_groups:
        # kandidat-B for gruppen:
        if cfg.require_same_party and isinstance(gkey, str):
            b_cand = B.df[B.df[f"{B.tag}_party"].astype(str) == gkey].copy()
        else:
            if isinstance(gkey, pd.Period):
                b_cand = B.df.copy()
                # grovt filter på ±2 måneder rundt A-perioden for å begrense søk
                # (i tillegg til dags-toleranse på par-nivå)
                pass
            else:
                b_cand = B.df.copy()

        if b_cand.empty:
            continue
        # For hver A: filtrer B på dags-toleranse ift A-dato (dersom dato finnes)
        for _, ar in a_sub.iterrows():
            a_amt = int(ar[f"{A.tag}_amt_cents"])
            a_sign = np.sign(a_amt)
            # begrens til samme fortegn
            bc = b_cand[np.sign(b_cand[f"{B.tag}_amt_cents"].astype("float")) == a_sign].copy()
            if ar[f"{A.tag}_date"] is not pd.NaT and pd.notna(ar[f"{A.tag}_date"]):
                okd = _within_days(pd.Series([ar[f"{A.tag}_date"]]*len(bc)), bc[f"{B.tag}_date"], cfg.days_tolerance)
                bc = bc[okd]
            if bc.empty:
                continue
            # Two-sum eksakt
            # Hash map: amt_cents -> list of B_idx
            bucket: Dict[int, List[int]] = {}
            for _, br in bc.iterrows():
                val = int(br[f"{B.tag}_amt_cents"])
                bucket.setdefault(val, []).append(int(br[f"{B.tag}_idx"]))

            found = False
            for _, br in bc.iterrows():
                v1 = int(br[f"{B.tag}_amt_cents"])
                need = a_amt - v1
                if need in bucket:
                    # Finn en partner som ikke er samme rad
                    for b2_idx in bucket[need]:
                        if b2_idx == int(br[f"{B.tag}_idx"]):
                            continue
                        pair = tuple(sorted([int(br[f"{B.tag}_idx"]), b2_idx]))
                        if cfg.unique_match and pair in used_B:
                            continue
                        # OK – bygg rad
                        row = {
                            f"{A.tag}_idx": ar[f"{A.tag}_idx"],
                            f"{B.tag}_idx_1": int(br[f"{B.tag}_idx"]),
                            f"{B.tag}_idx_2": int(b2_idx),
                            f"{A.tag}_amt_cents": a_amt,
                            f"{B.tag}_sum_cents": v1 + need,
                            "__delta_cents__": abs(a_amt - (v1 + need)),
                            f"{A.tag}_date": ar[f"{A.tag}_date"],
                        }
                        out_rows.append(row)
                        if cfg.unique_match:
                            used_B.add(pair)
                        found = True
                        break
                if found:
                    break

    if not out_rows:
        return pd.DataFrame()
    out = pd.DataFrame(out_rows).drop_duplicates(subset=[f"{A.tag}_idx", f"{B.tag}_idx_1", f"{B.tag}_idx_2"])
    return out

def match_invoice_equal(A: _Prepared, B: _Prepared, cfg: ABAnalysisConfig) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Likt faktura/dok.nr (normalisert). Returnerer:
      matches, beløpsavvik (|diff|>=min), datoavvik (> min_dager)
    """
    key = [f"{A.tag}_doc_norm", f"{B.tag}_doc_norm"]
    a = A.df[[f"{A.tag}_doc_norm", f"{A.tag}_idx", f"{A.tag}_amt_cents", f"{A.tag}_date", f"{A.tag}_party"]].copy()
    b = B.df[[f"{B.tag}_doc_norm", f"{B.tag}_idx", f"{B.tag}_amt_cents", f"{B.tag}_date", f"{B.tag}_party"]].copy()
    m = a.merge(b, left_on=f"{A.tag}_doc_norm", right_on=f"{B.tag}_doc_norm", how="inner")
    if cfg.require_same_party:
        m = m[m[f"{A.tag}_party"].astype(str) == m[f"{B.tag}_party"].astype(str)]
    if m.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    m["__amt_diff_cents__"] = (m[f"{A.tag}_amt_cents"] - m[f"{B.tag}_amt_cents"]).abs()
    m["__days__"] = (m[f"{A.tag}_date"] - m[f"{B.tag}_date"]).abs().dt.days
    # avvik
    dev_amt = m[m["__amt_diff_cents__"] >= int(round(cfg.key_amount_min_diff * 100))].copy() if cfg.key_amount_deviation else pd.DataFrame()
    dev_date = m[m["__days__"] > int(cfg.key_days_min_diff)].copy() if cfg.key_date_deviation else pd.DataFrame()
    # unik match om ønsket
    if cfg.unique_match:
        m = _enforce_unique(m, f"{A.tag}_idx", f"{B.tag}_idx", ("__amt_diff_cents__", "__days__"))
    return m, dev_amt, dev_date

def duplicate_invoice_per_party(df: pd.DataFrame, cols: Columns, cfg: ABAnalysisConfig) -> pd.DataFrame:
    """Dupliserte faktura/dok.nr innen samme part i ET datasett."""
    tag = "X"
    tmp = _prep(df, cols, tag, cfg).df
    keys = [f"{tag}_doc_norm"]
    if (getattr(cols, "part", "") and cols.part in df.columns):
        keys.append(f"{tag}_party")
    g = tmp.groupby(keys).size().reset_index(name="Antall")
    dkeys = g[g["Antall"] > 1][keys]
    if dkeys.empty:
        return pd.DataFrame()
    idx = tmp.merge(dkeys, on=keys, how="inner").index
    out = df.loc[idx].copy()
    return out

# ---------------------- Orkestrering ----------------------

@dataclass
class ABResult:
    same_amount: pd.DataFrame
    opposite_sign: pd.DataFrame
    two_sum: pd.DataFrame
    key_matches: pd.DataFrame
    key_dev_amount: pd.DataFrame
    key_dev_date: pd.DataFrame
    dup_invoice_A: pd.DataFrame
    dup_invoice_B: pd.DataFrame

def run_all(dfA: pd.DataFrame, cA: Columns,
            dfB: pd.DataFrame, cB: Columns,
            cfg: Optional[ABAnalysisConfig] = None) -> ABResult:
    cfg = cfg or ABAnalysisConfig()
    A = _prep(dfA, cA, "A", cfg)
    B = _prep(dfB, cB, "B", cfg)

    same = match_same_amount(A, B, cfg)
    oppo = match_opposite_sign(A, B, cfg)
    two = match_two_sum(A, B, cfg)
    key_m, key_amt, key_date = match_invoice_equal(A, B, cfg)
    dupA = duplicate_invoice_per_party(dfA, cA, cfg) if cfg.dup_invoice_per_party else pd.DataFrame()
    dupB = duplicate_invoice_per_party(dfB, cB, cfg) if cfg.dup_invoice_per_party else pd.DataFrame()

    return ABResult(
        same_amount=same,
        opposite_sign=oppo,
        two_sum=two,
        key_matches=key_m,
        key_dev_amount=key_amt,
        key_dev_date=key_date,
        dup_invoice_A=dupA,
        dup_invoice_B=dupB,
    )
