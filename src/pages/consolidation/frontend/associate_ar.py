"""Associate AR/import helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

from ..backend import storage
from ..backend.models import AssociateCase
from .associate_actions import on_save_associate_case
from .associate_state import (
    _fmt_no,
    _parse_float,
    current_associate_case,
    populate_associate_case_form,
    refresh_associate_case_tree,
)

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def _apply_field_suggestions(page: "ConsolidationPage", suggestions: list[object], *, source_mode: str, source_ref: str) -> int:
    applied = 0
    field_vars = {
        "share_of_result": page._associate_result_var,
        "share_of_other_equity": page._associate_other_equity_var,
        "dividends": page._associate_dividends_var,
    }
    for suggestion in suggestions:
        var = field_vars.get(getattr(suggestion, "field_name", ""))
        if var is None:
            continue
        source_label = getattr(suggestion, "source_label", "") or getattr(suggestion, "field_label", "")
        source_page = getattr(suggestion, "source_page", None)
        page_text = f"\nSide: {source_page}" if source_page else ""
        yes = messagebox.askyesno(
            "Bruk forslag",
            f"{getattr(suggestion, 'field_label', '')}\n"
            f"Kilde: {source_label}{page_text}\n"
            f"Råverdi: {_fmt_no(float(getattr(suggestion, 'raw_amount', 0.0) or 0.0), 2)}\n"
            f"Andel: {_fmt_no(float(getattr(suggestion, 'share_amount', 0.0) or 0.0), 2)}\n"
            f"Treffscore: {_fmt_no(float(getattr(suggestion, 'confidence', 0.0) or 0.0) * 100.0, 0)}%",
        )
        if not yes:
            continue
        var.set(_fmt_no(float(getattr(suggestion, "share_amount", 0.0) or 0.0), 2))
        applied += 1
    if applied:
        page._associate_source_mode_var.set(source_mode)
        page._associate_source_ref_var.set(source_ref)
    return applied


def on_import_associate_line_support(page: "ConsolidationPage") -> None:
    case = current_associate_case(page)
    if case is None:
        messagebox.showinfo("Tilknyttet", "Opprett eller velg en tilknyttet sak først.")
        return
    if not page._ensure_line_import_config():
        return
    assert page._regnskapslinjer is not None
    path = filedialog.askopenfilename(
        title="Hent forslag fra regnskapslinjer",
        filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("Alle filer", "*.*")],
    )
    if not path:
        return
    from ..backend.associate_equity_method import suggest_associate_fields_from_line_basis
    from ..backend.line_basis_import import import_company_line_basis

    try:
        line_df, warnings = import_company_line_basis(path, regnskapslinjer=page._regnskapslinjer)
        suggestions = suggest_associate_fields_from_line_basis(
            line_df,
            ownership_pct=_parse_float(page._associate_ownership_var.get()),
        )
    except Exception as exc:
        messagebox.showerror("Tilknyttet", str(exc))
        return

    if not suggestions:
        messagebox.showwarning("Ingen forslag", "Fant ingen egnede EK-forslag i regnskapslinjene.")
        return
    applied = _apply_field_suggestions(
        page,
        suggestions,
        source_mode="line_basis",
        source_ref=Path(path).name,
    )
    if warnings:
        messagebox.showwarning("Import-advarsler", "\n".join(warnings))
    if applied:
        on_save_associate_case(page)


def on_import_associate_pdf_support(page: "ConsolidationPage") -> None:
    case = current_associate_case(page)
    if case is None:
        messagebox.showinfo("Tilknyttet", "Opprett eller velg en tilknyttet sak først.")
        return
    if not page._ensure_line_import_config():
        return
    assert page._regnskapslinjer is not None
    path = filedialog.askopenfilename(
        title="Hent forslag fra PDF-regnskap",
        filetypes=[("PDF", "*.pdf"), ("Alle filer", "*.*")],
    )
    if not path:
        return
    from ..backend.associate_equity_method import suggest_associate_fields_from_line_basis
    from ..backend.pdf_line_suggestions import suggest_line_basis_from_pdf

    try:
        line_df = suggest_line_basis_from_pdf(path, regnskapslinjer=page._regnskapslinjer)
        suggestions = suggest_associate_fields_from_line_basis(
            line_df,
            ownership_pct=_parse_float(page._associate_ownership_var.get()),
        )
    except Exception as exc:
        logger.exception("Associate PDF support failed")
        messagebox.showerror("Tilknyttet", str(exc))
        return

    if not suggestions:
        messagebox.showwarning("Ingen forslag", "Fant ingen egnede EK-forslag i PDF-en.")
        return
    applied = _apply_field_suggestions(
        page,
        suggestions,
        source_mode="pdf",
        source_ref=Path(path).name,
    )
    if applied:
        on_save_associate_case(page)


def create_or_update_associate_case_from_ar_relation(
    page: "ConsolidationPage",
    *,
    company_name: str,
    company_orgnr: str = "",
    ownership_pct: float = 0.0,
    matched_client: str = "",
    relation_type: str = "",
    source_ref: str = "",
    note: str = "",
) -> AssociateCase | None:
    proj = page._ensure_project()
    normalized_name = str(company_name or "").strip()
    if not normalized_name:
        messagebox.showwarning("AR", "Mangler selskapsnavn for tilknyttet-sak.")
        return None

    existing_case = None
    orgnr_marker = f"AR orgnr: {str(company_orgnr or '').strip()}"
    for case in proj.associate_cases:
        if company_orgnr and orgnr_marker in str(case.notes or ""):
            existing_case = case
            break
        if str(case.name or "").strip().casefold() == normalized_name.casefold():
            existing_case = case
            break

    case = existing_case or AssociateCase()
    if existing_case is None:
        proj.associate_cases.append(case)

    investor_company_id = proj.parent_company_id or ""
    if not investor_company_id and len(proj.companies) == 1:
        investor_company_id = proj.companies[0].company_id

    case.name = normalized_name
    if investor_company_id and not str(case.investor_company_id or "").strip():
        case.investor_company_id = investor_company_id
    case.ownership_pct = float(ownership_pct or 0.0)
    case.source_mode = "ar"
    relation_marker = f"AR relasjon: {relation_type}" if relation_type else ""
    client_marker = f"AR klientmatch: {matched_client}" if matched_client else ""
    extra_note = " | ".join(
        part
        for part in [
            orgnr_marker if company_orgnr else "",
            relation_marker,
            client_marker,
            str(note or "").strip(),
            str(source_ref or "").strip(),
        ]
        if part
    )
    case.notes = extra_note or case.notes

    from ..backend.associate_equity_method import mark_associate_case_stale

    mark_associate_case_stale(case, proj)
    storage.save_project(proj)
    refresh_associate_case_tree(page)
    page._refresh_simple_elim_tree()
    page._refresh_journal_tree()
    page._update_status()
    if hasattr(page, "_tree_associate_cases"):
        try:
            page._select_left_tab(1, "_left_tab_elim")
            page._select_elim_tab(4, "_elim_tab_associates")
            page._tree_associate_cases.selection_set((case.case_id,))
            page._tree_associate_cases.focus(case.case_id)
        except Exception:
            pass
    try:
        populate_associate_case_form(page, case)
    except Exception:
        pass
    return case


def on_open_selected_associate_from_journal(page: "ConsolidationPage") -> None:
    sel = page._tree_journals.selection()
    if not sel or page._project is None:
        return
    journal = page._project.find_journal(sel[0])
    if journal is None:
        return
    case_id = str(getattr(journal, "source_associate_case_id", "") or "").strip()
    if not case_id:
        messagebox.showinfo("Journal", "Valgt bilag er ikke koblet til en tilknyttet sak.")
        return
    from .associate_actions import open_associate_case_by_id

    open_associate_case_by_id(page, case_id)
