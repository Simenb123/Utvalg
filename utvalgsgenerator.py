"""
Utvalgsgenerator – enkel Tkinter‑app (v1.2.1)
---------------------------------------------
• Laster inn hovedbok (Excel/CSV)
• Autodetekterer header‑rad og lar deg overstyre
• Gjetter kolonner (kan justeres manuelt)
• Viser pivotert kontovisning i **tabell** (multi‑select)
• **LIVE‑filter for retning**: Alle / Debet / Kredit
• Beløpsintervall og underpopulasjoner i eget utvalgs‑vindu
• Trekker bilag (med valgfri seed) og eksporterer til Excel

Avhengigheter: pandas, numpy, chardet, openpyxl
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd
import chardet

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ----------------------------- HJELP ------------------------------------
DECIMAL_COMMA = True  # beløp vises med komma som desimal og MED tusenskiller (mellomrom)

@dataclass
class Columns:
    konto: str = ""
    kontonavn: str = ""
    bilag: str = ""
    belop: str = ""


def les_fil(path: Path) -> pd.DataFrame:
    """Les fil *uten* å anta header (header=None). Alt som str for robusthet."""
    suf = path.suffix.lower()
    if suf in {".xlsx", ".xls"}:
        return pd.read_excel(path, engine="openpyxl", header=None, dtype=str)
    if suf == ".csv":
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig", header=None, dtype=str)
        except Exception:
            pass
        enc = chardet.detect(path.read_bytes()).get("encoding") or "latin1"
        for sep in (";", ","):
            try:
                return pd.read_csv(path, sep=sep, encoding=enc, header=None, dtype=str)
            except Exception:
                continue
    raise ValueError("Filen må være .xlsx, .xls eller .csv")


def gjett_kolonner(cols: list[str]) -> Columns:
    low = [str(c).lower() for c in cols]

    def first(pats: list[str]) -> str:
        for c, l in zip(cols, low):
            for p in pats:
                if re.search(p, l):
                    return c
        return ""

    return Columns(
        konto=first([r"\bkonto\b|konto.*nr|kontonummer|account ?no|acct ?no"]),
        kontonavn=first([r"kontonavn|account ?name|acct ?name|beskrivelse|tekst|description|name"]),
        bilag=first([r"\bbilag\b|voucher|dokument|dok\.? ?nr|document ?no|journal|voucher ?no|bilagsnr"]),
        belop=first([r"bel[oø]p|amount|sum(?!mary)|debet|kredit|debit|credit|saldo"]),
    )


def til_float(s: pd.Series) -> pd.Series:
    """Konverter typiske norske beløpsformater til float."""
    return (
        s.astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("kr", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .apply(lambda x: np.nan if x == "" else x)
        .astype(float)
    )


def fmt_amount(x: float | int | str) -> str:
    """Formater beløp med tusenskiller og komma (norsk), eller US-format hvis DECIMAL_COMMA=False."""
    try:
        xv = float(x)
    except (TypeError, ValueError):
        return ""
    if DECIMAL_COMMA:
        # 1) formater US: 12,345.67  2) bytt , -> mellomrom og . -> ,
        txt = f"{xv:,.2f}"
        return txt.replace(",", " ").replace(".", ",")
    else:
        return f"{xv:,.2f}"


# ---------------------- HEADER-DETEKSJON -------------------------------

def _is_numeric_like(x: str) -> bool:
    s = str(x or "").strip()
    for ch in " .,+-":
        s = s.replace(ch, "")
    return s.isdigit()


def detect_header_row(raw: pd.DataFrame, max_scan: int = 50) -> int:
    n = min(max_scan, len(raw))
    best_idx, best_score = 0, -1
    keywords = ["konto", "kontonummer", "kontonavn", "bilag", "beløp", "belop", "amount", "sum"]
    for i in range(n):
        row = raw.iloc[i].astype(str).fillna("")
        non_numeric = sum(not _is_numeric_like(v) and v != "" for v in row)
        unique_vals = len(set(v.strip().lower() for v in row if v.strip()))
        key_hits = sum(1 for v in row for k in keywords if k in v.lower())
        score = non_numeric * 2 + unique_vals + key_hits * 3
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx


def apply_header(raw: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    cols = raw.iloc[header_idx].astype(str).fillna("").str.strip()
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for c in cols:
        base = c or "kol"
        cnt = seen.get(base, 0)
        new_cols.append(base if cnt == 0 else f"{base}_{cnt}")
        seen[base] = cnt + 1
    df = raw.iloc[header_idx + 1:].reset_index(drop=True)
    df.columns = new_cols
    return df

# --------------------------- GUI KLASSE ---------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Utvalgsgenerator – Hovedbok → Bilagsutvalg")
        self.geometry("1100x740")
        self.minsize(980, 640)

        self.df_raw: pd.DataFrame | None = None   # uten header
        self.df: pd.DataFrame | None = None       # med header
        self.df_clean: pd.DataFrame | None = None # renset m/typer
        self.cols = Columns()
        self.df_acc: pd.DataFrame | None = None   # pivot pr. konto (med gjeldende filter)
        self.header_row = 0

        self._build_ui()

    # --------------------------- UI ------------------------------------
    def _build_ui(self):
        # Top: fil + kolonnevalg
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        self.path_var = tk.StringVar()
        ttk.Button(top, text="Åpne fil…", command=self.open_file).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text="Oppfrisk", command=self.refresh_all).pack(side=tk.LEFT)

        # Kolonnevalg
        colfrm = ttk.LabelFrame(self, text="Kolonner", padding=8)
        colfrm.pack(fill=tk.X, padx=8, pady=(0,8))

        self.cbo_konto = ttk.Combobox(colfrm, state="readonly")
        self.cbo_kontonavn = ttk.Combobox(colfrm, state="readonly")
        self.cbo_bilag = ttk.Combobox(colfrm, state="readonly")
        self.cbo_belop = ttk.Combobox(colfrm, state="readonly")

        for i, (lbl, cbo) in enumerate([
            ("Kontonummer:", self.cbo_konto),
            ("Kontonavn:", self.cbo_kontonavn),
            ("Bilagsnummer:", self.cbo_bilag),
            ("Beløp:", self.cbo_belop),
        ]):
            ttk.Label(colfrm, text=lbl, width=16).grid(row=0, column=2*i, sticky=tk.W, padx=(0,4))
            cbo.grid(row=0, column=2*i+1, sticky="ew", padx=(0,12))
            colfrm.grid_columnconfigure(2*i+1, weight=1)

        ttk.Button(colfrm, text="Bygg kontoliste", command=self.build_accounts).grid(row=0, column=8, padx=4)

        # Header-rad kontroll
        ttk.Label(colfrm, text="Header-rad (1=første):", width=16).grid(row=1, column=0, sticky=tk.W, pady=(8,0))
        self.spin_header = tk.Spinbox(colfrm, from_=1, to=9999, width=8)
        self.spin_header.grid(row=1, column=1, sticky="w", pady=(8,0))
        ttk.Button(colfrm, text="Oppdag", command=self.detect_and_apply_header).grid(row=1, column=2, sticky="w", pady=(8,0))
        ttk.Button(colfrm, text="Bruk header", command=self.apply_chosen_header).grid(row=1, column=3, sticky="w", pady=(8,0))
        ttk.Button(colfrm, text="Forhåndsvis rader", command=self.preview_rows).grid(row=1, column=4, sticky="w", pady=(8,0))

        # Midt: søk + tabell
        mid = ttk.Frame(self, padding=8)
        mid.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sfrm = ttk.Frame(left)
        sfrm.pack(fill=tk.X)
        ttk.Label(sfrm, text="Filter:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        ent = ttk.Entry(sfrm, textvariable=self.search_var)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ent.bind("<KeyRelease>", lambda e: self.refresh_account_list())
        # Debet/Kredit-valg (live)
        ttk.Label(sfrm, text="Retning:").pack(side=tk.LEFT, padx=(8,2))
        self.direction_var = tk.StringVar(value="Alle")
        self.cbo_dc = ttk.Combobox(sfrm, state="readonly", width=8, values=["Alle","Debet","Kredit"], textvariable=self.direction_var)
        self.cbo_dc.pack(side=tk.LEFT)
        self.cbo_dc.bind("<<ComboboxSelected>>", lambda e: self.recompute_accounts())

        lstfrm = ttk.LabelFrame(left, text="Konti (multi‑select)")
        lstfrm.pack(fill=tk.BOTH, expand=True, pady=(6,0))

        # Treeview med faktiske kolonner
        self.tree_accounts = ttk.Treeview(lstfrm, columns=("konto","navn","ant","sum"), show="headings", selectmode="extended")
        self.tree_accounts.heading("konto", text="Kontonummer")
        self.tree_accounts.heading("navn", text="Kontonavn")
        self.tree_accounts.heading("ant", text="Linjer")
        self.tree_accounts.heading("sum", text="Sum")
        self.tree_accounts.column("konto", width=120, anchor="w")
        self.tree_accounts.column("navn", width=260, anchor="w")
        self.tree_accounts.column("ant", width=70, anchor="e")
        self.tree_accounts.column("sum", width=140, anchor="e")
        self.tree_accounts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lstfrm, orient=tk.VERTICAL, command=self.tree_accounts.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_accounts.configure(yscrollcommand=sb.set)

        # Høyre: Info + handlinger
        right = ttk.LabelFrame(mid, text="Handlinger", padding=8)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(8,0))

        self.lbl_rows = ttk.Label(right, text="Ingen fil lastet.")
        self.lbl_rows.pack(anchor="w")

        frmN = ttk.Frame(right)
        frmN.pack(anchor="w", pady=(8,0))
        ttk.Label(frmN, text="Antall bilag som skal trekkes:").grid(row=0, column=0, sticky="w")
        self.spin_n = tk.Spinbox(frmN, from_=1, to=100000, width=8)
        self.spin_n.grid(row=0, column=1, padx=(6,0))
        self.spin_n.delete(0, tk.END)
        self.spin_n.insert(0, "20")

        self.seed_var = tk.StringVar(value="")
        chk = ttk.Checkbutton(right, text="Fast trekk (seed)", command=self.toggle_seed)
        chk.pack(anchor="w", pady=(6,0))
        self.ent_seed = ttk.Entry(right, textvariable=self.seed_var, state="disabled", width=16)
        self.ent_seed.pack(anchor="w")

        # Beløpsintervall
        rng = ttk.LabelFrame(right, text="Beløpsintervall", padding=6)
        rng.pack(fill=tk.X, pady=(10,0))
        ttk.Label(rng, text="Min:").grid(row=0, column=0, sticky="w")
        self.ent_min = ttk.Entry(rng, width=12)
        self.ent_min.grid(row=0, column=1, padx=4)
        ttk.Label(rng, text="Maks:").grid(row=0, column=2, sticky="w")
        self.ent_max = ttk.Entry(rng, width=12)
        self.ent_max.grid(row=0, column=3, padx=4)
        ttk.Label(rng, text="Del i N intervaller:").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6,0))
        self.cbo_bins = ttk.Combobox(rng, state="readonly", values=["Ingen", 2,3,4,5,6,8,10], width=10)
        self.cbo_bins.grid(row=1, column=2, columnspan=2, sticky="w", pady=(6,0))
        self.cbo_bins.set("Ingen")

        # Oppsummering live
        self.lbl_agg = ttk.Label(right, text="Visning: linjer=0 | sum=0,00")
        self.lbl_agg.pack(anchor="w", pady=(8,0))

        ttk.Button(right, text="Trekk utvalg", command=self.open_selection_window).pack(fill=tk.X, pady=(12,4))
        ttk.Button(right, text="Eksporter til Excel", command=self.export_excel).pack(fill=tk.X)

        self.status = ttk.Label(self, relief=tk.SUNKEN, anchor="w")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # -------------------------- FIL & KOLONNER --------------------------
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Velg hovedbok (Excel/CSV)",
            filetypes=[
                ("Excel/CSV", "*.xlsx *.xls *.csv"),
                ("Excel", "*.xlsx *.xls"),
                ("CSV", "*.csv"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return
        self.path_var.set(path)
        try:
            self.df_raw = les_fil(Path(path))
        except Exception as e:
            messagebox.showerror("Feil ved lesing", str(e))
            return
        self.after_load()

    def after_load(self):
        assert self.df_raw is not None
        self.header_row = detect_header_row(self.df_raw)
        self.df = apply_header(self.df_raw, self.header_row)

        total_rows = len(self.df_raw)
        self.spin_header.config(to=max(1, total_rows))
        self.spin_header.delete(0, tk.END)
        self.spin_header.insert(0, str(self.header_row + 1))

        cols = list(self.df.columns)
        for cbo in (self.cbo_konto, self.cbo_kontonavn, self.cbo_bilag, self.cbo_belop):
            cbo["values"] = cols
        g = gjett_kolonner(cols)
        if g.konto: self.cbo_konto.set(g.konto)
        if g.kontonavn: self.cbo_kontonavn.set(g.kontonavn)
        if g.bilag: self.cbo_bilag.set(g.bilag)
        if g.belop: self.cbo_belop.set(g.belop)

        self.lbl_rows.config(text=f"Rader: {len(self.df):,}")
        self.status.config(text=f"Fil lastet. Header antatt på rad {self.header_row+1}. Juster ved behov og trykk 'Bruk header'.")

    def refresh_all(self):
        if not self.path_var.get():
            return
        try:
            self.df_raw = les_fil(Path(self.path_var.get()))
            self.after_load()
        except Exception as e:
            messagebox.showerror("Feil", str(e))

    def detect_and_apply_header(self):
        if self.df_raw is None:
            return
        self.header_row = detect_header_row(self.df_raw)
        self.spin_header.delete(0, tk.END)
        self.spin_header.insert(0, str(self.header_row + 1))
        self.df = apply_header(self.df_raw, self.header_row)
        self.after_header_applied()

    def apply_chosen_header(self):
        if self.df_raw is None:
            return
        try:
            user_row = max(1, int(self.spin_header.get())) - 1
        except ValueError:
            messagebox.showwarning("Header", "Ugyldig radnummer.")
            return
        self.header_row = user_row
        self.df = apply_header(self.df_raw, self.header_row)
        self.after_header_applied()

    def after_header_applied(self):
        cols = list(self.df.columns)
        for cbo in (self.cbo_konto, self.cbo_kontonavn, self.cbo_bilag, self.cbo_belop):
            cbo["values"] = cols
        g = gjett_kolonner(cols)
        if g.konto: self.cbo_konto.set(g.konto)
        if g.kontonavn: self.cbo_kontonavn.set(g.kontonavn)
        if g.bilag: self.cbo_bilag.set(g.bilag)
        if g.belop: self.cbo_belop.set(g.belop)
        self.lbl_rows.config(text=f"Rader: {len(self.df):,}")
        self.status.config(text=f"Header satt til rad {self.header_row+1}. Velg kolonner og bygg kontoliste.")

    def preview_rows(self):
        """Vis et vindu med forhåndsvisning av de første radene fra råfilen.
        Dobbeltklikk en rad for å sette den som header (1-basert) og lukk vinduet.
        """
        if self.df_raw is None:
            messagebox.showinfo("Ingen fil", "Åpne en fil først.")
            return
        top = tk.Toplevel(self)
        top.title("Forhåndsvisning – dobbeltklikk rad for å sette header")
        top.geometry("900x500")
        ttk.Label(top, text="Tips: Dobbeltklikk på raden som er header. Den settes i feltet 'Header-rad'.").pack(fill=tk.X, padx=8, pady=6)

        frame = ttk.Frame(top)
        frame.pack(fill=tk.BOTH, expand=True)

        max_rows = 150
        dfp = self.df_raw.head(max_rows).fillna("")
        ncols = dfp.shape[1]
        cols = [f"kol{i+1}" for i in range(ncols)]
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120, stretch=True)
        for i in range(len(dfp)):
            vals = [str(v) for v in dfp.iloc[i].tolist()]
            tree.insert("", tk.END, iid=str(i), values=vals)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        def on_double(_event=None):
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            self.spin_header.delete(0, tk.END)
            self.spin_header.insert(0, str(idx + 1))
            top.destroy()
        tree.bind("<Double-1>", on_double)

        btnbar = ttk.Frame(top)
        btnbar.pack(fill=tk.X, pady=6)
        ttk.Button(btnbar, text="Sett som header og bruk", command=lambda: (on_double(), self.apply_chosen_header())).pack(side=tk.RIGHT, padx=8)


    # -------------------------- KONTOLISTE ------------------------------
    def build_accounts(self):
        if self.df is None:
            return
        self.cols = Columns(
            konto=self.cbo_konto.get(),
            kontonavn=self.cbo_kontonavn.get(),
            bilag=self.cbo_bilag.get(),
            belop=self.cbo_belop.get(),
        )
        missing = [k for k, v in self.cols.__dict__.items() if not v]
        if missing:
            messagebox.showwarning("Mangler kolonner", f"Velg kolonner for: {', '.join(missing)}")
            return

        df = self.df.copy()
        try:
            df[self.cols.belop] = til_float(df[self.cols.belop])
        except Exception:
            messagebox.showwarning("Beløp", "Klarte ikke å konvertere beløp – sjekk kolonnevalg.")
            return
        df[self.cols.konto] = (
            df[self.cols.konto]
            .astype(str)
            .str.extract(r"(\d+)", expand=False)
            .astype("Int64")
        )
        if self.cols.kontonavn not in df.columns:
            df[self.cols.kontonavn] = ""
        df = df.dropna(subset=[self.cols.konto, self.cols.bilag, self.cols.belop])

        self.df_clean = df
        self.recompute_accounts()
        self.status.config(text="Kontoliste oppdatert.")

    def recompute_accounts(self):
        """Bygg konto‑pivot ut fra df_clean og valgt retning (Alle/Debet/Kredit)."""
        if self.df_clean is None:
            return
        c = self.cols
        df = self.df_clean
        dir_sel = (self.direction_var.get() or "Alle").lower()
        if dir_sel.startswith("debet"):
            dfv = df[df[c.belop] > 0]
        elif dir_sel.startswith("kredit"):
            dfv = df[df[c.belop] < 0]
        else:
            dfv = df
        grp = (
            dfv.groupby([c.konto, c.kontonavn])[c.belop]
            .agg(Antall="count", Sum="sum")
            .reset_index()
            .sort_values([c.konto, c.kontonavn])
        )
        self.df_acc = grp
        self.refresh_account_list()

    def refresh_account_list(self):
        # Oppdater kontotabellen (Treeview)
        for i in self.tree_accounts.get_children():
            self.tree_accounts.delete(i)
        if self.df_acc is None:
            self.lbl_agg.config(text="Visning: linjer=0 | sum=0,00")
            return
        q = (self.search_var.get() or "").strip().lower()
        dfv = self.df_acc.copy()
        if q:
            def match(row):
                konto = str(row[self.cols.konto])
                navn = str(row[self.cols.kontonavn] or "").lower()
                return konto.startswith(q) or (q in navn)
            dfv = dfv[[match(r) for _, r in dfv.iterrows()]]
        tot_linjer = 0
        tot_sum = 0.0
        for _, r in dfv.iterrows():
            konto = str(r[self.cols.konto])
            navn = str(r[self.cols.kontonavn] or "")
            ant = int(r["Antall"]) if not pd.isna(r["Antall"]) else 0
            s = float(r["Sum"]) if not pd.isna(r["Sum"]) else 0.0
            self.tree_accounts.insert("", tk.END, iid=konto+"|"+navn, values=(konto, navn, f"{ant:,}", fmt_amount(s)))
            tot_linjer += ant
            tot_sum += s
        self.lbl_agg.config(text=f"Visning: linjer={tot_linjer:,} | sum={fmt_amount(tot_sum)}")

    def selected_accounts(self) -> list[int]:
        sel = []
        for iid in self.tree_accounts.selection():
            vals = self.tree_accounts.item(iid).get('values', [])
            if vals:
                try:
                    sel.append(int(str(vals[0])))
                except Exception:
                    continue
        return sel

    # -------------------------- UTVALG ----------------------------------
    def toggle_seed(self):
        if self.ent_seed["state"] == "disabled":
            self.ent_seed.config(state="normal")
        else:
            self.ent_seed.config(state="disabled")
            self.seed_var.set("")

    def parse_amount_entry(self, s: str) -> float | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(til_float(pd.Series([s]))[0])
        except Exception:
            try:
                return float(str(s).replace(" ", "").replace(".", "").replace(",", "."))
            except Exception:
                return None

    def open_selection_window(self):
        if self.df_clean is None or self.df_acc is None:
            return
        accounts = self.selected_accounts()
        if not accounts:
            messagebox.showinfo("Velg kontoer", "Marker én eller flere kontoer i tabellen.")
            return
        c = self.cols
        df = self.df_clean

        # Retningsfilter må også gjelde her
        dir_sel = (self.direction_var.get() or "Alle").lower()
        if dir_sel.startswith("debet"):
            df = df[df[c.belop] > 0]
        elif dir_sel.startswith("kredit"):
            df = df[df[c.belop] < 0]

        # Beløpsintervall
        min_v = self.parse_amount_entry(self.ent_min.get())
        max_v = self.parse_amount_entry(self.ent_max.get())
        mask = df[c.konto].isin(accounts)
        if min_v is not None:
            mask &= df[c.belop] >= min_v
        if max_v is not None:
            mask &= df[c.belop] <= max_v
        pop = df[mask].copy()
        if pop.empty:
            messagebox.showwarning("Tomt", "Ingen rader for valgte kontoer innen valgte filtre.")
            return

        view = (
            pop.groupby([c.konto, c.kontonavn])[c.belop]
            .agg(Linjer='count', Sum='sum')
            .reset_index()
            .sort_values([c.konto])
        )

        win = tk.Toplevel(self)
        win.title("Utvalgsvisning – valgte kontoer")
        win.geometry("900x560")

        topbar = ttk.Frame(win)
        topbar.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(topbar, text=f"Rader i populasjon: {len(pop):,}").pack(side=tk.LEFT)
        ttk.Label(
            topbar,
            text=(
                "Underpopulasjoner: deler beløp i N kvantiler (tilnærmet likt antall rader per bøtte).\n"
                "Tall i tabellen under viser antall unike bilag per bøtte."
            ),
        ).pack(side=tk.RIGHT)

        # Underpopulasjoner (valgfrie)
        bins_opt = self.cbo_bins.get()
        nb = int(bins_opt) if (isinstance(bins_opt, str) and bins_opt.isdigit()) else (bins_opt if isinstance(bins_opt, int) else 0)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        tree = ttk.Treeview(frame, columns=("konto","navn","linjer","sum"), show="headings")
        for cid, txt, w, anc in (
            ("konto","Kontonummer",120,"w"),
            ("navn","Kontonavn",260,"w"),
            ("linjer","Linjer",70,"e"),
            ("sum","Sum",120,"e"),
        ):
            tree.heading(cid, text=txt)
            tree.column(cid, width=w, anchor=anc)
        for _, r in view.iterrows():
            tree.insert("", tk.END, values=(str(r[c.konto]), str(r[c.kontonavn] or ""), f"{int(r['Linjer']):,}", fmt_amount(float(r['Sum']))))
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        if nb and nb > 0:
            qs = np.linspace(0, 1, nb+1)
            edges = pop[c.belop].quantile(qs).to_list()
            for i in range(1, len(edges)):
                if edges[i] <= edges[i-1]:
                    edges[i] = edges[i-1] + 0.01
            labels = [f"{fmt_amount(edges[i])} – {fmt_amount(edges[i+1])}" for i in range(nb)]
            cats = pd.cut(pop[c.belop], bins=edges, include_lowest=True, labels=labels)
            btab = pop.assign(Bucket=cats).groupby('Bucket')[c.bilag].nunique().reset_index(name='Unike bilag')

            buckf = ttk.LabelFrame(win, text="Underpopulasjoner (kvantilbasert)")
            buckf.pack(fill=tk.BOTH, expand=False, padx=8, pady=6)
            bucket_tree = ttk.Treeview(buckf, columns=("range","bilag"), show="headings")
            bucket_tree.heading("range", text="Beløpsintervall")
            bucket_tree.heading("bilag", text="Unike bilag")
            bucket_tree.column("range", width=300, anchor="w")
            bucket_tree.column("bilag", width=120, anchor="e")
            for _, r in btab.iterrows():
                bucket_tree.insert("", tk.END, values=(str(r['Bucket']), f"{int(r['Unike bilag']):,}"))
            bucket_tree.pack(fill=tk.X)

        btnbar = ttk.Frame(win)
        btnbar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btnbar, text="Trekk bilag nå", command=lambda: self._do_sample(pop, win)).pack(side=tk.RIGHT)

    def _do_sample(self, pop: pd.DataFrame, win: tk.Toplevel | None = None):
        c = self.cols
        unike = pop[c.bilag].dropna().astype(str).drop_duplicates()
        if unike.empty:
            messagebox.showwarning("Ingen bilag", "Finner ingen bilagsnummer i populasjonen.")
            return
        try:
            n = int(self.spin_n.get())
        except ValueError:
            messagebox.showwarning("Antall", "Ugyldig antall bilag.")
            return
        n = max(1, min(n, len(unike)))
        seed = None
        if self.ent_seed["state"] == "normal":
            try:
                seed = int(self.seed_var.get())
            except Exception:
                seed = None
        valgte = unike.sample(n=n, random_state=seed)
        self.sample_ids = set(valgte.tolist())

        ant_rader = (pop[c.bilag].astype(str).isin(self.sample_ids)).sum()
        messagebox.showinfo("Trekk klart", f"Valgte {n} bilag. Linjer i utvalget: {ant_rader:,}.")
        self.status.config(text=f"Trekk klart – {n} bilag valgt.")
        if win is not None:
            try:
                win.lift()
            except Exception:
                pass

    def export_excel(self):
        if self.df is None:
            return
        if not hasattr(self, "sample_ids") or not self.sample_ids:
            messagebox.showinfo("Ingen trekk", "Trekk bilag før eksport.")
            return

        c = self.cols
        df = self.df
        sample_ids = self.sample_ids

        fullt = df[df[c.bilag].astype(str).isin(sample_ids)].copy()

        accounts = self.selected_accounts()
        inter = fullt[fullt[c.konto].isin(accounts)].copy()

        summer = (
            inter.groupby(c.bilag)[c.belop]
            .agg(Sum_i_valgte_kontoer="sum", Linjer_i_valgte_kontoer="count")
            .reset_index()
        )

        path = filedialog.asksaveasfilename(
            title="Lagre Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Bilag_uttrekk_{len(sample_ids)}.xlsx",
        )
        if not path:
            return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as xw:
                fullt.to_excel(xw, "Fullt_bilagsutvalg", index=False)
                inter.to_excel(xw, "Kun_valgte_kontoer", index=False)
                summer.to_excel(xw, "Bilag_summer", index=False)
        except Exception as e:
            messagebox.showerror("Feil ved lagring", str(e))
            return

        messagebox.showinfo("Lagret", f"Excel eksportert til\n{path}")
        self.status.config(text=f"Eksportert: {path}")


# ------------------------------ SELFTESTS -------------------------------

def _run_selftests():
    # til_float
    s = pd.Series(["1 234,50", "1.234.567,89", "-123,00", "kr 1 000,00", ""])
    conv = til_float(s)
    assert abs(conv.iloc[0] - 1234.50) < 1e-6
    assert abs(conv.iloc[1] - 1234567.89) < 1e-6
    assert abs(conv.iloc[2] + 123.00) < 1e-6
    assert abs(conv.iloc[3] - 1000.00) < 1e-6
    assert np.isnan(conv.iloc[4])

    # fmt_amount – nå med tusenskiller (mellomrom) og komma
    assert fmt_amount(1234.5) == "1 234,50"
    assert fmt_amount(1234567.89) == "1 234 567,89"

    # header detection
    raw = pd.DataFrame([
        ["metadata", "should", "skip"],
        ["Kontonummer", "Kontonavn", "Beløp"],
        ["1000", "Bankinnskudd", "1 000,00"],
    ])
    idx = detect_header_row(raw)
    assert idx == 1
    df = apply_header(raw, idx)
    assert list(df.columns) == ["Kontonummer", "Kontonavn", "Beløp"]
    assert df.shape[0] == 1


# ------------------------------ MAIN -----------------------------------
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        try:
            _run_selftests()
            print("Selftests OK")
            sys.exit(0)
        except AssertionError as e:
            print("Selftests FAILED:", e)
            sys.exit(1)
    try:
        App().mainloop()
    except Exception as e:
        messagebox.showerror("Uventet feil", str(e))
        sys.exit(1)
