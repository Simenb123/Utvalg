"""Shared state/helpers for associate consolidation UI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from ..backend import storage
from ..backend.models import AssociateAdjustmentRow, AssociateCase

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
    if decimals > 0:
        formatted = f"{abs(value):,.{decimals}f}"
    else:
        formatted = f"{round(abs(value)):,}"
    formatted = formatted.replace(",", " ").replace(".", ",")
    return sign + formatted


def _normalize_entity_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _associate_case_status_label(case: AssociateCase | None, *, has_duplicate_company: bool = False) -> str:
    if case is None:
        return "Ingen sak valgt"
    if has_duplicate_company:
        return "Konflikt"
    status = str(getattr(case, "status", "") or "draft").strip().lower()
    if status == "generated":
        return "Klar"
    if status == "stale":
        return "Oppdater"
    return "Utkast"


def _parse_float(raw: object) -> float:
    text = str(raw or "").strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    return float(text)


def _parse_int(raw: object) -> int:
    text = str(raw or "").strip().replace(" ", "")
    if not text:
        return 0
    return int(float(text))


def _regnr_display(page: "ConsolidationPage", raw: object) -> str:
    regnr = _parse_int(raw)
    if regnr <= 0:
        return "-"
    name = page._regnr_to_name.get(regnr, "")
    return f"{regnr} {name}".strip()


def _refresh_mapping_summary(page: "ConsolidationPage") -> None:
    if not hasattr(page, "_associate_mapping_summary_var"):
        return
    default_mapping = {
        "investment_regnr": 575,
        "result_regnr": 100,
        "other_equity_regnr": 695,
        "retained_earnings_regnr": 705,
    }
    mapping_pairs = [
        ("investment_regnr", "Investering", page._associate_investment_regnr_var.get()),
        ("result_regnr", "Resultat", page._associate_result_regnr_var.get()),
        ("other_equity_regnr", "Andre EK", page._associate_other_equity_regnr_var.get()),
        ("retained_earnings_regnr", "Utbytte/disponering", page._associate_retained_regnr_var.get()),
    ]
    has_override = False
    for key, short_label, raw_value in mapping_pairs:
        regnr = _parse_int(raw_value)
        if regnr != int(default_mapping.get(key, 0)):
            has_override = True
        display = _regnr_display(page, raw_value)
        name_var = getattr(page, "_associate_mapping_name_vars", {}).get(key)
        if name_var is not None:
            name_var.set(f"{short_label}: {display}")
    if has_override:
        page._associate_mapping_summary_var.set(
            "Overstyrt mapping aktiv. Vis regnskapslinjer for detaljer eller nullstill til standard."
        )
    else:
        page._associate_mapping_summary_var.set(
            "Standard mapping aktiv. Du trenger normalt ikke å endre regnskapslinjene."
        )


def _set_mapping_visibility(page: "ConsolidationPage", visible: bool) -> None:
    page._associate_mapping_visible = bool(visible)
    if hasattr(page, "_associate_mapping_toggle_var"):
        page._associate_mapping_toggle_var.set("Skjul regnskapslinjer" if visible else "Vis regnskapslinjer")
    frame = getattr(page, "_associate_mapping_frame", None)
    if frame is None:
        return
    if visible:
        frame.grid()
    else:
        frame.grid_remove()


def on_toggle_associate_mapping(page: "ConsolidationPage") -> None:
    _set_mapping_visibility(page, not bool(getattr(page, "_associate_mapping_visible", False)))


def on_reset_associate_mapping(page: "ConsolidationPage") -> None:
    page._associate_investment_regnr_var.set("575")
    page._associate_result_regnr_var.set("100")
    page._associate_other_equity_regnr_var.set("695")
    page._associate_retained_regnr_var.set("705")
    _refresh_mapping_summary(page)


def _update_goodwill_display(page: "ConsolidationPage") -> None:
    from ..backend.associate_equity_method import _safe_float, compute_goodwill_amortization

    cost = _parse_float(getattr(page, "_associate_acq_cost_var", tk.StringVar()).get())
    net_assets = _parse_float(getattr(page, "_associate_net_assets_var", tk.StringVar()).get())
    years = max(_parse_int(getattr(page, "_associate_gw_years_var", tk.StringVar()).get()), 1)

    dummy = AssociateCase(
        acquisition_cost=cost,
        share_of_net_assets_at_acquisition=net_assets,
        goodwill_useful_life_years=years,
    )
    info = compute_goodwill_amortization(dummy)
    gw = info["goodwill"]
    annual = info["annual_amortization"]

    label = "Badwill" if gw < 0 else "Goodwill"
    page._associate_gw_computed_var.set(f"{label}: {_fmt_no(gw, 2)}")
    page._associate_gw_annual_var.set(_fmt_no(annual, 2))


def _on_compute_goodwill(page: "ConsolidationPage") -> None:
    _update_goodwill_display(page)


def _on_apply_goodwill_amortization(page: "ConsolidationPage") -> None:
    _update_goodwill_display(page)
    annual_text = page._associate_gw_annual_var.get().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        annual = abs(float(annual_text))
    except (ValueError, TypeError):
        annual = 0.0
    page._associate_excess_value_var.set(_fmt_no(annual, 2))


def _on_save_default_line_mapping(page: "ConsolidationPage") -> None:
    """Save the default line mapping to the project."""
    proj = getattr(page, "_project", None)
    if proj is None:
        return
    proj.default_associate_line_mapping = {
        "investment_regnr": _parse_int(page._default_investment_regnr_var.get()),
        "result_regnr": _parse_int(page._default_result_regnr_var.get()),
        "other_equity_regnr": _parse_int(page._default_other_equity_regnr_var.get()),
        "retained_earnings_regnr": _parse_int(page._default_retained_regnr_var.get()),
    }
    storage.save_project(proj)
    page._update_status()


def load_default_line_mapping_into_ui(page: "ConsolidationPage") -> None:
    """Load the project's default line mapping into the settings UI."""
    proj = getattr(page, "_project", None)
    defaults = getattr(proj, "default_associate_line_mapping", None) or {}
    if not hasattr(page, "_default_investment_regnr_var"):
        return
    page._default_investment_regnr_var.set(str(defaults.get("investment_regnr", 575)))
    page._default_result_regnr_var.set(str(defaults.get("result_regnr", 100)))
    page._default_other_equity_regnr_var.set(str(defaults.get("other_equity_regnr", 695)))
    page._default_retained_regnr_var.set(str(defaults.get("retained_earnings_regnr", 705)))


