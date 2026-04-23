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
    _CATALOG_AREA_PAYROLL_TAGS,
    _catalog_area_config,
    _catalog_area_matches,
    _catalog_area_options,
    _clean_text,
    _multiline_text,
    _normalize_catalog_document,
    _string_list,
)


class _CatalogEditor(ttk.Frame):  # type: ignore[misc]
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
        self._document: dict[str, Any] = {"groups": [], "tags": []}
        self._selected_key = ""
        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._area_var = tk.StringVar(value=_CATALOG_AREA_PAYROLL_TAGS) if tk is not None else None
        self._description_var = (
            tk.StringVar(value=_catalog_area_config(_CATALOG_AREA_PAYROLL_TAGS)["description"]) if tk is not None else None
        )
        self._id_var = tk.StringVar(value="") if tk is not None else None
        self._label_var = tk.StringVar(value="") if tk is not None else None
        self._category_var = tk.StringVar(value="") if tk is not None else None
        self._sort_var = tk.StringVar(value="0") if tk is not None else None
        self._active_var = tk.BooleanVar(value=True) if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Ny", command=self.new_entry).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Slett", command=self.delete_selected).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=4, rowspan=2, padx=(8, 0))

        ttk.Label(self, textvariable=self._description_var, style="Muted.TLabel", padding=(8, 0, 8, 4)).grid(
            row=1, column=0, sticky="ew"
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew")

        list_host = ttk.Frame(body, padding=(8, 0, 4, 8))
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(1, weight=1)
        body.add(list_host, weight=2)

        controls = ttk.Frame(list_host)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        controls.columnconfigure(3, weight=1)
        ttk.Label(controls, text="Område:").grid(row=0, column=0, sticky="w")
        area_combo = ttk.Combobox(
            controls,
            textvariable=self._area_var,
            values=_catalog_area_options(),
            state="readonly",
            width=24,
        )
        area_combo.grid(row=0, column=1, sticky="w", padx=(6, 12))
        try:
            area_combo.bind("<<ComboboxSelected>>", lambda _event: self._switch_area(), add="+")
        except Exception:
            pass
        ttk.Label(controls, text="Søk:").grid(row=0, column=2, sticky="w")
        search_entry = ttk.Entry(controls, textvariable=self._search_var)
        search_entry.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        try:
            search_entry.bind("<KeyRelease>", lambda _event: self._refresh_tree(), add="+")
        except Exception:
            pass

        tree_columns = ("Id", "Label", "Kategori", "Scope")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, width in (("Id", 180), ("Label", 220), ("Kategori", 150), ("Scope", 150)):
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
        body.add(detail_host, weight=3)

        ttk.Label(detail_host, text="Id").grid(row=0, column=0, sticky="w")
        ttk.Entry(detail_host, textvariable=self._id_var).grid(row=0, column=1, sticky="ew", pady=(0, 6))

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
        ttk.Checkbutton(config_row, text="Aktiv", variable=self._active_var).grid(row=0, column=0, sticky="w")
        ttk.Label(config_row, text="Sortering").grid(row=0, column=1, sticky="w", padx=(16, 0))
        ttk.Entry(config_row, textvariable=self._sort_var, width=10).grid(row=0, column=2, sticky="w", padx=(6, 0))

        ttk.Label(detail_host, text="Gjelder for").grid(row=3, column=0, sticky="w")
        ttk.Label(detail_host, text="Én scope per linje", style="Muted.TLabel").grid(row=3, column=1, sticky="e")
        self._applies_text = tk.Text(detail_host, height=6, wrap="word", undo=True)
        self._applies_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Aliaser").grid(row=5, column=0, sticky="w")
        self._aliases_text = tk.Text(detail_host, height=8, wrap="word", undo=True)
        self._aliases_text.grid(row=6, column=0, columnspan=2, sticky="nsew")

        ttk.Label(detail_host, text="Ekskluder aliaser").grid(row=7, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            detail_host,
            text="Ett ord/uttrykk per linje",
            style="Muted.TLabel",
        ).grid(row=7, column=1, sticky="e", pady=(8, 0))
        self._exclude_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._exclude_text.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(0, 4))
        ttk.Label(
            detail_host,
            text=(
                "Negative aliaser blokkerer direkte katalogtreff når de matcher "
                "kontonavn eller kontobruk. Eksempel på Post 100 Lønn o.l.: legg "
                "inn «aga» og «arbeidsgiveravgift» for å hindre at kontoer som "
                "«5422 AGA av påløpt lønn» drar mot Post 100."
            ),
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.reload()

    def _area_config(self) -> dict[str, Any]:
        return _catalog_area_config(self._area_var.get() if self._area_var is not None else "")

    def _bucket_name(self) -> str:
        return str(self._area_config().get("bucket") or "groups")

    def _area_categories(self) -> tuple[str, ...]:
        categories = self._area_config().get("categories")
        return tuple(categories) if isinstance(categories, tuple) else tuple(categories or ())

    def _default_category(self) -> str:
        return _clean_text(self._area_config().get("default_category"))

    def _entries(self) -> list[dict[str, Any]]:
        bucket_name = self._bucket_name()
        raw_entries = self._document.get(bucket_name, [])
        if isinstance(raw_entries, list):
            return raw_entries
        self._document[bucket_name] = []
        return self._document[bucket_name]

    def _visible_entries(self) -> list[dict[str, Any]]:
        allowed_categories = self._area_categories()
        return [entry for entry in self._entries() if _catalog_area_matches(entry, allowed_categories)]

    def _update_area_text(self) -> None:
        if self._description_var is not None:
            self._description_var.set(_clean_text(self._area_config().get("description")))

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

    def _find_entry(self, entry_id: str) -> dict[str, Any] | None:
        target = _clean_text(entry_id)
        if not target:
            return None
        for entry in self._entries():
            if _clean_text(entry.get("id")) == target:
                return entry
        return None

    def _clear_form(self) -> None:
        if self._id_var is not None:
            self._id_var.set("")
        if self._label_var is not None:
            self._label_var.set("")
        if self._category_var is not None:
            self._category_var.set(self._default_category())
        if self._sort_var is not None:
            self._sort_var.set("0")
        if self._active_var is not None:
            self._active_var.set(True)
        self._set_text_widget(self._applies_text, "")
        self._set_text_widget(self._aliases_text, "")
        self._set_text_widget(self._exclude_text, "")

    def _load_form(self, entry_id: str) -> None:
        entry = self._find_entry(entry_id) or {}
        if self._id_var is not None:
            self._id_var.set(_clean_text(entry.get("id")))
        if self._label_var is not None:
            self._label_var.set(_clean_text(entry.get("label")))
        if self._category_var is not None:
            self._category_var.set(_clean_text(entry.get("category")))
        if self._sort_var is not None:
            self._sort_var.set(str(int(entry.get("sort_order", 0) or 0)))
        if self._active_var is not None:
            self._active_var.set(bool(entry.get("active", True)))
        self._set_text_widget(self._applies_text, _multiline_text(entry.get("applies_to")))
        self._set_text_widget(self._aliases_text, _multiline_text(entry.get("aliases")))
        self._set_text_widget(self._exclude_text, _multiline_text(entry.get("exclude_aliases")))

    def _remove_entry(self, entry_id: str) -> None:
        target = _clean_text(entry_id)
        if not target:
            return
        bucket = self._entries()
        bucket[:] = [entry for entry in bucket if _clean_text(entry.get("id")) != target]

    def _commit_form(self, *, show_errors: bool) -> bool:
        old_key = _clean_text(self._selected_key)
        typed_key = _clean_text(self._id_var.get() if self._id_var is not None else "")
        entry_id = typed_key or old_key
        has_content = any(
            (
                self._label_var.get() if self._label_var is not None else "",
                self._category_var.get() if self._category_var is not None else "",
                self._get_text_widget(self._applies_text),
                self._get_text_widget(self._aliases_text),
                self._get_text_widget(self._exclude_text),
            )
        )
        if not entry_id:
            if show_errors and has_content and messagebox is not None:
                messagebox.showerror(self._title, "Id mangler.")
                return False
            return True
        existing = self._find_entry(entry_id)
        if existing is not None and entry_id != old_key:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, f"Oppføringen '{entry_id}' finnes allerede.")
            return False
        label = _clean_text(self._label_var.get() if self._label_var is not None else "")
        if not label:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, "Label mangler.")
            return False
        try:
            sort_order = int(_clean_text(self._sort_var.get() if self._sort_var is not None else "0") or 0)
        except Exception:
            sort_order = 0
        payload: dict[str, Any] = {
            "id": entry_id,
            "label": label,
            "category": _clean_text(self._category_var.get() if self._category_var is not None else ""),
            "active": bool(self._active_var.get()) if self._active_var is not None else True,
            "sort_order": sort_order,
            "applies_to": _string_list(self._get_text_widget(self._applies_text)),
            "aliases": _string_list(self._get_text_widget(self._aliases_text)),
            "exclude_aliases": _string_list(self._get_text_widget(self._exclude_text)),
        }
        self._remove_entry(old_key)
        self._entries().append(payload)
        self._selected_key = entry_id
        if self._id_var is not None:
            self._id_var.set(entry_id)
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
        rows = sorted(
            self._visible_entries(),
            key=lambda entry: (int(entry.get("sort_order", 0) or 0), _clean_text(entry.get("label")).casefold(), _clean_text(entry.get("id")).casefold()),
        )
        for entry in rows:
            entry_id = _clean_text(entry.get("id"))
            label = _clean_text(entry.get("label"))
            category = _clean_text(entry.get("category"))
            scope_preview = ", ".join(_string_list(entry.get("applies_to"))[:3])
            haystack = " ".join([entry_id, label, category, scope_preview, ", ".join(_string_list(entry.get("aliases"))[:3])]).casefold()
            if search_text and search_text not in haystack:
                continue
            try:
                tree.insert("", "end", iid=entry_id, values=(entry_id, label, category, scope_preview))
            except Exception:
                continue
        if selected and tree.exists(selected):
            try:
                tree.selection_set(selected)
                tree.focus(selected)
                tree.see(selected)
            except Exception:
                pass

    def _switch_area(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        self._selected_key = ""
        self._update_area_text()
        self._clear_form()
        self._refresh_tree()
        tree = getattr(self, "_tree", None)
        children = tree.get_children("") if tree is not None else ()
        if children:
            first = str(children[0])
            self._selected_key = first
            self._load_form(first)
            if tree is not None:
                try:
                    tree.selection_set(first)
                    tree.focus(first)
                    tree.see(first)
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

    def new_entry(self) -> None:
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
        self._remove_entry(selected)
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()

    def reload(self) -> None:
        document, path_text = self._loader()
        self._document = _normalize_catalog_document(document)
        if self._path_var is not None:
            self._path_var.set(path_text)
        self._selected_key = ""
        self._update_area_text()
        self._clear_form()
        self._refresh_tree()
        tree = getattr(self, "_tree", None)
        children = tree.get_children("") if tree is not None else ()
        if children:
            first = str(children[0])
            self._selected_key = first
            self._load_form(first)
            if tree is not None:
                try:
                    tree.selection_set(first)
                    tree.focus(first)
                    tree.see(first)
                except Exception:
                    pass

    def save(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        try:
            saved_path = self._saver(_normalize_catalog_document(self._document))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        self._refresh_tree()
        if self._on_saved is not None:
            self._on_saved()
