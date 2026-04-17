"""Preview/Test-panel for AdminPage (refaktor PR 7).

Frie funksjoner som tar ``page: AdminPage`` og leser/skriver direkte på
instansens widgets og state-variabler. AdminPage-metodene er tynne wrappers
som kaller hit. Mønsteret speiler ``page_analyse_ui.py`` / ``page_analyse_rl.py``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import classification_workspace
import konto_klassifisering
from account_profile import AccountProfileDocument

from page_admin_helpers import (
    _clean_text,
    _client_year,
    _effective_sb_rows,
    _format_amount,
)
from page_admin_preview import (
    _preview_detail,
    _preview_next_action_text,
    _preview_status_text,
)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


PAYROLL_PREVIEW_COLUMNS = ("Konto", "Kontonavn", "Status", "Neste", "UB")


def build_preview_ui(page: Any) -> None:
    """Bygg Preview/Test-fanen for lønn.

    Preview/Test er forbeholdt lønnsrelevante kontoer; regnskapslinje-mapping
    redigeres i ``Regnskapslinjer``-fanen.
    """
    page._preview_tab.columnconfigure(0, weight=1)
    page._preview_tab.rowconfigure(1, weight=1)

    header = ttk.Frame(page._preview_tab, padding=(8, 8, 8, 4))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(2, weight=1)
    ttk.Label(
        header,
        text=(
            "Preview viser hvilke lønnssignaler som traff for valgt konto, uten å "
            "skrive noe til klientprofilene. Regnskapslinje-mapping redigeres i "
            "Regnskapslinjer-fanen."
        ),
        style="Muted.TLabel",
        wraplength=960,
        justify="left",
    ).grid(row=0, column=0, columnspan=5, sticky="w")
    ttk.Label(header, text="Søk:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    search_entry = ttk.Entry(header, textvariable=page._preview_search_var)
    search_entry.grid(row=1, column=1, sticky="ew", padx=(6, 8), pady=(8, 0))
    try:
        search_entry.bind("<KeyRelease>", lambda _event: populate_preview_tree(page), add="+")
    except Exception:
        pass
    ttk.Label(header, text="Vis:").grid(row=1, column=2, sticky="e", pady=(8, 0))
    preview_filter = ttk.Combobox(
        header,
        textvariable=page._preview_filter_var,
        values=preview_filter_options(page),
        state="readonly",
        width=22,
    )
    preview_filter.grid(row=1, column=3, sticky="w", padx=(6, 8), pady=(8, 0))
    page._preview_filter_combo = preview_filter
    try:
        preview_filter.bind("<<ComboboxSelected>>", lambda _event: populate_preview_tree(page), add="+")
    except Exception:
        pass
    ttk.Button(header, text="Oppfrisk preview", command=lambda: refresh_preview_rows(page)).grid(
        row=1, column=4, padx=(8, 0), pady=(8, 0)
    )

    body = ttk.Panedwindow(page._preview_tab, orient="horizontal")
    body.grid(row=1, column=0, sticky="nsew")

    tree_host = ttk.Frame(body, padding=(8, 0, 4, 8))
    tree_host.rowconfigure(0, weight=1)
    tree_host.columnconfigure(0, weight=1)
    body.add(tree_host, weight=4)

    detail_host = ttk.LabelFrame(body, text="Hvorfor?", padding=(8, 8, 8, 8))
    body.add(detail_host, weight=3)
    page._preview_detail_host = detail_host

    tree = ttk.Treeview(
        tree_host,
        columns=PAYROLL_PREVIEW_COLUMNS,
        show="headings",
        selectmode="extended",
    )
    tree.grid(row=0, column=0, sticky="nsew")
    page._preview_tree = tree
    for col, heading, width, anchor in (
        ("Konto", "Konto", 90, "w"),
        ("Kontonavn", "Kontonavn", 220, "w"),
        ("Status", "Status", 110, "w"),
        ("Neste", "Neste", 180, "w"),
        ("UB", "UB", 110, "e"),
    ):
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=anchor)
    y_scroll = ttk.Scrollbar(tree_host, orient="vertical", command=tree.yview)
    y_scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=y_scroll.set)
    try:
        tree.bind("<<TreeviewSelect>>", lambda _event: update_preview_details(page), add="+")
    except Exception:
        pass

    page._preview_headline_var = (
        tk.StringVar(value="Preview er ikke lastet ennå. Åpne Preview/Test eller trykk Oppfrisk preview.")
        if tk is not None
        else None
    )
    page._preview_current_var = tk.StringVar(value="") if tk is not None else None
    page._preview_suggested_var = tk.StringVar(value="") if tk is not None else None
    page._preview_why_var = tk.StringVar(value="") if tk is not None else None
    ttk.Label(
        detail_host,
        textvariable=page._preview_headline_var,
        style="Section.TLabel",
        wraplength=360,
        justify="left",
    ).pack(anchor="w", fill="x")
    for title, variable in (
        ("Lagret nå", page._preview_current_var),
        ("Foreslått", page._preview_suggested_var),
        ("Hvorfor", page._preview_why_var),
    ):
        section = ttk.LabelFrame(detail_host, text=title, padding=(6, 6, 6, 6))
        section.pack(fill="x", pady=(8, 0))
        ttk.Label(
            section,
            textvariable=variable,
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", fill="x")


def preview_filter_value(page: Any) -> str:
    return _clean_text(page._preview_filter_var.get() if page._preview_filter_var is not None else "") or "Alle"


def preview_filter_options(page: Any) -> tuple[str, ...]:
    return (
        "Alle",
        "Lønnsrelevante",
        "Ikke lønnsrelevante",
        classification_workspace.QUEUE_SUSPICIOUS,
        classification_workspace.QUEUE_READY,
        classification_workspace.QUEUE_HISTORY,
        classification_workspace.QUEUE_REVIEW,
        classification_workspace.QUEUE_UNMAPPED,
        classification_workspace.QUEUE_LOCKED,
    )


def preview_matches_filter(page: Any, item: classification_workspace.ClassificationWorkspaceItem) -> bool:
    selected_filter = preview_filter_value(page)
    if selected_filter == "Alle":
        return True
    if selected_filter == "Lønnsrelevante":
        return _preview_status_text(item) != "Ikke lønnsrelevant"
    if selected_filter == "Ikke lønnsrelevante":
        return _preview_status_text(item) == "Ikke lønnsrelevant"
    return classification_workspace.queue_matches(item, selected_filter)


def selected_preview_account(page: Any) -> str:
    tree = getattr(page, "_preview_tree", None)
    if tree is None:
        return ""
    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    if not selection:
        return ""
    return str(selection[0] or "").strip()


def selected_preview_accounts(page: Any) -> list[str]:
    tree = getattr(page, "_preview_tree", None)
    if tree is None:
        return []
    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    return [str(item or "").strip() for item in selection if str(item or "").strip()]


def populate_preview_tree(page: Any) -> None:
    tree = getattr(page, "_preview_tree", None)
    if tree is None:
        return
    selected_account = selected_preview_account(page)
    try:
        for item in tree.get_children(""):
            tree.delete(item)
    except Exception:
        pass
    if page._preview_rows.empty or not page._preview_items:
        update_preview_details(page)
        return
    search_text = _clean_text(page._preview_search_var.get() if page._preview_search_var is not None else "").casefold()
    inserted: list[str] = []
    for _, row in page._preview_rows.iterrows():
        account_no = _clean_text(row.get("Konto"))
        item = page._preview_items.get(account_no)
        if item is None or not preview_matches_filter(page, item):
            continue
        haystack = " ".join(
            [
                account_no,
                _clean_text(row.get("Kontonavn")),
                _preview_status_text(item),
                _preview_next_action_text(item),
            ]
        ).casefold()
        if search_text and search_text not in haystack:
            continue
        values = (
            account_no,
            _clean_text(row.get("Kontonavn")),
            _preview_status_text(item),
            _preview_next_action_text(item),
            _format_amount(row.get("UB")),
        )
        try:
            tree.insert("", "end", iid=account_no, values=values)
            inserted.append(account_no)
        except Exception:
            continue
    target = selected_account if selected_account in inserted else (inserted[0] if inserted else "")
    if target:
        try:
            tree.selection_set(target)
            tree.focus(target)
            tree.see(target)
        except Exception:
            pass
    update_preview_details(page)


def refresh_preview_rows(page: Any) -> None:
    page._preview_rows = _effective_sb_rows(page._analyse_page)
    page._preview_items = {}
    if page._preview_rows.empty:
        populate_preview_tree(page)
        return
    client, year = _client_year()
    document = konto_klassifisering.load_document(client, year=year) if client else None
    history_document = konto_klassifisering.load_document(client, year=year - 1) if client and year else None
    if document is None:
        document = AccountProfileDocument(client=client, year=year)
    catalog = konto_klassifisering.load_catalog()
    usage: dict[str, Any] = {}
    dataset = getattr(page._analyse_page, "dataset", None)
    if isinstance(dataset, pd.DataFrame) and not dataset.empty:
        try:
            from a07_feature import build_account_usage_features

            usage = build_account_usage_features(dataset)
        except Exception:
            usage = {}
    page._preview_items = classification_workspace.build_workspace_items(
        page._preview_rows,
        document=document,
        history_document=history_document,
        catalog=catalog,
        usage_features=usage,
    )
    populate_preview_tree(page)


def update_preview_details(page: Any) -> None:
    headline_var = page._preview_headline_var
    current_var = page._preview_current_var
    suggested_var = page._preview_suggested_var
    why_var = page._preview_why_var
    if headline_var is None or current_var is None or suggested_var is None or why_var is None:
        return
    account_no = selected_preview_account(page)
    if not account_no:
        headline_var.set("Velg en konto for preview.")
        current_var.set("")
        suggested_var.set("")
        why_var.set("")
        return
    item = page._preview_items.get(account_no)
    if item is None:
        headline_var.set("Velg en konto for preview.")
        current_var.set("")
        suggested_var.set("")
        why_var.set("")
        return
    detail = _preview_detail(item)
    headline_var.set(detail["headline"])
    current_var.set(detail["current"])
    suggested_var.set(detail["suggested"])
    why_var.set(detail["why"])
