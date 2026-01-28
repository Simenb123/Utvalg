"""Motpostanalyse (GUI).

Tkinter-visning for motpostanalyse.

Kjerne-/eksport-logikk ligger i :mod:`motpost_konto_core` (pandas/openpyxl).
"""

import os
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from formatting import fmt_amount
from konto_utils import konto_to_str

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
    _konto_str,
    _fmt_date_ddmmyyyy,
    _fmt_percent_points,
)


class MotpostKontoView(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        df_transactions: pd.DataFrame,
        konto_list: list[str] | set[str] | tuple[str, ...],
        konto_name_map: Optional[dict[str, str]] = None,
    ):
        super().__init__(master)
        self.title("Motpostanalyse")
        self.geometry("1100x700")

        self._df_all = df_transactions
        # Optional mapping {konto -> kontonavn} for bedre info-tekst (best effort)
        self._konto_name_map: dict[str, str] = {
            _konto_str(k): str(v) for k, v in (konto_name_map or {}).items() if str(k).strip()
        }
        self._selected_accounts = {_konto_str(k) for k in konto_list}
        self._data = build_motpost_data(self._df_all, self._selected_accounts)

        self._outliers: set[str] = set()
        self._selected_motkonto: Optional[str] = None

        self._details_limit_var = tk.IntVar(value=200)

        self._build_ui()
        self._render_summary()

    def _format_selected_accounts(self) -> str:
        """Formater valgte kontoer for visning i topp-tekst.

        Hvis vi har konto->navn mapping, viser vi "<konto> <navn>".
        Ellers viser vi kun kontonummer.
        """
        if not getattr(self, "_konto_name_map", None):
            return ", ".join(self._data.selected_accounts)
        parts: list[str] = []
        for k in self._data.selected_accounts:
            name = self._konto_name_map.get(_konto_str(k))
            if name:
                parts.append(f"{k} {name}")
            else:
                parts.append(k)
        return ", ".join(parts)

    # --- UI bygging ---
    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        info = (
            f"Valgte kontoer: {self._format_selected_accounts()}  |  "
            f"Bilag i grunnlag: {self._data.bilag_count}  |  "
            f"Sum valgte kontoer (netto): {fmt_amount(self._data.selected_sum)}  |  "
            f"Kontroll (valgt + mot): {fmt_amount(self._data.control_sum)}"
        )
        self._info_label = ttk.Label(top, text=info)
        self._info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_frame = ttk.Frame(top)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame,
            text="Kombinasjoner",
            command=self._show_combinations,
        ).pack(side=tk.LEFT, padx=(0, 12))

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
            self._tree_summary.column(c, width=120 if c != "Tekst" else 300, anchor=tk.W)

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
        sp = ttk.Spinbox(header, from_=50, to=5000, increment=50, width=7, textvariable=self._details_limit_var, command=self._refresh_details)
        sp.pack(side=tk.LEFT)

        ttk.Button(header, text="Drilldown", command=self._drilldown).pack(side=tk.RIGHT)

        columns2 = ("Bilag", "Dato", "Tekst", "Beløp (valgte kontoer)", "Motbeløp", "Kontoer i bilag")
        self._tree_details = ttk.Treeview(bottom, columns=columns2, show="headings", selectmode="extended")
        for c in columns2:
            self._tree_details.heading(c, text=c)
            self._tree_details.column(c, width=120, anchor=tk.W)

        self._tree_details.column("Tekst", width=350)
        self._tree_details.column("Beløp (valgte kontoer)", anchor=tk.E, width=160)
        self._tree_details.column("Motbeløp", anchor=tk.E, width=120)
        self._tree_details.column("Kontoer i bilag", width=180)

        yscroll2 = ttk.Scrollbar(bottom, orient=tk.VERTICAL, command=self._tree_details.yview)
        self._tree_details.configure(yscrollcommand=yscroll2.set)

        self._tree_details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll2.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree_details.tag_configure("neg", foreground="red")

        # Aktiver multiselect + dobbelklikk/Enter for drilldown på bilag-listen
        configure_bilag_details_tree(self._tree_details, open_bilag_callback=self._open_bilag_drilldown)


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

        df_b = build_bilag_details(self._data, self._selected_motkonto)
        if df_b is None or df_b.empty:
            return

        limit = int(self._details_limit_var.get() or 200)
        df_b = df_b.head(limit)

        for _, row in df_b.iterrows():
            bilag = row.get("Bilag", "")
            dato = _fmt_date_ddmmyyyy(row.get("Dato"))
            tekst = row.get("Tekst", "")
            bel_sel = float(row.get("Beløp (valgte kontoer)", 0.0))
            motb = float(row.get("Motbeløp", 0.0))
            kontoer = row.get("Kontoer i bilag", "")

            tags: list[str] = []
            if bel_sel < 0 or motb < 0:
                tags.append("neg")

            self._tree_details.insert(
                "",
                tk.END,
                values=(bilag, dato, tekst, fmt_amount(bel_sel), fmt_amount(motb), kontoer),
                tags=tuple(tags),
            )

    # --- Events / actions ---
    def _on_select_motkonto(self, _event=None) -> None:
        sel = self._tree_summary.selection()
        if not sel:
            self._selected_motkonto = None
            self._refresh_details()
            return
        # Bruk første valgte som "aktiv" motkonto for bilagsvisning
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

            df_combo = build_motkonto_combinations(
                df_scope,
                self._data.selected_accounts,
                outlier_motkonto=self._outliers,
            )

            df_combo_per = build_motkonto_combinations_per_selected_account(
                df_scope,
                self._data.selected_accounts,
                outlier_motkonto=self._outliers,
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
        default_name = "motpostanalyse.xlsx"
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

            # Aapne filen automatisk etter eksport (plattformsikkert)
            try:
                import os
                import sys
                import subprocess

                if hasattr(os, "startfile"):
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                # Ikke kritisk om dette feiler (f.eks. i testmiljo)
                pass
        except Exception as e:
            messagebox.showerror("Motpostanalyse", f"Kunne ikke eksportere til Excel:\n{e}")

    def _open_bilag_drilldown(self, bilag: str) -> None:
        """Åpner bilagsdrilldown for ett bilag."""
        bilag = _konto_str(bilag)
        try:
            from views_bilag_drill import BilagDrillDialog

            dlg = BilagDrillDialog(self, self._df_all)
            dlg.preset_and_show(bilag)
        except Exception as e:
            messagebox.showerror("Motpostanalyse", f"Kunne ikke åpne drilldown:\n{e}")

    def _drilldown(self) -> None:
        bilag = treeview_first_selected_value(self._tree_details, col_index=0, value_transform=_konto_str)
        if not bilag:
            messagebox.showinfo("Motpostanalyse", "Velg et bilag i listen for å åpne drilldown.")
            return
        self._open_bilag_drilldown(bilag)


def treeview_value_from_iid(tree: Any, iid: Any, *, col_index: int = 0, value_transform: Callable[[Any], str] | None = None) -> Optional[str]:
    """Hent en verdi fra Treeview.item(iid, 'values')[col_index]."""
    if iid is None:
        return None
    try:
        values = tree.item(iid, "values")
    except Exception:
        return None
    if not values or len(values) <= col_index:
        return None
    raw = values[col_index]
    try:
        return value_transform(raw) if value_transform else str(raw)
    except Exception:
        return str(raw)


def treeview_first_selected_value(tree: Any, *, col_index: int = 0, value_transform: Callable[[Any], str] | None = None) -> Optional[str]:
    """Hent verdi fra første markerte rad i Treeview."""
    try:
        sel = list(tree.selection())
    except Exception:
        return None
    if not sel:
        return None
    return treeview_value_from_iid(tree, sel[0], col_index=col_index, value_transform=value_transform)


def _on_tree_double_click_open_value(event: Any, tree: Any, open_value_callback: Callable[[str], None], *, col_index: int = 0) -> str:
    """Dobbelklikk: identifiser raden under mus og åpne drilldown."""
    try:
        iid = tree.identify_row(event.y)
    except Exception:
        iid = None
    if iid:
        try:
            tree.selection_set(iid)
        except Exception:
            pass
        value = treeview_value_from_iid(tree, iid, col_index=col_index, value_transform=_konto_str)
        if value:
            open_value_callback(value)
    return "break"


def _on_tree_enter_open_first_selected(_event: Any, tree: Any, open_value_callback: Callable[[str], None], *, col_index: int = 0) -> str:
    value = treeview_first_selected_value(tree, col_index=col_index, value_transform=_konto_str)
    if value:
        open_value_callback(value)
    return "break"


def configure_bilag_details_tree(tree: Any, *, open_bilag_callback: Callable[[str], None]) -> None:
    """Fellesoppsett for bilag-listen i motpostanalyse:
    - Multiselect (extended)
    - Dobbelklikk åpner drilldown for bilaget
    - Enter åpner drilldown for første markerte bilag

    (Duck typing slik at dette kan testes uten Tk.)
    """
    try:
        tree.configure(selectmode="extended")
    except Exception:
        pass
    # Bind både med og uten 'add' for å støtte dummy-trær i tester
    try:
        tree.bind("<Double-1>", lambda e: _on_tree_double_click_open_value(e, tree, open_bilag_callback, col_index=0), add="+")
        tree.bind("<Return>", lambda e: _on_tree_enter_open_first_selected(e, tree, open_bilag_callback, col_index=0), add="+")
        return
    except Exception:
        pass
    try:
        tree.bind("<Double-1>", lambda e: _on_tree_double_click_open_value(e, tree, open_bilag_callback, col_index=0))
        tree.bind("<Return>", lambda e: _on_tree_enter_open_first_selected(e, tree, open_bilag_callback, col_index=0))
    except Exception:
        pass

def show_motpost_konto(
    master: Any,
    df_transactions: Optional[pd.DataFrame] = None,
    konto_list: Optional[Sequence[str]] = None,
    konto_name_map: Optional[dict[str, str]] = None,
    *,
    # Vanlige alias brukt i andre deler av kodebasen / eldre caller-signaturer
    df_all: Optional[pd.DataFrame] = None,
    selected_accounts: Optional[Sequence[str]] = None,
    selected_kontoer: Optional[Sequence[str]] = None,
    accounts: Optional[Sequence[str]] = None,
    **_: Any,
) -> None:
    """Entry-point brukt fra Analyse-fanen.

    Denne funksjonen er med vilje *bakoverkompatibel* og godtar flere signaturer:

    - show_motpost_konto(master, df, konto_list)
    - show_motpost_konto(master, df, konto_list, konto_name_map)
    - show_motpost_konto(master=..., df_all=df, selected_accounts=[...], konto_name_map={...})

    UI-klassen :class:`MotpostKontoView` forventer et DataFrame med transaksjoner og
    en liste med valgte kontoer. Konto-navn mapping er "best effort".
    """

    df = df_transactions if df_transactions is not None else df_all
    if df is None:
        # Best effort: ikke krasj – ingen data å vise
        return

    sel = konto_list or selected_accounts or selected_kontoer or accounts
    if not sel:
        # Typisk feiltilfelle: kall uten kontoer -> ikke åpne vindu
        return

    konto_norm = [_konto_str(k) for k in sel if str(k).strip()]
    if not konto_norm:
        return

    # Robust opprettelse: støtte både keyword og positional mapping i DummyView/tester
    try:
        MotpostKontoView(master, df, list(konto_norm), konto_name_map=konto_name_map)
        return
    except TypeError:
        pass
    try:
        MotpostKontoView(master, df, list(konto_norm), konto_name_map)
        return
    except TypeError:
        pass

    MotpostKontoView(master, df, list(konto_norm))

# Bakoverkompatibilitet (noen steder kan ha importert underscorenavnet)
_show_motpost_konto = show_motpost_konto