def _find_duplicate_company(page: "ConsolidationPage", case: AssociateCase | None):
    if case is None or page._project is None:
        return None
    normalized_case = _normalize_entity_name(case.name)
    if not normalized_case:
        return None
    for company in page._project.companies:
        if _normalize_entity_name(company.name) == normalized_case:
            return company
    return None


def _build_next_step_text(page: "ConsolidationPage", case: AssociateCase | None) -> str:
    if case is None:
        return (
            "Opprett saken fra AR eller med 'Ny sak'. Fyll deretter årets EK-bevegelser "
            "og generer EK-føring."
        )

    duplicate = _find_duplicate_company(page, case)
    if duplicate is not None:
        return (
            f"'{duplicate.name}' ligger også som vanlig selskap i konsolideringen. "
            "Velg enten fullkonsolidering eller EK-metoden for dette selskapet."
        )

    if not str(case.investor_company_id or "").strip():
        return "Velg investor før du går videre."
    if float(case.ownership_pct or 0.0) <= 0.0:
        return "Legg inn eierandel før EK-føringen kan genereres."

    status = str(case.status or "draft").strip().lower()
    if status == "generated":
        return "EK-føringen er oppdatert. Kjør konsolidering eller åpne journalen for kontroll."
    if status == "stale":
        return "Tallgrunnlaget er endret. Trykk 'Oppdater EK-føring' før du kjører konsolidering."
    return "Fyll årets EK-bevegelser og trykk 'Generer EK-føring'."


