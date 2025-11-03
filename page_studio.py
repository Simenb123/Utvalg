# page_studio.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Set
import numpy as np
import pandas as pd

from session import get_dataset
from models import Columns
from formatting import fmt_amount, fmt_int, parse_amount
from excel_export import export_and_open

class StudioPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self.cols = Columns()
        self.acc: List[int] = []
        self.pop = pd.DataFrame()
        self.sample_ids: Set[str] = set()

        top = ttk.Frame(self, padding=8); top.pack(fill=tk.X)
        self.lbl_info = ttk.Label(top, text="Ingen kontoutvalg mottatt fra Analyse.")
        self.lbl_info.pack(side=tk.LEFT, padx=(0,10))

        ttk.Label(top, text="Min beløp:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(top, width=12); self.ent_min.pack(side=tk.LEFT, padx=(4,8))
        ttk.Label(top, text="Maks beløp:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(top, width=12); self.ent_max.pack(side=tk.LEFT, padx=(4,12))

        ttk.Label(top, text="Intervaller (kvantiler):").pack(side=tk.LEFT)
        self.cbo_n = ttk.Combobox(top, state="readonly", values=[0, 4, 5, 6, 8, 10], width=6)
        self.cbo_n.set(6); self.cbo_n.pack(side=tk.LEFT, padx=(4,12))
        ttk.Button(top, text="Oppdater", command=self._rebuild_pop).pack(side=tk.LEFT)

        frame = ttk.Frame(self); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(frame, columns=("range","rows","unique","sum"), show="headings")
        for cid, txt, w, anc in (("range","Beløpsintervall",280,"w"),("rows","Linjer",100,"e"),("unique","Unike bilag",120,"e"),("sum","Sum",140,"e")):
            self.tree.heading(cid, text=txt); self.tree.column(cid, width=w, anchor=anc)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview).pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(self, padding=8); bottom.pack(fill=tk.X)
        ttk.Label(bottom, text="Antall bilag:").pack(side=tk.LEFT)
        self.ent_n = ttk.Entry(bottom, width=6); self.ent_n.insert(0, "20"); self.ent_n.pack(side=tk.LEFT, padx=(6,12))
        ttk.Button(bottom, text="Trekk bilag", command=self._sample).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Eksporter og åpne Excel", command=self._export_open).pack(side=tk.RIGHT)

        self.lbl_status = ttk.Label(self, text=""); self.lbl_status.pack(fill=tk.X, padx=8, pady=(0,6))

    def refresh_from_session(self):
        pass

    def load_from_accounts(self, accounts: List[int]):
        self.acc = accounts or []
        self._rebuild_pop()

    def _rebuild_pop(self):
        df, c = get_dataset()
        if df is None or c is None:
            messagebox.showwarning("Utvalg/studio", "Ingen datasett i session."); return
        self.cols = c
        if not self.acc:
            self.pop = pd.DataFrame()
            self.lbl_info.config(text="Ingen kontoutvalg mottatt. Gå til Analyse og trykk «Til studio-fanen».")
            self._refresh_buckets(); return

        mask = df[c.konto].astype("Int64").astype(int).isin(self.acc)
        mn = parse_amount(self.ent_min.get().strip()) if self.ent_min.get().strip() else None
        mx = parse_amount(self.ent_max.get().strip()) if self.ent_max.get().strip() else None
        if mn is not None: mask &= df[c.belop] >= mn
        if mx is not None: mask &= df[c.belop] <= mx
        self.pop = df[mask].copy()
        self.lbl_info.config(text=f"Populasjon for konto {self.acc}: linjer={fmt_int(len(self.pop))} | sum={fmt_amount(self.pop[c.belop].sum())}")
        self._refresh_buckets()

    def _refresh_buckets(self):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        if self.pop.empty:
            self.lbl_status.config(text=""); return
        c = self.cols; s = self.pop[c.belop]
        try: n = int(self.cbo_n.get())
        except Exception: n = 0
        if n <= 0:
            self.tree.insert("", tk.END, values=("—", fmt_int(len(self.pop)), fmt_int(self.pop[c.bilag].astype(str).nunique()), fmt_amount(float(s.sum()))))
            self.lbl_status.config(text="Ingen stratifisering (Intervaller = 0)."); return

        qs = np.linspace(0, 1, n+1)
        edges = s.quantile(qs).to_list()
        for i in range(1, len(edges)):
            if edges[i] <= edges[i-1]: edges[i] = edges[i-1] + 0.01
        labels = [f"{fmt_amount(edges[i])} – {fmt_amount(edges[i+1])}" for i in range(n)]
        cats = pd.cut(s, bins=edges, include_lowest=True, labels=labels)
        tab = (self.pop.assign(Bucket=cats)
                      .groupby("Bucket")
                      .agg(Linjer=("Bucket","count"),
                           Unike=(c.bilag, lambda x: x.astype(str).nunique()),
                           Sum=(c.belop,"sum"))
                      .reset_index())
        for _, r in tab.iterrows():
            self.tree.insert("", tk.END, values=(r["Bucket"], fmt_int(int(r["Linjer"])), fmt_int(int(r["Unike"])), fmt_amount(float(r["Sum"]))))
        self.lbl_status.config(text=f"Stratifisering: {n} intervaller.")

    def _sample(self):
        if self.pop.empty:
            messagebox.showinfo("Trekk", "Ingen populasjon."); return
        c = self.cols
        unike = self.pop[c.bilag].dropna().astype(str).drop_duplicates()
        if unike.empty:
            messagebox.showwarning("Bilag", "Fant ingen bilagsnummer."); return
        try: n = max(1, min(int(self.ent_n.get()), len(unike)))
        except Exception: n = min(20, len(unike))
        self.sample_ids = set(unike.sample(n=n, random_state=None).tolist())
        ant_rader = (self.pop[c.bilag].astype(str).isin(self.sample_ids)).sum()
        self.lbl_status.config(text=f"Trekk klart: {n} bilag | linjer i utvalg: {fmt_int(int(ant_rader))}.")

    def _export_open(self):
        if self.pop.empty or not self.sample_ids:
            messagebox.showinfo("Eksport", "Trekk bilag først."); return
        df, c = get_dataset()
        if df is None or c is None: return
        fullt = df[df[c.bilag].astype(str).isin(self.sample_ids)].copy()
        inter = fullt[fullt[c.konto].astype("Int64").astype(int).isin(self.acc)].copy()
        summer = (inter.groupby(c.bilag)[c.belop]
                        .agg(Sum_i_valgte_kontoer="sum", Linjer_i_valgte_kontoer="count")
                        .reset_index())
        export_and_open({
            "Fullt_bilagsutvalg": fullt,
            "Kun_valgte_kontoer": inter,
            "Bilag_summer": summer,
        }, prefer_date_cols={c.dato} if getattr(c, "dato", "") and c.dato in fullt.columns else set(),
           prefer_amount_cols={c.belop})
