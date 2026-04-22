from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .page_paths import (
    build_rule_form_values,
    build_rule_payload,
    copy_rulebook_to_storage,
    default_global_rulebook_path,
    load_matcher_settings,
    load_rulebook_document,
    save_matcher_settings,
    save_rulebook_document,
)


def build_source_overview_rows(
    *,
    a07_text: str,
    tb_text: str,
    mapping_text: str,
    rulebook_text: str,
    history_text: str,
) -> list[tuple[str, str]]:
    return [
        ("A07-kilde", a07_text),
        ("Saldobalanse", tb_text),
        ("Mapping", mapping_text),
        ("Rulebook", rulebook_text),
        ("Historikk", history_text),
    ]


def open_source_overview(page) -> None:
    existing = page._source_overview_window
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return
        except Exception:
            pass

    win = tk.Toplevel(page)
    win.title("A07-kilder")
    win.geometry("760x320")
    page._source_overview_window = win

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text="Kildeinfo for valgt klient/aar. Dette er bare referanseinfo, ikke en egen arbeidsflate.",
        style="Muted.TLabel",
        wraplength=700,
        justify="left",
    ).pack(anchor="w")

    grid = ttk.Frame(body)
    grid.pack(fill="both", expand=True, pady=(12, 0))
    grid.columnconfigure(1, weight=1)

    for row_idx, (label_text, value_text) in enumerate(
        build_source_overview_rows(
            a07_text=page.a07_path_var.get(),
            tb_text=page.tb_path_var.get(),
            mapping_text=page.mapping_path_var.get(),
            rulebook_text=page.rulebook_path_var.get(),
            history_text=page.history_path_var.get(),
        )
    ):
        ttk.Label(grid, text=f"{label_text}:", style="Section.TLabel").grid(
            row=row_idx,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=(0, 8),
        )
        ttk.Label(
            grid,
            text=value_text,
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=row_idx, column=1, sticky="nw", pady=(0, 8))

    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(8, 0))
    ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

    def _on_close() -> None:
        try:
            win.destroy()
        finally:
            page._source_overview_window = None

    win.protocol("WM_DELETE_WINDOW", _on_close)


