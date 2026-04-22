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
    _alias_concept_preview_text,
    _alias_preview_text,
    _clean_text,
    _int_list,
    _multiline_text,
    _normalize_alias_document,
    _saved_status_text,
    _string_list,
)


class _AliasEditor(ttk.Frame):  # type: ignore[misc]
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
        self._document: dict[str, Any] = {"concepts": {}}
        self._selected_key = ""
        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._concept_var = tk.StringVar(value="") if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        self._preview_var = tk.StringVar(value="") if tk is not None else None
        self._suspend_dirty = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Ny", command=self.new_concept).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Slett", command=self.delete_selected).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=4, rowspan=2, padx=(8, 0))

        ttk.Label(
            self,
            text="Avansert kompatibilitetslag for delte alias-konsepter. Nye A07-aliaser og ekskluderinger skal normalt vedlikeholdes i fanen A07-regler.",
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
        ).grid(row=1, column=0, sticky="ew")
        ttk.Label(
            self,
            textvariable=self._status_var,
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
            anchor="w",
            justify="left",
        ).grid(row=2, column=0, sticky="ew")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")

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

        tree_columns = ("Konsept", "Aliaser", "Kontointervall")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, width in (("Konsept", 180), ("Aliaser", 260), ("Kontointervall", 140)):
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

        ttk.Label(detail_host, text="Konsept-id").grid(row=0, column=0, sticky="w")
        concept_entry = ttk.Entry(detail_host, textvariable=self._concept_var)
        concept_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        try:
            concept_entry.bind("<KeyRelease>", lambda _event: self._mark_dirty(), add="+")
        except Exception:
            pass

        ttk.Label(detail_host, text="Aliaser").grid(row=1, column=0, sticky="w")
        ttk.Label(detail_host, text="Én verdi per linje", style="Muted.TLabel").grid(row=1, column=1, sticky="e")
        self._aliases_text = tk.Text(detail_host, height=8, wrap="word", undo=True)
        self._aliases_text.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Ekskluder aliaser").grid(row=3, column=0, sticky="w")
        self._exclude_text = tk.Text(detail_host, height=6, wrap="word", undo=True)
        self._exclude_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Kontointervall").grid(row=5, column=0, sticky="w")
        self._ranges_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._ranges_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Boost-kontoer").grid(row=7, column=0, sticky="w")
        ttk.Label(detail_host, text="Ett kontonummer per linje", style="Muted.TLabel").grid(row=7, column=1, sticky="e")
        self._boost_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._boost_text.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(
            detail_host,
            text="Bruk denne fanen for finjustering. A07-regler og terskler ligger fortsatt i egne faner.",
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=9, column=0, columnspan=2, sticky="w")
        ttk.Label(detail_host, text="Preview av valgt konsept").grid(row=10, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            detail_host,
            textvariable=self._preview_var,
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        for widget in (self._aliases_text, self._exclude_text, self._ranges_text, self._boost_text):
            try:
                widget.bind("<KeyRelease>", lambda _event: self._mark_dirty(), add="+")
            except Exception:
                continue

        self.reload()

    def _concepts(self) -> dict[str, dict[str, Any]]:
        concepts = self._document.get("concepts", {})
        if isinstance(concepts, dict):
            return concepts
        self._document["concepts"] = {}
        return self._document["concepts"]

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

    def _current_form_payload(self) -> dict[str, Any]:
        return {
            "aliases": _string_list(self._get_text_widget(self._aliases_text)),
            "exclude_aliases": _string_list(self._get_text_widget(self._exclude_text)),
            "account_ranges": _string_list(self._get_text_widget(self._ranges_text)),
            "boost_accounts": _int_list(self._get_text_widget(self._boost_text)),
        }

    def _sync_preview_from_form(self) -> None:
        if self._preview_var is None:
            return
        concept_id = _clean_text(self._concept_var.get() if self._concept_var is not None else "") or _clean_text(self._selected_key)
        payload = self._current_form_payload()
        if not concept_id and not any(payload.values()):
            self._preview_var.set("Ingen konsept valgt.")
            return
        self._preview_var.set(_alias_concept_preview_text(concept_id, payload))

    def _clear_form(self) -> None:
        self._suspend_dirty = True
        if self._concept_var is not None:
            self._concept_var.set("")
        self._set_text_widget(self._aliases_text, "")
        self._set_text_widget(self._exclude_text, "")
        self._set_text_widget(self._ranges_text, "")
        self._set_text_widget(self._boost_text, "")
        self._suspend_dirty = False
        self._sync_preview_from_form()

    def _load_form(self, concept_id: str) -> None:
        payload = self._concepts().get(concept_id, {})
        self._suspend_dirty = True
        if self._concept_var is not None:
            self._concept_var.set(concept_id)
        self._set_text_widget(self._aliases_text, _multiline_text(payload.get("aliases")))
        self._set_text_widget(self._exclude_text, _multiline_text(payload.get("exclude_aliases")))
        self._set_text_widget(self._ranges_text, _multiline_text(payload.get("account_ranges")))
        self._set_text_widget(self._boost_text, _multiline_text(payload.get("boost_accounts")))
        self._suspend_dirty = False
        self._sync_preview_from_form()
        if self._status_var is not None:
            self._status_var.set("Rediger aliasene til høyre og trykk Lagre når du er ferdig.")

    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        self._sync_preview_from_form()
        if self._status_var is not None:
            self._status_var.set("Endringer ikke lagret ennå.")

    def _commit_form(self, *, show_errors: bool) -> bool:
        concepts = self._concepts()
        old_key = _clean_text(self._selected_key)
        typed_key = _clean_text(self._concept_var.get() if self._concept_var is not None else "")
        concept_id = typed_key or old_key
        has_content = any(
            (
                self._get_text_widget(self._aliases_text),
                self._get_text_widget(self._exclude_text),
                self._get_text_widget(self._ranges_text),
                self._get_text_widget(self._boost_text),
            )
        )
        if not concept_id:
            if show_errors and has_content and messagebox is not None:
                messagebox.showerror(self._title, "Konsept-id mangler.")
                return False
            return True
        if old_key and concept_id != old_key and concept_id in concepts:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, f"Konseptet '{concept_id}' finnes allerede.")
            return False
        payload = self._current_form_payload()
        if old_key and concept_id != old_key:
            concepts.pop(old_key, None)
        concepts[concept_id] = payload
        self._selected_key = concept_id
        if self._concept_var is not None:
            self._concept_var.set(concept_id)
        self._sync_preview_from_form()
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
        for concept_id, payload in sorted(self._concepts().items(), key=lambda item: item[0].casefold()):
            alias_preview = _alias_preview_text(payload.get("aliases"))
            ranges_preview = ", ".join(_string_list(payload.get("account_ranges")))
            haystack = " ".join(
                [
                    concept_id,
                    alias_preview,
                    ", ".join(_string_list(payload.get("exclude_aliases"))[:2]),
                    ranges_preview,
                ]
            ).casefold()
            if search_text and search_text not in haystack:
                continue
            try:
                tree.insert(
                    "",
                    "end",
                    iid=concept_id,
                    values=(concept_id, alias_preview, ranges_preview),
                )
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

    def new_concept(self) -> None:
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
        self._concepts().pop(selected, None)
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()

    def reload(self, preserve_selection: str | None = None) -> None:
        document, path_text = self._loader()
        self._document = _normalize_alias_document(document)
        if self._path_var is not None:
            self._path_var.set(path_text)
        preferred = _clean_text(preserve_selection or self._selected_key)
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()
        keys = sorted(self._concepts().keys(), key=str.casefold)
        if keys:
            selected_key = preferred if preferred in self._concepts() else keys[0]
            self._selected_key = selected_key
            self._load_form(selected_key)
            tree = getattr(self, "_tree", None)
            if tree is not None and tree.exists(selected_key):
                try:
                    tree.selection_set(selected_key)
                    tree.focus(selected_key)
                    tree.see(selected_key)
                except Exception:
                    pass

    def save(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        selected_key = _clean_text(self._selected_key)
        try:
            saved_path = self._saver(_normalize_alias_document(self._document))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        self.reload(preserve_selection=selected_key)
        if self._status_var is not None:
            self._status_var.set(_saved_status_text(saved_path))
        if self._on_saved is not None:
            self._on_saved()
