"""Suggestion generation and suggestion list/detail helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    from tkinter import messagebox
except Exception:  # pragma: no cover
    messagebox = None  # type: ignore

from consolidation import storage
from consolidation.models import EliminationSuggestion
from consolidation.suggestions import (
    create_journal_from_suggestion,
    generate_suggestions,
    ignore_suggestion,
    unignore_suggestion,
)

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def _reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def _fmt_no(value: float, decimals: int = 0) -> str:
    if abs(value) < 0.005 and decimals == 0:
        return "0"
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}" if decimals > 0 else f"{round(abs(value)):,}"
    return sign + formatted.replace(",", " ").replace(".", ",")


_KIND_DISPLAY = {
    "intercompany": "Mellomværende",
    "interest": "Renter",
    "group_contribution": "Konsernbidrag",
    "investment_equity": "Investering/EK",
    "fx_difference": "Valutadiff",
}

_STATUS_DISPLAY = {"ny": "Ny", "ignorert": "Ignorert", "journalfoert": "Journalført"}


def on_generate_suggestions(page: "ConsolidationPage") -> None:
    if page._project is None or not page._mapped_tbs:
        messagebox.showinfo("Forslag", "Importer og map selskaper først.")
        return
    try:
        page._suggestions = generate_suggestions(page._project, page._mapped_tbs, page._regnr_to_name)
    except Exception as exc:
        logger.exception("Suggestion generation failed")
        messagebox.showerror("Feil", str(exc))
        return
    page._refresh_suggestion_tree()


def refresh_suggestion_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_suggestions
    _reset_sort_state(tree)
    _reset_sort_state(page._tree_suggestion_detail)
    tree.delete(*tree.get_children())
    page._tree_suggestion_detail.delete(*page._tree_suggestion_detail.get_children())

    name_map = {}
    parent_id = ""
    if page._project:
        name_map = {c.company_id: c.name for c in page._project.companies}
        parent_id = page._project.parent_company_id or ""

    show_all_pairs = page._show_all_pairs_var.get()
    selected_cid = ""
    try:
        sel = page._tree_companies.selection()
        if sel:
            selected_cid = sel[0]
    except Exception:
        pass

    allowed_kinds: set[str] = set()
    if page._sug_type_interco_var.get():
        allowed_kinds.add("intercompany")
    if page._sug_type_renter_var.get():
        allowed_kinds.add("interest")
    if page._sug_type_bidrag_var.get():
        allowed_kinds.add("group_contribution")
    if page._sug_type_invest_var.get():
        allowed_kinds.add("investment_equity")
    allowed_kinds.add("fx_difference")

    tolerance = page._project.match_tolerance_nok if page._project else 1000

    shown = 0
    for i, s in enumerate(page._suggestions):
        if s.kind not in allowed_kinds:
            continue

        if not show_all_pairs and parent_id:
            if s.company_a_id != parent_id and s.company_b_id != parent_id:
                continue
            if selected_cid and selected_cid != parent_id:
                other = s.company_b_id if s.company_a_id == parent_id else s.company_a_id
                if other != selected_cid:
                    continue

        shown += 1
        kind_text = _KIND_DISPLAY.get(s.kind, s.kind)
        status_text = _STATUS_DISPLAY.get(s.status, s.status)
        tags = (s.status,)
        if abs(s.diff_nok) > tolerance:
            tags = (s.status, "diff_warning")

        counterparty = name_map.get(s.company_b_id, s.company_b_id[:12])
        tree.insert(
            "",
            "end",
            iid=str(i),
            values=(
                kind_text,
                counterparty,
                s.line_name_a,
                s.line_name_b,
                _fmt_no(s.amount_a, 2),
                _fmt_no(s.amount_b, 2),
                _fmt_no(s.diff_nok, 2),
                status_text,
            ),
            tags=tags,
        )

    page._suggestion_count_var.set(f"{shown} forslag" if shown else "Ingen forslag for gjeldende filter")

    children = tree.get_children()
    if children:
        tree.selection_set(children[0])
        tree.see(children[0])
        page._on_suggestion_select()
    else:
        page._suggestion_detail_var.set("Ingen forslag for gjeldende filter.")
        page._clear_preview()


def on_suggestion_select(page: "ConsolidationPage", _event=None) -> None:
    sel = page._tree_suggestions.selection()
    if not sel:
        return
    try:
        idx = int(sel[0])
    except (ValueError, IndexError):
        return
    if idx < 0 or idx >= len(page._suggestions):
        return
    show_suggestion_detail(page, page._suggestions[idx])


def show_suggestion_detail(page: "ConsolidationPage", s: EliminationSuggestion) -> None:
    tree = page._tree_suggestion_detail
    tree.delete(*tree.get_children())

    name_map = {}
    if page._project:
        name_map = {c.company_id: c.name for c in page._project.companies}

    kind_text = _KIND_DISPLAY.get(s.kind, s.kind)
    page._suggestion_detail_var.set(
        f"{kind_text}: {s.line_name_a} / {s.line_name_b}  -  Diff: {_fmt_no(s.diff_nok, 2)} NOK"
    )

    for i, line in enumerate(s.journal_draft_lines):
        tree.insert(
            "",
            "end",
            iid=str(i),
            values=(line.regnr, name_map.get(line.company_id, line.company_id[:12]), _fmt_no(line.amount, 2), line.description),
        )

    page._compute_preview(s.journal_draft_lines)


def on_create_journal_from_suggestion(page: "ConsolidationPage") -> None:
    sel = page._tree_suggestions.selection()
    if not sel or page._project is None:
        return
    try:
        idx = int(sel[0])
    except (ValueError, IndexError):
        return
    if idx < 0 or idx >= len(page._suggestions):
        return

    s = page._suggestions[idx]
    if s.status == "journalfoert":
        messagebox.showinfo("Allerede opprettet", "Denne kandidaten har allerede en journal.")
        return

    journal = create_journal_from_suggestion(s, page._project)
    page._project.eliminations.append(journal)
    s.status = "journalfoert"
    storage.save_project(page._project)
    page._refresh_journal_tree()
    page._refresh_suggestion_tree()
    page._update_status()


def on_ignore_suggestion(page: "ConsolidationPage") -> None:
    sel = page._tree_suggestions.selection()
    if not sel or page._project is None:
        return
    try:
        idx = int(sel[0])
    except (ValueError, IndexError):
        return
    if idx < 0 or idx >= len(page._suggestions):
        return

    s = page._suggestions[idx]
    if s.status == "ignorert":
        unignore_suggestion(s.suggestion_key, page._project)
        s.status = "ny"
    else:
        ignore_suggestion(s.suggestion_key, page._project)
        s.status = "ignorert"

    storage.save_project(page._project)
    page._refresh_suggestion_tree()
