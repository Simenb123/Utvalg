from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import control_status as a07_control_status
from .page_control_data import build_control_accounts_summary


@dataclass(frozen=True)
class A07ControlPanelState:
    code: str
    summary_text: str
    intro_text: str
    meta_text: str
    match_text: str
    mapping_text: str = ""
    history_text: str = ""
    best_text: str = ""
    next_text: str = ""
    drag_text: str = ""
    linked_accounts_summary: str = ""
    next_action: str = ""
    use_saldobalanse_action: bool = False
    has_history: bool = False
    has_best_suggestion: bool = False
    best_suggestion_within_tolerance: bool = False
    is_locked: bool = False


def build_selected_code_status_message(
    *,
    code: object,
    accounts_df: pd.DataFrame | None,
    basis_col: str = "Endring",
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""
    summary = build_control_accounts_summary(
        accounts_df if isinstance(accounts_df, pd.DataFrame) else pd.DataFrame(),
        code_s,
        basis_col=basis_col,
    )
    return f"Valgt {code_s} | {summary}"


def build_gl_selection_status_message(
    *,
    control_gl_df: pd.DataFrame | None,
    account: object,
    selected_accounts: list[str] | tuple[str, ...],
) -> str:
    account_s = str(account or "").strip()
    if not account_s or control_gl_df is None or control_gl_df.empty:
        return ""

    selected = [str(value).strip() for value in (selected_accounts or []) if str(value).strip()]
    if not selected:
        selected = [account_s]

    matches = control_gl_df.loc[control_gl_df["Konto"].astype(str).str.strip() == account_s]
    code_s = str(matches.iloc[0].get("Kode") or "").strip() if not matches.empty else ""

    if len(selected) == 1:
        if code_s:
            return f"Konto {account_s} er koblet til {code_s}. Bruk hoyreklikk for aa vise koden eller endre mapping."
        return f"Konto {account_s} er ikke koblet enna. Velg A07-kode til hoyre og trykk -> for aa koble."

    mapped_codes: set[str] = set()
    for selected_account in selected:
        selected_matches = control_gl_df.loc[
            control_gl_df["Konto"].astype(str).str.strip() == str(selected_account).strip()
        ]
        if selected_matches.empty:
            continue
        selected_code = str(selected_matches.iloc[0].get("Kode") or "").strip()
        if selected_code:
            mapped_codes.add(selected_code)

    if not mapped_codes:
        return f"{len(selected)} kontoer er valgt uten kobling. Velg A07-kode til hoyre og bruk ->."
    if len(mapped_codes) == 1:
        return f"{len(selected)} kontoer er valgt og er koblet til {next(iter(mapped_codes))}."
    return f"{len(selected)} kontoer er valgt med {len(mapped_codes)} ulike A07-koder."


def build_control_panel_state(
    *,
    code: object,
    navn: object,
    status: object,
    work_label: object,
    why_text: object,
    next_action: object,
    a07_amount_text: object,
    gl_amount_text: object = "",
    diff_amount_text: object = "",
    linked_accounts_df: pd.DataFrame | None = None,
    basis_col: str = "Endring",
    has_history: bool = False,
    best_suggestion: pd.Series | None = None,
    is_locked: bool = False,
) -> A07ControlPanelState:
    code_s = str(code or "").strip()
    if not code_s:
        return A07ControlPanelState(
            code="",
            summary_text="Velg A07-kode til hoyre.",
            intro_text="",
            meta_text="",
            match_text="",
            linked_accounts_summary=build_control_accounts_summary(
                linked_accounts_df if isinstance(linked_accounts_df, pd.DataFrame) else pd.DataFrame(),
                "",
                basis_col=basis_col,
            ),
        )

    work_s = str(work_label or "").strip() or str(status or "").strip() or "Ukjent"
    next_action_s = str(next_action or "").strip()
    if not next_action_s:
        next_action_s = a07_control_status.control_next_action_label(
            status,
            has_history=has_history,
            best_suggestion=best_suggestion,
        )
    intro_fallback = a07_control_status.control_intro_text(
        work_s,
        has_history=has_history,
        best_suggestion=best_suggestion,
    )
    why_s = str(why_text or "").strip()
    display_name = str(navn or "").strip() or code_s

    summary_parts = [f"Valgt {display_name}"]
    if display_name != code_s:
        summary_parts.append(f"({code_s})")
    summary_parts.append(f"Status {work_s}")
    if is_locked:
        summary_parts.append("Last")

    match_parts = [f"A07 {str(a07_amount_text or '-').strip() or '-'}"]
    gl_s = str(gl_amount_text or "").strip()
    diff_s = str(diff_amount_text or "").strip()
    if gl_s:
        match_parts.append(f"GL {gl_s}")
    if diff_s:
        match_parts.append(f"Diff {diff_s}")

    use_saldobalanse_action = a07_control_status.is_saldobalanse_follow_up_action(next_action_s)
    meta_text = ""
    if use_saldobalanse_action:
        meta_text = "Klassifisering i Saldobalanse."

    linked_accounts_summary = build_control_accounts_summary(
        linked_accounts_df if isinstance(linked_accounts_df, pd.DataFrame) else pd.DataFrame(),
        code_s,
        basis_col=basis_col,
    )

    return A07ControlPanelState(
        code=code_s,
        summary_text=" | ".join(summary_parts),
        intro_text=f"Hvorfor: {why_s or intro_fallback}" if (why_s or intro_fallback) else "",
        meta_text=meta_text,
        match_text=" | ".join(match_parts),
        mapping_text="",
        history_text="",
        best_text="",
        next_text=f"Neste: {next_action_s}" if next_action_s and next_action_s != "Ingen handling nødvendig." else "",
        drag_text="",
        linked_accounts_summary=linked_accounts_summary,
        next_action=next_action_s,
        use_saldobalanse_action=use_saldobalanse_action,
        has_history=bool(has_history),
        has_best_suggestion=best_suggestion is not None,
        best_suggestion_within_tolerance=bool(best_suggestion is not None and best_suggestion.get("WithinTolerance", False)),
        is_locked=bool(is_locked),
    )
