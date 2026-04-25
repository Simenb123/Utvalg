"""page_consolidation_session.py - session/project loading helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import pandas as pd

from ..backend.models import CompanyTB, ConsolidationProject

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def _is_line_basis_company(company: object | None) -> bool:
    if company is None:
        return False
    return str(getattr(company, "basis_type", "tb") or "tb").strip().lower() == "regnskapslinje"


def _clear_project_ui(page: "ConsolidationPage") -> None:
    page._project = None
    getattr(page, "_company_tbs", {}).clear()
    getattr(page, "_company_line_bases", {}).clear()
    getattr(page, "_mapped_tbs", {}).clear()
    if hasattr(page, "_detail_meta_var"):
        page._detail_meta_var.set("")
    getattr(page, "_suggestions", {}).clear()

    for attr in (
        "_tree_companies",
        "_tree_journals",
        "_tree_elim_lines",
        "_tree_suggestions",
        "_tree_fx_rates",
        "_tree_associate_cases",
        "_tree_simple_elims",
        "_tree_elim_detail",
    ):
        tree = getattr(page, attr, None)
        if tree is None:
            continue
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass

    if hasattr(page, "_tree_draft_lines"):
        page._begin_new_elim_draft()
    if hasattr(page, "_associate_header_var"):
        page._clear_associate_case_form()


def refresh_from_session(
    page: "ConsolidationPage",
    sess: object,
    *,
    storage_module,
) -> None:
    if not page._tk_ok or page._status_var is None:
        return

    client = str(getattr(sess, "client", "") or "").strip()
    year = str(getattr(sess, "year", "") or "").strip()

    page._invalidate_run_cache()
    page._current_detail_cid = None
    page._show_empty_result("Kjør konsolidering for å vise resultat")

    if not client or not year:
        page._status_var.set("Velg klient og aar for aa starte.")
        page._project = None
        if hasattr(page, "_detail_meta_var"):
            page._detail_meta_var.set("")
        page._update_session_tb_button(sess)
        page._refresh_readiness()
        return

    page._lbl_statusbar.configure(text=f"Konsolidering | {client} / {year} | TB-only")

    proj = storage_module.load_project(client, year)
    if proj is not None:
        page._project = proj
        page._load_company_tbs()
        page._load_company_line_bases()
        page._compute_mapping_status()
        page._refresh_company_tree()
        page._refresh_simple_elim_tree()
        page._refresh_journal_tree()
        page._refresh_associate_case_tree()
        page._load_default_line_mapping_into_ui()
        page._clear_associate_case_form()
        page._begin_new_elim_draft()
        page._refresh_fx_tree()
        page._update_status()
    else:
        _clear_project_ui(page)
        page._status_var.set(
            f"{client} / {year} — ingen konsolideringsprosjekt. "
            "Importer et selskap for aa starte."
        )

    if page._project is None:
        page._refresh_readiness()
    page._update_session_tb_button(sess)


def ensure_project(
    page: "ConsolidationPage",
    *,
    session_module,
    storage_module,
) -> ConsolidationProject:
    if page._project is not None:
        return page._project

    client = str(getattr(session_module, "client", "") or "").strip()
    year = str(getattr(session_module, "year", "") or "").strip()
    if not client or not year:
        raise RuntimeError("Klient/aar er ikke valgt.")

    page._project = ConsolidationProject(client=client, year=year)
    storage_module.save_project(page._project)
    return page._project


def update_session_tb_button(page: "ConsolidationPage", _sess: object) -> None:
    has_data = page._resolve_active_client_tb() is not None

    already_parent = False
    if has_data and page._project is not None:
        parent_id = page._project.parent_company_id
        if parent_id:
            for company in page._project.companies:
                if company.company_id == parent_id and company.source_type in ("session", "session-sb"):
                    already_parent = True
                    break

    if has_data and not already_parent:
        page._btn_use_session_tb.pack(side="left", padx=(0, 4), before=page._btn_run)
    else:
        page._btn_use_session_tb.pack_forget()


def resolve_active_client_tb(
    _page: "ConsolidationPage",
    *,
    session_module,
) -> Optional[tuple[pd.DataFrame, str, str]]:
    client = str(getattr(session_module, "client", "") or "").strip()
    year = str(getattr(session_module, "year", "") or "").strip()
    if not client:
        return None

    tb = getattr(session_module, "tb_df", None)
    if tb is not None and isinstance(tb, pd.DataFrame) and not tb.empty:
        return tb, client, "session"

    if year:
        try:
            import client_store
            from trial_balance_reader import read_trial_balance

            versions = client_store.list_versions(client, year=year, dtype="sb")
            if versions:
                version = versions[0]
                sb_df = read_trial_balance(version.path)
                return sb_df, client, "session-sb"
        except Exception:
            logger.debug("Could not load SB from client_store", exc_info=True)

    return None


def on_use_session_tb(
    page: "ConsolidationPage",
    *,
    storage_module,
    simpledialog_module,
    messagebox_module,
) -> None:
    resolved = page._resolve_active_client_tb()
    if resolved is None:
        messagebox_module.showinfo(
            "Morselskap",
            "Ingen aktiv saldobalanse funnet.\n\n"
            "Last inn SAF-T eller velg SB-versjon for aktiv klient foerst.",
        )
        return

    tb, client_name, source_type = resolved
    proj = page._ensure_project()

    existing = None
    if proj.parent_company_id:
        for company in proj.companies:
            if company.company_id == proj.parent_company_id:
                existing = company
                break
    if existing is None:
        for company in proj.companies:
            if company.source_type in ("session", "session-sb"):
                existing = company
                break

    default_name = existing.name if existing is not None else client_name
    name = simpledialog_module.askstring(
        "Selskapsnavn (morselskap)",
        "Skriv inn selskapsnavn for morselskapet:",
        initialvalue=default_name,
    )
    if not name:
        return

    from ..backend.tb_import import _normalize_columns, validate_tb

    tb = _normalize_columns(tb.copy())
    warnings = validate_tb(tb)
    has_ib = bool((tb["ib"].abs() > 0.005).any()) if "ib" in tb.columns else False

    if existing is not None:
        existing.name = name
        existing.source_type = source_type
        existing.basis_type = "tb"
        existing.source_file = "aktiv klient" if source_type == "session" else "SAF-T SB"
        existing.row_count = len(tb)
        existing.has_ib = has_ib
        company_id = existing.company_id
    else:
        company = CompanyTB(
            name=name,
            source_type=source_type,
            basis_type="tb",
            source_file="aktiv klient" if source_type == "session" else "SAF-T SB",
            row_count=len(tb),
            has_ib=has_ib,
        )
        proj.companies.append(company)
        company_id = company.company_id

    proj.parent_company_id = company_id
    getattr(page, "_company_line_bases", {}).pop(company_id, None)
    storage_module.delete_company_line_basis(proj.client, proj.year, company_id)
    page._company_tbs[company_id] = tb
    storage_module.save_company_tb(proj.client, proj.year, company_id, tb)
    storage_module.save_project(proj)
    page._compute_mapping_status()
    page._refresh_company_tree()
    page._update_status()
    page._select_and_show_company(company_id)
    page._btn_use_session_tb.pack_forget()

    if warnings:
        messagebox_module.showwarning("Import-advarsler", "\n".join(warnings))


def load_company_tbs(page: "ConsolidationPage", *, storage_module) -> None:
    page._company_tbs.clear()
    if page._project is None:
        return

    from ..backend.tb_import import _normalize_columns

    for company in page._project.companies:
        if _is_line_basis_company(company):
            continue
        tb = storage_module.load_company_tb(
            page._project.client,
            page._project.year,
            company.company_id,
        )
        if tb is None:
            continue
        page._company_tbs[company.company_id] = _normalize_columns(tb)


def load_company_line_bases(page: "ConsolidationPage", *, storage_module) -> None:
    page._company_line_bases.clear()
    if page._project is None:
        return

    from ..backend.line_basis_import import normalize_company_line_basis

    for company in page._project.companies:
        if not _is_line_basis_company(company):
            continue
        basis = storage_module.load_company_line_basis(
            page._project.client,
            page._project.year,
            company.company_id,
        )
        if basis is not None:
            page._company_line_bases[company.company_id] = normalize_company_line_basis(basis)
