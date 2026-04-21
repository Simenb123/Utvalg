"""analyse_mapping_ui.py -- Kontomapping og problemkontoer.

Ekstrahert fra page_analyse.py.  Hver funksjon tar ``page`` (AnalysePage-instans)
som forste argument.
"""
from __future__ import annotations

from typing import Any, List, Optional


def _issue_for_account(page: Any, konto: str):
    target = str(konto or "").strip()
    if not target:
        return None
    for issue in getattr(page, "_mapping_issues", []) or []:
        if str(getattr(issue, "konto", "") or "").strip() == target:
            return issue
    return None


def refresh_mapping_issues(page: Any) -> None:
    try:
        import analyse_mapping_service
        issues = analyse_mapping_service.build_page_mapping_issues(page)
        problems = analyse_mapping_service.problem_mapping_issues(issues)
        summary = analyse_mapping_service.summarize_mapping_issues(issues)
        accounts = analyse_mapping_service.get_problem_accounts(issues)
    except Exception:
        issues = []
        problems = []
        summary = ""
        accounts = []
    page._mapping_issues = list(issues)
    page._mapping_problem_accounts = list(accounts)

    # Drift-deteksjon: konto med ulik RL år<->fjor, eller kun i ett år.
    drifts = _compute_mapping_drifts(page)
    page._mapping_drifts = list(drifts)
    drift_summary = ""
    if drifts:
        try:
            import rl_mapping_drift
            drift_summary = rl_mapping_drift.summary_text(drifts)
        except Exception:
            drift_summary = ""

    full_summary = str(summary or "")
    if drift_summary:
        full_summary = (full_summary + " | " + drift_summary).strip(" |") if full_summary else drift_summary
    page._mapping_warning = full_summary

    if getattr(page, "_mapping_warning_var", None) is not None:
        try:
            page._mapping_warning_var.set(page._mapping_warning)
        except Exception:
            pass
    update_mapping_warning_banner(page, problem_count=len(problems))


def _compute_mapping_drifts(page: Any) -> list:
    """Hent mapping-drift for gjeldende side. Returnerer tom liste ved feil."""
    try:
        import rl_mapping_drift
    except Exception:
        return []
    client = ""
    year: str | None = None
    try:
        import session as _session
        client = str(getattr(_session, "client", "") or "")
        _yv = getattr(_session, "year", None)
        year = str(_yv) if _yv else None
    except Exception:
        client = ""
        year = None
    if not client or not year:
        return []
    sb_df = getattr(page, "_rl_sb_df", None)
    sb_prev_df = getattr(page, "_rl_sb_prev_df", None)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    try:
        return rl_mapping_drift.detect_mapping_drift(
            client=client, year=year,
            sb_df=sb_df, sb_prev_df=sb_prev_df,
            intervals=intervals, regnskapslinjer=regnskapslinjer,
        )
    except Exception:
        return []


def show_mapping_drift_dialog(page: Any) -> None:
    """Åpne dialog som viser detaljert liste over mapping-drift."""
    drifts = getattr(page, "_mapping_drifts", None) or []
    if not drifts:
        return
    try:
        import rl_mapping_drift_dialog
        rl_mapping_drift_dialog.open_dialog(page, drifts)
    except Exception:
        pass


def update_mapping_warning_banner(page: Any, *, problem_count: Optional[int] = None) -> None:
    frame = getattr(page, "_mapping_banner_frame", None)
    if frame is None:
        return
    summary = str(getattr(page, "_mapping_warning", "") or "").strip()
    if problem_count is None:
        try:
            import analyse_mapping_service
            problem_count = len(
                analyse_mapping_service.problem_mapping_issues(
                    getattr(page, "_mapping_issues", []) or []
                )
            )
        except Exception:
            problem_count = 0
    try:
        if summary:
            frame.grid()
        else:
            frame.grid_remove()
    except Exception:
        pass

    selected_rows = get_selected_problem_account_rows(page)
    selected_issue = _issue_for_account(page, selected_rows[0][0]) if len(selected_rows) == 1 else None
    try:
        btn_show = getattr(page, "_btn_show_only_unmapped", None)
        if btn_show is not None:
            if problem_count:
                btn_show.state(["!disabled"])
            else:
                btn_show.state(["disabled"])
        btn_map = getattr(page, "_btn_map_selected_problem", None)
        if btn_map is not None:
            try:
                btn_map.configure(text="Map med forslag..." if getattr(selected_issue, "suggested_regnr", None) is not None else "Map valgt konto...")
            except Exception:
                pass
            if selected_rows:
                btn_map.state(["!disabled"])
            else:
                btn_map.state(["disabled"])
        btn_bulk = getattr(page, "_btn_bulk_map_problem", None)
        if btn_bulk is not None:
            try:
                btn_bulk.configure(text="Map valgte kontoer...")
            except Exception:
                pass
            if selected_rows:
                btn_bulk.state(["!disabled"])
            else:
                btn_bulk.state(["disabled"])
        btn_drift = getattr(page, "_btn_show_mapping_drift", None)
        if btn_drift is not None:
            drifts = getattr(page, "_mapping_drifts", None) or []
            try:
                if drifts:
                    btn_drift.state(["!disabled"])
                    btn_drift.grid()
                else:
                    btn_drift.state(["disabled"])
                    btn_drift.grid_remove()
            except Exception:
                pass
    except Exception:
        pass


