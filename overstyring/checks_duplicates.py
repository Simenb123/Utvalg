from __future__ import annotations

from typing import Any

import pandas as pd

from .core import CheckResult, build_voucher_summary, resolve_core_columns, _amount_from_cols, _normalize_key


def duplicate_lines_vouchers(
    df: pd.DataFrame,
    cols: Any | None = None,
    min_count: int = 2,
    include_only_same_sign: bool = True,
    check_id: str = "duplicate_lines",
    title: str = "Dupliserte linjer",
) -> CheckResult:
    """
    Finn bilag med dupliserte linjer (samme konto + beløp).

    - min_count: hvor mange like linjer som må finnes for å flagge
    - include_only_same_sign: hvis True, sammenligner vi på signert beløp
      (dvs +100 og -100 regnes ikke som "like").
    """
    colmap, missing = resolve_core_columns(df, cols=cols, strict=False)
    bilag_col = colmap.get("bilag", "")
    konto_col = colmap.get("konto", "")

    if not bilag_col or bilag_col not in df.columns or not konto_col or konto_col not in df.columns:
        return CheckResult(check_id, title, pd.DataFrame(), pd.DataFrame(), meta={"missing": missing})

    # Bruk "beløp" slik kontroller ellers gjør
    amt = _amount_from_cols(df, colmap)
    if not include_only_same_sign:
        amt = amt.abs()

    tmp = pd.DataFrame(index=df.index)
    tmp["__bilag__"] = _normalize_key(df[bilag_col])
    tmp["__konto__"] = _normalize_key(df[konto_col])
    tmp["__belop__"] = amt

    # groupby-størrelse per (bilag, konto, beløp) - vektoriseres via transform
    grp_size = tmp.groupby(["__bilag__", "__konto__", "__belop__"], dropna=True)["__belop__"].transform("size")
    is_dup = grp_size >= int(min_count)

    dup_lines = df[is_dup].copy()
    if dup_lines.empty:
        return CheckResult(check_id, title, pd.DataFrame(), df.iloc[0:0].copy(), meta={"missing": missing})

    bilags = _normalize_key(dup_lines[bilag_col]).dropna().unique().astype("string").tolist()

    summ_all = build_voucher_summary(df, cols=cols)
    summ = summ_all[summ_all["Bilag"].astype("string").isin(bilags)].copy()

    # Legg til "Antall dupliserte linjer" per bilag
    g = dup_lines.groupby(_normalize_key(dup_lines[bilag_col]), dropna=True)
    summ = summ.set_index("Bilag")
    summ["AntallDupliserteLinjer"] = g.size()
    summ = summ.reset_index()

    # Alle linjer for disse bilagene
    lines = df[_normalize_key(df[bilag_col]).isin(bilags)].copy()
    lines["__IsDuplicate__"] = False
    lines.loc[dup_lines.index.intersection(lines.index), "__IsDuplicate__"] = True

    return CheckResult(
        check_id=check_id,
        title=title,
        summary_df=summ.reset_index(drop=True),
        lines_df=lines.reset_index(drop=True),
        meta={
            "min_count": min_count,
            "include_only_same_sign": include_only_same_sign,
            "colmap": colmap,
            "missing": missing,
        },
    )
