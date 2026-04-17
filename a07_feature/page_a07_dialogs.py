from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Sequence

import pandas as pd

from formatting import format_number_no

_NUMERIC_COLUMNS_ZERO_DECIMALS = {"AntallKontoer"}
_NUMERIC_COLUMNS_THREE_DECIMALS = {"Score"}
_NUMERIC_COLUMNS_TWO_DECIMALS = {
    "A07_Belop",
    "A07",
    "AgaGrunnlag",
    "Belop",
    "Diff",
    "Endring",
    "FradragPaalopt",
    "GL_Belop",
    "GL_Sum",
    "IB",
    "KostnadsfortYtelse",
    "SamledeYtelser",
    "TilleggTidligereAar",
    "UB",
}


@dataclass(frozen=True)
class _PickerOption:
    key: str
    label: str
    search_text: str


def _format_picker_amount(value: object, *, decimals: int = 2) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, Decimal):
        return format_number_no(value, decimals)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number_no(value, decimals)
    if isinstance(value, str):
        formatted = format_number_no(value, decimals)
        return formatted if formatted != value else value
    return str(value)


def _numeric_decimals_for_column(column_id: str) -> int | None:
    if column_id in _NUMERIC_COLUMNS_ZERO_DECIMALS:
        return 0
    if column_id in _NUMERIC_COLUMNS_THREE_DECIMALS:
        return 3
    if column_id in _NUMERIC_COLUMNS_TWO_DECIMALS:
        return 2
    return None


def build_gl_picker_options(
    gl_df: pd.DataFrame,
    *,
    basis_col: str = "Endring",
) -> list[_PickerOption]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return []

    amount_col = basis_col if basis_col in gl_df.columns else "Belop"
    work = gl_df.copy()
    work["Konto"] = work["Konto"].astype(str).str.strip()
    work = work[work["Konto"] != ""].copy()
    work = work.drop_duplicates(subset=["Konto"], keep="first")
    work = work.sort_values(by=["Konto"], kind="stable")

    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        konto = str(row.get("Konto") or "").strip()
        if not konto:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get(amount_col))
        label_parts = [konto]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        label = " | ".join(label_parts)
        search_text = " ".join(part.lower() for part in label_parts if part)
        options.append(_PickerOption(key=konto, label=label, search_text=search_text))
    return options


def build_a07_picker_options(a07_df: pd.DataFrame) -> list[_PickerOption]:
    if a07_df is None or a07_df.empty or "Kode" not in a07_df.columns:
        return []

    work = a07_df.copy()
    work["Kode"] = work["Kode"].astype(str).str.strip()
    work = work[work["Kode"] != ""].copy()
    work = work.drop_duplicates(subset=["Kode"], keep="first")
    work = work.sort_values(by=["Kode"], kind="stable")

    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        kode = str(row.get("Kode") or "").strip()
        if not kode:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get("Belop"))
        label_parts = [kode]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        label = " | ".join(label_parts)
        search_text = " ".join(part.lower() for part in label_parts if part)
        options.append(_PickerOption(key=kode, label=label, search_text=search_text))
    return options


def _filter_picker_options(options: Sequence[_PickerOption], query: str) -> list[_PickerOption]:
    query_s = str(query or "").strip().lower()
    if not query_s:
        return list(options)
    return [option for option in options if query_s in option.search_text]


def apply_manual_mapping_choice(
    mapping: dict[str, str],
    konto: str | None,
    kode: str | None,
) -> tuple[str, str]:
    konto_s = str(konto or "").strip()
    kode_s = str(kode or "").strip()
    if not konto_s:
        raise ValueError("Mangler konto for mapping.")
    if not kode_s:
        raise ValueError("Mangler A07-kode for mapping.")

    mapping[konto_s] = kode_s
    return konto_s, kode_s


def apply_manual_mapping_choices(
    mapping: dict[str, str],
    accounts: Sequence[object],
    kode: str | None,
) -> list[str]:
    kode_s = str(kode or "").strip()
    if not kode_s:
        raise ValueError("Mangler A07-kode for mapping.")

    assigned: list[str] = []
    seen: set[str] = set()
    for account in accounts or ():
        konto_s = str(account or "").strip()
        if not konto_s or konto_s in seen:
            continue
        apply_manual_mapping_choice(mapping, konto_s, kode_s)
        assigned.append(konto_s)
        seen.add(konto_s)

    if not assigned:
        raise ValueError("Mangler konto for mapping.")

    return assigned


