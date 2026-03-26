from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from .models import SuggestionRow


def _parse_konto_list(raw: Any) -> List[str]:
    if raw is None:
        return []

    if isinstance(raw, (list, tuple, set)):
        out: List[str] = []
        for value in raw:
            text = str(value).strip()
            if text:
                out.append(text)
        return out

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        return [part.strip() for part in re.split(r"[,+;\s]+", text) if part.strip()]

    text = str(raw).strip()
    return [text] if text else []


def apply_suggestion_to_mapping(
    mapping: Dict[str, str],
    suggestion: Any,
    allow_overwrite: bool = False,
    *,
    override_existing: Optional[bool] = None,
    override_existing_mapping: Optional[bool] = None,
) -> Dict[str, str]:
    if (
        override_existing is not None
        and override_existing_mapping is not None
        and bool(override_existing) != bool(override_existing_mapping)
    ):
        raise ValueError(
            "apply_suggestion_to_mapping: conflicting override flags; use only one alias."
        )

    if override_existing_mapping is not None:
        allow_overwrite = bool(override_existing_mapping)
    elif override_existing is not None:
        allow_overwrite = bool(override_existing)

    if mapping is None:
        mapping = {}

    if isinstance(suggestion, SuggestionRow):
        code = str(suggestion.code).strip()
        kontoer = [str(k).strip() for k in suggestion.accounts]
    else:
        code_attr = getattr(suggestion, "code", None)
        accounts_attr = getattr(suggestion, "accounts", None)
        if code_attr is not None and accounts_attr is not None:
            code = str(code_attr).strip()
            kontoer = [str(k).strip() for k in accounts_attr]
        else:
            if isinstance(suggestion, pd.Series):
                code = str(suggestion.get("Kode") or suggestion.get("code") or "").strip()
                kontoer_raw = suggestion.get("ForslagKontoer") or suggestion.get("accounts")
            elif isinstance(suggestion, dict):
                code = str(suggestion.get("Kode") or suggestion.get("code") or "").strip()
                kontoer_raw = suggestion.get("ForslagKontoer") or suggestion.get("accounts")
            else:
                try:
                    code = str(suggestion["Kode"]).strip()
                except Exception:
                    try:
                        code = str(suggestion["code"]).strip()
                    except Exception:
                        code = ""
                try:
                    kontoer_raw = suggestion["ForslagKontoer"]
                except Exception:
                    try:
                        kontoer_raw = suggestion["accounts"]
                    except Exception:
                        kontoer_raw = None

            if not code:
                raise TypeError(
                    "apply_suggestion_to_mapping expected SuggestionRow or row-like input with Kode."
                )

            kontoer = _parse_konto_list(kontoer_raw)

    for konto in kontoer:
        konto_str = str(konto).strip()
        if not konto_str:
            continue
        if (not allow_overwrite) and konto_str in mapping and str(mapping.get(konto_str, "")).strip():
            continue
        mapping[konto_str] = code

    return mapping
