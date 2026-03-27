from __future__ import annotations

from typing import Any

import pandas as pd

import formatting
import regnskap_intelligence


def _show_message(messagebox: Any, fn_name: str, title: str, message: str, *, parent: Any = None) -> None:
    if messagebox is None:
        return
    try:
        fn = getattr(messagebox, fn_name, None)
        if callable(fn):
            if parent is not None:
                fn(title, message, parent=parent)
            else:
                fn(title, message)
    except Exception:
        pass


def _agg_mode(page: Any) -> str:
    try:
        var = getattr(page, "_var_aggregering", None)
        return str(var.get()) if var is not None else ""
    except Exception:
        return ""


def _current_client() -> str:
    try:
        import session

        return str(getattr(session, "client", None) or "").strip()
    except Exception:
        return ""


def _load_review_state(client: str) -> dict[str, dict[str, object]]:
    if not client:
        return {}
    try:
        import regnskap_client_overrides

        return regnskap_client_overrides.load_mapping_review_state(client)
    except Exception:
        return {}


def _save_review_state(client: str, konto: str, *, status: str, suggested_regnr: int | None = None, note: str = "") -> None:
    if not client or not konto:
        return
    try:
        import regnskap_client_overrides

        regnskap_client_overrides.set_mapping_review_state(
            client,
            konto,
            status=status,
            suggested_regnr=suggested_regnr,
            note=note,
        )
    except Exception:
        return


def _render_tree(tree: Any, rows: list[tuple[object, ...]]) -> None:
    if tree is None:
        return
    try:
        tree.delete(*tree.get_children(""))
    except Exception:
        pass
    for row in rows:
        try:
            tree.insert("", "end", values=row)
        except Exception:
            continue


def _map_regnskapslinje_label(regnr: object, regnskapslinje: object) -> str:
    nr_text = str(regnr or "").strip()
    name_text = str(regnskapslinje or "").strip()
    return f"{nr_text} {name_text}".strip()


def _load_current_overrides(client: str) -> dict[str, int]:
    if not client:
        return {}
    try:
        import regnskap_client_overrides
        import session as _session
        year = getattr(_session, "year", None) or ""
        return regnskap_client_overrides.load_account_overrides(
            client, year=str(year) if year else None)
    except Exception:
        return {}


def _merge_mapping_labels(mapped: pd.DataFrame, regnskapslinjer: pd.DataFrame | None) -> pd.DataFrame:
    out = mapped.copy()
    if regnskapslinjer is None or regnskapslinjer.empty:
        out["Regnskapslinje"] = ""
        return out

    try:
        from regnskap_mapping import normalize_regnskapslinjer

        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception:
        out["Regnskapslinje"] = ""
        return out

    labels = regn[["regnr", "regnskapslinje"]].copy()
    labels["regnr"] = labels["regnr"].astype(int)
    out = out.merge(labels, how="left", on="regnr")
    return out


