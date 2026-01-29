from __future__ import annotations

from typing import Any, Sequence
import re

import pandas as pd

from .core import CheckResult, build_voucher_summary, resolve_core_columns, _amount_from_cols, _normalize_key


def _split_tokens_csv(txt: str | None) -> list[str]:
    if not txt:
        return []
    parts = [p.strip() for p in str(txt).split(",")]
    return [p for p in parts if p]


def override_risk_vouchers(
    df: pd.DataFrame,
    cols: Any | None = None,
    keywords_csv: str | None = "kontant, cash, private, lån, loan, mellomværende, korrigering",
    min_score: float = 1.5,
    min_abs_amount: float = 100_000.0,
    rare_account_max_bilag: int = 3,
    rare_account_min_line_abs: float = 100_000.0,
    exclude_accounts: Sequence[str] | None = None,
    check_id: str = "risk_vouchers",
    title: str = "Risiko-bilag",
) -> CheckResult:
    """
    Heuristisk risikoscore per bilag.

    Dette er ikke "fasit", men en måte å finne bilag som bør vurderes ekstra.
    Logikken er *additiv* – flere signaler gir høyere score.

    Score-komponenter (typisk):
      - nøkkelord i tekst (1.0)
      - mangler dokumentnr (0.5)
      - få linjer (0.5)
      - kun debet/kredit (0.5)
      - månedsslutt (0.25)
      - årsslutt (0.25)
      - sjeldne kontoer på store beløp (1.0)

    Filtrering:
      - behold bilag med score >= min_score OG abs(netto) >= min_abs_amount
      - exclude_accounts kan brukes til å fjerne bilag som inneholder spesifikke kontoer (linjenivå)
    """
    colmap, missing = resolve_core_columns(df, cols=cols, strict=False)
    bilag_col = colmap.get("bilag", "")
    konto_col = colmap.get("konto", "")
    tekst_col = colmap.get("tekst", "")
    doc_col = colmap.get("dokumentnr", "")
    dato_col = colmap.get("dato", "")

    if not bilag_col or bilag_col not in df.columns:
        return CheckResult(check_id, title, pd.DataFrame(), pd.DataFrame(), meta={"missing": missing})

    # Basis-sammendrag (hele bilaget)
    summ = build_voucher_summary(df, cols=cols)
    if summ.empty:
        return CheckResult(check_id, title, summ, df.iloc[0:0].copy(), meta={"missing": missing})

    summ = summ.copy()
    score = pd.Series(0.0, index=summ.index, dtype="float64")
    reasons = pd.Series("", index=summ.index, dtype="string")

    def _add(mask: pd.Series, points: float, reason: str) -> None:
        nonlocal score, reasons
        if mask.any():
            score.loc[mask] = score.loc[mask] + float(points)
            reasons.loc[mask] = reasons.loc[mask] + f"{reason}; "

    # 1) Nøkkelord
    keywords = [k.lower() for k in _split_tokens_csv(keywords_csv)]
    if keywords and tekst_col and tekst_col in df.columns:
        pattern = "|".join(re.escape(k) for k in keywords)
        text_s = df[tekst_col].astype("string").fillna("")
        hit = text_s.str.lower().str.contains(pattern, regex=True, na=False)
        bilag_hit = _normalize_key(df.loc[hit, bilag_col]).dropna().unique().astype("string").tolist()
        _add(summ["Bilag"].astype("string").isin(bilag_hit), 1.0, "tekst: nøkkelord")

    # 2) Mangler dokumentnr
    if doc_col and doc_col in df.columns:
        doc_s = df[doc_col].astype("string").fillna("").str.strip()
        missing_doc_bilag = _normalize_key(df.loc[doc_s.eq("") | doc_s.str.lower().eq("nan"), bilag_col]).dropna().unique().astype("string").tolist()
        _add(summ["Bilag"].astype("string").isin(missing_doc_bilag), 0.5, "mangler dokumentnr")

    # 3) Få linjer
    _add(summ["AntallLinjer"] <= 2, 0.5, "få linjer")

    # 4) Kun debet eller kun kredit
    has_debet = summ["SumDebetAbs"] > 0
    has_kredit = summ["SumKreditAbs"] > 0
    _add(has_debet ^ has_kredit, 0.5, "kun en side (debet/kredit)")

    # 5) Månedsslutt / årsslutt
    # Bruker DatoMax om tilgjengelig, ellers beregner på df
    if "DatoMax" in summ.columns and summ["DatoMax"].notna().any():
        d = pd.to_datetime(summ["DatoMax"], errors="coerce")
    elif dato_col and dato_col in df.columns:
        d_line = pd.to_datetime(df[dato_col], errors="coerce", dayfirst=True)
        max_by_bilag = pd.DataFrame({"Bilag": _normalize_key(df[bilag_col]), "__d__": d_line}).groupby("Bilag", dropna=True)["__d__"].max()
        d = pd.to_datetime(summ["Bilag"].map(max_by_bilag), errors="coerce")
    else:
        d = pd.Series(pd.NaT, index=summ.index)

    d1 = d + pd.Timedelta(days=1)
    month_end = d.notna() & (d1.dt.month != d.dt.month)
    year_end = d.notna() & (d.dt.month == 12) & (d.dt.day >= 28)
    _add(month_end, 0.25, "månedsslutt")
    _add(year_end, 0.25, "årsslutt")

    # 6) Sjeldne kontoer brukt på store beløp
    if konto_col and konto_col in df.columns:
        bilag_key = _normalize_key(df[bilag_col])
        konto_key = _normalize_key(df[konto_col])

        konto_bilag_counts = (
            pd.DataFrame({"konto": konto_key, "bilag": bilag_key})
            .dropna()
            .drop_duplicates()
            .groupby("konto")["bilag"]
            .size()
        )
        rare_accounts = set(konto_bilag_counts[konto_bilag_counts <= int(rare_account_max_bilag)].index.astype("string").tolist())

        amt_abs = _amount_from_cols(df, colmap).abs()
        is_rare_line = konto_key.astype("string").isin(rare_accounts) & (amt_abs >= float(rare_account_min_line_abs))
        rare_bilag = bilag_key[is_rare_line].dropna().unique().astype("string").tolist()
        _add(summ["Bilag"].astype("string").isin(rare_bilag), 1.0, "sjeldne kontoer + store beløp")

    # Legg på kolonner
    summ["Risikoscore"] = score
    summ["Risikogrunnlag"] = reasons.str.strip()

    # Filtrer
    keep = (summ["Risikoscore"] >= float(min_score)) & (summ["NettoAbs"] >= float(min_abs_amount))
    summ = summ[keep].copy()

    # Eventuell konto-ekskludering (fjerner bilag som inneholder ekskluderte kontoer)
    if exclude_accounts and konto_col and konto_col in df.columns and not summ.empty:
        exclude_set = {str(x).strip() for x in exclude_accounts if str(x).strip()}
        if exclude_set:
            bilag_key = _normalize_key(df[bilag_col])
            konto_key = _normalize_key(df[konto_col])
            bad_bilag = bilag_key[konto_key.astype("string").isin(exclude_set)].dropna().unique().astype("string").tolist()
            summ = summ[~summ["Bilag"].astype("string").isin(bad_bilag)].copy()

    if summ.empty:
        return CheckResult(check_id, title, summ, df.iloc[0:0].copy(), meta={"missing": missing})

    bilags = summ["Bilag"].astype("string").tolist()
    lines = df[_normalize_key(df[bilag_col]).isin(bilags)].copy()

    return CheckResult(
        check_id=check_id,
        title=title,
        summary_df=summ.reset_index(drop=True),
        lines_df=lines.reset_index(drop=True),
        meta={
            "keywords_csv": keywords_csv,
            "min_score": min_score,
            "min_abs_amount": min_abs_amount,
            "rare_account_max_bilag": rare_account_max_bilag,
            "rare_account_min_line_abs": rare_account_min_line_abs,
            "exclude_accounts": list(exclude_accounts or []),
            "colmap": colmap,
            "missing": missing,
        },
    )
