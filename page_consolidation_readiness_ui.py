"""page_consolidation_readiness_ui.py - readiness panel helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import consolidation_readiness as readiness

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage


def _reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def refresh_readiness(page: "ConsolidationPage") -> None:
    try:
        report = readiness.build_readiness_report(page)
        page._readiness_report = report
        page._readiness_status_var.set(readiness.summarize_report(report))
        summary_var = getattr(page, "_readiness_summary_var", None)
        if summary_var is not None:
            if report.issues:
                summary_var.set(
                    f"{report.blockers} blokkere | {report.warnings} advarsler | {report.infos} info"
                )
            else:
                summary_var.set("Ingen kontroller avdekket avvik.")
        page._refresh_controls_tree()
    except Exception:
        page._readiness_report = None
        try:
            page._readiness_status_var.set("")
        except Exception:
            pass


def refresh_controls_tree(page: "ConsolidationPage") -> None:
    tree = getattr(page, "_tree_controls", None)
    if tree is None:
        return

    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    report = getattr(page, "_readiness_report", None)
    issue_map: dict[str, object] = {}
    if report is None:
        page._readiness_issue_map = issue_map
        return

    for idx, issue in enumerate(getattr(report, "issues", []) or []):
        issue_id = f"issue:{idx}"
        issue_map[issue_id] = issue
        values = (
            getattr(issue, "severity", ""),
            getattr(issue, "category", ""),
            getattr(issue, "company_name", "") or getattr(issue, "company_id", "") or "Globalt",
            getattr(issue, "message", ""),
            getattr(issue, "action", ""),
        )
        tags = (str(getattr(issue, "severity", "") or ""),)
        tree.insert("", "end", iid=issue_id, values=values, tags=tags)
    page._readiness_issue_map = issue_map


def open_selected_readiness_issue(page: "ConsolidationPage") -> None:
    tree = getattr(page, "_tree_controls", None)
    if tree is None:
        return

    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    if not selection:
        try:
            focused = tree.focus()
        except Exception:
            focused = ""
        if focused:
            selection = [focused]
    if not selection:
        return

    issue = getattr(page, "_readiness_issue_map", {}).get(selection[0])
    if issue is None:
        return

    action = str(getattr(issue, "action", "") or "")
    company_id = str(getattr(issue, "company_id", "") or "")
    if action == "open_mapping":
        if company_id:
            page._select_and_show_company(company_id)
        page._show_company_detail(page._current_detail_cid or company_id)
        try:
            page._mapping_tab.show_unmapped()
        except Exception:
            pass
        page._select_right_tab(1, "_right_tab_mapping")
        return

    if action == "open_valuta":
        page._select_left_tab(1, "_left_tab_elim")
        try:
            page._select_elim_tab(3, "_elim_tab_fx")
        except Exception:
            pass
        if company_id:
            try:
                page._tree_fx_rates.selection_set((company_id,))
                page._tree_fx_rates.focus(company_id)
                page._tree_fx_rates.see(company_id)
            except Exception:
                pass
        return

    if action == "open_elimination":
        page._select_left_tab(1, "_left_tab_elim")
        try:
            page._select_elim_tab(1, "_elim_tab_journals")
        except Exception:
            pass
        target = str(getattr(issue, "action_target", "") or "")
        if target and getattr(page, "_tree_journals", None) is not None:
            try:
                page._tree_journals.selection_set((target,))
                page._tree_journals.focus(target)
                page._tree_journals.see(target)
                page._show_journal_lines()
            except Exception:
                pass
        return

    if action == "open_associate_case":
        target = str(getattr(issue, "action_target", "") or "")
        if target:
            page._open_associate_case_by_id(target)
        return

    if action == "open_grunnlag":
        if company_id:
            page._select_and_show_company(company_id)
        page._select_left_tab(2, "_left_tab_grunnlag")
        return

    if action == "rerun":
        try:
            page._select_right_tab(2, "_right_tab_result")
            page._rerun_consolidation()
        except Exception:
            pass
