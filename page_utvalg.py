from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

try:
    import session  # type: ignore
except Exception:
    class session:  # type: ignore
        dataset = None

from io_utils import apply_kontoserie_filter
from views_virtual_transactions import VirtualTransactionsPanel

try:
    from views_selection_studio import SelectionStudio
except Exception:
    class SelectionStudio:  # stub
        def __init__(self, master, df, on_commit=None): 
            messagebox.showinfo("Stratifisering", "Stratifisering er ikke tilgjengelig i denne builden.")

try:
    from views_bilag_drill import BilagDrillDialog
except Exception:
    class BilagDrillDialog:  # stub
        def __init__(self, master, df, bilag_col="Bilag"): pass
        def preset_and_show(self, *_a, **_k):
            messagebox.showinfo("Bilagsdrill", "Bilagsdrill er ikke tilgjengelig i denne builden.")

try:
    from ui_loading import LoadingOverlay
except Exception:
    class LoadingOverlay:
        def __init__(self, *_a, **_k): pass
        def busy(self, *_a, **_k):
            class _C: 
                def __enter__(self_s): return None
                def __exit__(self_s, *e): return False
            return _C()

class UtvalgPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.loading = LoadingOverlay(self)
        self._df_all = pd.DataFrame()
        self._df_filtered = pd.DataFrame()
        self._visible_columns = []

        self._build_ui()
        self.after(300, self._autoload_from_session)

    def _build_ui(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=6, pady=6)
        ttk.Label(bar, text="Søk:").pack(side="left")
        self.var_search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_search, width=20).pack(side="left")

        ttk.Label(bar, text="Retning:").pack(side="left", padx=(8,0))
        self.var_dir = tk.StringVar(value="Alle")
        ttk.Combobox(bar, values=("Alle","Debet","Kredit"), textvariable=self.var_dir, width=8, state="readonly").pack(side="left")

        ttk.Label(bar, text="Kontoserier:").pack(side="left", padx=(8,0))
        self.var_series = {i: tk.BooleanVar(value=False) for i in range(1,9+1)}
        for i in range(1,9+1):
            ttk.Checkbutton(bar, text=str(i), variable=self.var_series[i], command=self.apply_filters).pack(side="left")

        ttk.Button(bar, text="Bruk filtre", command=self.apply_filters).pack(side="left", padx=(8,0))
        ttk.Button(bar, text="Til underpop/Stratifisering", command=self._open_studio).pack(side="left", padx=(8,0))

        self.lbl_sum = ttk.Label(self, text="Oppsummering: rader=0 | sum=0,00")
        self.lbl_sum.pack(anchor="w", padx=6)

        self.trans = VirtualTransactionsPanel(self, columns=["Bilag","Konto","Kontonavn","Dato","Beløp","Tekst"],
                                              display_limit=200, on_row_dblclick=self._open_drill)
        self.trans.pack(fill="both", expand=True, padx=6, pady=6)

    def _autoload_from_session(self):
        try:
            if getattr(session, "dataset", None) is None or len(session.dataset)==0:
                return
            df: pd.DataFrame = session.dataset.copy()
        except Exception:
            return
        base_cols = ["Bilag","Konto","Kontonavn","Dato","Beløp","Tekst",
                     "Kundenr","Kundenavn","Leverandørnr","Leverandørnavn","Valuta","Valutabeløp","MVA-kode","MVA-beløp","MVA-prosent"]
        self._visible_columns = [c for c in base_cols if c in df.columns] or list(df.columns[:10])
        self._df_all = df
        self.apply_filters()

    def apply_filters(self):
        with self.loading.busy("Filtrerer utvalg..."):
            df = self._df_all
            if df.empty:
                self.trans.set_dataframe(pd.DataFrame(), columns=self._visible_columns)
                self.lbl_sum.config(text="Oppsummering: rader=0 | sum=0,00")
                return
            q = self.var_search.get().strip().lower()
            if q:
                txtcols = [c for c in ("Tekst","Kontonavn") if c in df.columns]
                if txtcols:
                    mask = False
                    for c in txtcols:
                        mask = mask | df[c].astype(str).str.lower().str.contains(q, na=False)
                    df = df[mask]
            if "Beløp" in df.columns:
                bel = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
                dirv = self.var_dir.get()
                if dirv=="Debet": df = df[bel>0]
                elif dirv=="Kredit": df = df[bel<0]
            series = {i for i,var in self.var_series.items() if var.get()}
            if series:
                df = apply_kontoserie_filter(df, series, konto_col="Konto")

            self._df_filtered = df
            n = len(df)
            s = pd.to_numeric(df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()
            self.lbl_sum.config(text=f"Oppsummering: rader={n:,} | sum={s:,.2f}".replace(",", " ").replace(".", ","))
            self.trans.set_dataframe(df[self._visible_columns], columns=self._visible_columns)

    def _open_studio(self):
        if self._df_filtered.empty:
            messagebox.showinfo("Stratifisering", "Ingen rader i utvalg. Marker kontoer og/eller sett filtre først.")
            return
        def on_commit(sample_df: pd.DataFrame):
            self._df_filtered = sample_df.copy()
            n = len(sample_df)
            s = pd.to_numeric(sample_df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()
            self.lbl_sum.config(text=f"Oppsummering: rader={n:,} | sum={s:,.2f}".replace(",", " ").replace(".", ","))
            self.trans.set_dataframe(self._df_filtered[self._visible_columns], columns=self._visible_columns)
        try:
            SelectionStudio(self, self._df_filtered, on_commit=on_commit)
        except Exception:
            messagebox.showinfo("Stratifisering", "Stratifisering ikke tilgjengelig i denne builden.")

    def _open_drill(self, row):
        try:
            if row is None or "Bilag" not in self._df_all.columns:
                return
            dlg = BilagDrillDialog(self, self._df_all, bilag_col="Bilag")
            dlg.preset_and_show(row.get("Bilag",""))
        except Exception:
            messagebox.showinfo("Bilag", "Bilagsdrill ikke tilgjengelig i denne builden.")
