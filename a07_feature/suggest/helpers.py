from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional, Set, Tuple

import pandas as pd

from .models import (
    BASIS_ALIASES,
    BASIS_DEBET,
    BASIS_ENDRING,
    BASIS_IB,
    BASIS_KREDIT,
    BASIS_UB,
    PAYROLL_TOKENS,
)
from .rulebook import RulebookRule


_word_re = re.compile(r"[A-Za-z0-9]+")


def _norm_token(token: str) -> str:
    text = token.strip().lower()
    text = text.replace("ø", "oe").replace("æ", "ae").replace("å", "aa")
    return text


def _tokenize(text: str) -> Set[str]:
    if not text:
        return set()

    normalized = _norm_token(str(text))
    tokens = {_norm_token(match.group(0)) for match in _word_re.finditer(normalized)}
    out = set()
    for token in tokens:
        if token.isdigit() or len(token) >= 3:
            out.add(token)
    return out


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
            return float(value)
        text = str(value).strip()
        if not text:
            return 0.0
        text = text.replace(" ", "").replace("\xa0", "")
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        return float(text)
    except Exception:
        return 0.0


def _konto_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(\d{3,6})", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _konto_in_ranges(konto: Any, ranges: Tuple[Tuple[int, int], ...]) -> bool:
    if not ranges:
        return False
    konto_int = _konto_int(konto)
    if konto_int is None:
        return False
    for start, end in ranges:
        if start <= konto_int <= end:
            return True
    return False


def available_basis(gl_df: pd.DataFrame) -> Set[str]:
    cols_l = {str(c).strip().lower(): c for c in gl_df.columns}
    avail: Set[str] = set()

    for basis, aliases in BASIS_ALIASES.items():
        found_col = None
        for alias in aliases:
            if alias in cols_l:
                found_col = cols_l[alias]
                break
        if found_col is None:
            continue
        try:
            series = pd.to_numeric(gl_df[found_col], errors="coerce").fillna(0.0)
            if float(series.abs().sum()) > 0.0:
                avail.add(basis)
        except Exception:
            avail.add(basis)

    if BASIS_ENDRING not in avail and BASIS_DEBET in avail and BASIS_KREDIT in avail:
        avail.add(BASIS_ENDRING)

    return avail


def _get_series(gl_df: pd.DataFrame, basis: str) -> pd.Series:
    want_basis = str(basis or "").strip() or BASIS_UB
    cols_l = {str(c).strip().lower(): c for c in gl_df.columns}

    for alias in BASIS_ALIASES.get(want_basis, (want_basis.lower(),)):
        if alias in cols_l:
            return pd.to_numeric(gl_df[cols_l[alias]], errors="coerce").fillna(0.0)

    if want_basis == BASIS_ENDRING:
        deb = None
        for alias in BASIS_ALIASES[BASIS_DEBET]:
            if alias in cols_l:
                deb = pd.to_numeric(gl_df[cols_l[alias]], errors="coerce").fillna(0.0)
                break
        kre = None
        for alias in BASIS_ALIASES[BASIS_KREDIT]:
            if alias in cols_l:
                kre = pd.to_numeric(gl_df[cols_l[alias]], errors="coerce").fillna(0.0)
                break
        if deb is not None and kre is not None:
            return deb - kre

    return pd.Series([0.0] * len(gl_df), index=gl_df.index, dtype="float64")


def _is_a07_relevant_account(konto: Any, name_tokens: Set[str]) -> bool:
    konto_int = _konto_int(konto)
    if konto_int is not None:
        text = str(konto_int)
        if text.startswith(("5", "6")):
            return True
        if text.startswith(("26", "27", "28", "29")):
            return True

    if name_tokens & PAYROLL_TOKENS:
        return True

    return False


def _auto_basis_for_code(
    code: str,
    code_name: str,
    avail: Set[str],
    *,
    default_basis: str,
    basis_by_code: Mapping[str, str],
    rule: Optional[RulebookRule],
) -> str:
    code_l = str(code or "").strip().lower()
    name_l = _norm_token(str(code_name or "").strip())

    if code in basis_by_code:
        candidate = str(basis_by_code[code])
        if candidate in avail:
            return candidate
    if code_l in basis_by_code:
        candidate = str(basis_by_code[code_l])
        if candidate in avail:
            return candidate

    if rule and rule.basis:
        candidate = str(rule.basis).strip()
        if candidate.lower() == "ub":
            normalized = BASIS_UB
        elif candidate.lower() == "ib":
            normalized = BASIS_IB
        elif candidate.lower() == "endring":
            normalized = BASIS_ENDRING
        elif candidate.lower() == "debet":
            normalized = BASIS_DEBET
        elif candidate.lower() == "kredit":
            normalized = BASIS_KREDIT
        else:
            normalized = candidate
        if normalized in avail:
            return normalized

    expense_like = any(token in code_l for token in ("loenn", "bonus", "feriep", "kilometer", "kommun", "forsik"))
    liability_like = any(token in code_l for token in ("trekk", "skatt", "forskudd")) or "trekk" in name_l

    if expense_like and BASIS_DEBET in avail:
        return BASIS_DEBET
    if liability_like and BASIS_KREDIT in avail:
        return BASIS_KREDIT
    if BASIS_ENDRING in avail:
        return BASIS_ENDRING
    if default_basis in avail:
        return default_basis
    if BASIS_UB in avail:
        return BASIS_UB
    if BASIS_IB in avail:
        return BASIS_IB
    return BASIS_ENDRING


def _score_account(
    *,
    target_abs: float,
    gl_amount: float,
    code_tokens: Set[str],
    acct_tokens: Set[str],
    konto: Any,
    rule: Optional[RulebookRule],
) -> Tuple[float, Tuple[str, ...]]:
    gl_abs = abs(float(gl_amount))
    target = abs(float(target_abs))

    denominator = max(target, 1.0)
    diff = abs(target - gl_abs)
    amount_score = 1.0 - min(diff / denominator, 1.0)

    hits = tuple(sorted(code_tokens & acct_tokens))
    token_score = (len(hits) / max(len(code_tokens), 1)) if code_tokens else 0.0

    rule_score = 0.0
    sign_score = 1.0
    if rule:
        in_range = 1.0 if _konto_in_ranges(konto, rule.allowed_ranges) else 0.0
        boosted = 1.0 if (_konto_int(konto) in set(rule.boost_accounts)) else 0.0
        rule_score = 0.5 * in_range + 0.5 * boosted
        if rule.expected_sign in (1, -1):
            sign_score = 1.0 if float(gl_amount) * float(rule.expected_sign) >= 0 else 0.0

    score = 0.50 * amount_score + 0.25 * token_score + 0.15 * rule_score + 0.10 * sign_score
    return max(0.0, min(1.0, score)), hits
