"""
LEGACY-FIL (ikke i aktiv bruk)

Dette er en tidligere versjon av analyse-siden.
Ny funksjonalitet skal normalt IKKE legges her.

Gjeldende analyse-GUI er:
    AnalysePage i page_analyse.py

Filen beholdes midlertidig som referanse/backup.
"""

# page_analyser.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, List, Optional, Tuple
import pandas as pd

from session import get_dataset, has_dataset
from models import Columns, AnalysisConfig  # fra dine modeller  :contentReference[oaicite:5]{index=5}
from analysis_pack import run_all, AnalysisResult
from formatting import fmt_amount, fmt_date, parse_amount, parse_date, fmt_int
from excel_export import export_and_open

class AnalyserPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self.cols = Columns()
        self.df: Optional[pd.DataFrame] = None
        self.cfg = AnalysisConfig()

        # ---------------- topp: filter & konfig ----------------
        f = ttk.Frame(self, padding=8); f.pack(fill=tk.X)
        ttk.Label(f, text="Retning:").pack(side=tk.LEFT)
        self.var_dir = tk.StringVar(value="Alle")
        self.cbo_dir = ttk.Combobox(f, state="readonly", width=8, values=["Alle","Debet","Kredit"], textvariable=self.var_dir)
        self.cbo_dir.pack(side=tk.LEFT, padx=(4,12))

        ttk.Label(f, text="Min beløp:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(f, width=12); self.ent_min.pack(side=tk.LEFT, padx=(4,8))
        ttk.Label(f, text="Maks beløp:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(f, width=12); self.ent_max.pack(side=tk.LEFT, padx=(4,12))

        ttk.Label(f, text="Periode: fra").pack(side=tk.LEFT)
        self.ent_from = ttk.Entry(f, width=12); self.ent_from.pack(side=tk.LEFT, padx=(4,4))
        ttk.Label(f, text="til").pack(side=tk.LEFT)
        self.ent_to = ttk.Entry(f, width=12); self.ent_to.pack(side=tk.LEFT, padx=(4,12))
        ttk.Label(f, text="(dd.mm.åååå)").pack(side=tk.LEFT)

        ttk.Button(f, text="Kjør analyser", command=self._run).pack(side=tk.RIGHT)
        ttk.Button(f, text="Eksporter og åpne Excel", command=self._export).pack(side=tk.RIGHT, padx=(0,8))

        # ---------------- midt: analyseresultater (faner) --------------
        self.nb = ttk.Notebook(self); self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2,8))
        self.tabs: Dict[str, Tuple[ttk.Frame, ttk.Treeview]] = {}

        for name in (
            "Runde beløp (transaksjoner)",
            "Andel runde per gruppe",
            "Dupl. dok+konto",
            "Dupl. beløp+dato+part",
            "Outliers",
            "Utenfor periode",
        ):
            frame = ttk.Frame(self.nb); self.nb.add(frame, text=name)
            tree = ttk.Treeview(frame, columns=("c1","c2","c3","c4","c5","c6","c7","c8","c9","c10"), show="headings")
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set); vsb.pack(side=tk.RIGHT, fill=tk.Y)
            self.tabs[name] = (frame, tree)

        self.lbl_hint = ttk.Label(self, text="Tips: kjør analyser for å se resultater. Excel‑eksport åpner arbeidsbok med ark per analyse.")
        self.lbl_hint.pack(fill=tk.X, padx=8)

        self._last_result: Optional[AnalysisResult] = None

    # ---------------- public ----------------
    def refresh_from_session(self):
        if not has_dataset():
            self.df, self.cols = None, Columns()
            for _, tree in self.tabs.values():
                for iid in tree.get_children(): tree.delete(iid)
            return
        df, cols = get_dataset()
        self.df, self.cols = df, cols

    # ---------------- internal ----------------
    def _parse_amount(self, s: str) -> Optional[float]:
        s = (s or "").strip()
        if not s: return None
        v = parse_amount(s)
        return None if v is None else float(v)

    def _parse_date(self, s: str):
        s = (s or "").strip()
        if not s: return None
        return parse_date(s)

    def _run(self):
        if self.df is None or self.cols is None:
            messagebox.showinfo("Analyser", "Ingen datasett aktivt."); return

        dirx = self.var_dir.get() or "Alle"
        min_v = self._parse_amount(self.ent_min.get())
        max_v = self._parse_amount(self.ent_max.get())
        dfrom = self._parse_date(self.ent_from.get())
        dto = self._parse_date(self.ent_to.get())

        res = run_all(self.df, self.cols, self.cfg,
                      direction=dirx, min_amount=min_v, max_amount=max_v,
                      date_from=dfrom, date_to=dto)
        self._last_result = res

        # fyll tabs
        self._fill_round_tx(res.round_tx)
        self._fill_round_share(res.round_share)
        self._fill_dup_doc(res.dup_doc_account)
        self._fill_dup_adp(res.dup_amt_date_part)
        self._fill_outliers(res.outliers)
        self._fill_ooper(res.out_of_period)

    # ----------- fyll faner (Treeviews) -------------
    def _reset_tree(self, name: str, headers: List[Tuple[str, int, str]]):
        frame, tree = self.tabs[name]
        for iid in tree.get_children(): tree.delete(iid)
        # rekonstruksjon av kolonner
        cols = [f"c{i+1}" for i in range(len(headers))]
        tree["columns"] = cols
        for i, (txt, w, anc) in enumerate(headers):
            cid = cols[i]
            tree.heading(cid, text=txt)
            tree.column(cid, width=w, anchor=anc)

    def _fill_round_tx(self, df: pd.DataFrame):
        name = "Runde beløp (transaksjoner)"
        headers = [("Dato",100,"w"),("Bilag",120,"w"),("Tekst",320,"w"),("Part",180,"w"),
                   ("Konto",80,"e"),("Kontonavn",220,"w"),("Beløp",120,"e"),("Base",80,"e"),("Avvik",80,"e")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        c = self.cols
        date_col = getattr(c, "dato", None) if getattr(c, "dato", "") in df.columns else None
        text_col = getattr(c, "tekst", None) if getattr(c, "tekst", "") in df.columns else None
        part_col = getattr(c, "part", None) if getattr(c, "part", "") in df.columns else None

        for _, r in df.head(2000).iterrows():
            row = [
                fmt_date(r[date_col]) if date_col else "",
                str(r[c.bilag]),
                str(r[text_col]) if text_col else "",
                str(r[part_col]) if part_col else "",
                str(r[c.konto]),
                str(r[c.kontonavn]) if not pd.isna(r[c.kontonavn]) else "",
                fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0),
                str(int(r["__RoundBase__"])) if pd.notna(r["__RoundBase__"]) else "",
                fmt_amount(float(r["__RoundDist__"])) if pd.notna(r["__RoundDist__"]) else "",
            ]
            self.tabs[name][1].insert("", tk.END, values=row)

    def _fill_round_share(self, df: pd.DataFrame):
        name = "Andel runde per gruppe"
        headers = [("Gruppe",320,"w"),("Rader",100,"e"),("Runde",100,"e"),("Andel %",100,"e"),("Flagg",80,"center")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        for _, r in df.head(2000).iterrows():
            pct = f"{float(r['Andel_runde'])*100:,.2f}".replace(",", " ").replace(".", ",")
            row = [str(r["Gruppe"]), fmt_int(int(r["Total"])), fmt_int(int(r["Runde"])), pct, "Ja" if bool(r["Flagg"]) else ""]
            self.tabs[name][1].insert("", tk.END, values=row)

    def _fill_dup_doc(self, df: pd.DataFrame):
        name = "Dupl. dok+konto"
        headers = [("Dato",100,"w"),("Bilag",120,"w"),("Tekst",320,"w"),
                   ("Konto",80,"e"),("Kontonavn",220,"w"),("Beløp",120,"e")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        c = self.cols
        dcol = getattr(c, "dato", None) if getattr(c, "dato", "") in df.columns else None
        tcol = getattr(c, "tekst", None) if getattr(c, "tekst", "") in df.columns else None
        for _, r in df.head(2000).iterrows():
            row = [
                fmt_date(r[dcol]) if dcol else "",
                str(r[c.bilag]),
                str(r[tcol]) if tcol else "",
                str(r[c.konto]),
                str(r[c.kontonavn]) if not pd.isna(r[c.kontonavn]) else "",
                fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0),
            ]
            self.tabs[name][1].insert("", tk.END, values=row)

    def _fill_dup_adp(self, df: pd.DataFrame):
        name = "Dupl. beløp+dato+part"
        headers = [("Dato",100,"w"),("Part",180,"w"),("Bilag",120,"w"),("Tekst",320,"w"),
                   ("Konto",80,"e"),("Kontonavn",220,"w"),("Beløp",120,"e")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        c = self.cols
        dcol = getattr(c, "dato", None) if getattr(c, "dato", "") in df.columns else None
        pcol = getattr(c, "part", None) if getattr(c, "part", "") in df.columns else None
        tcol = getattr(c, "tekst", None) if getattr(c, "tekst", "") in df.columns else None
        for _, r in df.head(2000).iterrows():
            row = [
                fmt_date(r[dcol]) if dcol else "",
                str(r[pcol]) if pcol else "",
                str(r[c.bilag]),
                str(r[tcol]) if tcol else "",
                str(r[c.konto]),
                str(r[c.kontonavn]) if not pd.isna(r[c.kontonavn]) else "",
                fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0),
            ]
            self.tabs[name][1].insert("", tk.END, values=row)

    def _fill_outliers(self, df: pd.DataFrame):
        name = "Outliers"
        headers = [("Gruppe",160,"w"),("Metode",80,"w"),("Score",90,"e"),("Senter",110,"e"),("Skala",110,"e"),
                   ("Dato",100,"w"),("Bilag",120,"w"),("Tekst",280,"w"),("Konto",80,"e"),("Beløp",120,"e")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        c = self.cols
        dcol = getattr(c, "dato", None) if getattr(c, "dato", "") in df.columns else None
        tcol = getattr(c, "tekst", None) if getattr(c, "tekst", "") in df.columns else None
        for _, r in df.head(2000).iterrows():
            row = [
                str(r["__Group__"]),
                str(r["__Method__"]),
                f"{float(r['__Score__']):,.2f}".replace(",", " ").replace(".", ","),
                fmt_amount(float(r["__Center__"])),
                fmt_amount(float(r["__Scale__"])),
                fmt_date(r[dcol]) if dcol else "",
                str(r[c.bilag]),
                str(r[tcol]) if tcol else "",
                str(r[c.konto]),
                fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0),
            ]
            self.tabs[name][1].insert("", tk.END, values=row)

    def _fill_ooper(self, df: pd.DataFrame):
        name = "Utenfor periode"
        headers = [("Dato",100,"w"),("Bilag",120,"w"),("Tekst",320,"w"),("Part",180,"w"),
                   ("Konto",80,"e"),("Kontonavn",220,"w"),("Beløp",120,"e")]
        self._reset_tree(name, headers)
        if df is None or df.empty:
            return
        c = self.cols
        dcol = c.dato if getattr(c, "dato", "") in df.columns else None
        tcol = c.tekst if getattr(c, "tekst", "") in df.columns else None
        pcol = c.part if getattr(c, "part", "") in df.columns else None
        for _, r in df.head(2000).iterrows():
            row = [
                fmt_date(r[dcol]) if dcol else "",
                str(r[c.bilag]),
                str(r[tcol]) if tcol else "",
                str(r[pcol]) if pcol else "",
                str(r[c.konto]),
                str(r[c.kontonavn]) if not pd.isna(r[c.kontonavn]) else "",
                fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0),
            ]
            self.tabs[name][1].insert("", tk.END, values=row)

    # ------------------------ eksport -------------------------
    def _export(self):
        if self._last_result is None:
            messagebox.showinfo("Eksport", "Kjør analyser først."); return

        c = self.cols
        r = self._last_result

        # For Excel: gi standard kolonnenavn
        def std_tx(df: pd.DataFrame) -> pd.DataFrame:
            if df is None or df.empty:
                return pd.DataFrame()
            out = df.copy()
            rename = {
                c.konto: "Konto",
                c.kontonavn: "Kontonavn",
                c.bilag: "Bilag",
            }
            if getattr(c, "dato", "") and c.dato in out.columns: rename[c.dato] = "Dato"
            if getattr(c, "tekst", "") and c.tekst in out.columns: rename[c.tekst] = "Tekst"
            if getattr(c, "part", "") and c.part in out.columns: rename[c.part] = "Part"
            rename[c.belop] = "Beløp"
            if "__RoundBase__" in out.columns: rename["__RoundBase__"] = "Base"
            if "__RoundDist__" in out.columns: rename["__RoundDist__"] = "Avvik"
            if "__Group__" in out.columns: rename["__Group__"] = "Gruppe"
            if "__Method__" in out.columns: rename["__Method__"] = "Metode"
            if "__Center__" in out.columns: rename["__Center__"] = "Senter"
            if "__Scale__" in out.columns: rename["__Scale__"] = "Skala"
            if "__Score__" in out.columns: rename["__Score__"] = "Score"
            out = out.rename(columns=rename)
            return out

        sheets = {
            "Runde_transaksjoner": std_tx(r.round_tx),
            "Runde_andel": r.round_share.rename(columns={"Gruppe":"Gruppe","Total":"Rader","Runde":"Runde","Andel_runde":"Andel","Flagg":"Flagg"}) if r.round_share is not None else pd.DataFrame(),
            "Dupl_dok_konto": std_tx(r.dup_doc_account),
            "Dupl_belop_dato_part": std_tx(r.dup_amt_date_part),
            "Outliers": std_tx(r.outliers),
            "Utenfor_periode": std_tx(r.out_of_period),
        }

        prefer_dates = {"Dato"}
        prefer_amounts = {"Beløp", "Senter", "Skala", "Avvik"}
        path = export_and_open(sheets, prefer_date_cols=prefer_dates, prefer_amount_cols=prefer_amounts)
        messagebox.showinfo("Eksport", f"Eksportert og åpnet:\n{path}")
