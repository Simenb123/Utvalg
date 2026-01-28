"""Motpostanalyse (GUI).

Tkinter-visning for motpostanalyse.

Kjerne-/eksport-logikk ligger i :mod:`motpost_konto_core` (pandas/openpyxl).

NB: `page_analyse_actions.open_motpost()` prøver flere signaturer for
bakoverkompatibilitet. Derfor er `show_motpost_konto()` implementert tolerant.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable, Optional

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from formatting import fmt_amount

from motpost_combinations_popup import show_motkonto_combinations_popup
from motpost_combinations import (
    build_motkonto_combinations,
    build_motkonto_combinations_per_selected_account,
)
from motpost_konto_core import (
    MotpostData,
    build_bilag_details,
    build_motpost_data,
    build_motpost_excel_workbook,
    _fmt_date_ddmmyyyy,
    _fmt_percent_points,
    _konto_str,
)


class MotpostKontoView(tk.Toplevel):
    def __init__(self, master: tk.Misc, df_transactions: pd.DataFrame, konto_list: Iterable[str]):
        super().__init__(master)
        self.title("Motpostanalyse")
        self.geometry("1100x700")

        self._df_all = df_transactions
        self._selected_accounts = {_konto_str(k) for k in (konto_list or [])}
        self._data: MotpostData = build_motpost_data(self._df_all, self._selected_accounts)

        self._outliers: set[str] = set()
        self._selected_motkonto: Optional[str] = None

        self._details_limit_var = tk.IntVar(value=200)

        self._build_ui()
        self._render_summary()

    # --- UI ---
    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        info = (
            f"Valgte kontoer: {', '.join(self._data.selected_accounts)}  |  "
            f"Bilag i grunnlag: {self._data.bilag_count}  |  "
            f"Sum valgte kontoer (netto): {fmt_amount(self._data.selected_sum)}  |  "
            f"Kontroll (valgt + mot): {fmt_amount(self._data.control_sum)}"
        )
        self._info_label = ttk.Label(top, text=info)
        self._info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_frame = ttk.Frame(top)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Kombinasjoner", command=self._show_combinations).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Button(btn_frame, text="Merk outlier", command=self._mark_outlier).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Nullstill outliers", command=self._clear_outliers).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Eksporter Excel", command=self._export_excel).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Lukk", command=self.destroy).pack(side=tk.LEFT)

        # Mid: motkonto pivot
        mid = ttk.Frame(self)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10)

        ttk.Label(mid, text="Motkonto (pivot)").pack(anchor=tk.W)

        columns = ("Motkonto", "Kontonavn", "Sum", "% andel", "Antall bilag", "Outlier")
        self._tree_summary = ttk.Treeview(mid, columns=columns, show="headings", selectmode="extended")
        for c in columns:
            self._tree_summary.heading(c, text=c)
            self._tree_summary.column(c, width=120, anchor=tk.W)

        self._tree_summary.column("Sum", anchor=tk.E, width=140)
        self._tree_summary.column("% andel", anchor=tk.E, width=90)
        self._tree_summary.column("Antall bilag", anchor=tk.E, width=90)
        self._tree_summary.column("Outlier", anchor=tk.W, width=70)

        yscroll = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self._tree_summary.yview)
        self._tree_summary.configure(yscrollcommand=yscroll.set)

        self._tree_summary.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree_summary.tag_configure("neg", foreground="red")
        self._tree_summary.tag_configure("outlier", background="#FFF2CC")
        self._tree_summary.bind("<<TreeviewSelect>>", self._on_select_motkonto)

        # Bottom: bilag-liste for valgt motkonto
        bottom = ttk.Frame(self)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8, 10))

        header = ttk.Frame(bottom)
        header.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(header, text="Bilag for valgt motkonto").pack(side=tk.LEFT)
        ttk.Label(header, text="Vis:").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Spinbox(
            header,
            from_=50,
            to=5000,
            increment=50,
            width=7,
            textvariable=self._details_limit_var,
            command=self._refresh_details,
        ).pack(side=tk.LEFT)

        ttk.Button(header, text="Drilldown", command=self._drilldown).pack(side=tk.RIGHT)

        detail_cols = ("Bilag", "Dato", "Tekst", "Sum valgt", "Sum mot", "Diff")
        self._tree_details = ttk.Treeview(bottom, columns=detail_cols, show="headings", selectmode="browse")
        for c in detail_cols:
            self._tree_details.heading(c, text=c)
            anchor = tk.E if c in {"Sum valgt", "Sum mot", "Diff"} else tk.W
            self._tree_details.column(c, width=130 if c != "Tekst" else 420, anchor=anchor)

        yscroll2 = ttk.Scrollbar(bottom, orient=tk.VERTICAL, command=self._tree_details.yview)
        self._tree_details.configure(yscrollcommand=yscroll2.set)

        self._tree_details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll2.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree_details.tag_configure("neg", foreground="red")

    # --- Rendering ---
    def _render_summary(self) -> None:
        self._tree_summary.delete(*self._tree_summary.get_children())

        df = self._data.df_motkonto
        if df is None or df.empty:
            return

        for _, row in df.iterrows():
            motkonto = _konto_str(row.get("Motkonto"))
            kontonavn = row.get("Kontonavn", "")
            s = float(row.get("Sum", 0.0))
            share = float(row.get("% andel", 0.0))
            cnt = int(row.get("Antall bilag", 0))
            out = "Ja" if motkonto in self._outliers else ""

            tags: list[str] = []
            if s < 0:
                tags.append("neg")
            if motkonto in self._outliers:
                tags.append("outlier")

            self._tree_summary.insert(
                "",
                tk.END,
                values=(motkonto, kontonavn, fmt_amount(s), _fmt_percent_points(share), cnt, out),
                tags=tuple(tags),
            )

    def _refresh_details(self) -> None:
        self._tree_details.delete(*self._tree_details.get_children())

        if not self._selected_motkonto:
            return

        # build_bilag_details har signatur (data, motkonto). Bruk posisjonelle
        # argumenter for å unngå "unexpected keyword" ved refaktor.
        df_b = build_bilag_details(self._data, self._selected_motkonto)
        if df_b is None or df_b.empty:
            return

        limit = int(self._details_limit_var.get() or 200)
        df_b = df_b.head(limit)

        for _, row in df_b.iterrows():
            bilag = row.get("Bilag", "")
            dato = _fmt_date_ddmmyyyy(row.get("Dato"))
            tekst = row.get("Tekst", "")
            sum_valgt = float(row.get("Beløp (valgte kontoer)", 0.0))
            sum_mot = float(row.get("Motbeløp", 0.0))
            diff = sum_valgt + sum_mot

            tags: list[str] = []
            if sum_valgt < 0 or sum_mot < 0 or diff < 0:
                tags.append("neg")

            self._tree_details.insert(
                "",
                tk.END,
                values=(bilag, dato, tekst, fmt_amount(sum_valgt), fmt_amount(sum_mot), fmt_amount(diff)),
                tags=tuple(tags),
            )

    # --- Events / actions ---
    def _on_select_motkonto(self, _event=None) -> None:
        sel = self._tree_summary.selection()
        if not sel:
            self._selected_motkonto = None
            self._refresh_details()
            return
        item = sel[0]
        motkonto = self._tree_summary.item(item, "values")[0]
        self._selected_motkonto = _konto_str(motkonto)
        self._refresh_details()

    def _mark_outlier(self) -> None:
        sel = self._tree_summary.selection()
        if not sel:
            messagebox.showinfo("Motpostanalyse", "Velg en eller flere motkontoer for å markere som outlier.")
            return
        for item in sel:
            motkonto = self._tree_summary.item(item, "values")[0]
            self._outliers.add(_konto_str(motkonto))
        self._render_summary()

    def _clear_outliers(self) -> None:
        self._outliers.clear()
        self._render_summary()

    def _show_combinations(self) -> None:
        """Vis en enkel oversikt over motkonto-kombinasjoner (popup)."""

        try:
            df_scope = self._data.df_scope
            if df_scope is None or df_scope.empty:
                messagebox.showinfo("Kombinasjoner", "Ingen data i grunnlaget.")
                return

            selected_set = {str(k) for k in self._data.selected_accounts if str(k).strip()}

            # build_motkonto_combinations forventer (df_scope, selected_accounts, ...)
            df_combo = build_motkonto_combinations(df_scope, selected_set, outlier_motkonto=self._outliers)
            df_combo_per = build_motkonto_combinations_per_selected_account(
                df_scope, selected_set, outlier_motkonto=self._outliers
            )

            bilag_total = int(df_scope["Bilag"].astype(str).nunique()) if "Bilag" in df_scope.columns else 0
            summary = (
                f"Antall kombinasjoner: {len(df_combo)} | "
                f"Bilag i grunnlag: {bilag_total} | "
                f"Rader per konto: {len(df_combo_per)}"
            )

            show_motkonto_combinations_popup(
                self,
                df_combos=df_combo,
                df_combo_per_selected=df_combo_per,
                title="Motkonto-kombinasjoner",
                summary=summary,
            )
        except Exception as e:
            messagebox.showerror("Kombinasjoner", f"Kunne ikke vise kombinasjoner:\n{e}")

    def _export_excel(self) -> None:
        default_name = f"motpostanalyse_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Lagre Excel",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            wb = build_motpost_excel_workbook(
                self._data,
                outlier_motkonto=self._outliers,
                selected_motkonto=self._selected_motkonto,
            )
            wb.save(path)
            messagebox.showinfo("Motpostanalyse", f"Eksportert til Excel:\n{path}")

            # Åpne filen automatisk etter eksport (best-effort)
            try:
                import sys
                import subprocess

                if hasattr(os, "startfile"):
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Motpostanalyse", f"Kunne ikke eksportere til Excel:\n{e}")

    def _drilldown(self) -> None:
        sel = self._tree_details.selection()
        if not sel:
            messagebox.showinfo("Motpostanalyse", "Velg et bilag i listen for å åpne drilldown.")
            return
        bilag = self._tree_details.item(sel[0], "values")[0]
        bilag = _konto_str(bilag)
        try:
            from views_bilag_drill import BilagDrillDialog

            dlg = BilagDrillDialog(self, self._df_all)
            dlg.preset_and_show(bilag)
        except Exception as e:
            messagebox.showerror("Motpostanalyse", f"Kunne ikke åpne drilldown:\n{e}")


def show_motpost_konto(
    master: tk.Misc,
    df_transactions: Optional[pd.DataFrame] = None,
    konto_list: Optional[Iterable[str]] = None,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Entry-point brukt fra Analyse-fanen (tolerant signatur).

    Kallere kan sende:
      - (master, df, accounts)
      - (master, df_all=df, selected_accounts=accounts, konto_name_map=...)
      - (master, df, accounts, konto_name_map)  # eldre fallback
    """

    df = df_transactions if isinstance(df_transactions, pd.DataFrame) else None
    if df is None:
        for k in ("df_all", "df_base", "df_transactions"):
            v = kwargs.get(k)
            if isinstance(v, pd.DataFrame):
                df = v
                break

    accounts_obj: Any = konto_list
    if accounts_obj is None:
        for k in ("konto_list", "selected_accounts", "accounts"):
            v = kwargs.get(k)
            if v is not None:
                accounts_obj = v
                break

    if accounts_obj is None and args:
        cand = args[0]
        if not isinstance(cand, dict):
            accounts_obj = cand

    if isinstance(accounts_obj, dict):
        accounts_obj = None

    accounts: list[str] = []
    if accounts_obj is not None:
        if isinstance(accounts_obj, (str, int, float)):
            accounts = [_konto_str(accounts_obj)]
        else:
            try:
                for a in accounts_obj:
                    s = _konto_str(a).strip()
                    if s and s not in accounts:
                        accounts.append(s)
            except TypeError:
                s = _konto_str(accounts_obj).strip()
                if s:
                    accounts = [s]

    if df is None or df.empty:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            try:
                messagebox.showerror("Motpostanalyse", "Kunne ikke åpne motpostanalyse: mangler datagrunnlag.")
            except Exception:
                pass
        return

    if not accounts:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            try:
                messagebox.showerror("Motpostanalyse", "Kunne ikke åpne motpostanalyse: ingen kontoer valgt.")
            except Exception:
                pass
        return

    MotpostKontoView(master, df, accounts)


# Bakoverkompatibilitet (noen steder kan ha importert underscorenavnet)
_show_motpost_konto = show_motpost_konto
