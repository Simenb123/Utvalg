from __future__ import annotations

from typing import Any, Callable, Iterable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


from page_admin_helpers import (
    _clean_text,
    _int_list,
    _multiline_text,
    _normalize_rulebook_document,
    _string_list,
)
from a07_feature.control.rf1022_bridge import (
    RF1022_GROUP_LABELS,
    RF1022_UNKNOWN_GROUP,
)


_SIGN_TO_DISPLAY = {
    "": "Ingen",
    "-1": "Negativ",
    "0": "Uten betydning",
    "1": "Positiv",
}
_DISPLAY_TO_SIGN = {value: key for key, value in _SIGN_TO_DISPLAY.items()}

_RF1022_GROUP_ORDER = (
    "100_loenn_ol",
    "100_refusjon",
    "111_naturalytelser",
    "112_pensjon",
    RF1022_UNKNOWN_GROUP,
)
_RF1022_TO_DISPLAY = {
    **{group_id: RF1022_GROUP_LABELS.get(group_id, group_id) for group_id in _RF1022_GROUP_ORDER},
    RF1022_UNKNOWN_GROUP: "Må fordeles",
    "": "Må fordeles",
}
_DISPLAY_TO_RF1022 = {label: group_id for group_id, label in _RF1022_TO_DISPLAY.items() if group_id}
_RF1022_DISPLAY_VALUES = tuple(_RF1022_TO_DISPLAY[group_id] for group_id in _RF1022_GROUP_ORDER)

_AGA_TO_DISPLAY = {
    True: "Ja",
    False: "Nei",
    None: "Ukjent",
}
_DISPLAY_TO_AGA = {
    "ja": True,
    "j": True,
    "true": True,
    "1": True,
    "nei": False,
    "n": False,
    "false": False,
    "0": False,
}


def _display_sign(value: object) -> str:
    return _SIGN_TO_DISPLAY.get(_clean_text(value), "Ingen")


def _stored_sign(value: object) -> str:
    display = _clean_text(value)
    if display in _DISPLAY_TO_SIGN:
        return _DISPLAY_TO_SIGN[display]
    if display in _SIGN_TO_DISPLAY:
        return display
    return ""


def _display_rf1022_group(value: object) -> str:
    group_id = _clean_text(value) or RF1022_UNKNOWN_GROUP
    return _RF1022_TO_DISPLAY.get(group_id, group_id)


def _stored_rf1022_group(value: object) -> str:
    display = _clean_text(value)
    if display in _DISPLAY_TO_RF1022:
        return _DISPLAY_TO_RF1022[display]
    return display or RF1022_UNKNOWN_GROUP