def refresh_associate_case_actions(page: "ConsolidationPage", case: AssociateCase | None) -> None:
    duplicate = _find_duplicate_company(page, case)
    if case is None:
        page._associate_header_var.set("Ingen tilknyttet sak valgt.")
        page._associate_status_var.set("Brukes for selskaper som ikke skal fullkonsolideres.")
    else:
        source_mode = str(case.source_mode or "manual").strip() or "manual"
        source_label = {
            "manual": "Manuell",
            "ar": "AR",
            "line_basis": "Regnskapslinjer",
            "pdf": "PDF",
        }.get(source_mode, source_mode)
        status_label = _associate_case_status_label(case, has_duplicate_company=duplicate is not None)
        page._associate_header_var.set(case.name or "Tilknyttet sak")
        if duplicate is not None:
            page._associate_status_var.set(
                f"Status: {status_label} | Kilde: {source_label} | Også importert som selskap: {duplicate.name}"
            )
        else:
            page._associate_status_var.set(f"Status: {status_label} | Kilde: {source_label}")

    page._associate_next_step_var.set(_build_next_step_text(page, case))

    generate_text = "Generer EK-føring"
    if case is not None:
        status = str(case.status or "draft").strip().lower()
        if status == "stale":
            generate_text = "Oppdater EK-føring"
        elif status == "generated":
            generate_text = "Regenerer EK-føring"

    if hasattr(page, "_btn_generate_associate"):
        page._btn_generate_associate.configure(
            text=generate_text,
            state="normal" if case is not None else "disabled",
        )
    if hasattr(page, "_btn_save_associate"):
        page._btn_save_associate.configure(state="normal" if case is not None else "disabled")
    if hasattr(page, "_btn_delete_associate"):
        page._btn_delete_associate.configure(state="normal" if case is not None else "disabled")
    if hasattr(page, "_btn_open_associate_journal"):
        page._btn_open_associate_journal.configure(
            state="normal" if case is not None and str(case.journal_id or "").strip() else "disabled"
        )


def current_associate_case(page: "ConsolidationPage") -> AssociateCase | None:
    if page._project is None:
        return None
    case_id = getattr(page, "_current_associate_case_id", None)
    if case_id:
        return page._project.find_associate_case(case_id)
    return None


def clear_associate_case_form(page: "ConsolidationPage") -> None:
    page._current_associate_case_id = None
    page._associate_manual_rows = []
    if hasattr(page, "_associate_name_var"):
        page._associate_name_var.set("")
        page._associate_investor_var.set("")
        page._associate_ownership_var.set("0")
        page._associate_acquisition_date_var.set("")
        page._associate_notes_var.set("")
        page._associate_source_mode_var.set("manual")
        page._associate_source_ref_var.set("")
        page._associate_opening_var.set("0")
        page._associate_result_var.set("0")
        page._associate_other_equity_var.set("0")
        page._associate_dividends_var.set("0")
        page._associate_impairment_var.set("0")
        page._associate_excess_value_var.set("0")
        page._associate_acq_cost_var.set("0")
        page._associate_net_assets_var.set("0")
        page._associate_gw_years_var.set("5")
        page._associate_gw_computed_var.set("")
        page._associate_gw_annual_var.set("")
        page._associate_investment_regnr_var.set("575")
        page._associate_result_regnr_var.set("100")
        page._associate_other_equity_regnr_var.set("695")
        page._associate_retained_regnr_var.set("705")
        _refresh_mapping_summary(page)
        _set_mapping_visibility(page, False)
    page._associate_header_var.set("Ingen tilknyttet sak valgt.")
    page._associate_status_var.set("")
    page._associate_calc_summary_var.set("Ingen beregning.")
    page._associate_journal_summary_var.set("Ingen journal generert.")
    if hasattr(page, "_tree_associate_adjustments"):
        page._tree_associate_adjustments.delete(*page._tree_associate_adjustments.get_children())
    if hasattr(page, "_tree_associate_calc"):
        page._tree_associate_calc.delete(*page._tree_associate_calc.get_children())
    if hasattr(page, "_tree_associate_journal"):
        page._tree_associate_journal.delete(*page._tree_associate_journal.get_children())
    refresh_associate_case_actions(page, None)


