from __future__ import annotations

from .queue_shared import *  # noqa: F403


def _accounts_by_code(mapping: Mapping[object, object] | None) -> dict[str, list[str]]:
    by_code: dict[str, set[str]] = {}
    for account, code in (mapping or {}).items():
        account_s = str(account or "").strip()
        code_s = str(code or "").strip()
        if not account_s or not code_s:
            continue
        by_code.setdefault(code_s, set()).add(account_s)
    return {
        code: sorted(accounts, key=lambda value: (len(value), value))
        for code, accounts in by_code.items()
    }

def _safe_previous_accounts_by_code(
    *,
    mapping_current: Mapping[object, object] | None,
    mapping_previous: Mapping[object, object] | None,
    gl_df: pd.DataFrame,
) -> dict[str, list[str]]:
    previous_by_code = _accounts_by_code(mapping_previous)
    if not previous_by_code:
        return {}
    current_by_code = _accounts_by_code(mapping_current)
    gl_accounts = {
        str(account).strip()
        for account in gl_df.get("Konto", pd.Series(dtype="object")).astype(str).tolist()
        if str(account).strip()
    }
    current_owner = {
        str(account).strip(): str(code or "").strip()
        for account, code in (mapping_current or {}).items()
        if str(account or "").strip()
    }

    safe: dict[str, list[str]] = {}
    for code, accounts in previous_by_code.items():
        if current_by_code.get(code):
            continue
        if any(account not in gl_accounts for account in accounts):
            continue
        if any(current_owner.get(account) and current_owner.get(account) != code for account in accounts):
            continue
        safe[code] = accounts
    return safe

