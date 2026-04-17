"""Company tree, clipboard, right-click and mapping actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    messagebox = None  # type: ignore
    ttk = None  # type: ignore

from consolidation import storage
from page_consolidation_common import (
    format_company_row_count,
    is_line_basis_company,
    reset_sort_state,
    source_display,
)

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage


def refresh_company_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_companies
    reset_sort_state(tree)
    tree.delete(*tree.get_children())
    page._refresh_associate_investor_choices()
    if page._project is None:
        return
    parent_id = page._project.parent_company_id or ""
    companies = sorted(page._project.companies, key=lambda c: (0 if c.company_id == parent_id else 1, c.name))
    for company in companies:
        pct = page._mapping_pct.get(company.company_id, -1)
        unmapped_count, zero_unmapped_count = page._split_unmapped_counts(company.company_id)
        review_count = len(page._mapping_review_accounts.get(company.company_id, set()))
        if is_line_basis_company(company):
            mapping_text = "Direkte" if pct >= 0 else "Mangler grunnlag"
            tag = ("done",) if pct >= 0 else ()
        elif pct < 0:
            mapping_text = "-"
            tag = ()
        elif pct >= 100 and unmapped_count == 0 and zero_unmapped_count == 0 and review_count == 0:
            mapping_text = "100%"
            tag = ("done",)
        elif unmapped_count > 0 or review_count > 0:
            parts = []
            if unmapped_count > 0:
                parts.append(f"{unmapped_count} umappet")
            if zero_unmapped_count > 0:
                parts.append(f"{zero_unmapped_count} umappet 0-linje")
            if review_count > 0:
                parts.append(f"{review_count} avvik")
            mapping_text = f"{pct}% ({', '.join(parts)})"
            tag = ("review",)
        elif zero_unmapped_count > 0:
            mapping_text = f"{pct}% ({zero_unmapped_count} umappet 0-linje)"
            tag = ()
        else:
            mapping_text = f"{pct}%"
            tag = ("review",) if pct < 90 else ()
        display_name = f"★ {company.name}" if company.company_id == parent_id else company.name
        tree.insert(
            "",
            "end",
            iid=company.company_id,
            values=(
                display_name,
                source_display(company.source_type, company.has_ib),
                format_company_row_count(company),
                mapping_text,
            ),
            tags=tag,
        )


def copy_tree_to_clipboard(page: "ConsolidationPage", tree: ttk.Treeview) -> None:
    lines = ["\t".join(str(tree.heading(col, "text")) for col in tree["columns"])]
    for iid in tree.get_children():
        lines.append("\t".join(str(value) for value in tree.item(iid, "values")))
    try:
        page.clipboard_clear()
        page.clipboard_append("\n".join(lines))
    except Exception:
        pass


def on_company_right_click(page: "ConsolidationPage", event) -> None:
    if str(page._tree_companies.identify_region(event.x, event.y)) == "heading":
        page._companies_col_mgr.show_header_menu(event)
        return
    iid = page._tree_companies.identify_row(event.y)
    if iid:
        page._tree_companies.selection_set(iid)
        page._company_menu.post(event.x_root, event.y_root)


def on_detail_right_click(page: "ConsolidationPage", event) -> None:
    if str(page._tree_detail.identify_region(event.x, event.y)) == "heading":
        page._detail_col_mgr.show_header_menu(event)
        return
    iid = page._tree_detail.identify_row(event.y)
    if not iid:
        return
    page._tree_detail.selection_set(iid)
    if page._project is not None and page._current_detail_cid:
        company = page._project.find_company(page._current_detail_cid)
        if company is not None and is_line_basis_company(company):
            return
    page._detail_menu.post(event.x_root, event.y_root)


def on_result_right_click(page: "ConsolidationPage", event) -> None:
    page._result_col_mgr.on_right_click(event)


def on_detail_double_click(page: "ConsolidationPage", event) -> None:
    iid = page._tree_detail.identify_row(event.y)
    if iid:
        page._tree_detail.selection_set(iid)
        page._on_change_mapping()


def on_change_mapping(page: "ConsolidationPage") -> None:
    sel_detail = page._tree_detail.selection()
    sel_company = page._tree_companies.selection()
    if not sel_detail or not sel_company or page._project is None:
        return
    company_id = sel_company[0]
    company = page._project.find_company(company_id)
    if company is not None and is_line_basis_company(company):
        return

    selected: dict[str, tuple[str, str, str]] = {}
    for iid in sel_detail:
        vals = page._tree_detail.item(iid, "values")
        if vals:
            konto = str(vals[0]).strip()
            if konto and konto not in selected:
                selected[konto] = (konto, str(vals[1]), str(vals[2]) if vals[2] else "")
    selected_kontos = list(selected.values())
    if not selected_kontos:
        return

    regnskapslinjer = page._regnskapslinjer
    if regnskapslinjer is None:
        try:
            from consolidation.mapping import load_shared_config
            _, regnskapslinjer = load_shared_config()
        except Exception as exc:
            messagebox.showerror("Konfigurasjon", f"Kunne ikke laste regnskapslinjer:\n{exc}")
            return

    choices: list[str] = []
    regnr_list: list[int] = []
    for _, row in regnskapslinjer.iterrows():
        regnr = int(row["regnr"])
        if bool(row.get("sumpost", False)):
            continue
        choices.append(f"{regnr} - {row.get('regnskapslinje', '')}")
        regnr_list.append(regnr)

    dlg = tk.Toplevel(page)
    dlg.title("Tildel regnskapslinje")
    dlg.transient(page)
    dlg.grab_set()
    if len(selected_kontos) == 1:
        konto, kontonavn, _ = selected_kontos[0]
        ttk.Label(dlg, text=f"Konto: {konto} - {kontonavn}", font=("", 10, "bold")).pack(padx=12, pady=(12, 4), anchor="w")
    else:
        ttk.Label(dlg, text=f"{len(selected_kontos)} kontoer valgt", font=("", 10, "bold")).pack(padx=12, pady=(12, 4), anchor="w")
        preview = ", ".join(konto for konto, _, _ in selected_kontos[:8])
        if len(selected_kontos) > 8:
            preview += f" ... (+{len(selected_kontos) - 8})"
        ttk.Label(dlg, text=preview, foreground="gray").pack(padx=12, anchor="w")

    ttk.Label(dlg, text="Velg regnskapslinje:").pack(padx=12, pady=(8, 2), anchor="w")
    combo = ttk.Combobox(dlg, textvariable=tk.StringVar(), values=choices, width=50)
    combo.pack(padx=12, fill="x")
    if len(selected_kontos) == 1 and selected_kontos[0][2]:
        for idx, regnr in enumerate(regnr_list):
            if str(regnr) == selected_kontos[0][2]:
                combo.current(idx)
                break

    result = {"regnr": None}

    def _close() -> None:
        dlg.grab_release()
        dlg.destroy()

    def _on_ok() -> None:
        idx = combo.current()
        if idx < 0:
            messagebox.showwarning("Velg linje", "Velg en regnskapslinje.", parent=dlg)
            return
        result["regnr"] = regnr_list[idx]
        _close()

    def _on_remove() -> None:
        result["regnr"] = "remove"
        _close()

    btn_frm = ttk.Frame(dlg)
    btn_frm.pack(fill="x", padx=12, pady=12)
    ttk.Button(btn_frm, text="Avbryt", command=_close).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frm, text="OK", command=_on_ok).pack(side="right")
    if any(regnr for _, _, regnr in selected_kontos):
        ttk.Button(btn_frm, text="Fjern overstyring", command=_on_remove).pack(side="left")

    dlg.wait_window()
    if result["regnr"] is None:
        return
    if company_id == page._project.parent_company_id:
        messagebox.showinfo(
            "Mapping styres fra Analyse",
            "Morselskapet bruker Analyse som kilde til sannhet for mapping. Endre parent-mapping i Analyse-fanen, og kjoer deretter konsolidering paa nytt.",
            parent=dlg,
        )
        page._show_company_detail(company_id)
        return

    overrides = page._project.mapping_config.company_overrides
    if company_id not in overrides:
        overrides[company_id] = {}
    for konto, _, _ in selected_kontos:
        if result["regnr"] == "remove":
            overrides[company_id].pop(konto, None)
        else:
            overrides[company_id][konto] = result["regnr"]
    if company_id in overrides and not overrides[company_id]:
        del overrides[company_id]

    page._project.touch()
    storage.save_project(page._project)
    page._invalidate_run_cache()
    page._compute_mapping_status()
    page._refresh_company_tree()
    page._show_company_detail(company_id)


def on_mapping_overrides_changed(page: "ConsolidationPage", company_id: str, new_overrides: dict[str, int]) -> None:
    if page._project is None:
        return
    if company_id == page._project.parent_company_id:
        try:
            messagebox.showinfo(
                "Mapping styres fra Analyse",
                "Morselskapet bruker Analyse som kilde til sannhet for mapping. Endre parent-mapping i Analyse-fanen, og kjoer deretter konsolidering paa nytt.",
            )
        except Exception:
            pass
        page._show_company_detail(company_id)
        return
    overrides = page._project.mapping_config.company_overrides
    if new_overrides:
        overrides[company_id] = dict(new_overrides)
    else:
        overrides.pop(company_id, None)
    page._project.touch()
    storage.save_project(page._project)
    page._invalidate_run_cache()
    page._compute_mapping_status()
    page._refresh_company_tree()
    page._show_company_detail(company_id)


def on_company_select(page: "ConsolidationPage", _event=None) -> None:
    sel = page._tree_companies.selection()
    if sel:
        page._show_company_detail(sel[0])
        if page._suggestions and not page._show_all_pairs_var.get():
            page._refresh_suggestion_tree()


def on_set_parent(page: "ConsolidationPage") -> None:
    sel = page._tree_companies.selection()
    if not sel or page._project is None:
        return
    cid = sel[0]
    company = page._project.find_company(cid)
    if company is None:
        return
    page._project.parent_company_id = "" if page._project.parent_company_id == cid else cid
    page._project.touch()
    storage.save_project(page._project)
    page._invalidate_run_cache()
    page._refresh_company_tree()


def on_delete_company(page: "ConsolidationPage", _event=None) -> None:
    sel = page._tree_companies.selection()
    if not sel or page._project is None:
        return
    cid = sel[0]
    company = page._project.find_company(cid)
    if company is None or not messagebox.askyesno("Slett selskap", f"Slett {company.name}?"):
        return
    page._project.companies = [item for item in page._project.companies if item.company_id != cid]
    page._company_tbs.pop(cid, None)
    page._company_line_bases.pop(cid, None)
    page._mapped_tbs.pop(cid, None)
    page._mapping_pct.pop(cid, None)
    storage.delete_company_tb(page._project.client, page._project.year, cid)
    storage.delete_company_line_basis(page._project.client, page._project.year, cid)
    storage.save_project(page._project)
    page._refresh_company_tree()
    page._tree_detail.delete(*page._tree_detail.get_children())
    page._update_status()


def select_and_show_company(page: "ConsolidationPage", company_id: str) -> None:
    try:
        page._tree_companies.selection_set(company_id)
        page._tree_companies.see(company_id)
        page._show_company_detail(company_id)
        page._select_left_tab(0, "_left_tab_companies")
    except Exception:
        pass