def populate_associate_case_form(page: "ConsolidationPage", case: AssociateCase) -> None:
    page._current_associate_case_id = case.case_id
    page._associate_manual_rows = [AssociateAdjustmentRow(**vars(row)) for row in case.manual_adjustment_rows]
    investor = ""
    if page._project is not None:
        company = page._project.find_company(case.investor_company_id)
        if company is not None:
            investor = f"{company.company_id} - {company.name}"
    mapping = dict(case.line_mapping or {})
    page._associate_name_var.set(case.name)
    page._associate_investor_var.set(investor)
    page._associate_ownership_var.set(_fmt_no(float(case.ownership_pct or 0.0), 2))
    page._associate_acquisition_date_var.set(case.acquisition_date)
    page._associate_notes_var.set(case.notes)
    page._associate_source_mode_var.set(case.source_mode or "manual")
    page._associate_source_ref_var.set(case.journal_id or "")
    page._associate_opening_var.set(_fmt_no(float(case.opening_carrying_amount or 0.0), 2))
    page._associate_result_var.set(_fmt_no(float(case.share_of_result or 0.0), 2))
    page._associate_other_equity_var.set(_fmt_no(float(case.share_of_other_equity or 0.0), 2))
    page._associate_dividends_var.set(_fmt_no(float(case.dividends or 0.0), 2))
    page._associate_impairment_var.set(_fmt_no(float(case.impairment or 0.0), 2))
    page._associate_excess_value_var.set(_fmt_no(float(case.excess_value_amortization or 0.0), 2))
    page._associate_acq_cost_var.set(_fmt_no(float(case.acquisition_cost or 0.0), 2))
    page._associate_net_assets_var.set(_fmt_no(float(case.share_of_net_assets_at_acquisition or 0.0), 2))
    page._associate_gw_years_var.set(str(max(int(case.goodwill_useful_life_years or 5), 1)))
    _update_goodwill_display(page)
    page._associate_investment_regnr_var.set(str(mapping.get("investment_regnr", 575)))
    page._associate_result_regnr_var.set(str(mapping.get("result_regnr", 100)))
    page._associate_other_equity_regnr_var.set(str(mapping.get("other_equity_regnr", 695)))
    page._associate_retained_regnr_var.set(str(mapping.get("retained_earnings_regnr", 705)))
    _refresh_mapping_summary(page)
    _set_mapping_visibility(page, False)
    refresh_associate_case_actions(page, case)
    refresh_associate_adjustment_tree(page)
    refresh_associate_case_views(page, case)


def _build_case_from_form(page: "ConsolidationPage", *, existing: AssociateCase | None = None) -> AssociateCase:
    case = existing or AssociateCase()
    case.name = str(page._associate_name_var.get() or "").strip()
    investor_raw = str(page._associate_investor_var.get() or "").strip()
    case.investor_company_id = investor_raw.split(" - ", 1)[0].strip() if investor_raw else ""
    case.ownership_pct = _parse_float(page._associate_ownership_var.get())
    case.acquisition_date = str(page._associate_acquisition_date_var.get() or "").strip()
    case.notes = str(page._associate_notes_var.get() or "").strip()
    case.source_mode = str(page._associate_source_mode_var.get() or "manual").strip() or "manual"
    case.opening_carrying_amount = _parse_float(page._associate_opening_var.get())
    case.share_of_result = _parse_float(page._associate_result_var.get())
    case.share_of_other_equity = _parse_float(page._associate_other_equity_var.get())
    case.dividends = abs(_parse_float(page._associate_dividends_var.get()))
    case.impairment = abs(_parse_float(page._associate_impairment_var.get()))
    case.excess_value_amortization = abs(_parse_float(page._associate_excess_value_var.get()))
    case.acquisition_cost = _parse_float(page._associate_acq_cost_var.get())
    case.share_of_net_assets_at_acquisition = _parse_float(page._associate_net_assets_var.get())
    case.goodwill_useful_life_years = max(_parse_int(page._associate_gw_years_var.get()), 1)
    case.line_mapping = {
        "investment_regnr": _parse_int(page._associate_investment_regnr_var.get()),
        "result_regnr": _parse_int(page._associate_result_regnr_var.get()),
        "other_equity_regnr": _parse_int(page._associate_other_equity_regnr_var.get()),
        "retained_earnings_regnr": _parse_int(page._associate_retained_regnr_var.get()),
    }
    case.manual_adjustment_rows = [AssociateAdjustmentRow(**vars(row)) for row in page._associate_manual_rows]
    return case