def _suggestions_by_code(suggestions_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
        return {}
    work = suggestions_df.copy()
    work["_code_key"] = work["Kode"].fillna("").astype(str).str.strip()
    return {
        str(code).strip(): group.drop(columns=["_code_key"], errors="ignore").copy()
        for code, group in work.groupby("_code_key", sort=False)
        if str(code).strip()
    }

def _best_suggestions_by_code(
    suggestions_by_code: Mapping[str, pd.DataFrame],
    *,
    locked_codes: set[str],
) -> dict[str, pd.Series]:
    best: dict[str, pd.Series] = {}
    for code, code_suggestions in suggestions_by_code.items():
        row = best_suggestion_row_for_code(code_suggestions, code, locked_codes=locked_codes)
        if row is not None:
            best[code] = row
    return best

def _mapping_audit_reasons_by_code(mapping_audit_df: pd.DataFrame | None) -> dict[str, list[str]]:
    if mapping_audit_df is None or mapping_audit_df.empty:
        return {}
    if "CurrentA07Code" not in mapping_audit_df.columns or "Status" not in mapping_audit_df.columns:
        return {}
    work = mapping_audit_df.copy()
    work["_code_key"] = work["CurrentA07Code"].fillna("").astype(str).str.strip()
    work["_status_key"] = work["Status"].fillna("").astype(str).str.strip()
    bad = work.loc[work["_status_key"].isin({"Mistenkelig", "Feil"})]
    reasons_by_code: dict[str, list[str]] = {}
    for _, row in bad.iterrows():
        code = str(row.get("_code_key") or "").strip()
        if not code:
            continue
        account = str(row.get("Konto") or "").strip()
        reason = str(row.get("Reason") or "").strip()
        if account and reason:
            reasons_by_code.setdefault(code, []).append(f"{account}: {reason}")
        elif reason:
            reasons_by_code.setdefault(code, []).append(reason)
    return reasons_by_code

def build_control_queue_df(
    a07_overview_df: pd.DataFrame,
    suggestions_df: pd.DataFrame,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
    code_profile_state: dict[str, dict[str, object]] | None = None,
    locked_codes: set[str] | None = None,
    mapping_audit_df: pd.DataFrame | None = None,
    rulebook: object | None = None,
) -> pd.DataFrame:
    if a07_overview_df is None or a07_overview_df.empty:
        return _empty_control_df()

    if suggestions_df is None:
        suggestions_df = _empty_suggestions_df()
    elif not suggestions_df.empty and "SuggestionGuardrail" not in suggestions_df.columns:
        suggestions_df = decorate_suggestions_for_display(suggestions_df, gl_df)

    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    effective_rulebook = _load_effective_rulebook(rulebook)
    suggestions_lookup = _suggestions_by_code(suggestions_df)
    best_suggestion_lookup = _best_suggestions_by_code(suggestions_lookup, locked_codes=locked)
    current_accounts_lookup = _accounts_by_code(mapping_current)
    history_accounts_lookup = _safe_previous_accounts_by_code(
        mapping_current=mapping_current,
        mapping_previous=mapping_previous,
        gl_df=gl_df,
    )
    account_name_lookup = build_account_name_lookup(gl_df)
    audit_reasons_lookup = _mapping_audit_reasons_by_code(mapping_audit_df)
    rows: list[dict[str, object]] = []
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        aga_value = _optional_bool(row.get("AgaPliktig"))
        if aga_value is None:
            aga_value = _rulebook_aga_pliktig(effective_rulebook, code)
        rf1022_group_id = a07_code_rf1022_group(code)
        work_family = work_family_for_rf1022_group(rf1022_group_id)
        reconcile_status = str(row.get("Status") or "").strip()
        current_accounts = current_accounts_lookup.get(code, [])
        history_accounts = history_accounts_lookup.get(code, [])
        code_suggestions = suggestions_lookup.get(code, _empty_suggestions_df())
        best_row = best_suggestion_lookup.get(code)
        profile_state = dict((code_profile_state or {}).get(code) or {})
        profile_source = str(profile_state.get("source") or "").strip().lower()
        has_explicit_mapping = bool(current_accounts)
        locked_flag = bool(code in locked or profile_state.get("locked"))
        needs_control_group = bool(profile_state.get("missing_control_group"))
        needs_control_tags = bool(profile_state.get("missing_control_tags"))
        has_control_conflict = bool(profile_state.get("control_conflict"))
        matching_ready = bool(not code_suggestions.empty)
        suggestion_guardrail = str(best_row.get("SuggestionGuardrail") or "").strip() if best_row is not None else ""
        suggestion_guardrail_reason = (
            str(best_row.get("SuggestionGuardrailReason") or "").strip() if best_row is not None else ""
        )
        current_mapping_suspicious, current_mapping_suspicious_reason = evaluate_current_mapping_suspicion(
            code=code,
            code_name=navn,
            current_accounts=current_accounts,
            history_accounts=history_accounts,
            gl_df=gl_df,
            profile_state=profile_state,
            account_name_lookup=account_name_lookup,
        )
        audit_reasons = audit_reasons_lookup.get(code, [])
        if audit_reasons:
            current_mapping_suspicious = True
            current_mapping_suspicious_reason = "; ".join(audit_reasons[:3])
        next_action = a07_control_status.control_next_action_label(
            reconcile_status,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if locked_flag:
            work_status = "Ferdig"
        elif has_explicit_mapping and profile_source == "history":
            work_status = "Historikk"
        elif has_explicit_mapping:
            work_status = "Manuell"
        elif next_action in {
            "Bruk historikk.",
            "Bruk beste forslag.",
            "Sammenlign med historikk.",
            "Vurder foreslÃ¥tt mapping.",
            "Aapne historikk for valgt kode.",
            "Se forslag for valgt kode.",
        }:
            work_status = "Forslag"
        else:
            work_status = "UlÃ¸st"
        if work_status == "Ferdig":
            display_status = "Ferdig"
        elif has_control_conflict or needs_control_group:
            display_status = "Krever RF-1022"
        elif needs_control_tags:
            display_status = "Krever lÃ¸nnsflagg"
        elif work_status == "Historikk":
            display_status = "Historikk brukt"
        elif work_status == "Forslag" and bool(history_accounts) and best_row is None:
            display_status = "Historikk klar"
        elif work_status == "Forslag":
            display_status = "Trygt forslag"
        elif work_status == "Manuell":
            display_status = "Kontroller mapping"
        else:
            display_status = "MÃ¥ avklares"

        recommended = a07_control_status.control_recommendation_label(
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if work_status == "Historikk":
            recommended = "Se historikk"
            next_action = "Sammenlign med historikk."
        elif has_control_conflict:
            recommended = "RF-1022"
            next_action = "Rydd RF-1022-post for mappede kontoer."
        elif needs_control_group:
            recommended = "RF-1022"
            next_action = "Tildel RF-1022-post i Saldobalanse."
        elif needs_control_tags:
            recommended = "LÃ¸nnsflagg"
            next_action = "FullfÃ¸r lÃ¸nnsflagg i Saldobalanse."
        elif work_status == "Manuell":
            recommended = "Kontroller"
            next_action = "Kontroller dagens mapping."
        elif display_status == "Ferdig":
            recommended = "Ferdig"
            next_action = "Ingen handling nÃ¸dvendig."

        if locked_flag:
            guided_status = "Ferdig"
            display_status = "Ferdig"
            recommended = "Ferdig"
            guided_next = "Ingen handling"
            next_action = "Ingen handling nodvendig."
        elif current_mapping_suspicious:
            guided_status = "Mistenkelig kobling"
            display_status = "Mistenkelig kobling"
            recommended = "Se forslag" if best_row is not None else "Kontroller kobling"
            guided_next = "Se forslag" if best_row is not None else "Kontroller kobling"
            next_action = (
                "Se forslag for valgt kode."
                if best_row is not None
                else current_mapping_suspicious_reason or "Kontroller dagens kobling."
            )
        elif best_row is not None and not has_explicit_mapping:
            guided_status = "Har forslag"
            display_status = "Har forslag"
            recommended = "Se forslag"
            guided_next = "Se forslag"
            next_action = suggestion_guardrail_reason or "Se forslag for valgt kode."
        elif bool(history_accounts) and not has_explicit_mapping:
            guided_status = "Har historikk"
            display_status = "Har historikk"
            recommended = "Se historikk"
            guided_next = "Se historikk"
            next_action = "Aapne historikk for valgt kode."
        elif has_control_conflict or needs_control_group or needs_control_tags:
            guided_status = "Lonnskontroll"
            display_status = "Lonnskontroll"
            recommended = "Apne lonnsklassifisering"
            guided_next = "Apne lonnsklassifisering"
            if has_control_conflict:
                next_action = "Rydd RF-1022-post for mappede kontoer."
            elif needs_control_group:
                next_action = "Tildel RF-1022-post i Saldobalanse."
            else:
                next_action = "Fullfor lonnsflagg i Saldobalanse."
        elif has_explicit_mapping and best_row is not None and reconcile_status != "OK":
            guided_status = "Har forslag"
            display_status = "Har forslag"
            recommended = "Se forslag"
            guided_next = "Se forslag"
            next_action = suggestion_guardrail_reason or "Se forslag for valgt kode."
        elif has_explicit_mapping:
            guided_status = "Kontroller kobling"
            display_status = "Kontroller kobling"
            recommended = "Kontroller kobling"
            guided_next = "Kontroller kobling"
            next_action = "Kontroller dagens kobling."
        else:
            guided_status = "Maa avklares"
            display_status = "Maa avklares"
            recommended = "Kontroller kobling"
            guided_next = "Kontroller kobling"
            next_action = "Velg koblinger eller vurder forslag."

        display_name = navn or code
        if code and navn and navn.casefold() != code.casefold():
            display_name = f"{navn} ({code})"

        rows.append(
            {
                "A07Post": display_name,
                "Kode": code,
                "Navn": navn,
                "AgaPliktig": _format_aga_pliktig(aga_value),
                "A07_Belop": row.get("Belop"),
                "GL_Belop": row.get("GL_Belop"),
                "Diff": row.get("Diff"),
                "AntallKontoer": row.get("AntallKontoer"),
                "Status": display_status,
                "DagensMapping": ", ".join(current_accounts),
                "Anbefalt": recommended,
                "Arbeidsstatus": work_status,
                "GuidetStatus": guided_status,
                "GuidetNeste": guided_next,
                "MatchingReady": matching_ready,
                "SuggestionGuardrail": suggestion_guardrail,
                "SuggestionGuardrailReason": suggestion_guardrail_reason,
                "CurrentMappingSuspicious": current_mapping_suspicious,
                "CurrentMappingSuspiciousReason": current_mapping_suspicious_reason,
                "Rf1022GroupId": rf1022_group_id,
                "WorkFamily": work_family,
                "ReconcileStatus": reconcile_status,
                "NesteHandling": next_action,
                "Locked": locked_flag,
                "Hvorfor": str(profile_state.get("why_summary") or "").strip(),
            }
        )

    out = pd.DataFrame(rows, columns=[*_CONTROL_COLUMNS, *_CONTROL_EXTRA_COLUMNS])
    if out.empty:
        return out

    status_priority = {
        "Mistenkelig kobling": 0,
        "Har forslag": 1,
        "Har historikk": 2,
        "Maa avklares": 3,
        "Lonnskontroll": 4,
        "Kontroller kobling": 5,
        "Ferdig": 6,
    }
    work_status = out.get("GuidetStatus", pd.Series(index=out.index, dtype="object")).fillna("").astype(str)
    diff_abs = pd.to_numeric(out.get("Diff"), errors="coerce").abs()
    a07_abs = pd.to_numeric(out.get("A07_Belop"), errors="coerce").abs()
    belop_abs = diff_abs.where(diff_abs.notna() & diff_abs.ne(0), a07_abs).fillna(0)
    sort_df = out.assign(_status_priority=work_status.map(status_priority).fillna(9), _belop_abs=belop_abs)
    sort_df = sort_df.sort_values(
        by=["_status_priority", "_belop_abs", "Kode"],
        ascending=[True, False, True],
        kind="stable",
    )
    return sort_df.drop(columns=["_status_priority", "_belop_abs"], errors="ignore").reset_index(drop=True)

