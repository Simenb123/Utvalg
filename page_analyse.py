"""page_analyse.py

Analyse-fanen: konto-pivot (venstre) + transaksjonsliste (høyre).

Refaktorering (2026):
- Mer av pandas-/databyggelogikk er flyttet til `analyse_viewdata.py`
  slik at denne modulen i større grad kan fokusere på GUI.
- Excel-eksport og motpost/bilagsdrill er fortsatt tilgjengelig via knapper.

Designmål:
- Robust i headless/CI (Tk kan feile i linux uten display)
- Best-effort: manglende kolonner => tomme visninger, ikke crash
- Norske formater: dd.mm.yyyy, tusenskiller med mellomrom, desimal komma
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    filedialog = None  # type: ignore

import pandas as pd

import analyse_viewdata as av
import formatting
import session
from analyse_model import build_pivot_by_account
from analysis_filters import filter_dataset, parse_amount
from controller_export import export_to_excel
from konto_utils import konto_to_str
from logger import get_logger
from page_analyse_actions import open_motpost

log = get_logger()


# -----------------------------------------------------------------------------
# Headless/test helpers
# -----------------------------------------------------------------------------

def _running_under_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _safe_showinfo(title: str, msg: str) -> None:
    if messagebox is None or _running_under_pytest():
        return
    try:
        messagebox.showinfo(title, msg)
    except Exception:
        pass


def _safe_showerror(title: str, msg: str) -> None:
    if messagebox is None or _running_under_pytest():
        return
    try:
        messagebox.showerror(title, msg)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Bilagsdrill dialog dependency (tests monkeypatcher denne)
# -----------------------------------------------------------------------------

try:  # pragma: no cover (importeres i runtime GUI)
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None  # type: ignore


# -----------------------------------------------------------------------------
# Optional: behold gamle helper-navn (kan være nyttig i eldre tester)
# -----------------------------------------------------------------------------

try:  # pragma: no cover
    import ui_hotkeys as _ui_hotkeys  # type: ignore
except Exception:  # pragma: no cover
    _ui_hotkeys = None  # type: ignore


def _treeview_select_all(tree: object) -> None:
    """Bakoverkompatibel wrapper (brukes av eldre tester)."""
    if _ui_hotkeys is not None:
        try:
            _ui_hotkeys.treeview_select_all(tree)  # type: ignore[attr-defined]
            return
        except Exception:
            pass

    # Minimal fallback
    try:
        children = tree.get_children()  # type: ignore[attr-defined]
        tree.selection_set(children)  # type: ignore[attr-defined]
    except Exception:
        return


def _treeview_selection_to_tsv(tree: object) -> str:
    """Bakoverkompatibel wrapper (brukes av eldre tester)."""
    if _ui_hotkeys is not None:
        try:
            return _ui_hotkeys.treeview_selection_to_tsv(tree)  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        cols = tree["columns"]  # type: ignore[index]
        sel = tree.selection()  # type: ignore[attr-defined]
    except Exception:
        return ""

    lines: list[str] = []
    lines.append("\t".join(str(c) for c in cols))
    for item in sel:
        try:
            values = tree.item(item).get("values") or []  # type: ignore[attr-defined]
        except Exception:
            values = []
        lines.append("\t".join(str(v) for v in values))
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Retning / filtervalg
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class _DirectionOpt:
    label: str
    value: Optional[str]  # None | "debet" | "kredit"


_DIR_OPTIONS: List[_DirectionOpt] = [
    _DirectionOpt("Alle", None),
    _DirectionOpt("Debet", "debet"),
    _DirectionOpt("Kredit", "kredit"),
]


_BaseFrame = ttk.Frame if ttk is not None else object


class AnalysePage(_BaseFrame):  # type: ignore[misc]
    """GUI-side for analyse."""

    PIVOT_COLS = ("Konto", "Kontonavn", "Sum", "Antall")
    TX_COLS = tuple(av.DEFAULT_TX_COLS)

    def __init__(self, master=None):
        # --- headless-friendly init ---
        self._tk_ok: bool = False
        self._init_error: Optional[Exception] = None

        # Attributter som testene forventer at finnes
        self.dataset: object | None = None
        self._df_all: Optional[pd.DataFrame] = None
        self._df_filtered: Optional[pd.DataFrame] = None
        self._utvalg_callback: Optional[Callable[[List[str]], None]] = None

        # GUI widgets (settes i _build_ui)
        self._pivot_tree: Optional[ttk.Treeview] = None  # type: ignore[assignment]
        self._tx_tree: Optional[ttk.Treeview] = None  # type: ignore[assignment]
        self._lbl_tx_summary: Optional[ttk.Label] = None  # type: ignore[assignment]

        # Siste pivot (for eksport)
        self._pivot_df_last: Optional[pd.DataFrame] = None

        if tk is None or ttk is None:
            # Tkinter ikke tilgjengelig i dette miljøet
            self._tk_ok = False
            return

        try:
            super().__init__(master)
            self._tk_ok = True
        except Exception as e:  # TclError / display-problemer
            self._tk_ok = False
            self._init_error = e
            return

        # --- vars ---
        self._var_search = tk.StringVar(value="")
        self._var_direction = tk.StringVar(value=_DIR_OPTIONS[0].label)
        self._var_min = tk.StringVar(value="")
        self._var_max = tk.StringVar(value="")
        self._var_max_rows = tk.IntVar(value=200)
        self._series_vars = [tk.IntVar(value=0) for _ in range(10)]

        self._build_ui()

    # ---------------------------------------------------------------------
    # Public API expected by ui_main/tests
    # ---------------------------------------------------------------------

    def set_utvalg_callback(self, callback: Callable[[List[str]], None]) -> None:
        self._utvalg_callback = callback

    def refresh_from_session(self, sess: object = session) -> None:
        """Reload data from session and refresh UI.

        Viktig: Vi beholder råverdien i self.dataset (ikke bare DataFrame),
        slik at headless-tester kan sette dummy-verdier og verifisere at
        metoden faktisk oppdaterer feltet.
        """
        df = getattr(sess, "dataset", None)

        # Behold råverdien på self.dataset (gir enklere testing/headless).
        self.dataset = df  # type: ignore[assignment]

        if isinstance(df, pd.DataFrame):
            self._df_all = df
        else:
            self._df_all = None

        self._apply_filters_and_refresh()

    # ---------------------------------------------------------------------
    # UI building
    # ---------------------------------------------------------------------

    def _build_ui(self) -> None:
        if not self._tk_ok:
            return

        # Filter row
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(filter_frame, text="Søk:").grid(row=0, column=0, sticky="w")
        ent_search = ttk.Entry(filter_frame, textvariable=self._var_search, width=18)
        ent_search.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(filter_frame, text="Retning:").grid(row=0, column=2, sticky="e")
        opt = ttk.OptionMenu(filter_frame, self._var_direction, self._var_direction.get(), *[o.label for o in _DIR_OPTIONS])
        opt.grid(row=0, column=3, sticky="w", padx=(4, 12))

        ttk.Label(filter_frame, text="Kontoserier:").grid(row=0, column=4, sticky="e")
        series_frame = ttk.Frame(filter_frame)
        series_frame.grid(row=0, column=5, sticky="w", padx=(4, 12))
        for d in range(10):
            cb = ttk.Checkbutton(
                series_frame,
                text=str(d),
                variable=self._series_vars[d],
            )
            cb.pack(side="left", padx=(2, 0))

        ttk.Label(filter_frame, text="Vis:").grid(row=0, column=6, sticky="e", padx=(12, 0))
        spn_rows = ttk.Spinbox(filter_frame, from_=50, to=5000, increment=50, textvariable=self._var_max_rows, width=6)
        spn_rows.grid(row=0, column=7, sticky="w", padx=(4, 12))

        ttk.Label(filter_frame, text="Min beløp:").grid(row=0, column=8, sticky="e")
        ent_min = ttk.Entry(filter_frame, textvariable=self._var_min, width=10)
        ent_min.grid(row=0, column=9, sticky="w", padx=(4, 8))

        ttk.Label(filter_frame, text="Maks beløp:").grid(row=0, column=10, sticky="e")
        ent_max = ttk.Entry(filter_frame, textvariable=self._var_max, width=10)
        ent_max.grid(row=0, column=11, sticky="w", padx=(4, 12))

        btn_reset = ttk.Button(filter_frame, text="Nullstill", command=self._reset_filters)
        btn_reset.grid(row=0, column=12, sticky="e")

        btn_apply = ttk.Button(filter_frame, text="Bruk filtre", command=self._apply_filters_and_refresh)
        btn_apply.grid(row=0, column=13, sticky="e", padx=(6, 0))

        btn_all = ttk.Button(filter_frame, text="Marker alle", command=self._select_all_accounts)
        btn_all.grid(row=0, column=14, sticky="e", padx=(12, 0))

        btn_to_utvalg = ttk.Button(filter_frame, text="Til utvalg", command=self._send_selected_to_utvalg)
        btn_to_utvalg.grid(row=0, column=15, sticky="e", padx=(6, 0))

        btn_motpost = ttk.Button(filter_frame, text="Motpost", command=self._open_motpost)
        btn_motpost.grid(row=0, column=16, sticky="e", padx=(6, 0))

        # allow the right side to expand
        filter_frame.grid_columnconfigure(16, weight=1)

        # Main split
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)

        # Pivot side
        pivot_frame = ttk.Frame(main)
        pivot_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        pivot_frame.grid_rowconfigure(1, weight=1)
        pivot_frame.grid_columnconfigure(0, weight=1)

        hdr_pivot = ttk.Frame(pivot_frame)
        hdr_pivot.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        hdr_pivot.grid_columnconfigure(0, weight=1)

        ttk.Label(hdr_pivot, text="Pivot pr konto").grid(row=0, column=0, sticky="w")
        ttk.Button(hdr_pivot, text="Eksporter", command=self._export_pivot_to_excel).grid(
            row=0, column=1, sticky="e", padx=(6, 0)
        )

        self._pivot_tree = ttk.Treeview(
            pivot_frame,
            columns=self.PIVOT_COLS,
            show="headings",
            selectmode="extended",
        )
        for col, w in zip(self.PIVOT_COLS, (90, 220, 110, 70)):
            anchor = "e" if col in ("Sum", "Antall") else "w"
            self._pivot_tree.heading(col, text=col)
            self._pivot_tree.column(col, width=w, anchor=anchor)
        self._pivot_tree.grid(row=1, column=0, sticky="nsew")

        sb_pivot = ttk.Scrollbar(pivot_frame, orient="vertical", command=self._pivot_tree.yview)
        sb_pivot.grid(row=1, column=1, sticky="ns")
        self._pivot_tree.configure(yscrollcommand=sb_pivot.set)

        # Transactions side
        tx_frame = ttk.Frame(main)
        tx_frame.grid(row=1, column=1, sticky="nsew")
        tx_frame.grid_rowconfigure(1, weight=1)
        tx_frame.grid_columnconfigure(0, weight=1)

        hdr_tx = ttk.Frame(tx_frame)
        hdr_tx.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        hdr_tx.grid_columnconfigure(0, weight=1)

        self._lbl_tx_summary = ttk.Label(hdr_tx, text="Oppsummering: (ingen rader)")
        self._lbl_tx_summary.grid(row=0, column=0, sticky="w")

        ttk.Button(hdr_tx, text="Bilagsdrill", command=self._open_bilag_drilldown_from_tx_selection).grid(
            row=0, column=1, sticky="e", padx=(6, 0)
        )
        ttk.Button(hdr_tx, text="Eksporter", command=self._export_transactions_to_excel).grid(
            row=0, column=2, sticky="e", padx=(6, 0)
        )

        self._tx_tree = ttk.Treeview(tx_frame, columns=self.TX_COLS, show="headings")
        col_widths = {
            "Bilag": 80,
            "Beløp": 100,
            "Tekst": 240,
            "Kunder": 160,
            "Konto": 70,
            "Kontonavn": 180,
            "Dato": 90,
        }
        for col in self.TX_COLS:
            anchor = "e" if col == "Beløp" else "w"
            self._tx_tree.heading(col, text=col)
            self._tx_tree.column(col, width=col_widths.get(col, 120), anchor=anchor)
        self._tx_tree.grid(row=1, column=0, sticky="nsew")

        sb_tx = ttk.Scrollbar(tx_frame, orient="vertical", command=self._tx_tree.yview)
        sb_tx.grid(row=1, column=1, sticky="ns")
        self._tx_tree.configure(yscrollcommand=sb_tx.set)

        # Formatting tags (negative)
        self._tx_tree.tag_configure("neg", foreground="red")

        # Bilagsdrilldown (dobbeltklikk / Enter)
        self._tx_tree.bind("<Double-1>", lambda _e: self._open_bilag_drilldown_from_tx_selection())
        self._tx_tree.bind("<Return>", lambda _e: self._open_bilag_drilldown_from_tx_selection())

        # Events
        self._pivot_tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_transactions_view())

        # Helpful shortcuts
        ent_search.bind("<Return>", lambda _e: self._apply_filters_and_refresh())
        ent_min.bind("<Return>", lambda _e: self._apply_filters_and_refresh())
        ent_max.bind("<Return>", lambda _e: self._apply_filters_and_refresh())

    # ---------------------------------------------------------------------
    # Filtering / refresh
    # ---------------------------------------------------------------------

    def _reset_filters(self) -> None:
        if not self._tk_ok:
            return
        self._var_search.set("")
        self._var_direction.set(_DIR_OPTIONS[0].label)
        self._var_min.set("")
        self._var_max.set("")
        self._var_max_rows.set(200)
        for v in self._series_vars:
            v.set(0)
        self._apply_filters_and_refresh()

    def _apply_filters_and_refresh(self) -> None:
        if not self._tk_ok:
            return

        # Finn DataFrame
        df_raw = self.dataset
        if not isinstance(df_raw, pd.DataFrame):
            self._df_filtered = None
            self._pivot_df_last = None
            self._clear_tree(self._pivot_tree)
            self._clear_tree(self._tx_tree)
            if self._lbl_tx_summary is not None:
                self._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            return

        self._df_all = df_raw

        # Parse filter inputs
        search = str(self._var_search.get() or "")
        direction_label = str(self._var_direction.get() or "Alle")
        min_val = parse_amount(self._var_min.get())
        max_val = parse_amount(self._var_max.get())

        kontoserier = [i for i, v in enumerate(self._series_vars) if int(v.get() or 0) == 1]

        try:
            df_f = filter_dataset(
                df_raw,
                search=search,
                direction=direction_label,
                min_amount=min_val,
                max_amount=max_val,
                kontoserier=kontoserier,
            )
        except Exception as e:
            log.exception("Filterfeil")
            _safe_showerror("Analyse", f"Kunne ikke filtrere datasettet.\n\n{e}")
            df_f = df_raw.copy()

        # Normaliser Konto til streng (for stabil UI/utvalg)
        if isinstance(df_f, pd.DataFrame) and not df_f.empty and "Konto" in df_f.columns:
            try:
                df_f = df_f.copy()
                df_f["Konto"] = df_f["Konto"].map(konto_to_str)
            except Exception:
                pass

        self._df_filtered = df_f

        self._refresh_pivot()
        self._refresh_transactions_view()

    def _clear_tree(self, tree: Optional[ttk.Treeview]) -> None:
        if tree is None:
            return
        try:
            for item in tree.get_children():
                tree.delete(item)
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Pivot: selection helpers
    # ---------------------------------------------------------------------

    def _select_all_accounts(self) -> None:
        if self._pivot_tree is None:
            return
        try:
            children = self._pivot_tree.get_children()
            self._pivot_tree.selection_set(children)
        except Exception:
            return
        self._refresh_transactions_view()

    def _get_selected_accounts(self) -> List[str]:
        if self._pivot_tree is None:
            return []

        try:
            sel = self._pivot_tree.selection()
        except Exception:
            sel = ()

        # Hvis ingenting er valgt: returner alle kontoer i pivoten (brukervennlig)
        items = list(sel) if sel else list(self._pivot_tree.get_children())

        accounts: list[str] = []
        for item in items:
            konto = ""
            try:
                konto = str(self._pivot_tree.set(item, "Konto") or "")
            except Exception:
                konto = ""
            konto = konto_to_str(konto)
            if konto:
                accounts.append(konto)

        # dedupe, behold rekkefølge
        seen: set[str] = set()
        unique: list[str] = []
        for a in accounts:
            if a not in seen:
                unique.append(a)
                seen.add(a)
        return unique

    # ---------------------------------------------------------------------
    # Pivot: refresh
    # ---------------------------------------------------------------------

    def _refresh_pivot(self) -> None:
        if self._pivot_tree is None:
            return

        self._clear_tree(self._pivot_tree)
        self._pivot_df_last = None

        if self._df_filtered is None or self._df_filtered.empty:
            return

        if "Konto" not in self._df_filtered.columns:
            return

        try:
            pivot = build_pivot_by_account(self._df_filtered)
        except Exception as e:
            log.exception("Pivotfeil")
            _safe_showerror("Analyse", f"Kunne ikke bygge pivot.\n\n{e}")
            return

        if pivot is None or pivot.empty:
            return

        self._pivot_df_last = pivot.copy()

        # Velg hvilke kolonnenavn som finnes i pivot
        sum_col = "Sum beløp" if "Sum beløp" in pivot.columns else ("Sum" if "Sum" in pivot.columns else None)
        cnt_col = "Antall bilag" if "Antall bilag" in pivot.columns else ("Antall" if "Antall" in pivot.columns else None)

        for row in pivot.itertuples(index=False):
            # itertuples gir attributtnavn som kolonnenavn; fallback med getattr
            konto = konto_to_str(getattr(row, "Konto", ""))
            kontonavn = getattr(row, "Kontonavn", "") if hasattr(row, "Kontonavn") else ""

            sum_val = getattr(row, sum_col.replace(" ", "_") if sum_col else "", 0.0) if sum_col else 0.0
            cnt_val = getattr(row, cnt_col.replace(" ", "_") if cnt_col else "", "") if cnt_col else ""

            # Robust fallback: hvis itertuples ikke ga forventet navn
            if sum_col and (sum_val == 0.0 or sum_val == ""):
                try:
                    sum_val = float(pivot.loc[pivot["Konto"] == konto, sum_col].iloc[0])
                except Exception:
                    sum_val = 0.0
            if cnt_col and (cnt_val == "" or cnt_val is None):
                try:
                    cnt_val = int(pivot.loc[pivot["Konto"] == konto, cnt_col].iloc[0])
                except Exception:
                    cnt_val = ""

            self._pivot_tree.insert(
                "",
                "end",
                values=(
                    konto,
                    str(kontonavn or ""),
                    formatting.fmt_amount(sum_val),
                    formatting.fmt_int(cnt_val),
                ),
            )

    # ---------------------------------------------------------------------
    # Transactions: refresh
    # ---------------------------------------------------------------------

    def _refresh_transactions_view(self) -> None:
        if self._tx_tree is None or self._lbl_tx_summary is None:
            return

        self._clear_tree(self._tx_tree)

        if self._df_filtered is None or self._df_filtered.empty:
            self._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            return

        sel_accounts = self._get_selected_accounts()
        if not sel_accounts:
            self._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            return

        max_rows = 200
        try:
            max_rows = int(self._var_max_rows.get() or 200)
        except Exception:
            max_rows = 200

        df_all, df_show = av.compute_selected_transactions(self._df_filtered, sel_accounts, max_rows=max_rows)

        if df_all is None or df_all.empty:
            self._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            return

        # Totals for full selection
        bel_all = pd.to_numeric(df_all.get("Beløp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        total_rows = len(df_all)
        total_sum = float(bel_all.sum())

        # Display subset
        shown_rows = len(df_show)
        bel_show = pd.to_numeric(df_show.get("Beløp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        shown_sum = float(bel_show.sum())

        if total_rows == shown_rows:
            self._lbl_tx_summary.config(
                text=f"Oppsummering: {total_rows} rader | Sum: {formatting.fmt_amount(total_sum)}"
            )
        else:
            self._lbl_tx_summary.config(
                text=(
                    f"Oppsummering: {shown_rows} av {total_rows} rader | "
                    f"Sum: {formatting.fmt_amount(shown_sum)} (totalt {formatting.fmt_amount(total_sum)})"
                )
            )

        # Bygg visnings-DF (renser Kunder, formaterer Dato)
        df_view = av.build_transactions_view_df(df_show, tx_cols=self.TX_COLS)

        # Sett inn rader
        for row in df_view.itertuples(index=False):
            belop_val = getattr(row, "Beløp", 0.0)
            try:
                bel_float = float(belop_val)
            except Exception:
                bel_float = 0.0

            tags = ("neg",) if bel_float < 0 else ()

            self._tx_tree.insert(
                "",
                "end",
                values=(
                    getattr(row, "Bilag", ""),
                    formatting.fmt_amount(bel_float),
                    getattr(row, "Tekst", ""),
                    getattr(row, "Kunder", ""),
                    getattr(row, "Konto", ""),
                    getattr(row, "Kontonavn", ""),
                    getattr(row, "Dato", ""),
                ),
                tags=tags,
            )

    # ---------------------------------------------------------------------
    # Bilagsdrilldown (Analyse)
    # ---------------------------------------------------------------------

    def _get_selected_bilag_from_tx_tree(self) -> str:
        """Hent valgt bilag fra transaksjonslisten (TX tree)."""
        if self._tx_tree is None:
            return ""
        try:
            sel = self._tx_tree.selection()
        except Exception:
            sel = ()
        if not sel:
            return ""
        item = sel[0]

        bilag = ""
        try:
            bilag = str(self._tx_tree.set(item, "Bilag") or "")
        except Exception:
            bilag = ""

        if not bilag:
            try:
                values = self._tx_tree.item(item).get("values") or []
                if values:
                    bilag = str(values[0])
            except Exception:
                bilag = ""

        return str(bilag).strip()

    def _open_bilag_drilldown_from_tx_selection(self) -> None:
        bilag = self._get_selected_bilag_from_tx_tree()
        if not bilag:
            _safe_showinfo("Bilagsdrill", "Velg en transaksjon i listen først.")
            return
        self._open_bilag_drilldown_for_bilag(bilag)

    def _resolve_df_all(self) -> Optional[pd.DataFrame]:
        """Hent "alle transaksjoner" (grunnlag for drilldown/motpost).

        NB: Enkelte tester bruker AnalysePage.__new__ og setter bare noen felter
        manuelt. Derfor må denne metoden bruke getattr og tåle at _df_all ikke finnes.
        """
        df_self = getattr(self, "_df_all", None)
        if isinstance(df_self, pd.DataFrame):
            return df_self
        if isinstance(getattr(self, "dataset", None), pd.DataFrame):
            return getattr(self, "dataset")  # type: ignore[return-value]
        # fallback: global session.dataset
        df = getattr(session, "dataset", None)
        return df if isinstance(df, pd.DataFrame) else None

    def _open_bilag_drilldown_for_bilag(self, bilag_value: str) -> None:
        df_all = self._resolve_df_all()
        df_base = self._df_filtered if isinstance(self._df_filtered, pd.DataFrame) else df_all

        if df_all is None or df_base is None:
            _safe_showerror("Bilagsdrill", "Ingen datagrunnlag tilgjengelig.")
            return

        # Scope df_base til valgte kontoer (tests forventer dette)
        accounts = self._get_selected_accounts()
        if accounts and "Konto" in df_base.columns:
            try:
                konto_norm = df_base["Konto"].map(konto_to_str)
                df_base = df_base.loc[konto_norm.isin(set(accounts))].copy()
            except Exception:
                pass

        if _open_bilag_drill_dialog is None:
            _safe_showerror("Bilagsdrill", "Bilagsdrill-modul er ikke tilgjengelig.")
            return

        # Foretrekk signatur med keyword args
        try:
            _open_bilag_drill_dialog(
                self,
                df_base=df_base,
                df_all=df_all,
                bilag_value=bilag_value,
                bilag_col="Bilag",
            )
            return
        except TypeError:
            pass
        except Exception as e:
            _safe_showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
            return

        # Backwards compatible alias
        try:
            _open_bilag_drill_dialog(
                self,
                df_base=df_base,
                df_all=df_all,
                preset_bilag=bilag_value,
                bilag_col="Bilag",
            )
            return
        except TypeError:
            pass
        except Exception as e:
            _safe_showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
            return

        # Eldre signatur (positional)
        try:
            _open_bilag_drill_dialog(self, df_base, df_all, bilag_value)
        except Exception as e:
            _safe_showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")

    # ---------------------------------------------------------------------
    # Motpostanalyse (Analyse -> Motpost)
    # ---------------------------------------------------------------------

    def _open_motpost(self) -> None:
        open_motpost(
            parent=self,
            df_filtered=self._df_filtered,
            df_all=self._resolve_df_all(),
            selected_accounts=self._get_selected_accounts(),
            dataset=self.dataset,
        )

    # ---------------------------------------------------------------------
    # Excel export
    # ---------------------------------------------------------------------

    def _ask_save_path(self, *, title: str, suggested_name: str) -> str:
        if filedialog is None or _running_under_pytest():
            return ""
        try:
            return filedialog.asksaveasfilename(
                title=title,
                defaultextension=".xlsx",
                initialfile=suggested_name,
                filetypes=[("Excel", "*.xlsx")],
            )
        except Exception:
            return ""

    def _prepare_pivot_export_sheets(self) -> dict[str, pd.DataFrame]:
        return av.prepare_pivot_export_sheets(self._df_filtered, pivot_df=self._pivot_df_last)

    def _prepare_transactions_export_sheets(self) -> dict[str, pd.DataFrame]:
        max_rows = 200
        try:
            max_rows = int(self._var_max_rows.get() or 200)
        except Exception:
            max_rows = 200

        return av.prepare_transactions_export_sheets(
            self._df_filtered,
            selected_accounts=self._get_selected_accounts(),
            max_rows=max_rows,
            tx_cols=self.TX_COLS,
        )

    def _export_pivot_to_excel(self) -> None:
        sheets = self._prepare_pivot_export_sheets()
        if not sheets:
            _safe_showinfo("Eksport", "Ingen data å eksportere.")
            return

        path = self._ask_save_path(title="Eksporter pivot", suggested_name="pivot.xlsx")
        if not path:
            return

        try:
            export_to_excel(path, sheets)
            _safe_showinfo("Eksport", f"Eksportert til:\n{path}")
        except Exception as e:
            log.exception("Eksportfeil")
            _safe_showerror("Eksport", f"Kunne ikke eksportere.\n\n{e}")

    def _export_transactions_to_excel(self) -> None:
        sheets = self._prepare_transactions_export_sheets()
        if not sheets:
            _safe_showinfo("Eksport", "Ingen transaksjoner å eksportere.")
            return

        path = self._ask_save_path(title="Eksporter transaksjoner", suggested_name="transaksjoner.xlsx")
        if not path:
            return

        try:
            export_to_excel(path, sheets)
            _safe_showinfo("Eksport", f"Eksportert til:\n{path}")
        except Exception as e:
            log.exception("Eksportfeil")
            _safe_showerror("Eksport", f"Kunne ikke eksportere.\n\n{e}")

    # ---------------------------------------------------------------------
    # Utvalg callback
    # ---------------------------------------------------------------------

    def _send_to_selection(self, accounts: List[str]) -> None:
        if self._utvalg_callback is not None:
            self._utvalg_callback(accounts)

    def _send_selected_to_utvalg(self) -> None:
        accounts = self._get_selected_accounts()
        if not accounts:
            if self._lbl_tx_summary is not None:
                self._lbl_tx_summary.config(text="Ingen kontoer valgt.")
            return
        self._send_to_selection(accounts)
