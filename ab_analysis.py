from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from models import Columns

@dataclass
class ABConfig:
    days_tolerance: int = 3
    amount_tolerance: float = 0.0
    require_same_party: bool = False
    invoice_drop_non_alnum: bool = True
    invoice_strip_leading_zeros: bool = True
    unique_match: bool = True
    max_pairs_per_bucket: int = 50000
    max_rows_two_sum_bucket: int = 2000

def _norm_amt(x: float, tol: float) -> float:
    v = float(x)
    return round(v, 2)

def _within_days(d1: Optional[pd.Timestamp], d2: Optional[pd.Timestamp], maxd: int) -> bool:
    if d1 is None or d2 is None or pd.isna(d1) or pd.isna(d2):
        return True
    return abs((pd.to_datetime(d1) - pd.to_datetime(d2)).days) <= int(maxd)

def _bucket_by(df: pd.DataFrame, cols: Columns, require_same_party: bool):
    c = cols
    if require_same_party and getattr(c, "part", None) and c.part in df.columns:
        return {k: chunk for k, chunk in df.groupby(df[c.part].fillna("").astype(str))}
    else:
        return {("ALL",): df}

def _pair_unique(pairs: pd.DataFrame, unique: bool) -> pd.DataFrame:
    if not unique:
        return pairs
    usedA = set(); usedB = set(); rows = []
    for _, r in pairs.sort_values("days_diff").iterrows():
        a, b = int(r["row_A"]), int(r["row_B"])
        if a in usedA or b in usedB: continue
        usedA.add(a); usedB.add(b); rows.append(r)
    return pd.DataFrame(rows, columns=pairs.columns) if rows else pairs.iloc[0:0]

def same_amount(df: pd.DataFrame, cols: Columns, cfg: ABConfig) -> pd.DataFrame:
    c = cols
    out_rows = []
    for _bk, chunk in _bucket_by(df, c, cfg.require_same_party).items():
        g = chunk.copy()
        g["__amt"] = g[c.belop].apply(lambda v: _norm_amt(v, cfg.amount_tolerance))
        g = g.sort_values("__amt")
        for amt, grp in g.groupby("__amt"):
            if len(grp) < 2: 
                continue
            ix = grp.index.to_list()
            n = len(ix); count = 0
            for i in range(n):
                for j in range(i+1, n):
                    r1 = grp.loc[ix[i]]; r2 = grp.loc[ix[j]]
                    if not _within_days(r1.get(getattr(c,"dato",""), None), r2.get(getattr(c,"dato",""), None), cfg.days_tolerance):
                        continue
                    out_rows.append(dict(
                        row_A=int(ix[i]), row_B=int(ix[j]),
                        amount=float(amt), same_sign=bool(np.sign(r1[c.belop]) == np.sign(r2[c.belop])),
                        days_diff=(abs((pd.to_datetime(r1.get(getattr(c,"dato",""), None)) - pd.to_datetime(r2.get(getattr(c,"dato",""), None))).days)
                                   if getattr(c,"dato","") in grp.columns else np.nan),
                        bilag_A=str(r1[c.bilag]), bilag_B=str(r2[c.bilag]),
                        konto_A=str(r1[c.konto]), konto_B=str(r2[c.konto]),
                        party_A=str(r1.get(getattr(c,"part",""), "")), party_B=str(r2.get(getattr(c,"part",""), "")),
                        tekst_A=str(r1.get(getattr(c,"tekst",""), ""))[:120], tekst_B=str(r2.get(getattr(c,"tekst",""), ""))[:120],
                        type="Lik beløp"
                    ))
                    count += 1
                    if count >= cfg.max_pairs_per_bucket: break
                if count >= cfg.max_pairs_per_bucket: break
    pairs = pd.DataFrame(out_rows)
    if not pairs.empty:
        pairs = _pair_unique(pairs, cfg.unique_match)
    return pairs

