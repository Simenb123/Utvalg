from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass

import pandas as pd

from a07_feature.control.data import (
    a07_suggestion_is_strict_auto,
    filter_suggestions_for_rf1022_group,
    rf1022_group_a07_codes,
)


ASSIGN_A07 = "assign_a07"
ASSIGN_RF1022 = "assign_rf1022"
NOOP = "noop"
PROMPT_A07_CODE = "prompt_a07_code"
PROMPT_RF1022_GROUP = "prompt_rf1022_group"


@dataclass(frozen=True)
class ControlGlActionPlan:
    action: str
    accounts: tuple[str, ...] = ()
    target_code: str = ""
    target_group: str = ""
    source_label: str = ""
    message: str = ""


RF1022_GROUP_NAME_HINTS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "100_loenn_ol": (
        (("overtid",), "overtidsgodtgjoerelse"),
        (("time", "timelonn", "timelønn"), "timeloenn"),
        (("trekk", "ferie"), "trekkloennForFerie"),
        (("ferie", "feriepenger"), "feriepenger"),
        (("styre", "honorar", "verv"), "styrehonorarOgGodtgjoerelseVerv"),
        (("lonn", "lønn", "bonus", "etterlonn", "etterlønn"), "fastloenn"),
    ),
    "111_naturalytelser": (
        (("telefon", "mobil", "ekom", "elektron"), "elektroniskKommunikasjon"),
        (("forsik", "gruppeliv", "ulykke"), "skattepliktigDelForsikringer"),
    ),
}


def clean_account_ids(accounts: Sequence[object] | None) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for account in accounts or ():
        account_s = str(account or "").strip()
        if not account_s or account_s in seen:
            continue
        cleaned.append(account_s)
        seen.add(account_s)
    return tuple(cleaned)


def plan_selected_control_gl_action(
    *,
    accounts: Sequence[object] | None,
    work_level: object,
    selected_code: object,
    selected_rf1022_group: object,
) -> ControlGlActionPlan:
    account_ids = clean_account_ids(accounts)
    if not account_ids:
        return ControlGlActionPlan(action=NOOP)

    work_level_s = str(work_level or "").strip() or "a07"
    if work_level_s == "rf1022":
        group_id = str(selected_rf1022_group or "").strip()
        if group_id:
            return ControlGlActionPlan(
                action=ASSIGN_RF1022,
                accounts=account_ids,
                target_group=group_id,
                source_label="RF-1022-mapping",
            )
        return ControlGlActionPlan(
            action=PROMPT_RF1022_GROUP,
            accounts=account_ids,
            message="Velg en RF-1022-post til hoyre for du tildeler kontoer fra GL-listen.",
        )

    code = str(selected_code or "").strip()
    if code:
        return ControlGlActionPlan(
            action=ASSIGN_A07,
            accounts=account_ids,
            target_code=code,
            source_label="Mapping",
        )
    return ControlGlActionPlan(
        action=PROMPT_A07_CODE,
        accounts=account_ids,
        message="Velg en A07-kode til hoyre for du tildeler kontoer fra GL-listen.",
    )


def apply_accounts_to_code(
    mapping: MutableMapping[str, str],
    accounts: Sequence[object] | None,
    code: object,
) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        raise ValueError("Mangler A07-kode for mapping.")
    assigned: list[str] = []
    for account in clean_account_ids(accounts):
        mapping[account] = code_s
        assigned.append(account)
    if not assigned:
        raise ValueError("Mangler konto for mapping.")
    return assigned


def _split_mapping_accounts(value: object) -> set[str]:
    raw = str(value or "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def resolve_rf1022_target_code(
    *,
    group_id: object,
    accounts: Sequence[object] | None = None,
    selected_code: object = None,
    effective_mapping: Mapping[object, object] | None = None,
    suggestions_df: pd.DataFrame | None = None,
    gl_df: pd.DataFrame | None = None,
) -> str | None:
    group_s = str(group_id or "").strip()
    allowed_codes = tuple(rf1022_group_a07_codes(group_s))
    if not group_s or not allowed_codes:
        return None

    selected_code_s = str(selected_code or "").strip()
    if selected_code_s in allowed_codes:
        return selected_code_s

    account_ids = clean_account_ids(accounts)
    mapped_codes: list[str] = []
    mapping = dict(effective_mapping or {})
    for account in account_ids:
        mapped_code = str(mapping.get(account) or "").strip()
        if mapped_code in allowed_codes:
            mapped_codes.append(mapped_code)
    if mapped_codes:
        unique_mapped_codes = sorted(set(mapped_codes))
        if len(unique_mapped_codes) == 1:
            return unique_mapped_codes[0]
        return None

    if isinstance(suggestions_df, pd.DataFrame) and not suggestions_df.empty and account_ids:
        scoped = filter_suggestions_for_rf1022_group(suggestions_df, group_s)
        if not scoped.empty:
            ranked: list[tuple[int, int, float, str]] = []
            account_set = set(account_ids)
            for _, row in scoped.iterrows():
                code = str(row.get("Kode") or "").strip()
                if code not in allowed_codes:
                    continue
                if not a07_suggestion_is_strict_auto(row):
                    continue
                suggestion_accounts = _split_mapping_accounts(row.get("ForslagKontoer"))
                if not suggestion_accounts:
                    continue
                overlap = len(account_set & suggestion_accounts)
                if overlap <= 0:
                    continue
                within_tolerance = 1 if bool(row.get("WithinTolerance")) else 0
                score_raw = pd.to_numeric(row.get("Score"), errors="coerce")
                try:
                    score = float(score_raw) if pd.notna(score_raw) else 0.0
                except Exception:
                    score = 0.0
                ranked.append((overlap, within_tolerance, score, code))
            if ranked:
                ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
                return ranked[0][3]

    if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and account_ids:
        try:
            names = gl_df.loc[gl_df["Konto"].astype(str).str.strip().isin(account_ids), "Navn"]
        except Exception:
            names = pd.Series(dtype="object")
        names_text = " ".join(str(value or "").strip().lower() for value in names if str(value or "").strip())
        for keywords, code in RF1022_GROUP_NAME_HINTS.get(group_s, ()):
            if code not in allowed_codes:
                continue
            if code == "styrehonorarOgGodtgjoerelseVerv" and "honorar" in names_text:
                if not any(token in names_text for token in ("styre", "verv", "godtgj")):
                    continue
            if all(keyword in names_text for keyword in keywords):
                return code
            if any(keyword in names_text for keyword in keywords):
                return code

    if len(allowed_codes) == 1:
        return allowed_codes[0]
    return None


__all__ = [
    "ASSIGN_A07",
    "ASSIGN_RF1022",
    "ControlGlActionPlan",
    "NOOP",
    "PROMPT_A07_CODE",
    "PROMPT_RF1022_GROUP",
    "RF1022_GROUP_NAME_HINTS",
    "apply_accounts_to_code",
    "clean_account_ids",
    "plan_selected_control_gl_action",
    "resolve_rf1022_target_code",
]
