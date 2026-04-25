"""Associate case actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    simpledialog = None  # type: ignore
    messagebox = None  # type: ignore

from ..backend import storage
from ..backend.models import AssociateAdjustmentRow, AssociateCase
from .associate_state import _build_case_from_form, _parse_float, _parse_int, clear_associate_case_form, current_associate_case, populate_associate_case_form, refresh_associate_adjustment_tree, refresh_associate_case_actions, refresh_associate_case_tree, refresh_associate_case_views

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def on_new_associate_case(page: "ConsolidationPage") -> None:
    if page._project is None:
        page._ensure_project()
    if page._project is None:
        return
    name = simpledialog.askstring("Ny tilknyttet", "Navn på tilknyttet selskap:")
    if not name:
        return
    proj_defaults = getattr(page._project, "default_associate_line_mapping", None) or {}
    case = AssociateCase(name=name.strip())
    if proj_defaults:
        merged = dict(case.line_mapping)
        merged.update(proj_defaults)
        case.line_mapping = merged
    if len(page._project.companies) == 1:
        case.investor_company_id = page._project.companies[0].company_id
    page._project.associate_cases.append(case)
    storage.save_project(page._project)
    refresh_associate_case_tree(page)
    page._tree_associate_cases.selection_set(case.case_id)
    page._tree_associate_cases.focus(case.case_id)
    populate_associate_case_form(page, case)


def on_associate_case_selected(page: "ConsolidationPage", _event=None) -> None:
    if page._project is None:
        return
    sel = page._tree_associate_cases.selection()
    if not sel:
        clear_associate_case_form(page)
        return
    case = page._project.find_associate_case(sel[0])
    if case is not None:
        populate_associate_case_form(page, case)


def on_save_associate_case(page: "ConsolidationPage") -> None:
    if page._project is None:
        page._ensure_project()
    if page._project is None:
        return
    try:
        existing = current_associate_case(page)
        if existing is None:
            existing = AssociateCase()
            page._project.associate_cases.append(existing)
        case = _build_case_from_form(page, existing=existing)
        from ..backend.associate_equity_method import mark_associate_case_stale

        mark_associate_case_stale(case, page._project)
        storage.save_project(page._project)
        refresh_associate_case_tree(page)
        page._update_status()
        populate_associate_case_form(page, case)
    except Exception as exc:
        messagebox.showerror("Tilknyttet sak", str(exc))


def on_delete_associate_case(page: "ConsolidationPage") -> None:
    if page._project is None:
        return
    case = current_associate_case(page)
    if case is None:
        return
    if not messagebox.askyesno("Slett tilknyttet", f"Slett '{case.name}'?"):
        return
    from ..backend.associate_equity_method import delete_associate_case

    delete_associate_case(case.case_id, page._project)
    storage.save_project(page._project)
    refresh_associate_case_tree(page)
    page._refresh_simple_elim_tree()
    page._refresh_journal_tree()
    clear_associate_case_form(page)
    page._update_status()
    page._clear_preview()
    page._rerun_consolidation()


def on_generate_associate_journal(page: "ConsolidationPage") -> None:
    if page._project is None:
        page._ensure_project()
    if page._project is None:
        return
    on_save_associate_case(page)
    case = current_associate_case(page)
    if case is None:
        return
    try:
        from ..backend.associate_equity_method import sync_associate_case_journal

        journal = sync_associate_case_journal(case, page._project)
        storage.save_project(page._project)
        refresh_associate_case_tree(page)
        populate_associate_case_form(page, case)
        page._refresh_simple_elim_tree()
        page._refresh_journal_tree()
        page._update_status()
        try:
            page._tree_journals.selection_set((journal.journal_id,))
            page._tree_journals.focus(journal.journal_id)
        except Exception:
            pass
        page._clear_preview()
        page._rerun_consolidation()
    except Exception as exc:
        logger.exception("Associate journal generation failed")
        messagebox.showerror("EK-metode", str(exc))


def on_open_associate_journal(page: "ConsolidationPage") -> None:
    case = current_associate_case(page)
    if case is None or page._project is None or not case.journal_id:
        return
    journal = page._project.find_journal(case.journal_id)
    if journal is None:
        return
    page._select_left_tab(1, "_left_tab_elim")
    page._select_elim_tab(1, "_elim_tab_journals")
    try:
        page._tree_journals.selection_set((journal.journal_id,))
        page._tree_journals.focus(journal.journal_id)
        page._refresh_elim_lines(journal)
    except Exception:
        pass


def open_associate_case_by_id(page: "ConsolidationPage", case_id: str) -> None:
    if page._project is None or not hasattr(page, "_tree_associate_cases"):
        return
    case = page._project.find_associate_case(case_id)
    if case is None:
        return
    page._select_left_tab(1, "_left_tab_elim")
    page._select_elim_tab(4, "_elim_tab_associates")
    page._tree_associate_cases.selection_set((case.case_id,))
    page._tree_associate_cases.focus(case.case_id)
    populate_associate_case_form(page, case)


def on_add_associate_adjustment(page: "ConsolidationPage") -> None:
    raw = simpledialog.askstring(
        "Ny justering",
        "Label ; Beløp ; Motpost regnr ; Beskrivelse\nEksempel: Emisjon ; 25000 ; 695 ; Kapitalendring",
    )
    if not raw:
        return
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) < 3:
        messagebox.showwarning("Justering", "Skriv minst: Label ; Beløp ; Motpost regnr")
        return
    try:
        row = AssociateAdjustmentRow(
            label=parts[0],
            amount=_parse_float(parts[1]),
            offset_regnr=_parse_int(parts[2]),
            description=parts[3] if len(parts) > 3 else "",
        )
    except Exception as exc:
        messagebox.showerror("Justering", str(exc))
        return
    page._associate_manual_rows.append(row)
    refresh_associate_adjustment_tree(page)


def on_edit_associate_adjustment(page: "ConsolidationPage") -> None:
    sel = page._tree_associate_adjustments.selection()
    if not sel:
        return
    row = next((item for item in page._associate_manual_rows if item.row_id == sel[0]), None)
    if row is None:
        return
    raw = simpledialog.askstring(
        "Rediger justering",
        "Label ; Beløp ; Motpost regnr ; Beskrivelse",
        initialvalue=f"{row.label} ; {row.amount} ; {row.offset_regnr} ; {row.description}",
    )
    if not raw:
        return
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) < 3:
        return
    row.label = parts[0]
    row.amount = _parse_float(parts[1])
    row.offset_regnr = _parse_int(parts[2])
    row.description = parts[3] if len(parts) > 3 else ""
    refresh_associate_adjustment_tree(page)


def on_delete_associate_adjustment(page: "ConsolidationPage") -> None:
    sel = page._tree_associate_adjustments.selection()
    if not sel:
        return
    page._associate_manual_rows = [row for row in page._associate_manual_rows if row.row_id != sel[0]]
    refresh_associate_adjustment_tree(page)
