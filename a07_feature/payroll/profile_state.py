from __future__ import annotations

from pathlib import Path

import classification_config
import classification_workspace
import pandas as pd

from account_profile_legacy_api import AccountProfileLegacyApi
from a07_feature import mapping_source

from .. import page_a07_env as _env


def _account_profile_api_for_a07(
    *,
    app_paths_module=None,
    classification_config_module=None,
    account_profile_api_cls=AccountProfileLegacyApi,
) -> AccountProfileLegacyApi:
    app_paths_ref = app_paths_module or _env.app_paths
    classification_config_ref = classification_config_module or classification_config
    return account_profile_api_cls(
        base_dir=Path(app_paths_ref.data_dir()) / "konto_klassifisering_profiles",
        catalog_path=classification_config_ref.resolve_catalog_path(),
    )


def _clean_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _load_code_profile_state(
    client: str | None,
    year: str | int | None,
    mapping_current: dict[str, str] | None,
    gl_df: pd.DataFrame | None = None,
    *,
    account_profile_api_loader=None,
    clean_context_value=None,
    konto_klassifisering_module=None,
) -> dict[str, dict[str, object]]:
    clean_value = clean_context_value or _clean_context_value
    account_profile_api = account_profile_api_loader or _account_profile_api_for_a07
    konto_klassifisering_ref = konto_klassifisering_module or _env.konto_klassifisering

    client_s = clean_value(client)
    if not client_s:
        return {}

    year_i: int | None = None
    year_s = clean_value(year)
    if year_s:
        try:
            year_i = int(year_s)
        except Exception:
            year_i = None

    try:
        document = account_profile_api().load_document(client=client_s, year=year_i)
    except Exception:
        try:
            document = mapping_source.load_current_document(client_s, year=year_i)
        except Exception:
            document = None
    try:
        if year_i is None:
            history_document = None
        else:
            history_document, _ = mapping_source.load_nearest_prior_document(client_s, year_i)
    except Exception:
        history_document = None
    try:
        if konto_klassifisering_ref is not None:
            catalog = konto_klassifisering_ref.load_catalog()
        else:
            catalog = None
    except Exception:
        catalog = None
    if document is None:
        return {}

    rows: list[dict[str, object]] = []
    gl_by_account: dict[str, dict[str, object]] = {}
    if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and "Konto" in gl_df.columns:
        gl_source = gl_df.copy()
        gl_source["Konto"] = gl_source["Konto"].astype(str).str.strip()
        for _, row in gl_source.iterrows():
            account_s = str(row.get("Konto") or "").strip()
            if not account_s or account_s in gl_by_account:
                continue
            gl_by_account[account_s] = {
                "Kontonavn": str(row.get("Navn") or row.get("Kontonavn") or "").strip(),
                "IB": row.get("IB"),
                "Endring": row.get("Endring"),
                "UB": row.get("UB"),
            }
    for account, mapped_code in (mapping_current or {}).items():
        account_s = str(account or "").strip()
        code_s = str(mapped_code or "").strip()
        if not account_s or not code_s:
            continue
        row = {"Konto": account_s, **gl_by_account.get(account_s, {})}
        rows.append(row)

    items_by_account = classification_workspace.build_workspace_items(
        rows,
        document=document,
        history_document=history_document,
        catalog=catalog,
    )
    state_by_code = classification_workspace.build_code_workspace_state(
        mapping_current or {},
        items_by_account,
    )
    normalized: dict[str, dict[str, object]] = {}
    for code, raw in state_by_code.items():
        sources = {str(value).strip() for value in raw.get("sources", set()) if str(value).strip()}
        if sources == {"history"}:
            source = "history"
        elif "manual" in sources:
            source = "manual"
        elif "history" in sources:
            source = "manual"
        else:
            source = next(iter(sorted(sources)), "unknown")
        normalized[code] = {
            "source": source,
            "sources": tuple(sorted(sources)),
            "confidence": raw.get("confidence"),
            "locked": bool(raw.get("locked", False)),
            "missing_control_group": bool(raw.get("missing_control_group", False)),
            "missing_control_tags": bool(raw.get("missing_control_tags", False)),
            "control_conflict": bool(raw.get("control_conflict", False)),
            "why_summary": str(raw.get("why_summary") or "").strip(),
        }
    return normalized


__all__ = [
    "_account_profile_api_for_a07",
    "_clean_context_value",
    "_load_code_profile_state",
]
