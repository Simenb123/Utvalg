from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Sequence, Tuple
import pandas as pd
from pathlib import Path
import tempfile, os

try:
    from formatting import format_number_no
except Exception:
    def format_number_no(x, d=2):
        try: return f"{float(x):,.{d}f}".replace(",", " ").replace(".", ",")
        except Exception: return str(x)

def _compute_motpost(df: pd.DataFrame, accounts: Sequence[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if df is None or df.empty or not accounts:
        return pd.DataFrame(), pd.DataFrame()
    need = {"Bilag","Konto","Beløp"}
    if not need.issubset(df.columns): return pd.DataFrame(), pd.DataFrame()
    A = df[df["Konto"].astype(str).isin(set(map(str, accounts)))][["Bilag","Konto","Beløp"]].rename(columns={"Konto":"Konto_A","Beløp":"Beløp_A"})
    if A.empty: return pd.DataFrame(), pd.DataFrame()
    B = df[["Bilag","Konto","Beløp"]].rename(columns={"Konto":"Konto_B","Beløp":"Beløp_B"})
    pairs = pd.merge(A, B, on="Bilag", how="inner"); pairs = pairs[pairs["Konto_A"]!=pairs["Konto_B"]]
    if pairs.empty: return pd.DataFrame(), pd.DataFrame()
    bilag = pairs.groupby(["Konto_A","Konto_B","Bilag"], as_index=False)["Beløp_B"].sum().rename(columns={"Beløp_B":"Sum_mot_bilag"})
    summ = bilag.groupby(["Konto_A","Konto_B"], as_index=False).agg(Sum_mot=("Sum_mot_bilag","sum"), Antall_bilag=("Bilag","nunique"))
    names = df[["Konto","Kontonavn"]].drop_duplicates()
    summ = (summ.merge(names.rename(columns={"Konto":"Konto_A","Kontonavn":"Kontonavn"}), on="Konto_A", how="left")
                 .merge(names.rename(columns={"Konto":"Konto_B","Kontonavn":"Motnavn"}), on="Konto_B", how="left")
                 .rename(columns={"Konto_A":"Konto","Konto_B":"Motkonto"})
                 .sort_values(["Konto","Sum_mot","Antall_bilag","Motkonto"], ascending=[True,False,False,True]))
    bilag = bilag.rename(columns={"Konto_A":"Konto","Konto_B":"Motkonto"}).sort_values(["Konto","Motkonto","Bilag"])
    return summ, bilag

def show_motpost_konto(master, df: pd.DataFrame, accounts: Sequence[str], bus=None) -> None:
    win = tk.Toplevel(master); win.title("Motpost – fordeling"); win.geometry("1100x600"); win.transient(master)
    top = ttk.Frame(win); top.pack(fill="x", padx=8, pady=6)
    ttk.Label(top, text=f"Konto(er): {', '.join(accounts)}").pack(side="left")
    btn1 = ttk.Button(top, text="Eksporter resultat"); btn2=ttk.Button(top, text="Eksporter bilagsliste")
    btn2.pack(side="right"); btn1.pack(side="right", padx=(6,0))

    pan = ttk.Panedwindow(win, orient="vertical"); pan.pack(fill="both", expand=True, padx=8, pady=6)
    up = ttk.Frame(pan); up.columnconfigure(0, weight=1); up.rowconfigure(0, weight=1)
    lo = ttk.Frame(pan); lo.columnconfigure(0, weight=1); lo.rowconfigure(0, weight=1)

    cols = ["Konto","Kontonavn","Motkonto","Motnavn","Sum_mot","Antall_bilag"]
    tv = ttk.Treeview(up, columns=cols, show="headings")
    for c in cols: tv.heading(c, text=c); tv.column(c, width=(120 if c in ("Konto","Motkonto") else 240 if c in ("Kontonavn","Motnavn") else 120), anchor=("e" if c in ("Sum_mot","Antall_bilag") else "w"))
    vss = ttk.Scrollbar(up, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=vss.set)
    tv.grid(row=0, column=0, sticky="nsew"); vss.grid(row=0, column=1, sticky="ns")

    cols2 = ["Konto","Motkonto","Bilag","Sum_mot_bilag"]
    tv2 = ttk.Treeview(lo, columns=cols2, show="headings")
    for c in cols2: tv2.heading(c, text=c); tv2.column(c, width=(120 if c in ("Konto","Motkonto","Bilag") else 120), anchor=("e" if c == "Sum_mot_bilag" else "w"))
    vss2 = ttk.Scrollbar(lo, orient="vertical", command=tv2.yview); tv2.configure(yscrollcommand=vss2.set)
    tv2.grid(row=0, column=0, sticky="nsew"); vss2.grid(row=0, column=1, sticky="ns")

    pan.add(up, weight=3); pan.add(lo, weight=2)

    try:
        summ, bilag = _compute_motpost(df, accounts)
    except Exception as e:
        messagebox.showerror("Motpost", f"Feil under beregning: {e}"); win.destroy(); return

    if not summ.empty:
        for _, r in summ.iterrows():
            tv.insert("", "end", values=[r.get("Konto",""), r.get("Kontonavn",""), r.get("Motkonto",""), r.get("Motnavn",""), format_number_no(r.get("Sum_mot",0.0),2), int(r.get("Antall_bilag",0) or 0)])
    if not bilag.empty:
        for _, r in bilag.iterrows():
            tv2.insert("", "end", values=[r.get("Konto",""), r.get("Motkonto",""), r.get("Bilag",""), format_number_no(r.get("Sum_mot_bilag",0.0),2)])

    def export_result():
        if summ is None or summ.empty: messagebox.showinfo("Motpost","Ingen data"); return
        path = Path(tempfile.gettempdir()) / "motpost_resultat.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xw: summ.to_excel(xw, index=False, sheet_name="Motpost_fordeling")
        os.startfile(str(path))
    def export_bilag():
        if bilag is None or bilag.empty: messagebox.showinfo("Motpost","Ingen data"); return
        path = Path(tempfile.gettempdir()) / "motpost_bilag.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as xw: bilag.to_excel(xw, index=False, sheet_name="Motpost_bilag")
        os.startfile(str(path))
    btn1.configure(command=export_result); btn2.configure(command=export_bilag)