def remove_mapping_accounts(mapping: dict[str, str], accounts: Sequence[object]) -> list[str]:
    removed: list[str] = []
    seen: set[str] = set()
    for account in accounts or ():
        konto_s = str(account or "").strip()
        if not konto_s or konto_s in seen:
            continue
        seen.add(konto_s)
        if konto_s in mapping:
            mapping.pop(konto_s, None)
            removed.append(konto_s)
    return removed


def _editor_list_items(text: object) -> list[str]:
    raw = str(text or "")
    parts = [
        part.strip()
        for line in raw.splitlines()
        for part in line.split(",")
        if part.strip()
    ]
    return parts


def _format_editor_list(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return ", ".join(out)


def _format_editor_ranges(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    out: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            start = str(value[0]).strip()
            end = str(value[1]).strip()
            if start and end:
                out.append(f"{start}-{end}" if start != end else start)
                continue
        text = str(value or "").strip()
        if text:
            out.append(text)
    return "\n".join(out)


def _parse_editor_ints(text: object) -> list[int]:
    out: list[int] = []
    for item in _editor_list_items(text):
        digits = "".join(ch for ch in item if ch.isdigit())
        if digits:
            out.append(int(digits))
    return out


def _format_special_add_editor(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    lines: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        account = str(value.get("account") or "").strip()
        if not account:
            continue
        basis = str(value.get("basis") or "").strip()
        weight = value.get("weight", 1.0)
        weight_text = str(weight).strip()
        parts = [account]
        if basis or weight_text:
            parts.append(basis)
        if weight_text:
            parts.append(weight_text)
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _parse_special_add_editor(text: object) -> list[dict[str, object]]:
    lines = str(text or "").splitlines()
    out: list[dict[str, object]] = []
    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if not parts:
            continue
        account = str(parts[0] or "").strip()
        if not account:
            continue
        basis = str(parts[1] or "").strip() if len(parts) >= 2 else ""
        weight_raw = str(parts[2] or "").strip() if len(parts) >= 3 else ""
        try:
            weight = float(weight_raw) if weight_raw else 1.0
        except Exception:
            weight = 1.0
        item: dict[str, object] = {"account": account}
        if basis:
            item["basis"] = basis
        if weight != 1.0:
            item["weight"] = weight
        out.append(item)
    return out


def _format_aliases_editor(aliases: object) -> str:
    if not isinstance(aliases, dict):
        return ""
    lines: list[str] = []
    for raw_key in sorted(aliases, key=lambda value: str(value).lower()):
        key = str(raw_key or "").strip()
        raw_values = aliases.get(raw_key)
        if not key or not isinstance(raw_values, (list, tuple)):
            continue
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        lines.append(f"{key} = {', '.join(values)}" if values else key)
    return "\n".join(lines)


def _parse_aliases_editor(text: object) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw_line in str(text or "").splitlines():
        line = str(raw_line).strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key_raw, values_raw = line.split("=", 1)
        else:
            key_raw, values_raw = line, ""
        key = str(key_raw or "").strip()
        if not key:
            continue
        out[key] = _editor_list_items(values_raw)
    return out


def _count_nonempty_mapping(mapping: dict[str, str]) -> int:
    return sum(1 for value in (mapping or {}).values() if str(value).strip())


def _parse_konto_tokens(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def open_manual_mapping_dialog(
    parent: tk.Misc,
    *,
    account_options: Sequence[_PickerOption],
    code_options: Sequence[_PickerOption],
    initial_account: str | None = None,
    initial_code: str | None = None,
    title: str = "Ny eller rediger mapping",
) -> tuple[str, str] | None:
    if not account_options or not code_options:
        return None

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("1100x560")

    result: dict[str, tuple[str, str] | None] = {"value": None}
    selected_account = str(initial_account or "").strip() or None
    selected_code = str(initial_code or "").strip() or None
    filtered_accounts = list(account_options)
    filtered_codes = list(code_options)

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)

    ttk.Label(
        outer,
        text="Velg konto og A07-kode. Skriv i søkefeltene for å filtrere listene.",
    ).pack(anchor="w")

    columns = ttk.Frame(outer)
    columns.pack(fill="both", expand=True, pady=(8, 0))
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    columns.rowconfigure(0, weight=1)

    status_var = tk.StringVar(value="")
    account_query = tk.StringVar(value="")
    code_query = tk.StringVar(value="")

    def _build_picker_column(parent_frame: ttk.Frame, title_text: str) -> tuple[ttk.Entry, tk.Listbox, ttk.Label]:
        ttk.Label(parent_frame, text=title_text).pack(anchor="w")
        entry = ttk.Entry(parent_frame)
        entry.pack(fill="x", pady=(4, 6))

        list_frame = ttk.Frame(parent_frame)
        list_frame.pack(fill="both", expand=True)

        ybar = ttk.Scrollbar(list_frame, orient="vertical")
        ybar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, activestyle="dotbox", exportselection=False, yscrollcommand=ybar.set)
        listbox.pack(side="left", fill="both", expand=True)
        ybar.config(command=listbox.yview)

        count_label = ttk.Label(parent_frame, text="")
        count_label.pack(anchor="w", pady=(6, 0))
        return entry, listbox, count_label

    account_frame = ttk.Frame(columns)
    account_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    code_frame = ttk.Frame(columns)
    code_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    account_entry, account_listbox, account_count = _build_picker_column(account_frame, "Konto")
    code_entry, code_listbox, code_count = _build_picker_column(code_frame, "A07-kode")

    account_entry.configure(textvariable=account_query)
    code_entry.configure(textvariable=code_query)

    def _selected_option(listbox: tk.Listbox, options: Sequence[_PickerOption]) -> _PickerOption | None:
        try:
            idx = int(listbox.curselection()[0])
        except Exception:
            return None
        if idx < 0 or idx >= len(options):
            return None
        return options[idx]

    def _fill_list(
        listbox: tk.Listbox,
        options: Sequence[_PickerOption],
        count_label: ttk.Label,
        total_count: int,
        selected_key: str | None,
    ) -> None:
        listbox.delete(0, tk.END)
        for option in options:
            listbox.insert(tk.END, option.label)

        count_label.configure(text=f"Viser {len(options)} av {total_count}")
        if not options:
            return

        idx = 0
        if selected_key:
            for pos, option in enumerate(options):
                if option.key == selected_key:
                    idx = pos
                    break

        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)

    def _update_status() -> None:
        account_text = selected_account or "-"
        code_text = selected_code or "-"
        status_var.set(f"Valg: {account_text} -> {code_text}")

    def _refresh_account_list() -> None:
        nonlocal filtered_accounts, selected_account
        filtered_accounts = _filter_picker_options(account_options, account_query.get())
        _fill_list(
            account_listbox,
            filtered_accounts,
            account_count,
            len(account_options),
            selected_account,
        )
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _refresh_code_list() -> None:
        nonlocal filtered_codes, selected_code
        filtered_codes = _filter_picker_options(code_options, code_query.get())
        _fill_list(
            code_listbox,
            filtered_codes,
            code_count,
            len(code_options),
            selected_code,
        )
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_account_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_account
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _on_code_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_code
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_ok() -> None:
        if not selected_account or not selected_code:
            messagebox.showinfo("A07", "Velg både konto og A07-kode.", parent=win)
            return
        result["value"] = (selected_account, selected_code)
        win.destroy()

    def _on_cancel() -> None:
        result["value"] = None
        win.destroy()

    account_query.trace_add("write", lambda *_args: _refresh_account_list())
    code_query.trace_add("write", lambda *_args: _refresh_code_list())

    account_listbox.bind("<<ListboxSelect>>", _on_account_select)
    code_listbox.bind("<<ListboxSelect>>", _on_code_select)
    account_listbox.bind("<Double-Button-1>", lambda _event: code_entry.focus_set())
    code_listbox.bind("<Double-Button-1>", lambda _event: _on_ok())
    win.bind("<Return>", lambda *_args: _on_ok())
    win.bind("<Escape>", lambda *_args: _on_cancel())

    ttk.Label(outer, textvariable=status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="Avbryt", command=_on_cancel).pack(side="right")
    ttk.Button(buttons, text="Bruk mapping", command=_on_ok).pack(side="right", padx=(0, 6))

    _refresh_account_list()
    _refresh_code_list()
    account_entry.focus_set()

    win.wait_window()
    return result["value"]
