"""TB and client-list import helpers for consolidation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from consolidation.models import CompanyTB

from page_consolidation_import_finalize import ensure_line_import_config, finalize_import, finalize_line_basis_import

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage

logger = logging.getLogger(__name__)


def _is_line_basis_company(company: object | None) -> bool:
    if company is None:
        return False
    return str(getattr(company, "basis_type", "tb") or "tb").strip().lower() == "regnskapslinje"


def _load_active_client_trial_balance(
    client_display: str,
    *,
    year: str,
    silent: bool,
    messagebox_module,
) -> tuple[pd.DataFrame, object, Path] | None:
    chosen_client = str(client_display or "").strip()
    if not chosen_client or not year:
        return None

    try:
        import client_store

        version = client_store.get_active_version(chosen_client, year=year, dtype="sb")
    except Exception as exc:
        if not silent:
            messagebox_module.showerror(
                "Klientliste",
                f"Kunne ikke hente aktiv saldobalanse for {chosen_client}:\n{exc}",
            )
        return None

    version_path = str(getattr(version, "path", "") or "").strip() if version is not None else ""
    if not version_path:
        if not silent:
            messagebox_module.showinfo(
                "Klientliste",
                f"Fant ingen aktiv saldobalanse for {chosen_client} i {year}.",
            )
        return None

    try:
        from trial_balance_reader import read_trial_balance

        tb_df = read_trial_balance(version_path)
    except Exception as exc:
        logger.exception("Kunne ikke lese aktiv SB fra klientliste")
        if not silent:
            messagebox_module.showerror(
                "Klientliste",
                f"Kunne ikke lese aktiv saldobalanse for {chosen_client}:\n{exc}",
            )
        return None

    return tb_df, version, Path(version_path)


def find_company_by_name(page: "ConsolidationPage", name: str) -> CompanyTB | None:
    if page._project is None:
        return None
    normalized = str(name or "").strip().casefold()
    if not normalized:
        return None
    for company in page._project.companies:
        if str(company.name or "").strip().casefold() == normalized:
            return company
    return None


def on_import_selected_company_from_client_list(
    page: "ConsolidationPage",
    *,
    storage_module,
    tb_import_module,
    simpledialog_module,
    messagebox_module,
) -> None:
    if page._project is None:
        return
    sel = page._tree_companies.selection()
    if not sel:
        return
    company = page._project.find_company(sel[0])
    if company is None:
        return
    import_company_from_client_list(
        page,
        target_company=company,
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        simpledialog_module=simpledialog_module,
        messagebox_module=messagebox_module,
    )


def on_import_company_from_client_list(
    page: "ConsolidationPage",
    *,
    storage_module,
    tb_import_module,
    simpledialog_module,
    messagebox_module,
) -> None:
    import_company_from_client_list(
        page,
        target_company=None,
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        simpledialog_module=simpledialog_module,
        messagebox_module=messagebox_module,
    )


def import_company_from_client_list(
    page: "ConsolidationPage",
    *,
    target_company: CompanyTB | None = None,
    storage_module,
    tb_import_module,
    simpledialog_module,
    messagebox_module,
) -> None:
    proj = page._ensure_project()
    year = str(proj.year or "").strip()
    if not year:
        messagebox_module.showinfo("Klientliste", "Velg aar for du importerer fra klientlisten.")
        return

    try:
        import client_store

        clients = client_store.list_clients()
    except Exception as exc:
        messagebox_module.showerror("Klientliste", f"Kunne ikke lese klientlisten:\n{exc}")
        return

    if not clients:
        messagebox_module.showinfo("Klientliste", "Fant ingen klienter i klientlisten.")
        return

    try:
        from client_picker_dialog import open_client_picker
    except Exception as exc:
        messagebox_module.showerror("Klientliste", f"Kunne ikke apne klientvelger:\n{exc}")
        return

    try:
        from client_meta_index import get_index

        client_meta = get_index()
    except Exception:
        client_meta = None

    initial_selection = str(target_company.name if target_company is not None else proj.client or "").strip()
    chosen_client = open_client_picker(
        page,
        clients,
        client_meta=client_meta,
        initial_query="",
        initial_selection=initial_selection or None,
        title=f"Velg klient med aktiv saldobalanse ({year})",
        show_mine_filter=True,
    )
    if not chosen_client:
        return

    loaded = _load_active_client_trial_balance(
        chosen_client,
        year=year,
        silent=False,
        messagebox_module=messagebox_module,
    )
    if loaded is None:
        return
    tb_df, version, resolved_path = loaded

    default_name = str(target_company.name if target_company is not None else chosen_client).strip() or str(chosen_client)
    name = simpledialog_module.askstring(
        "Importer fra klientliste",
        "Selskapsnavn i konsolideringen:",
        initialvalue=default_name,
    )
    if not name:
        return

    existing_company = target_company or find_company_by_name(page, name)
    finalize_import(
        page,
        tb_df,
        name,
        resolved_path,
        existing_company=existing_company,
        source_type="client_store_sb",
        source_file=str(getattr(version, "filename", "") or resolved_path.name),
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        messagebox_module=messagebox_module,
    )


def import_company_from_client_name(
    page: "ConsolidationPage",
    client_display: str,
    *,
    target_company_name: str | None = None,
    target_company: CompanyTB | None = None,
    silent: bool = False,
    storage_module,
    tb_import_module,
    messagebox_module,
) -> CompanyTB | None:
    proj = page._ensure_project()
    year = str(proj.year or "").strip()
    chosen_client = str(client_display or "").strip()
    if not chosen_client or not year:
        return None

    loaded = _load_active_client_trial_balance(
        chosen_client,
        year=year,
        silent=silent,
        messagebox_module=messagebox_module,
    )
    if loaded is None:
        return None
    tb_df, version, resolved_path = loaded

    name = str(target_company_name or chosen_client).strip() or chosen_client
    existing_company = target_company or find_company_by_name(page, name)
    return finalize_import(
        page,
        tb_df,
        name,
        resolved_path,
        existing_company=existing_company,
        source_type="client_store_sb",
        source_file=str(getattr(version, "filename", "") or resolved_path.name),
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        messagebox_module=messagebox_module,
    )


def import_companies_from_ar_batch(
    page: "ConsolidationPage",
    rows: list[dict[str, Any]],
    *,
    storage_module,
    tb_import_module,
    messagebox_module,
) -> list[CompanyTB | None]:
    results: list[CompanyTB | None] = []
    for row in rows:
        matched_client = str(row.get("matched_client") or "").strip()
        has_sb = bool(row.get("has_active_sb"))
        if not matched_client or not has_sb:
            results.append(None)
            continue
        try:
            company = import_company_from_client_name(
                page,
                matched_client,
                target_company_name=str(row.get("company_name") or matched_client).strip() or matched_client,
                silent=True,
                storage_module=storage_module,
                tb_import_module=tb_import_module,
                messagebox_module=messagebox_module,
            )
            results.append(company)
        except Exception:
            logger.exception("Batch-import feilet for %s", matched_client)
            results.append(None)
    return results


def on_reimport_company(
    page: "ConsolidationPage",
    *,
    filedialog_module,
    simpledialog_module,
    messagebox_module,
    storage_module,
    tb_import_module,
) -> None:
    sel = page._tree_companies.selection()
    if not sel or page._project is None:
        return
    company = page._project.find_company(sel[0])
    if company is None:
        return

    if _is_line_basis_company(company):
        if company.source_type == "pdf_regnskap":
            path = filedialog_module.askopenfilename(
                title=f"Reimporter PDF-regnskap for {company.name}",
                filetypes=[("PDF", "*.pdf"), ("Alle filer", "*.*")],
            )
            if not path:
                return
            if not ensure_line_import_config(page, messagebox_module=messagebox_module):
                return
            assert page._regnskapslinjer is not None
            from consolidation.pdf_line_suggestions import suggest_line_basis_from_pdf
            from consolidation_pdf_review_dialog import review_pdf_line_suggestions

            try:
                suggestions = suggest_line_basis_from_pdf(path, regnskapslinjer=page._regnskapslinjer)
            except Exception as exc:
                messagebox_module.showerror("PDF-importfeil", str(exc))
                return
            approved = review_pdf_line_suggestions(page, suggestions)
            if approved is None or approved.empty:
                return
            finalize_line_basis_import(
                page,
                approved,
                company.name,
                Path(path),
                source_type="pdf_regnskap",
                existing_company=company,
                storage_module=storage_module,
                messagebox_module=messagebox_module,
            )
            return

        path = filedialog_module.askopenfilename(
            title=f"Reimporter regnskapslinjer for {company.name}",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("Alle filer", "*.*")],
        )
        if not path:
            return
        if not ensure_line_import_config(page, messagebox_module=messagebox_module):
            return
        assert page._regnskapslinjer is not None
        from consolidation.line_basis_import import import_company_line_basis

        try:
            df, _warnings = import_company_line_basis(path, regnskapslinjer=page._regnskapslinjer)
        except Exception as exc:
            messagebox_module.showerror("Importfeil", str(exc))
            return

        finalize_line_basis_import(
            page,
            df,
            company.name,
            Path(path),
            source_type="rl_excel" if Path(path).suffix.lower() in (".xlsx", ".xlsm", ".xls") else "rl_csv",
            existing_company=company,
            storage_module=storage_module,
            messagebox_module=messagebox_module,
        )
        return

    if str(getattr(company, "source_type", "") or "").strip().lower() == "client_store_sb":
        import_company_from_client_list(
            page,
            target_company=company,
            storage_module=storage_module,
            tb_import_module=tb_import_module,
            simpledialog_module=simpledialog_module,
            messagebox_module=messagebox_module,
        )
        return

    path = filedialog_module.askopenfilename(
        title=f"Reimporter TB for {company.name}",
        filetypes=[
            ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
            ("Alle filer", "*.*"),
        ],
    )
    if not path:
        return

    suffix = Path(path).suffix.lower()
    if suffix in (".xml", ".zip"):
        try:
            _, df, warnings = tb_import_module.import_company_tb(path, company.name)
        except Exception as exc:
            messagebox_module.showerror("Importfeil", str(exc))
            return
        finalize_import(
            page,
            df,
            company.name,
            Path(path),
            existing_company=company,
            storage_module=storage_module,
            tb_import_module=tb_import_module,
            messagebox_module=messagebox_module,
        )
        if warnings:
            messagebox_module.showwarning("Import-advarsler", "\n".join(warnings))
        return

    try:
        from tb_preview_dialog import open_tb_preview

        result = open_tb_preview(page, path, initial_name=company.name)
    except Exception as exc:
        messagebox_module.showerror("Feil", f"Forhandsvisning feilet:\n{exc}")
        return
    if result is None:
        return

    df, _name = result
    from consolidation.tb_import import _normalize_columns

    finalize_import(
        page,
        _normalize_columns(df),
        company.name,
        Path(path),
        existing_company=company,
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        messagebox_module=messagebox_module,
    )


def on_import_company(
    page: "ConsolidationPage",
    *,
    filedialog_module,
    simpledialog_module,
    messagebox_module,
    storage_module,
    tb_import_module,
) -> None:
    path = filedialog_module.askopenfilename(
        title="Importer saldobalanse",
        filetypes=[
            ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
            ("Alle filer", "*.*"),
        ],
    )
    if not path:
        return

    suffix = Path(path).suffix.lower()
    if suffix in (".xml", ".zip"):
        import_saft_direct(
            page,
            path,
            simpledialog_module=simpledialog_module,
            messagebox_module=messagebox_module,
            tb_import_module=tb_import_module,
            storage_module=storage_module,
        )
        return

    try:
        from tb_preview_dialog import open_tb_preview

        result = open_tb_preview(page, path, initial_name=Path(path).stem)
    except Exception as exc:
        logger.exception("Preview dialog failed")
        messagebox_module.showerror("Feil", f"Kunne ikke apne forhandsvisning:\n{exc}")
        return

    if result is None:
        return

    df, name = result
    finalize_import(
        page,
        df,
        name,
        Path(path),
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        messagebox_module=messagebox_module,
    )


def import_saft_direct(
    page: "ConsolidationPage",
    path: str,
    *,
    simpledialog_module,
    messagebox_module,
    tb_import_module,
    storage_module,
) -> None:
    name = simpledialog_module.askstring(
        "Selskapsnavn",
        "Skriv inn selskapsnavn:",
        initialvalue=Path(path).stem,
    )
    if not name:
        return

    try:
        _company, df, warnings = tb_import_module.import_company_tb(path, name)
    except Exception as exc:
        messagebox_module.showerror("Importfeil", str(exc))
        return

    finalize_import(
        page,
        df,
        name,
        Path(path),
        storage_module=storage_module,
        tb_import_module=tb_import_module,
        messagebox_module=messagebox_module,
    )
    if warnings:
        messagebox_module.showwarning("Import-advarsler", "\n".join(warnings))

