from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.shared.ui.selection_summary import build_selection_summary_text

from .data import build_control_accounts_summary


@dataclass(frozen=True)
class A07ControlPanelState:
    code: str
    summary_text: str
    badges_text: str = ""
    reason_text: str = ""
    linked_accounts_summary: str = ""
    next_action: str = ""
    action_label: str = ""
    action_target: str = "mapping"
    meta_text: str = ""
    next_text: str = ""
    match_text: str = ""
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
    audit_status = str(matches.iloc[0].get("MappingAuditStatus") or "").strip() if not matches.empty else ""
    audit_reason = str(matches.iloc[0].get("MappingAuditReason") or "").strip() if not matches.empty else ""

    if audit_status in {"Mistenkelig", "Feil"}:
        suffix = f": {audit_reason}" if audit_reason else "."
        return f"Konto {account_s} har {audit_status.lower()} A07-kobling{suffix}"

    if len(selected) == 1:
        if code_s:
            return f"Konto {account_s} er koblet til {code_s}. Bruk høyreklikk for å vise koden eller endre kobling."
        return f"Konto {account_s} er ikke koblet ennå. Velg A07-kode til høyre og bruk ->."

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
        return f"{len(selected)} kontoer er valgt uten kobling. Velg A07-kode til høyre og bruk ->."
    if len(mapped_codes) == 1:
        return f"{len(selected)} kontoer er valgt og er koblet til {next(iter(mapped_codes))}."
    return f"{len(selected)} kontoer er valgt med {len(mapped_codes)} ulike A07-koder."


