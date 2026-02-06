import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any

import pandas as pd

from formatting import fmt_amount, fmt_date

# Optional: enable sorting if module exists (introduced in later patches)
try:
    from ui_treeview_sort import enable_treeview_sorting  # type: ignore
except Exception:  # pragma: no cover
    enable_treeview_sorting = None  # type: ignore


class BilagDrillDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, df: pd.DataFrame, bilag_col: str = "Bilag"):
        super().__init__(master)
        self.df = df.copy()
        self.bilag_col = bilag_col

        self.title("Bilagsdrill")
        self.geometry("1000x650")

        # Compat aliases expected by wrapper/older code
        self.var_bilag = tk.StringVar()
        self._bilag_var = self.var_bilag

        # --- Top controls ---
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="Bilag:").pack(side=tk.LEFT)
        self.entry = ttk.Entry(top, textvariable=self.var_bilag, width=20)
        self.entry.pack(side=tk.LEFT, padx=(6, 8))
        self.entry.bind("<Return>", lambda e: self._refresh())
        ttk.Button(top, text="Vis", command=self._refresh).pack(side=tk.LEFT)

        # --- Treeview ---
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.tree = ttk.Treeview(tree_frame, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Styling helpers
        self.tree.tag_configure("neg", foreground="red")

        self._setup_columns()

        if enable_treeview_sorting:
            try:
                enable_treeview_sorting(self.tree)
            except Exception:
                pass

    # -----------------
    # Public-ish helpers
    # -----------------
    def show_bilag(self, bilag: Any) -> None:
        """Compatibility API used by some callers."""
        self.var_bilag.set("" if bilag is None else str(bilag))
        self._refresh()

    def _do_show(self) -> None:
        """Compatibility alias."""
        self._refresh()

    def _refresh(self) -> None:
        """Compatibility alias."""
        self._show_bilag()

    # -----------------
    # Internal
    # -----------------
    def _setup_columns(self) -> None:
        cols = list(self.df.columns)
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=self._suggest_width(col), anchor=self._suggest_anchor(col), stretch=True)

    @staticmethod
    def _suggest_width(col: str) -> int:
        c = col.lower()
        if c in ("konto", "bilag"):
            return 80
        if "dato" in c:
            return 110
        if "beløp" in c or "belop" in c or "sum" in c or "motbel" in c:
            return 120
        if "tekst" in c or "beskrivelse" in c:
            return 260
        if "navn" in c:
            return 200
        return 120

    @staticmethod
    def _suggest_anchor(col: str) -> str:
        c = col.lower()
        if "beløp" in c or "belop" in c or "sum" in c or "motbel" in c:
            return tk.E
        return tk.W

    @staticmethod
    def _is_blank(val: Any) -> bool:
        if val is None:
            return True
        try:
            return bool(pd.isna(val))
        except Exception:
            return False

    def _format_cell(self, col: str, val: Any) -> str:
        if self._is_blank(val):
            return ""

        col_l = col.lower()

        # Dates
        if "dato" in col_l:
            try:
                return fmt_date(val)
            except Exception:
                return str(val)

        # Amount-like columns
        if "beløp" in col_l or "belop" in col_l or "sum" in col_l or "motbel" in col_l:
            try:
                return fmt_amount(float(val), decimals=2)
            except Exception:
                return str(val)

        # Integer-ish numbers often arrive as float (e.g. 14420.0)
        if isinstance(val, float) and val.is_integer():
            return str(int(val))

        return str(val)

    def _show_bilag(self) -> None:
        bilag = self.var_bilag.get().strip()
        if not bilag:
            messagebox.showwarning("Mangler bilag", "Skriv inn bilagsnummer.")
            return

        # Filter bilag
        try:
            mask = self.df[self.bilag_col].astype(str) == bilag
        except Exception:
            mask = self.df[self.bilag_col] == bilag

        df_bilag = self.df.loc[mask]

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        if df_bilag.empty:
            messagebox.showinfo("Ingen treff", f"Fant ingen rader for bilag {bilag}.")
            return

        cols = list(self.df.columns)
        # Identify the first amount-like column (for neg highlighting)
        amount_col = None
        for c in cols:
            cl = c.lower()
            if "beløp" in cl or "belop" in cl or "sum" in cl or "motbel" in cl:
                amount_col = c
                break

        for _, row in df_bilag.iterrows():
            values = [self._format_cell(c, row.get(c)) for c in cols]

            tags = ()
            if amount_col is not None:
                try:
                    v = row.get(amount_col)
                    if not self._is_blank(v) and float(v) < 0:
                        tags = ("neg",)
                except Exception:
                    pass

            self.tree.insert("", tk.END, values=values, tags=tags)

        # Focus tree for keyboard navigation
        try:
            first = self.tree.get_children()[0]
            self.tree.focus(first)
            self.tree.selection_set(first)
        except Exception:
            pass
