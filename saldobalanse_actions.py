"""saldobalanse_actions.py — Handling-funksjoner for Saldobalanse-fanen.

Alle funksjonene tar `page` (SaldobalansePage-instans) som første argument
og leser/skriver via side-metoder (`page._selected_accounts()`,
`page._profile_for_account(...)`, `page._set_status(...)`). Klassen beholder
tynne metode-delegater for command=-bindings og test-kompatibilitet.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

import account_detail_classification
import classification_config
import classification_workspace
import konto_klassifisering
import payroll_classification
import payroll_feedback
import session
from a07_feature.rule_learning import append_a07_rule_boost_account, append_a07_rule_keyword

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from saldobalanse_payload import (
    STALE_OWNED_COMPANY_LABEL,
    _load_owned_company_name_map,
    _normalize_classification_field_value,
    _suggested_update_for_item,
)


log = logging.getLogger(__name__)


def _invalidate_cache(page) -> None:
    """Dispatch via SaldobalansePage so test doubles (SimpleNamespace) work.

    Tests pass mock objects without the method; the class attribute operates
    on the object's __dict__ directly (just assignments), which works on any
    instance.
    """
    import page_saldobalanse as _ps
    _ps.SaldobalansePage._invalidate_payload_cache(page)




def map_selected_account(page) -> None:
    konto, kontonavn = page._selected_account()
    if not konto or page._analyse_page is None:
        return
    try:
        import page_analyse_sb

        page_analyse_sb.remap_sb_account(page=page._analyse_page, konto=konto, kontonavn=kontonavn)
    except Exception:
        return
    _invalidate_cache(page)
    page.refresh()


def build_feedback_events(
    page,
    updates: dict[str, dict[str, object]],
    *,
    action_type: str,
) -> list[dict[str, object]]:
    def _num(value: object) -> float:
        try:
            return float(pd.to_numeric([value], errors="coerce")[0])
        except Exception:
            return 0.0

    if page._df_last is None or page._df_last.empty:
        return []

    by_account = page._df_last.copy()
    by_account["Konto"] = by_account["Konto"].astype(str).str.strip()
    by_account = by_account.set_index("Konto", drop=False)

    events: list[dict[str, object]] = []
    for account, fields in updates.items():
        account_s = str(account or "").strip()
        if not account_s or not isinstance(fields, dict):
            continue
        row = by_account.loc[account_s] if account_s in by_account.index else None
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0] if not row.empty else None
        result = page._payroll_suggestions.get(account_s)
        suggestion_rows: list[dict[str, object]] = []
        if result is not None:
            for suggestion in result.suggestions.values():
                value = suggestion.value
                if isinstance(value, tuple):
                    value_out: object = list(value)
                else:
                    value_out = value
                suggestion_rows.append(
                    {
                        "field_name": suggestion.field_name,
                        "value": value_out,
                        "source": suggestion.source,
                        "confidence": suggestion.confidence,
                        "reason": suggestion.reason,
                    }
                )
        events.append(
            {
                "action_type": action_type,
                "account_no": account_s,
                "account_name": "" if row is None else str(row.get("Kontonavn") or "").strip(),
                "amount_basis": {
                    "IB": 0.0 if row is None else _num(row.get("IB")),
                    "Endring": 0.0 if row is None else _num(row.get("Endring")),
                    "UB": 0.0 if row is None else _num(row.get("UB")),
                },
                "selected": {
                    key: (list(value) if isinstance(value, tuple) else value)
                    for key, value in fields.items()
                },
                "suggestions": suggestion_rows,
            }
        )
    return events

def persist_payroll_updates(
    page,
    updates: dict[str, dict[str, object]],
    *,
    source: str = "manual",
    confidence: float | None = 1.0,
    status_text: str | None = None,
    feedback_action: str | None = None,
) -> None:
    client, year = page._client_context()
    if not client or not updates:
        return
    feedback_events = page._build_feedback_events(updates, action_type=feedback_action or source)
    try:
        konto_klassifisering.update_profiles(
            client,
            updates,
            year=year,
            source=source,
            confidence=confidence,
        )
    except Exception as exc:
        page._set_status(f"Kunne ikke lagre klassifisering: {exc}")
        return
    try:
        payroll_feedback.append_feedback_events(
            client=client,
            year=year,
            events=feedback_events,
        )
    except Exception:
        log.debug("Kunne ikke skrive payroll-feedbacklogg.", exc_info=True)
    _invalidate_cache(page)
    page.refresh()
    if status_text:
        page._set_status_detail("")
        page._set_status(status_text)

def edit_detail_class_for_selected_accounts(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    try:
        catalog = account_detail_classification.load_detail_class_catalog()
    except Exception:
        catalog = []
    # Nåverdi hentes fra første konto
    first = accounts[0]
    current_id = ""
    profile = page._profile_for_account(first)
    if profile is not None:
        current_id = str(getattr(profile, "detail_class_id", "") or "")
    chosen = page._prompt_detail_class_choice(catalog, current_id)
    if chosen is None:
        return
    updates = {account: {"detail_class_id": chosen} for account in accounts}
    status_msg = (
        f"Fjernet detaljklasse-overstyring på {len(accounts)} kontoer."
        if chosen == ""
        else f"Satte detaljklassifisering på {len(accounts)} kontoer."
    )
    page._persist_payroll_updates(
        updates,
        status_text=status_msg,
        feedback_action="manual_set_detail_class",
    )

def edit_owned_company_for_selected_accounts(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    client, year = page._client_context()
    ownership_map = _load_owned_company_name_map(client, year)
    first = accounts[0]
    current_orgnr = ""
    profile = page._profile_for_account(first)
    if profile is not None:
        current_orgnr = str(getattr(profile, "owned_company_orgnr", "") or "")
    chosen = page._prompt_owned_company_choice(ownership_map, current_orgnr)
    if chosen is None:
        return
    updates = {account: {"owned_company_orgnr": chosen} for account in accounts}
    status_msg = (
        f"Fjernet selskapskobling på {len(accounts)} kontoer."
        if chosen == ""
        else f"Koblet {len(accounts)} kontoer til eid selskap."
    )
    page._persist_payroll_updates(
        updates,
        status_text=status_msg,
        feedback_action="manual_set_owned_company",
    )

def prompt_detail_class_choice(
    page,
    catalog: list[Any],
    current_id: str,
) -> str | None:
    """Modal dropdown; returner valgt id, "" for tom, eller None hvis avbrutt."""

    if tk is None or ttk is None:
        return None
    options: list[tuple[str, str]] = [("", "(ingen overstyring — bruk global regel)")]
    for entry in catalog:
        label = f"{getattr(entry, 'navn', '') or getattr(entry, 'id', '')}"
        options.append((str(getattr(entry, "id", "") or ""), label))

    dlg = tk.Toplevel(page)
    dlg.title("Sett detaljklassifisering")
    dlg.transient(page.winfo_toplevel())
    dlg.grab_set()
    ttk.Label(dlg, text="Velg detaljklasse:").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
    display_values = [label for _id, label in options]
    var = tk.StringVar(value="")
    current_label = next((lab for _id, lab in options if _id == current_id), display_values[0])
    var.set(current_label)
    combo = ttk.Combobox(dlg, textvariable=var, values=display_values, state="readonly", width=50)
    combo.grid(row=1, column=0, padx=10, pady=4, sticky="ew")

    result: dict[str, str | None] = {"value": None}

    def _ok() -> None:
        chosen_label = var.get()
        for cid, lab in options:
            if lab == chosen_label:
                result["value"] = cid
                break
        dlg.destroy()

    def _cancel() -> None:
        result["value"] = None
        dlg.destroy()

    buttons = ttk.Frame(dlg)
    buttons.grid(row=2, column=0, pady=(10, 10))
    ttk.Button(buttons, text="Lagre", command=_ok).pack(side="left", padx=6)
    ttk.Button(buttons, text="Avbryt", command=_cancel).pack(side="left", padx=6)
    dlg.bind("<Return>", lambda _e: _ok())
    dlg.bind("<Escape>", lambda _e: _cancel())
    page.wait_window(dlg)
    return result["value"]

def prompt_owned_company_choice(
    page,
    ownership_map: dict[str, str],
    current_orgnr: str,
) -> str | None:
    """Modal dropdown; returner valgt orgnr, "" for tom, eller None hvis avbrutt."""

    if tk is None or ttk is None:
        return None

    entries: list[tuple[str, str]] = [("", "(ingen kobling)")]
    for orgnr, name in sorted(ownership_map.items(), key=lambda item: item[1].casefold()):
        entries.append((orgnr, f"{name} ({orgnr})"))

    cleaned_current = "".join(ch for ch in str(current_orgnr or "") if ch.isdigit())
    stale = bool(cleaned_current) and cleaned_current not in ownership_map
    if stale:
        entries.append(
            (cleaned_current, f"{STALE_OWNED_COMPANY_LABEL} ({cleaned_current})")
        )

    dlg = tk.Toplevel(page)
    dlg.title("Sett eid selskap")
    dlg.transient(page.winfo_toplevel())
    dlg.grab_set()
    ttk.Label(dlg, text="Velg eid selskap:").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
    display_values = [label for _val, label in entries]
    var = tk.StringVar(value="")
    current_label = next(
        (lab for org, lab in entries if org == cleaned_current),
        display_values[0],
    )
    var.set(current_label)
    combo = ttk.Combobox(dlg, textvariable=var, values=display_values, state="readonly", width=50)
    combo.grid(row=1, column=0, padx=10, pady=4, sticky="ew")

    result: dict[str, str | None] = {"value": None}

    def _ok() -> None:
        chosen_label = var.get()
        for orgnr, lab in entries:
            if lab == chosen_label:
                result["value"] = orgnr
                break
        dlg.destroy()

    def _cancel() -> None:
        result["value"] = None
        dlg.destroy()

    buttons = ttk.Frame(dlg)
    buttons.grid(row=2, column=0, pady=(10, 10))
    ttk.Button(buttons, text="Lagre", command=_ok).pack(side="left", padx=6)
    ttk.Button(buttons, text="Avbryt", command=_cancel).pack(side="left", padx=6)
    dlg.bind("<Return>", lambda _e: _ok())
    dlg.bind("<Escape>", lambda _e: _cancel())
    page.wait_window(dlg)
    return result["value"]

def open_advanced_classification(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    try:
        from views_konto_klassifisering import open_klassifisering_editor
    except Exception:
        return
    subset = page._df_last.loc[page._df_last["Konto"].astype(str).isin(accounts), ["Konto", "Kontonavn", "IB", "Endring", "UB"]].copy()
    client, year = page._client_context()
    open_klassifisering_editor(
        page,
        client=client,
        year=year,
        kontoer=subset.rename(columns={"Kontonavn": "Navn"}),
        on_save=page._hard_refresh,
    )
    page._hard_refresh()

def assign_a07_to_selected_accounts(page, code: str) -> None:
    code_s = str(code or "").strip()
    accounts = page._selected_accounts()
    if not code_s or not accounts:
        return
    updates = {account: {"a07_code": code_s} for account in accounts}
    page._persist_payroll_updates(
        updates,
        status_text=f"Tildelte A07-kode {code_s} til {len(accounts)} kontoer.",
        feedback_action="manual_assign_a07",
    )

def assign_group_to_selected_accounts(page, group_id: str) -> None:
    group_s = str(group_id or "").strip()
    accounts = page._selected_accounts()
    if not group_s or not accounts:
        return
    updates = {account: {"control_group": group_s} for account in accounts}
    page._persist_payroll_updates(
        updates,
        status_text=f"Tildelte RF-1022-post til {len(accounts)} kontoer.",
        feedback_action="manual_assign_rf1022",
    )

def add_tag_to_selected_accounts(page, tag_id: str) -> None:
    tag_s = str(tag_id or "").strip()
    accounts = page._selected_accounts()
    if not tag_s or not accounts:
        return
    updates: dict[str, dict[str, object]] = {}
    for account in accounts:
        current = page._profile_for_account(account)
        tags = set(getattr(current, "control_tags", ()) or ())
        tags.add(tag_s)
        updates[account] = {"control_tags": tuple(sorted(tags))}
    page._persist_payroll_updates(
        updates,
        status_text=f"La til lønnsflagg på {len(accounts)} kontoer.",
        feedback_action="manual_add_tag",
    )

def remove_tag_from_selected_accounts(page, tag_id: str) -> None:
    tag_s = str(tag_id or "").strip()
    accounts = page._selected_accounts()
    if not tag_s or not accounts:
        return
    updates: dict[str, dict[str, object]] = {}
    for account in accounts:
        current = page._profile_for_account(account)
        tags = {tag for tag in (getattr(current, "control_tags", ()) or ()) if str(tag).strip() and str(tag).strip() != tag_s}
        updates[account] = {"control_tags": tuple(sorted(tags))}
    page._persist_payroll_updates(
        updates,
        status_text=f"Fjernet lønnsflagg på {len(accounts)} kontoer.",
        feedback_action="manual_remove_tag",
    )

def append_selected_account_name_to_a07_alias(page, code: str) -> None:
    code_s = str(code or "").strip()
    _account_no, account_name = page._selected_account()
    alias_text = str(account_name or "").strip()
    if not code_s or not alias_text:
        page._set_status("Velg én konto med kontonavn for å legge til A07-alias.")
        return
    try:
        result = append_a07_rule_keyword(code_s, alias_text, exclude=False)
    except Exception as exc:
        page._set_status(f"Kunne ikke lagre A07-alias: {exc}")
        return
    page._after_rule_learning_saved(f"La til kontonavn som A07-alias for {code_s}: {alias_text} ({result.path.name})")

def append_selected_account_to_a07_boost(page, code: str) -> None:
    code_s = str(code or "").strip()
    account_no, _account_name = page._selected_account()
    if not code_s or not account_no:
        page._set_status("Velg én konto for å legge kontonummer til A07-oppsettet.")
        return
    try:
        result = append_a07_rule_boost_account(code_s, account_no)
    except Exception as exc:
        page._set_status(f"Kunne ikke lagre A07-boost: {exc}")
        return
    page._after_rule_learning_saved(f"La til konto {account_no} som A07-boost for {code_s} ({result.path.name})")

def append_selected_account_name_to_rf1022_alias(page, group_id: str) -> None:
    group_s = str(group_id or "").strip()
    _account_no, account_name = page._selected_account()
    alias_text = str(account_name or "").strip()
    if not group_s or not alias_text:
        page._set_status("Velg én konto med kontonavn for å legge til RF-1022-alias.")
        return
    document = classification_config.load_catalog_document()
    raw_groups = document.get("groups")
    if isinstance(raw_groups, list):
        groups = raw_groups
    elif isinstance(raw_groups, dict):
        groups = list(raw_groups.values())
    else:
        groups = []
    payload = next(
        (
            entry
            for entry in groups
            if isinstance(entry, dict) and str(entry.get("id", "") or "").strip() == group_s
        ),
        None,
    )
    if payload is None:
        payload = {
            "id": group_s,
            "label": group_s,
            "active": True,
            "sort_order": 9999,
            "applies_to": ["analyse", "a07", "kontrolloppstilling"],
            "aliases": [],
            "category": "payroll_rf1022_group",
        }
        groups.append(payload)
    aliases = [str(value).strip() for value in payload.get("aliases", []) if str(value).strip()]
    if alias_text not in aliases:
        aliases.append(alias_text)
    payload["aliases"] = aliases
    document["groups"] = groups
    path = classification_config.save_catalog_document(document)
    page._after_rule_learning_saved(f"La til kontonavn som RF-1022-alias for {group_s}: {alias_text} ({path.name})")

def after_rule_learning_saved(page, message: str) -> None:
    try:
        payroll_classification.invalidate_runtime_caches()
    except Exception:
        pass
    _invalidate_cache(page)
    app = getattr(session, "APP", None)
    for attr_name in ("page_a07", "page_analyse"):
        other_page = getattr(app, attr_name, None)
        refresh = getattr(other_page, "refresh_from_session", None)
        if callable(refresh):
            try:
                refresh(session)
            except Exception:
                continue
    page.refresh()
    page._set_status(f"{message} Forslagscache er nullstilt. Bruk Oppfrisk om du vil kontrollere endringen på nytt.")

def apply_history_to_selected_accounts(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    if page._history_document is None:
        page._ensure_payroll_context_loaded()
    if page._history_document is None:
        return
    updates: dict[str, dict[str, object]] = {}
    skipped_missing = 0
    skipped_same = 0
    for account in accounts:
        history_profile = page._history_document.get(account)
        if history_profile is None:
            skipped_missing += 1
            continue
        history_update = {
            "a07_code": str(getattr(history_profile, "a07_code", "") or "").strip(),
            "control_group": str(getattr(history_profile, "control_group", "") or "").strip(),
            "control_tags": tuple(getattr(history_profile, "control_tags", ()) or ()),
        }
        current_profile = page._profile_for_account(account)
        current_state = {
            "a07_code": str(getattr(current_profile, "a07_code", "") or "").strip() if current_profile else "",
            "control_group": str(getattr(current_profile, "control_group", "") or "").strip()
            if current_profile
            else "",
            "control_tags": tuple(getattr(current_profile, "control_tags", ()) or ()) if current_profile else (),
        }
        if all(
            _normalize_classification_field_value(current_state[key])
            == _normalize_classification_field_value(value)
            for key, value in history_update.items()
        ):
            skipped_same += 1
            continue
        updates[account] = history_update
    if not updates:
        reasons: list[str] = []
        if skipped_same:
            reasons.append(f"{skipped_same} allerede i samsvar med historikk")
        if skipped_missing:
            reasons.append(f"{skipped_missing} uten historikk")
        reason_text = f" ({', '.join(reasons)})" if reasons else ""
        page._set_status(f"Ingen kontoer oppdatert med fjorårets klassifisering{reason_text}.")
        return
    skipped_total = len(accounts) - len(updates)
    page._persist_payroll_updates(
        updates,
        source="history",
        confidence=1.0,
        status_text=(
            f"Brukte fjorårets klassifisering på {len(updates)} kontoer."
            + (f" Hoppet over {skipped_total}." if skipped_total else "")
        ),
        feedback_action="use_history",
    )

def apply_best_suggestions_to_selected_accounts(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    updates: dict[str, dict[str, object]] = {}
    skipped_locked = 0
    skipped_without_suggestion = 0
    skipped_same = 0
    for account in accounts:
        item = page._workspace_item_for_account(account)
        if item is None:
            skipped_without_suggestion += 1
            continue
        if bool(getattr(item.current, "locked", False)):
            skipped_locked += 1
            continue
        fields = _suggested_update_for_item(item)
        if fields:
            updates[account] = fields
        elif classification_workspace.matching_suggestion_labels(item):
            skipped_same += 1
        else:
            skipped_without_suggestion += 1
    if not updates:
        reasons: list[str] = []
        if skipped_same:
            reasons.append(f"{skipped_same} i samsvar")
        if skipped_locked:
            reasons.append(f"{skipped_locked} låst")
        if skipped_without_suggestion:
            reasons.append(f"{skipped_without_suggestion} uten forslag")
        reason_text = f" ({', '.join(reasons)})" if reasons else ""
        page._set_status(f"Ingen forslag godkjent{reason_text}.")
        return
    skipped_total = len(accounts) - len(updates)
    page._persist_payroll_updates(
        updates,
        source="heuristic",
        confidence=0.9,
        status_text=(
            f"Godkjente forslag på {len(updates)} kontoer."
            + (f" Hoppet over {skipped_total}." if skipped_total else "")
        ),
        feedback_action="approve_suggestion",
    )

def toggle_lock_selected_accounts(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    profiles = [page._profile_for_account(account) for account in accounts]
    should_lock = not all(bool(getattr(profile, "locked", False)) for profile in profiles if profile is not None)
    updates = {account: {"locked": should_lock} for account in accounts}
    page._persist_payroll_updates(
        updates,
        status_text=f"{'Låste' if should_lock else 'Låste opp'} {len(accounts)} kontoer.",
        feedback_action="toggle_lock",
    )

def clear_selected_payroll_fields(page) -> None:
    accounts = page._selected_accounts()
    if not accounts:
        return
    updates = {
        account: {
            "a07_code": "",
            "control_group": "",
            "control_tags": (),
        }
        for account in accounts
    }
    page._persist_payroll_updates(
        updates,
        status_text=f"Nullstilte lønnsklassifisering på {len(accounts)} kontoer.",
        feedback_action="clear_payroll_fields",
    )

def clear_selected_suspicious_payroll_fields(page) -> None:
    accounts = page._selected_suspicious_accounts()
    if not accounts:
        page._set_status("Fant ingen mistenkelige lagrede lønnsklassifiseringer i utvalget.")
        return
    updates = {
        account: {
            "a07_code": "",
            "control_group": "",
            "control_tags": (),
        }
        for account in accounts
    }
    page._persist_payroll_updates(
        updates,
        status_text=f"Nullstilte lønnsklassifisering på {len(accounts)} mistenkelige kontoer.",
        feedback_action="clear_suspicious_payroll_fields",
    )

