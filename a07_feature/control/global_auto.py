from __future__ import annotations

from typing import Mapping

import pandas as pd

from .basis import control_gl_basis_column_for_account as _shared_control_gl_basis_column_for_account
from .rf1022_bridge import RF1022_UNKNOWN_GROUP, resolve_a07_rf1022_group, rf1022_group_a07_codes


_GLOBAL_AUTO_PLAN_COLUMNS = (
    "Konto",
    "Navn",
    "Kode",
    "Rf1022GroupId",
    "Kol",
    "Belop",
    "Action",
    "Status",
    "Reason",
)


def _global_auto_empty_plan() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_GLOBAL_AUTO_PLAN_COLUMNS))


def _global_auto_row_text(row: pd.Series | Mapping[str, object], column: str) -> str:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return ""
    try:
        value = getter(column)
    except Exception:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def _global_auto_row_value(row: pd.Series | Mapping[str, object], column: str) -> object:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return ""
    try:
        return getter(column)
    except Exception:
        return ""


def _global_auto_candidate_has_semantic_support(row: pd.Series | Mapping[str, object]) -> bool:
    if _global_auto_row_text(row, "Matchgrunnlag"):
        return True
    if _global_auto_row_text(row, "HitTokens"):
        return True
    if _global_auto_row_text(row, "AnchorSignals"):
        return True
    for column in ("UsedRulebook", "UsedUsage", "UsedSpecialAdd"):
        value = _global_auto_row_value(row, column)
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        if isinstance(value, str):
            if value.strip().casefold() in {"1", "true", "ja", "yes"}:
                return True
        elif bool(value):
            return True
    return False


def _global_auto_candidate_has_amount_support(row: pd.Series | Mapping[str, object]) -> bool:
    if _global_auto_row_text(row, "Belopsgrunnlag"):
        return True
    amount_evidence = _global_auto_row_text(row, "AmountEvidence").casefold()
    if amount_evidence in {"exact", "within_tolerance"}:
        return True
    value = _global_auto_row_value(row, "WithinTolerance")
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "ja", "yes"}
    return bool(value)


def _global_auto_candidate_is_strict(row: pd.Series | Mapping[str, object]) -> bool:
    if not _global_auto_candidate_has_semantic_support(row):
        return False
    if not _global_auto_candidate_has_amount_support(row):
        return False
    status = _global_auto_row_text(row, "Forslagsstatus")
    if status == "Trygt forslag":
        return True
    guardrail = _global_auto_row_text(row, "SuggestionGuardrail").casefold()
    return guardrail == "accepted"


def _global_auto_candidate_suggestion_df(
    *,
    account: str,
    code: str,
    row: pd.Series | Mapping[str, object],
    strict: bool,
) -> pd.DataFrame:
    match_basis = _global_auto_row_text(row, "Matchgrunnlag")
    amount_basis = _global_auto_row_text(row, "Belopsgrunnlag")
    has_amount = bool(amount_basis) or _global_auto_candidate_has_amount_support(row)
    return pd.DataFrame(
        [
            {
                "Kode": code,
                "ForslagKontoer": account,
                "WithinTolerance": bool(has_amount),
                "SuggestionGuardrail": "accepted" if strict else "review",
                "UsedRulebook": bool(match_basis),
                "UsedUsage": "kontobruk" in match_basis.casefold(),
                "UsedSpecialAdd": "special" in match_basis.casefold() or "spesial" in match_basis.casefold(),
                "HitTokens": match_basis,
                "Explain": match_basis,
            }
        ]
    )


def _global_auto_gl_row_df(
    *,
    account: str,
    row: pd.Series | Mapping[str, object],
    gl_by_account: Mapping[str, pd.Series],
    basis_col: str,
) -> pd.DataFrame:
    gl_row = gl_by_account.get(account)
    if gl_row is not None:
        return pd.DataFrame([dict(gl_row)])

    name = _global_auto_row_text(row, "Navn")
    amount = _global_auto_row_value(row, "BelopAktiv")
    if amount in ("", None):
        amount = _global_auto_row_value(row, "Belop")
    value_column = _shared_control_gl_basis_column_for_account(account, name, requested_basis=basis_col)
    data = {
        "Konto": account,
        "Navn": name,
        "IB": 0.0,
        "Endring": 0.0,
        "UB": 0.0,
        "BelopAktiv": amount,
        "Kol": value_column,
    }
    data[value_column] = amount
    return pd.DataFrame([data])


