"""tilleggsposteringer.py

Tilleggsposteringer (supplementary journal entries) per klient/år.

Lar brukeren legge inn årsoppgjørsposteringer som justerer
saldobalanse-tall og flyter gjennom pivot og SB-visning automatisk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Optional

import pandas as pd

_EXCEL_EXTS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}


@dataclass(frozen=True)
class SupplementaryImportResult:
    entries: list[dict]
    total_rows: int
    imported_rows: int
    skipped_rows: int


def import_entries_from_excel(path: str | Path) -> SupplementaryImportResult:
    """Importer tilleggsposteringer fra Excel-formatet brukt for ÅO-posteringer."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if file_path.suffix.lower() not in _EXCEL_EXTS:
        raise ValueError("Kun Excel-filer (.xlsx/.xlsm/.xltx/.xltm/.xls) støttes.")

    from excel_importer import read_excel_robust

    df = read_excel_robust(str(file_path))
    return _parse_import_dataframe(df)


def _parse_import_dataframe(df: pd.DataFrame) -> SupplementaryImportResult:
    if df is None or df.empty:
        return SupplementaryImportResult(entries=[], total_rows=0, imported_rows=0, skipped_rows=0)

    col_konto = _find_source_col(df, "kontonr", "kontonummer", "konto", "account")
    col_bilag = _find_source_col(df, "bilagsnr", "bilagsnummer", "bilag", "voucher")
    col_text = _find_source_col(df, "tekst", "beskrivelse", "description", "transaksjonsbeskrivelse")
    col_kontonavn = _find_source_col(df, "kontonavn", "accountname", "account name")
    col_netto = _find_source_col(df, "netto", "beløp", "belop", "amount")
    col_debet = _find_source_col(df, "debet", "debit")
    col_kredit = _find_source_col(df, "kredit", "credit")
    col_bilag_prefix = _find_adjacent_blank_col(df, anchor_col=col_bilag)

    if not col_konto:
        raise ValueError("Fant ikke kolonne for kontonummer i importfilen.")
    if not any((col_netto, col_debet, col_kredit)):
        raise ValueError("Fant ikke kolonne for beløp/netto/debet/kredit i importfilen.")

    entries: list[dict] = []
    total_rows = len(df.index)

    for _, row in df.iterrows():
        konto = _clean_account(row.get(col_konto))
        amount = _resolve_amount(row, col_netto=col_netto, col_debet=col_debet, col_kredit=col_kredit)
        if not konto or amount is None or abs(amount) < 0.005:
            continue
        entries.append(
            {
                "bilag": _build_bilag(
                    row.get(col_bilag_prefix) if col_bilag_prefix else None,
                    row.get(col_bilag) if col_bilag else None,
                ),
                "konto": konto,
                "belop": amount,
                "beskrivelse": _first_text(
                    row.get(col_text) if col_text else None,
                    row.get(col_kontonavn) if col_kontonavn else None,
                ),
            }
        )

    return SupplementaryImportResult(
        entries=entries,
        total_rows=total_rows,
        imported_rows=len(entries),
        skipped_rows=max(total_rows - len(entries), 0),
    )


def _find_source_col(df: pd.DataFrame, *candidates: str) -> str | None:
    norms = {str(col): _norm_text(col) for col in df.columns}
    for candidate in candidates:
        wanted = _norm_text(candidate)
        for col, normalized in norms.items():
            if normalized == wanted:
                return col
    for candidate in candidates:
        wanted = _norm_text(candidate)
        for col, normalized in norms.items():
            if wanted and wanted in normalized:
                return col
    return None


