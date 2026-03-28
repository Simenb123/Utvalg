"""tb_preview_dialog.py — Forhåndsvisning og kolonnebekreftelse for saldobalanse.

Viser:
  - Gjenkjente kolonner med mulighet for manuell korreksjon
  - Preview av de første N radene
  - Bekreft / Avbryt
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

from trial_balance_reader import (
    TrialBalanceColumns,
    infer_trial_balance_columns,
    read_raw_trial_balance,
    read_trial_balance,
    _clean_frame,
)

logger = logging.getLogger(__name__)

# Felt som brukeren kan mappe → intern nøkkel
_FIELD_LABELS = {
    "konto": "Konto",
    "kontonavn": "Kontonavn",
    "ib": "IB (inngående)",
    "ub": "UB (utgående)",
    "netto": "Netto / Endring",
    "debet": "Debet",
    "kredit": "Kredit",
}


class TBPreviewDialog(tk.Toplevel):  # type: ignore[misc]
    """Dialog for forhåndsvisning og kolonnebekreftelse av saldobalanse."""

    def __init__(
        self,
        parent: tk.Widget,
        file_path: str | Path,
        *,
        sheet_name: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Forhåndsvisning — Saldobalanse")
        self.geometry("800x520")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._file_path = Path(file_path)
        self._sheet_name = sheet_name
        self._raw_df: Optional[pd.DataFrame] = None
        self._inferred: Optional[TrialBalanceColumns] = None
        self._combos: dict[str, ttk.Combobox] = {}

        # Result: normalized DataFrame, or None if cancelled
        self.result: Optional[pd.DataFrame] = None
        self.result_columns: Optional[TrialBalanceColumns] = None

        self._build_ui()
        self._load_preview()

    def _build_ui(self) -> None:
        # --- Top: file info ---
        info = ttk.Frame(self)
        info.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(info, text=f"Fil: {self._file_path.name}", font=("", 10, "bold")).pack(
            anchor="w",
        )

        # --- Column mapping ---
        map_frame = ttk.LabelFrame(self, text="Kolonnegjenkjenning")
        map_frame.pack(fill="x", padx=10, pady=4)

        self._map_inner = ttk.Frame(map_frame)
        self._map_inner.pack(fill="x", padx=8, pady=6)

        # --- Status label ---
        self._status_var = tk.StringVar(value="Leser fil...")
        ttk.Label(self, textvariable=self._status_var, foreground="gray").pack(
            anchor="w", padx=10, pady=(0, 4),
        )

        # --- Preview table ---
        prev_frame = ttk.LabelFrame(self, text="Forhåndsvisning (første rader)")
        prev_frame.pack(fill="both", expand=True, padx=10, pady=4)

        self._tree = ttk.Treeview(prev_frame, show="headings", selectmode="none")
        self._tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(prev_frame, orient="horizontal", command=self._tree.xview)
        sb.pack(fill="x", side="bottom")
        self._tree.configure(xscrollcommand=sb.set)

        # --- Buttons ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(btn_frame, text="Bekreft og last inn", command=self._on_confirm).pack(
            side="right", padx=(4, 0),
        )
        ttk.Button(btn_frame, text="Avbryt", command=self.destroy).pack(side="right")

    def _load_preview(self) -> None:
        try:
            self._raw_df = read_raw_trial_balance(
                self._file_path, sheet_name=self._sheet_name, max_rows=20,
            )
        except Exception as exc:
            self._status_var.set(f"Feil ved lesing: {exc}")
            return

        # Infer columns
        try:
            self._inferred = infer_trial_balance_columns(self._raw_df)
            self._status_var.set(
                f"Gjenkjent {self._raw_df.shape[1]} kolonner, {self._raw_df.shape[0]} rader vist."
            )
        except ValueError as exc:
            self._inferred = None
            self._status_var.set(f"Kolonnegjenkjenning delvis: {exc}")

        self._populate_mapping()
        self._populate_preview()

    def _populate_mapping(self) -> None:
        if self._raw_df is None:
            return

        all_cols = ["(ikke valgt)"] + list(self._raw_df.columns)

        for widget in self._map_inner.winfo_children():
            widget.destroy()
        self._combos.clear()

        row = 0
        for key, label in _FIELD_LABELS.items():
            ttk.Label(self._map_inner, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=2,
            )
            cmb = ttk.Combobox(
                self._map_inner, values=all_cols, state="readonly", width=30,
            )

            # Set detected value
            detected = getattr(self._inferred, key, None) if self._inferred else None
            if detected and detected in self._raw_df.columns:
                cmb.set(detected)
            else:
                cmb.set("(ikke valgt)")

            cmb.grid(row=row, column=1, sticky="w", pady=2)
            self._combos[key] = cmb
            row += 1

    def _populate_preview(self) -> None:
        if self._raw_df is None:
            return

        # Clear tree
        self._tree.delete(*self._tree.get_children())

        cols = list(self._raw_df.columns)
        self._tree["columns"] = cols
        for c in cols:
            self._tree.heading(c, text=str(c))
            self._tree.column(c, width=100, minwidth=60)

        for _, row in self._raw_df.head(10).iterrows():
            vals = [str(v) if pd.notna(v) else "" for v in row]
            self._tree.insert("", "end", values=vals)

    def _get_user_mapping(self) -> TrialBalanceColumns:
        """Build TrialBalanceColumns from user's combo selections."""
        def _get(key: str) -> Optional[str]:
            val = self._combos[key].get()
            if val == "(ikke valgt)" or not val:
                return None
            return val

        konto = _get("konto")
        if not konto:
            raise ValueError("Konto-kolonnen må velges.")

        return TrialBalanceColumns(
            konto=konto,
            kontonavn=_get("kontonavn"),
            ib=_get("ib"),
            ub=_get("ub"),
            netto=_get("netto"),
            debet=_get("debet"),
            kredit=_get("kredit"),
        )

    def _on_confirm(self) -> None:
        try:
            cols = self._get_user_mapping()
        except ValueError as exc:
            self._status_var.set(str(exc))
            return

        # Validate that at least UB or netto (or debet+kredit) is selected
        if cols.ub is None and cols.netto is None:
            if cols.debet is None or cols.kredit is None:
                self._status_var.set("Velg minst UB eller Netto (eller Debet+Kredit).")
                return

        # Read full file and standardize with user's mapping
        try:
            from trial_balance_reader import _standardize
            full_df = read_raw_trial_balance(
                self._file_path, sheet_name=self._sheet_name, max_rows=None,
            )
            self.result = _standardize(full_df, cols)
            self.result_columns = cols
        except Exception as exc:
            self._status_var.set(f"Feil: {exc}")
            return

        self.destroy()


def open_tb_preview(
    parent: tk.Widget,
    file_path: str | Path,
    *,
    sheet_name: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Convenience: åpne preview-dialog og returner normalisert DataFrame (eller None)."""
    dlg = TBPreviewDialog(parent, file_path, sheet_name=sheet_name)
    parent.wait_window(dlg)
    return dlg.result
