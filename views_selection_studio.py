
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Tuple
import pandas as pd
import numpy as np

from io_utils import ensure_abs_belop
from excel_export import export_strata_and_sample

class SelectionStudio(tk.Toplevel):
    """Veiviser for Delutvalg & Stratifisering.
    Input: filtrert utvalgs-DF. Viser grunnlag, lager strata og trekker sample.
    """
    def __init__(self, master, df: pd.DataFrame, on_commit=None):
        super().__init__(master)
        self.title("Delutvalg og stratifisering")
        self.geometry("1200x750")
        self.on_commit = on_commit
        self.df_base = df.copy()
        self.df_work = self.df_base.copy()  # etter lokale filtre
        self.df_sample = pd.DataFrame()

        # -- venstre kontrollpanel (steg)
        left = ttk.Frame(self)
        left.pack(side="left", fill="y", padx=6, pady=6)

        ttk.Label(left, text="Steg 1: Filtre (grunnlag)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0,2))
        self.var_dir = tk.StringVar(value="Alle")
        ttk.Label(left, text="Retning:").pack(anchor="w")
        ttk.Combobox(left, values=("Alle","Debet","Kredit"), textvariable=self.var_dir, width=12, state="readonly").pack(anchor="w")

        ttk.Label(left, text="Beløp fra/til:").pack(anchor="w", pady=(6,0))
        self.var_min = tk.StringVar(value="")
        self.var_max = tk.StringVar(value="")
        rowb = ttk.Frame(left); rowb.pack(anchor="w")
        ttk.Entry(rowb, textvariable=self.var_min, width=10).pack(side="left")
        ttk.Label(rowb, text=" til ").pack(side="left")
        ttk.Entry(rowb, textvariable=self.var_max, width=10).pack(side="left")
        self.var_abs = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Bruk absolutt beløp", variable=self.var_abs).pack(anchor="w", pady=(4,6))
        ttk.Button(left, text="Oppdater grunnlag", command=self._apply_base_filters).pack(anchor="w")

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=8)

        ttk.Label(left, text="Steg 2: Stratifisering", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0,2))
        self.var_mode = tk.StringVar(value="quantile")
        ttk.Combobox(left, values=("quantile","equal"), textvariable=self.var_mode, width=12, state="readonly").pack(anchor="w")
        ttk.Label(left, text="Antall strata (k):").pack(anchor="w", pady=(6,0))
        self.var_k = tk.IntVar(value=5)
        ttk.Spinbox(left, from_=2, to=50, textvariable=self.var_k, width=6).pack(anchor="w")

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=8)

        ttk.Label(left, text="Steg 3: Trekk", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0,2))
        ttk.Label(left, text="N per stratum:").pack(anchor="w")
        self.var_n = tk.IntVar(value=5)
        ttk.Spinbox(left, from_=1, to=1000, textvariable=self.var_n, width=6).pack(anchor="w")
        ttk.Label(left, text="Seed:").pack(anchor="w", pady=(6,0))
        self.var_seed = tk.IntVar(value=42)
        ttk.Spinbox(left, from_=0, to=10_000, textvariable=self.var_seed, width=8).pack(anchor="w", pady=(0,6))
        rowt = ttk.Frame(left); rowt.pack(anchor="w", pady=(4,0))
        ttk.Button(rowt, text="Forhåndsvis", command=self._build_and_sample).pack(side="left")
        ttk.Button(rowt, text="Legg i utvalg", command=self._commit).pack(side="left", padx=6)
        ttk.Button(rowt, text="Eksporter Excel", command=self._export_excel).pack(side="left")

        # -- høyre: strata + sample tabeller
        right = ttk.Frame(self); right.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        # status
        self.lbl_base = ttk.Label(right, text="Grunnlag: 0 rader | Sum: 0")
        self.lbl_base.pack(anchor="w")

        # strata
        ttk.Label(right, text="Strata (for valgt grunnlag)").pack(anchor="w", pady=(6,2))
        self.tree_strata = ttk.Treeview(right, show="headings", height=8)
        self.tree_strata.pack(fill="x")
        self.tree_strata["columns"] = ("Stratum","N","SumBeløp","Min","Median","Max","Intervall")
        for c, w in zip(self.tree_strata["columns"], (70,80,120,100,100,100,220)):
            self.tree_strata.heading(c, text=c); self.tree_strata.column(c, width=w, stretch=(c=="Intervall"))
        # sample
        ttk.Label(right, text="Trekk (samlet)").pack(anchor="w", pady=(8,2))
        self.tree_sample = ttk.Treeview(right, show="headings")
        self.tree_sample.pack(fill="both", expand=True)
        self._base_summary()
        self._build_and_sample()

    # helpers
    def _apply_base_filters(self):
        df = self.df_base.copy()
        s = ensure_abs_belop(df, "Beløp") if self.var_abs.get() else pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
        # retning
        dirv = self.var_dir.get()
        if dirv == "Debet":
            df = df[s > 0]
            s = s.loc[df.index]
        elif dirv == "Kredit":
            df = df[s < 0] if not self.var_abs.get() else df[pd.to_numeric(df["Beløp"], errors="coerce") < 0]
            s = s.loc[df.index]
        # beløpsintervall
        try:
            vmin = float(str(self.var_min.get()).replace(" ", "").replace(",", ".") or "nan")
        except Exception:
            vmin = float("nan")
        try:
            vmax = float(str(self.var_max.get()).replace(" ", "").replace(",", ".") or "nan")
        except Exception:
            vmax = float("nan")
        if not np.isnan(vmin):
            df = df[s >= (abs(vmin) if self.var_abs.get() else vmin)]
            s = s.loc[df.index]
        if not np.isnan(vmax):
            df = df[s <= (abs(vmax) if self.var_abs.get() else vmax)]
            s = s.loc[df.index]

        self.df_work = df
        self._base_summary()

    def _base_summary(self):
        N = len(self.df_work)
        S = pd.to_numeric(self.df_work["Beløp"], errors="coerce").fillna(0.0).sum()
        self.lbl_base.config(text=f"Grunnlag: {N:,} rader | Sum: {S:,.2f}".replace(",", " ").replace(".", ","))

    def _build_and_sample(self):
        df = self.df_work
        if len(df) == 0:
            # Clear views
            self.tree_strata.delete(*self.tree_strata.get_children())
            self.tree_sample.delete(*self.tree_sample.get_children())
            return

        s = ensure_abs_belop(df, "Beløp") if self.var_abs.get() else pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
        k = max(2, int(self.var_k.get()))
        mode = self.var_mode.get()

        # Lag strata‑etiketter
        if mode == "equal":
            cats = pd.cut(s, bins=k, duplicates="drop")
        else:
            cats = pd.qcut(s.rank(method="first"), q=k, labels=False)  # robust mot duplikater
            # map til intervaller for visning
            edges = np.quantile(s, q=np.linspace(0,1,k+1))
            # konstruer Categorical med intervall‑tekst
            bins = pd.IntervalIndex.from_breaks(edges, closed="both")
            # cats_qcut = pd.cut(s, bins=bins, include_lowest=True)
            # Men behold like store grupper ved å bruke rank‑qcut‑etiketter
            cats = pd.Categorical.from_codes(cats, categories=[str(b) for b in bins], ordered=True)

        df_strata = df.copy()
        df_strata["__stratum__"] = cats.astype(str)
        g = df_strata.groupby("__stratum__", observed=True)
        summary = g["Beløp"].agg(N="count", SumBeløp="sum", Min="min", Median="median", Max="max").reset_index().rename(columns={"__stratum__":"Stratum"})
        # vis strata
        self.tree_strata.delete(*self.tree_strata.get_children())
        for _, r in summary.iterrows():
            self.tree_strata.insert("", "end", values=[r["Stratum"], r["N"], f"{r['SumBeløp']:.2f}".replace(".", ","), f"{r['Min']:.2f}".replace(".", ","), f"{r['Median']:.2f}".replace(".", ","), f"{r['Max']:.2f}".replace(".", ","), r["Stratum"]])

        # Sample n per stratum
        n = max(1, int(self.var_n.get()))
        rng = np.random.default_rng(int(self.var_seed.get()))
        parts = []
        for key, grp in g:
            if len(grp) == 0:
                continue
            take = min(n, len(grp))
            idx = rng.choice(grp.index.values, size=take, replace=False)
            parts.append(df_strata.loc[idx])
        sample = pd.concat(parts, axis=0) if parts else df_strata.iloc[0:0]
        sample = sample.drop(columns=["__stratum__"], errors="ignore")
        self.df_sample = sample

        # vis sample (begrens kolonner for oversikt)
        self.tree_sample.delete(*self.tree_sample.get_children())
        cols = ["Bilag","Konto","Kontonavn","Dato","Beløp","Tekst"]
        cols = [c for c in cols if c in sample.columns]
        # legg til Stratum for visning (beregnes igjen)
        sample2 = df_strata.loc[sample.index, ["__stratum__"]].join(sample[cols])
        viscols = ["Bilag"] + [c for c in cols if c!="Bilag"] + ["__stratum__"]
        self.tree_sample["columns"] = tuple(viscols)
        for c in viscols:
            self.tree_sample.heading(c, text=("Stratum" if c=="__stratum__" else c))
            self.tree_sample.column(c, width=120, stretch=True)
        for _, r in sample2.iterrows():
            self.tree_sample.insert("", "end", values=[r.get(c, "") for c in viscols])

    def _commit(self):
        if self.on_commit and not self.df_sample.empty:
            self.on_commit(self.df_sample)
            self.destroy()

    def _export_excel(self):
        if self.df_sample.empty:
            messagebox.showinfo("Eksporter", "Ingen rader i trekk.")
            return
        p = filedialog.asksaveasfilename(title="Lagre Excel", defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")])
        if not p:
            return
        # bygg strata df på nytt fra GUI-tabell
        cols = ["Stratum","N","SumBeløp","Min","Median","Max","Intervall"]
        rows = []
        for iid in self.tree_strata.get_children():
            rows.append([self.tree_strata.set(iid, c) for c in cols])
        strata_df = pd.DataFrame(rows, columns=cols)
        export_strata_and_sample(p, strata_df, self.df_sample)
