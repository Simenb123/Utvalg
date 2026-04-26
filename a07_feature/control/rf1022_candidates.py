from __future__ import annotations

from typing import Sequence

import pandas as pd

from .evidence import candidate_bool, candidate_text, candidate_tokens, normalize_candidate_evidence
from .rf1022_bridge import (
    RF1022_A07_BRIDGE as _RF1022_A07_BRIDGE,
    resolve_a07_rf1022_group,
    rf1022_group_a07_codes,
)


_RF1022_CANDIDATE_DATA_COLUMNS = (
    "Konto",
    "Navn",
    "Kode",
    "BelopAktiv",
    "Rf1022GroupId",
    "Matchgrunnlag",
    "Belopsgrunnlag",
    "Forslagsstatus",
)

_RF1022_SPECIAL_ADD_ACCOUNTS: dict[str, set[str]] = {
    "feriepenger": {"2940"},
}


def _safe_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _suggestion_account_tokens(raw: object) -> list[str]:
    return list(candidate_tokens(raw))


def _suggestion_flag(row: pd.Series, column: str) -> bool:
    return candidate_bool(row, column)


def _suggestion_text(row: pd.Series, column: str) -> str:
    return candidate_text(row, column)


def _suggestion_has_rf1022_anchor(row: pd.Series) -> tuple[bool, str]:
    evidence = normalize_candidate_evidence(row)
    anchor_signals = evidence.anchor_signals.casefold()
    hit_tokens = evidence.hit_tokens
    parts: list[str] = []
    if evidence.used_rulebook:
        parts.append("Regelbok/alias")
    if hit_tokens or "navnetreff" in anchor_signals:
        parts.append(f"Navn/alias: {hit_tokens}" if hit_tokens else "Navn/alias")
    if evidence.used_special_add:
        parts.append("Tilleggsregel")
    cleaned = [part for idx, part in enumerate(parts) if part and part not in parts[:idx]]
    return bool(cleaned), ", ".join(cleaned)


def _suggestion_has_amount_support(row: pd.Series) -> tuple[bool, str]:
    evidence = _suggestion_text(row, "AmountEvidence").lower()
    within = _suggestion_flag(row, "WithinTolerance")
    diff_abs = abs(_safe_float(row.get("AmountDiffAbs", row.get("Diff"))) or 0.0)
    if within and evidence in {"", "exact", "within_tolerance"}:
        if diff_abs <= 0.01:
            return True, "Eksakt belop"
        return True, "Innen toleranse"
    if within and not evidence:
        return True, "Innen toleranse"
    return False, ""


def _candidate_target_amount(row: pd.Series) -> float:
    target = _safe_float(row.get("A07_Belop"))
    if target is None:
        target = _safe_float(row.get("GL_Sum"))
    return float(target or 0.0)


def _candidate_tolerance(row: pd.Series) -> float:
    target_abs = abs(_candidate_target_amount(row))
    return max(100.0, 0.02 * max(target_abs, 1.0))


def _candidate_account_amount(gl_row: pd.Series, value_col: str) -> float:
    amount = _safe_float(gl_row.get(value_col)) if value_col else None
    if amount is None:
        amount = _safe_float(gl_row.get("BelopAktiv"))
    return float(amount or 0.0)


def _is_special_add_account(row: pd.Series, account: str) -> bool:
    code = _suggestion_text(row, "Kode")
    return account in _RF1022_SPECIAL_ADD_ACCOUNTS.get(code, set()) and normalize_candidate_evidence(row).used_special_add


def _refund_account_has_specific_support(row: pd.Series, account: str, account_name: object) -> bool:
    code = _suggestion_text(row, "Kode").casefold()
    code_name = _suggestion_text(row, "KodeNavn").casefold()
    if "sumavgiftsgrunnlagrefusjon" not in code and "refusjon" not in code_name:
        return True
    if str(account).strip() == "5800":
        return True
    evidence = normalize_candidate_evidence(row)
    text = f"{account_name or ''} {evidence.hit_tokens} {evidence.anchor_signals} {evidence.match_basis}".casefold()
    return any(token in text for token in ("nav", "sykepenger", "sykepenge", "foreldrepenger", "foreldrepenge"))


def _candidate_account_anchor(
    row: pd.Series,
    gl_row: pd.Series,
    account: str,
    *,
    account_count: int,
) -> tuple[bool, str]:
    if not _refund_account_has_specific_support(row, account, gl_row.get("Navn")):
        return False, ""
    history_accounts = set(_suggestion_account_tokens(row.get("HistoryAccounts")))
    if account in history_accounts:
        return True, "Historikk"
    if _is_special_add_account(row, account):
        return True, "Tilleggsregel"
    evidence = normalize_candidate_evidence(row)

    hit_tokens = _suggestion_account_tokens(_suggestion_text(row, "HitTokens").replace(" ", ","))
    account_text = f"{account} {gl_row.get('Navn') or ''}".casefold()
    account_hits = [token for token in hit_tokens if token.casefold() and token.casefold() in account_text]
    if account_hits:
        return True, f"Navn/alias: {', '.join(account_hits)}"

    if account_count == 1 and evidence.used_rulebook:
        return True, "Regelbok/alias"
    if account_count == 1 and evidence.used_usage:
        return True, "Kontobruk"
    return False, ""