def build_global_auto_mapping_plan(
    candidates_df: pd.DataFrame | None,
    gl_df: pd.DataFrame | None,
    suggestions_df: pd.DataFrame | None,
    mapping_current: Mapping[str, str] | None,
    *,
    solved_codes: set[str] | None = None,
    locked_codes: set[str] | None = None,
    basis_col: str = "Endring",
    rulebook: object | None = None,
) -> pd.DataFrame:
    if candidates_df is None or candidates_df.empty:
        return _global_auto_empty_plan()

    from .mapping_audit import build_mapping_audit_df

    gl_by_account: dict[str, pd.Series] = {}
    if gl_df is not None and not gl_df.empty and "Konto" in gl_df.columns:
        gl_work = gl_df.copy()
        gl_work["Konto"] = gl_work["Konto"].fillna("").astype(str).str.strip()
        for _, gl_row in gl_work.iterrows():
            account = str(gl_row.get("Konto") or "").strip()
            if account and account not in gl_by_account:
                gl_by_account[account] = gl_row

    planned_mapping = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_current or {}).items()
        if str(account).strip()
    }
    solved = {str(code).strip() for code in (solved_codes or set()) if str(code).strip()}
    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    rows: list[dict[str, object]] = []

    for _, row in candidates_df.iterrows():
        account = _global_auto_row_text(row, "Konto")
        code = _global_auto_row_text(row, "Kode")
        group_id = _global_auto_row_text(row, "Rf1022GroupId")
        if not code and group_id:
            group_codes = rf1022_group_a07_codes(group_id)
            if len(group_codes) == 1:
                code = group_codes[0]
        name = _global_auto_row_text(row, "Navn")
        strict = _global_auto_candidate_is_strict(row)
        action = "review"
        status = "Maa vurderes"
        reason = "Kandidaten er ikke strict-auto."
        kol = str(_global_auto_row_value(row, "Kol") or "").strip()
        belop = _global_auto_row_value(row, "Belop")
        if belop in ("", None):
            belop = _global_auto_row_value(row, "BelopAktiv")

        if not account or not code:
            action = "invalid"
            status = "Ugyldig"
            reason = "Kandidaten mangler konto eller A07-kode."
        elif not strict:
            action = "review"
            status = "Maa vurderes"
            reason = "Kandidaten er ikke godkjent som trygt forslag."
        elif account not in gl_by_account:
            action = "invalid"
            status = "Ugyldig"
            reason = "Kontoen finnes ikke i aktiv GL."
        else:
            current_code = str(planned_mapping.get(account) or "").strip()
            resolved_group = resolve_a07_rf1022_group(code)
            if code in solved:
                action = "already"
                status = "Allerede avstemt"
                reason = "A07-koden har allerede 0 i diff og er ferdig."
            elif current_code == code:
                action = "already"
                status = "Allerede koblet"
                reason = "Kontoen er allerede koblet til samme A07-kode."
            elif current_code and current_code != code:
                action = "conflict"
                status = "Konflikt"
                reason = f"Kontoen er allerede koblet til {current_code}."
            elif code in locked:
                action = "locked"
                status = "Laast"
                reason = f"A07-koden {code} er laast."
            elif resolved_group == RF1022_UNKNOWN_GROUP:
                action = "review"
                status = "Uavklart"
                reason = "A07-koden mangler avklart RF-1022-bro."
            elif group_id and group_id != resolved_group:
                action = "blocked"
                status = "Feil"
                reason = f"Kandidaten peker til {group_id}, men A07-koden peker til {resolved_group}."
            else:
                gl_row_df = _global_auto_gl_row_df(
                    account=account,
                    row=row,
                    gl_by_account=gl_by_account,
                    basis_col=basis_col,
                )
                synthetic_suggestion = _global_auto_candidate_suggestion_df(
                    account=account,
                    code=code,
                    row=row,
                    strict=strict,
                )
                support_suggestions = synthetic_suggestion
                if suggestions_df is not None and not suggestions_df.empty:
                    support_suggestions = pd.concat(
                        [suggestions_df, synthetic_suggestion],
                        ignore_index=True,
                        sort=False,
                    )
                audit_df = build_mapping_audit_df(
                    gl_row_df,
                    {account: code},
                    suggestions_df=support_suggestions,
                    basis_col=basis_col,
                    rulebook=rulebook,
                )
                if audit_df.empty:
                    action = "review"
                    status = "Uavklart"
                    reason = "Kunne ikke kontrollere simulert mapping."
                else:
                    audit_row = audit_df.iloc[0]
                    audit_status = str(audit_row.get("Status") or "").strip()
                    audit_reason = str(audit_row.get("Reason") or "").strip()
                    kol = str(audit_row.get("Kol") or kol or "").strip()
                    belop = audit_row.get("Belop")
                    if audit_status == "Trygg":
                        action = "apply"
                        status = "Trygg"
                        reason = audit_reason or "Simulert mapping er trygg."
                        planned_mapping[account] = code
                    else:
                        action = "review" if audit_status in {"Mistenkelig", "Uavklart"} else "blocked"
                        status = audit_status or "Maa vurderes"
                        reason = audit_reason or "Simulert mapping er ikke trygg."

        rows.append(
            {
                "Konto": account,
                "Navn": name,
                "Kode": code,
                "Rf1022GroupId": group_id or resolve_a07_rf1022_group(code),
                "Kol": kol,
                "Belop": belop,
                "Action": action,
                "Status": status,
                "Reason": reason,
            }
        )

    if not rows:
        return _global_auto_empty_plan()
    return pd.DataFrame(rows, columns=list(_GLOBAL_AUTO_PLAN_COLUMNS)).reset_index(drop=True)


__all__ = ["build_global_auto_mapping_plan"]