def _build_account_mode_context(page: Any) -> dict[str, Any]:
    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty or "Konto" not in df_filtered.columns:
        return {"accounts_df": pd.DataFrame(), "summary": "Ingen kontoer valgt.", "selected_rows": [], "transactions_df": pd.DataFrame()}

    try:
        selected_accounts = list(page._get_selected_accounts())
    except Exception:
        selected_accounts = []

    if not selected_accounts:
        return {"accounts_df": pd.DataFrame(), "summary": "Ingen kontoer valgt.", "selected_rows": [], "transactions_df": pd.DataFrame()}

    work = df_filtered.loc[df_filtered["Konto"].astype(str).str.strip().isin([str(v).strip() for v in selected_accounts])].copy()
    if work.empty:
        return {"accounts_df": pd.DataFrame(), "summary": "Ingen kontoer i valgt scope.", "selected_rows": [], "transactions_df": pd.DataFrame()}

    rows = work[["Konto"]].copy()
    rows["Konto"] = rows["Konto"].astype(str)
    rows["_cnt"] = 1
    if "Beløp" in work.columns:
        rows["_belop"] = pd.to_numeric(work["Beløp"], errors="coerce").fillna(0.0)
    else:
        rows["_belop"] = 0.0
    rows["Kontonavn"] = work["Kontonavn"].fillna("").astype(str) if "Kontonavn" in work.columns else ""
    grouped = rows.groupby(["Konto", "Kontonavn"], as_index=False).agg(Antall=("_cnt", "sum"), Endring=("_belop", "sum"))

    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = getattr(page, "_rl_sb_df", None)
    if isinstance(sb_df, pd.DataFrame) and not sb_df.empty and "konto" in sb_df.columns:
        sb_work = sb_df.copy()
        sb_work["konto"] = sb_work["konto"].astype(str)
        sb_work["ib"] = pd.to_numeric(sb_work.get("ib"), errors="coerce").fillna(0.0)
        sb_work["ub"] = pd.to_numeric(sb_work.get("ub"), errors="coerce").fillna(0.0)
        sb_grouped = sb_work.groupby("konto", as_index=False).agg(IB=("ib", "sum"), UB=("ub", "sum"))
        grouped = grouped.merge(sb_grouped, how="left", left_on="Konto", right_on="konto")
        grouped["IB"] = grouped["IB"].fillna(0.0)
        grouped["UB"] = grouped["UB"].fillna(grouped["Endring"])
        grouped.drop(columns=["konto"], inplace=True, errors="ignore")
    else:
        grouped["IB"] = 0.0
        grouped["UB"] = grouped["Endring"]

    grouped["Nr"] = pd.NA
    grouped["Regnskapslinje"] = ""

    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    if intervals is not None:
        try:
            from regnskap_mapping import apply_account_overrides, apply_interval_mapping

            probe = pd.DataFrame({"konto": grouped["Konto"].astype(str).tolist()})
            mapped = apply_interval_mapping(probe, intervals, konto_col="konto").mapped
            overrides = _load_current_overrides(_current_client())
            mapped = apply_account_overrides(mapped, overrides, konto_col="konto")
            mapped = _merge_mapping_labels(mapped, regnskapslinjer)
            label_map = {
                str(row.konto): (int(row.regnr) if row.regnr == row.regnr else pd.NA, str(row.regnskapslinje or "").strip())
                for row in mapped.itertuples(index=False)
            }
            grouped["Nr"] = grouped["Konto"].map(lambda konto: label_map.get(str(konto), (pd.NA, ""))[0])
            grouped["Regnskapslinje"] = grouped["Konto"].map(lambda konto: label_map.get(str(konto), (pd.NA, ""))[1])
        except Exception:
            pass

    grouped = grouped[["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]].copy()
    grouped = grouped.sort_values("Konto", kind="mergesort", ignore_index=True)
    summary = (
        f"Valgte kontoer: {len(grouped.index)} | "
        f"IB: {formatting.fmt_amount(grouped['IB'].sum())} | "
        f"Endring: {formatting.fmt_amount(grouped['Endring'].sum())} | "
        f"UB: {formatting.fmt_amount(grouped['UB'].sum())}"
    )
    return {
        "accounts_df": grouped,
        "summary": summary,
        "selected_rows": [],
        "transactions_df": work,
    }


def _build_detail_context(page: Any) -> dict[str, Any]:
    if _agg_mode(page) == "Regnskapslinje":
        try:
            import page_analyse_rl

            return page_analyse_rl.build_selected_rl_detail_context(page=page)
        except Exception:
            return {"accounts_df": pd.DataFrame(), "summary": "Ingen regnskapslinje valgt.", "selected_rows": [], "transactions_df": pd.DataFrame()}
    return _build_account_mode_context(page)


def _selected_detail_account(page: Any) -> str:
    value = str(getattr(page, "_detail_selected_account", "") or "").strip()
    return value


def _set_selected_detail_account(page: Any, konto: str) -> None:
    setattr(page, "_detail_selected_account", str(konto or "").strip())


def get_selected_detail_account_row(page: Any) -> pd.Series | None:
    detail_df = getattr(page, "_detail_accounts_df", None)
    konto = _selected_detail_account(page)
    if not isinstance(detail_df, pd.DataFrame) or detail_df.empty or not konto:
        return None
    match = detail_df.loc[detail_df["Konto"].astype(str).str.strip() == konto]
    if match.empty:
        return None
    return match.iloc[0]


def _format_account_rows(detail_df: pd.DataFrame) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for row in detail_df.itertuples(index=False):
        rows.append(
            (
                str(row.Konto),
                str(row.Kontonavn),
                str(row.OppfortSom or ""),
                str(row.OppforerSegSom or ""),
                str(row.ForslattRL or ""),
                str(row.Confidence or ""),
                str(row.Review or ""),
                str(row.Avvik or ""),
                formatting.fmt_amount(float(row.IB or 0.0)),
                formatting.fmt_amount(float(row.Endring or 0.0)),
                formatting.fmt_amount(float(row.UB or 0.0)),
                formatting.format_int_no(int(row.Antall or 0)),
            )
        )
    return rows


def _render_suggestion_rows(page: Any) -> None:
    tree = getattr(page, "_detail_suggestion_tree", None)
    if tree is None:
        return

    row = get_selected_detail_account_row(page)
    if row is None:
        _render_tree(tree, [])
        try:
            getattr(page, "_detail_status_var").set("Velg en konto i detaljpanelet for å se forslag og avvik.")
        except Exception:
            pass
        return

    suggestions = getattr(page, "_detail_suggestions_by_account", {}) or {}
    profiles = getattr(page, "_detail_profiles_by_account", {}) or {}
    konto = str(row.get("Konto", "") or "").strip()
    suggestion = suggestions.get(konto)
    profile = profiles.get(konto)
    rows = regnskap_intelligence.build_suggestion_rows(suggestion, profile)
    _render_tree(tree, rows)

    status_parts: list[str] = []
    if suggestion is not None:
        status_parts.append(f"Forslag: {suggestion.confidence_label}")
        if suggestion.suggested_regnskapslinje:
            status_parts.append(suggestion.suggested_regnskapslinje)
    if profile is not None and profile.alerts:
        status_parts.append(regnskap_intelligence.summarize_alerts([alert.message for alert in profile.alerts]))
    try:
        getattr(page, "_detail_status_var").set(" | ".join(part for part in status_parts if part))
    except Exception:
        pass


def _restore_detail_selection(page: Any) -> None:
    tree = getattr(page, "_detail_accounts_tree", None)
    detail_df = getattr(page, "_detail_accounts_df", None)
    if tree is None or not isinstance(detail_df, pd.DataFrame):
        return

    selected_account = _selected_detail_account(page)
    item_to_focus = ""
    for item in tree.get_children(""):
        try:
            konto = str(tree.set(item, "Konto") or "").strip()
        except Exception:
            konto = ""
        if not konto:
            continue
        if selected_account and konto == selected_account:
            item_to_focus = item
            break
        if not selected_account and not item_to_focus:
            item_to_focus = item

    if not item_to_focus:
        _set_selected_detail_account(page, "")
        _render_suggestion_rows(page)
        return

    try:
        tree.selection_set(item_to_focus)
        tree.focus(item_to_focus)
        tree.see(item_to_focus)
    except Exception:
        pass

    try:
        konto = str(tree.set(item_to_focus, "Konto") or "").strip()
    except Exception:
        konto = ""
    _set_selected_detail_account(page, konto)
    _render_suggestion_rows(page)


def refresh_detail_panel(page: Any) -> None:
    tree = getattr(page, "_detail_accounts_tree", None)
    if tree is None:
        return

    context = _build_detail_context(page)
    base_accounts_df = context.get("accounts_df")
    if not isinstance(base_accounts_df, pd.DataFrame):
        base_accounts_df = pd.DataFrame()

    client = _current_client()
    review_state = _load_review_state(client)
    detail_df, suggestions, profiles = regnskap_intelligence.analyze_account_rows(
        base_accounts_df,
        df_all=getattr(page, "dataset", None),
        regnskapslinjer=getattr(page, "_rl_regnskapslinjer", None),
        review_state=review_state,
    )

    only_flagged = False
    try:
        only_flagged = bool(getattr(page, "_detail_only_flagged_var").get())
    except Exception:
        only_flagged = False
    if only_flagged and not detail_df.empty:
        detail_df = detail_df.loc[detail_df.apply(regnskap_intelligence.has_actionable_deviation, axis=1)].reset_index(drop=True)

    setattr(page, "_detail_accounts_df", detail_df)
    setattr(page, "_detail_suggestions_by_account", suggestions)
    setattr(page, "_detail_profiles_by_account", profiles)
    setattr(page, "_detail_context", context)

    _render_tree(tree, _format_account_rows(detail_df))
    summary = str(context.get("summary", "") or "").strip()
    if detail_df.empty:
        summary = summary or "Ingen detaljrader i valgt scope."
    try:
        getattr(page, "_detail_summary_var").set(summary)
    except Exception:
        pass
    _restore_detail_selection(page)


def on_detail_account_selected(page: Any, _event: Any = None) -> None:
    tree = getattr(page, "_detail_accounts_tree", None)
    if tree is None:
        return

    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    if not selection:
        _set_selected_detail_account(page, "")
        _render_suggestion_rows(page)
        try:
            page._refresh_transactions_view()
        except Exception:
            pass
        return

    item = selection[0]
    try:
        konto = str(tree.set(item, "Konto") or "").strip()
    except Exception:
        konto = ""
    _set_selected_detail_account(page, konto)
    _render_suggestion_rows(page)
    try:
        page._refresh_transactions_view()
    except Exception:
        pass


def focus_detail_panel(page: Any) -> bool:
    tree = getattr(page, "_detail_accounts_tree", None)
    if tree is None:
        return False
    refresh_detail_panel(page)
    try:
        tree.focus_set()
    except Exception:
        pass
    return True


def _refresh_after_mapping_change(page: Any) -> None:
    try:
        page._refresh_pivot()
    except Exception:
        pass
    try:
        if _agg_mode(page) == "Regnskapslinje":
            import page_analyse_rl

            regnr_values = [regnr for regnr, _ in page_analyse_rl.get_selected_rl_rows(page=page)]
            page._restore_rl_pivot_selection(regnr_values)
    except Exception:
        pass
    refresh_detail_panel(page)
    try:
        page._refresh_transactions_view()
    except Exception:
        pass


def open_mapping_dialog_for_selected_account(page: Any, *, messagebox: Any) -> None:
    row = get_selected_detail_account_row(page)
    if row is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Velg en konto i detaljpanelet først.", parent=page)
        return

    client = _current_client()
    if not client:
        _show_message(messagebox, "showerror", "Analyse-detaljer", "Ingen aktiv klient i sesjonen. Kan ikke lagre mapping.", parent=page)
        return

    try:
        from views_rl_account_drill import open_account_mapping_dialog
    except Exception as exc:
        _show_message(messagebox, "showerror", "Analyse-detaljer", f"Kunne ikke åpne mappingdialog.\n\n{exc}", parent=page)
        return

    open_account_mapping_dialog(
        page,
        client=client,
        konto=str(row.get("Konto", "") or "").strip(),
        kontonavn=str(row.get("Kontonavn", "") or "").strip(),
        current_regnr=row.get("Nr"),
        current_regnskapslinje=str(row.get("Regnskapslinje", "") or "").strip(),
        regnskapslinjer=getattr(page, "_rl_regnskapslinjer", None),
        on_saved=lambda *_a, **_k: _refresh_after_mapping_change(page),
        on_removed=lambda *_a, **_k: _refresh_after_mapping_change(page),
    )


def remove_override_for_selected_account(page: Any, *, messagebox: Any) -> None:
    row = get_selected_detail_account_row(page)
    if row is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Velg en konto i detaljpanelet først.", parent=page)
        return

    client = _current_client()
    konto = str(row.get("Konto", "") or "").strip()
    if not client or not konto:
        _show_message(messagebox, "showerror", "Analyse-detaljer", "Manglende klient eller konto for override.", parent=page)
        return

    try:
        import regnskap_client_overrides

        import session as _session
        year = getattr(_session, "year", None) or ""
        regnskap_client_overrides.remove_account_override(
            client, konto, year=str(year) if year else None)
    except Exception as exc:
        _show_message(messagebox, "showerror", "Analyse-detaljer", f"Kunne ikke fjerne override.\n\n{exc}", parent=page)
        return

    _refresh_after_mapping_change(page)


def apply_suggestion_for_selected_account(page: Any, *, messagebox: Any) -> None:
    row = get_selected_detail_account_row(page)
    if row is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Velg en konto i detaljpanelet først.", parent=page)
        return

    konto = str(row.get("Konto", "") or "").strip()
    suggestion = (getattr(page, "_detail_suggestions_by_account", {}) or {}).get(konto)
    client = _current_client()
    if suggestion is None or suggestion.suggested_regnr is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Fant ikke et konkret forslag å bruke for valgt konto.", parent=page)
        return
    if not client:
        _show_message(messagebox, "showerror", "Analyse-detaljer", "Ingen aktiv klient i sesjonen. Kan ikke lagre forslag.", parent=page)
        return

    approved = True
    if hasattr(messagebox, "askyesno"):
        try:
            approved = bool(
                messagebox.askyesno(
                    "Bruk forslag",
                    f"Bruk forslag for konto {konto}?\n\nNy regnskapslinje: {suggestion.suggested_regnskapslinje or suggestion.suggested_regnr}\n\n{suggestion.explanation}",
                    parent=page,
                )
            )
        except Exception:
            approved = True
    if not approved:
        return

    try:
        import regnskap_client_overrides

        import session as _session
        year = getattr(_session, "year", None) or ""
        regnskap_client_overrides.set_account_override(
            client, konto, int(suggestion.suggested_regnr),
            year=str(year) if year else None)
    except Exception as exc:
        _show_message(messagebox, "showerror", "Analyse-detaljer", f"Kunne ikke lagre forslaget.\n\n{exc}", parent=page)
        return

    _save_review_state(
        client,
        konto,
        status="accepted",
        suggested_regnr=suggestion.suggested_regnr,
        note=suggestion.explanation,
    )
    _refresh_after_mapping_change(page)


def reject_suggestion_for_selected_account(page: Any, *, messagebox: Any) -> None:
    row = get_selected_detail_account_row(page)
    if row is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Velg en konto i detaljpanelet først.", parent=page)
        return

    konto = str(row.get("Konto", "") or "").strip()
    suggestion = (getattr(page, "_detail_suggestions_by_account", {}) or {}).get(konto)
    client = _current_client()
    if not client:
        _show_message(messagebox, "showerror", "Analyse-detaljer", "Ingen aktiv klient i sesjonen. Kan ikke lagre vurderingen.", parent=page)
        return

    note = suggestion.explanation if suggestion is not None else "Forslag avvist fra Analyse."
    _save_review_state(
        client,
        konto,
        status="rejected",
        suggested_regnr=getattr(suggestion, "suggested_regnr", None),
        note=note,
    )
    refresh_detail_panel(page)


def explain_selected_account(page: Any, *, messagebox: Any) -> None:
    row = get_selected_detail_account_row(page)
    if row is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Velg en konto i detaljpanelet først.", parent=page)
        return

    konto = str(row.get("Konto", "") or "").strip()
    suggestion = (getattr(page, "_detail_suggestions_by_account", {}) or {}).get(konto)
    profile = (getattr(page, "_detail_profiles_by_account", {}) or {}).get(konto)
    if suggestion is None:
        _show_message(messagebox, "showinfo", "Analyse-detaljer", "Ingen forklaring tilgjengelig for valgt konto.", parent=page)
        return

    lines = [suggestion.explanation, ""]
    if profile is not None:
        lines.append(f"Oppført som: {_map_regnskapslinje_label(profile.current_regnr, profile.current_regnskapslinje)}")
        lines.append(f"Oppfører seg som: {suggestion.behavior_label}")
        if profile.observation.dominant_counterparty_groups:
            lines.append(f"Dominerende motposter: {', '.join(profile.observation.dominant_counterparty_groups)}")
        lines.append(f"Fortegn: {profile.observation.direction_label}")
        lines.append("")
    for evidence in suggestion.evidences:
        prefix = "+" if evidence.score >= 0 else "-"
        lines.append(f"{prefix} {evidence.signal}: {evidence.detail}")
    for alert in suggestion.alerts:
        lines.append(f"! {alert.severity}: {alert.message}")

    _show_message(messagebox, "showinfo", "Forklaring", "\n".join(lines).strip(), parent=page)


def selected_transaction_accounts(page: Any, default_accounts: list[str]) -> list[str]:
    selected_account = _selected_detail_account(page)
    if selected_account:
        return [selected_account]
    return list(default_accounts)


def _select_account_items(page: Any, accounts: list[str]) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    wanted = {str(account or "").strip() for account in accounts if str(account or "").strip()}
    if not wanted:
        return

    items_to_select: list[str] = []
    for item in tree.get_children(""):
        try:
            konto = str(tree.set(item, "Konto") or "").strip()
        except Exception:
            konto = ""
        if konto in wanted:
            items_to_select.append(item)
    if not items_to_select:
        return
    try:
        tree.selection_set(items_to_select)
        tree.focus(items_to_select[0])
        tree.see(items_to_select[0])
    except Exception:
        pass


def jump_to_analysis_context(page: Any, context: dict[str, object] | None) -> None:
    if not isinstance(context, dict):
        return

    month_from = str(context.get("period_from") or "").strip()
    month_to = str(context.get("period_to") or "").strip()
    accounts = [str(value).strip() for value in (context.get("accounts") or []) if str(value).strip()]
    regnr_values = []
    for value in context.get("regnr_values") or []:
        try:
            regnr_values.append(int(value))
        except Exception:
            continue

    try:
        if month_from:
            getattr(page, "_var_date_from").set(month_from)
        if month_to:
            getattr(page, "_var_date_to").set(month_to)
    except Exception:
        pass

    try:
        page._apply_filters_now()
    except Exception:
        try:
            page._apply_filters_and_refresh()
        except Exception:
            pass

    if _agg_mode(page) == "Regnskapslinje" and regnr_values:
        try:
            page._restore_rl_pivot_selection(regnr_values)
        except Exception:
            pass
    elif accounts:
        _select_account_items(page, accounts)

    if len(accounts) == 1:
        _set_selected_detail_account(page, accounts[0])
    else:
        _set_selected_detail_account(page, "")

    refresh_detail_panel(page)
    try:
        page._refresh_transactions_view()
    except Exception:
        pass


__all__ = [
    "apply_suggestion_for_selected_account",
    "explain_selected_account",
    "focus_detail_panel",
    "get_selected_detail_account_row",
    "jump_to_analysis_context",
    "on_detail_account_selected",
    "open_mapping_dialog_for_selected_account",
    "refresh_detail_panel",
    "reject_suggestion_for_selected_account",
    "remove_override_for_selected_account",
    "selected_transaction_accounts",
]