def _candidate_account_amount_support(
    row: pd.Series,
    gl_row: pd.Series,
    account: str,
    value_col: str,
    *,
    account_count: int,
) -> tuple[bool, str]:
    amount = _candidate_account_amount(gl_row, value_col)
    if _is_special_add_account(row, account) and abs(amount) > 0.000001:
        return True, "Tilleggsregel"

    row_has_amount, row_amount_text = _suggestion_has_amount_support(row)
    if account_count == 1 and row_has_amount:
        return True, row_amount_text

    if not _suggestion_flag(row, "WithinTolerance"):
        return False, ""
    target = _candidate_target_amount(row)
    tolerance = _candidate_tolerance(row)
    if abs(abs(amount) - abs(target)) <= tolerance:
        if abs(abs(amount) - abs(target)) <= 0.01:
            return True, "Eksakt belop"
        return True, "Egen konto innen toleranse"
    return False, ""


def build_rf1022_candidate_df(
    control_gl_df: pd.DataFrame | None,
    suggestions_df: pd.DataFrame | None,
    group_id: object | None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    """Build strict RF-1022 account candidates for the compact A07 surface.

    A candidate must be tied to the selected RF-1022 group through the A07
    code bridge and have both semantic/catalog support and amount support.
    History-only and amount-only rows are intentionally excluded.
    """

    empty = pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))
    group_s = str(group_id or "").strip()
    if (
        not group_s
        or suggestions_df is None
        or suggestions_df.empty
        or control_gl_df is None
        or control_gl_df.empty
    ):
        return empty
    if "Kode" not in suggestions_df.columns or "ForslagKontoer" not in suggestions_df.columns:
        return empty

    allowed_codes = set(rf1022_group_a07_codes(group_s))
    if not allowed_codes:
        return empty

    gl_work = control_gl_df.copy()
    if "Konto" not in gl_work.columns:
        return empty
    gl_work["Konto"] = gl_work["Konto"].fillna("").astype(str).str.strip()
    gl_by_account: dict[str, pd.Series] = {}
    for _, gl_row in gl_work.iterrows():
        account = str(gl_row.get("Konto") or "").strip()
        if account and account not in gl_by_account:
            gl_by_account[account] = gl_row

    value_col = "BelopAktiv" if "BelopAktiv" in gl_work.columns else (basis_col if basis_col in gl_work.columns else "")
    if value_col not in gl_work.columns:
        value_col = "Endring" if "Endring" in gl_work.columns else ""

    rows_by_account: dict[str, dict[str, object]] = {}
    for _, row in suggestions_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or resolve_a07_rf1022_group(code) != group_s:
            continue
        if _suggestion_text(row, "SuggestionGuardrail").lower() == "blocked":
            continue
        row_has_anchor, row_match_text = _suggestion_has_rf1022_anchor(row)
        if not row_has_anchor:
            continue
        accounts = _suggestion_account_tokens(row.get("ForslagKontoer"))
        account_count = len(accounts)
        status = (
            "Trygt forslag"
            if _suggestion_text(row, "SuggestionGuardrail").lower() == "accepted"
            else "Må vurderes"
        )
        for account in accounts:
            gl_row = gl_by_account.get(account)
            if gl_row is None:
                continue
            has_anchor, match_text = _candidate_account_anchor(
                row,
                gl_row,
                account,
                account_count=account_count,
            )
            has_amount, amount_text = _candidate_account_amount_support(
                row,
                gl_row,
                account,
                value_col,
                account_count=account_count,
            )
            if not has_anchor or not has_amount:
                continue
            if row_match_text and row_match_text not in match_text:
                match_text = f"{match_text}, {row_match_text}" if match_text else row_match_text
            candidate = {
                "Konto": account,
                "Navn": str(gl_row.get("Navn") or "").strip(),
                "Kode": code,
                "BelopAktiv": gl_row.get(value_col) if value_col else gl_row.get("BelopAktiv"),
                "Rf1022GroupId": group_s,
                "Matchgrunnlag": match_text,
                "Belopsgrunnlag": amount_text,
                "Forslagsstatus": status,
            }
            existing = rows_by_account.get(account)
            if existing is None or existing.get("Forslagsstatus") != "Trygt forslag":
                rows_by_account[account] = candidate

    if not rows_by_account:
        return empty
    out = pd.DataFrame(rows_by_account.values())
    return out.reindex(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS), fill_value="").sort_values(
        by=["Forslagsstatus", "Konto"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def build_rf1022_candidate_df_for_groups(
    control_gl_df: pd.DataFrame | None,
    suggestions_df: pd.DataFrame | None,
    group_ids: Sequence[object] | None = None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    """Build RF-1022 candidates across groups for global automatic matching."""

    groups = [
        str(group_id or "").strip()
        for group_id in (group_ids or tuple(_RF1022_A07_BRIDGE.keys()))
        if str(group_id or "").strip()
    ]
    groups = list(dict.fromkeys(groups))
    if not groups:
        return pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))

    frames: list[pd.DataFrame] = []
    for group_id in groups:
        frame = build_rf1022_candidate_df(
            control_gl_df,
            suggestions_df,
            group_id,
            basis_col=basis_col,
        )
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))

    out = pd.concat(frames, ignore_index=True)
    return out.reindex(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS), fill_value="").sort_values(
        by=["Forslagsstatus", "Rf1022GroupId", "Konto"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)


__all__ = [
    "build_rf1022_candidate_df",
    "build_rf1022_candidate_df_for_groups",
]