def opposite_sign(df: pd.DataFrame, cols: Columns, cfg: ABConfig) -> pd.DataFrame:
    c = cols
    out_rows = []
    for _bk, chunk in _bucket_by(df, c, cfg.require_same_party).items():
        g = chunk.copy()
        g["__abs"] = g[c.belop].abs().round(2)
        pos = g[g[c.belop] > 0]; neg = g[g[c.belop] < 0]
        if pos.empty or neg.empty: 
            continue
        dict_neg = {}
        for idx, r in neg.iterrows():
            dict_neg.setdefault(float(r["__abs"]), []).append((idx, r))
        count = 0
        for idxp, rp in pos.iterrows():
            amt = float(rp["__abs"])
            cand = dict_neg.get(amt, [])
            for idxn, rn in cand:
                if not _within_days(rp.get(getattr(c,"dato",""), None), rn.get(getattr(c,"dato",""), None), cfg.days_tolerance):
                    continue
                out_rows.append(dict(
                    row_A=int(idxp), row_B=int(idxn),
                    amount=float(amt), same_sign=False,
                    days_diff=(abs((pd.to_datetime(rp.get(getattr(c,"dato",""), None)) - pd.to_datetime(rn.get(getattr(c,"dato",""), None))).days)
                               if getattr(c,"dato","") in g.columns else np.nan),
                    bilag_A=str(rp[c.bilag]), bilag_B=str(rn[c.bilag]),
                    konto_A=str(rp[c.konto]), konto_B=str(rn[c.konto]),
                    party_A=str(rp.get(getattr(c,"part",""), "")), party_B=str(rn.get(getattr(c,"part",""), "")),
                    tekst_A=str(rp.get(getattr(c,"tekst",""), ""))[:120], tekst_B=str(rn.get(getattr(c,"tekst",""), ""))[:120],
                    type="Motsatt fortegn"
                ))
                count += 1
                if count >= cfg.max_pairs_per_bucket: break
            if count >= cfg.max_pairs_per_bucket: break
    pairs = pd.DataFrame(out_rows)
    if not pairs.empty:
        pairs = _pair_unique(pairs, cfg.unique_match)
    return pairs

def two_sum(df: pd.DataFrame, cols: Columns, cfg: ABConfig) -> pd.DataFrame:
    c = cols
    out_rows = []
    for _bk, chunk in _bucket_by(df, c, cfg.require_same_party).items():
        g = chunk.copy()
        g["__abs"] = g[c.belop].abs().round(2)
        pos = g[g[c.belop] > 0].copy(); neg = g[g[c.belop] < 0].copy()
        if pos.empty or neg.empty:
            continue
        if len(neg) > cfg.max_rows_two_sum_bucket:
            neg = neg.nlargest(cfg.max_rows_two_sum_bucket, "__abs")
        neg_by_amt = {}
        for idx, r in neg.iterrows():
            neg_by_amt.setdefault(float(r["__abs"]), []).append((idx, r))
        count = 0
        for ia, ra in pos.iterrows():
            amt = float(ra["__abs"])
            tried = set()
            for a1 in list(neg_by_amt.keys()):
                a2 = round(amt - a1, 2)
                if (a1, a2) in tried or (a2, a1) in tried:
                    continue
                tried.add((a1,a2))
                list1 = neg_by_amt.get(a1, []); list2 = neg_by_amt.get(a2, [])
                for idx1, r1 in list1:
                    for idx2, r2 in list2:
                        if idx1 == idx2: continue
                        if not _within_days(ra.get(getattr(c,"dato",""), None), r1.get(getattr(c,"dato",""), None), cfg.days_tolerance):
                            continue
                        if not _within_days(ra.get(getattr(c,"dato",""), None), r2.get(getattr(c,"dato",""), None), cfg.days_tolerance):
                            continue
                        out_rows.append(dict(
                            row_A=int(ia), row_B1=int(idx1), row_B2=int(idx2),
                            amount=float(amt), days_diff=np.nan,
                            bilag_A=str(ra[c.bilag]), bilag_B1=str(r1[c.bilag]), bilag_B2=str(r2[c.bilag]),
                            konto_A=str(ra[c.konto]), konto_B1=str(r1[c.konto]), konto_B2=str(r2[c.konto]),
                            party_A=str(ra.get(getattr(c,"part",""), "")), party_B1=str(r1.get(getattr(c,"part",""), "")), party_B2=str(r2.get(getattr(c,"part",""), "")),
                            tekst_A=str(ra.get(getattr(c,"tekst",""), ""))[:120], tekst_B1=str(r1.get(getattr(c,"tekst",""), ""))[:120], tekst_B2=str(r2.get(getattr(c,"tekst",""), ""))[:120],
                            type="Two-sum (to motposter)"
                        ))
                        count += 1
                        if count >= cfg.max_pairs_per_bucket: break
                    if count >= cfg.max_pairs_per_bucket: break
                if count >= cfg.max_pairs_per_bucket: break
            if count >= cfg.max_pairs_per_bucket: break
    return pd.DataFrame(out_rows)
