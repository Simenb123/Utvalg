from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

from io_utils import fmt_amount
from treeutils import attach_sorting
from models import BucketConfig


def open_selection(parent, ctrl, accounts, n_suggested: int, seed: int | None):
    """Utvalgsvindu med underpopulasjon (bøtter) og trekk-knapp."""
    pop = ctrl.selection_pop(accounts)
    if pop.empty:
        messagebox.showwarning("Tomt", "Ingen rader for valgte kontoer innen valgte filtre.")
        return

    win = tk.Toplevel(parent); win.title("Utvalg – valgte kontoer"); win.geometry("1050x700")

    topbar = ttk.Frame(win); topbar.pack(fill=tk.X, padx=8, pady=6)
    ttk.Label(topbar, text=f"Populasjon: linjer {len(pop):,} | netto {fmt_amount(pop[ctrl.cols.belop].sum())} | |beløp| {fmt_amount(pop[ctrl.cols.belop].abs().sum())}").pack(side=tk.LEFT)

    # Oppsummering per konto
    frame = ttk.LabelFrame(win, text="Oppsummering per konto"); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
    tree = ttk.Treeview(frame, columns=("konto","navn","linjer","sum"), show="headings")
    for cid, txt, w, anc in (("konto","Kontonummer",120,"w"),
                             ("navn","Kontonavn",260,"w"),
                             ("linjer","Linjer",80,"e"),
                             ("sum","Sum (netto)",140,"e")):
        tree.heading(cid, text=txt); tree.column(cid, width=w, anchor=anc)
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=vsb.set); tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    view = pop.groupby([ctrl.cols.konto, ctrl.cols.kontonavn])[ctrl.cols.belop].agg(Linjer="count", Sum="sum").reset_index()
    for _, r in view.sort_values([ctrl.cols.konto]).iterrows():
        tree.insert("", tk.END, values=(str(r[ctrl.cols.konto]), str(r[ctrl.cols.kontonavn] or ""), f"{int(r['Linjer']):,}", fmt_amount(float(r['Sum']))))
    attach_sorting(tree, {"konto":"int","navn":"str","linjer":"int","sum":"amount"})

    # Underpopulasjoner
    buck = ttk.LabelFrame(win, text="Underpopulasjoner (stratifisering av beløp)"); buck.pack(fill=tk.BOTH, expand=False, padx=8, pady=6)
    row1 = ttk.Frame(buck); row1.pack(fill=tk.X)
    ttk.Label(row1, text="Antall intervaller:").pack(side=tk.LEFT)
    nscale = tk.Scale(row1, from_=0, to=12, orient="horizontal", length=220, showvalue=True); nscale.pack(side=tk.LEFT, padx=(6,10))
    ttk.Label(row1, text="Metode:").pack(side=tk.LEFT, padx=(12,2))
    method_var = tk.StringVar(value="quantile")
    ttk.Combobox(row1, state="readonly", values=["quantile", "equal"], textvariable=method_var, width=10).pack(side=tk.LEFT)
    ttk.Label(row1, text="Grunnlag:").pack(side=tk.LEFT, padx=(12,2))
    basis_var = tk.StringVar(value="abs")
    ttk.Combobox(row1, state="readonly", values=["abs", "signed"], textvariable=basis_var, width=10).pack(side=tk.LEFT)

    info = ttk.Label(buck, anchor="w",
                     text="Forklaring: 'quantile' ≈ likt antall linjer pr. bøtte. 'equal' = like kr‑spenn.\n'basis=abs' bruker |beløp|; 'signed' bruker beløp.")
    info.pack(fill=tk.X, pady=(4,0))

    tbl = ttk.Treeview(buck, columns=("fra","til","linjer","bilag","sum_netto","sum_abs","andel_l","andel_s"), show="headings")
    for cid, txt, w, anc in (
        ("fra","Fra",150,"e"), ("til","Til",150,"e"), ("linjer","Linjer",80,"e"),
        ("bilag","Unike bilag",110,"e"), ("sum_netto","Sum (netto)",140,"e"),
        ("sum_abs","Sum |beløp|",140,"e"), ("andel_l","Andel linjer",110,"e"), ("andel_s","Andel sum| |",120,"e")
    ):
        tbl.heading(cid, text=txt); tbl.column(cid, width=w, anchor=anc)
    tbl.pack(fill=tk.X, padx=2, pady=4)
    attach_sorting(tbl, {"fra":"amount","til":"amount","linjer":"int","bilag":"int","sum_netto":"amount","sum_abs":"amount","andel_l":"float","andel_s":"float"})

    def upd_buckets(_e=None):
        tbl.delete(*tbl.get_children())
        n = int(nscale.get())
        if n <= 0: return
        cfg = BucketConfig(n_buckets=n, method=method_var.get(), basis=basis_var.get())
        tab = ctrl.buckets_table(pop, cfg)
        for _, r in tab.iterrows():
            tbl.insert("", tk.END, values=(
                str(r["Fra"]), str(r["Til"]), f"{int(r['Linjer']):,}", f"{int(r['Unike bilag']):,}",
                fmt_amount(float(r["Sum (netto)"])), fmt_amount(float(r["Sum |beløp|"])),
                f"{float(r['Andel linjer'])*100:,.2f} %".replace(",", " ").replace(".", ","),
                f"{float(r['Andel sum| |'])*100:,.2f} %".replace(",", " ").replace(".", ","),
            ))
    nscale.bind("<ButtonRelease-1>", upd_buckets)
    for v in (method_var, basis_var): v.trace_add("write", lambda *_: upd_buckets())

    # Trekk-knapp
    btnbar = ttk.Frame(win); btnbar.pack(fill=tk.X, padx=8, pady=8)
    nvar = tk.IntVar(value=int(n_suggested))
    ttk.Label(btnbar, text="Antall å trekke:").pack(side=tk.LEFT)
    tk.Spinbox(btnbar, from_=1, to=100000, textvariable=nvar, width=8).pack(side=tk.LEFT, padx=(4,12))
    ttk.Button(btnbar, text="Trekk bilag nå", command=lambda: _do_sample(ctrl, pop, nvar.get(), seed, win)).pack(side=tk.RIGHT)


def _do_sample(ctrl, pop: pd.DataFrame, n: int, seed: int | None, win):
    chosen, rows = ctrl.do_sample(pop, n, seed)
    if not chosen:
        messagebox.showwarning("Ingen bilag", "Finner ingen bilagsnummer i populasjonen.")
        return
    messagebox.showinfo("Trekk klart", f"Valgte {len(chosen)} bilag. Linjer i utvalget: {rows:,}.")
    try: win.lift()
    except Exception: pass
