"""tilleggsposteringer.py

Tilleggsposteringer (supplementary journal entries) per klient/år.

Lar brukeren legge inn årsoppgjørsposteringer som justerer
saldobalanse-tall og flyter gjennom pivot og SB-visning automatisk.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd


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
        from tkinter import ttk
    except Exception:
        return

    import regnskap_client_overrides
    import formatting

    entries = regnskap_client_overrides.load_supplementary_entries(client, year)

    dlg = tk.Toplevel(parent)
    dlg.title(f"Tilleggsposteringer \u2014 {client} ({year})")
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
    btn_frame = ttk.Frame(dlg)
    btn_frame.grid(row=row, column=0, columnspan=2, sticky="e", padx=12, pady=(8, 12))

    def _ok() -> None:
        try:
            raw = var_belop.get().strip().replace(" ", "").replace(",", ".")
            amount = float(raw)
        except (ValueError, TypeError):
            return
        if var_side.get() == "Kredit":
            amount = -abs(amount)
        else:
            amount = abs(amount)
        result = {
            "bilag": var_bilag.get().strip(),
            "konto": var_konto.get().strip(),
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
