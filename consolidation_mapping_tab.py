"""consolidation_mapping_tab.py — Analyse-lik mapping-editor for konsolidering.

To-liste UI:
  Venstre: Kontoer (konto, kontonavn, regnr, rl_navn) med multi-select
  Hoyre:   Regnskapslinjer (regnr, navn) med single-select
  Midt:    Tildel / Fjern knapper
  Bunn:    Statuslinje med mapping-prosent

Frittstaaende ttk.Frame — ingen avhengigheter til session eller bus.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd


def _fmt_no(value: float, decimals: int = 0) -> str:
    """Norsk beloepsformat: mellomrom som tusenskille, komma som desimal."""
    if abs(value) < 0.005 and decimals == 0:
        return "0"
    sign = "-" if value < 0 else ""
    if decimals > 0:
        formatted = f"{abs(value):,.{decimals}f}"
    else:
        formatted = f"{round(abs(value)):,}"
    formatted = formatted.replace(",", " ").replace(".", ",")
    return sign + formatted

logger = logging.getLogger(__name__)


class MappingTab(ttk.Frame):  # type: ignore[misc]
    """Two-list mapping editor for konto → regnskapslinje overrides."""

    def __init__(
        self,
        parent,
        *,
        on_overrides_changed: Optional[Callable[[str, dict[str, int]], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._on_overrides_changed = on_overrides_changed

        # Current state
        self._company_id: Optional[str] = None
        self._tb: Optional[pd.DataFrame] = None
        self._mapped_tb: Optional[pd.DataFrame] = None
        self._overrides: dict[str, int] = {}
        self._base_regnr: dict[str, Optional[int]] = {}  # interval-mapping regnr per konto
        self._regnr_to_name: dict[int, str] = {}
        self._rl_rows: list[tuple[int, str]] = []  # (regnr, name) for leaf lines

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=4)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=3)
        self.rowconfigure(0, weight=1)

        # --- Left: Kontoer ---
        left_frm = ttk.Frame(self)
        left_frm.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=4)
        left_frm.rowconfigure(1, weight=1)
        left_frm.columnconfigure(0, weight=1)

        # Filter row
        filter_left = ttk.Frame(left_frm)
        filter_left.grid(row=0, column=0, sticky="ew")
        filter_left.columnconfigure(1, weight=1)

        ttk.Label(filter_left, text="Filter:").grid(row=0, column=0, padx=(0, 4))
        self._filter_left_var = tk.StringVar()
        self._filter_left_var.trace_add("write", lambda *_: self._refresh_left_tree())
        ttk.Entry(filter_left, textvariable=self._filter_left_var).grid(
            row=0, column=1, sticky="ew",
        )

        self._show_unmapped_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filter_left, text="Kun umappede",
            variable=self._show_unmapped_var,
            command=self._refresh_left_tree,
        ).grid(row=0, column=2, padx=(8, 0))

        self._hide_zero_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_left, text="Kun linjer med verdi",
            variable=self._hide_zero_var,
            command=self._refresh_left_tree,
        ).grid(row=0, column=3, padx=(8, 0))

        # Treeview
        acct_cols = ("konto", "kontonavn", "ib", "netto", "ub", "regnr", "rl_navn")
        self._tree_left = ttk.Treeview(
            left_frm, columns=acct_cols, show="headings",
            selectmode="extended",
        )
        _left_headings = {
            "konto": "Konto", "kontonavn": "Kontonavn",
            "ib": "IB", "netto": "Bevegelse", "ub": "UB",
            "regnr": "Regnr", "rl_navn": "Regnskapslinje",
        }
        _left_widths = {
            "konto": 70, "kontonavn": 120, "ib": 80, "netto": 80, "ub": 80,
            "regnr": 45, "rl_navn": 120,
        }
        for c in acct_cols:
            self._tree_left.heading(c, text=_left_headings[c])
            anchor = "w" if c in ("kontonavn", "rl_navn") else "e"
            self._tree_left.column(c, width=_left_widths.get(c, 80), anchor=anchor)

        self._tree_left.tag_configure("unmapped", background="#FCEBD9")
        self._tree_left.tag_configure("override", background="#DDE8F0")

        sb_left = ttk.Scrollbar(left_frm, orient="vertical", command=self._tree_left.yview)
        self._tree_left.configure(yscrollcommand=sb_left.set)
        self._tree_left.grid(row=1, column=0, sticky="nsew")
        sb_left.grid(row=1, column=1, sticky="ns")

        # --- Center: Buttons ---
        btn_frm = ttk.Frame(self)
        btn_frm.grid(row=0, column=1, padx=8, pady=4)

        self._btn_assign = ttk.Button(btn_frm, text="Tildel \u2192", command=self._on_assign)
        self._btn_assign.pack(pady=(40, 4))
        self._btn_remove = ttk.Button(btn_frm, text="\u2190 Fjern", command=self._on_remove)
        self._btn_remove.pack(pady=(0, 4))

        # --- Right: Regnskapslinjer ---
        right_frm = ttk.Frame(self)
        right_frm.grid(row=0, column=2, sticky="nsew", padx=(2, 4), pady=4)
        right_frm.rowconfigure(1, weight=1)
        right_frm.columnconfigure(0, weight=1)

        # Filter row
        filter_right = ttk.Frame(right_frm)
        filter_right.grid(row=0, column=0, sticky="ew")
        filter_right.columnconfigure(1, weight=1)

        ttk.Label(filter_right, text="Filter:").grid(row=0, column=0, padx=(0, 4))
        self._filter_right_var = tk.StringVar()
        self._filter_right_var.trace_add("write", lambda *_: self._refresh_right_tree())
        ttk.Entry(filter_right, textvariable=self._filter_right_var).grid(
            row=0, column=1, sticky="ew",
        )

        # Treeview
        rl_cols = ("regnr", "regnskapslinje")
        self._tree_right = ttk.Treeview(
            right_frm, columns=rl_cols, show="headings",
            selectmode="browse",
        )
        self._tree_right.heading("regnr", text="Nr")
        self._tree_right.heading("regnskapslinje", text="Regnskapslinje")
        self._tree_right.column("regnr", width=50, anchor="e")
        self._tree_right.column("regnskapslinje", width=180, anchor="w")

        sb_right = ttk.Scrollbar(right_frm, orient="vertical", command=self._tree_right.yview)
        self._tree_right.configure(yscrollcommand=sb_right.set)
        self._tree_right.grid(row=1, column=0, sticky="nsew")
        sb_right.grid(row=1, column=1, sticky="ns")

        # --- Bottom: Status ---
        self._status_var = tk.StringVar(value="Velg et selskap for aa redigere mapping.")
        ttk.Label(self, textvariable=self._status_var, foreground="gray").grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(0, 4),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(
        self,
        company_id: str,
        tb: pd.DataFrame,
        mapped_tb: Optional[pd.DataFrame],
        overrides: dict[str, int],
        regnskapslinjer: pd.DataFrame,
        regnr_to_name: dict[int, str],
    ) -> None:
        """Populate both lists for a company."""
        self._company_id = company_id
        self._tb = tb
        self._mapped_tb = mapped_tb
        self._overrides = dict(overrides)  # work with a copy
        self._regnr_to_name = regnr_to_name

        # Build base regnr map (from interval mapping, before overrides)
        self._base_regnr.clear()
        if mapped_tb is not None and "regnr" in mapped_tb.columns and "konto" in mapped_tb.columns:
            for _, row in mapped_tb.iterrows():
                konto = str(row["konto"])
                regnr_raw = row["regnr"]
                try:
                    regnr_val = int(regnr_raw) if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan") else None
                except (ValueError, TypeError):
                    regnr_val = None
                # Base regnr = interval-mapped value (ignoring overrides)
                if konto in overrides:
                    # For overridden kontos, the mapped_tb already reflects the override.
                    # We store the override value, but mark it as overridden in the tree.
                    self._base_regnr[konto] = regnr_val
                else:
                    self._base_regnr[konto] = regnr_val

        # Build leaf rl list
        self._rl_rows = []
        for _, row in regnskapslinjer.iterrows():
            is_sum = bool(row.get("sumpost", False))
            if not is_sum:
                rn = int(row["regnr"])
                name = str(row.get("regnskapslinje", ""))
                self._rl_rows.append((rn, name))

        self._refresh_left_tree()
        self._refresh_right_tree()
        self._update_status()

    def get_overrides(self) -> dict[str, int]:
        """Return current overrides dict."""
        return dict(self._overrides)

    def clear(self) -> None:
        """Clear all data (e.g. when no company selected)."""
        self._company_id = None
        self._tb = None
        self._mapped_tb = None
        self._overrides.clear()
        self._base_regnr.clear()
        self._rl_rows.clear()
        self._tree_left.delete(*self._tree_left.get_children())
        self._tree_right.delete(*self._tree_right.get_children())
        self._status_var.set("Velg et selskap for aa redigere mapping.")

    # ------------------------------------------------------------------
    # Refresh trees
    # ------------------------------------------------------------------

    def _refresh_left_tree(self) -> None:
        tree = self._tree_left
        tree.delete(*tree.get_children())

        if self._tb is None:
            return

        filter_text = self._filter_left_var.get().strip().lower()
        show_unmapped_only = self._show_unmapped_var.get()
        hide_zero = self._hide_zero_var.get()

        for _, row in self._tb.iterrows():
            konto = str(row.get("konto", ""))
            kontonavn = str(row.get("kontonavn", ""))

            # Beloep
            try:
                ib = float(row.get("ib", 0) or 0)
                ub = float(row.get("ub", 0) or 0)
                netto = float(row.get("netto", 0) or 0)
            except (ValueError, TypeError):
                ib = ub = netto = 0.0

            # Filter: hide zero-lines
            if hide_zero and abs(ib) < 0.005 and abs(ub) < 0.005 and abs(netto) < 0.005:
                continue

            # Determine effective regnr: override > interval-mapped > None
            if konto in self._overrides:
                regnr = self._overrides[konto]
            elif konto in self._base_regnr and self._base_regnr[konto] is not None:
                regnr = self._base_regnr[konto]
            else:
                regnr = None

            # Filter: unmapped only
            if show_unmapped_only and regnr is not None:
                continue

            # Filter: text search
            if filter_text:
                haystack = f"{konto} {kontonavn}".lower()
                if filter_text not in haystack:
                    continue

            regnr_display = str(regnr) if regnr is not None else ""
            rl_navn = self._regnr_to_name.get(regnr, "") if regnr is not None else ""

            # Tag: unmapped or override
            if regnr is None:
                tag = ("unmapped",)
            elif konto in self._overrides:
                tag = ("override",)
            else:
                tag = ()

            tree.insert("", "end", iid=konto, values=(
                konto, kontonavn,
                _fmt_no(ib, 2), _fmt_no(netto, 2), _fmt_no(ub, 2),
                regnr_display, rl_navn,
            ), tags=tag)

    def _refresh_right_tree(self) -> None:
        tree = self._tree_right
        tree.delete(*tree.get_children())

        filter_text = self._filter_right_var.get().strip().lower()

        for regnr, name in self._rl_rows:
            if filter_text:
                haystack = f"{regnr} {name}".lower()
                if filter_text not in haystack:
                    continue
            tree.insert("", "end", iid=str(regnr), values=(regnr, name))

    def _update_status(self) -> None:
        if self._tb is None:
            self._status_var.set("Velg et selskap for aa redigere mapping.")
            return

        total = len(self._tb)
        mapped = 0
        for _, row in self._tb.iterrows():
            konto = str(row.get("konto", ""))
            if konto in self._overrides:
                mapped += 1
            elif konto in self._base_regnr and self._base_regnr[konto] is not None:
                mapped += 1

        pct = int(mapped * 100 / total) if total > 0 else 0
        self._status_var.set(f"{mapped}/{total} kontoer mappet ({pct}%)")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_assign(self) -> None:
        """Assign selected accounts to selected regnskapslinje."""
        if self._company_id is None:
            return

        # Get selected regnskapslinje (right)
        sel_right = self._tree_right.selection()
        if not sel_right:
            return
        try:
            target_regnr = int(sel_right[0])
        except (ValueError, TypeError):
            return

        # Get selected accounts (left, multi-select)
        sel_left = self._tree_left.selection()
        if not sel_left:
            return

        # Apply overrides
        for konto in sel_left:
            self._overrides[str(konto)] = target_regnr

        self._refresh_left_tree()
        self._update_status()

        # Re-select the accounts that were just assigned (if still visible)
        for konto in sel_left:
            if self._tree_left.exists(str(konto)):
                self._tree_left.selection_add(str(konto))

        # Notify parent
        if self._on_overrides_changed:
            self._on_overrides_changed(self._company_id, self.get_overrides())

    def _on_remove(self) -> None:
        """Remove override for selected accounts (revert to interval mapping)."""
        if self._company_id is None:
            return

        sel_left = self._tree_left.selection()
        if not sel_left:
            return

        for konto in sel_left:
            self._overrides.pop(str(konto), None)

        self._refresh_left_tree()
        self._update_status()

        # Re-select
        for konto in sel_left:
            if self._tree_left.exists(str(konto)):
                self._tree_left.selection_add(str(konto))

        # Notify parent
        if self._on_overrides_changed:
            self._on_overrides_changed(self._company_id, self.get_overrides())
