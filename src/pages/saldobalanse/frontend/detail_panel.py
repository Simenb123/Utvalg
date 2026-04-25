"""saldobalanse_detail_panel.py — Detaljpanel og statustekst for Saldobalanse-fanen.

Beskrivelser og totaler i høyre-panelet — funksjoner tar `page` som første
argument. Klassen [page_saldobalanse.py](page_saldobalanse.py) beholder tynne
delegater.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import classification_workspace
import formatting
import payroll_classification

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from ..backend.payload import (
    PAYROLL_COLUMNS,
    WORK_MODE_PAYROLL,
    _payroll_match_basis_text,
    _payroll_problem_text,
    _rf1022_treatment_text,
    _top_payroll_suggestion,
)


def payroll_intro_sections(page) -> dict[str, str]:
    return {
        "headline": "Lønnsklassifisering",
        "current": (
            "Køer\n"
            "Mistenkelig lagret: åpenbart feil lagret klassifisering.\n"
            "Klar til forslag: trygge forslag klare til bruk.\n"
            "Historikk tilgjengelig: fjoråret finnes, men er ikke brukt ennå.\n"
            "Trenger vurdering: forslag finnes, men må vurderes.\n"
            "Umappet: ingen klassifisering er satt.\n"
            "Låste: beholdes uendret til du låser opp."
        ),
        "suggested": (
            "Forslag\n"
            "1. Velg kø øverst.\n"
            "2. Velg konto i listen.\n"
            "3. Les forslag og neste handling.\n"
            "4. Bruk primærknappen når den passer.\n"
            "5. Behandle flere kontoer samlet bare når de faktisk skal likt."
        ),
        "treatment": "RF-1022-behandling vises her for valgt konto.",
        "next": "Velg en konto for å få én tydelig anbefalt handling.",
        "why": "",
    }

def selection_detail_sections(
    page,
    items: list[classification_workspace.ClassificationWorkspaceItem],
    *,
    button_label: str,
) -> dict[str, str]:
    queue_order = (
        classification_workspace.QUEUE_SUSPICIOUS,
        classification_workspace.QUEUE_READY,
        classification_workspace.QUEUE_HISTORY,
        classification_workspace.QUEUE_REVIEW,
        classification_workspace.QUEUE_UNMAPPED,
        classification_workspace.QUEUE_LOCKED,
        classification_workspace.QUEUE_SAVED,
    )
    queue_counts: dict[str, int] = {}
    for item in items:
        queue_counts[item.queue_name] = queue_counts.get(item.queue_name, 0) + 1
    queue_parts = [f"{name}: {queue_counts[name]}" for name in queue_order if queue_counts.get(name)]
    remaining = [name for name in queue_counts if name not in queue_order]
    queue_parts.extend(f"{name}: {queue_counts[name]}" for name in sorted(remaining))
    mixed_selection = len(queue_counts) > 1
    return {
        "headline": f"{len(items)} valgte kontoer",
        "current": "Utvalg\n" + ("\n".join(queue_parts) if queue_parts else "Ingen kontoer valgt."),
        "suggested": (
            "Forslag\n"
            + (
                f"Primærhandling: {button_label}\n"
                "Bruk den bare når den passer for hele utvalget."
                if button_label
                else "Velg en konto for å få en tydelig anbefalt handling."
            )
        ),
        "treatment": (
            "RF-1022-behandling må vurderes per konto."
            if mixed_selection
            else "RF-1022-behandling kan som regel håndteres samlet for dette utvalget."
        ),
        "next": (
            "Åpne klassifisering hvis kontoene trenger ulik behandling."
            if mixed_selection
            else (button_label or "Velg konto for å få en tydelig anbefalt handling.")
        ),
        "why": "",
    }

def refresh_detail_panel(page) -> None:
    headline_var = page._detail_headline_var
    current_var = page._detail_current_var
    suggested_var = page._detail_suggested_var
    treatment_var = getattr(page, "_detail_treatment_var", None)
    next_var = getattr(page, "_detail_next_var", None)
    why_var = page._detail_why_var
    if (
        headline_var is None
        or current_var is None
        or suggested_var is None
        or treatment_var is None
        or next_var is None
        or why_var is None
    ):
        return
    items = page._selected_workspace_items()
    action, button_label = page._determine_primary_action(items)
    page._current_primary_action = action
    if len(items) == 1:
        detail = classification_workspace.format_why_panel(items[0])
        headline_var.set(detail["headline"])
        current_var.set(detail["current"])
        suggested_var.set(detail["suggested"])
        treatment_var.set(detail.get("treatment", ""))
        next_var.set(detail.get("next", ""))
        why_var.set(detail.get("why", ""))
        page._set_status_detail(
            " | ".join(
                part
                for part in (
                    f"Valgt {items[0].account_no}",
                    items[0].account_name or "-",
                    f"Status {items[0].status_label}",
                )
                if part
            )
        )
    elif items:
        detail = page._selection_detail_sections(items, button_label=button_label)
        headline_var.set(detail["headline"])
        current_var.set(detail["current"])
        suggested_var.set(detail["suggested"])
        treatment_var.set(detail.get("treatment", ""))
        next_var.set(detail.get("next", ""))
        why_var.set(detail.get("why", ""))
        page._set_status_detail(f"{len(items)} valgte kontoer" + (f" | {button_label}" if button_label else ""))
    else:
        if page._is_payroll_mode():
            intro = page._payroll_intro_sections()
            headline_var.set(intro["headline"])
            current_var.set(intro["current"])
            suggested_var.set(intro["suggested"])
            treatment_var.set(intro.get("treatment", ""))
            next_var.set(intro.get("next", ""))
            why_var.set(intro.get("why", ""))
            page._set_status_detail("Velg kø og konto for å starte.")
        else:
            headline_var.set("Velg en konto for å se klassifisering.")
            current_var.set("")
            suggested_var.set("")
            treatment_var.set("")
            next_var.set("")
            why_var.set("")
            page._set_status_detail("")
    sync_selection_actions = getattr(page, "_sync_selection_actions_visibility", None)
    if callable(sync_selection_actions):
        sync_selection_actions()
    refresh_totals = getattr(page, "_refresh_selection_totals", None)
    if callable(refresh_totals):
        refresh_totals()

def refresh_selection_totals(page) -> None:
    summary_var = getattr(page, "_selection_totals_var", None)
    if summary_var is None:
        return
    accounts = page._selected_accounts()
    if not accounts or page._df_last.empty:
        try:
            summary_var.set("")
        except Exception:
            pass
        return
    try:
        subset = page._df_last.loc[page._df_last["Konto"].astype(str).isin(accounts)].copy()
    except Exception:
        subset = pd.DataFrame()
    if subset.empty:
        try:
            summary_var.set("")
        except Exception:
            pass
        return
    ib_series = subset["IB"] if "IB" in subset.columns else pd.Series(0.0, index=subset.index)
    change_series = subset["Endring"] if "Endring" in subset.columns else pd.Series(0.0, index=subset.index)
    ub_series = subset["UB"] if "UB" in subset.columns else pd.Series(0.0, index=subset.index)
    total_change = float(pd.to_numeric(change_series, errors="coerce").fillna(0.0).sum())
    total_ub = float(pd.to_numeric(ub_series, errors="coerce").fillna(0.0).sum())
    total_ib = float(pd.to_numeric(ib_series, errors="coerce").fillna(0.0).sum())
    parts = [
        f"{len(subset.index)} valgt",
        f"IB {formatting.fmt_amount(total_ib)}",
        f"Endring {formatting.fmt_amount(total_change)}",
        f"UB {formatting.fmt_amount(total_ub)}",
    ]
    if len(subset.index) == 1:
        row = subset.iloc[0]
        parts.append(f"{row.get('Konto') or '-'} {row.get('Kontonavn') or '-'}")
    try:
        summary_var.set(" | ".join(parts))
    except Exception:
        pass

def selected_payroll_detail_text(page) -> str:
    account_no, account_name = page._selected_account()
    if not account_no:
        return ""
    row = page._row_for_account(account_no)
    if row is None:
        return ""
    result = page._payroll_result_for_account(account_no)
    profile = page._profile_for_account(account_no)
    catalog = page._profile_catalog

    parts = [f"Valgt {account_no}"]
    if account_name:
        parts.append(account_name)

    actual_a07 = str(getattr(profile, "a07_code", "") or "").strip()
    actual_group = payroll_classification.format_control_group(
        str(getattr(profile, "control_group", "") or "").strip(),
        catalog,
    )
    actual_tags = payroll_classification.format_control_tags(getattr(profile, "control_tags", ()), catalog)
    suggestion_map = dict(result.suggestions) if result is not None else {}

    suggested_a07 = ""
    if "a07_code" in suggestion_map and isinstance(suggestion_map["a07_code"].value, str):
        suggested_a07 = str(suggestion_map["a07_code"].value or "").strip()
    suggested_group = ""
    if "control_group" in suggestion_map and isinstance(suggestion_map["control_group"].value, str):
        suggested_group = payroll_classification.format_control_group(
            str(suggestion_map["control_group"].value or "").strip(),
            catalog,
        )
    suggested_tags = ""
    if "control_tags" in suggestion_map and isinstance(suggestion_map["control_tags"].value, tuple):
        suggested_tags = payroll_classification.format_control_tags(suggestion_map["control_tags"].value, catalog)

    if actual_a07:
        parts.append(f"Lagret A07: {actual_a07}")
    elif suggested_a07:
        parts.append(f"Forslag A07: {suggested_a07}")

    if actual_group:
        parts.append(f"Lagret RF-1022: {actual_group}")
    elif suggested_group:
        parts.append(f"Forslag RF-1022: {suggested_group}")

    if actual_tags:
        parts.append(f"Lagrede flagg: {actual_tags}")
    elif suggested_tags:
        parts.append(f"Forslag flagg: {suggested_tags}")

    if result is not None and result.payroll_status:
        parts.append(f"Status: {result.payroll_status}")

    confidence = getattr(profile, "confidence", None)
    top_suggestion = _top_payroll_suggestion(result)
    if confidence is None and top_suggestion is not None:
        confidence = top_suggestion.confidence
    confidence_text = payroll_classification.confidence_label(confidence)
    if confidence_text:
        parts.append(f"Sikkerhet: {confidence_text}")

    match_basis = _payroll_match_basis_text(result)
    if match_basis:
        parts.append(f"Match: {match_basis}")

    rf1022_text = str(actual_group or suggested_group or "").strip()
    treatment_text = _rf1022_treatment_text(
        account_no,
        account_name,
        ib=row.get("IB"),
        endring=row.get("Endring"),
        ub=row.get("UB"),
        rf1022_text=rf1022_text,
    )
    if treatment_text:
        parts.append(treatment_text)

    problem = page._suspicious_profile_issue_for_account(
        account_no,
        account_name=account_name,
        profile=profile,
    )
    if not problem:
        problem = _payroll_problem_text(result, top_suggestion) if result is not None else ""
    if problem:
        parts.append(problem)

    next_action = page._next_action_for_account(
        account_no,
        account_name=account_name,
        result=result,
        profile=profile,
    )
    if next_action:
        parts.append(f"Neste: {next_action}")

    if len(parts) == 2:
        parts.append("Ingen lagret klassifisering eller forslag.")
    return " | ".join(parts)

def sync_status_text(page) -> None:
    if page._status_var is None:
        return
    text = page._status_base_text
    if page._status_detail_text:
        text = f"{text} | {page._status_detail_text}" if text else page._status_detail_text
    try:
        page._status_var.set(text)
    except Exception:
        pass

def set_status_detail(page, text: str) -> None:
    page._status_detail_text = str(text or "").strip()
    page._sync_status_text()