def refresh_associate_adjustment_tree(page: "ConsolidationPage") -> None:
    if not hasattr(page, "_tree_associate_adjustments"):
        return
    tree = page._tree_associate_adjustments
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    for row in page._associate_manual_rows:
        tree.insert(
            "",
            "end",
            iid=row.row_id,
            values=(
                row.label,
                _fmt_no(float(row.amount or 0.0), 2),
                row.offset_regnr,
                row.description,
            ),
        )


def refresh_associate_case_tree(page: "ConsolidationPage") -> None:
    if not hasattr(page, "_tree_associate_cases"):
        return
    tree = page._tree_associate_cases
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    refresh_investor_choices(page)
    if page._project is None:
        return
    for case in page._project.associate_cases:
        investor = page._project.find_company(case.investor_company_id)
        status = str(case.status or "draft").strip().lower() or "draft"
        duplicate = _find_duplicate_company(page, case)
        display_status = _associate_case_status_label(case, has_duplicate_company=duplicate is not None)
        if duplicate is not None:
            tag = ("stale",)
        else:
            tag = (status,) if status in {"draft", "generated", "stale"} else ()
        tree.insert(
            "",
            "end",
            iid=case.case_id,
            values=(
                case.name,
                investor.name if investor is not None else case.investor_company_id,
                f"{float(case.ownership_pct or 0.0):.2f}%",
                display_status,
            ),
            tags=tag,
        )


def refresh_associate_case_views(page: "ConsolidationPage", case: AssociateCase | None) -> None:
    if case is None:
        page._associate_calc_summary_var.set("Ingen beregning.")
        page._associate_journal_summary_var.set("Ingen journal generert.")
        page._tree_associate_calc.delete(*page._tree_associate_calc.get_children())
        page._tree_associate_journal.delete(*page._tree_associate_journal.get_children())
        return

    from ..backend.associate_equity_method import build_associate_case_calculation

    calc = build_associate_case_calculation(case)
    page._associate_calc_summary_var.set(
        "Inngående "
        f"{_fmt_no(float(calc['opening_carrying_amount']), 2)} | Bevegelse "
        f"{_fmt_no(float(calc['total_movement']), 2)} | Utgående "
        f"{_fmt_no(float(calc['closing_carrying_amount']), 2)}"
    )
    calc_tree = page._tree_associate_calc
    _reset_sort_state(calc_tree)
    calc_tree.delete(*calc_tree.get_children())
    for idx, movement in enumerate(calc["movements"], start=1):
        calc_tree.insert(
            "",
            "end",
            iid=f"calc-{idx}",
            values=(
                movement.get("label", ""),
                _fmt_no(float(movement.get("movement", 0.0) or 0.0), 2),
                movement.get("investment_regnr", ""),
                movement.get("offset_regnr", ""),
            ),
        )

    journal_tree = page._tree_associate_journal
    _reset_sort_state(journal_tree)
    journal_tree.delete(*journal_tree.get_children())
    journal = page._project.find_journal(case.journal_id) if page._project is not None and case.journal_id else None
    if journal is None:
        page._associate_journal_summary_var.set("Ingen journal generert.")
        return
    page._associate_journal_summary_var.set(f"{journal.display_label} | {journal.kind} | {journal.status}")
    for idx, line in enumerate(journal.lines, start=1):
        journal_tree.insert(
            "",
            "end",
            iid=f"journal-{idx}",
            values=(
                line.regnr,
                page._regnr_to_name.get(int(line.regnr or 0), ""),
                _fmt_no(float(line.amount or 0.0), 2),
                line.description,
            ),
        )


def refresh_investor_choices(page: "ConsolidationPage") -> None:
    if not hasattr(page, "_associate_investor_cb"):
        return
    if page._project is None:
        page._associate_investor_cb["values"] = ()
        return
    values = [f"{company.company_id} - {company.name}" for company in page._project.companies]
    page._associate_investor_cb["values"] = values
