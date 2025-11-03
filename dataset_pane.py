# dataset_pane.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Tuple, Optional
import pandas as pd

import io_utils as iou
from models import Columns
import ml_map  # mini-ML

class DatasetPane:
    def __init__(self, parent: tk.Tk | tk.Toplevel | ttk.Frame, title: str = "Datasett"):
        self.parent = parent
        self.frm = ttk.LabelFrame(parent, text=title, padding=8)

        top = ttk.Frame(self.frm); top.pack(fill=tk.X)
        self.var_path = tk.StringVar()
        ttk.Button(top, text="Åpne…", command=self._open).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.var_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,8))
        ttk.Button(top, text="Forhåndsvis", command=self._preview).pack(side=tk.RIGHT)

        # Kolonnekart
        mapf = ttk.Frame(self.frm); mapf.pack(fill=tk.X, pady=(8,0))
        self.cbo_konto = _cbo(mapf, "Kontonummer:")
        self.cbo_kontonavn = _cbo(mapf, "Kontonavn:")
        self.cbo_bilag = _cbo(mapf, "Bilagsnr:")

        # Beløp: single eller (debet/kredit)
        self.cbo_belop = _cbo(mapf, "Beløp (single):")
        self.cbo_debit = _cbo(mapf, "Debet (valgfri):")
        self.cbo_credit = _cbo(mapf, "Kredit (valgfri):")

        self.cbo_dato = _cbo(mapf, "Dato:")
        self.cbo_tekst = _cbo(mapf, "Tekst:")
        self.cbo_part = _cbo(mapf, "Part/Kunde:")

        hdr = ttk.Frame(self.frm); hdr.pack(fill=tk.X, pady=(8,0))
        ttk.Label(hdr, text="Header-rad (1=første):").pack(side=tk.LEFT)
        self.spin_header = tk.Spinbox(hdr, from_=1, to=9999, width=8)
        self.spin_header.pack(side=tk.LEFT, padx=(6,8))
        ttk.Button(hdr, text="Oppdag", command=self._detect_header).pack(side=tk.LEFT, padx=(0,4))
        ttk.Button(hdr, text="Bruk", command=self._apply_header).pack(side=tk.LEFT)

        btnbar = ttk.Frame(self.frm); btnbar.pack(fill=tk.X, pady=(10,0))
        ttk.Button(btnbar, text="Bygg datasett", command=self._build).pack(side=tk.RIGHT)
        self.lbl_status = ttk.Label(self.frm, text="", foreground="#555")
        self.lbl_status.pack(fill=tk.X, pady=(4,0))

        self._raw: Optional[pd.DataFrame] = None
        self._df: Optional[pd.DataFrame] = None
        self._built_df: Optional[pd.DataFrame] = None
        self._built_cols: Optional[Columns] = None

    # --- fil/header ---
    def _open(self):
        path = filedialog.askopenfilename(
            title="Åpne hovedbok (Excel/CSV)",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("Alle filer", "*.*")]
        )
        if not path: return
        self.var_path.set(path)
        try:
            self._raw = iou.read_any(path)
        except Exception as e:
            messagebox.showerror("Feil ved lesing", str(e)); return
        self._after_load()

    def _after_load(self):
        assert self._raw is not None
        idx = iou.detect_header_row(self._raw)
        self.spin_header.delete(0, tk.END); self.spin_header.insert(0, str(idx+1))
        self._df = iou.apply_header(self._raw, idx)

        cols = list(self._df.columns)
        for cbo in (self.cbo_konto, self.cbo_kontonavn, self.cbo_bilag,
                    self.cbo_belop, self.cbo_debit, self.cbo_credit,
                    self.cbo_dato, self.cbo_tekst, self.cbo_part):
            cbo["values"] = cols

        learned = ml_map.suggest(cols)
        if learned:
            self.cbo_konto.set(learned.get("konto", self.cbo_konto.get()))
            self.cbo_kontonavn.set(learned.get("kontonavn", self.cbo_kontonavn.get()))
            self.cbo_bilag.set(learned.get("bilag", self.cbo_bilag.get()))
            self.cbo_belop.set(learned.get("belop", self.cbo_belop.get()))
            if "debit" in learned: self.cbo_debit.set(learned["debit"])
            if "credit" in learned: self.cbo_credit.set(learned["credit"])
            if "dato" in learned: self.cbo_dato.set(learned["dato"])
            if "tekst" in learned: self.cbo_tekst.set(learned["tekst"])
            if "part" in learned: self.cbo_part.set(learned["part"])
        else:
            g = iou.guess_columns(cols)
            if g.konto: self.cbo_konto.set(g.konto)
            if g.kontonavn: self.cbo_kontonavn.set(g.kontonavn)
            if g.bilag: self.cbo_bilag.set(g.bilag)
            if g.belop: self.cbo_belop.set(g.belop)
            if g.dato: self.cbo_dato.set(g.dato)
            if g.tekst: self.cbo_tekst.set(g.tekst)
            if g.part: self.cbo_part.set(g.part)

        self._built_df = None; self._built_cols = None
        self.lbl_status.config(text=f"Header antatt på rad {self.spin_header.get()}. Velg/juster kolonner og trykk «Bygg datasett».")

    def _detect_header(self):
        if self._raw is None: return
        idx = iou.detect_header_row(self._raw)
        self.spin_header.delete(0, tk.END); self.spin_header.insert(0, str(idx+1))
        self._df = iou.apply_header(self._raw, idx)
        self._built_df = None; self._built_cols = None
        self.lbl_status.config(text=f"Header oppdaget: rad {idx+1}.")

    def _apply_header(self):
        if self._raw is None: return
        try:
            idx = max(1, int(self.spin_header.get())) - 1
        except ValueError:
            messagebox.showwarning("Header", "Ugyldig radnummer."); return
        self._df = iou.apply_header(self._raw, idx)
        self._built_df = None; self._built_cols = None
        self.lbl_status.config(text=f"Header satt til rad {idx+1}.")

    def _preview(self):
        if self._raw is None:
            messagebox.showinfo("Ingen fil", "Åpne en fil først."); return
        top = tk.Toplevel(self.parent)
        top.title("Forhåndsvisning – dobbeltklikk rad for å sette header")
        top.geometry("980x520")

        frm = ttk.Frame(top); frm.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(frm, columns=[f"kol{i+1}" for i in range(self._raw.shape[1])], show="headings")
        for i in range(self._raw.shape[1]):
            col = f"kol{i+1}"; tree.heading(col, text=col); tree.column(col, width=120, stretch=True)
        for r in range(min(200, len(self._raw))):
            vals = [str(v) for v in self._raw.iloc[r].tolist()]
            tree.insert("", tk.END, iid=str(r), values=vals)
        vsb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set); tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        def on_double(_e=None):
            sel = tree.selection()
            if not sel: return
            idx = int(sel[0])
            self.spin_header.delete(0, tk.END); self.spin_header.insert(0, str(idx+1))
            try: top.destroy()
            except Exception: pass
        tree.bind("<Double-1>", on_double)

    # --- bygg / API ---
    def build_dataset(self) -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
        if self._df is None:
            if self._raw is None: return None, None
            try:
                idx = max(1, int(self.spin_header.get())) - 1
            except ValueError:
                idx = iou.detect_header_row(self._raw)
            self._df = iou.apply_header(self._raw, idx)

        konto = self.cbo_konto.get() or ""
        kontonavn = self.cbo_kontonavn.get() or ""
        bilag = self.cbo_bilag.get() or ""
        belop = (self.cbo_belop.get() or "").strip()
        debit = (self.cbo_debit.get() or "").strip()
        credit = (self.cbo_credit.get() or "").strip()

        if not all([konto, kontonavn, bilag]):
            messagebox.showwarning("Mangler kolonner", "Velg minst konto, navn og bilag.")
            return None, None

        use_dc = (debit and credit)
        if not belop and not use_dc:
            messagebox.showwarning("Beløp", "Velg Beløp (single) eller både Debet og Kredit.")
            return None, None

        chosen = [konto, kontonavn, bilag] + ([belop] if belop else []) + ([debit, credit] if use_dc else [])
        for ch in chosen:
            if ch and ch not in self._df.columns:
                messagebox.showwarning("Kolonne finnes ikke",
                                       f"Kolonnen «{ch}» finnes ikke i datasettet etter header.\nVelg på nytt.")
                return None, None

        df = self._df.copy()

        # Konto, navn
        df[konto] = iou.coerce_account_series(df[konto])
        if kontonavn not in df.columns:
            df[kontonavn] = ""

        # Beløp
        if use_dc:
            dser = iou.coerce_amount_series(df[debit])
            cser = iou.coerce_amount_series(df[credit])
            df["__BELØP__"] = (dser - cser).astype(float)
            belop_col = "__BELØP__"
        else:
            df[belop] = iou.coerce_amount_series(df[belop])
            belop_col = belop

        # Valgfrie
        date_name = self.cbo_dato.get() or ""
        if date_name and date_name in df.columns:
            df[date_name] = iou.coerce_date_series(df[date_name])

        # Tekst/part beholdes som str hvis valgt
        df = df.dropna(subset=[konto, bilag, belop_col])

        c = Columns(
            konto=konto, kontonavn=kontonavn, bilag=bilag,
            belop=belop_col, debit=debit if use_dc else "", credit=credit if use_dc else "",
            tekst=(self.cbo_tekst.get() or ""), dato=(date_name or ""), part=(self.cbo_part.get() or "")
        )
        return df, c

    def _build(self):
        df, cols = self.build_dataset()
        if df is None or cols is None: return
        headers = list(self._df.columns) if self._df is not None else []
        ml_map.learn(headers, {
            "konto": cols.konto, "kontonavn": cols.kontonavn,
            "bilag": cols.bilag, "belop": (cols.belop if cols.belop != "__BELØP__" else (self.cbo_belop.get() or "")),
            "debit": cols.debit or "", "credit": cols.credit or "",
            "dato": self.cbo_dato.get() or "", "tekst": self.cbo_tekst.get() or "", "part": self.cbo_part.get() or "",
        })
        self._built_df, self._built_cols = df, cols
        self.lbl_status.config(text=f"Datasett bygget: {len(df):,} rader. Klikk «Bruk datasett» for å fortsette.")

    def get_last_build(self) -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
        return self._built_df, self._built_cols

def _cbo(parent: ttk.Frame, label: str) -> ttk.Combobox:
    row = ttk.Frame(parent); row.pack(fill=tk.X, pady=2)
    ttk.Label(row, text=label, width=16).pack(side=tk.LEFT)
    cbo = ttk.Combobox(row, state="readonly")
    cbo.pack(side=tk.LEFT, fill=tk.X, expand=True)
    return cbo