def get_selected_problem_account_rows(page: Any) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    wanted = {str(v).strip() for v in getattr(page, "_mapping_problem_accounts", []) if str(v).strip()}
    if not wanted:
        return rows
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return rows
    try:
        selected = list(tree.selection())
    except Exception:
        selected = []
    if not selected:
        try:
            focused = tree.focus()
        except Exception:
            focused = ""
        if focused:
            selected = [focused]
    for item in selected:
        try:
            konto = str(tree.set(item, "Konto") or "").strip()
        except Exception:
            konto = ""
        if not konto or konto not in wanted:
            continue
        try:
            kontonavn = str(tree.set(item, "Kontonavn") or "").strip()
        except Exception:
            kontonavn = ""
        rows.append((konto, kontonavn))
    return rows


def focus_problem_account(page: Any, konto: str) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    target = str(konto or "").strip()
    if not target:
        return
    try:
        items = tree.get_children("")
    except Exception:
        items = ()
    for item in items:
        try:
            value = str(tree.set(item, "Konto") or "").strip()
        except Exception:
            value = ""
        if value != target:
            continue
        try:
            tree.selection_set((item,))
        except Exception:
            pass
        try:
            tree.focus(item)
        except Exception:
            pass
        try:
            tree.see(item)
        except Exception:
            pass
        break
    update_mapping_warning_banner(page)
    try:
        page._refresh_transactions_view()
    except Exception:
        pass


def show_only_unmapped_accounts(page: Any) -> None:
    try:
        page._var_aggregering.set("Saldobalanse")
    except Exception:
        pass
    try:
        if page._var_tx_view_mode is not None:
            page._var_tx_view_mode.set("Saldobalanse")
    except Exception:
        pass
    try:
        if page._var_show_only_unmapped is not None:
            page._var_show_only_unmapped.set(True)
    except Exception:
        pass
    try:
        page._refresh_pivot()
    except Exception:
        pass
    accounts = [str(v).strip() for v in getattr(page, "_mapping_problem_accounts", []) if str(v).strip()]
    if accounts:
        focus_problem_account(page, accounts[0])


def on_show_only_unmapped_changed(page: Any, _event: Any = None) -> None:
    try:
        if page._var_show_only_unmapped is not None and bool(page._var_show_only_unmapped.get()):
            page._var_aggregering.set("Saldobalanse")
    except Exception:
        pass
    try:
        page._refresh_pivot()
    except Exception:
        pass
    try:
        page._refresh_transactions_view()
    except Exception:
        pass


def map_selected_problem_account(page: Any) -> None:
    rows = get_selected_problem_account_rows(page)
    if not rows:
        return
    import page_analyse_sb

    konto, kontonavn = rows[0]
    page_analyse_sb.remap_sb_account(page=page, konto=konto, kontonavn=kontonavn)
    try:
        refresh_mapping_issues(page)
        page._refresh_pivot()
        focus_problem_account(page, konto)
    except Exception:
        pass


def bulk_map_selected_problem_accounts(page: Any) -> None:
    rows = get_selected_problem_account_rows(page)
    if not rows:
        return
    import page_analyse_sb

    page_analyse_sb._remap_multiple_sb_accounts(page=page, kontoer=rows)
    try:
        refresh_mapping_issues(page)
        page._refresh_pivot()
        if rows:
            focus_problem_account(page, rows[0][0])
    except Exception:
        pass
