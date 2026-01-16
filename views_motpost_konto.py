"""views_motpost_konto

En enkel (MVP) motpostanalyse for markerte kontoer i Analyse-fanen.

Mål:
- Bruker markerer én eller flere kontoer i pivot-tabellen (Analyse).
- Vi finner alle bilag hvor de valgte kontoene inngår.
- Vi viser hvilke *andre* kontoer (motkontoer) som forekommer i disse bilagene,
  akkumulert (pivot) pr. motkonto.
- Bruker kan klikke på en motkonto for å se bilagene bak.
- Drilldown: Åpne bilagsdrill for valgt bilag.

Bevisst avgrenset:
- Ingen "forventede motkontoer" / outlier-logikk i denne iterasjonen.
- Fokus på enkel visning + drilldown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

try:
    import tkinter as tk
    from tkinter import filedialog, ttk

    TK_AVAILABLE = True
except Exception:  # pragma: no cover
    TK_AVAILABLE = False

    class _TkStub:
        class Toplevel:
            def __init__(self, *args, **kwargs):
                raise RuntimeError('Tkinter is not available in this environment.')

        class Misc:
            pass

    tk = _TkStub()  # type: ignore
    filedialog = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import formatting
from konto_utils import konto_to_str

try:
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None  # type: ignore


REQUIRED_COLS: tuple[str, ...] = ("Bilag", "Konto", "Beløp")


def _uniq_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _normalize_accounts(konto_list: Sequence[Any]) -> List[str]:
    """Normalize a list of account values to comparable strings."""
    out: List[str] = []
    for k in konto_list:
        try:
            s = konto_to_str(k)
        except Exception:
            s = str(k).strip()
        if s:
            out.append(s)
    return _uniq_preserve_order(out)


def _bilag_key_series(series: pd.Series) -> pd.Series:
    """Create a stable, comparable bilag key.

    Handles typical "3.0" vs "3" mismatches by stripping a trailing ".0".
    """
    s = series.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)
    # astype(str) turns NaN into "nan"; treat that as missing
    return s.replace({"nan": ""})


@dataclass
class MotpostData:
    accounts: List[str]
    bilag_keys: List[str]
    df_tx: pd.DataFrame
    df_summary: pd.DataFrame
    df_details: pd.DataFrame


def build_motpost_data(df_transactions: pd.DataFrame, konto_list: Sequence[Any]) -> MotpostData:
    """Build summary + detail frames for motpost analysis.

    Summary is aggregated *across all selected accounts* (combined view), i.e.
    each motkonto appears once.

    df_details contains one row per (bilag, motkonto).
    """
    accounts = _normalize_accounts(konto_list)

    empty_summary = pd.DataFrame(columns=["Motkonto", "Motkontonavn", "SumBeløp", "Antall bilag"])
    empty_details = pd.DataFrame(
        columns=[
            "Bilag_key",
            "Bilag",
            "Motkonto",
            "Motkontonavn",
            "Motbeløp",
            "Beløp valgte kontoer",
            "Kontoer",
            "Dato",
            "Tekst",
        ]
    )

    if df_transactions is None or not isinstance(df_transactions, pd.DataFrame) or df_transactions.empty:
        return MotpostData(accounts=accounts, bilag_keys=[], df_tx=pd.DataFrame(), df_summary=empty_summary, df_details=empty_details)

    if not accounts:
        # Still return a df_tx with Bilag_key for drilldown robustness.
        df_tx = df_transactions.copy()
        if "Bilag" in df_tx.columns:
            df_tx["Bilag_key"] = _bilag_key_series(df_tx["Bilag"])
        return MotpostData(accounts=accounts, bilag_keys=[], df_tx=df_tx, df_summary=empty_summary, df_details=empty_details)

    # Ensure required columns exist
    for col in REQUIRED_COLS:
        if col not in df_transactions.columns:
            return MotpostData(accounts=accounts, bilag_keys=[], df_tx=df_transactions.copy(), df_summary=empty_summary, df_details=empty_details)

    df_tx = df_transactions.copy()
    df_tx["Konto"] = df_tx["Konto"].apply(konto_to_str)
    df_tx["Beløp"] = pd.to_numeric(df_tx["Beløp"], errors="coerce").fillna(0.0)
    df_tx["Bilag_key"] = _bilag_key_series(df_tx["Bilag"])
    df_tx = df_tx[df_tx["Bilag_key"] != ""]

    accounts_set = set(accounts)

    df_sel = df_tx[df_tx["Konto"].isin(accounts_set)]
    bilag_keys = sorted(df_sel["Bilag_key"].unique().tolist())

    if not bilag_keys:
        return MotpostData(accounts=accounts, bilag_keys=[], df_tx=df_tx, df_summary=empty_summary, df_details=empty_details)

    # Only consider bilag where selected accounts exist
    df_scope = df_tx[df_tx["Bilag_key"].isin(bilag_keys)]

    # Motpost lines are all lines in those bilag not belonging to selected accounts.
    df_mot = df_scope[~df_scope["Konto"].isin(accounts_set)]

    if df_mot.empty:
        return MotpostData(accounts=accounts, bilag_keys=bilag_keys, df_tx=df_tx, df_summary=empty_summary, df_details=empty_details)

    mot_name_map: dict[str, str] = {}
    if "Kontonavn" in df_mot.columns:
        try:
            s = df_mot.dropna(subset=["Kontonavn"]).groupby("Konto")["Kontonavn"].first()
            mot_name_map = {str(k): str(v) for k, v in s.to_dict().items()}
        except Exception:
            mot_name_map = {}

    # Summary per motkonto
    df_summary = (
        df_mot.groupby("Konto")
        .agg(**{"SumBeløp": ("Beløp", "sum"), "Antall bilag": ("Bilag_key", "nunique")})
        .reset_index()
        .rename(columns={"Konto": "Motkonto"})
    )
    df_summary["Motkontonavn"] = df_summary["Motkonto"].map(mot_name_map).fillna("")
    df_summary = df_summary[["Motkonto", "Motkontonavn", "SumBeløp", "Antall bilag"]]

    # Sort by absolute amount (descending)
    df_summary["__abs"] = df_summary["SumBeløp"].abs()
    df_summary = df_summary.sort_values("__abs", ascending=False).drop(columns=["__abs"]).reset_index(drop=True)

    # Detail rows per (bilag, motkonto)
    df_details = (
        df_mot.groupby(["Bilag_key", "Konto"])
        .agg(Motbeløp=("Beløp", "sum"))
        .reset_index()
        .rename(columns={"Konto": "Motkonto"})
    )
    df_details["Motkontonavn"] = df_details["Motkonto"].map(mot_name_map).fillna("")
    # Map a representative bilag value for display (prefer a clean string without trailing .0)
    bilag_disp = df_scope.groupby("Bilag_key")["Bilag"].first()
    try:
        bilag_disp = (
            bilag_disp.astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .replace({"nan": "", "None": ""})
        )
    except Exception:
        bilag_disp = bilag_disp

    df_details["Bilag"] = df_details["Bilag_key"].map(bilag_disp).fillna("")
    df_details.loc[df_details["Bilag"] == "", "Bilag"] = df_details["Bilag_key"]

    # Sum of selected accounts per bilag (useful context)
    sel_sum = df_sel.groupby("Bilag_key")["Beløp"].sum()
    df_details["Beløp valgte kontoer"] = df_details["Bilag_key"].map(sel_sum)

    # Selected accounts present in the bilag
    sel_accounts = df_sel.groupby("Bilag_key")["Konto"].apply(lambda s: ", ".join(sorted(set(s))))
    df_details["Kontoer"] = df_details["Bilag_key"].map(sel_accounts).fillna("")

    # Optional metadata
    for col in ("Dato", "Tekst"):
        if col in df_scope.columns:
            meta = df_scope.groupby("Bilag_key")[col].first()
            df_details[col] = df_details["Bilag_key"].map(meta)
        else:
            df_details[col] = ""

    df_details = df_details[
        [
            "Bilag_key",
            "Bilag",
            "Motkonto",
            "Motkontonavn",
            "Motbeløp",
            "Beløp valgte kontoer",
            "Kontoer",
            "Dato",
            "Tekst",
        ]
    ]

    df_details["__abs"] = df_details["Motbeløp"].abs()
    df_details = df_details.sort_values("__abs", ascending=False).drop(columns=["__abs"]).reset_index(drop=True)

    return MotpostData(accounts=accounts, bilag_keys=bilag_keys, df_tx=df_tx, df_summary=df_summary, df_details=df_details)


class MotpostKontoView(tk.Toplevel):
    def __init__(self, master: tk.Misc, data: MotpostData) -> None:
        super().__init__(master)
        self.title("Motpostanalyse")
        self.geometry("1100x700")

        self._data = data
        self._df_tx = data.df_tx
        self._df_summary = data.df_summary
        self._df_details = data.df_details

        self._current_details_view: pd.DataFrame = data.df_details

        self._build_ui()
        self._populate_summary()

        # Default: select first summary row to populate bilag list.
        self.after(0, self._select_first_summary_row)

    def _build_ui(self) -> None:
        info = ttk.Label(
            self,
            text=(
                f"Valgte kontoer: {', '.join(self._data.accounts)}   |   "
                f"Bilag i grunnlag: {formatting.format_int_no(len(self._data.bilag_keys))}"
            ),
        )
        info.pack(anchor="w", padx=10, pady=(10, 6))

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        # --- Summary tree (motkonto pivot) ---
        frm_sum = ttk.LabelFrame(main, text="Motkonto (pivot)")
        frm_sum.grid(row=0, column=0, sticky="nsew")
        frm_sum.rowconfigure(0, weight=1)
        frm_sum.columnconfigure(0, weight=1)

        self.tv_sum = ttk.Treeview(
            frm_sum,
            columns=("Motkonto", "Motkontonavn", "SumBeløp", "Antall bilag"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        self.tv_sum.heading("Motkonto", text="Motkonto")
        self.tv_sum.heading("Motkontonavn", text="Kontonavn")
        self.tv_sum.heading("SumBeløp", text="Sum")
        self.tv_sum.heading("Antall bilag", text="Antall bilag")

        self.tv_sum.column("Motkonto", width=90, anchor="w")
        self.tv_sum.column("Motkontonavn", width=350, anchor="w")
        self.tv_sum.column("SumBeløp", width=140, anchor="e")
        self.tv_sum.column("Antall bilag", width=120, anchor="e")

        sb_sum = ttk.Scrollbar(frm_sum, orient="vertical", command=self.tv_sum.yview)
        self.tv_sum.configure(yscrollcommand=sb_sum.set)

        self.tv_sum.grid(row=0, column=0, sticky="nsew")
        sb_sum.grid(row=0, column=1, sticky="ns")

        self.tv_sum.tag_configure("neg", foreground="red")
        self.tv_sum.bind("<<TreeviewSelect>>", self._on_summary_select)

        # --- Detail tree (bilag list for selected motkonto) ---
        frm_det = ttk.LabelFrame(main, text="Bilag for valgt motkonto")
        frm_det.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        frm_det.rowconfigure(0, weight=1)
        frm_det.columnconfigure(0, weight=1)

        self.tv_det = ttk.Treeview(
            frm_det,
            columns=(
                "Bilag",
                "Dato",
                "Tekst",
                "Beløp valgte kontoer",
                "Motbeløp",
                "Kontoer",
            ),
            show="headings",
            selectmode="browse",
            height=12,
        )
        self.tv_det.heading("Bilag", text="Bilag")
        self.tv_det.heading("Dato", text="Dato")
        self.tv_det.heading("Tekst", text="Tekst")
        self.tv_det.heading("Beløp valgte kontoer", text="Beløp (valgte kontoer)")
        self.tv_det.heading("Motbeløp", text="Motbeløp")
        self.tv_det.heading("Kontoer", text="Kontoer i bilag")

        self.tv_det.column("Bilag", width=90, anchor="w")
        self.tv_det.column("Dato", width=110, anchor="w")
        self.tv_det.column("Tekst", width=360, anchor="w")
        self.tv_det.column("Beløp valgte kontoer", width=160, anchor="e")
        self.tv_det.column("Motbeløp", width=140, anchor="e")
        self.tv_det.column("Kontoer", width=220, anchor="w")

        sb_det = ttk.Scrollbar(frm_det, orient="vertical", command=self.tv_det.yview)
        self.tv_det.configure(yscrollcommand=sb_det.set)

        self.tv_det.grid(row=0, column=0, sticky="nsew")
        sb_det.grid(row=0, column=1, sticky="ns")

        self.tv_det.tag_configure("neg", foreground="red")
        self.tv_det.bind("<Double-1>", lambda _e: self._drilldown_selected_bilag())

        # --- Bottom buttons ---
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=(0, 10))

        btn_drill = ttk.Button(btns, text="Drilldown", command=self._drilldown_selected_bilag)
        btn_export = ttk.Button(btns, text="Eksporter Excel", command=self._export_excel)
        btn_close = ttk.Button(btns, text="Lukk", command=self.destroy)

        btn_drill.pack(side="left")
        btn_export.pack(side="left", padx=6)
        btn_close.pack(side="right")

    def _populate_summary(self) -> None:
        self.tv_sum.delete(*self.tv_sum.get_children())

        if self._df_summary.empty:
            # Keep view open, but show empty
            return

        for _, row in self._df_summary.iterrows():
            motkonto = str(row.get("Motkonto", ""))
            navn = str(row.get("Motkontonavn", ""))
            sumbelop = float(row.get("SumBeløp", 0.0) or 0.0)
            antall = int(row.get("Antall bilag", 0) or 0)

            tags = ("neg",) if sumbelop < 0 else ()

            self.tv_sum.insert(
                "",
                "end",
                iid=motkonto,
                values=(
                    motkonto,
                    navn,
                    formatting.format_number_no(sumbelop),
                    formatting.format_int_no(antall),
                ),
                tags=tags,
            )

    def _select_first_summary_row(self) -> None:
        if self.tv_sum.get_children():
            first = self.tv_sum.get_children()[0]
            self.tv_sum.selection_set(first)
            self.tv_sum.focus(first)
            self.tv_sum.see(first)
            self._on_summary_select()
        else:
            self._populate_details(self._df_details.iloc[0:0])

    def _on_summary_select(self, _event: Any | None = None) -> None:
        sel = self.tv_sum.selection()
        if not sel:
            self._populate_details(self._df_details.iloc[0:0])
            return

        motkonto = str(sel[0])
        df_view = self._df_details[self._df_details["Motkonto"].astype(str) == motkonto]
        self._populate_details(df_view)

    def _populate_details(self, df_view: pd.DataFrame) -> None:
        self._current_details_view = df_view
        self.tv_det.delete(*self.tv_det.get_children())

        if df_view is None or df_view.empty:
            return

        for _, row in df_view.iterrows():
            bilag_key = str(row.get("Bilag_key", ""))
            bilag_disp = str(row.get("Bilag", ""))
            dato = formatting.fmt_date(row.get("Dato", ""))
            tekst = str(row.get("Tekst", ""))

            belop_sel = float(row.get("Beløp valgte kontoer", 0.0) or 0.0)
            motbelop = float(row.get("Motbeløp", 0.0) or 0.0)
            kontoer = str(row.get("Kontoer", ""))

            iid = f"{bilag_key}__{row.get('Motkonto', '')}"

            tags = ("neg",) if motbelop < 0 else ()

            self.tv_det.insert(
                "",
                "end",
                iid=iid,
                values=(
                    bilag_disp,
                    dato,
                    tekst,
                    formatting.format_number_no(belop_sel),
                    formatting.format_number_no(motbelop),
                    kontoer,
                ),
                tags=tags,
            )

    def _drilldown_selected_bilag(self) -> None:
        sel = self.tv_det.selection()
        if not sel:
            return

        item = str(sel[0])
        bilag_key = item.split("__", 1)[0].strip()
        if not bilag_key:
            vals = self.tv_det.item(item, "values") or ()
            if not vals:
                return
            bilag_key = str(vals[0]).strip()
        if not bilag_key:
            return

        # Prefer the same drilldown dialog used elsewhere (marks selected accounts as "i kontoutvalg")
        if _open_bilag_drill_dialog is not None:
            try:
                df_base = self._df_tx[self._df_tx["Konto"].map(konto_to_str).isin(set(self._data.accounts))]
                _open_bilag_drill_dialog(
                    master=self,
                    df_base=df_base,
                    df_all=self._df_tx,
                    bilag_value=bilag_key,
                    bilag_col="Bilag_key",
                )
                return
            except Exception:
                pass

        # Fallback to a simpler dialog if available
        try:
            from views_bilag_drill import BilagDrillDialog

            dialog = BilagDrillDialog(self, self._df_tx, bilag_col="Bilag_key")
            dialog.preset_and_show(bilag_key)
        except Exception:
            return


    def _export_excel(self) -> None:
        """Export summary + currently shown bilag list to Excel."""
        if filedialog is None:  # pragma: no cover
            return
        try:
            from openpyxl import Workbook
        except Exception:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="motpostanalyse.xlsx",
        )
        if not path:
            return

        wb = Workbook()

        # Sheet 1: Summary
        ws = wb.active
        ws.title = "Motpost"
        ws.append(["Motkonto", "Kontonavn", "SumBeløp", "Antall bilag"])
        for _, row in self._df_summary.iterrows():
            ws.append(
                [
                    row.get("Motkonto", ""),
                    row.get("Motkontonavn", ""),
                    float(row.get("SumBeløp", 0.0) or 0.0),
                    int(row.get("Antall bilag", 0) or 0),
                ]
            )

        # Sheet 2: Details (filtered view)
        ws2 = wb.create_sheet("Bilag")
        ws2.append(
            [
                "Bilag",
                "Motkonto",
                "Kontonavn",
                "Motbeløp",
                "Beløp valgte kontoer",
                "Kontoer",
                "Dato",
                "Tekst",
            ]
        )

        df_view = self._current_details_view if self._current_details_view is not None else self._df_details
        for _, row in df_view.iterrows():
            ws2.append(
                [
                    row.get("Bilag", ""),
                    row.get("Motkonto", ""),
                    row.get("Motkontonavn", ""),
                    float(row.get("Motbeløp", 0.0) or 0.0),
                    float(row.get("Beløp valgte kontoer", 0.0) or 0.0),
                    row.get("Kontoer", ""),
                    row.get("Dato", ""),
                    row.get("Tekst", ""),
                ]
            )

        try:
            wb.save(path)
        except Exception:
            return


def show_motpost_konto(master: tk.Misc, df_transactions: pd.DataFrame, konto_list: Sequence[Any]) -> "MotpostKontoView":
    '''Open motpost view as a popup window.'''

    if not TK_AVAILABLE:  # pragma: no cover
        raise RuntimeError('Tkinter is not available, cannot open Motpost-vindu.')

    if not isinstance(df_transactions, pd.DataFrame):
        raise TypeError('df_transactions must be a pandas DataFrame')

    data = build_motpost_data(df_transactions=df_transactions, konto_list=konto_list)
    view = MotpostKontoView(master, data)
    view.grab_set()
    view.focus_force()
    return view
