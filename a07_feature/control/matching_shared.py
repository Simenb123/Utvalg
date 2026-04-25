from __future__ import annotations

from typing import Mapping

import pandas as pd


_SEMANTIC_FAMILY_TOKENS: dict[str, tuple[str, ...]] = {
    "payroll": (
        "lonn",
        "loenn",
        "overtid",
        "ferie",
        "feriepenger",
        "etterlonn",
        "etterloenn",
        "godtgjoerelse",
        "godtgodt",
        "styrehonorar",
    ),
    "pension": (
        "pensjon",
        "premie",
        "otp",
    ),
    "phone": (
        "telefon",
        "elektronisk",
        "kommunikasjon",
        "mobil",
    ),
    "insurance": ("forsikring",),
    "tax": (
        "skatt",
        "aga",
        "arbeidsgiveravgift",
        "forskuddstrekk",
        "refusjon",
    ),
}

_SEMANTIC_FAMILY_LABELS = {
    "payroll": "lonn/godtgjoerelse",
    "pension": "pensjon",
    "phone": "telefon/kommunikasjon",
    "insurance": "forsikring",
    "tax": "skatt/aga/refusjon",
}


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        try:
            text = str(value or "").strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
            return float(text)
        except Exception:
            return 0.0


def _format_picker_amount(value: object, *, decimals: int = 2) -> str:
    amount = _safe_float(value)
    text = f"{amount:,.{int(decimals)}f}"
    return text.replace(",", " ").replace(".", ",")


def _parse_konto_tokens(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(value).strip() for value in raw if str(value).strip()]
    else:
        values = [part.strip() for part in str(raw or "").replace(";", ",").split(",") if part.strip()]

    seen: set[str] = set()
    accounts: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        accounts.append(value)
    return accounts


def _normalize_semantic_text(value: object) -> str:
    text = str(value or "").strip().casefold()
    replacements = {
        "Ã¸": "o",
        "Ã¦": "ae",
        "Ã¥": "a",
        "Ã¶": "o",
        "Ã¤": "a",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def infer_semantic_family(value: object) -> str:
    text = _normalize_semantic_text(value)
    if not text:
        return ""
    for family, tokens in _SEMANTIC_FAMILY_TOKENS.items():
        if any(token in text for token in tokens):
            return family
    return ""


def _family_label(family: str) -> str:
    return _SEMANTIC_FAMILY_LABELS.get(str(family or "").strip(), "annen familie")


def build_account_name_lookup(gl_df: pd.DataFrame) -> dict[str, str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return {}

    lookup: dict[str, str] = {}
    names = gl_df["Navn"] if "Navn" in gl_df.columns else pd.Series("", index=gl_df.index)
    for konto, navn in zip(gl_df["Konto"].tolist(), names.tolist()):
        konto_s = str(konto or "").strip()
        if not konto_s:
            continue
        lookup[konto_s] = str(navn or "").strip()
    return lookup


def format_accounts_with_names(
    raw: object,
    *,
    account_names: Mapping[str, str] | None = None,
    joiner: str = " + ",
    max_items: int | None = None,
) -> str:
    accounts = _parse_konto_tokens(raw)
    if not accounts:
        return ""

    visible = accounts
    hidden_count = 0
    if max_items is not None and int(max_items) > 0 and len(accounts) > int(max_items):
        visible = accounts[: int(max_items)]
        hidden_count = len(accounts) - len(visible)

    labels: list[str] = []
    for account in visible:
        name = str((account_names or {}).get(account) or "").strip()
        labels.append(f"{account} {name}".strip())
    if hidden_count > 0:
        labels.append(f"+{hidden_count} til")
    return joiner.join(labels)


__all__ = [
    "_family_label",
    "_format_picker_amount",
    "_normalize_semantic_text",
    "_parse_konto_tokens",
    "_safe_float",
    "build_account_name_lookup",
    "format_accounts_with_names",
    "infer_semantic_family",
]
