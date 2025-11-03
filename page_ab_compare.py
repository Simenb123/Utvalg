# page_ab_compare.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional, Tuple
import pandas as pd

from dataset_pane import DatasetPane  # gjenbruk av ditt panel  :contentReference[oaicite:4]{index=4}
from models import Columns, ABAnalysisConfig  # konfig/kolonner  :contentReference[oaicite:5]{index=5}
from ab_analysis import run_all, ABResult
from formatting import fmt_amount, fmt_date, parse_amount, parse_date, fmt_int
from excel_export import export_and_open

class ABPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self.cfg = ABAnalysisConfig()
        self.dfA: Optional[pd.DataFrame] = None
        self.dfB: Optional[pd.DataFrame] = None
        self.cA = Columns(); self.cB = Columns()
        self._last: Optional[ABResult] = None

        # Øvre del: to dataset-paneler (A og B)
        pan = ttk.Panedwindow(self, orient=tk.HORIZONTAL); pan.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pan); pan.add(left, weight=1)
        right = ttk.Frame(pan); pan.add(right, weight=1)

        ttk.Label(left, text="Datasett A").pack(anchor="w", padx=8, pady=(8,0))
        self.dsA = DatasetPane(left, title="A – kolonnekart")
        self.dsA.frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        barA = ttk.Frame(left); barA.pack(fill=tk.X, padx=8, pady=(0,8))
        ttk.Button(barA, text="Bruk A", command=self._use_A).pack(side=tk.RIGHT)

        ttk.Label(right, text="Datasett B").pack(anchor="w", padx=8, pady=(8,0))
        self.dsB = DatasetPane(right, title="B – kolonnekart")
        self.dsB.frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        barB = ttk.Frame(right); barB.pack(fill=tk.X, padx=8, pady=(0,8))
        ttk.Button(barB, text="Bruk B", command=self._use_B).pack(side=tk.RIGHT)

        # Midtre: A/B-innstillinger
        cfg = ttk.LabelFrame(self, text="A/B-innstillinger", padding=8)
        cfg.pack(fill=tk.X, padx=8, pady=(6,2))
        self.var_same_party = tk.BooleanVar(value=self.cfg.require_same_party)
        ttk.Checkbutton(cfg, text="Krev samme part/kunde", variable=self.var_same_party).pack(side=tk.LEFT)
        self.var_unique = tk.BooleanVar(value=self.cfg.unique_match)
        ttk.Checkbutton(cfg, text="Unik match (maks 1–1)", variable=self.var_unique).pack(side=tk.LEFT, padx=(8,0))

        ttk.Label(cfg, text="Beløpstoleranse (kr):").pack(side=tk.LEFT, padx=(16,2))
        self.ent_tol_amt = ttk.Entry(cfg, width=10); self.ent_tol_amt.insert(0, f"{self.cfg.amount_tolerance:.2f}".replace(".", ","))
        self.ent_tol_amt.pack(side=tk.LEFT)
        ttk.Label(cfg, text="Dagstoleranse:").pack(side=tk.LEFT, padx=(12,2))
        self.ent_tol_days = ttk.Entry(cfg, width=6); self.ent_tol_days.insert(0, str(self.cfg.days_tolerance))
        self.ent_tol_days.pack(side=tk.LEFT, padx=(0,6))

        ttk.Button(cfg, text="Kjør A/B‑analyse", command=self._run).pack(side=tk.RIGHT)
        ttk.Button(cfg, text="Eksporter og åpne Excel", command=self._export).pack(side=tk.RIGHT, padx=(0,8))

        # Nedre del: Resultatfaner
        self.nb = ttk.Notebook(self); self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2,8))
        self.tabs: Dict[str, ttk.Treeview] = {}
        for name in (
            "Like beløp (±tol, ±dager)",
            "Motsatt fortegn (±tol, ±dager)",
            "Two‑sum (B+B=A)",
            "Likt faktura/dok.nr",
            "Avvik: beløp på nøkkel",
            "Avvik: dato på nøkkel",
            "Dupl. faktura per part – A",
            "Dupl. faktura per part – B",
        ):
            frame = ttk.Frame(self.nb); self.nb.add(frame, text=name)
            tree = ttk.Treeview(frame, columns=("c1","c2","c3","c4","c5","c6","c7","c8","c9","c10"), show="headings")
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set); vsb.pack(side=tk.RIGHT, fill=tk.Y)
            self.tabs[name] = tree

        self.hint = ttk.Label(self, text="Tips: bygg A og B øverst, sett toleranser, og kjør A/B‑analyse. Eksport åpner Excel direkte.")
        self.hint.pack(fill=tk.X, padx=8)

    # ---------------- dataset A/B ----------------
    def _use_A(self):
        df, c = self.dsA.build_dataset()
        if df is None or c is None:
            return
        self.dfA, self.cA = df, c
        messagebox.showinfo("Datasett A", f"A aktivert – {len(df):,} rader.")

    def _use_B(self):
        df, c = self.dsB.build_dataset()
        if df is None or c is None:
            return
        self.dfB, self.cB = df, c
        messagebox.showinfo("Datasett B", f"B aktivert – {len(df):,} rader.")

    # ---------------- run / export ----------------
    def _run(self):
        if self.dfA is None or self.dfB is None:
            messagebox.showinfo("A/B", "Bygg og aktiver både A og B først.")
            return
        cfg = ABAnalysisConfig()
        cfg.require_same_party = bool(self.var_same_party.get())
        cfg.unique_match = bool(self.var_unique.get())
        # toleranser
        amt = self.ent_tol_amt.get().strip()
        cfg.amount_tolerance = float(parse_amount(amt) or 0.0)
        try:
            cfg.days_tolerance = int((self.ent_tol_days.get() or "0").strip())
        except Exception:
            cfg.days_tolerance = 0

        res = run_all(self.dfA, self.cA, self.dfB, self.cB, cfg)
        self._last = res
        self._fill_all(res)

    def _export(self):
        if self._last is None:
            messagebox.showinfo("Eksport", "Kjør A/B‑analyse først.")
            return
        cA, cB = self.cA, self.cB
        r = self._last

        def std_tx(df: pd.DataFrame, side: str) -> pd.DataFrame:
            if df is None or df.empty:
                return pd.DataFrame()
            out = df.copy()
            # Lag lesbare kolonner
            rename = {}
            for tag, c in (("A", cA), ("B", cB)):
                if f"{tag}_idx" in out.columns: rename[f"{tag}_idx"] = f"{tag}_Index"
                if f"{tag}_konto" in out.columns: rename[f"{tag}_konto"] = f"{tag}_Konto"
                if f"{tag}_bilag" in out.columns: rename[f"{tag}_bilag"] = f"{tag}_Bilag"
                if f"{tag}_date" in out.columns: rename[f"{tag}_date"] = f"{tag}_Dato"
                if f"{tag}_party" in out.columns: rename[f"{tag}_party"] = f"{tag}_Part"
                if f"{tag}_amt_cents" in out.columns: rename[f"{tag}_amt_cents"] = f"{tag}_Beløp_øre"
                if f"{tag}_sum_cents" in out.columns: rename[f"{tag}_sum_cents"] = f"{tag}_Sum_øre"
                if f"{tag}_doc_norm" in out.columns: rename[f"{tag}_doc_norm"] = f"{tag}_Dok_norm"
            out = out.rename(columns=rename)
            # Konverter øre→kr for utskrift (behold øre som hjelpekoll om ønsket)
            for col in list(out.columns):
                if col.endswith("_Beløp_øre") or col.endswith("_Sum_øre"):
                    kr_col = col.replace("_øre", "")
                    out[kr_col] = out[col].astype(float) / 100.0
            return out

        sheets = {
            "Like_belop": std_tx(r.same_amount, "same"),
            "Motsatt_fortegn": std_tx(r.opposite_sign, "oppo"),
            "Two_sum": std_tx(r.two_sum, "two"),
            "Likt_faktura": std_tx(r.key_matches, "key"),
            "Avvik_belop_key": std_tx(r.key_dev_amount, "key_amt"),
            "Avvik_dato_key": std_tx(r.key_dev_date, "key_date"),
            "Dupl_faktura_A": r.dup_invoice_A if r.dup_invoice_A is not None else pd.DataFrame(),
            "Dupl_faktura_B": r.dup_invoice_B if r.dup_invoice_B is not None else pd.DataFrame(),
        }
        prefer_dates = {"A_Dato", "B_Dato", "Dato"}
        prefer_amounts = {"A_Beløp", "B_Beløp", "Sum", "Beløp", "A_Sum", "B_Sum"}
        path = export_and_open(sheets, prefer_date_cols=prefer_dates, prefer_amount_cols=prefer_amounts)
        messagebox.showinfo("Eksport", f"Eksportert og åpnet:\n{path}")

    # ---------------- fill GUI ----------------
    def _reset_tree(self, name: str, headers: List[Tuple[str,int,str]]):
        tr = self.tabs[name]
        for iid in tr.get_children(): tr.delete(iid)
        cols = [f"c{i+1}" for i in range(len(headers))]
        tr["columns"] = cols
        for i, (txt, w, anc) in enumerate(headers):
            cid = cols[i]
            tr.heading(cid, text=txt); tr.column(cid, width=w, anchor=anc)

    def _fill_all(self, r: ABResult):
        # Like beløp
        name = "Like beløp (±tol, ±dager)"
        self._reset_tree(name, [("A‑Dato",100,"w"),("A‑Bilag",120,"w"),("A‑Part",160,"w"),("A‑Beløp",120,"e"),
                                ("B‑Dato",100,"w"),("B‑Bilag",120,"w"),("B‑Part",160,"w"),("B‑Beløp",120,"e"),
                                ("Δ beløp",100,"e"),("Δ dager",80,"e")])
        if r.same_amount is not None and not r.same_amount.empty:
            df = r.same_amount
            for _, x in df.head(2000).iterrows():
                row = [
                    fmt_date(x.get("A_date")), str(x.get("A_bilag")), str(x.get("A_party")), fmt_amount(float(x.get("A_amt_cents",0))/100.0),
                    fmt_date(x.get("B_date")), str(x.get("B_bilag")), str(x.get("B_party")), fmt_amount(float(x.get("B_amt_cents",0))/100.0),
                    fmt_amount(float(x.get("__delta_cents__",0))/100.0),
                    f"{int(float(x.get('__days__',0))):d}",
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Motsatt fortegn
        name = "Motsatt fortegn (±tol, ±dager)"
        self._reset_tree(name, [("A‑Dato",100,"w"),("A‑Bilag",120,"w"),("A‑Part",160,"w"),("A‑Beløp",120,"e"),
                                ("B‑Dato",100,"w"),("B‑Bilag",120,"w"),("B‑Part",160,"w"),("B‑Beløp",120,"e"),
                                ("|A+B|",100,"e"),("Δ dager",80,"e")])
        if r.opposite_sign is not None and not r.opposite_sign.empty:
            df = r.opposite_sign
            for _, x in df.head(2000).iterrows():
                row = [
                    fmt_date(x.get("A_date")), str(x.get("A_bilag")), str(x.get("A_party")), fmt_amount(float(x.get("A_amt_cents",0))/100.0),
                    fmt_date(x.get("B_date")), str(x.get("B_bilag")), str(x.get("B_party")), fmt_amount(float(x.get("B_amt_cents",0))/100.0),
                    fmt_amount(float(x.get("__delta_cents__",0))/100.0),
                    f"{int(float(x.get('__days__',0))):d}",
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Two-sum
        name = "Two‑sum (B+B=A)"
        self._reset_tree(name, [("A‑Index",80,"e"),("A‑Beløp",120,"e"),("B1‑Index",80,"e"),("B2‑Index",80,"e"),("Δ beløp",100,"e"),("A‑Dato",100,"w")])
        if r.two_sum is not None and not r.two_sum.empty:
            df = r.two_sum
            for _, x in df.head(2000).iterrows():
                row = [
                    fmt_int(int(x.get("A_idx",0))),
                    fmt_amount(float(x.get("A_amt_cents",0))/100.0),
                    fmt_int(int(x.get("B_idx_1",0))),
                    fmt_int(int(x.get("B_idx_2",0))),
                    fmt_amount(float(x.get("__delta_cents__",0))/100.0),
                    fmt_date(x.get("A_date")),
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Likt faktura/dok.nr
        name = "Likt faktura/dok.nr"
        self._reset_tree(name, [("Dok‑norm",160,"w"),("A‑Bilag",120,"w"),("A‑Part",160,"w"),("A‑Beløp",120,"e"),("A‑Dato",100,"w"),
                                ("B‑Bilag",120,"w"),("B‑Part",160,"w"),("B‑Beløp",120,"e"),("B‑Dato",100,"w"),
                                ("Δ beløp",100,"e")])
        if r.key_matches is not None and not r.key_matches.empty:
            df = r.key_matches
            for _, x in df.head(2000).iterrows():
                row = [
                    str(x.get("A_doc_norm")),
                    str(x.get("A_bilag")), str(x.get("A_party")), fmt_amount(float(x.get("A_amt_cents",0))/100.0), fmt_date(x.get("A_date")),
                    str(x.get("B_bilag")), str(x.get("B_party")), fmt_amount(float(x.get("B_amt_cents",0))/100.0), fmt_date(x.get("B_date")),
                    fmt_amount(float(x.get("__amt_diff_cents__",0))/100.0),
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Avvik beløp
        name = "Avvik: beløp på nøkkel"
        self._reset_tree(name, [("Dok‑norm",160,"w"),("A‑Beløp",120,"e"),("B‑Beløp",120,"e"),("Δ beløp",100,"e")])
        if r.key_dev_amount is not None and not r.key_dev_amount.empty:
            df = r.key_dev_amount
            for _, x in df.head(2000).iterrows():
                row = [
                    str(x.get("A_doc_norm")),
                    fmt_amount(float(x.get("A_amt_cents",0))/100.0),
                    fmt_amount(float(x.get("B_amt_cents",0))/100.0),
                    fmt_amount(float(x.get("__amt_diff_cents__",0))/100.0),
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Avvik dato
        name = "Avvik: dato på nøkkel"
        self._reset_tree(name, [("Dok‑norm",160,"w"),("A‑Dato",100,"w"),("B‑Dato",100,"w"),("Δ dager",80,"e")])
        if r.key_dev_date is not None and not r.key_dev_date.empty:
            df = r.key_dev_date
            for _, x in df.head(2000).iterrows():
                row = [
                    str(x.get("A_doc_norm")),
                    fmt_date(x.get("A_date")),
                    fmt_date(x.get("B_date")),
                    f"{int(float(x.get('__days__',0))):d}",
                ]
                self.tabs[name].insert("", tk.END, values=row)

        # Duplikater
        name = "Dupl. faktura per part – A"
        self._reset_tree(name, [("Bilag",140,"w"),("Part",180,"w"),("Dato",100,"w"),("Konto",80,"e"),("Beløp",120,"e")])
        if r.dup_invoice_A is not None and not r.dup_invoice_A.empty:
            for _, x in r.dup_invoice_A.head(2000).iterrows():
                row = [str(x.get(self.cA.bilag)), str(x.get(self.cA.part,"")), fmt_date(x.get(self.cA.dato)), str(x.get(self.cA.konto)), fmt_amount(float(x.get(self.cA.belop,0)))]
                self.tabs[name].insert("", tk.END, values=row)
        name = "Dupl. faktura per part – B"
        self._reset_tree(name, [("Bilag",140,"w"),("Part",180,"w"),("Dato",100,"w"),("Konto",80,"e"),("Beløp",120,"e")])
        if r.dup_invoice_B is not None and not r.dup_invoice_B.empty:
            for _, x in r.dup_invoice_B.head(2000).iterrows():
                row = [str(x.get(self.cB.bilag)), str(x.get(self.cB.part,"")), fmt_date(x.get(self.cB.dato)), str(x.get(self.cB.konto)), fmt_amount(float(x.get(self.cB.belop,0)))]
                self.tabs[name].insert("", tk.END, values=row)