def _coerce_aga_pliktig(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    return _DISPLAY_TO_AGA.get(_clean_text(value).casefold())


def _display_aga_pliktig(value: object) -> str:
    return _AGA_TO_DISPLAY[_coerce_aga_pliktig(value)]


def _stored_aga_pliktig(value: object) -> bool | None:
    return _coerce_aga_pliktig(value)


def _special_add_rows_from_payload(values: object) -> list[tuple[str, str, str, str]]:
    if not isinstance(values, (list, tuple)):
        return []
    rows: list[tuple[str, str, str, str]] = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        account = _clean_text(entry.get("account"))
        if not account:
            continue
        keywords = ", ".join(_string_list(entry.get("keywords") or entry.get("name_keywords")))
        basis = _clean_text(entry.get("basis"))
        weight = entry.get("weight")
        weight_text = ""
        if weight not in (None, ""):
            try:
                weight_text = str(float(weight))
            except Exception:
                weight_text = _clean_text(weight)
        rows.append((account, keywords, basis, weight_text))
    return rows


def _special_add_payload_from_rows(rows: Iterable[Iterable[object]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw_row in rows:
        values = list(raw_row)
        account = _clean_text(values[0] if len(values) > 0 else "")
        if not account:
            continue
        keywords = _string_list(str(values[1] if len(values) > 1 else "").replace(",", "\n"))
        basis = _clean_text(values[2] if len(values) > 2 else "")
        weight_text = _clean_text(values[3] if len(values) > 3 else "")
        row: dict[str, Any] = {"account": account}
        if keywords:
            row["keywords"] = keywords
        if basis:
            row["basis"] = basis
        if weight_text:
            try:
                row["weight"] = float(weight_text.replace(",", "."))
            except Exception:
                pass
        out.append(row)
    return out


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
        self._dirty = False
        self._suspend_dirty = False

        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        self._rule_var = tk.StringVar(value="") if tk is not None else None
        self._label_var = tk.StringVar(value="") if tk is not None else None
        self._category_var = tk.StringVar(value="") if tk is not None else None
        self._basis_var = tk.StringVar(value="UB") if tk is not None else None
        self._expected_sign_var = tk.StringVar(value="Ingen") if tk is not None else None
        self._aga_pliktig_var = tk.StringVar(value="Ukjent") if tk is not None else None
        self._rf1022_group_var = tk.StringVar(value=_display_rf1022_group(RF1022_UNKNOWN_GROUP)) if tk is not None else None
        self._special_account_var = tk.StringVar(value="") if tk is not None else None
        self._special_keywords_var = tk.StringVar(value="") if tk is not None else None
        self._special_basis_var = tk.StringVar(value="Endring") if tk is not None else None
        self._special_weight_var = tk.StringVar(value="1.0") if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self._status_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        ttk.Button(header, text="Ny", command=self.new_rule).grid(row=0, column=2, rowspan=2, padx=(8, 0))
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

        tree_columns = ("code", "name", "accounts", "basis", "aga", "rf1022")
        tree = ttk.Treeview(list_host, columns=tree_columns, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, heading, width in (
            ("code", "A07-kode", 180),
            ("name", "Navn", 220),
            ("accounts", "Kontoer", 150),
            ("basis", "Beløpskolonne", 110),
            ("aga", "AGA-pliktig", 95),
            ("rf1022", "RF-1022", 150),
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
        self._build_alias_tab(tabs)
        self._build_accounts_tab(tabs)
        self._build_advanced_tab(tabs)
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

        ttk.Label(frame, text="A07-kode").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._rule_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Visningsnavn").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._label_var).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Beløpskolonne").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Combobox(
            frame,
            textvariable=self._basis_var,
            values=("", "UB", "Endring", "IB"),
            state="readonly",
            width=16,
        ).grid(row=2, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Forventet beløpsretning").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self._expected_sign_var,
            values=("Ingen", "Positiv", "Negativ", "Uten betydning"),
            state="readonly",
            width=20,
        ).grid(row=3, column=1, sticky="w")

        ttk.Label(frame, text="AGA-pliktig").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            frame,
            textvariable=self._aga_pliktig_var,
            values=("Ukjent", "Ja", "Nei"),
            state="readonly",
            width=16,
        ).grid(row=4, column=1, sticky="w", pady=(8, 0))

        ttk.Label(frame, text="RF-1022-post").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            frame,
            textvariable=self._rf1022_group_var,
            values=_RF1022_DISPLAY_VALUES,
            state="readonly",
            width=28,
        ).grid(row=5, column=1, sticky="w", pady=(8, 0))

    def _build_alias_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)
        tabs.add(frame, text="Aliaser")

        ttk.Label(frame, text="Trefford/navn").grid(row=0, column=0, sticky="w")
        self._keywords_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._keywords_text.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        ttk.Label(frame, text="Skal ikke matche").grid(row=2, column=0, sticky="w")
        self._exclude_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._exclude_text.grid(row=3, column=0, sticky="nsew")

    def _build_accounts_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)
        tabs.add(frame, text="Kontoer")

        ttk.Label(frame, text="Kontoområder").grid(row=0, column=0, sticky="w")
        self._ranges_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._ranges_text.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        ttk.Label(frame, text="Prioriterte kontoer").grid(row=2, column=0, sticky="w")
        self._boost_text = tk.Text(frame, height=8, wrap="word", undo=True)
        self._boost_text.grid(row=3, column=0, sticky="nsew")

    def _build_advanced_tab(self, tabs: Any) -> None:
        frame = ttk.Frame(tabs, padding=(8, 8, 8, 8))
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)
        tabs.add(frame, text="Avansert")

        ttk.Label(frame, text="Kategori").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self._category_var).grid(row=0, column=1, columnspan=5, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Periodiserings-/balansekontoer").grid(row=1, column=0, columnspan=6, sticky="w")
        tree = ttk.Treeview(
            frame,
            columns=("account", "keywords", "basis", "weight"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        tree.grid(row=2, column=0, columnspan=6, sticky="nsew", pady=(0, 8))
        self._special_tree = tree
        for column, heading, width in (
            ("account", "Kontoområde", 140),
            ("keywords", "Navnetreff", 180),
            ("basis", "Beløpskolonne", 150),
            ("weight", "Vekt", 90),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        try:
            tree.bind("<<TreeviewSelect>>", lambda _event: self._handle_special_select(), add="+")
        except Exception:
            pass

        ttk.Label(frame, text="Kontoområde").grid(row=4, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self._special_account_var, width=14).grid(row=5, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(frame, text="Navnetreff").grid(row=4, column=1, sticky="w")
        ttk.Entry(frame, textvariable=self._special_keywords_var, width=18).grid(row=5, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(frame, text="Beløpskolonne").grid(row=4, column=2, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self._special_basis_var,
            values=("", "Endring", "UB", "IB"),
            state="readonly",
            width=16,
        ).grid(row=5, column=2, sticky="ew", padx=(0, 8))
        ttk.Label(frame, text="Vekt").grid(row=4, column=3, sticky="w")
        ttk.Entry(frame, textvariable=self._special_weight_var, width=10).grid(row=5, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Legg til / oppdater", command=self._add_or_update_special_row).grid(row=5, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Fjern", command=self._remove_special_row).grid(row=5, column=5, sticky="ew")

    def _bind_dirty_tracking(self) -> None:
        for variable in (
            self._rule_var,
            self._label_var,
            self._category_var,
            self._basis_var,
            self._expected_sign_var,
            self._aga_pliktig_var,
            self._rf1022_group_var,
        ):
            trace_add = getattr(variable, "trace_add", None)
            if callable(trace_add):
                try:
                    trace_add("write", lambda *_args: self._mark_dirty())
                except Exception:
                    pass

        for widget in (
            self._keywords_text,
            self._exclude_text,
            self._ranges_text,
            self._boost_text,
        ):
            try:
                widget.bind("<KeyRelease>", lambda _event: self._mark_dirty(), add="+")
                widget.bind("<<Paste>>", lambda _event: self._mark_dirty(), add="+")
            except Exception:
                continue

    def _rules(self) -> dict[str, dict[str, Any]]:
        rules = self._document.get("rules", {})
        if isinstance(rules, dict):
            return rules
        self._document["rules"] = {}
        return self._document["rules"]

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        if self._status_var is not None:
            self._status_var.set("Ulagrede endringer" if self._dirty else "Lagret")

    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        self._set_dirty(True)

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
        self._suspend_dirty = True
        try:
            for variable in (self._rule_var, self._label_var, self._category_var):
                if variable is not None:
                    variable.set("")
            if self._basis_var is not None:
                self._basis_var.set("UB")
            if self._expected_sign_var is not None:
                self._expected_sign_var.set("Ingen")
            if self._aga_pliktig_var is not None:
                self._aga_pliktig_var.set("Ukjent")
            if self._rf1022_group_var is not None:
                self._rf1022_group_var.set(_display_rf1022_group(RF1022_UNKNOWN_GROUP))
            for widget in (
                self._keywords_text,
                self._exclude_text,
                self._ranges_text,
                self._boost_text,
            ):
                self._set_text_widget(widget, "")
            self._load_special_rows(())
            self._clear_special_inputs()
        finally:
            self._suspend_dirty = False

    def _load_form(self, rule_id: str) -> None:
        payload = self._rules().get(rule_id, {})
        self._suspend_dirty = True
        try:
            if self._rule_var is not None:
                self._rule_var.set(rule_id)
            if self._label_var is not None:
                self._label_var.set(_clean_text(payload.get("label")) or rule_id)
            if self._category_var is not None:
                self._category_var.set(_clean_text(payload.get("category")))
            if self._basis_var is not None:
                self._basis_var.set(_clean_text(payload.get("basis")) or "UB")
            if self._expected_sign_var is not None:
                self._expected_sign_var.set(_display_sign(payload.get("expected_sign")))
            if self._aga_pliktig_var is not None:
                self._aga_pliktig_var.set(_display_aga_pliktig(payload.get("aga_pliktig")))
            if self._rf1022_group_var is not None:
                self._rf1022_group_var.set(_display_rf1022_group(payload.get("rf1022_group")))
            self._set_text_widget(self._keywords_text, _multiline_text(payload.get("keywords")))
            self._set_text_widget(self._exclude_text, _multiline_text(payload.get("exclude_keywords")))
            self._set_text_widget(self._ranges_text, _multiline_text(payload.get("allowed_ranges")))
            self._set_text_widget(self._boost_text, _multiline_text(payload.get("boost_accounts")))
            self._load_special_rows(payload.get("special_add"))
            self._clear_special_inputs()
        finally:
            self._suspend_dirty = False

    def _load_special_rows(self, values: object) -> None:
        tree = getattr(self, "_special_tree", None)
        if tree is None:
            return
        try:
            for item in tree.get_children(""):
                tree.delete(item)
        except Exception:
            pass
        for index, row in enumerate(_special_add_rows_from_payload(values), start=1):
            try:
                tree.insert("", "end", iid=str(index), values=row)
            except Exception:
                continue

    def _special_row_values(self) -> list[tuple[str, str, str, str]]:
        tree = getattr(self, "_special_tree", None)
        if tree is None:
            return []
        rows: list[tuple[str, str, str]] = []
        try:
            children = tree.get_children("")
        except Exception:
            children = ()
        for item in children:
            try:
                raw_values = tree.item(item, "values")
            except Exception:
                raw_values = ()
            values = list(raw_values or ())
            rows.append(
                (
                    _clean_text(values[0] if len(values) > 0 else ""),
                    _clean_text(values[1] if len(values) > 1 else ""),
                    _clean_text(values[2] if len(values) > 2 else ""),
                    _clean_text(values[3] if len(values) > 3 else ""),
                )
            )
        return rows

    def _special_add_payload(self) -> list[dict[str, Any]]:
        return _special_add_payload_from_rows(self._special_row_values())

    def _clear_special_inputs(self) -> None:
        for variable, value in (
            (self._special_account_var, ""),
            (self._special_keywords_var, ""),
            (self._special_basis_var, "Endring"),
            (self._special_weight_var, "1.0"),
        ):
            if variable is not None:
                try:
                    variable.set(value)
                except Exception:
                    pass

    def _handle_special_select(self) -> None:
        tree = getattr(self, "_special_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        try:
            values = list(tree.item(selection[0], "values") or ())
        except Exception:
            values = []
        self._suspend_dirty = True
        try:
            for variable, index in (
                (self._special_account_var, 0),
                (self._special_keywords_var, 1),
                (self._special_basis_var, 2),
                (self._special_weight_var, 3),
            ):
                if variable is not None:
                    variable.set(_clean_text(values[index] if len(values) > index else ""))
        finally:
            self._suspend_dirty = False

    def _add_or_update_special_row(self) -> None:
        account = _clean_text(self._special_account_var.get() if self._special_account_var is not None else "")
        if not account:
            if messagebox is not None:
                messagebox.showerror(self._title, "Konto mangler.")
            return
        basis = _clean_text(self._special_basis_var.get() if self._special_basis_var is not None else "")
        keywords = _clean_text(self._special_keywords_var.get() if self._special_keywords_var is not None else "")
        weight = _clean_text(self._special_weight_var.get() if self._special_weight_var is not None else "")
        if weight:
            try:
                float(weight.replace(",", "."))
            except Exception:
                if messagebox is not None:
                    messagebox.showerror(self._title, "Vekt må være et tall.")
                return
        row = (account, keywords, basis, weight)
        tree = getattr(self, "_special_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        try:
            if selection:
                tree.item(selection[0], values=row)
            else:
                existing = list(tree.get_children(""))
                next_id = str(len(existing) + 1)
                while next_id in existing:
                    next_id = str(int(next_id) + 1)
                tree.insert("", "end", iid=next_id, values=row)
        except Exception:
            return
        self._mark_dirty()

    def _remove_special_row(self) -> None:
        tree = getattr(self, "_special_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        try:
            for item in selection:
                tree.delete(item)
        except Exception:
            return
        self._clear_special_inputs()
        self._mark_dirty()

    def _current_payload(self) -> tuple[str, dict[str, Any], bool]:
        old_key = _clean_text(self._selected_key)
        typed_key = _clean_text(self._rule_var.get() if self._rule_var is not None else "")
        rule_id = typed_key or old_key
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
        expected_sign = _stored_sign(self._expected_sign_var.get() if self._expected_sign_var is not None else "")
        if expected_sign:
            payload["expected_sign"] = int(expected_sign)
        aga_pliktig = _stored_aga_pliktig(self._aga_pliktig_var.get() if self._aga_pliktig_var is not None else "")
        if aga_pliktig is not None:
            payload["aga_pliktig"] = aga_pliktig
        rf1022_group = _stored_rf1022_group(self._rf1022_group_var.get() if self._rf1022_group_var is not None else "")
        if rf1022_group:
            payload["rf1022_group"] = rf1022_group
        special_add = self._special_add_payload()
        if special_add:
            payload["special_add"] = special_add
        basis_is_default = basis in ("", "UB")
        has_content = any(
            (
                label,
                category,
                keywords,
                exclude_keywords,
                allowed_ranges,
                boost_accounts,
                "" if basis_is_default else basis,
                expected_sign,
                aga_pliktig is not None,
                "" if rf1022_group == RF1022_UNKNOWN_GROUP else rf1022_group,
                special_add,
            )
        )
        return rule_id, payload, bool(has_content)

    def _commit_form(self, *, show_errors: bool) -> bool:
        rules = self._rules()
        old_key = _clean_text(self._selected_key)
        rule_id, payload, has_content = self._current_payload()
        if not rule_id:
            if show_errors and has_content and messagebox is not None:
                messagebox.showerror(self._title, "A07-kode mangler.")
                return False
            return True
        if rule_id in rules and rule_id != old_key:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, f"Regelen '{rule_id}' finnes allerede.")
            return False

        previous = rules.get(old_key if old_key else rule_id)
        if old_key and rule_id != old_key:
            rules.pop(old_key, None)
        rules[rule_id] = payload
        if previous != payload or (old_key and old_key != rule_id):
            self._mark_dirty()
        self._selected_key = rule_id
        if self._rule_var is not None:
            self._suspend_dirty = True
            try:
                self._rule_var.set(rule_id)
            finally:
                self._suspend_dirty = False
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
            label = _clean_text(payload.get("label")) or rule_id
            ranges_preview = ", ".join(_string_list(payload.get("allowed_ranges"))[:2])
            basis = _clean_text(payload.get("basis"))
            aga = _display_aga_pliktig(payload.get("aga_pliktig"))
            rf1022 = _display_rf1022_group(payload.get("rf1022_group"))
            haystack = " ".join(
                [
                    rule_id,
                    label,
                    ranges_preview,
                    aga,
                    rf1022,
                    ", ".join(_string_list(payload.get("keywords"))[:3]),
                    ", ".join(_string_list(payload.get("exclude_keywords"))[:5]),
                    ", ".join(str(value) for value in _int_list(payload.get("boost_accounts"))[:5]),
                ]
            ).casefold()
            if search_text and search_text not in haystack:
                continue
            try:
                tree.insert("", "end", iid=rule_id, values=(rule_id, label, ranges_preview, basis, aga, rf1022))
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
        if next_key == _clean_text(self._selected_key):
            return
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
        self._mark_dirty()

    def reload(self, select_key: object | None = None) -> None:
        preferred_key = _clean_text(select_key) or _clean_text(self._selected_key)
        document, path_text = self._loader()
        self._document = _normalize_rulebook_document(document)
        self._suspend_dirty = True
        try:
            if self._path_var is not None:
                self._path_var.set(path_text)
            self._selected_key = ""
            self._clear_form()
            self._refresh_tree()
            keys = sorted(self._rules().keys(), key=str.casefold)
            if keys:
                target_key = preferred_key if preferred_key in self._rules() else keys[0]
                self._selected_key = target_key
                self._load_form(target_key)
                tree = getattr(self, "_tree", None)
                if tree is not None and tree.exists(target_key):
                    try:
                        tree.selection_set(target_key)
                        tree.focus(target_key)
                        tree.see(target_key)
                    except Exception:
                        pass
        finally:
            self._suspend_dirty = False
        self._set_dirty(False)

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
        self._set_dirty(False)
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
