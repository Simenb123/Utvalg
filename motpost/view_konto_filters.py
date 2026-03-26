from __future__ import annotations

from typing import Any

import pandas as pd


def _normalize_mva_code_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    try:
        num = float(text.replace(" ", "").replace(",", "."))
    except Exception:
        return text.upper()
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return text.upper()


def _normalize_mva_rate_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    try:
        num = float(text.replace(" ", "").replace(",", "."))
    except Exception:
        return text
    if abs(num) <= 1.0:
        num *= 100.0
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return f"{num:.1f}".rstrip("0").rstrip(".")


def _split_tokens(value: Any, *, kind: str) -> tuple[str, ...]:
    raw = [part.strip() for part in str(value or "").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    normalize = _normalize_mva_rate_token if kind == "rate" else _normalize_mva_code_token
    for part in raw:
        token = normalize(part)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def available_mva_codes(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty or "MVA-kode" not in df.columns:
        return ["Alle"]

    codes: list[str] = []
    seen: set[str] = set()
    for value in df["MVA-kode"].tolist():
        for token in _split_tokens(value, kind="code"):
            if token in seen:
                continue
            seen.add(token)
            codes.append(token)
    return ["Alle", *sorted(codes, key=lambda s: (len(s), s))]


def enrich_details_with_mva_flags(df: pd.DataFrame, *, expected_rate: Any = "25") -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    code_series = out["MVA-kode"] if "MVA-kode" in out.columns else pd.Series([""] * len(out), index=out.index)
    rate_series = out["MVA-prosent"] if "MVA-prosent" in out.columns else pd.Series([""] * len(out), index=out.index)
    out["_mva_code_tokens"] = code_series.map(lambda v: _split_tokens(v, kind="code"))
    out["_mva_rate_tokens"] = rate_series.map(lambda v: _split_tokens(v, kind="rate"))
    out["_mva_has_code"] = out["_mva_code_tokens"].map(bool)

    expected_token = _normalize_mva_rate_token(expected_rate)
    if expected_token:
        out["_mva_matches_expected"] = out["_mva_rate_tokens"].map(
            lambda values: bool(values) and all(token == expected_token for token in values)
        )
        out["_mva_avvik"] = ~out["_mva_matches_expected"]
    else:
        out["_mva_matches_expected"] = False
        out["_mva_avvik"] = False

    return out


def filter_bilag_details_by_mva(
    df: pd.DataFrame,
    *,
    mva_code: Any = "Alle",
    mode: str | None = "Alle",
    expected_rate: Any = "25",
) -> pd.DataFrame:
    out = enrich_details_with_mva_flags(df, expected_rate=expected_rate)
    if out.empty:
        return out

    code_token = _normalize_mva_code_token(mva_code)
    if code_token and code_token != "ALLE":
        out = out.loc[out["_mva_code_tokens"].map(lambda values: code_token in values)]

    mode_norm = str(mode or "Alle").strip().lower()
    if mode_norm == "med mva-kode":
        out = out.loc[out["_mva_has_code"]]
    elif mode_norm == "uten mva-kode":
        out = out.loc[~out["_mva_has_code"]]
    elif mode_norm == "treffer forventet":
        out = out.loc[out["_mva_matches_expected"]]
    elif mode_norm == "avvik fra forventet":
        out = out.loc[out["_mva_avvik"]]

    return out.copy()