def _parse_amount(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None
    low = text.lower()
    if low in {"nan", "none", "null", "na"}:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    text = text.replace("\xa0", " ").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        parsed = float(text)
    except Exception:
        return None
    return -abs(parsed) if negative else parsed


def build_gl_selection_amount_summary(
    *,
    control_gl_df: pd.DataFrame | None,
    selected_accounts: list[str] | tuple[str, ...],
) -> str:
    if control_gl_df is None or control_gl_df.empty or "Konto" not in control_gl_df.columns:
        return ""

    selected: list[str] = []
    seen: set[str] = set()
    for value in selected_accounts or ():
        account = str(value or "").strip()
        if not account or account in seen:
            continue
        selected.append(account)
        seen.add(account)
    if not selected:
        return ""

    amount_columns = [column for column in ("IB", "Endring", "UB") if column in control_gl_df.columns]
    if not amount_columns:
        return ""

    try:
        accounts = control_gl_df["Konto"].astype(str).str.strip()
        matches = control_gl_df.loc[accounts.isin(set(selected))]
    except Exception:
        return ""
    if matches.empty:
        return ""

    sums: dict[str, float] = {}
    for column in amount_columns:
        total = 0.0
        parsed_count = 0
        for raw in matches[column].tolist():
            parsed = _parse_amount(raw)
            if parsed is None:
                continue
            total += parsed
            parsed_count += 1
        if parsed_count:
            sums[column] = total

    if not sums:
        return ""

    return build_selection_summary_text(
        len(selected),
        sums,
        row_noun="kontoer",
        priority=("IB", "Endring", "UB"),
        max_items=3,
        hide_zero=False,
    )


def build_control_panel_state(
    *,
    code: object,
    navn: object,
    guided_status: object = "",
    guided_next: object = "",
    why_text: object = "",
    next_action: object = "",
    linked_accounts_df: pd.DataFrame | None = None,
    basis_col: str = "Endring",
    has_history: bool = False,
    best_suggestion: pd.Series | None = None,
    matching_ready: bool = False,
    suggestion_count: int = 0,
    current_mapping_suspicious: bool = False,
    current_mapping_suspicious_reason: object = "",
    is_locked: bool = False,
    status: object = "",
    work_label: object = "",
    a07_amount_text: object = "",
    gl_amount_text: object = "",
    diff_amount_text: object = "",
) -> A07ControlPanelState:
    code_s = str(code or "").strip()
    if not code_s:
        return A07ControlPanelState(
            code="",
            summary_text="1. Velg konto eller A07-post  2. Forstå status  3. Jobb videre nederst",
            reason_text="Start med en kode i høyre liste eller en konto i venstre liste.",
            linked_accounts_summary=build_control_accounts_summary(
                linked_accounts_df if isinstance(linked_accounts_df, pd.DataFrame) else pd.DataFrame(),
                "",
                basis_col=basis_col,
            ),
        )

    display_name = str(navn or "").strip() or code_s
    legacy_status_text = str(work_label or status or "").strip()
    status_text = str(guided_status or "").strip() or legacy_status_text or "Må avklares"
    next_text = str(guided_next or "").strip() or "Kontroller kobling"
    next_action_text = str(next_action or "").strip()
    reason_text = str(current_mapping_suspicious_reason or why_text or next_action or "").strip()

    badge_parts: list[str] = []
    if matching_ready:
        badge_parts.append("Matching kjort")
    if suggestion_count > 0:
        badge_parts.append(f"Forslag {int(suggestion_count)}")
    if has_history:
        badge_parts.append("Historikk")
    current_account_count = int(len(linked_accounts_df.index)) if isinstance(linked_accounts_df, pd.DataFrame) else 0
    if current_account_count > 0:
        badge_parts.append(f"Koblinger {current_account_count}")

    action_label = next_text
    action_target = "mapping"
    if next_text == "Se forslag":
        action_target = "suggestions"
    elif next_text == "Se historikk":
        action_target = "history"
    elif next_text in {"Apne lonnsklassifisering", "Åpne lønnsklassifisering"}:
        action_target = "saldobalanse"
    elif next_text == "Kontroller kobling":
        action_target = "mapping"

    if current_mapping_suspicious and suggestion_count > 0:
        action_label = "Se forslag"
        action_target = "suggestions"
    elif best_suggestion is not None and status_text in {"Kontroller kobling", "Maa avklares", "Må avklares"}:
        action_label = "Se forslag"
        action_target = "suggestions"
    elif status_text in {"Lonnskontroll", "Lønnskontroll"}:
        action_label = "Åpne lønnsklassifisering"
        action_target = "saldobalanse"
    elif status_text == "Har historikk":
        action_label = "Se historikk"
        action_target = "history"
    elif status_text == "Har forslag":
        action_label = "Se forslag"
        action_target = "suggestions"
    elif status_text in {"Kontroller kobling", "Maa avklares", "Må avklares"}:
        action_label = "Kontroller kobling"
        action_target = "mapping"
    elif status_text == "Ferdig":
        action_label = "Ferdig"
        action_target = "none"

    if not reason_text:
        if current_mapping_suspicious:
            reason_text = "Dagens kobling ser mistenkelig ut."
        elif best_suggestion is not None and status_text in {"Kontroller kobling", "Maa avklares", "Må avklares"}:
            reason_text = "Det finnes et konkret forslag som kan vurderes."
        elif status_text == "Har forslag":
            reason_text = "Det finnes forslag som kan vurderes."
        elif status_text == "Har historikk":
            reason_text = "Det finnes tidligere bruk som kan sammenlignes."
        elif status_text in {"Lonnskontroll", "Lønnskontroll"}:
            reason_text = "Denne posten krever oppfølging i lønnsklassifiseringen."
        elif status_text == "Kontroller kobling":
            reason_text = "Eksisterende kobling bør kontrolleres."
        elif status_text in {"Maa avklares", "Må avklares"}:
            reason_text = "Det finnes ingen trygg standardløsning ennå."

    linked_accounts_summary = build_control_accounts_summary(
        linked_accounts_df if isinstance(linked_accounts_df, pd.DataFrame) else pd.DataFrame(),
        code_s,
        basis_col=basis_col,
    )

    use_saldobalanse_action = action_target == "saldobalanse" or "Saldobalanse" in next_action_text
    meta_text = "Klassifisering i Saldobalanse." if use_saldobalanse_action else " | ".join(badge_parts)
    legacy_next_text = f"Neste: {next_action_text}" if next_action_text else ""
    match_parts = [
        ("A07", a07_amount_text),
        ("SB", gl_amount_text),
        ("Diff", diff_amount_text),
    ]
    match_text = " | ".join(
        f"{label} {str(value).strip()}"
        for label, value in match_parts
        if str(value or "").strip()
    )

    return A07ControlPanelState(
        code=code_s,
        summary_text=f"{display_name} | {status_text}",
        badges_text=" | ".join(badge_parts),
        reason_text=reason_text,
        linked_accounts_summary=linked_accounts_summary,
        next_action=next_action_text,
        action_label=action_label,
        action_target=action_target,
        meta_text=meta_text,
        next_text=legacy_next_text,
        match_text=match_text,
        use_saldobalanse_action=use_saldobalanse_action,
        has_history=bool(has_history),
        has_best_suggestion=best_suggestion is not None,
        best_suggestion_within_tolerance=bool(best_suggestion is not None and best_suggestion.get("WithinTolerance", False)),
        is_locked=bool(is_locked),
    )
