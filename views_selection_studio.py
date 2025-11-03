from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Sequence
import pandas as pd
import numpy as np

from session import get_dataset
from models import Columns
from formatting import fmt_amount, fmt_int, parse_amount, fmt_date
from export_utils import export_selection_to_excel

class SelectionStudio(ttk.Frame):
    """
    Segmentering/kvantiler + trekk/eksport.
    Brukes som fane i hovedvinduet.
    """
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self.df: Optional[pd.DataFrame] = None
        self.cols: Optional[Columns] = None
        self._accounts: Optional[Sequence[int]] = None

        self._build()

    def _build(self):
        # Filterlinje
        filt = ttk.Frame(self, padding=8); filt.pack(fill=tk.X)
        ttk.Label(filt, text="Retning:").pack(side=tk.LEFT)
        self.var_dir = tk.StringVar(value="Alle")
        self.cbo_dir = ttk.Combobox(filt, state="readonly", values=["Alle","Debet","Kredit"], width=8, textvariable=self.var_dir)
        self.cbo_dir.pack(side=tk.LEFT, padx=(6,12))
        ttk.Label(filt, text="Min beløp:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(filt, width=12); self.ent_min.pack(side=tk.LEFT, padx=(4,6))
        ttk.Label(filt, text="Maks beløp:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(filt, width=12); self.ent_max.pack(side=tk.LEFT, padx=(4,12))
        ttk.Button(filt, text="Oppdater", command=self.refresh).pack(side=tk.LEFT, padx=(4,12))

        self.pop_lbl = ttk.Label(filt, text="Populasjon = 0 linjer | sum 0,00"); self.pop_lbl.pack(side=tk.LEFT, padx=12)

        # Segmenttabel – venstre
        split = ttk.Panedwindow(self, orient=tk.HORIZONTAL); split.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        left = ttk.Frame(split); split.add(left, weight=2)
        cfg = ttk.Frame(left); cfg.pack(fill=tk.X)
        ttk.Label(cfg, text="Kvantiler:").pack(side=tk.LEFT)
        self.cbo_bins = ttk.Combobox(cfg, state="readonly", width=10, values=["Ingen", 2,3,4,5,6,8,10])
        self.cbo_bins.set("Ingen"); self.cbo_bins.pack(side=tk.LEFT, padx=(6,12))
        ttk.Button(cfg, text="Bygg kvantiler", command=self.refresh).pack(side=tk.LEFT)

        self.tree_seg = ttk.Treeview(left, columns=("seg","linjer","sum"), show="headings", selectmode="browse")
        for c, t, w, a in (("seg","Segment",300,"w"),("linjer","Linjer",80,"e"),("sum","Sum",140,"e")):
            self.tree_seg.heading(c, text=t); self.tree_seg.column(c, width=w, anchor=a)
        self.tree_seg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(left, orient="vertical", command=self.tree_seg.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_seg.bind("<<TreeviewSelect>>", lambda _e: self._fill_transactions())

        # Transaksjoner – høyre
        right = ttk.Frame(split); split.add(right, weight=5)
        self.tree_tx = ttk.Treeview(right, columns=("dato","bilag","tekst","belop","konto","navn"), show="headings")
        for c, t, w, a in (("dato","Dato",90,"w"),("bilag","Bilag",120,"w"),("tekst","Tekst",380,"w"),("belop","Beløp",120,"e"),("konto","Konto",80,"e"),("navn","Kontonavn",220,"w")):
            self.tree_tx.heading(c, text=t); self.tree_tx.column(c, width=w, anchor=a)
        self.tree_tx.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(right, orient="vertical", command=self.tree_tx.yview).pack(side=tk.RIGHT, fill=tk.Y)

        # Bunn – trekk/eksport
        bottom = ttk.Frame(self, padding=8); bottom.pack(fill=tk.X)
        ttk.Label(bottom, text="Antall bilag:").pack(side=tk.LEFT)
        self.ent_n = ttk.Entry(bottom, width=6); self.ent_n.insert(0, "20"); self.ent_n.pack(side=tk.LEFT, padx=(6,12))
        self.var_per_bucket = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text="Trekk pr. bøtte (kvantil)", variable=self.var_per_bucket).pack(side=tk.LEFT)

        ttk.Label(bottom, text="Seed:").pack(side=tk.LEFT, padx=(12,0))
        self.ent_seed = ttk.Entry(bottom, width=8); self.ent_seed.pack(side=tk.LEFT, padx=(6,12))

        ttk.Button(bottom, text="Trekk bilag", command=self._do_sample).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Eksporter til Excel (åpne)", command=self._export).pack(side=tk.RIGHT)

    # ---------- API fra Analyse ----------
    def set_accounts(self, accounts):
        self._accounts = list(accounts) if accounts else None
        self.refresh()

    # ---------- core ----------
    def _get_filtered(self) -> pd.DataFrame:
        df, cols = get_dataset()
        if df is None or cols is None:
            return pd.DataFrame()
        self.df, self.cols = df, cols
        c = cols
        out = df
        # konto-subset
        if self._accounts:
            out = out[out[c.konto].astype("Int64").isin(self._accounts)]
        # retning
        dir_sel = (self.cbo_dir.get() or "Alle").lower()
        if dir_sel.startswith("debet"):
            out = out[out[c.belop] > 0]
        elif dir_sel.startswith("kredit"):
            out = out[out[c.belop] < 0]
        # beløpsintervall
        mn = parse_amount(self.ent_min.get() or None)
        mx = parse_amount(self.ent_max.get() or None)
        if mn is not None:
            out = out[out[c.belop] >= mn]
        if mx is not None:
            out = out[out[c.belop] <= mx]
        return out.copy()

    def refresh(self):
        df = self._get_filtered()
        c = self.cols
        for iid in self.tree_seg.get_children(): self.tree_seg.delete(iid)
        for iid in self.tree_tx.get_children(): self.tree_tx.delete(iid)
        self.pop_lbl.config(text=f"Populasjon = {len(df):,} linjer | sum {fmt_amount(df[c.belop].sum() if c else 0)}")
        if df.empty or c is None:
            return

        # kvantiler
        nb = self.cbo_bins.get()
        nb = int(nb) if (isinstance(nb, str) and nb.isdigit()) else (nb if isinstance(nb, int) else 0)

        # hovedsegment (alt)
        self.tree_seg.insert("", tk.END, iid="__ALL__", values=("Populasjon", fmt_int(len(df)), fmt_amount(float(df[c.belop].sum()))))

        self._df_cache = {"__ALL__": df}
        if nb and nb > 0:
            qs = np.linspace(0, 1, nb+1)
            edges = df[c.belop].quantile(qs).to_list()
            for i in range(1, len(edges)):
                if edges[i] <= edges[i-1]:
                    edges[i] = edges[i-1] + 0.01
            labels = [f"{fmt_amount(edges[i])} – {fmt_amount(edges[i+1])}" for i in range(nb)]
            cats = pd.cut(df[c.belop], bins=edges, include_lowest=True, labels=labels)
            for label in labels:
                seg_df = df[cats == label]
                self._df_cache[label] = seg_df
                self.tree_seg.insert("", tk.END, iid=label, values=(label, fmt_int(len(seg_df)), fmt_amount(float(seg_df[c.belop].sum()))))

        # velg første rad
        first = self.tree_seg.get_children()
        if first:
            self.tree_seg.selection_set(first[0])
            self._fill_transactions()

    def _fill_transactions(self):
        sel = self.tree_seg.selection()
        if not sel: return
        key = sel[0]
        df = self._df_cache.get(key)
        if df is None: return
        c = self.cols
        for iid in self.tree_tx.get_children(): self.tree_tx.delete(iid)
        dcol = c.dato if (c and c.dato in df.columns) else None
        tcol = c.tekst if (c and c.tekst in df.columns) else None
        for _, r in df.iterrows():
            dato = fmt_date(r[dcol]) if dcol else ""
            bilag = str(r[c.bilag])
            tekst = str(r[tcol]) if tcol else ""
            belop = fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0)
            konto = str(r[c.konto])
            navn  = str(r[c.kontonavn] or "")
            self.tree_tx.insert("", tk.END, values=(dato, bilag, tekst, belop, konto, navn))

    # ---------- sampling / export ----------
    def _do_sample(self):
        sel = self.tree_seg.selection()
        if not sel:
            messagebox.showwarning("Trekk", "Velg et segment.")
            return
        key = sel[0]
        df = self._df_cache.get(key)
        if df is None or df.empty:
            messagebox.showwarning("Trekk", "Segmentet er tomt."); return
        c = self.cols
        try:
            n = max(1, int(self.ent_n.get()))
        except Exception:
            messagebox.showwarning("Antall", "Ugyldig antall."); return

        per_bucket = bool(self.var_per_bucket.get())
        seed = None
        try:
            seed = int(self.ent_seed.get())
        except Exception:
            seed = None

        if per_bucket and key == "__ALL__":
            messagebox.showinfo("Trekk", "Velg en bestemt kvantil-bøtte for 'Trekk pr. bøtte'.")
            return

        unike = df[c.bilag].dropna().astype(str).drop_duplicates()
        if unike.empty:
            messagebox.showwarning("Trekk", "Ingen bilagsnummer funnet.")
            return

        if per_bucket:
            sample = unike.sample(n=min(n, len(unike)), random_state=seed)
        else:
            sample = unike.sample(n=min(n, len(unike)), random_state=seed)

        self._sample_ids = set(sample.tolist())
        rader = (df[c.bilag].astype(str).isin(self._sample_ids)).sum()
        messagebox.showinfo("Trekk klart", f"Valgte {len(self._sample_ids)} bilag. Linjer i utvalget: {rader:,}.")

    def _export(self):
        if not hasattr(self, "_sample_ids") or not self._sample_ids:
            messagebox.showinfo("Eksport", "Trekk bilag før eksport.")
            return
        df, c = self.df, self.cols
        if df is None or c is None:
            return
        try:
            export_selection_to_excel(df, c, self._sample_ids)
        except Exception as e:
            messagebox.showerror("Eksport feilet", str(e))
