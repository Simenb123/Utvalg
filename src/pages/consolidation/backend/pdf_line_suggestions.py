"""Foreslå regnskapslinje-grunnlag fra PDF-regnskap."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


_AMOUNT_RE = re.compile(r"\(?-?\d[\d .\u00a0]*(?:[.,]\d{2})?\)?")


def _norm_text(value: object) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "æ": "ae",
        "ø": "oe",
        "å": "aa",
        "&": " og ",
        "/": " ",
        "-": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_amount(text: str) -> float | None:
    matches = [m.group(0) for m in _AMOUNT_RE.finditer(text or "")]
    if not matches:
        return None
    candidate = matches[-1].strip()
    negative = candidate.startswith("(") and candidate.endswith(")")
    candidate = candidate.strip("()").replace(" ", "").replace("\u00a0", "")
    if not candidate:
        return None
    last_comma = candidate.rfind(",")
    last_dot = candidate.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            candidate = candidate.replace(".", "").replace(",", ".")
        else:
            candidate = candidate.replace(",", "")
    elif last_comma >= 0:
        decimal_part = candidate[last_comma + 1 :]
        if len(decimal_part) == 2:
            candidate = candidate.replace(".", "").replace(",", ".")
        else:
            candidate = candidate.replace(",", "")
    elif last_dot >= 0:
        decimal_part = candidate[last_dot + 1 :]
        if len(decimal_part) != 2:
            candidate = candidate.replace(".", "")
    try:
        value = float(candidate)
    except Exception:
        return None
    return -abs(value) if negative else value


def _score_line_match(line_norm: str, rl_norm: str) -> tuple[float, str]:
    if not line_norm or not rl_norm:
        return 0.0, "none"
    if line_norm == rl_norm:
        return 1.0, "exact"
    if rl_norm in line_norm:
        return 0.97, "contains"
    line_tokens = set(line_norm.split())
    rl_tokens = set(rl_norm.split())
    overlap = len(line_tokens & rl_tokens) / max(len(rl_tokens), 1)
    ratio = SequenceMatcher(a=line_norm, b=rl_norm).ratio()
    if overlap >= 0.8 and ratio >= 0.7:
        return min(0.92, 0.72 + overlap * 0.15 + ratio * 0.1), "token"
    if ratio >= 0.86:
        return min(0.84, 0.3 + ratio * 0.55), "fuzzy"
    return 0.0, "none"


def suggest_line_basis_from_pdf(
    path: str | Path,
    *,
    regnskapslinjer: pd.DataFrame,
    min_confidence: float = 0.55,
) -> pd.DataFrame:
    """Bygg forslag til regnskapslinje-import fra PDF."""
    from document_engine.engine import extract_text_from_file
    from src.shared.regnskap.mapping import normalize_regnskapslinjer

    src = Path(path).expanduser().resolve()
    extracted = extract_text_from_file(src)
    regn = normalize_regnskapslinjer(regnskapslinjer)
    leaf = regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].copy()

    rl_rows = [
        {
            "regnr": int(row["regnr"]),
            "regnskapslinje": str(row.get("regnskapslinje", "") or ""),
            "norm": _norm_text(row.get("regnskapslinje", "")),
        }
        for _, row in leaf.iterrows()
        if str(row.get("regnskapslinje", "") or "").strip()
    ]

    candidates: dict[int, dict[str, object]] = {}
    for segment in extracted.segments:
        lines = [str(line or "").strip() for line in str(segment.text or "").splitlines() if str(line or "").strip()]
        for idx, line in enumerate(lines):
            line_norm = _norm_text(line)
            if not line_norm:
                continue
            amount = _parse_amount(line)
            if amount is None and idx + 1 < len(lines):
                amount = _parse_amount(lines[idx + 1])
            if amount is None:
                continue
            for rl_row in rl_rows:
                score, match_type = _score_line_match(line_norm, rl_row["norm"])
                if score <= 0:
                    continue
                candidate = {
                    "regnr": int(rl_row["regnr"]),
                    "regnskapslinje": str(rl_row["regnskapslinje"]),
                    "ub": float(amount),
                    "confidence": round(float(score), 3),
                    "source_page": int(segment.page or 0) or pd.NA,
                    "source_text": line,
                    "source_regnskapslinje": line,
                    "review_status": "",
                    "match_status": "suggested" if score >= min_confidence else "low_confidence",
                    "match_type": match_type,
                    "pdf_source": extracted.source,
                    "ocr_used": bool(extracted.ocr_used),
                }
                existing = candidates.get(candidate["regnr"])
                if existing is None or float(candidate["confidence"]) > float(existing.get("confidence", 0.0)):
                    candidates[candidate["regnr"]] = candidate

    if not candidates:
        return pd.DataFrame(
            columns=[
                "regnr",
                "regnskapslinje",
                "ub",
                "confidence",
                "source_page",
                "source_text",
                "source_regnskapslinje",
                "review_status",
                "match_status",
                "match_type",
                "pdf_source",
                "ocr_used",
            ]
        )

    result = pd.DataFrame(list(candidates.values())).sort_values(
        ["match_status", "regnr"],
        na_position="last",
    ).reset_index(drop=True)
    return result
