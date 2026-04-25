"""FX tab UI and FX-related actions for consolidation."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    simpledialog = None  # type: ignore
    ttk = None  # type: ignore

from consolidation import storage
from .common import reset_sort_state
from ui_managed_treeview import ColumnSpec, ManagedTreeview

if TYPE_CHECKING:
    from .page import ConsolidationPage


def build_valuta_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(1, weight=1)

    lbl_frm = ttk.LabelFrame(parent, text="Prosjektinnstillinger", padding=8)
    lbl_frm.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
    lbl_frm.columnconfigure(1, weight=1)
    ttk.Label(lbl_frm, text="Rapporteringsvaluta:").grid(row=0, column=0, sticky="w", pady=2)
    page._fx_reporting_var = tk.StringVar(value="NOK")
    ttk.Entry(lbl_frm, textvariable=page._fx_reporting_var, width=6).grid(row=0, column=1, sticky="w", padx=(4, 0))
    ttk.Label(lbl_frm, text="Match-toleranse (NOK):").grid(row=1, column=0, sticky="w", pady=2)
    page._fx_tolerance_var = tk.StringVar(value="1000")
    ttk.Entry(lbl_frm, textvariable=page._fx_tolerance_var, width=10).grid(row=1, column=1, sticky="w", padx=(4, 0))
    ttk.Button(lbl_frm, text="Lagre", command=page._on_save_fx_settings).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    frm_rates = ttk.LabelFrame(parent, text="Valutakurser per selskap", padding=8)
    frm_rates.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
    frm_rates.columnconfigure(0, weight=1)
    frm_rates.rowconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)

    page._tree_fx_rates = ttk.Treeview(
        frm_rates,
        columns=("company", "currency", "closing_rate", "average_rate"),
        show="headings",
        height=6,
    )
    for col, text, width, anchor in (
        ("company", "Selskap", 140, "w"),
        ("currency", "Valuta", 60, "w"),
        ("closing_rate", "Sluttkurs", 80, "e"),
        ("average_rate", "Snittkurs", 80, "e"),
    ):
        page._tree_fx_rates.heading(col, text=text)
        page._tree_fx_rates.column(col, width=width, anchor=anchor)
    page._tree_fx_rates.grid(row=0, column=0, sticky="nsew")
    page._fx_tree_mgr = ManagedTreeview(
        page._tree_fx_rates,
        view_id="fx_rates",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("company", "Selskap", width=140, pinned=True, stretch=True),
            ColumnSpec("currency", "Valuta", width=60),
            ColumnSpec("closing_rate", "Sluttkurs", width=80, anchor="e"),
            ColumnSpec("average_rate", "Snittkurs", width=80, anchor="e"),
        ],
    )
    page._fx_col_mgr = page._fx_tree_mgr.column_manager
    btn_frm = ttk.Frame(frm_rates)
    btn_frm.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    ttk.Button(btn_frm, text="Rediger valuta...", command=page._on_edit_fx_rate).pack(side="left")


def has_foreign_currency(page: "ConsolidationPage") -> bool:
    if page._project is None:
        return False
    reporting = page._project.reporting_currency or "NOK"
    for company in page._project.companies:
        if company.currency_code and company.currency_code != reporting:
            return True
        if abs(company.closing_rate - 1.0) > 0.0001 or abs(company.average_rate - 1.0) > 0.0001:
            return True
    return False


def update_valuta_tab_visibility(page: "ConsolidationPage") -> None:
    try:
        page._elim_nb.tab(page._elim_tab_fx, state="normal" if page._has_foreign_currency() else "hidden")
    except Exception:
        pass


def refresh_fx_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_fx_rates
    reset_sort_state(tree)
    tree.delete(*tree.get_children())
    if page._project is None:
        return
    page._fx_reporting_var.set(page._project.reporting_currency or "NOK")
    page._fx_tolerance_var.set(str(page._project.match_tolerance_nok))
    for company in page._project.companies:
        tree.insert(
            "",
            "end",
            iid=company.company_id,
            values=(
                company.name,
                company.currency_code or page._project.reporting_currency,
                f"{company.closing_rate:.4f}",
                f"{company.average_rate:.4f}",
            ),
        )
    page._update_valuta_tab_visibility()


def on_save_fx_settings(page: "ConsolidationPage") -> None:
    if page._project is None:
        return
    page._project.reporting_currency = page._fx_reporting_var.get().strip().upper() or "NOK"
    try:
        page._project.match_tolerance_nok = float(page._fx_tolerance_var.get().replace(",", ".").strip() or "1000")
    except ValueError:
        pass
    storage.save_project(page._project)
    page._invalidate_run_cache()


def on_edit_fx_rate(page: "ConsolidationPage") -> None:
    sel = page._tree_fx_rates.selection()
    if not sel or page._project is None:
        return
    company = page._project.find_company(sel[0])
    if company is None:
        return
    raw = simpledialog.askstring(
        "Valutakurs",
        f"Selskap: {company.name}\nValutakode ; Sluttkurs ; Snittkurs\nEksempel: SEK ; 0.98 ; 0.97",
        initialvalue=f"{company.currency_code or 'NOK'} ; {company.closing_rate} ; {company.average_rate}",
    )
    if not raw:
        return
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) >= 1:
        company.currency_code = parts[0].upper()
    if len(parts) >= 2:
        try:
            company.closing_rate = float(parts[1].replace(",", "."))
        except ValueError:
            pass
    if len(parts) >= 3:
        try:
            company.average_rate = float(parts[2].replace(",", "."))
        except ValueError:
            pass
    storage.save_project(page._project)
    page._invalidate_run_cache()
    page._refresh_fx_tree()
