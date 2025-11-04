from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict
from models import Columns
from excel_export import export_temp_excel
import ab_analysis as ab
import dup_period_checks as dup

def _is_round_amount(x: float, bases=(1000, 500, 100), tol: float = 0.0) -> bool:
    ax = abs(float(x))
    for b in bases:
        r = ax % b
        if r <= tol or (b - r) <= tol:
            return True
    return False

def round_share_by_group(df: pd.DataFrame, cols: Columns, group: str = "Konto",
                         bases=(1000, 500, 100), tol: float = 0.0,
                         min_rows: int = 20) -> pd.DataFrame:
    c = cols
    d = df.copy()
    if group.lower().startswith("måned") and getattr(c, "dato", None) and c.dato in d.columns:
        d["__måned"] = pd.to_datetime(d[c.dato], errors="coerce").dt.to_period("M").astype(str)
        key = "__måned"; label = "Måned"
    elif group.lower().startswith("part") and getattr(c, "part", None) and c.part in d.columns:
        key = c.part; label = "Part"
    else:
        key = c.konto; label = "Konto"
    d["__is_round"] = d[c.belop].apply(lambda v: _is_round_amount(v, bases=bases, tol=tol))
    tab = d.groupby(key)["__is_round"].agg(antall="count", runde="sum").reset_index().rename(columns={key: label})
    tab["andel_runde"] = tab["runde"] / tab["antall"]
    tab = tab[tab["antall"] >= int(min_rows)].sort_values("andel_runde", ascending=False)
    return tab

def _mad_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x); mad = np.median(np.abs(x - med)) or 1.0
    return 0.6745 * (x - med) / mad

def outliers_by_group(df: pd.DataFrame, cols: Columns, method: str = "MAD", threshold: float = 3.5,
                      group_by: str = "Konto", min_group_size: int = 20, basis: str = "abs") -> pd.DataFrame:
    c = cols; d = df.copy()
    if basis == "abs": d["__val"] = d[c.belop].abs().astype(float)
    else: d["__val"] = d[c.belop].astype(float)

    if group_by.lower().startswith("part") and getattr(c, "part", None) and c.part in d.columns:
        key = c.part; label = "Part"
    elif group_by.lower().startswith("konto+") and getattr(c, "part", None) and c.part in d.columns:
        key = [c.konto, c.part]; label = "Konto+Part"
    else:
        key = c.konto; label = "Konto"

    outs = []
    for g, chunk in d.groupby(key):
        if len(chunk) < int(min_group_size): continue
        x = chunk["__val"].to_numpy()
        if method.upper() == "IQR":
            q1, q3 = np.percentile(x, [25, 75]); iqr = q3 - q1 or 1.0
            lo, hi = q1 - threshold*iqr, q3 + threshold*iqr
            mask = (x < lo) | (x > hi)
        else:
            z = _mad_z(x); mask = np.abs(z) >= threshold
        if mask.any():
            flagged = chunk.loc[mask].copy()
            if label == "Konto": flagged["__gruppe"] = flagged[c.konto].astype(str)
            elif label == "Part": flagged["__gruppe"] = flagged[c.part].astype(str)
            else: flagged["__gruppe"] = flagged[c.konto].astype(str) + " | " + flagged.get(c.part, "").astype(str)
            outs.append(flagged)
    if outs: return pd.concat(outs, axis=0, ignore_index=True)
    return pd.DataFrame(columns=list(df.columns) + ["__gruppe"])

def generate_analysis_workbook(df: pd.DataFrame, cols: Columns,
                               round_group="Konto", round_bases=(1000, 500, 100), round_tol=0.0, round_min_rows=20,
                               out_method="MAD", out_threshold=3.5, out_group="Konto", out_min_group=20, out_basis="abs",
                               period_from=None, period_to=None) -> str:
    sheets: Dict[str, pd.DataFrame] = {}
    # Runde beløp andeler
    try: sheets["Runde_beløp_andeler"] = round_share_by_group(df, cols, group=round_group, bases=round_bases, tol=round_tol, min_rows=round_min_rows)
    except Exception: pass
    # Outliers
    try: sheets["Outliers"] = outliers_by_group(df, cols, method=out_method, threshold=out_threshold, group_by=out_group, min_group_size=out_min_group, basis=out_basis)
    except Exception: pass
    # A/B-krysshint
    try:
        x = ab.same_amount(df, cols, ab.ABConfig());   sheets.update({"AB_Lik_beløp": x} if not x.empty else {})
        x = ab.opposite_sign(df, cols, ab.ABConfig()); sheets.update({"AB_Motsatt_fortegn": x} if not x.empty else {})
        x = ab.two_sum(df, cols, ab.ABConfig());       sheets.update({"AB_Two_sum": x} if not x.empty else {})
    except Exception: pass
    # Duplikater & periodeavvik (utvidet)
    try:
        x = dup.duplicates_doc_account(df, cols);             sheets.update({"DUP_Doknr+Konto": x} if not x.empty else {})
        x = dup.duplicates_doc_account_amount(df, cols);      sheets.update({"DUP_Doknr+Konto+Beløp": x} if not x.empty else {})
        x = dup.duplicates_identical_rows(df, cols);          sheets.update({"DUP_Identiske_rader": x} if not x.empty else {})
        x = dup.duplicates_amount_date_per_party(df, cols);   sheets.update({"DUP_Beløp+Dato_pr_Part": x} if not x.empty else {})
        x = dup.period_out_of_scope(df, cols, date_from=period_from, date_to=period_to); sheets.update({"Periode_avvik": x} if not x.empty else {})
        x = dup.due_date_before_docdate(df, cols);            sheets.update({"Periode_Forfall_før_Dato": x} if not x.empty else {})
        x = dup.date_outside_row_period(df, cols);            sheets.update({"Periode_Dato_utenfor_Radens_Perioder": x} if not x.empty else {})
    except Exception: pass

    if not sheets:
        sheets["Info"] = pd.DataFrame({"Melding": ["Ingen analyser ble produsert (mangler kanskje relevante kolonner)."]})
    return export_temp_excel(sheets, prefix="Analyser_")