def _find_adjacent_blank_col(df: pd.DataFrame, *, anchor_col: str | None) -> str | None:
    if not anchor_col:
        return None
    columns = list(df.columns)
    try:
        idx = columns.index(anchor_col)
    except ValueError:
        return None
    for neighbour in (idx - 1, idx + 1):
        if 0 <= neighbour < len(columns):
            name = str(columns[neighbour])
            if _is_blank_header(name):
                return name
    return None


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _is_blank_header(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text == "" or text.startswith("unnamed:")


def _clean_account(value: Any) -> str:
    text = _stringify_cell(value)
    if not text:
        return ""
    digits = re.sub(r"\D+", "", text)
    return digits or text


def _build_bilag(prefix: Any, bilagsnr: Any) -> str:
    parts = [_stringify_cell(prefix), _stringify_cell(bilagsnr)]
    return " ".join(part for part in parts if part)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _stringify_cell(value)
        if text:
            return text
    return ""


def _stringify_cell(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value}".rstrip("0").rstrip(".")

    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none"}:
        return ""
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _to_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none"}:
        return None

    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def _resolve_amount(
    row: pd.Series,
    *,
    col_netto: str | None,
    col_debet: str | None,
    col_kredit: str | None,
) -> float | None:
    netto = _to_float(row.get(col_netto)) if col_netto else None
    if netto is not None and abs(netto) > 0.005:
        return netto

    debet = _to_float(row.get(col_debet)) if col_debet else None
    kredit = _to_float(row.get(col_kredit)) if col_kredit else None
    amount = (debet or 0.0) - (kredit or 0.0)
    if abs(amount) > 0.005:
        return amount

    if netto is not None:
        return netto
    return None


# =====================================================================
# Juster SB med tilleggsposteringer
# =====================================================================

def apply_to_sb(sb_df: pd.DataFrame, entries: list[dict]) -> pd.DataFrame:
    """Returner en kopi av sb_df med tilleggsposteringer lagt til.

    Justerer 'ub' og 'netto'/'endring' for eksisterende kontoer.
    Legger til nye rader for kontoer som ikke finnes i SB.
    """
    if not entries or sb_df is None or sb_df.empty:
        return sb_df

    df = sb_df.copy()

    # Finn kolonnenavn (case-insensitive)
    col_konto = _find_col(df, "konto")
    col_ub = _find_col(df, "ub")
    col_netto = _find_col(df, ("netto", "endring"))
    col_ib = _find_col(df, "ib")
    col_kontonavn = _find_col(df, "kontonavn")

    if not col_konto or not col_ub:
        return sb_df

    # Ensure numeric
    for c in (col_ub, col_netto, col_ib):
        if c and c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Aggreger entries per konto
    konto_sums: dict[str, float] = {}
    konto_beskr: dict[str, str] = {}
    for e in entries:
        k = str(e.get("konto", "")).strip()
        b = float(e.get("belop", 0.0))
        if k and abs(b) > 0.005:
            konto_sums[k] = konto_sums.get(k, 0.0) + b
            if not konto_beskr.get(k):
                konto_beskr[k] = str(e.get("beskrivelse", ""))

    # Juster eksisterende rader
    existing = set(df[col_konto].astype(str))
    for konto, amount in konto_sums.items():
        if konto in existing:
            mask = df[col_konto].astype(str) == konto
            df.loc[mask, col_ub] = df.loc[mask, col_ub] + amount
            if col_netto:
                df.loc[mask, col_netto] = df.loc[mask, col_netto] + amount

    # Legg til nye rader for kontoer som ikke finnes i SB
    new_rows = []
    for konto, amount in konto_sums.items():
        if konto not in existing:
            row = {c: "" for c in df.columns}
            row[col_konto] = konto
            if col_kontonavn:
                row[col_kontonavn] = konto_beskr.get(konto, "Tilleggspostering")
            if col_ib:
                row[col_ib] = 0.0
            row[col_ub] = amount
            if col_netto:
                row[col_netto] = amount
            new_rows.append(row)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    return df


def _find_col(df: pd.DataFrame, names: str | tuple[str, ...]) -> str | None:
    if isinstance(names, str):
        names = (names,)
    for c in df.columns:
        if c.lower() in names:
            return c
    return None


# =====================================================================
# Dialog
# =====================================================================

def open_dialog(parent: Any, *, client: str, year: str,
                on_changed: Any = None) -> None:
    """Åpne dialogen for tilleggsposteringer."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception:
        return

    import formatting
    import src.shared.regnskap.client_overrides as regnskap_client_overrides

    entries = regnskap_client_overrides.load_supplementary_entries(client, year)

    dlg = tk.Toplevel(parent)
    dlg.title(f"Tilleggsposteringer — {client} ({year})")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.minsize(750, 400)

    # --- Treeview ---
    cols = ("Bilag", "Konto", "Debet", "Kredit", "Beskrivelse")
    tree_frame = ttk.Frame(dlg)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

    tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                        selectmode="extended", height=12)
    tree.grid(row=0, column=0, sticky="nsew")

    v_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    v_scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=v_scroll.set)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)

    tree.heading("Bilag", text="Bilag", anchor="w")
    tree.heading("Konto", text="Konto", anchor="w")
    tree.heading("Debet", text="Debet", anchor="e")
    tree.heading("Kredit", text="Kredit", anchor="e")
    tree.heading("Beskrivelse", text="Beskrivelse", anchor="w")

    tree.column("Bilag", width=80, anchor="w")
    tree.column("Konto", width=80, anchor="w")
    tree.column("Debet", width=120, anchor="e")
    tree.column("Kredit", width=120, anchor="e")
    tree.column("Beskrivelse", width=250, anchor="w", stretch=True)

    # State
    state: dict[str, Any] = {"entries": list(entries), "changed": False}

    def _refresh_tree() -> None:
        for item in tree.get_children():
            tree.delete(item)
        total_debet = 0.0
        total_kredit = 0.0
        for e in state["entries"]:
            belop = float(e.get("belop", 0.0))
            if belop > 0:
                d_txt = formatting.fmt_amount(belop)
                k_txt = ""
                total_debet += belop
            elif belop < 0:
                d_txt = ""
                k_txt = formatting.fmt_amount(abs(belop))
                total_kredit += abs(belop)
            else:
                d_txt = k_txt = ""
            tree.insert("", "end", values=(
                e.get("bilag", ""),
                e.get("konto", ""),
                d_txt, k_txt,
                e.get("beskrivelse", ""),
            ))
        diff = total_debet - total_kredit
        diff_txt = f"Diff: {formatting.fmt_amount(diff)}" if abs(diff) > 0.005 else "Balansert"
        summary_var.set(
            f"Debet: {formatting.fmt_amount(total_debet)}  |  "
            f"Kredit: {formatting.fmt_amount(total_kredit)}  |  "
            f"{diff_txt}  |  "
            f"{len(state['entries'])} linjer"
        )

    # --- Summary ---
    summary_var = tk.StringVar()
    ttk.Label(dlg, textvariable=summary_var, font=("Segoe UI", 9)).pack(
        padx=10, pady=2, anchor="w")

    # --- Buttons ---
    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(fill="x", padx=10, pady=(4, 10))

    def _add_entry() -> None:
        _open_entry_editor(dlg, entry=None, callback=lambda e: (
            state["entries"].append(e),
            _set_changed(),
            _refresh_tree(),
        ))

    def _import_entries() -> None:
        path = filedialog.askopenfilename(
            parent=dlg,
            title="Importer ÅO-posteringer",
            filetypes=[
                ("Excel-filer", "*.xlsx *.xlsm *.xltx *.xltm *.xls"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        try:
            result = import_entries_from_excel(path)
        except Exception as exc:
            messagebox.showerror(
                "Tilleggsposteringer",
                f"Kunne ikke importere filen.\n\n{exc}",
                parent=dlg,
            )
            return

        if not result.entries:
            messagebox.showinfo(
                "Tilleggsposteringer",
                "Fant ingen posteringer med konto og beløp i filen.",
                parent=dlg,
            )
            return

        had_existing = bool(state["entries"])
        import_mode = "append"
        if had_existing:
            ask_choice = getattr(messagebox, "askyesnocancel", None)
            if callable(ask_choice):
                replace = ask_choice(
                    "Tilleggsposteringer",
                    "Det finnes allerede tilleggsposteringer i dialogen.\n\n"
                    "Velg Ja for å erstatte dem, Nei for å legge importen til eksisterende linjer.",
                    parent=dlg,
                )
                if replace is None:
                    return
            else:
                replace = messagebox.askyesno(
                    "Tilleggsposteringer",
                    "Det finnes allerede tilleggsposteringer i dialogen.\n\n"
                    "Velg Ja for å erstatte dem. Velg Nei for å legge importen til eksisterende linjer.",
                    parent=dlg,
                )
            import_mode = "replace" if replace else "append"

        if import_mode == "replace":
            state["entries"] = list(result.entries)
        else:
            state["entries"].extend(result.entries)

        _set_changed()
        _refresh_tree()

        lines = [f"Importerte {result.imported_rows} ÅO-posteringer fra Excel."]
        if import_mode == "replace":
            lines.append("Eksisterende linjer i dialogen ble erstattet.")
        elif had_existing:
            lines.append("Importen ble lagt til eksisterende linjer i dialogen.")
        if result.skipped_rows:
            lines.append(f"Hoppet over {result.skipped_rows} rad(er) uten gyldig konto/beløp.")
        messagebox.showinfo("Tilleggsposteringer", "\n".join(lines), parent=dlg)

    def _edit_entry() -> None:
        sel = tree.selection()
        if not sel:
            return
        idx = tree.index(sel[0])
        if 0 <= idx < len(state["entries"]):
            old = state["entries"][idx]
            _open_entry_editor(dlg, entry=old, callback=lambda e: (
                state["entries"].__setitem__(idx, e),
                _set_changed(),
                _refresh_tree(),
            ))

    def _delete_entries() -> None:
        sel = tree.selection()
        if not sel:
            return
        indices = sorted([tree.index(s) for s in sel], reverse=True)
        for idx in indices:
            if 0 <= idx < len(state["entries"]):
                state["entries"].pop(idx)
        _set_changed()
        _refresh_tree()

    def _set_changed() -> None:
        state["changed"] = True

    def _save_and_close() -> None:
        if state["changed"]:
            regnskap_client_overrides.save_supplementary_entries(
                client, year, state["entries"])
            if callable(on_changed):
                on_changed()
        dlg.destroy()

    def _on_dblclick(_event: Any) -> None:
        _edit_entry()

    tree.bind("<Double-1>", _on_dblclick)
    tree.bind("<Delete>", lambda _e: _delete_entries())

    ttk.Button(btn_frame, text="Legg til", command=_add_entry).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Importer Excel...", command=_import_entries).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Rediger", command=_edit_entry).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Slett", command=_delete_entries).pack(side="left", padx=(0, 4))

    ttk.Button(btn_frame, text="Lagre og lukk", command=_save_and_close).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy).pack(side="right")

    _refresh_tree()

    dlg.update_idletasks()
    w, h = max(dlg.winfo_width(), 750), max(dlg.winfo_height(), 400)
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")


def _open_entry_editor(parent: Any, *, entry: Optional[dict],
                        callback: Any) -> None:
    """Editor for en enkelt tilleggspostering."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return

    dlg = tk.Toplevel(parent)
    dlg.title("Rediger postering" if entry else "Ny postering")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    var_bilag = tk.StringVar(value=entry.get("bilag", "ÅO") if entry else "ÅO")
    var_konto = tk.StringVar(value=entry.get("konto", "") if entry else "")
    var_belop = tk.StringVar()
    var_side = tk.StringVar(value="Debet")
    var_beskr = tk.StringVar(value=entry.get("beskrivelse", "") if entry else "")

    if entry:
        belop = float(entry.get("belop", 0.0))
        if belop < 0:
            var_side.set("Kredit")
            var_belop.set(str(abs(belop)))
        else:
            var_belop.set(str(belop))

    row = 0
    ttk.Label(dlg, text="Bilag:").grid(row=row, column=0, sticky="w", padx=(12, 4), pady=4)
    ttk.Entry(dlg, textvariable=var_bilag, width=12).grid(row=row, column=1, sticky="w", padx=4, pady=4)

    row += 1
    ttk.Label(dlg, text="Konto:").grid(row=row, column=0, sticky="w", padx=(12, 4), pady=4)
    ttk.Entry(dlg, textvariable=var_konto, width=12).grid(row=row, column=1, sticky="w", padx=4, pady=4)

    row += 1
    ttk.Label(dlg, text="Beløp:").grid(row=row, column=0, sticky="w", padx=(12, 4), pady=4)
    amount_frame = ttk.Frame(dlg)
    amount_frame.grid(row=row, column=1, sticky="w", padx=4, pady=4)
    ttk.Entry(amount_frame, textvariable=var_belop, width=14).pack(side="left")
    ttk.Radiobutton(amount_frame, text="Debet", variable=var_side, value="Debet").pack(side="left", padx=(8, 0))
    ttk.Radiobutton(amount_frame, text="Kredit", variable=var_side, value="Kredit").pack(side="left", padx=(4, 0))

    row += 1
    ttk.Label(dlg, text="Beskrivelse:").grid(row=row, column=0, sticky="w", padx=(12, 4), pady=4)
    ttk.Entry(dlg, textvariable=var_beskr, width=40).grid(row=row, column=1, sticky="ew", padx=4, pady=4)

    row += 1
    var_error = tk.StringVar(value="")
    ttk.Label(dlg, textvariable=var_error, foreground="red").grid(
        row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 0),
    )

    row += 1
    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=row, column=0, columnspan=2, sticky="e", padx=12, pady=(4, 12))

    def _ok() -> None:
        konto = var_konto.get().strip()
        if not konto:
            var_error.set("Konto er påkrevd.")
            return
        try:
            raw = var_belop.get().strip().replace(" ", "").replace(",", ".")
            amount = float(raw)
        except (ValueError, TypeError):
            var_error.set("Ugyldig beløp.")
            return
        if abs(amount) < 0.005:
            var_error.set("Beløp kan ikke være null.")
            return
        if var_side.get() == "Kredit":
            amount = -abs(amount)
        else:
            amount = abs(amount)
        result = {
            "bilag": var_bilag.get().strip(),
            "konto": konto,
            "belop": amount,
            "beskrivelse": var_beskr.get().strip(),
        }
        dlg.destroy()
        callback(result)

    ttk.Button(btn_frame, text="OK", command=_ok).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy).pack(side="right")

    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    dlg.geometry(f"+{x}+{y}")
