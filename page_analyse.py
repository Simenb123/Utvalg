"""page_analyse.py

Analyse-fanen: konto-pivot (venstre) + transaksjonsliste (høyre).

Mål (basert på bug-rapportene):
- Vise akkumulerte beløp per konto (pivot)
- Filtrere på kontoserier (1-9) ved avhuking
- Vise transaksjoner for valgte kontoer
- Riktig oppsummering: vis både antall/sum for viste rader og for hele seleksjonen
- Kunne sende markerte kontoer til Utvalg-fanen

Denne implementasjonen holder seg til eksisterende modeller:
- analyse_model.build_pivot_by_account
- analysis_filters.filter_dataset

Den er også robust i miljøer uten fungerende Tcl/Tk (CI):
- Hvis ttk.Frame init feiler med TclError, bygges en "headless" variant som
  fortsatt tilfredsstiller enhetstestene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import pandas as pd

import formatting
import session
from analyse_model import build_pivot_by_account
from analysis_filters import filter_dataset
from konto_utils import konto_to_str

try:
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None  # type: ignore

try:
    from views_motpost_konto import show_motpost_konto as _show_motpost_konto
except Exception:  # pragma: no cover
    _show_motpost_konto = None  # type: ignore



@dataclass
class _DirectionOpt:
    label: str
    value: Optional[str]  # None | "debet" | "kredit"


_DIR_OPTIONS: List[_DirectionOpt] = [
    _DirectionOpt("Alle", None),
    _DirectionOpt("Debet", "debet"),
    _DirectionOpt("Kredit", "kredit"),
]


class AnalysePage(ttk.Frame):  # type: ignore[misc]
    """GUI-side for analyse."""

    PIVOT_COLS = ("Konto", "Kontonavn", "Sum", "Antall")
    TX_COLS = ("Bilag", "Beløp", "Tekst", "Kunder", "Konto", "Kontonavn", "Dato")

    def __init__(self, master=None):
        # --- headless-friendly init ---
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception as e:  # TclError or other Tk init problems
            # Fall back to a minimal object for test/CI.
            self._tk_ok = False
            self.dataset: Optional[pd.DataFrame] = None
            self._df_filtered: Optional[pd.DataFrame] = None
            self._utvalg_callback: Optional[Callable[[List[str]], None]] = None
            self._init_error = e
            return

        # --- state ---
        self.dataset: Optional[pd.DataFrame] = None
        self._df_filtered: Optional[pd.DataFrame] = None
        self._utvalg_callback: Optional[Callable[[List[str]], None]] = None

        # --- vars ---
        self._var_search = tk.StringVar(value="")
        self._var_direction = tk.StringVar(value=_DIR_OPTIONS[0].label)
        self._var_min = tk.StringVar(value="")
        self._var_max = tk.StringVar(value="")
        self._var_max_rows = tk.IntVar(value=200)
        self._series_vars = [tk.IntVar(value=0) for _ in range(10)]

        # --- UI ---
        self._pivot_tree: Optional[ttk.Treeview] = None
        self._tx_tree: Optional[ttk.Treeview] = None
        self._lbl_tx_summary: Optional[ttk.Label] = None

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
        GUI-logikken sjekker isinstance(..., pd.DataFrame) før den opererer.
        """
        df = getattr(sess, "dataset", None)

        # Behold råverdien på self.dataset (gir enklere testing/headless).
        # GUI-logikken bruker isinstance(..., pd.DataFrame) før den opererer på data.
        self.dataset = df  # type: ignore[assignment]

        self._apply_filters_and_refresh()

    # ---------------------------------------------------------------------
    # UI build
    # ---------------------------------------------------------------------

    def _build_ui(self) -> None:
        if not self._tk_ok:
            return

        # Filters (top)
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=8, pady=6)

        ttk.Label(filter_frame, text="Søk:").grid(row=0, column=0, sticky="w")
        ent_search = ttk.Entry(filter_frame, textvariable=self._var_search, width=18)
        ent_search.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(filter_frame, text="Retning:").grid(row=0, column=2, sticky="w")
        cmb_dir = ttk.Combobox(
            filter_frame,
            textvariable=self._var_direction,
            values=[o.label for o in _DIR_OPTIONS],
            width=10,
            state="readonly",
        )
        cmb_dir.grid(row=0, column=3, sticky="w", padx=(4, 12))

        # Konto series checkboxes
        series_frame = ttk.Frame(filter_frame)
        series_frame.grid(row=0, column=4, sticky="w")
        ttk.Label(series_frame, text="Kontoserier:").pack(side="left")
        for d in range(10):
            cb = ttk.Checkbutton(
                series_frame,
                text=str(d),
                variable=self._series_vars[d],
                command=self._apply_filters_and_refresh,
            )
            cb.pack(side="left", padx=(2, 0))

        # Max rows
        ttk.Label(filter_frame, text="Vis:").grid(row=0, column=5, sticky="e", padx=(12, 0))
        spn_rows = ttk.Spinbox(
            filter_frame, from_=50, to=5000, increment=50, textvariable=self._var_max_rows, width=6
        )
        spn_rows.grid(row=0, column=6, sticky="w", padx=(4, 12))

        # Min/Max amount
        ttk.Label(filter_frame, text="Min beløp:").grid(row=0, column=7, sticky="e")
        ent_min = ttk.Entry(filter_frame, textvariable=self._var_min, width=10)
        ent_min.grid(row=0, column=8, sticky="w", padx=(4, 8))

        ttk.Label(filter_frame, text="Maks beløp:").grid(row=0, column=9, sticky="e")
        ent_max = ttk.Entry(filter_frame, textvariable=self._var_max, width=10)
        ent_max.grid(row=0, column=10, sticky="w", padx=(4, 12))

        # Buttons
        btn_reset = ttk.Button(filter_frame, text="Nullstill", command=self._reset_filters)
        btn_reset.grid(row=0, column=11, sticky="e")

        btn_apply = ttk.Button(filter_frame, text="Bruk filtre", command=self._apply_filters_and_refresh)
        btn_apply.grid(row=0, column=12, sticky="e", padx=(6, 0))

        btn_all = ttk.Button(filter_frame, text="Marker alle", command=self._select_all_accounts)
        btn_all.grid(row=0, column=13, sticky="e", padx=(12, 0))

        btn_to_utvalg = ttk.Button(filter_frame, text="Til utvalg", command=self._send_selected_to_utvalg)
        btn_to_utvalg.grid(row=0, column=14, sticky="e", padx=(6, 0))


        btn_motpost = ttk.Button(filter_frame, text="Motpost", command=self._open_motpost)
        btn_motpost.grid(row=0, column=16, sticky="e", padx=(6, 0))

        btn_override = ttk.Button(filter_frame, text="Overstyring", command=self._open_override_checks)
        btn_override.grid(row=0, column=15, sticky="e", padx=(6, 0))

        # allow the right side to expand
        filter_frame.grid_columnconfigure(16, weight=1)

        # Main split
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)

        ttk.Label(main, text="Pivot pr. konto").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(main, text="Transaksjoner").grid(row=0, column=1, sticky="w", pady=(0, 4))

        # Pivot tree
        pivot_frame = ttk.Frame(main)
        pivot_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        pivot_frame.grid_rowconfigure(0, weight=1)
        pivot_frame.grid_columnconfigure(0, weight=1)

        self._pivot_tree = ttk.Treeview(pivot_frame, columns=self.PIVOT_COLS, show="headings", selectmode="extended")
        for col, w in zip(self.PIVOT_COLS, (90, 220, 110, 70)):
            anchor = "e" if col in ("Sum", "Antall") else "w"
            self._pivot_tree.heading(col, text=col)
            self._pivot_tree.column(col, width=w, anchor=anchor)
        self._pivot_tree.grid(row=0, column=0, sticky="nsew")

        sb_pivot = ttk.Scrollbar(pivot_frame, orient="vertical", command=self._pivot_tree.yview)
        sb_pivot.grid(row=0, column=1, sticky="ns")
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

        ttk.Button(
            hdr_tx,
            text="Bilagsdrill",
            command=self._open_bilag_drilldown_from_tx_selection,
        ).grid(row=0, column=1, sticky="e", padx=(6, 0))


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
        # Headless: just keep dataset pointer updated.
        if not self._tk_ok:
            return

        if self.dataset is None or not isinstance(self.dataset, pd.DataFrame):
            self._df_filtered = None
            self._clear_tree(self._pivot_tree)
            self._clear_tree(self._tx_tree)
            if self._lbl_tx_summary is not None:
                self._lbl_tx_summary.config(text="Oppsummering: (ingen rader)")
            return

        search = (self._var_search.get() or "").strip()
        direction_label = self._var_direction.get()
        direction = next((o.value for o in _DIR_OPTIONS if o.label == direction_label), None)
        min_amount = self._safe_float(self._var_min.get())
        max_amount = self._safe_float(self._var_max.get())

        # kontoserier: if none selected => no kontoserie-filter
        kontoserier = [i for i, v in enumerate(self._series_vars) if v.get()]
        kontoserier_arg = kontoserier if kontoserier else None

        df_f = filter_dataset(
            self.dataset,
            search=search,
            direction=direction,
            min_amount=min_amount,
            max_amount=max_amount,
            abs_amount=False,
            kontoserier=kontoserier_arg,
        )

        # Normalise Konto for safe selection/filtering.
        if "Konto" in df_f.columns:
            df_f = df_f.copy()
            df_f["Konto"] = df_f["Konto"].map(konto_to_str)

        self._df_filtered = df_f
        self._refresh_pivot()
        self._refresh_transactions_view()

    @staticmethod
    def _safe_float(s: str) -> Optional[float]:
        try:
            s2 = (s or "").strip()
            if not s2:
                return None
            return float(s2.replace(" ", "").replace(",", "."))
        except Exception:
            return None

    @staticmethod
    def _clear_tree(tree: Optional[ttk.Treeview]) -> None:
        if tree is None:
            return
        for item in tree.get_children(""):
            tree.delete(item)

    # ---------------------------------------------------------------------
    # Pivot + transactions
    # ---------------------------------------------------------------------

    def _refresh_pivot(self) -> None:
        if self._pivot_tree is None:
            return

        self._clear_tree(self._pivot_tree)
        if self._df_filtered is None or self._df_filtered.empty:
            return

        pivot_df = build_pivot_by_account(self._df_filtered)
        # Expect columns: Konto, Kontonavn, Sum beløp, Antall bilag
        for _, row in pivot_df.iterrows():
            konto = konto_to_str(row.get("Konto", ""))
            navn = str(row.get("Kontonavn", "") or "")
            sum_val = row.get("Sum beløp", 0.0)
            cnt_val = row.get("Antall bilag", 0)

            sum_txt = formatting.fmt_amount(sum_val)
            cnt_txt = formatting.format_int_no(cnt_val)

            self._pivot_tree.insert("", "end", values=(konto, navn, sum_txt, cnt_txt))

    def _select_all_accounts(self) -> None:
        if self._pivot_tree is None:
            return
        items = self._pivot_tree.get_children("")
        self._pivot_tree.selection_set(items)
        self._refresh_transactions_view()

    def _get_selected_accounts(self) -> List[str]:
        if self._pivot_tree is None:
            return []
        accounts: List[str] = []
        # Brukeren forventer ofte at "Til utvalg" tar med alle synlige konti når
        # det ikke er gjort eksplisitt rad-markering.
        selected = self._pivot_tree.selection()
        if not selected:
            selected = self._pivot_tree.get_children()

        for item in selected:
            konto = konto_to_str(self._pivot_tree.set(item, "Konto"))
            if konto:
                accounts.append(konto)
        # de-dupe while preserving order
        seen = set()
        unique: List[str] = []
        for a in accounts:
            if a not in seen:
                unique.append(a)
                seen.add(a)
        return unique

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

        if "Konto" not in self._df_filtered.columns:
            self._lbl_tx_summary.config(text="Oppsummering: (mangler Konto-kolonne)")
            return

        df_sel_all = self._df_filtered[self._df_filtered["Konto"].isin(sel_accounts)].copy()

        # Totals for full selection
        bel_all = pd.to_numeric(df_sel_all.get("Beløp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        total_rows = len(df_sel_all)
        total_sum = float(bel_all.sum())

        # Display subset
        max_rows = int(self._var_max_rows.get() or 200)
        if max_rows <= 0:
            max_rows = 200
        df_show = df_sel_all.head(max_rows)
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

        # Column fallbacks
        def _get_kunder(r: pd.Series) -> str:
            for c in ("Kunder", "Kundenavn", "Kunde", "Leverandør", "Motpart"):
                if c in r.index:
                    v = r.get(c)
                    if v is not None and str(v).strip() != "":
                        return str(v)
            return ""

        for _, row in df_show.iterrows():
            bilag = konto_to_str(row.get("Bilag", ""))
            belop_val = row.get("Beløp", "")
            belop_txt = formatting.fmt_amount(belop_val)
            tekst = str(row.get("Tekst", "") or "")
            kunder = _get_kunder(row)
            konto = konto_to_str(row.get("Konto", ""))
            kontonavn = str(row.get("Kontonavn", "") or "")
            dato_txt = formatting.fmt_date(row.get("Dato", ""))

            tags = ()
            try:
                if float(pd.to_numeric(belop_val, errors="coerce")) < 0:
                    tags = ("neg",)
            except Exception:
                pass

            self._tx_tree.insert(
                "",
                "end",
                values=(bilag, belop_txt, tekst, kunder, konto, kontonavn, dato_txt),
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
        # Prefer Treeview-set på kolonnenavn
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
        """Åpne bilagsdrill basert på valgt transaksjon i listen."""
        bilag = self._get_selected_bilag_from_tx_tree()
        if not bilag:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Bilagsdrill", "Velg en transaksjon i listen først.")
                except Exception:
                    pass
            return
        self._open_bilag_drilldown_for_bilag(bilag)


    # ---------------------------------------------------------------------
    # Motpostanalyse (Analyse -> Motpost)
    # ---------------------------------------------------------------------

    def _open_motpost(self) -> None:
        """Åpne en enkel motpostanalyse for valgte kontoer.

        Prinsipp:
        - Bruk *gjeldende filter* for å finne hvilke bilag som inngår (scope)
        - Når bilagene er identifisert, hentes alle linjer for disse bilagene
          fra full datasett slik at motposter alltid blir med.
        """

        accounts = self._get_selected_accounts()
        if not accounts:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost", "Velg minst én konto i pivot-listen først.")
                except Exception:
                    pass
            return

        # Fullt datasett
        df_all: Optional[pd.DataFrame] = None
        if isinstance(getattr(self, "dataset", None), pd.DataFrame):
            df_all = self.dataset
        if df_all is None or df_all.empty:
            if isinstance(getattr(session, "dataset", None), pd.DataFrame):
                df_all = session.dataset

        if df_all is None or df_all.empty:
            if messagebox is not None:
                try:
                    messagebox.showerror("Motpost", "Fant ingen datasett (dataset) å analysere.")
                except Exception:
                    pass
            return

        # Minimumskrav
        required_cols = {"Bilag", "Konto", "Beløp"}
        missing = [c for c in required_cols if c not in df_all.columns]
        if missing:
            if messagebox is not None:
                try:
                    messagebox.showerror(
                        "Motpost",
                        "Datasettet mangler nødvendige kolonner: " + ", ".join(missing),
                    )
                except Exception:
                    pass
            return

        df_filtered = self._df_filtered if isinstance(getattr(self, "_df_filtered", None), pd.DataFrame) else None
        df_scope_source = df_filtered if df_filtered is not None and not df_filtered.empty else df_all

        accounts_set = set(accounts)
        konto_norm = df_scope_source["Konto"].map(konto_to_str)
        mask_sel = konto_norm.isin(accounts_set)

        bilag_keys = (
            df_scope_source.loc[mask_sel, "Bilag"]
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .replace({"nan": "", "None": ""})
        )
        bilag_list = [b for b in bilag_keys.unique().tolist() if b]

        if not bilag_list:
            if messagebox is not None:
                try:
                    messagebox.showinfo(
                        "Motpost",
                        "Fant ingen bilag for valgte kontoer i gjeldende filter.",
                    )
                except Exception:
                    pass
            return

        # Scope-datasett: alle linjer for scope-bilagene fra full datasett
        bilag_all = (
            df_all["Bilag"]
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .replace({"nan": "", "None": ""})
        )
        df_scope = df_all.loc[bilag_all.isin(set(bilag_list))].copy()

        if df_scope.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Motpost", "Fant ingen transaksjoner i scope for valgt(e) bilag.")
                except Exception:
                    pass
            return

        if _show_motpost_konto is None:
            if messagebox is not None:
                try:
                    messagebox.showerror("Motpost", "Motpostanalyse er ikke tilgjengelig (mangler GUI-støtte).")
                except Exception:
                    pass
            return

        try:
            _show_motpost_konto(master=self, df_transactions=df_scope, konto_list=accounts)
        except Exception as e:
            if messagebox is not None:
                try:
                    messagebox.showerror("Motpost", f"Kunne ikke åpne motpostanalyse.\n\n{e}")
                except Exception:
                    pass



    # ---------------------------------------------------------------------
    # Transaksjonsanalyser (overstyring av kontroller)
    # ---------------------------------------------------------------------

    def _open_override_checks(self) -> None:
        """Åpne transaksjonsanalyser for revisjonsrisiko – ledelsens overstyring."""
        # Fullt datasett
        df_all: Optional[pd.DataFrame] = None
        if isinstance(getattr(self, "dataset", None), pd.DataFrame):
            df_all = self.dataset
        if df_all is None or df_all.empty:
            if isinstance(getattr(session, "dataset", None), pd.DataFrame):
                df_all = session.dataset

        if df_all is None or df_all.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Transaksjonsanalyser", "Ingen datasett lastet.")
                except Exception:
                    pass
            return

        # Scope (valgte kontoer / gjeldende filter) brukes kun til markering i drilldown
        df_scope: Optional[pd.DataFrame] = None
        try:
            if isinstance(getattr(self, "_df_filtered", None), pd.DataFrame) and not self._df_filtered.empty:
                df_scope = self._df_filtered
        except Exception:
            df_scope = None

        # Prøv å hente Columns-mapping (hvis satt av importen)
        cols_obj = None
        try:
            _df_sess, cols_obj = session.get_dataset()
        except Exception:
            cols_obj = None

        try:
            from views_override_checks import open_override_checks_popup
        except Exception as e:
            if messagebox is not None:
                try:
                    messagebox.showerror("Transaksjonsanalyser", f"Kunne ikke laste modul for transaksjonsanalyser:\n{e}")
                except Exception:
                    pass
            return

        try:
            open_override_checks_popup(self, df_all=df_all, df_scope=df_scope, cols=cols_obj)
        except Exception as e:
            if messagebox is not None:
                try:
                    messagebox.showerror("Transaksjonsanalyser", f"Kunne ikke åpne analysevindu.\n\n{e}")
                except Exception:
                    pass
            return


    def _open_bilag_drilldown_for_bilag(self, bilag_value: str) -> None:
        """Åpne bilagsdrill for gitt bilag.

        - df_base: transaksjoner for valgte kontoer (markeres som "I kontoutvalg")
        - df_all: hele datasettet (slik at motposter kommer med)
        """
        if _open_bilag_drill_dialog is None:
            if messagebox is not None:
                try:
                    messagebox.showinfo(
                        "Bilagsdrill",
                        "Bilagsdrill er ikke tilgjengelig (mangler selection_studio_drill).",
                    )
                except Exception:
                    pass
            return

        df_all = self.dataset if isinstance(self.dataset, pd.DataFrame) else None
        df_filtered = self._df_filtered if isinstance(self._df_filtered, pd.DataFrame) else None

        if df_all is None:
            df_all = df_filtered
        if df_filtered is None:
            df_filtered = df_all

        if df_all is None or df_filtered is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
            if messagebox is not None:
                try:
                    messagebox.showinfo("Bilagsdrill", "Ingen data tilgjengelig for drilldown.")
                except Exception:
                    pass
            return

        df_base = df_filtered
        try:
            sel_accounts = self._get_selected_accounts()
        except Exception:
            sel_accounts = []

        if sel_accounts and "Konto" in df_filtered.columns:
            df_base = df_filtered[df_filtered["Konto"].isin(sel_accounts)].copy()
            if df_base.empty:
                df_base = df_filtered

        # Kjør dialogen – robust mot flere signaturvarianter (bakoverkompat)
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
            if messagebox is not None:
                try:
                    messagebox.showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
                except Exception:
                    pass
            return

        # Eldre aliaser (historiske kall)
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
            if messagebox is not None:
                try:
                    messagebox.showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
                except Exception:
                    pass
            return

        # Eldste signatur (posisjonelle)
        try:
            _open_bilag_drill_dialog(self, df_base, df_all, bilag_value)
        except Exception as e:
            if messagebox is not None:
                try:
                    messagebox.showerror("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
                except Exception:
                    pass

    # ---------------------------------------------------------------------
    # Selection -> Utvalg
    # ---------------------------------------------------------------------

    def _send_to_selection(self, accounts: List[str]) -> None:
        """Internal helper for tests + callback-based wiring."""
        if self._utvalg_callback is not None:
            self._utvalg_callback(accounts)

    def _send_selected_to_utvalg(self) -> None:
        accounts = self._get_selected_accounts()
        if not accounts:
            if self._lbl_tx_summary is not None:
                self._lbl_tx_summary.config(text="Ingen kontoer valgt.")
            return
        self._send_to_selection(accounts)


    def _prepare_transactions_export_sheets(self) -> dict[str, pd.DataFrame]:
        """Bygger ark-map for eksport av transaksjoner.

        - Valgfritt: begrenser til valgte kontoer (dersom _get_selected_accounts finnes)
        - Slår sammen kunde-kolonner til en felles kolonne: "Kunder"
        - Parser dato robust for blandede formater (norsk + ISO) uten FutureWarning
        """
        df = getattr(self, "_df_filtered", None)
        if df is None or df.empty:
            return {"Transaksjoner": pd.DataFrame()}

        out = df.copy()

        # Begrens til valgte kontoer (dersom metoden finnes)
        try:
            selected_accounts = list(self._get_selected_accounts())
        except Exception:
            selected_accounts = []
        if selected_accounts and "Konto" in out.columns:
            selected_accounts_s = {str(x) for x in selected_accounts}
            out = out[out["Konto"].astype(str).isin(selected_accounts_s)].copy()

        # Kunder: slå sammen "Kundenavn" og "Kunde" -> "Kunder"
        def _clean_customer(s: pd.Series) -> pd.Series:
            s = s.fillna("").astype("string").str.strip()
            return s.replace({"nan": ""})

        if any(c in out.columns for c in ("Kunder", "Kunde", "Kundenavn")):
            if "Kunder" in out.columns:
                kunder = _clean_customer(out["Kunder"])
            else:
                s_name = _clean_customer(out["Kundenavn"]) if "Kundenavn" in out.columns else pd.Series([""] * len(out), index=out.index, dtype="string")
                s_kunde = _clean_customer(out["Kunde"]) if "Kunde" in out.columns else pd.Series([""] * len(out), index=out.index, dtype="string")
                # Preferer kundenavn hvis tilgjengelig, ellers kunde
                kunder = s_name.where(s_name != "", s_kunde)
            out["Kunder"] = kunder

            drop_cols = [c for c in ("Kundenavn", "Kunde") if c in out.columns]
            if drop_cols:
                out = out.drop(columns=drop_cols)

        # Dato: robust parsing for blandede formater (dd.mm.yyyy + yyyy-mm-dd)
        if "Dato" in out.columns:
            ser = out["Dato"]
            ser_str = ser.astype("string").fillna("").str.strip()

            # Pre-alloker strengkolonne
            out_dato = pd.Series([""] * len(out), index=out.index, dtype="object")

            mask_no = ser_str.str.match(r"^\d{2}\.\d{2}\.\d{4}$")
            if mask_no.any():
                dt_no = pd.to_datetime(ser_str[mask_no], format="%d.%m.%Y", errors="coerce")
                out_dato.loc[mask_no] = dt_no.dt.strftime("%d.%m.%Y").fillna("")

            mask_iso = ser_str.str.match(r"^\d{4}-\d{2}-\d{2}$")
            if mask_iso.any():
                dt_iso = pd.to_datetime(ser_str[mask_iso], format="%Y-%m-%d", errors="coerce")
                out_dato.loc[mask_iso] = dt_iso.dt.strftime("%d.%m.%Y").fillna("")

            # Fallback for andre formater: forsøk pandas-parser, men unngå FutureWarning
            mask_rest = (~mask_no) & (~mask_iso) & (ser_str != "")
            if mask_rest.any():
                import warnings

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=FutureWarning)
                    dt_rest = pd.to_datetime(ser_str[mask_rest], errors="coerce", dayfirst=True)

                formatted = dt_rest.dt.strftime("%d.%m.%Y")
                # Behold original hvis vi ikke klarer å parse
                out_dato.loc[mask_rest] = formatted.fillna(ser_str[mask_rest])

            out["Dato"] = out_dato

        # Max rader
        var_max = getattr(self, "_var_max_rows", None)
        try:
            max_rows = int(var_max.get())
        except Exception:
            try:
                max_rows = int(var_max)
            except Exception:
                max_rows = 200

        if max_rows > 0 and len(out) > max_rows:
            out = out.head(max_rows).copy()

        return {"Transaksjoner": out}


    def _prepare_pivot_export_sheets(self) -> dict[str, pd.DataFrame]:
        """Bygger ark-map for eksport av pivot-tabellen.

        Dersom siste pivot allerede er beregnet (_pivot_df_last), brukes den.
        """
        pivot_df = getattr(self, "_pivot_df_last", None)
        if pivot_df is None or getattr(pivot_df, "empty", True):
            pivot_df = self._build_pivot_df(getattr(self, "_df_filtered", pd.DataFrame()))

        try:
            import analyse_viewdata as av  # lokal import for å unngå sirkler
            sheet_name = av.SHEET_PIVOT
        except Exception:
            sheet_name = "Pivot pr konto"

        return {sheet_name: pivot_df}

