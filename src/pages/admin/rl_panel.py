"""RL-kontroll-panel for AdminPage (refaktor PR 7).

Frie funksjoner som tar ``page: AdminPage`` og leser/skriver direkte på
instansens widgets og state-variabler. AdminPage-metodene er tynne wrappers
som kaller hit. RL-kontroll-fanen er parkert i runtime, men buttons/handlers
må fortsatt virke når den bygges.
"""

from __future__ import annotations

from typing import Any

import analyse_mapping_service
import session

from page_admin_helpers import _clean_text, _format_amount
from page_admin_preview import (
    _RL_PREVIEW_FILTER_OPTIONS,
    _format_rl_baseline,
    _format_rl_current,
    _format_rl_mapping_source,
    _format_rl_override,
    _format_rl_suggestion,
    _rl_preview_detail,
    _rl_preview_is_ready_for_suggestion,
    _rl_preview_status_text,
)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


RL_PREVIEW_COLUMNS = (
    "Konto",
    "Kontonavn",
    "Status",
    "Mappingkilde",
    "Baseline",
    "Override",
    "Effektiv",
    "Forslag",
    "Belop",
)


def build_rl_control_ui(page: Any) -> None:
    """Bygg den dedikerte RL-kontroll-fanen.

    Fanen samler hele RL-mappingflyten: diagnose, overstyr-styring,
    forslag og navigasjon til Analyse. Preview/Test er ikke lenger
    involvert i RL.
    """
    page._rl_control_tab.columnconfigure(0, weight=1)
    page._rl_control_tab.rowconfigure(3, weight=1)

    header = ttk.Frame(page._rl_control_tab, padding=(8, 8, 8, 4))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(2, weight=1)
    ttk.Label(
        header,
        text=(
            "RL-kontroll viser hvilke kontoer som er mappet til en "
            "regnskapslinje, hvor mappingen kommer fra, og hvilke "
            "kontoer som trenger handling. Handlinger skriver til "
            "klient-overstyringer og refresher resten av applikasjonen."
        ),
        style="Muted.TLabel",
        wraplength=960,
        justify="left",
    ).grid(row=0, column=0, columnspan=5, sticky="w")
    ttk.Label(header, text="Søk:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    search_entry = ttk.Entry(header, textvariable=page._rl_search_var)
    search_entry.grid(row=1, column=1, sticky="ew", padx=(6, 8), pady=(8, 0))
    try:
        search_entry.bind("<KeyRelease>", lambda _event: populate_rl_control_tree(page), add="+")
    except Exception:
        pass
    ttk.Label(header, text="Vis:").grid(row=1, column=2, sticky="e", pady=(8, 0))
    rl_filter = ttk.Combobox(
        header,
        textvariable=page._rl_filter_var,
        values=_RL_PREVIEW_FILTER_OPTIONS,
        state="readonly",
        width=22,
    )
    rl_filter.grid(row=1, column=3, sticky="w", padx=(6, 8), pady=(8, 0))
    page._rl_filter_combo = rl_filter
    try:
        rl_filter.bind("<<ComboboxSelected>>", lambda _event: populate_rl_control_tree(page), add="+")
    except Exception:
        pass
    ttk.Button(header, text="Oppfrisk", command=lambda: refresh_rl_control_rows(page)).grid(
        row=1, column=4, padx=(8, 0), pady=(8, 0)
    )

    page._rl_status_var = tk.StringVar(value="") if tk is not None else None
    if page._rl_status_var is not None:
        ttk.Label(
            page._rl_control_tab,
            textvariable=page._rl_status_var,
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew")

    actions = ttk.Frame(page._rl_control_tab, padding=(8, 0, 8, 4))
    actions.grid(row=2, column=0, sticky="ew")
    ttk.Button(
        actions,
        text="Sett override…",
        command=lambda: on_rl_set_override_clicked(page),
    ).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(
        actions,
        text="Fjern override",
        command=lambda: on_rl_clear_override_clicked(page),
    ).grid(row=0, column=1, padx=(0, 6))
    ttk.Button(
        actions,
        text="Bruk forslag",
        command=lambda: on_rl_use_suggestion_clicked(page),
    ).grid(row=0, column=2, padx=(0, 6))
    ttk.Button(
        actions,
        text="Åpne i Analyse",
        command=lambda: on_rl_open_in_analyse_clicked(page),
    ).grid(row=0, column=3, padx=(0, 6))

    body = ttk.Panedwindow(page._rl_control_tab, orient="horizontal")
    body.grid(row=3, column=0, sticky="nsew")

    tree_host = ttk.Frame(body, padding=(8, 0, 4, 8))
    tree_host.rowconfigure(0, weight=1)
    tree_host.columnconfigure(0, weight=1)
    body.add(tree_host, weight=4)

    detail_host = ttk.LabelFrame(body, text="Hvorfor?", padding=(8, 8, 8, 8))
    body.add(detail_host, weight=3)

    tree = ttk.Treeview(
        tree_host,
        columns=RL_PREVIEW_COLUMNS,
        show="headings",
        selectmode="extended",
    )
    tree.grid(row=0, column=0, sticky="nsew")
    page._rl_control_tree = tree
    for col, heading, width, anchor in (
        ("Konto", "Konto", 90, "w"),
        ("Kontonavn", "Kontonavn", 220, "w"),
        ("Status", "Status", 110, "w"),
        ("Mappingkilde", "Mappingkilde", 110, "w"),
        ("Baseline", "Baseline", 90, "w"),
        ("Override", "Override", 90, "w"),
        ("Effektiv", "Effektiv", 200, "w"),
        ("Forslag", "Forslag", 200, "w"),
        ("Belop", "Beløp", 110, "e"),
    ):
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=anchor)
    y_scroll = ttk.Scrollbar(tree_host, orient="vertical", command=tree.yview)
    y_scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=y_scroll.set)
    try:
        tree.bind("<<TreeviewSelect>>", lambda _event: update_rl_control_details(page), add="+")
    except Exception:
        pass
    try:
        tree.bind(
            "<Double-Button-1>",
            lambda _event: on_rl_set_override_clicked(page),
            add="+",
        )
    except Exception:
        pass

    page._rl_headline_var = tk.StringVar(value="Velg en konto for RL-detaljer.") if tk is not None else None
    page._rl_current_var = tk.StringVar(value="") if tk is not None else None
    page._rl_suggested_var = tk.StringVar(value="") if tk is not None else None
    page._rl_why_var = tk.StringVar(value="") if tk is not None else None
    ttk.Label(
        detail_host,
        textvariable=page._rl_headline_var,
        style="Section.TLabel",
        wraplength=360,
        justify="left",
    ).pack(anchor="w", fill="x")
    for title, variable in (
        ("Nå", page._rl_current_var),
        ("Forslag", page._rl_suggested_var),
        ("Hvorfor", page._rl_why_var),
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


def rl_filter_value(page: Any) -> str:
    return _clean_text(page._rl_filter_var.get() if page._rl_filter_var is not None else "") or "Alle"


def rl_matches_filter(page: Any, row: Any) -> bool:
    # Gå via page._rl_filter_value() slik at testene kan monkeypatche metoden
    # på et SimpleNamespace-fake uten å sette opp tkinter-variabler.
    selected_filter = page._rl_filter_value()
    if selected_filter == "Alle":
        return True
    if selected_filter == "Klar til forslag":
        return _rl_preview_is_ready_for_suggestion(row)
    return _rl_preview_status_text(row) == selected_filter


def selected_rl_account(page: Any) -> str:
    tree = getattr(page, "_rl_control_tree", None)
    if tree is None:
        return ""
    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    if not selection:
        return ""
    return str(selection[0] or "").strip()


def selected_rl_accounts(page: Any) -> list[str]:
    tree = getattr(page, "_rl_control_tree", None)
    if tree is None:
        return []
    try:
        selection = list(tree.selection())
    except Exception:
        selection = []
    return [str(item or "").strip() for item in selection if str(item or "").strip()]


def refresh_rl_control_rows(page: Any) -> None:
    """Last og render RL-kontroll-grid med Admin-rader fra service.

    Parkert: RL-kontroll er deaktivert i runtime, så denne tåler at widgets
    ikke er bygget og returnerer tidlig hvis så er tilfelle.
    """
    if getattr(page, "_rl_control_tree", None) is None:
        return
    rows = (
        analyse_mapping_service.build_page_admin_rl_rows(page._analyse_page, use_filtered_hb=False)
        if page._analyse_page is not None
        else []
    )
    page._rl_rows = {row.konto: row for row in rows}
    update_rl_control_banner(page)
    populate_rl_control_tree(page)


def update_rl_control_banner(page: Any) -> None:
    var = getattr(page, "_rl_status_var", None)
    if var is None:
        return
    rows = list(page._rl_rows.values())
    if not rows:
        var.set("RL-status: ingen kontoer å diagnosere ennå.")
        return
    try:
        summary = analyse_mapping_service.summarize_rl_status(rows)
    except Exception:
        var.set("")
        return
    var.set(
        "RL-status — {total} kontoer · interval {iv} · override {ov} · "
        "unmapped {um} · sumline {sl} · problem {pb} · forslag {sg}".format(
            total=summary.total,
            iv=summary.interval_count,
            ov=summary.override_count,
            um=summary.unmapped_count,
            sl=summary.sumline_count,
            pb=summary.problem_count,
            sg=summary.suggestion_count,
        )
    )


def populate_rl_control_tree(page: Any) -> None:
    tree = getattr(page, "_rl_control_tree", None)
    if tree is None:
        return
    selected_account_val = selected_rl_account(page)
    try:
        for item in tree.get_children(""):
            tree.delete(item)
    except Exception:
        pass
    if not page._rl_rows:
        update_rl_control_details(page)
        return
    search_text = _clean_text(
        page._rl_search_var.get() if page._rl_search_var is not None else ""
    ).casefold()
    inserted: list[str] = []
    for account_no, row in page._rl_rows.items():
        if not rl_matches_filter(page, row):
            continue
        status_text = _rl_preview_status_text(row)
        mapping_source = _format_rl_mapping_source(row)
        baseline_text = _format_rl_baseline(row)
        override_text = _format_rl_override(row)
        effective_text = _format_rl_current(row)
        suggestion_text = _format_rl_suggestion(row)
        haystack = " ".join(
            [
                account_no,
                _clean_text(row.kontonavn),
                status_text,
                mapping_source,
                baseline_text,
                override_text,
                effective_text,
                suggestion_text,
            ]
        ).casefold()
        if search_text and search_text not in haystack:
            continue
        values = (
            account_no,
            _clean_text(row.kontonavn),
            status_text,
            mapping_source,
            baseline_text,
            override_text,
            effective_text,
            suggestion_text,
            _format_amount(row.belop),
        )
        try:
            tree.insert("", "end", iid=account_no, values=values)
            inserted.append(account_no)
        except Exception:
            continue
    target = selected_account_val if selected_account_val in inserted else (inserted[0] if inserted else "")
    if target:
        try:
            tree.selection_set(target)
            tree.focus(target)
            tree.see(target)
        except Exception:
            pass
    update_rl_control_details(page)


def update_rl_control_details(page: Any) -> None:
    headline_var = getattr(page, "_rl_headline_var", None)
    current_var = getattr(page, "_rl_current_var", None)
    suggested_var = getattr(page, "_rl_suggested_var", None)
    why_var = getattr(page, "_rl_why_var", None)
    if headline_var is None or current_var is None or suggested_var is None or why_var is None:
        return
    account_no = selected_rl_account(page)
    if not account_no:
        headline_var.set("Velg en konto for RL-detaljer.")
        current_var.set("")
        suggested_var.set("")
        why_var.set("")
        return
    row = page._rl_rows.get(account_no)
    if row is None:
        headline_var.set("Velg en konto for RL-detaljer.")
        current_var.set("")
        suggested_var.set("")
        why_var.set("")
        return
    detail = _rl_preview_detail(row)
    headline_var.set(detail["headline"])
    current_var.set(detail["current"])
    suggested_var.set(detail["suggested"])
    why_var.set(detail["why"])


def on_rl_set_override_clicked(page: Any) -> None:
    try:
        from tkinter import messagebox
    except Exception:
        return
    account_no = selected_rl_account(page)
    if not account_no:
        messagebox.showinfo(
            "Sett override",
            "Velg en konto i RL-kontroll-grid før du setter override.",
            parent=page,
        )
        return
    admin_row = page._rl_rows.get(account_no)
    if admin_row is None:
        return
    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
    except Exception:
        client = ""
    if not client:
        messagebox.showerror(
            "Sett override",
            "Ingen aktiv klient – kan ikke lagre override.",
            parent=page,
        )
        return

    regnskapslinjer = (
        getattr(page._analyse_page, "_rl_regnskapslinjer", None)
        if page._analyse_page is not None
        else None
    )

    from views_rl_account_drill import open_account_mapping_dialog

    def _on_changed() -> None:
        after_rl_override_change(page)

    open_account_mapping_dialog(
        page,
        client=client,
        konto=admin_row.konto,
        kontonavn=admin_row.kontonavn,
        current_regnr=admin_row.effective_regnr,
        current_regnskapslinje=admin_row.effective_regnskapslinje,
        suggested_regnr=admin_row.suggested_regnr,
        suggested_regnskapslinje=admin_row.suggested_regnskapslinje,
        suggestion_reason=admin_row.suggestion_reason,
        suggestion_source=admin_row.suggestion_source,
        confidence_bucket=admin_row.confidence_bucket,
        sign_note=admin_row.sign_note,
        regnskapslinjer=regnskapslinjer,
        on_saved=_on_changed,
        on_removed=_on_changed,
    )


def on_rl_clear_override_clicked(page: Any) -> None:
    try:
        from tkinter import messagebox
    except Exception:
        return
    accounts = selected_rl_accounts(page) or [selected_rl_account(page)]
    accounts = [a for a in accounts if a]
    if not accounts:
        messagebox.showinfo(
            "Fjern override",
            "Velg én eller flere kontoer i RL-kontroll-grid.",
            parent=page,
        )
        return
    targets = [
        page._rl_rows[a]
        for a in accounts
        if a in page._rl_rows and page._rl_rows[a].override_regnr is not None
    ]
    if not targets:
        messagebox.showinfo(
            "Fjern override",
            "Ingen av de valgte kontoene har en aktiv override.",
            parent=page,
        )
        return
    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
        year_val = getattr(_session, "year", None)
        year = str(year_val) if year_val else None
    except Exception:
        client = ""
        year = None
    if not client:
        messagebox.showerror(
            "Fjern override",
            "Ingen aktiv klient – kan ikke fjerne override.",
            parent=page,
        )
        return
    konto_text = ", ".join(row.konto for row in targets[:5])
    if len(targets) > 5:
        konto_text += f" (+{len(targets) - 5} til)"
    if not messagebox.askyesno(
        "Fjern override",
        f"Fjerne override for {len(targets)} konto(er)?\n{konto_text}",
        parent=page,
    ):
        return
    errors: list[str] = []
    for row in targets:
        try:
            analyse_mapping_service.clear_account_override(
                client, row.konto, year=year
            )
        except Exception as exc:
            errors.append(f"{row.konto}: {exc}")
    if errors:
        messagebox.showerror(
            "Fjern override",
            "Noen overrides kunne ikke fjernes:\n" + "\n".join(errors),
            parent=page,
        )
    after_rl_override_change(page)


def on_rl_use_suggestion_clicked(page: Any) -> None:
    """Bruk smartforslaget for valgt rad som klient-override.

    Skriver ``suggested_regnr`` som override og refresher gridet. Krever at
    valgt rad har et forslag og at status er ``unmapped`` eller ``sumline``
    (dvs. at den er klar til forslag).
    """
    try:
        from tkinter import messagebox
    except Exception:
        return
    # Gå via metodene på page slik at testene kan monkeypatche enkeltmetoder
    # på et SimpleNamespace-fake.
    account_no = page._selected_rl_account()
    if not account_no:
        messagebox.showinfo(
            "Bruk forslag",
            "Velg en konto i RL-kontroll-grid før du bruker forslag.",
            parent=page,
        )
        return
    admin_row = page._rl_rows.get(account_no)
    if admin_row is None:
        return
    if not _rl_preview_is_ready_for_suggestion(admin_row):
        messagebox.showinfo(
            "Bruk forslag",
            "Valgt konto har ikke noe smartforslag å bruke.",
            parent=page,
        )
        return
    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
        year_val = getattr(_session, "year", None)
        year = str(year_val) if year_val else None
    except Exception:
        client = ""
        year = None
    if not client:
        messagebox.showerror(
            "Bruk forslag",
            "Ingen aktiv klient – kan ikke lagre override.",
            parent=page,
        )
        return
    try:
        analyse_mapping_service.set_account_override(
            client, admin_row.konto, int(admin_row.suggested_regnr), year=year
        )
    except Exception as exc:
        messagebox.showerror(
            "Bruk forslag",
            f"Klarte ikke å lagre override for {admin_row.konto}: {exc}",
            parent=page,
        )
        return
    page._after_rl_override_change()


def on_rl_open_in_analyse_clicked(page: Any) -> None:
    """Bytt til Analyse-fanen og fokuser valgt konto hvis mulig."""
    account_no = selected_rl_account(page)
    if not account_no:
        return
    app = getattr(session, "APP", None)
    analyse_page = getattr(app, "page_analyse", None) or page._analyse_page
    if analyse_page is None:
        return
    show_page = getattr(app, "show_page", None) if app is not None else None
    if callable(show_page):
        try:
            show_page(analyse_page)
        except Exception:
            pass
    # Fall tilbake på _focus_problem_account — den eneste konto-fokus-APIen
    # som faktisk finnes på AnalysePage i dag. Hvis framtidig `focus_account`
    # legges til som public API, foretrekk den.
    for attr in ("focus_account", "_focus_problem_account"):
        focus = getattr(analyse_page, attr, None)
        if callable(focus):
            try:
                focus(account_no)
                return
            except Exception:
                continue


def after_rl_override_change(page: Any) -> None:
    try:
        page._notify_rule_change()
    except Exception:
        pass
