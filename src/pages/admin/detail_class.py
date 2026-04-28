from __future__ import annotations

from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import account_detail_classification

from page_admin_helpers import (
    _clean_text,
    _saved_status_text,
    _string_list,
)


class _DetailClassEditor(ttk.Frame):  # type: ignore[misc]
    _CATEGORY_CHOICES: tuple[str, ...] = account_detail_classification.VALID_KATEGORIER

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
        self._document: dict[str, Any] = {"classes": []}
        self._selected_key = ""
        self._suspend_tree_select = False
        self._suspend_dirty = False
        self._dirty = False

        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        self._id_var = tk.StringVar(value="") if tk is not None else None
        self._name_var = tk.StringVar(value="") if tk is not None else None
        self._category_var = tk.StringVar(value="forpliktelse") if tk is not None else None
        self._sort_var = tk.StringVar(value="0") if tk is not None else None
        self._active_var = tk.BooleanVar(value=True) if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self._status_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        ttk.Button(header, text="Ny", command=self.new_class).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Slett", command=self.delete_selected).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Forkast endringer", command=self.reload).grid(row=0, column=4, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=5, rowspan=2, padx=(8, 0))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew")

        list_host = ttk.Frame(body, padding=(8, 0, 4, 8))
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(1, weight=1)
        body.add(list_host, weight=2)

        search_row = ttk.Frame(list_host)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Søk").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_row, textvariable=self._search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        try:
            search_entry.bind("<KeyRelease>", lambda _event: self._refresh_tree(), add="+")
        except Exception:
            pass

        tree_columns = ("class_id", "name", "category", "accounts", "active", "sort")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, heading, width in (
            ("class_id", "Klasse-id", 180),
            ("name", "Navn", 210),
            ("category", "Kategori", 110),
            ("accounts", "Kontoer", 140),
            ("active", "Aktiv", 60),
            ("sort", "Sortering", 75),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        y_scroll = ttk.Scrollbar(list_host, orient="vertical", command=tree.yview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)
        try:
            tree.bind("<<TreeviewSelect>>", lambda _event: self._handle_tree_select(), add="+")
        except Exception:
            pass

        detail_host = ttk.Frame(body, padding=(4, 0, 8, 8))
        detail_host.columnconfigure(0, weight=1)
        detail_host.rowconfigure(0, weight=1)
        body.add(detail_host, weight=3)

        tabs = ttk.Notebook(detail_host)
        tabs.grid(row=0, column=0, sticky="nsew")
        self._detail_tabs = tabs

        self._build_basic_tab(tabs)
        self._build_accounts_tab(tabs)
        self._build_alias_tab(tabs)
        self._bind_dirty_tracking()

        try:
            self.bind_all("<Control-s>", self._handle_save_shortcut, add="+")
        except Exception:
            pass

        self.reload()

    def _build_basic_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(1, weight=1)
        tabs.add(frame, text="Grunnregel")

        ttk.Label(frame, text="Klasse-id").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._id_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Navn").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._name_var).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Kategori").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(
            frame,
            textvariable=self._category_var,
            values=self._CATEGORY_CHOICES,
            state="readonly",
            width=16,
        ).grid(row=2, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Sortering").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._sort_var, width=10).grid(row=3, column=1, sticky="w", pady=(0, 8))
        ttk.Checkbutton(frame, text="Aktiv", variable=self._active_var).grid(row=4, column=1, sticky="w")

    def _build_accounts_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        tabs.add(frame, text="Kontoer")

        ttk.Label(frame, text="Kontoområder").grid(row=0, column=0, sticky="w")
        self._ranges_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._ranges_text.grid(row=1, column=0, sticky="nsew")
        try:
            self._ranges_text.bind("<Tab>", lambda _e: (frame.tk_focusNext().focus(), "break")[1], add="+")
        except Exception:
            pass

    def _build_alias_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)
        tabs.add(frame, text="Aliaser")

        ttk.Label(frame, text="Trefford/navn").grid(row=0, column=0, sticky="w")
        self._aliases_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._aliases_text.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        ttk.Label(frame, text="Skal ikke matche").grid(row=2, column=0, sticky="w")
        self._exclude_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._exclude_text.grid(row=3, column=0, sticky="nsew")

    def _bind_dirty_tracking(self) -> None:
        for widget in (self._ranges_text, self._aliases_text, self._exclude_text):
            try:
                widget.bind("<KeyRelease>", lambda _event: self._mark_dirty(), add="+")
                widget.bind("<<Paste>>", lambda _event: self._mark_dirty(), add="+")
            except Exception:
                continue
        for var in (self._id_var, self._name_var, self._category_var, self._sort_var, self._active_var):
            trace_add = getattr(var, "trace_add", None)
            if callable(trace_add):
                try:
                    trace_add("write", lambda *_args: self._mark_dirty())
                except Exception:
                    pass

    # ---- helpers ----------------------------------------------------

    def _classes(self) -> list[dict[str, Any]]:
        classes = self._document.get("classes")
        if not isinstance(classes, list):
            self._document["classes"] = []
            return self._document["classes"]
        return classes

    def _class_by_id(self, class_id: str) -> dict[str, Any] | None:
        target = _clean_text(class_id)
        for entry in self._classes():
            if _clean_text(entry.get("id")) == target:
                return entry
        return None

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
        try:
            sortering = int(_clean_text(self._sort_var.get()) or 0) if self._sort_var is not None else 0
        except (TypeError, ValueError):
            sortering = 0
        return {
            "id": _clean_text(self._id_var.get() if self._id_var is not None else ""),
            "navn": _clean_text(self._name_var.get() if self._name_var is not None else ""),
            "kategori": _clean_text(self._category_var.get() if self._category_var is not None else "") or "annet",
            "kontointervall": _string_list(self._get_text_widget(self._ranges_text)),
            "aliaser": _string_list(self._get_text_widget(self._aliases_text)),
            "ekskluder_aliaser": _string_list(self._get_text_widget(self._exclude_text)),
            "aktiv": bool(self._active_var.get()) if self._active_var is not None else True,
            "sortering": sortering,
        }

    def _clear_form(self) -> None:
        self._suspend_dirty = True
        try:
            if self._id_var is not None:
                self._id_var.set("")
            if self._name_var is not None:
                self._name_var.set("")
            if self._category_var is not None:
                self._category_var.set("forpliktelse")
            if self._sort_var is not None:
                self._sort_var.set("0")
            if self._active_var is not None:
                self._active_var.set(True)
            self._set_text_widget(self._ranges_text, "")
            self._set_text_widget(self._aliases_text, "")
            self._set_text_widget(self._exclude_text, "")
        finally:
            self._suspend_dirty = False

    def _load_form(self, class_id: str) -> None:
        entry = self._class_by_id(class_id) or {}
        self._suspend_dirty = True
        try:
            if self._id_var is not None:
                self._id_var.set(_clean_text(entry.get("id")) or class_id)
            if self._name_var is not None:
                self._name_var.set(_clean_text(entry.get("navn")))
            if self._category_var is not None:
                kategori = _clean_text(entry.get("kategori")).casefold() or "forpliktelse"
                if kategori not in self._CATEGORY_CHOICES:
                    kategori = "annet"
                self._category_var.set(kategori)
            if self._sort_var is not None:
                try:
                    sort_value = int(entry.get("sortering") or 0)
                except (TypeError, ValueError):
                    sort_value = 0
                self._sort_var.set(str(sort_value))
            if self._active_var is not None:
                aktiv_raw = entry.get("aktiv")
                self._active_var.set(True if aktiv_raw is None else bool(aktiv_raw))
            self._set_text_widget(self._ranges_text, "\n".join(_string_list(entry.get("kontointervall"))))
            self._set_text_widget(self._aliases_text, "\n".join(_string_list(entry.get("aliaser"))))
            self._set_text_widget(self._exclude_text, "\n".join(_string_list(entry.get("ekskluder_aliaser"))))
        finally:
            self._suspend_dirty = False

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        if self._status_var is not None:
            self._status_var.set("Ulagrede endringer" if self._dirty else "Lagret")

    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        self._set_dirty(True)

    def _row_values(self, entry: dict[str, Any]) -> tuple[str, ...]:
        return (
            _clean_text(entry.get("id")),
            _clean_text(entry.get("navn")),
            _clean_text(entry.get("kategori")) or "annet",
            ", ".join(_string_list(entry.get("kontointervall"))),
            "ja" if entry.get("aktiv", True) else "nei",
            str(entry.get("sortering") or 0),
        )

    def _commit_form(self, *, show_errors: bool) -> bool:
        payload = self._current_form_payload()
        old_key = _clean_text(self._selected_key)
        new_id = payload["id"]
        has_content = any(
            (
                payload["navn"],
                payload["kontointervall"],
                payload["aliaser"],
                payload["ekskluder_aliaser"],
            )
        )
        if not new_id:
            if show_errors and has_content and messagebox is not None:
                messagebox.showerror(self._title, "Klasse-id mangler.")
                return False
            return True

        classes = self._classes()
        if old_key and new_id != old_key:
            for entry in classes:
                if _clean_text(entry.get("id")) == new_id:
                    if show_errors and messagebox is not None:
                        messagebox.showerror(self._title, f"Klasse-id '{new_id}' finnes allerede.")
                    return False

        existing = None
        target_key = old_key or new_id
        for entry in classes:
            if _clean_text(entry.get("id")) == target_key:
                existing = entry
                break

        previous = dict(existing) if isinstance(existing, dict) else None
        if existing is None:
            classes.append(dict(payload))
            self._mark_dirty()
        else:
            existing.clear()
            existing.update(payload)
            if previous != payload:
                self._mark_dirty()

        self._selected_key = new_id
        return True

    def _refresh_tree(self) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        selected = _clean_text(self._selected_key)
        search_text = _clean_text(self._search_var.get() if self._search_var is not None else "").casefold()
        self._suspend_tree_select = True
        try:
            for item in tree.get_children(""):
                tree.delete(item)
        except Exception:
            pass
        entries = sorted(
            self._classes(),
            key=lambda e: (
                int(e.get("sortering") or 0),
                _clean_text(e.get("id")).casefold(),
            ),
        )
        for entry in entries:
            class_id = _clean_text(entry.get("id"))
            if not class_id:
                continue
            values = self._row_values(entry)
            haystack = " ".join(values).casefold()
            if search_text and search_text not in haystack:
                continue
            try:
                tree.insert("", "end", iid=class_id, values=values)
            except Exception:
                continue
        if selected and tree.exists(selected):
            try:
                tree.selection_set(selected)
                tree.focus(selected)
                tree.see(selected)
            except Exception:
                pass
        self._suspend_tree_select = False

    def _handle_tree_select(self) -> None:
        if self._suspend_tree_select:
            return
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
        if next_key == _clean_text(self._selected_key):
            return
        if not self._commit_form(show_errors=True):
            if self._selected_key and tree.exists(self._selected_key):
                self._suspend_tree_select = True
                try:
                    tree.selection_set(self._selected_key)
                except Exception:
                    pass
                self._suspend_tree_select = False
            return
        self._selected_key = next_key
        refresh_tree = getattr(self, "_refresh_tree", None)
        if callable(refresh_tree):
            refresh_tree()
        self._load_form(next_key)

    # ---- public actions ---------------------------------------------

    def new_class(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        self._selected_key = ""
        self._clear_form()
        tree = getattr(self, "_tree", None)
        if tree is not None:
            self._suspend_tree_select = True
            try:
                tree.selection_remove(tree.selection())
            except Exception:
                pass
            self._suspend_tree_select = False
        if self._status_var is not None and not self._dirty:
            self._status_var.set("Ny klasse")

    def delete_selected(self) -> None:
        selected = _clean_text(self._selected_key)
        if not selected:
            return
        classes = self._classes()
        original_len = len(classes)
        classes[:] = [entry for entry in classes if _clean_text(entry.get("id")) != selected]
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()
        if len(classes) != original_len:
            self._mark_dirty()

    def reload(self, preserve_selection: str | None = None) -> None:
        document, path_text = self._loader()
        self._document = account_detail_classification.normalize_document(document)
        self._suspend_dirty = True
        try:
            if self._path_var is not None:
                self._path_var.set(path_text)
            preferred = _clean_text(preserve_selection or self._selected_key)
            self._selected_key = ""
            self._clear_form()
            self._refresh_tree()
            ids = [_clean_text(entry.get("id")) for entry in self._classes() if _clean_text(entry.get("id"))]
            if ids:
                selected_key = preferred if preferred in ids else ids[0]
                self._selected_key = selected_key
                self._load_form(selected_key)
                tree = getattr(self, "_tree", None)
                if tree is not None and tree.exists(selected_key):
                    self._suspend_tree_select = True
                    try:
                        tree.selection_set(selected_key)
                        tree.focus(selected_key)
                        tree.see(selected_key)
                    except Exception:
                        pass
                    self._suspend_tree_select = False
        finally:
            self._suspend_dirty = False
        self._set_dirty(False)

    def save(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        selected_key = _clean_text(self._selected_key)
        try:
            saved_path = self._saver(account_detail_classification.normalize_document(self._document))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        self.reload(preserve_selection=selected_key)
        if self._status_var is not None:
            self._status_var.set(_saved_status_text(saved_path))
        self._dirty = False
        if self._on_saved is not None:
            self._on_saved()

    def _focus_is_inside(self) -> bool:
        try:
            widget = self.focus_get()
        except Exception:
            return False
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _handle_save_shortcut(self, _event: object = None) -> str | None:
        if not self._focus_is_inside():
            return None
        self.save()
        return "break"
