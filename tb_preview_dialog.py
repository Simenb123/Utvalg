"""tb_preview_dialog.py — Forhåndsvisning og kolonnekorrigering for saldobalanse.

Standalone Toplevel-dialog som:
  1. Leser rå TB fra fil (read_raw_trial_balance)
  2. Gjetter kolonner via alias-matching + year-detection
  3. Viser brukeren detekterte kolonner med dropdown-korrigering
  4. Viser preview av de første radene
  5. Ved bekreftelse: leser full fil og returnerer normalisert DataFrame

Ingen avhengigheter til session, bus, DatasetPane eller HB-pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

from trial_balance_reader import (
    TrialBalanceColumns,
    infer_columns_with_year_detection,
    read_raw_trial_balance,
    read_trial_balance,
    _standardize,
    _to_amount_series,
)

logger = logging.getLogger(__name__)

# Labels shown in the UI for each canonical field
_FIELD_LABELS: Dict[str, str] = {
    "konto": "Konto",
    "kontonavn": "Kontonavn",
    "ib": "IB (Inngående balanse)",
    "ub": "UB (Utgående balanse)",
    "netto": "Netto / Endring",
    "debet": "Debet",
    "kredit": "Kredit",
}

# Which fields are required vs optional
_REQUIRED_FIELDS = {"konto"}
_OPTIONAL_FIELDS = {"kontonavn", "ib", "ub", "netto", "debet", "kredit"}

_NONE_CHOICE = "— Ikke valgt —"


class TBPreviewDialog(tk.Toplevel):
    """Modal dialog for previewing and correcting TB column mapping."""

    def __init__(
        self,
        parent: tk.Misc,
        file_path: str | Path,
        *,
        initial_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.title("Forhåndsvisning — Saldobalanse")
        self.transient(parent)
        self.grab_set()

        self._file_path = Path(file_path)
        self._result: Optional[tuple[pd.DataFrame, str]] = None  # (df, company_name)
        self._combos: Dict[str, ttk.Combobox] = {}

        # Read raw preview
        try:
            self._raw_df = read_raw_trial_balance(file_path, max_rows=50)
        except Exception as exc:
            messagebox.showerror(
                "Lesefeil",
                f"Kunne ikke lese filen:\n{exc}",
                parent=self,
            )
            self.destroy()
            return

        if self._raw_df.empty:
            messagebox.showinfo(
                "Tom fil",
                "Filen inneholder ingen data.",
                parent=self,
            )
            self.destroy()
            return

        self._columns = list(self._raw_df.columns)

        # Auto-detect columns
        try:
            self._detected, self._year_map = infer_columns_with_year_detection(
                self._raw_df,
            )
        except ValueError:
            # Detection failed — start with all blanks
            self._detected = TrialBalanceColumns(
                konto=None,
                kontonavn=None,
                ib=None,
                ub=None,
                netto=None,
                debet=None,
                kredit=None,
            )
            self._year_map = {}

        self._build_ui(initial_name)
        self._update_preview()

        # Center on parent
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, initial_name: str) -> None:
        self.minsize(700, 500)

        # --- Company name ---
        name_frm = ttk.Frame(self)
        name_frm.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(name_frm, text="Selskapsnavn:").pack(side="left")
        self._name_var = tk.StringVar(value=initial_name or self._file_path.stem)
        name_entry = ttk.Entry(name_frm, textvariable=self._name_var, width=40)
        name_entry.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # --- File info ---
        info_frm = ttk.Frame(self)
        info_frm.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Label(
            info_frm,
            text=f"Fil: {self._file_path.name}  |  Kolonner: {len(self._columns)}  |  "
            f"Preview: {len(self._raw_df)} rader",
            foreground="gray",
        ).pack(anchor="w")

        if self._year_map:
            yr_text = ", ".join(
                f"{orig} → {canon.upper()}" for orig, canon in self._year_map.items()
            )
            ttk.Label(
                info_frm,
                text=f"Årstall-kolonner detektert: {yr_text}",
                foreground="#2266AA",
            ).pack(anchor="w")

        # --- Column mapping ---
        map_frm = ttk.LabelFrame(self, text="Kolonnemapping")
        map_frm.pack(fill="x", padx=12, pady=4)

        choices = [_NONE_CHOICE] + [str(c) for c in self._columns]

        for row_idx, (key, label) in enumerate(_FIELD_LABELS.items()):
            required = key in _REQUIRED_FIELDS
            lbl_text = f"{label} *" if required else label
            ttk.Label(map_frm, text=lbl_text).grid(
                row=row_idx, column=0, sticky="w", padx=(8, 4), pady=2,
            )

            combo = ttk.Combobox(
                map_frm, values=choices, state="readonly", width=30,
            )
            combo.grid(row=row_idx, column=1, sticky="w", padx=(0, 8), pady=2)

            # Set initial value from detection
            detected_val = getattr(self._detected, key, None)
            if detected_val and detected_val in self._columns:
                combo.set(str(detected_val))
            else:
                combo.set(_NONE_CHOICE)

            combo.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())
            self._combos[key] = combo

        # --- Preview table ---
        preview_frm = ttk.LabelFrame(self, text="Forhåndsvisning (normalisert)")
        preview_frm.pack(fill="both", expand=True, padx=12, pady=4)

        preview_cols = ("konto", "kontonavn", "ib", "ub", "netto")
        self._preview_tree = ttk.Treeview(
            preview_frm, columns=preview_cols, show="headings", height=10,
        )
        for c in preview_cols:
            self._preview_tree.heading(c, text=c.capitalize())
            w = 160 if c == "kontonavn" else 100
            anchor = "w" if c == "kontonavn" else "e"
            self._preview_tree.column(c, width=w, anchor=anchor)

        sb = ttk.Scrollbar(
            preview_frm, orient="vertical", command=self._preview_tree.yview,
        )
        self._preview_tree.configure(yscrollcommand=sb.set)
        self._preview_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # --- Status label ---
        self._status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._status_var, foreground="gray").pack(
            fill="x", padx=12, pady=(0, 4),
        )

        # --- Buttons ---
        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_frm, text="Avbryt", command=self._on_cancel).pack(
            side="right", padx=(4, 0),
        )
        ttk.Button(btn_frm, text="Bekreft og importer", command=self._on_confirm).pack(
            side="right",
        )

    # ------------------------------------------------------------------
    # Preview update
    # ------------------------------------------------------------------

    def _get_user_mapping(self) -> Optional[TrialBalanceColumns]:
        """Build TrialBalanceColumns from current combo selections."""
        vals = {}
        for key, combo in self._combos.items():
            v = combo.get()
            vals[key] = v if v != _NONE_CHOICE else None

        if not vals.get("konto"):
            return None

        return TrialBalanceColumns(
            konto=vals["konto"],
            kontonavn=vals.get("kontonavn"),
            ib=vals.get("ib"),
            ub=vals.get("ub"),
            netto=vals.get("netto"),
            debet=vals.get("debet"),
            kredit=vals.get("kredit"),
        )

    def _update_preview(self) -> None:
        """Refresh the preview treeview based on current mapping."""
        tree = self._preview_tree
        tree.delete(*tree.get_children())

        cols = self._get_user_mapping()
        if cols is None:
            self._status_var.set("Velg minst Konto-kolonnen.")
            return

        try:
            preview_df = _standardize(self._raw_df, cols)
            for _, row in preview_df.head(20).iterrows():
                tree.insert("", "end", values=(
                    row.get("konto", ""),
                    row.get("kontonavn", ""),
                    f"{float(row.get('ib', 0)):,.2f}",
                    f"{float(row.get('ub', 0)):,.2f}",
                    f"{float(row.get('netto', 0)):,.2f}",
                ))
            self._status_var.set(f"{len(preview_df)} rader i preview.")
        except Exception as exc:
            self._status_var.set(f"Preview-feil: {exc}")

    # ------------------------------------------------------------------
    # Confirm / Cancel
    # ------------------------------------------------------------------

    def _on_confirm(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning(
                "Selskapsnavn mangler",
                "Skriv inn et selskapsnavn.",
                parent=self,
            )
            return

        cols = self._get_user_mapping()
        if cols is None or not cols.konto:
            messagebox.showwarning(
                "Konto mangler",
                "Du må velge hvilken kolonne som er Konto.",
                parent=self,
            )
            return

        # Check that we have at least UB, netto, or debet+kredit
        has_value_col = (
            cols.ub is not None
            or cols.netto is not None
            or (cols.debet is not None and cols.kredit is not None)
        )
        if not has_value_col:
            messagebox.showwarning(
                "Verdikolonne mangler",
                "Velg minst UB, Netto, eller Debet+Kredit.\n\n"
                "IB alene er ikke tilstrekkelig for konsolidering.",
                parent=self,
            )
            return

        # Read full file and standardize with user mapping.
        # Viktig: bruk samme header-robuste lesing som readeren, ellers blir
        # Maestro-lignende filer lest med tittelrad som header ved import.
        try:
            if self._file_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
                from trial_balance_reader import (
                    _guess_sheet_name,
                    _clean_frame,
                    _read_sheet_with_detected_header,
                )
                sn = _guess_sheet_name(self._file_path)
                full_df = _read_sheet_with_detected_header(self._file_path, sn)
                full_df = _clean_frame(full_df)
            else:
                from trial_balance_reader import _clean_frame
                full_df = pd.read_csv(
                    self._file_path, sep=None, engine="python",
                )
                full_df = _clean_frame(full_df)

            result_df = _standardize(full_df, cols)
        except Exception as exc:
            messagebox.showerror(
                "Importfeil",
                f"Kunne ikke lese full fil:\n{exc}",
                parent=self,
            )
            return

        if result_df.empty:
            messagebox.showwarning(
                "Ingen data",
                "Normalisering ga ingen rader. Sjekk kolonnemappingen.",
                parent=self,
            )
            return

        self._result = (result_df, name)
        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.grab_release()
        self.destroy()

    @property
    def result(self) -> Optional[tuple[pd.DataFrame, str]]:
        """Returns (normalized_df, company_name) or None if cancelled."""
        return self._result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def open_tb_preview(
    parent: tk.Misc,
    file_path: str | Path,
    *,
    initial_name: str = "",
) -> Optional[tuple[pd.DataFrame, str]]:
    """Open the TB preview dialog and return (df, name) or None.

    This is a blocking call — it waits for the dialog to close.
    """
    if tk is None:
        return None

    dlg = TBPreviewDialog(parent, file_path, initial_name=initial_name)
    dlg.wait_window()
    return dlg.result
