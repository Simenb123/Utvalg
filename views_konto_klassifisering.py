"""views_konto_klassifisering.py - editor dialog for konto-klassifisering.

Opnes fra Analyse-fanen. Brukeren kan fortsatt tildele kontrollgrupper som før,
men dialogen viser na ogsa profilfelt fra den nye kontoprofilmodellen.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import konto_klassifisering as _kk

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:
    import formatting
except Exception:  # pragma: no cover
    formatting = None  # type: ignore


def _fmt_confidence(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) * 100:.0f}%"
    except Exception:
        return ""


def _row_source_label(source: object) -> str:
    text = str(source or "").strip()
    return text


def _fmt_amount(value: object) -> str:
    if formatting is not None:
        try:
            return formatting.fmt_amount(value)
        except Exception:
            pass
    try:
        number = float(value or 0.0)
    except Exception:
        return ""
    return f"{number:,.2f}".replace(",", " ").replace(".", ",")


def _to_number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _has_amounts(row: dict[str, object]) -> bool:
    return any(abs(_to_number(row.get(key))) > 1e-9 for key in ("ib", "endring", "ub"))


def _format_a07_option(code: str, label: str | None = None) -> str:
    code_text = str(code or "").strip()
    label_text = str(label or "").strip()
    if not code_text:
        return ""
    if label_text:
        return f"{code_text} - {label_text}"
    return code_text


def _parse_a07_option(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if " - " in text:
        return text.split(" - ", 1)[0].strip()
    return text


def _build_account_rows(kontoer: Any) -> list[dict[str, object]]:
    if pd is not None and isinstance(kontoer, pd.DataFrame):
        if "Konto" not in kontoer.columns:
            return []
        name_col = "Navn" if "Navn" in kontoer.columns else "Kontonavn" if "Kontonavn" in kontoer.columns else None
        rows: list[dict[str, object]] = []
        for _, row in kontoer.iterrows():
            konto = str(row.get("Konto", "") or "").strip()
            if not konto:
                continue
            rows.append(
                {
                    "konto": konto,
                    "navn": str(row.get(name_col, "") or "").strip() if name_col else "",
                    "ib": _to_number(row.get("IB")),
                    "endring": _to_number(row.get("Endring")),
                    "ub": _to_number(row.get("UB")),
                }
            )
        return rows

    normalized: list[dict[str, object]] = []
    for item in kontoer or []:
        try:
            konto = str(item[0] or "").strip()
            navn = str(item[1] or "").strip()
        except Exception:
            continue
        if not konto:
            continue
        normalized.append(
            {
                "konto": konto,
                "navn": navn,
                "ib": 0.0,
                "endring": 0.0,
                "ub": 0.0,
            }
        )
    return normalized


def _build_group_summary_text(
    rows: Iterable[dict[str, object]],
    mapping: dict[str, str],
    a07_mapping: dict[str, str] | None = None,
    *,
    label_by_id: dict[str, str] | None = None,
) -> str:
    visible_rows = list(rows or [])
    if not visible_rows:
        return "(ingen kontoer i utvalget)"

    labels = dict(label_by_id or {})
    grouped: dict[str, dict[str, float]] = {}
    without_group = 0
    for row in visible_rows:
        konto = str(row.get("konto", "") or "").strip()
        if not konto:
            continue
        group_id = str(mapping.get(konto, "") or "").strip()
        if not group_id:
            without_group += 1
            continue
        group_name = labels.get(group_id, group_id)
        stats = grouped.setdefault(
            group_name,
            {"count": 0.0, "ib": 0.0, "endring": 0.0, "ub": 0.0},
        )
        stats["count"] += 1
        stats["ib"] += _to_number(row.get("ib"))
        stats["endring"] += _to_number(row.get("endring"))
        stats["ub"] += _to_number(row.get("ub"))
    if without_group:
        grouped["(uten kontrollgruppe)"] = {
            "count": float(without_group),
            "ib": sum(_to_number(row.get("ib")) for row in visible_rows if not str(mapping.get(str(row.get("konto", "") or "").strip(), "") or "").strip()),
            "endring": sum(_to_number(row.get("endring")) for row in visible_rows if not str(mapping.get(str(row.get("konto", "") or "").strip(), "") or "").strip()),
            "ub": sum(_to_number(row.get("ub")) for row in visible_rows if not str(mapping.get(str(row.get("konto", "") or "").strip(), "") or "").strip()),
        }

    total_accounts = len(visible_rows)
    classified_accounts = total_accounts - without_group
    a07_assigned = sum(
        1
        for row in visible_rows
        if str((a07_mapping or {}).get(str(row.get("konto", "") or "").strip(), "") or "").strip()
    )

    lines = [
        f"Viser {total_accounts} kontoer | Kontrollgruppe {classified_accounts} | Uklassifisert {without_group} | A07-kode {a07_assigned}",
    ]
    def _sort_key(item: tuple[str, dict[str, float]]) -> tuple[int, float, str]:
        name, stats = item
        is_unclassified = 0 if name == "(uten kontrollgruppe)" else 1
        return (is_unclassified, -abs(float(stats.get("endring", 0.0))), name.casefold())

    for group_name, stats in sorted(grouped.items(), key=_sort_key):
        count = int(stats.get("count", 0.0))
        suffix = "konto" if count == 1 else "kontoer"
        lines.append(
            f"{group_name}: {count} {suffix} | Endring {_fmt_amount(stats.get('endring'))} | UB {_fmt_amount(stats.get('ub'))}"
        )
    return "\n".join(lines)


def open_klassifisering_editor(
    master: Any,
    *,
    client: str,
    kontoer: Any,
    year: int | None = None,
    on_save: Any = None,
) -> None:
    """Open the classification editor as a toplevel dialog."""
    if tk is None:
        return

    mapping = _kk.load(client)
    load_a07_mapping = getattr(_kk, "load_a07_mapping", None)
    a07_mapping = load_a07_mapping(client, year=year) if callable(load_a07_mapping) else {}
    load_a07_code_options = getattr(_kk, "load_a07_code_options", None)
    a07_options = load_a07_code_options() if callable(load_a07_code_options) else []
    try:
        profile_rows = _kk.build_profile_rows(client, kontoer, year=year)
    except Exception:
        log.exception("Kunne ikke bygge profilrader for kontoklassifisering")
        profile_rows = []

    dlg = _KlassifiseringsEditor(
        master,
        client=client,
        year=year,
        kontoer=kontoer,
        mapping=mapping,
        a07_mapping=a07_mapping,
        a07_options=a07_options,
        profile_rows=profile_rows,
        on_save=on_save,
    )
    dlg.grab_set()
    master.wait_window(dlg)


class _KlassifiseringsEditor(tk.Toplevel):  # type: ignore[misc]
    def __init__(
        self,
        master: Any,
        *,
        client: str,
        year: int | None,
        kontoer: Any,
        mapping: dict[str, str],
        a07_mapping: dict[str, str],
        a07_options: list[tuple[str, str]],
        profile_rows: list[Any],
        on_save: Any,
    ) -> None:
        super().__init__(master)
        self._client = client
        self._year = year
        self._konto_rows = _build_account_rows(kontoer)
        self._mapping = dict(mapping)
        self._a07_mapping = {
            str(account_no).strip(): str(code).strip()
            for account_no, code in (a07_mapping or {}).items()
            if str(account_no).strip()
        }
        self._a07_options = [
            (str(code).strip(), str(label or "").strip())
            for code, label in (a07_options or [])
            if str(code).strip()
        ]
        self._profile_rows = {
            str(getattr(row, "account_no", "")).strip(): row
            for row in (profile_rows or [])
            if str(getattr(row, "account_no", "")).strip()
        }
        self._catalog = _kk.load_catalog()
        self._group_label_by_id: dict[str, str] = {}
        self._group_id_by_label: dict[str, str] = {}
        self._dirty_group_accounts: set[str] = set()
        self._dirty_a07_accounts: set[str] = set()
        self._on_save = on_save
        self._filter_var = tk.StringVar()
        self._group_filter_var = tk.StringVar(value="(alle)")
        self._only_nonzero_var = tk.BooleanVar(value=True)

        self.title(f"Kontoklassifisering - {client}")
        self.geometry("1080x640")
        self.resizable(True, True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")
        tb.columnconfigure(3, weight=1)

        ttk.Label(tb, text="Sok konto/navn:").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(tb, textvariable=self._filter_var, width=24).grid(row=0, column=1, padx=(0, 10))
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        ttk.Checkbutton(
            tb,
            text="Kun linjer med verdi",
            variable=self._only_nonzero_var,
            command=self._apply_filter,
        ).grid(row=0, column=2, sticky="w", padx=(0, 10))

        ttk.Label(tb, text="Vis gruppe:").grid(row=0, column=3, sticky="e", padx=(0, 4))
        self._group_cb = ttk.Combobox(tb, textvariable=self._group_filter_var, state="readonly", width=28)
        self._group_cb.grid(row=0, column=4, padx=(0, 10))
        self._group_cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Button(tb, text="Nullstill filter", width=14, command=self._clear_filter).grid(row=0, column=5, padx=(0, 10))
        ttk.Button(tb, text="Fjern alle grupper", command=self._clear_all_groups).grid(row=0, column=6, padx=(0, 4))

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        left = ttk.Frame(pane)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pane.add(left, weight=4)

        cols = ("konto", "kontonavn", "ib", "endring", "ub", "gruppe", "a07", "kilde", "sikkerhet")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="extended")
        self._tree.heading("konto", text="Konto", anchor="w")
        self._tree.heading("kontonavn", text="Navn", anchor="w")
        self._tree.heading("ib", text="IB", anchor="e")
        self._tree.heading("endring", text="Endring", anchor="e")
        self._tree.heading("ub", text="UB", anchor="e")
        self._tree.heading("gruppe", text="Kontrollgruppe", anchor="w")
        self._tree.heading("a07", text="A07-kode", anchor="w")
        self._tree.heading("kilde", text="Kilde", anchor="w")
        self._tree.heading("sikkerhet", text="Sikkerhet", anchor="e")
        self._tree.column("konto", width=90, anchor="w", stretch=False)
        self._tree.column("kontonavn", width=260, anchor="w", stretch=True)
        self._tree.column("ib", width=110, anchor="e", stretch=False)
        self._tree.column("endring", width=110, anchor="e", stretch=False)
        self._tree.column("ub", width=110, anchor="e", stretch=False)
        self._tree.column("gruppe", width=200, anchor="w", stretch=False)
        self._tree.column("a07", width=150, anchor="w", stretch=False)
        self._tree.column("kilde", width=110, anchor="w", stretch=False)
        self._tree.column("sikkerhet", width=90, anchor="e", stretch=False)
        self._tree.tag_configure("assigned", foreground="#1A56A0")
        self._tree.tag_configure("unassigned", foreground="#888888")
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=vsb.set)

        right = ttk.Frame(pane, padding=(8, 4))
        right.rowconfigure(11, weight=1)
        right.columnconfigure(0, weight=1)
        pane.add(right, weight=1)

        ttk.Label(right, text="Tildel kontrollgruppe til valgte kontoer:", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        self._assign_var = tk.StringVar()
        self._assign_cb = ttk.Combobox(right, textvariable=self._assign_var, width=28)
        self._assign_cb.grid(row=1, column=0, sticky="ew", pady=(0, 4))

        ttk.Button(right, text="Tildel gruppe >", command=self._assign_group).grid(
            row=2, column=0, sticky="new", pady=(0, 6)
        )

        ttk.Separator(right, orient="horizontal").grid(row=3, column=0, sticky="ew", pady=8)
        ttk.Button(right, text="Fjern gruppe (valgte)", command=self._remove_group).grid(
            row=4, column=0, sticky="new", pady=(0, 4)
        )
        ttk.Separator(right, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=8)

        ttk.Label(right, text="Tildel A07-kode til valgte kontoer:", font=("TkDefaultFont", 10, "bold")).grid(
            row=6, column=0, sticky="w", pady=(0, 6)
        )
        self._a07_assign_var = tk.StringVar()
        self._a07_assign_cb = ttk.Combobox(right, textvariable=self._a07_assign_var, width=28)
        self._a07_assign_cb.grid(row=7, column=0, sticky="ew", pady=(0, 4))

        ttk.Button(right, text="Tildel A07-kode >", command=self._assign_a07_code).grid(
            row=8, column=0, sticky="new", pady=(0, 6)
        )
        ttk.Button(right, text="Fjern A07-kode (valgte)", command=self._remove_a07_code).grid(
            row=9, column=0, sticky="new", pady=(0, 4)
        )
        ttk.Separator(right, orient="horizontal").grid(row=10, column=0, sticky="ew", pady=8)

        ttk.Label(right, text="Grupper i bruk:", font=("TkDefaultFont", 9, "bold")).grid(
            row=11, column=0, sticky="w", pady=(0, 4)
        )
        self._summary_text = tk.Text(
            right,
            width=30,
            height=14,
            state="disabled",
            relief="flat",
            bg="#F4F6F9",
            font=("TkDefaultFont", 9),
        )
        self._summary_text.grid(row=12, column=0, sticky="nsew")

        bot = ttk.Frame(self, padding=(6, 4))
        bot.grid(row=2, column=0, sticky="ew")
        self._status_lbl = ttk.Label(bot, text="", foreground="#555")
        self._status_lbl.pack(side="left")

        ttk.Button(bot, text="Lukk", command=self.destroy, width=10).pack(side="right", padx=(4, 0))
        ttk.Button(bot, text="Lagre", command=self._save, width=10).pack(side="right")

    def _profile_for(self, konto: str) -> Any:
        return self._profile_rows.get(str(konto).strip())

    def _row_values(self, row: dict[str, object]) -> tuple[str, str, str, str, str, str, str, str, str]:
        konto = str(row.get("konto", "") or "").strip()
        navn = str(row.get("navn", "") or "").strip()
        group = self._display_group(self._mapping.get(konto, ""))
        profile = self._profile_for(konto)
        if konto in self._dirty_a07_accounts:
            a07_code = self._a07_mapping.get(konto, "")
        else:
            a07_code = str(
                self._a07_mapping.get(konto, "")
                or getattr(profile, "a07_code", "")
                or getattr(profile, "suggested_a07_code", "")
                or ""
            )
        if konto in self._dirty_group_accounts or konto in self._dirty_a07_accounts:
            source = "manual"
            confidence_text = "100%"
        else:
            source = _row_source_label(getattr(profile, "source", "") or "")
            confidence_text = _fmt_confidence(getattr(profile, "confidence", None))
        return (
            konto,
            navn,
            _fmt_amount(row.get("ib")),
            _fmt_amount(row.get("endring")),
            _fmt_amount(row.get("ub")),
            group,
            a07_code,
            source,
            confidence_text,
        )

    def _populate(self) -> None:
        self._refresh_tree(self._konto_rows)
        self._refresh_combos()
        self._refresh_summary(self._konto_rows)

    def _display_group(self, group_id: str | None) -> str:
        raw = str(group_id or "").strip()
        if not raw:
            return ""
        return self._group_label_by_id.get(raw, raw)

    def _resolve_group_value(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        return self._group_id_by_label.get(raw, raw)

    def _refresh_tree(self, kontoer: list[dict[str, object]]) -> None:
        selected = tuple(self._tree.selection())
        self._tree.delete(*self._tree.get_children())
        for row in kontoer:
            konto = str(row.get("konto", "") or "").strip()
            if not konto:
                continue
            group = self._mapping.get(konto, "")
            tag = "assigned" if group else "unassigned"
            self._tree.insert("", "end", iid=konto, values=self._row_values(row), tags=(tag,))
        for konto in selected:
            if self._tree.exists(konto):
                self._tree.selection_add(konto)

    def _refresh_combos(self) -> None:
        entries = list(_kk.default_group_entries(scope="analyse"))
        label_by_id = {group_id: label for group_id, label in entries}
        for group_id in sorted({str(value).strip() for value in self._mapping.values() if str(value).strip()}):
            label_by_id.setdefault(group_id, _kk.group_label(group_id) or group_id)
        self._group_label_by_id = label_by_id
        self._group_id_by_label = {}
        ordered_labels: list[str] = []
        for group_id, label in entries:
            if not label:
                continue
            self._group_id_by_label.setdefault(label, group_id)
            if label not in ordered_labels:
                ordered_labels.append(label)
        extra_labels = sorted(
            {
                label
                for group_id, label in label_by_id.items()
                if label and label not in ordered_labels
            },
            key=str.casefold,
        )
        for label in extra_labels:
            ordered_labels.append(label)
            resolved = next((gid for gid, lbl in label_by_id.items() if lbl == label), "")
            if resolved:
                self._group_id_by_label.setdefault(label, resolved)
        self._assign_cb["values"] = ordered_labels
        self._group_cb["values"] = ["(alle)", "(uten gruppe)"] + ordered_labels
        self._a07_assign_cb["values"] = [_format_a07_option(code, label) for code, label in self._a07_options]

    def _refresh_summary(self, rows: list[dict[str, object]] | None = None) -> None:
        text = _build_group_summary_text(
            rows if rows is not None else self._konto_rows,
            self._mapping,
            self._a07_mapping,
            label_by_id=self._group_label_by_id,
        )
        try:
            self._summary_text.configure(state="normal")
            self._summary_text.delete("1.0", "end")
            self._summary_text.insert("end", text)
            self._summary_text.configure(state="disabled")
        except Exception:
            pass

    def _apply_filter(self) -> None:
        query = self._filter_var.get().strip().lower()
        group_filter = self._group_filter_var.get()
        result: list[dict[str, object]] = []
        for row in self._konto_rows:
            konto = str(row.get("konto", "") or "").strip()
            navn = str(row.get("navn", "") or "").strip()
            if query and query not in konto.lower() and query not in navn.lower():
                continue
            if self._only_nonzero_var.get() and not _has_amounts(row):
                continue
            group_id = self._mapping.get(konto, "")
            if group_filter == "(uten gruppe)" and group_id:
                continue
            group_name = self._display_group(group_id)
            if group_filter not in ("(alle)", "(uten gruppe)") and group_name != group_filter:
                continue
            result.append(row)
        self._refresh_tree(result)
        self._refresh_summary(result)

    def _clear_filter(self) -> None:
        self._filter_var.set("")
        self._group_filter_var.set("(alle)")
        self._only_nonzero_var.set(True)
        self._apply_filter()

    def _on_tree_select(self, _event: Any = None) -> None:
        selection = self._tree.selection()
        count = len(selection)
        self._status_lbl.configure(text=f"{count} konto{'er' if count != 1 else ''} valgt")

    def _assign_group(self) -> None:
        group_name = self._assign_var.get().strip()
        group_id = self._resolve_group_value(group_name)
        selection = self._tree.selection()
        if not group_id or not selection:
            return
        for konto in selection:
            self._mapping[konto] = group_id
            self._dirty_group_accounts.add(str(konto))
        self._apply_filter()
        self._refresh_combos()
        self._status_lbl.configure(text=f"Tildelte '{self._display_group(group_id)}' til {len(selection)} kontoer")

    def _remove_group(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        for konto in selection:
            self._mapping.pop(konto, None)
            self._dirty_group_accounts.add(str(konto))
        self._apply_filter()
        self._status_lbl.configure(text=f"Fjernet gruppe fra {len(selection)} kontoer")

    def _clear_all_groups(self) -> None:
        self._mapping.clear()
        self._dirty_group_accounts = {
            str(row.get("konto", "") or "").strip()
            for row in self._konto_rows
            if str(row.get("konto", "") or "").strip()
        }
        self._apply_filter()
        self._status_lbl.configure(text="Alle grupper fjernet")

    def _assign_a07_code(self) -> None:
        code = _parse_a07_option(self._a07_assign_var.get())
        selection = self._tree.selection()
        if not code or not selection:
            return
        for konto in selection:
            self._a07_mapping[str(konto)] = code
            self._dirty_a07_accounts.add(str(konto))
        self._apply_filter()
        self._status_lbl.configure(text=f"Tildelte A07-kode '{code}' til {len(selection)} kontoer")

    def _remove_a07_code(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        for konto in selection:
            self._a07_mapping.pop(str(konto), None)
            self._dirty_a07_accounts.add(str(konto))
        self._apply_filter()
        self._status_lbl.configure(text=f"Fjernet A07-kode fra {len(selection)} kontoer")

    def _save(self) -> None:
        _kk.save(self._client, self._mapping)
        save_a07_mapping = getattr(_kk, "save_a07_mapping", None)
        if callable(save_a07_mapping):
            save_a07_mapping(self._client, self._a07_mapping, year=self._year)
        self._status_lbl.configure(text="Lagret.")
        if callable(self._on_save):
            try:
                self._on_save()
            except Exception:
                pass
