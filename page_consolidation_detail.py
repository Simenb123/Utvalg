"""page_consolidation_detail.py - detail view implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage

logger = logging.getLogger(__name__)


def _reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def _is_line_basis_company(company: object | None) -> bool:
    if company is None:
        return False
    return str(getattr(company, "basis_type", "tb") or "tb").strip().lower() == "regnskapslinje"


def _set_detail_context(
    page: "ConsolidationPage",
    company: object | None,
    basis: pd.DataFrame | None,
    *,
    build_detail_meta_text,
) -> None:
    if hasattr(page, "_detail_meta_var"):
        page._detail_meta_var.set(build_detail_meta_text(company, basis))


def populate_grunnlag(
    page: "ConsolidationPage",
    regnr: int,
    *,
    is_sumpost: bool = False,
    fmt_no,
) -> None:
    tree = page._tree_grunnlag
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())

    rl_name = page._regnr_to_name.get(regnr, "")

    leaf_regnrs: list[int] = [regnr]
    if is_sumpost and page._regnskapslinjer is not None:
        try:
            from regnskap_mapping import expand_regnskapslinje_selection

            expanded = expand_regnskapslinje_selection(
                regnskapslinjer=page._regnskapslinjer,
                selected_regnr=[regnr],
            )
            if expanded:
                leaf_regnrs = expanded
        except Exception:
            logger.debug("Could not expand sumpost %s", regnr, exc_info=True)

    run_result = page._last_run_result
    if run_result is None or run_result.account_details is None:
        page._grunnlag_label_var.set(f"Regnr {regnr}: {rl_name}")
        tree.insert(
            "",
            "end",
            values=(
                "",
                "",
                "Kjør konsolidering for å se grunnlag",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ),
        )
        return

    details: pd.DataFrame = run_result.account_details
    leaf_set = set(float(r) for r in leaf_regnrs)
    mask = details["regnr"].notna() & details["regnr"].astype(float).isin(leaf_set)
    filtered = details.loc[mask].copy()

    mode = page._result_mode_var.get()
    company_filter = ""
    if mode == "Valgt selskap":
        cid = getattr(page, "_current_detail_cid", None)
        proj = getattr(page, "_project", None)
        if cid and proj:
            company = proj.find_company(cid)
            if company:
                company_filter = company.name
                filtered = filtered[filtered["selskap"] == company_filter]

    scope_parts: list[str] = []
    if is_sumpost and len(leaf_regnrs) > 1:
        scope_parts.append(f"{len(leaf_regnrs)} underliggende linjer")
    scope_parts.append(company_filter if company_filter else "alle selskaper")
    page._grunnlag_label_var.set(f"Regnr {regnr}: {rl_name} ({', '.join(scope_parts)})")

    if filtered.empty:
        tree.insert(
            "",
            "end",
            values=(
                "",
                "",
                f"Ingen kontoer paa regnr {regnr}",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ),
        )
        return

    filtered = filtered.sort_values(
        ["selskap", "konto"],
        na_position="last",
    ).reset_index(drop=True)

    for _, row in filtered.iterrows():
        selskap = str(row.get("selskap", ""))
        konto = str(row.get("konto", ""))
        kontonavn = str(row.get("kontonavn", ""))
        row_regnr = int(row["regnr"])
        rl = str(row.get("regnskapslinje", ""))
        ib = float(row.get("ib", 0.0)) if pd.notna(row.get("ib")) else 0.0
        netto = float(row.get("netto", 0.0)) if pd.notna(row.get("netto")) else 0.0
        ub_orig = float(row.get("ub_original", 0.0)) if pd.notna(row.get("ub_original")) else 0.0
        valuta = str(row.get("valuta", ""))
        kurs = float(row.get("kurs", 1.0)) if pd.notna(row.get("kurs")) else 1.0
        ub_conv = float(row.get("ub", 0.0)) if pd.notna(row.get("ub")) else 0.0
        valutaeffekt = ub_conv - ub_orig

        tags = ("neg",) if ub_conv < -0.005 else ()
        tree.insert(
            "",
            "end",
            values=(
                selskap,
                konto,
                kontonavn,
                row_regnr,
                rl,
                fmt_no(ib, 2),
                fmt_no(netto, 2),
                fmt_no(ub_orig, 2),
                valuta,
                fmt_no(kurs, 4) if abs(kurs - 1.0) > 0.0001 else "1",
                fmt_no(ub_conv, 2),
                fmt_no(valutaeffekt, 2) if abs(valutaeffekt) > 0.005 else "",
            ),
            tags=tags,
        )


def configure_detail_tree_columns(
    page: "ConsolidationPage",
    *,
    line_basis: bool,
    detail_tb_column_specs,
    detail_line_column_specs,
) -> None:
    mode = "line" if line_basis else "tb"
    if getattr(page, "_detail_tree_mode", None) == mode:
        return

    specs = detail_line_column_specs if line_basis else detail_tb_column_specs
    col_ids = [spec.id for spec in specs]
    tree = page._tree_detail

    if hasattr(page, "_detail_tree_mgr") and page._detail_tree_mgr is not None:
        try:
            page._detail_tree_mgr.update_columns(specs, default_visible=col_ids)
            page._detail_col_mgr = page._detail_tree_mgr.column_manager
        except Exception:
            pass
    else:
        try:
            tree["displaycolumns"] = "#all"
        except Exception:
            pass
        try:
            tree["columns"] = col_ids
        except Exception:
            pass
        for spec in specs:
            try:
                tree.heading(spec.id, text=spec.heading or spec.id)
            except Exception:
                pass
            try:
                tree.column(
                    spec.id,
                    width=int(spec.width),
                    minwidth=int(spec.minwidth),
                    anchor=spec.anchor,
                    stretch=bool(spec.stretch),
                )
            except Exception:
                pass

    page._detail_tree_mode = mode


def show_company_detail(
    page: "ConsolidationPage",
    company_id: str,
    *,
    build_detail_meta_text,
) -> None:
    page._current_detail_cid = company_id
    company = page._project.find_company(company_id) if page._project is not None else None

    effective_raw = page._get_effective_company_basis(company_id)
    tb = page._mapped_tbs.get(company_id)
    if tb is None or (isinstance(tb, pd.DataFrame) and tb.empty):
        tb = effective_raw
    if tb is None:
        page._tree_detail.delete(*page._tree_detail.get_children())
        _set_detail_context(
            page,
            company,
            None,
            build_detail_meta_text=build_detail_meta_text,
        )
        return

    _set_detail_context(
        page,
        company,
        tb,
        build_detail_meta_text=build_detail_meta_text,
    )

    if company is not None and _is_line_basis_company(company):
        page._mapping_tab.clear()
        if hasattr(page._mapping_tab, "_status_var"):
            page._mapping_tab._status_var.set(
                "Direkte regnskapslinje-grunnlag: konto-mapping er ikke relevant.",
            )
    elif page._regnskapslinjer is not None:
        overrides = page._get_effective_company_overrides(company_id)
        read_only_reason = ""
        if page._project is not None and company_id == page._project.parent_company_id:
            read_only_reason = "Mor styres fra Analyse. Endre parent-mapping i Analyse-fanen."
        page._mapping_tab.set_data(
            company_id,
            effective_raw if effective_raw is not None else tb,
            page._mapped_tbs.get(company_id),
            overrides,
            page._regnskapslinjer,
            page._regnr_to_name,
            review_accounts=getattr(page, "_mapping_review_accounts", {}).get(company_id, set()),
            read_only_reason=read_only_reason,
        )

    if company is not None and _is_line_basis_company(company):
        page._populate_line_basis_detail_tree(tb)
    else:
        page._populate_detail_tree(tb, company_id)

    page._build_company_result(company_id)
    if page._result_mode_var.get() == "Valgt selskap":
        page._refresh_result_view()


def populate_detail_tree(
    page: "ConsolidationPage",
    tb: pd.DataFrame,
    company_id: str,
    *,
    fmt_no,
    format_count_label,
    format_filtered_count_label,
) -> None:
    page._configure_detail_tree_columns(line_basis=False)
    tree = page._tree_detail
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    unmapped = set(page._mapping_unmapped.get(company_id, []))
    review_accounts = set(getattr(page, "_mapping_review_accounts", {}).get(company_id, set()))
    hide_zero = page._detail_hide_zero_var.get()
    grouped: dict[str, dict[str, object]] = {}
    for _, row in tb.iterrows():
        konto = str(row.get("konto", "") or "").strip()
        if not konto:
            continue
        kontonavn = str(row.get("kontonavn", "") or "").strip()
        regnr_raw = row.get("regnr", "")
        try:
            regnr_int = (
                int(regnr_raw)
                if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan")
                else None
            )
        except (ValueError, TypeError):
            regnr_int = None

        item = grouped.setdefault(
            konto,
            {
                "konto": konto,
                "kontonavn": kontonavn,
                "regnr": regnr_int,
                "ib": 0.0,
                "netto": 0.0,
                "ub": 0.0,
            },
        )
        if kontonavn and not str(item.get("kontonavn", "") or "").strip():
            item["kontonavn"] = kontonavn
        if item.get("regnr") is None and regnr_int is not None:
            item["regnr"] = regnr_int
        for col in ("ib", "netto", "ub"):
            try:
                item[col] = float(item.get(col, 0.0) or 0.0) + float(row.get(col, 0.0) or 0.0)
            except (ValueError, TypeError):
                pass

    total = len(grouped)
    shown = 0

    for konto, row in grouped.items():
        try:
            ib = float(row.get("ib", 0) or 0)
            ub = float(row.get("ub", 0) or 0)
            netto = float(row.get("netto", 0) or 0)
        except (ValueError, TypeError):
            ib = ub = netto = 0.0

        if hide_zero and abs(ib) < 0.005 and abs(ub) < 0.005 and abs(netto) < 0.005:
            continue

        shown += 1
        regnr_int = row.get("regnr")
        regnr_display = regnr_int if regnr_int is not None else ""
        rl_navn = page._regnr_to_name.get(int(regnr_int), "") if regnr_int is not None else ""
        tag = ("review",) if konto in unmapped or konto in review_accounts else ()
        tree.insert(
            "",
            "end",
            iid=konto,
            values=(
                konto,
                row.get("kontonavn", ""),
                regnr_display,
                rl_navn,
                fmt_no(ib, 2),
                fmt_no(netto, 2),
                fmt_no(ub, 2),
            ),
            tags=tag,
        )

    if hide_zero and total > shown:
        page._detail_count_var.set(format_filtered_count_label(shown, total, "konto", "kontoer"))
    else:
        page._detail_count_var.set(format_count_label(total, "konto", "kontoer"))


def populate_line_basis_detail_tree(
    page: "ConsolidationPage",
    basis: pd.DataFrame,
    *,
    fmt_no,
    format_count_label,
    format_filtered_count_label,
) -> None:
    page._configure_detail_tree_columns(line_basis=True)
    tree = page._tree_detail
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    hide_zero = page._detail_hide_zero_var.get()
    shown = 0

    work = basis.copy().sort_values(["regnr", "regnskapslinje"], na_position="last")
    total = len(work.index)
    for idx, (_, row) in enumerate(work.iterrows(), start=1):
        ub = float(row.get("ub", 0.0) or 0.0) if pd.notna(row.get("ub")) else 0.0
        if hide_zero and abs(ub) < 0.005:
            continue
        shown += 1
        regnr_val = int(row["regnr"]) if pd.notna(row.get("regnr")) else ""
        source_line = str(row.get("source_regnskapslinje", "") or row.get("regnskapslinje", "") or "")
        source_page = int(row["source_page"]) if pd.notna(row.get("source_page")) else ""
        confidence_raw = row.get("confidence")
        confidence_display = ""
        if pd.notna(confidence_raw):
            confidence_display = f"{fmt_no(float(confidence_raw) * 100.0, 0)}%"

        review_status = str(row.get("review_status", "") or "").strip().lower()
        if review_status == "approved":
            status_display = "Godkjent"
            tags = ("approved",)
        elif review_status:
            status_display = review_status.replace("_", " ").capitalize()
            tags = ("review",)
        elif pd.notna(confidence_raw) and float(confidence_raw) < 0.75:
            status_display = "Lav score"
            tags = ("review",)
        else:
            status_display = "Direkte"
            tags = ()

        tree.insert(
            "",
            "end",
            iid=f"rl-{idx}",
            values=(
                regnr_val,
                str(row.get("regnskapslinje", "") or ""),
                source_line,
                fmt_no(ub, 2),
                source_page,
                status_display,
                confidence_display,
            ),
            tags=tags,
        )

    if hide_zero and total > shown:
        page._detail_count_var.set(format_filtered_count_label(shown, total, "linje", "linjer"))
    else:
        page._detail_count_var.set(format_count_label(total, "linje", "linjer"))


def on_detail_filter_changed(page: "ConsolidationPage") -> None:
    cid = getattr(page, "_current_detail_cid", None)
    if not cid:
        return
    if page._project is not None:
        company = page._project.find_company(cid)
        if company is not None and _is_line_basis_company(company):
            basis = page._mapped_tbs.get(cid)
            if basis is None or (isinstance(basis, pd.DataFrame) and basis.empty):
                basis = page._company_line_bases.get(cid)
            if basis is not None:
                page._populate_line_basis_detail_tree(basis)
            return
    tb = page._mapped_tbs.get(cid)
    if tb is None or (isinstance(tb, pd.DataFrame) and tb.empty):
        tb = page._company_tbs.get(cid)
    if tb is not None:
        page._populate_detail_tree(tb, cid)
