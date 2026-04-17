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
    """Editor for global detaljklassifisering (skyldig-konti mm.).

    Bygger på samme mønster som `_AliasEditor` men håndterer rikere
    skjema (kategori, aktiv-flagg, sortering, ekskluder-aliaser) og
    bruker selection-guard for å unngå freeze ved rad-klikk.
    """

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
        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._id_var = tk.StringVar(value="") if tk is not None else None
        self._name_var = tk.StringVar(value="") if tk is not None else None
        self._category_var = tk.StringVar(value="forpliktelse") if tk is not None else None
        self._sort_var = tk.StringVar(value="0") if tk is not None else None
        self._active_var = tk.BooleanVar(value=True) if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        self._suspend_dirty = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Ny", command=self.new_class).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Slett", command=self.delete_selected).grid(row=0, column=2, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=3, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=4, rowspan=2, padx=(8, 0))

        ttk.Label(
            self,
            text=(
                "Definer globale detalj-klasser (alias + kontointervall + ekskludering). "
                "Klientspesifikke valg pr konto gjøres i Saldobalanse."
            ),
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

        tree_columns = ("Id", "Navn", "Kategori", "Intervall", "Aktiv", "Sort")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, width in (
            ("Id", 180),
            ("Navn", 200),
            ("Kategori", 110),
            ("Intervall", 120),
            ("Aktiv", 60),
            ("Sort", 60),
        ):
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
        detail_host.rowconfigure(5, weight=1)
        detail_host.rowconfigure(7, weight=1)
        detail_host.rowconfigure(9, weight=1)
        body.add(detail_host, weight=3)

        ttk.Label(detail_host, text="Id").grid(row=0, column=0, sticky="w")
        id_entry = ttk.Entry(detail_host, textvariable=self._id_var)
        id_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(detail_host, text="Navn").grid(row=1, column=0, sticky="w")
        ttk.Entry(detail_host, textvariable=self._name_var).grid(row=1, column=1, sticky="ew", pady=(0, 6))

        meta_row = ttk.Frame(detail_host)
        meta_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        meta_row.columnconfigure(1, weight=1)
        meta_row.columnconfigure(3, weight=0)
        ttk.Label(meta_row, text="Kategori").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            meta_row,
            textvariable=self._category_var,
            values=self._CATEGORY_CHOICES,
            state="readonly",
            width=14,
        ).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(meta_row, text="Sortering").grid(row=0, column=2, sticky="w")
        ttk.Entry(meta_row, textvariable=self._sort_var, width=8).grid(row=0, column=3, sticky="w", padx=(6, 12))
        ttk.Checkbutton(meta_row, text="Aktiv", variable=self._active_var).grid(row=0, column=4, sticky="w", padx=(6, 0))

        ttk.Label(detail_host, text="Kontointervall").grid(row=3, column=0, sticky="w")
        ttk.Label(detail_host, text="F.eks. 2740-2770 (én pr linje)", style="Muted.TLabel").grid(row=3, column=1, sticky="e")
        self._ranges_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._ranges_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        self._ranges_text.bind("<Tab>", lambda _e: (detail_host.tk_focusNext().focus(), "break")[1], add="+")

        ttk.Label(detail_host, text="Aliaser").grid(row=5, column=0, sticky="w")
        ttk.Label(detail_host, text="Én verdi per linje", style="Muted.TLabel").grid(row=5, column=1, sticky="e")
        self._aliases_text = tk.Text(detail_host, height=6, wrap="word", undo=True)
        self._aliases_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(detail_host, text="Ekskluder aliaser").grid(row=7, column=0, sticky="w")
        self._exclude_text = tk.Text(detail_host, height=5, wrap="word", undo=True)
        self._exclude_text.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        for widget in (self._ranges_text, self._aliases_text, self._exclude_text):
            try:
                widget.bind("<KeyRelease>", lambda _event: self._mark_dirty(), add="+")
            except Exception:
                continue
        for var in (self._id_var, self._name_var, self._category_var, self._sort_var):
            if var is not None:
                try:
                    var.trace_add("write", lambda *_args: self._mark_dirty())
                except Exception:
                    pass
        if self._active_var is not None:
            try:
                self._active_var.trace_add("write", lambda *_args: self._mark_dirty())
            except Exception:
                pass

        self.reload()

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
        self._suspend_dirty = False

    def _load_form(self, class_id: str) -> None:
        entry = self._class_by_id(class_id) or {}
        self._suspend_dirty = True
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
        self._suspend_dirty = False
        if self._status_var is not None:
            self._status_var.set("Rediger detalj-klassen og trykk Lagre.")

    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        if self._status_var is not None:
            self._status_var.set("Endringer ikke lagret ennå.")

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
                messagebox.showerror(self._title, "Id mangler.")
                return False
            return True
        classes = self._classes()
        if old_key and new_id != old_key:
            # rename-sjekk
            for entry in classes:
                if _clean_text(entry.get("id")) == new_id:
                    if show_errors and messagebox is not None:
                        messagebox.showerror(self._title, f"Id '{new_id}' finnes allerede.")
                    return False
        existing = None
        target_key = new_id if old_key and new_id != old_key else (old_key or new_id)
        for entry in classes:
            if _clean_text(entry.get("id")) == target_key:
                existing = entry
                break
        if existing is None:
            # Ny klasse
            classes.append(dict(payload))
        else:
            existing.update(payload)
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
        if self._status_var is not None:
            self._status_var.set("Fyll ut ny detalj-klasse og trykk Lagre.")

    def delete_selected(self) -> None:
        selected = _clean_text(self._selected_key)
        if not selected:
            return
        classes = self._classes()
        classes[:] = [entry for entry in classes if _clean_text(entry.get("id")) != selected]
        self._selected_key = ""
        self._clear_form()
        self._refresh_tree()
        if self._status_var is not None:
            self._status_var.set(f"Slettet '{selected}' (ikke lagret ennå).")

    def reload(self, preserve_selection: str | None = None) -> None:
        document, path_text = self._loader()
        self._document = account_detail_classification.normalize_document(document)
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
        if self._on_saved is not None:
            self._on_saved()
