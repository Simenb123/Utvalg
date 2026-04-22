from __future__ import annotations

from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


from page_admin_helpers import (
    _clean_text,
    _format_special_add_lines,
    _int_list,
    _multiline_text,
    _normalize_rulebook_document,
    _parse_special_add_lines,
    _string_list,
)


class _RulebookEditor(ttk.Frame):  # type: ignore[misc]
    def __init__(
        self,
        master: Any,
        *,
        title: str,
        loader: Callable[[], tuple[Any, str]],
        saver: Callable[[Any], str],
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._loader = loader
        self._saver = saver
        self._on_saved = on_saved
        self._document: dict[str, Any] = {"rules": {}}
        self._selected_key = ""
        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._rule_var = tk.StringVar(value="") if tk is not None else None
        self._label_var = tk.StringVar(value="") if tk is not None else None
        self._category_var = tk.StringVar(value="") if tk is not None else None
        self._basis_var = tk.StringVar(value="Endring") if tk is not None else None
        self._expected_sign_var = tk.StringVar(value="") if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Ny", command=self.new_rule).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Slett", command=self.delete_selected).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=4, rowspan=2, padx=(8, 0))

        ttk.Label(
            self,
            text="Primær flate for A07-regler: aliaser, ekskluderinger, intervaller, basis, scoring og special_add. Konseptaliaser er kun avansert kompatibilitet.",
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
        ).grid(row=1, column=0, sticky="ew")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew")

        list_host = ttk.Frame(body, padding=(8, 0, 4, 8))
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(1, weight=1)
        body.add(list_host, weight=2)

        search_row = ttk.Frame(list_host)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Søk:").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_row, textvariable=self._search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        try:
            search_entry.bind("<KeyRelease>", lambda _event: self._refresh_tree(), add="+")
        except Exception:
            pass

        tree_columns = ("Kode", "Label", "Intervall", "Basis")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, width in (("Kode", 180), ("Label", 220), ("Intervall", 150), ("Basis", 80)):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="w")
        y_scroll = ttk.Scrollbar(list_host, orient="vertical", command=tree.yview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)
        try:
            tree.bind("<<TreeviewSelect>>", lambda _event: self._handle_tree_select(), add="+")
        except Exception:
            pass

        detail_host = ttk.Frame(body, padding=(4, 0, 8, 8))
        detail_host.columnconfigure(1, weight=1)
        detail_host.rowconfigure(4, weight=1)
        detail_host.rowconfigure(6, weight=1)
        detail_host.rowconfigure(8, weight=1)
        detail_host.rowconfigure(10, weight=1)
        body.add(detail_host, weight=3)

        ttk.Label(detail_host, text="Kode-id").grid(row=0, column=0, sticky="w")
        ttk.Entry(detail_host, textvariable=self._rule_var).grid(row=0, column=1, sticky="ew", pady=(0, 6))

        meta_row = ttk.Frame(detail_host)
        meta_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        meta_row.columnconfigure(1, weight=1)
        meta_row.columnconfigure(3, weight=1)
        ttk.Label(meta_row, text="Label").grid(row=0, column=0, sticky="w")
        ttk.Entry(meta_row, textvariable=self._label_var).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(meta_row, text="Kategori").grid(row=0, column=2, sticky="w")
        ttk.Entry(meta_row, textvariable=self._category_var).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        config_row = ttk.Frame(detail_host)
        config_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(config_row, text="Basis").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            config_row,
            textvariable=self._basis_var,
            values=("", "Endring", "UB", "IB"),
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(config_row, text="Forventet sign").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            config_row,
            textvariable=self._expected_sign_var,
            values=("", "-1", "0", "1"),
            state="readonly",
            width=8,
        ).grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(detail_host, text="Keywords").grid(row=3, column=0, sticky="w")
        ttk.Label(detail_host, text="Én verdi per linje", style="Muted.TLabel").grid(row=3, column=1, sticky="e")
        self._keywords_text = tk.Text(detail_host, height=7, wrap="word", undo=True)
        self._keywords_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Ekskluder keywords").grid(row=5, column=0, sticky="w")
        self._exclude_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._exclude_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Kontointervall").grid(row=7, column=0, sticky="w")
        self._ranges_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._ranges_text.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Boost-kontoer").grid(row=9, column=0, sticky="w")
        ttk.Label(detail_host, text="Ett kontonummer per linje", style="Muted.TLabel").grid(row=9, column=1, sticky="e")
        self._boost_text = tk.Text(detail_host, height=4, wrap="word", undo=True)
        self._boost_text.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Special add").grid(row=11, column=0, sticky="w")
        ttk.Label(
            detail_host,
            text="Format: konto | basis | weight",
            style="Muted.TLabel",
        ).grid(row=11, column=1, sticky="e")
        self._special_add_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._special_add_text.grid(row=12, column=0, columnspan=2, sticky="nsew")

        self.reload()

    def _rules(self) -> dict[str, dict[str, Any]]:
        rules = self._document.get("rules", {})
        if isinstance(rules, dict):
            return rules
        self._document["rules"] = {}
        return self._document["rules"]

    def _set_text_widget(self, widget: Any, value: str) -> None:
        try:
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        except Exception:
            return

    def _get_text_widget(self, widget: Any) -> str:
        try:
            return widget.get("1.0", "end").strip()
        except Exception:
            return ""

    def _clear_form(self) -> None:
        for variable in (self._rule_var, self._label_var, self._category_var, self._expected_sign_var):
            if variable is not None:
                variable.set("")
        if self._basis_var is not None:
            self._basis_var.set("Endring")
        for widget in (
            self._keywords_text,
            self._exclude_text,
            self._ranges_text,
            self._boost_text,
            self._special_add_text,
        ):
            self._set_text_widget(widget, "")

    def _load_form(self, rule_id: str) -> None:
        payload = self._rules().get(rule_id, {})
        if self._rule_var is not None:
            self._rule_var.set(rule_id)
        if self._label_var is not None:
            self._label_var.set(_clean_text(payload.get("label")) or rule_id)
        if self._category_var is not None:
            self._category_var.set(_clean_text(payload.get("category")))
        if self._basis_var is not None:
            self._basis_var.set(_clean_text(payload.get("basis")) or "Endring")
        if self._expected_sign_var is not None:
            self._expected_sign_var.set(_clean_text(payload.get("expected_sign")))
        self._set_text_widget(self._keywords_text, _multiline_text(payload.get("keywords")))
        self._set_text_widget(self._exclude_text, _multiline_text(payload.get("exclude_keywords")))
        self._set_text_widget(self._ranges_text, _multiline_text(payload.get("allowed_ranges")))
        self._set_text_widget(self._boost_text, _multiline_text(payload.get("boost_accounts")))
        self._set_text_widget(self._special_add_text, _format_special_add_lines(payload.get("special_add")))

    def _commit_form(self, *, show_errors: bool) -> bool:
        rules = self._rules()
        old_key = _clean_text(self._selected_key)
        typed_key = _clean_text(self._rule_var.get() if self._rule_var is not None else "")
        rule_id = typed_key or old_key
        has_content = any(
            (
                self._label_var.get() if self._label_var is not None else "",
                self._get_text_widget(self._keywords_text),
                self._get_text_widget(self._exclude_text),
                self._get_text_widget(self._ranges_text),
                self._get_text_widget(self._boost_text),
                self._get_text_widget(self._special_add_text),
            )
        )
        if not rule_id:
            if show_errors and has_content and messagebox is not None:
                messagebox.showerror(self._title, "Kode-id mangler.")
                return False
            return True
        if old_key and rule_id != old_key and rule_id in rules:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, f"Regelen '{rule_id}' finnes allerede.")
            return False
        payload: dict[str, Any] = {}
        label = _clean_text(self._label_var.get() if self._label_var is not None else "")
        if label:
            payload["label"] = label
        category = _clean_text(self._category_var.get() if self._category_var is not None else "")
        if category:
            payload["category"] = category
        keywords = _string_list(self._get_text_widget(self._keywords_text))
        if keywords:
            payload["keywords"] = keywords
        exclude_keywords = _string_list(self._get_text_widget(self._exclude_text))
        if exclude_keywords:
            payload["exclude_keywords"] = exclude_keywords
        allowed_ranges = _string_list(self._get_text_widget(self._ranges_text))
        if allowed_ranges:
            payload["allowed_ranges"] = allowed_ranges
        boost_accounts = _int_list(self._get_text_widget(self._boost_text))
        if boost_accounts:
            payload["boost_accounts"] = boost_accounts
        basis = _clean_text(self._basis_var.get() if self._basis_var is not None else "")
        if basis:
            payload["basis"] = basis
        expected_sign = _clean_text(self._expected_sign_var.get() if self._expected_sign_var is not None else "")
        if expected_sign:
            try:
                parsed_sign = int(expected_sign)
            except Exception:
                parsed_sign = None
            if parsed_sign in (-1, 0, 1):
                payload["expected_sign"] = parsed_sign
        special_add = _parse_special_add_lines(self._get_text_widget(self._special_add_text))
        if special_add:
            payload["special_add"] = special_add
        if old_key and rule_id != old_key:
            rules.pop(old_key, None)
        rules[rule_id] = payload
        self._selected_key = rule_id
        if self._rule_var is not None:
            self._rule_var.set(rule_id)
        return True

    def _refresh_tree(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        selected = _clean_text(self._selected_key)
        search_text = _clean_text(self._search_var.get() if self._search_var is not None else "").casefold()
        try:
            for item in tree.get_children(""):
                tree.delete(item)
        except Exception:
            pass
        for rule_id, payload in sorted(self._rules().items(), key=lambda item: item[0].casefold()):
            label = _clean_text(payload.get("label"))
            label_display = label or rule_id
            ranges_preview = ", ".join(_string_list(payload.get("allowed_ranges"))[:2])
            basis = _clean_text(payload.get("basis"))
            haystack = " ".join(
                [
                    rule_id,
                    label_display,
                    ranges_preview,
                    ", ".join(_string_list(payload.get("keywords"))[:3]),
                    ", ".join(_string_list(payload.get("exclude_keywords"))[:5]),
                    ", ".join(str(value) for value in _int_list(payload.get("boost_accounts"))[:5]),
                ]
            ).casefold()
            if search_text and search_text not in haystack:
                continue
            try:
                tree.insert("", "end", iid=rule_id, values=(rule_id, label_display, ranges_preview, basis))
            except Exception:
                continue
        if selected and tree.exists(selected):
            try:
                tree.selection_set(selected)
                tree.focus(selected)
                tree.see(selected)
            except Exception:
                pass

    def _handle_tree_select(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        next_key = _clean_text(selection[0])
        if not self._commit_form(show_errors=True):
            if self._selected_key and tree.exists(self._selected_key):
                try:
                    tree.selection_set(self._selected_key)
                except Exception:
                    pass
            return
        self._selected_key = next_key
        self._load_form(next_key)

    def new_rule(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        self._selected_key = ""
        self._clear_form()
        tree = getattr(self, "_tree", None)
        if tree is not None:
            try:
                tree.selection_remove(tree.selection())
            except Exception:
                pass

    def delete_selected(self) -> None:
        selected = _clean_text(self._selected_key)
        if not selected:
            return
        self._rules().pop(selected, None)
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()

    def reload(self) -> None:
        document, path_text = self._loader()
        self._document = _normalize_rulebook_document(document)
        if self._path_var is not None:
            self._path_var.set(path_text)
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()
        keys = sorted(self._rules().keys(), key=str.casefold)
        if keys:
            self._selected_key = keys[0]
            self._load_form(keys[0])
            tree = getattr(self, "_tree", None)
            if tree is not None and tree.exists(keys[0]):
                try:
                    tree.selection_set(keys[0])
                    tree.focus(keys[0])
                    tree.see(keys[0])
                except Exception:
                    pass

    def save(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        try:
            saved_path = self._saver(_normalize_rulebook_document(self._document))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        self._refresh_tree()
        if self._on_saved is not None:
            self._on_saved()
