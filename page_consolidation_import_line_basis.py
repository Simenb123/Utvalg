"""Line-basis and PDF import helpers for consolidation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage


from page_consolidation_import_finalize import ensure_line_import_config, finalize_line_basis_import


def on_export_company_line_template(
    page: "ConsolidationPage",
    *,
    filedialog_module,
    messagebox_module,
) -> None:
    if not ensure_line_import_config(page, messagebox_module=messagebox_module):
        return
    assert page._regnskapslinjer is not None

    path = filedialog_module.asksaveasfilename(
        title="Eksporter regnskapslinje-mal",
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")],
        initialfile="regnskapslinje_mal.xlsx",
    )
    if not path:
        return

    from consolidation.line_basis_import import export_line_basis_template

    try:
        saved = export_line_basis_template(path, regnskapslinjer=page._regnskapslinjer)
        messagebox_module.showinfo("Mal eksportert", f"Lagret til:\n{saved}")
    except Exception as exc:
        messagebox_module.showerror("Eksportfeil", str(exc))


def on_import_company_lines(
    page: "ConsolidationPage",
    *,
    filedialog_module,
    simpledialog_module,
    messagebox_module,
    storage_module,
) -> None:
    if not ensure_line_import_config(page, messagebox_module=messagebox_module):
        return
    assert page._regnskapslinjer is not None

    path = filedialog_module.askopenfilename(
        title="Importer regnskapslinjer",
        filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("Alle filer", "*.*")],
    )
    if not path:
        return

    from consolidation.line_basis_import import import_company_line_basis

    try:
        df, _warnings = import_company_line_basis(path, regnskapslinjer=page._regnskapslinjer)
    except Exception as exc:
        messagebox_module.showerror("Importfeil", str(exc))
        return

    name = simpledialog_module.askstring(
        "Selskapsnavn",
        "Skriv inn selskapsnavn:",
        initialvalue=Path(path).stem,
    )
    if not name:
        return

    finalize_line_basis_import(
        page,
        df,
        name,
        Path(path),
        source_type="rl_excel" if Path(path).suffix.lower() in (".xlsx", ".xlsm", ".xls") else "rl_csv",
        storage_module=storage_module,
        messagebox_module=messagebox_module,
    )


def on_import_company_pdf(
    page: "ConsolidationPage",
    *,
    filedialog_module,
    simpledialog_module,
    messagebox_module,
    storage_module,
) -> None:
    if not ensure_line_import_config(page, messagebox_module=messagebox_module):
        return
    assert page._regnskapslinjer is not None

    path = filedialog_module.askopenfilename(
        title="Importer fra PDF-regnskap",
        filetypes=[("PDF", "*.pdf"), ("Alle filer", "*.*")],
    )
    if not path:
        return

    from consolidation.pdf_line_suggestions import suggest_line_basis_from_pdf
    from consolidation_pdf_review_dialog import review_pdf_line_suggestions

    try:
        suggestions = suggest_line_basis_from_pdf(path, regnskapslinjer=page._regnskapslinjer)
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("PDF-forslag feilet")
        messagebox_module.showerror("PDF-importfeil", str(exc))
        return

    if suggestions.empty:
        messagebox_module.showwarning("Ingen forslag", "Fant ingen regnskapslinjer med belop i PDF-en.")
        return

    approved = review_pdf_line_suggestions(page, suggestions)
    if approved is None or approved.empty:
        return

    name = simpledialog_module.askstring(
        "Selskapsnavn",
        "Skriv inn selskapsnavn:",
        initialvalue=Path(path).stem,
    )
    if not name:
        return

    finalize_line_basis_import(
        page,
        approved,
        name,
        Path(path),
        source_type="pdf_regnskap",
        storage_module=storage_module,
        messagebox_module=messagebox_module,
    )