def open_mapping_overview(page, mapping_columns) -> None:
    existing = getattr(page, "_mapping_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return
        except Exception:
            pass

    win = tk.Toplevel(page)
    win.title("A07-mappinger")
    win.geometry("760x520")
    page._mapping_window = win

    header = ttk.Frame(win, padding=10)
    header.pack(fill="x")
    ttk.Label(
        header,
        text="Lagrede mappinger for valgt klient/aar. Bruk dette vinduet ved behov, ikke som hovedarbeidsflate.",
        style="Muted.TLabel",
        wraplength=700,
        justify="left",
    ).pack(anchor="w")

    summary_var = tk.StringVar(value="")
    ttk.Label(header, textvariable=summary_var, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    body = ttk.Frame(win, padding=(10, 0, 10, 10))
    body.pack(fill="both", expand=True)
    tree = page._build_tree_tab(body, mapping_columns)

    def _refresh_window_tree() -> None:
        page._fill_tree(tree, page.mapping_df, mapping_columns, iid_column="Konto")
        summary_var.set(f"Antall mappinger: {len(page.mapping_df)}")

    def _selected_account() -> str | None:
        selection = tree.selection()
        if not selection:
            return None
        return str(selection[0]).strip() or None

    def _sync_hidden_selection() -> bool:
        account = _selected_account()
        if not account:
            messagebox.showinfo("A07", "Velg en mappingrad forst.", parent=win)
            return False
        try:
            page.tree_mapping.selection_set(account)
            page.tree_mapping.focus(account)
            page.tree_mapping.see(account)
        except Exception:
            pass
        return True

    actions = ttk.Frame(win, padding=(10, 0, 10, 10))
    actions.pack(fill="x")
    ttk.Button(
        actions,
        text="Rediger valgt",
        command=lambda: (_sync_hidden_selection() and page._open_manual_mapping_clicked(), _refresh_window_tree()),
    ).pack(side="left")
    ttk.Button(
        actions,
        text="Fjern valgt",
        command=lambda: (_sync_hidden_selection() and page._remove_selected_mapping(), _refresh_window_tree()),
    ).pack(side="left", padx=(6, 0))
    ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

    def _on_close() -> None:
        try:
            win.destroy()
        finally:
            page._mapping_window = None

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh_window_tree()


def open_matcher_admin(
    page,
    *,
    matcher_settings_defaults: dict[str, float | int],
    format_aliases_editor,
    parse_aliases_editor,
) -> None:
    existing = page._matcher_admin_window
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return
        except Exception:
            pass

    rulebook_path = page.rulebook_path or default_global_rulebook_path()
    document = load_rulebook_document(rulebook_path)
    settings = load_matcher_settings()

    win = tk.Toplevel(page)
    win.title("Matcher-admin")
    win.geometry("1100x760")
    page._matcher_admin_window = win

    notebook = ttk.Notebook(win)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    tab_rules = ttk.Frame(notebook)
    tab_settings = ttk.Frame(notebook)
    notebook.add(tab_rules, text="Rulebook")
    notebook.add(tab_settings, text="Innstillinger")

    status_var = tk.StringVar(
        value="Rediger regler og innstillinger her. Lagre deretter og oppdater A07-forslag."
    )

    header = ttk.Frame(tab_rules, padding=(0, 0, 0, 8))
    header.pack(fill="x")
    ttk.Label(
        header,
        text=f"Global rulebook: {rulebook_path}",
        style="Muted.TLabel",
        wraplength=1000,
        justify="left",
    ).pack(anchor="w")

    split = ttk.Panedwindow(tab_rules, orient="horizontal")
    split.pack(fill="both", expand=True)

    left = ttk.Frame(split, padding=(0, 0, 8, 0))
    right = ttk.Frame(split)
    split.add(left, weight=1)
    split.add(right, weight=3)

    code_tree = ttk.Treeview(left, columns=("Kode", "Status", "Label"), show="headings", height=20)
    for column_id, heading, width in (
        ("Kode", "Kode", 180),
        ("Status", "Status", 90),
        ("Label", "Label", 180),
    ):
        code_tree.heading(column_id, text=heading)
        code_tree.column(column_id, width=width, anchor="w")
    code_tree.pack(fill="both", expand=True)

    left_buttons = ttk.Frame(left, padding=(0, 8, 0, 0))
    left_buttons.pack(fill="x")

    form = ttk.Frame(right)
    form.pack(fill="both", expand=True)
    for idx in range(2):
        form.columnconfigure(idx, weight=1 if idx == 1 else 0)

    code_var = tk.StringVar(value="")
    label_var = tk.StringVar(value="")
    category_var = tk.StringVar(value="")
    boost_var = tk.StringVar(value="")
    basis_var = tk.StringVar(value="")
    expected_sign_var = tk.StringVar(value="")

    ttk.Label(form, text="Kode").grid(row=0, column=0, sticky="w", pady=(0, 4))
    ttk.Entry(form, textvariable=code_var, width=30).grid(row=0, column=1, sticky="ew", pady=(0, 4))
    ttk.Label(form, text="Label").grid(row=1, column=0, sticky="w", pady=(0, 4))
    ttk.Entry(form, textvariable=label_var).grid(row=1, column=1, sticky="ew", pady=(0, 4))
    ttk.Label(form, text="Kategori").grid(row=2, column=0, sticky="w", pady=(0, 4))
    ttk.Entry(form, textvariable=category_var).grid(row=2, column=1, sticky="ew", pady=(0, 4))
    ttk.Label(form, text="Boost-kontoer").grid(row=3, column=0, sticky="w", pady=(0, 4))
    ttk.Entry(form, textvariable=boost_var).grid(row=3, column=1, sticky="ew", pady=(0, 4))
    ttk.Label(form, text="Basis").grid(row=4, column=0, sticky="w", pady=(0, 4))
    ttk.Combobox(
        form,
        textvariable=basis_var,
        state="readonly",
        values=["", "UB", "IB", "Endring", "Debet", "Kredit"],
        width=18,
    ).grid(row=4, column=1, sticky="w", pady=(0, 4))
    ttk.Label(form, text="Forventet fortegn").grid(row=5, column=0, sticky="w", pady=(0, 4))
    ttk.Combobox(
        form,
        textvariable=expected_sign_var,
        state="readonly",
        values=["", "-1", "0", "1"],
        width=10,
    ).grid(row=5, column=1, sticky="w", pady=(0, 4))

    ttk.Label(
        form,
        text="Tillatte konto-intervaller\nEtt intervall per linje, f.eks. 5000-5999 eller 5210",
    ).grid(row=6, column=0, sticky="nw", pady=(8, 4))
    allowed_text = tk.Text(form, height=5, width=60)
    allowed_text.grid(row=6, column=1, sticky="ew", pady=(8, 4))

    ttk.Label(
        form,
        text="Nokkelord\nKomma eller én per linje",
    ).grid(row=7, column=0, sticky="nw", pady=(0, 4))
    keywords_text = tk.Text(form, height=5, width=60)
    keywords_text.grid(row=7, column=1, sticky="ew", pady=(0, 4))

    ttk.Label(
        form,
        text="Ekskluder noekkelord\nKomma eller en per linje",
    ).grid(row=8, column=0, sticky="nw", pady=(0, 4))
    exclude_keywords_text = tk.Text(form, height=4, width=60)
    exclude_keywords_text.grid(row=8, column=1, sticky="ew", pady=(0, 4))

    ttk.Label(
        form,
        text="Special add\nFormat: konto | basis | weight",
    ).grid(row=9, column=0, sticky="nw", pady=(0, 4))
    special_text = tk.Text(form, height=5, width=60)
    special_text.grid(row=9, column=1, sticky="ew", pady=(0, 4))

    ttk.Label(
        form,
        text="Aliaser\nFormat: noekkel = alias1, alias2",
    ).grid(row=10, column=0, sticky="nw", pady=(8, 4))
    aliases_text = tk.Text(form, height=8, width=60)
    aliases_text.grid(row=10, column=1, sticky="nsew", pady=(8, 4))
    form.rowconfigure(10, weight=1)

    settings_form = ttk.Frame(tab_settings, padding=10)
    settings_form.pack(fill="both", expand=True)
    for idx in range(2):
        settings_form.columnconfigure(idx, weight=1 if idx == 1 else 0)

    settings_vars = {
        name: tk.StringVar(value=str(settings[name]))
        for name in matcher_settings_defaults
    }
    settings_rows = (
        ("tolerance_rel", "Relativ toleranse"),
        ("tolerance_abs", "Absolutt toleranse"),
        ("max_combo", "Maks konto-kombinasjon"),
        ("candidates_per_code", "Kandidater per kode"),
        ("top_suggestions_per_code", "Viste forslag per kode"),
        ("historical_account_boost", "Historikkboost konto"),
        ("historical_combo_boost", "Historikkboost kombinasjon"),
    )
    for row_idx, (name, label) in enumerate(settings_rows):
        ttk.Label(settings_form, text=label).grid(row=row_idx, column=0, sticky="w", pady=4)
        ttk.Entry(settings_form, textvariable=settings_vars[name], width=18).grid(
            row=row_idx, column=1, sticky="w", pady=4
        )

    ttk.Label(
        settings_form,
        text="Disse innstillingene styrer solverens toleranser, kombinasjonsdybde og historikkprior.",
        style="Muted.TLabel",
        wraplength=760,
        justify="left",
    ).grid(row=len(settings_rows), column=0, columnspan=2, sticky="w", pady=(10, 0))

    footer = ttk.Frame(win, padding=(10, 0, 10, 10))
    footer.pack(fill="x")
    ttk.Label(footer, textvariable=status_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
    action_row = ttk.Frame(footer)
    action_row.pack(fill="x")

    state: dict[str, object] = {
        "document": document,
        "rulebook_path": rulebook_path,
        "status_var": status_var,
    }
    page._matcher_admin_state = state

    def _rules() -> dict[str, dict[str, object]]:
        raw_rules = document.setdefault("rules", {})
        if not isinstance(raw_rules, dict):
            document["rules"] = {}
            raw_rules = document["rules"]
        return raw_rules  # type: ignore[return-value]

    def _available_codes() -> list[str]:
        codes = {
            str(code).strip()
            for code in _rules().keys()
            if str(code).strip()
        }
        if page.workspace.a07_df is not None and not page.workspace.a07_df.empty and "Kode" in page.workspace.a07_df.columns:
            codes.update(
                str(code).strip()
                for code in page.workspace.a07_df["Kode"].astype(str).tolist()
                if str(code).strip()
            )
        return sorted(codes, key=lambda value: (value.lower(), value))

    def _read_text(widget: tk.Text) -> str:
        return widget.get("1.0", "end").strip()

    def _write_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    def _selected_code() -> str | None:
        selection = code_tree.selection()
        if not selection:
            return None
        return str(selection[0]).strip() or None

    def _load_rule_to_form(code: str | None) -> None:
        code_s = str(code or "").strip()
        raw = _rules().get(code_s, {}) if code_s else {}
        values = build_rule_form_values(code_s, raw)
        code_var.set(values["code"])
        label_var.set(values["label"])
        category_var.set(values["category"])
        boost_var.set(values["boost_accounts"])
        basis_var.set(values["basis"])
        expected_sign_var.set(values["expected_sign"])
        _write_text(allowed_text, values["allowed_ranges"])
        _write_text(keywords_text, values["keywords"])
        _write_text(exclude_keywords_text, values.get("exclude_keywords", ""))
        _write_text(special_text, values["special_add"])
        status_var.set(f"Redigerer regel for {code_s or 'ny kode'}.")

    def _clear_form(prefill_code: str | None = None) -> None:
        _load_rule_to_form(prefill_code)

    def _refresh_code_tree(selected_code: str | None = None) -> None:
        current = selected_code or _selected_code()
        for item in code_tree.get_children():
            code_tree.delete(item)

        for code in _available_codes():
            raw = _rules().get(code)
            has_rule = isinstance(raw, dict) and bool(raw)
            label = str((raw or {}).get("label") or "").strip() if isinstance(raw, dict) else ""
            code_tree.insert(
                "",
                "end",
                iid=code,
                values=(code, "Regel" if has_rule else "Ingen regel", label),
            )

        children = code_tree.get_children()
        if not children:
            _clear_form(page._selected_control_code())
            return

        target = current if current and current in children else children[0]
        code_tree.selection_set(target)
        code_tree.focus(target)
        code_tree.see(target)
        _load_rule_to_form(target)

    def _save_rule() -> str | None:
        existing_code = _selected_code()
        existing_rule = _rules().get(existing_code or "", {})
        try:
            code, payload = build_rule_payload(
                {
                    "code": code_var.get(),
                    "label": label_var.get(),
                    "category": category_var.get(),
                    "allowed_ranges": _read_text(allowed_text),
                    "keywords": _read_text(keywords_text),
                    "exclude_keywords": _read_text(exclude_keywords_text),
                    "boost_accounts": boost_var.get(),
                    "basis": basis_var.get(),
                    "expected_sign": expected_sign_var.get(),
                    "special_add": _read_text(special_text),
                },
                existing_rule=existing_rule,
            )
        except Exception as exc:
            messagebox.showerror("Matcher-admin", str(exc), parent=win)
            return None

        if existing_code and existing_code != code:
            _rules().pop(existing_code, None)
        _rules()[code] = payload
        _refresh_code_tree(code)
        status_var.set(f"Regel lagret i admin-vinduet for {code}.")
        return code

    def _delete_rule() -> None:
        code = _selected_code() or str(code_var.get() or "").strip()
        if not code or code not in _rules():
            messagebox.showinfo("Matcher-admin", "Velg en regel som finnes først.", parent=win)
            return
        if not messagebox.askyesno(
            "Matcher-admin",
            f"Vil du slette regelen for {code} fra global rulebook?",
            parent=win,
        ):
            return
        _rules().pop(code, None)
        _refresh_code_tree()
        status_var.set(f"Regel slettet for {code}.")

    def _save_admin(refresh_after: bool) -> None:
        current_code = str(code_var.get() or "").strip()
        form_has_content = any(
            [
                str(label_var.get() or "").strip(),
                str(category_var.get() or "").strip(),
                str(boost_var.get() or "").strip(),
                str(basis_var.get() or "").strip(),
                str(expected_sign_var.get() or "").strip(),
                _read_text(allowed_text),
                _read_text(keywords_text),
                _read_text(exclude_keywords_text),
                _read_text(special_text),
            ]
        )
        if form_has_content or current_code in _rules():
            if _save_rule() is None:
                return

        document["aliases"] = parse_aliases_editor(_read_text(aliases_text))
        document["rules"] = _rules()
        try:
            saved_rulebook = save_rulebook_document(rulebook_path, document)
            saved_settings = save_matcher_settings({name: var.get() for name, var in settings_vars.items()})
            page.rulebook_path = saved_rulebook
            page.matcher_settings = load_matcher_settings(saved_settings)
            page.rulebook_path_var.set(f"Rulebook: {saved_rulebook}")
            if refresh_after:
                page._refresh_core(focus_code=page._selected_control_code())
                page.status_var.set("Matcher-admin lagret og A07-forslag oppdatert.")
            else:
                page.status_var.set("Matcher-admin lagret.")
            status_var.set(
                f"Lagret global rulebook og matcher-innstillinger til {saved_rulebook.parent}."
            )
        except Exception as exc:
            messagebox.showerror("Matcher-admin", f"Kunne ikke lagre matcher-admin:\n{exc}", parent=win)

    ttk.Button(
        left_buttons,
        text="Ny regel",
        command=lambda: _clear_form(page._selected_control_code()),
    ).pack(side="left")
    ttk.Button(left_buttons, text="Slett regel", command=_delete_rule).pack(side="left", padx=(6, 0))

    code_tree.bind("<<TreeviewSelect>>", lambda _event: _load_rule_to_form(_selected_code()))

    _write_text(aliases_text, format_aliases_editor(document.get("aliases", {})))

    ttk.Button(action_row, text="Lagre regel", command=_save_rule).pack(side="left")
    ttk.Button(action_row, text="Lagre admin", command=lambda: _save_admin(False)).pack(side="left", padx=(6, 0))
    ttk.Button(
        action_row,
        text="Lagre og oppdater A07",
        command=lambda: _save_admin(True),
    ).pack(side="left", padx=(6, 0))
    ttk.Button(action_row, text="Lukk", command=win.destroy).pack(side="right")

    def _on_close() -> None:
        try:
            win.destroy()
        finally:
            page._matcher_admin_window = None
            page._matcher_admin_state = None

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh_code_tree(page._selected_control_code())
