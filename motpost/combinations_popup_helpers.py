from __future__ import annotations

"""Hjelpefunksjoner for kombinasjonspopup (UI).

Bevisst plassert i egen modul for å holde `combinations_popup.py` mer
håndterlig.

Disse funksjonene er UI-nære, men ikke Tk-interaktive.
"""

import pandas as pd

from formatting import fmt_amount


def truncate_text(text: str, max_len: int = 80) -> str:
    """Trunkerer tekst for visning i Treeview.

    Brukes for kommentarfelt slik at lange tekster ikke gjør tabellen treg/uhåndterlig.
    """
    s = "" if text is None else str(text)
    s = s.strip()
    if max_len <= 0:
        return s
    if len(s) <= max_len:
        return s
    if max_len <= 3:
        return s[:max_len]
    return s[: max_len - 1] + "…"


def format_combo_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Formatterer DF for visning i Treeview: tall -> formatert tekst."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()

    if "Sum valgte kontoer" in out.columns:
        out["Sum valgte kontoer"] = out["Sum valgte kontoer"].map(fmt_amount)

    if "% andel bilag" in out.columns:

        def _fmt_pct(x: object) -> str:
            if x is None:
                return ""
            try:
                if str(x) == "":
                    return ""
            except Exception:
                return ""
            try:
                return f"{float(x):.1f}%"
            except Exception:
                return ""

        out["% andel bilag"] = out["% andel bilag"].map(_fmt_pct)

    if "Outlier" in out.columns:
        out["Outlier"] = out["Outlier"].fillna("")

    return out


def build_bilag_rows(df_combo: pd.DataFrame, df_sel: pd.DataFrame, df_mot: pd.DataFrame) -> pd.DataFrame:
    """Bygger en per-bilag-tabell for valgt kombinasjon (pandas)."""
    # Selected sum per bilag (already direction filtered)
    sel_by_bilag = df_sel.groupby("Bilag_str")["Beløp_num"].sum()

    # Mot sum per bilag (net, all directions)
    mot_by_bilag = df_mot.groupby("Bilag_str")["Beløp_num"].sum()

    # Meta
    has_date = "Dato" in df_combo.columns
    has_text = "Tekst" in df_combo.columns
    date_by_bilag = df_combo.groupby("Bilag_str")["Dato"].first() if has_date else None
    text_by_bilag = df_combo.groupby("Bilag_str")["Tekst"].first() if has_text else None
    konto_count = df_combo.groupby("Bilag_str")["Konto_str"].nunique()

    idx = sorted(df_combo["Bilag_str"].dropna().unique().tolist())
    df_rows = pd.DataFrame(index=idx)
    df_rows["Bilag"] = df_rows.index
    df_rows["Dato"] = date_by_bilag.reindex(idx) if date_by_bilag is not None else ""
    df_rows["Tekst"] = text_by_bilag.reindex(idx) if text_by_bilag is not None else ""
    df_rows["Beløp_valgt"] = sel_by_bilag.reindex(idx).fillna(0.0)
    df_rows["Motbeløp"] = mot_by_bilag.reindex(idx).fillna(0.0)
    df_rows["Kontoer"] = konto_count.reindex(idx).fillna(0).astype(int)

    # Default order: largest absolute selected amount first
    df_rows["_abs"] = df_rows["Beløp_valgt"].abs()
    df_rows = df_rows.sort_values(["_abs", "Bilag"], ascending=[False, True])
    df_rows = df_rows.drop(columns=["_abs"])
    return df_rows
