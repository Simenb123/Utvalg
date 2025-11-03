# views_main.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Set, Optional

import pandas as pd

from session import get_dataset, has_dataset
from models import Columns
from controller_core import DataControllerCore
from formatting import fmt_amount, fmt_int, fmt_date
from controller_sample import frames_for_sample, export_sample_to_temp_and_open
from views_dataset import open_dataset_window
from preferences import load_preferences
from ui_utils import enable_treeview_sort


class MainView:
    def __init__(self, parent: tk.Tk | tk.Toplevel):
        self.win = tk.Toplevel(parent)
        self.win.title("Utvalgsgenerator – Hovedvisning")
        self.win.geometry("1280x900")

        self.ctrl = DataControllerCore()
        self.cols = Columns()
        self._df_acc_show: pd.DataFrame = pd.DataFrame()
        self._df_tx_show: pd.DataFrame = pd.DataFrame()
        self.sample_ids: Set[str] = set()

        # ---- Topptoolbar ----
        tools = ttk.Frame(self.win); tools.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(tools, text="Åpne datasett …", command=lambda: open_dataset_window(self.win)).pack(side=tk.LEFT)
        ttk.Button(tools, text="Last datasett fra session", command=self._load_from_session).pack(side=tk.LEFT, padx=(6,0))

        # ---- Filterlinje ----
        filt = ttk.LabelFrame(self.win, text="Filtre og statistikk", padding=6)
        filt.pack(fill=tk.X, padx=8, pady=(0,6))

        ttk.Label(filt, text="Søk (konto/kontonavn):").pack(side=tk.LEFT)
        self.var_search = tk.StringVar()
        ent = ttk.Entry(filt, textvariable=self.var_search, width=30)
        ent.pack(side=tk.LEFT, padx=(6,12))
        ent.bind("<KeyRelease>", lambda _e: self.refresh_view())

        pref = load_preferences()
        self.var_dir = tk.StringVar(value=pref.default_direction or "Alle")
        ttk.Label(filt, text="Retning:").pack(side=tk.LEFT)
        self.cbo_dir = ttk.Combobox(filt, state="readonly", values=["Alle","Debet","Kredit"], width=8, textvariable=self.var_dir)
        self.cbo_dir.pack(side=tk.LEFT, padx=(6,12))
        self.cbo_dir.bind("<<ComboboxSelected>>", lambda _e: self.refresh_view())

        ttk.Label(filt, text="Min beløp:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(filt, width=12); self.ent_min.pack(side=tk.LEFT, padx=(4,6))
        ttk.Label(filt, text="Maks beløp:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(filt, width=12); self.ent_max.pack(side=tk.LEFT, padx=(4,12))
        ttk.Button(filt, text="Bruk", command=self.refresh_view).pack(side=tk.LEFT, padx=(0,8))

        self.var_basis = tk.StringVar(value="signed")
        ttk.Label(filt, text="Beløpsfilter på:").pack(side=tk.LEFT)
        ttk.Radiobutton(filt, text="Signert", value="signed", variable=self.var_basis, command=self.refresh_view).pack(side=tk.LEFT, padx=(6,0))
        ttk.Radiobutton(filt, text="ABS(|beløp|)", value="abs", variable=self.var_basis, command=self.refresh_view).pack(side=tk.LEFT, padx=(6,12))

        self.lbl_agg = ttk.Label(filt, text="Visning: linjer=0 | sum=0,00"); self.lbl_agg.pack(side=tk.LEFT, padx=(12,0))
        self.lbl_sel = ttk.Label(filt, text="Markert: linjer=0 | sum=0,00"); self.lbl_sel.pack(side=tk.LEFT, padx=(12,0))

        # ---- Split venstre/høyre ----
        split = ttk.Panedwindow(self.win, orient=tk.HORIZONTAL); split.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,6))

        # Venstre
        left = ttk.Frame(split); split.add(left, weight=3)
        ttk.Label(left, text="Kontopivot (linjer & sum) – velg én/flere kontoer").pack(anchor="w")
        self.tree_acc = ttk.Treeview(left, columns=("konto","navn","ant","sum"), show="headings", selectmode="extended")
        for cid, title, w, anc in (("konto","Kontonummer",120,"w"),("navn","Kontonavn",360,"w"),("ant","Linjer",100,"e"),("sum","Sum",140,"e")):
            self.tree_acc.heading(cid, text=title); self.tree_acc.column(cid, width=w, anchor=anc)
        self.tree_acc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(left, orient="vertical", command=self.tree_acc.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_acc.bind("<<TreeviewSelect>>", lambda _e: (self._update_marked_summary(), self._refresh_transactions()))
        enable_treeview_sort(self.tree_acc, {"konto":"int","navn":"text","ant":"int","sum":"amount"})

        # Høyre
        right = ttk.Frame(split); split.add(right, weight=5)
        ttk.Label(right, text="Transaksjoner for markerte kontoer").pack(anchor="w")
        self.tree_tx = ttk.Treeview(right, columns=("dato","bilag","tekst","belop","konto"), show="headings")
        self.tree_tx.heading("dato", text="Dato")
        self.tree_tx.heading("bilag", text="Bilag")
        self.tree_tx.heading("tekst", text="Tekst")
        self.tree_tx.heading("belop", text="Beløp")
        self.tree_tx.heading("konto", text="Konto")
        self.tree_tx.column("dato", width=100, anchor="w")
        self.tree_tx.column("bilag", width=120, anchor="w")
        self.tree_tx.column("tekst", width=420, anchor="w")
        self.tree_tx.column("belop", width=120, anchor="e")
        self.tree_tx.column("konto", width=80, anchor="e")
        self.tree_tx.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(right, orient="vertical", command=self.tree_tx.yview).pack(side=tk.RIGHT, fill=tk.Y)
        enable_treeview_sort(self.tree_tx, {"dato":"date","bilag":"text","tekst":"text","belop":"amount","konto":"int"})

        # Nederst
        bottom = ttk.LabelFrame(self.win, text="Trekk og eksport", padding=6)
        bottom.pack(fill=tk.X, padx=8, pady=(0,8))
        ttk.Label(bottom, text="Antall bilag:").pack(side=tk.LEFT)
        self.spin_n = tk.Spinbox(bottom, from_=1, to=100000, width=8); self.spin_n.delete(0, tk.END); self.spin_n.insert(0, "20")
        self.spin_n.pack(side=tk.LEFT, padx=(6,10))
        ttk.Label(bottom, text="Seed:").pack(side=tk.LEFT)
        self.ent_seed = ttk.Entry(bottom, width=10); self.ent_seed.pack(side=tk.LEFT, padx=(6,10))
        ttk.Button(bottom, text="Trekk bilag", command=self._draw_quick).pack(side=tk.LEFT, padx=(8,0))
        ttk.Button(bottom, text="Åpne utvalg i Excel nå", command=self._open_quick).pack(side=tk.RIGHT)

        if has_dataset():
            self._load_from_session()

    # ----------------------- datasett/filtre -----------------------
    def _parse_amount(self, s: str) -> Optional[float]:
        t = (s or "").strip().replace(" ", "").replace("kr","")
        if not t: return None
        t = t.replace(".", "").replace(",", ".")
        try: return float(t)
        except Exception: return None

    def _load_from_session(self):
        df, cols = get_dataset()
        if df is None or cols is None or df.empty:
            messagebox.showinfo("Datasett", "Ingen datasett i session. Åpne datasett først.")
            return
        self.cols = cols
        self.ctrl.init_prepared(df, cols)
        self.refresh_view()

    # ----------------------- visning -----------------------
    def refresh_view(self):
        if self.ctrl.df_clean is None:
            return
        self.ctrl.set_direction(self.var_dir.get())
        self.ctrl.set_amount_basis(self.var_basis.get())
        self.ctrl.set_amount_range(self._parse_amount(self.ent_min.get()), self._parse_amount(self.ent_max.get()))

        df_acc = self.ctrl.df_acc if self.ctrl.df_acc is not None else pd.DataFrame()
        if df_acc.empty:
            self._df_acc_show = df_acc
            for iid in self.tree_acc.get_children(): self.tree_acc.delete(iid)
            self.lbl_agg.config(text="Visning: linjer=0 | sum=0,00")
            self.lbl_sel.config(text="Markert: linjer=0 | sum=0,00")
            self._refresh_transactions()
            return

        q = (self.var_search.get() or "").strip().lower()
        if q:
            mask = (
                df_acc[self.cols.konto].astype(str).str.startswith(q, na=False) |
                df_acc[self.cols.kontonavn].astype(str).str.lower().str.contains(q, na=False)
            )
            df_acc = df_acc[mask]

        for iid in self.tree_acc.get_children(): self.tree_acc.delete(iid)
        tot_linjer, tot_sum = 0, 0.0
        for _, r in df_acc.iterrows():
            konto = str(r[self.cols.konto])
            navn = "" if pd.isna(r[self.cols.kontonavn]) else str(r[self.cols.kontonavn])
            ant = int(r.get("Antall", r.get("Linjer", 0)))
            sm = float(r["Sum"])
            self.tree_acc.insert("", tk.END, iid=f"{konto}|{navn}", values=(konto, navn, fmt_int(ant), fmt_amount(sm)))
            tot_linjer += ant; tot_sum += sm
        self._df_acc_show = df_acc.copy()
        self.lbl_agg.config(text=f"Visning: linjer={fmt_int(tot_linjer)} | sum={fmt_amount(tot_sum)}")
        self._update_marked_summary()
        self._refresh_transactions()

    def _selected_accounts(self) -> List[int]:
        out: List[int] = []
        for iid in self.tree_acc.selection():
            v = self.tree_acc.item(iid).get("values", [])
            if v:
                try: out.append(int(str(v[0])))
                except Exception: pass
        return out

    def _update_marked_summary(self):
        if self._df_acc_show is None or self._df_acc_show.empty:
            self.lbl_sel.config(text="Markert: linjer=0 | sum=0,00"); return
        sel = set(self.tree_acc.selection())
        if not sel:
            self.lbl_sel.config(text="Markert: linjer=0 | sum=0,00"); return
        keycol = self._df_acc_show[self.cols.konto].astype(str) + "|" + self._df_acc_show[self.cols.kontonavn].astype(str)
        dfm = self._df_acc_show[keycol.isin(sel)]
        m_linjer = int(dfm.get("Antall", dfm.get("Linjer", 0)).sum())
        m_sum = float(dfm["Sum"].sum()) if not dfm.empty else 0.0
        self.lbl_sel.config(text=f"Markert: linjer={fmt_int(m_linjer)} | sum={fmt_amount(m_sum)}")

    # ----------------------- transaksjoner -----------------------
    def _refresh_transactions(self):
        for iid in self.tree_tx.get_children(): self.tree_tx.delete(iid)
        df = self.ctrl.filtered_df()
        if df is None or df.empty:
            self._df_tx_show = pd.DataFrame(); return

        acc = self._selected_accounts()
        if not acc:
            self._df_tx_show = pd.DataFrame(); return
        c = self.cols
        df = df[df[c.konto].astype("Int64").astype(int).isin(acc)].copy()

        col_dato = getattr(self.cols, "dato", None)
        col_txt = getattr(self.cols, "tekst", None)
        if col_dato and col_dato not in df.columns:
            col_dato = None
        if col_txt and col_txt not in df.columns:
            col_txt = None

        for _, r in df.iterrows():
            dato = fmt_date(r[col_dato]) if col_dato else ""
            bilag = str(r[c.bilag])
            tekst = str(r[col_txt]) if col_txt else ""
            belop = fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0)
            konto = str(r[c.konto])
            self.tree_tx.insert("", tk.END, values=(dato, bilag, tekst, belop, konto))
        self._df_tx_show = df

    # ----------------------- quick sample -----------------------
    def _draw_quick(self):
        if self._df_tx_show is None or self._df_tx_show.empty:
            messagebox.showinfo("Ingen transaksjoner", "Marker konto(er) først.")
            return
        try:
            n = int(self.spin_n.get())
        except Exception:
            messagebox.showwarning("Antall", "Ugyldig antall bilag."); return
        c = self.cols
        uniq = self._df_tx_show[c.bilag].dropna().astype(str).drop_duplicates()
        if uniq.empty:
            messagebox.showwarning("Ingen bilag", "Finner ingen bilagsnummer i transaksjonene."); return
        seed_txt = self.ent_seed.get().strip()
        rng = int(seed_txt) if seed_txt else None
        pick = uniq.sample(n=min(n, len(uniq)), random_state=rng)
        self.sample_ids = set(pick.tolist())
        messagebox.showinfo("Trekk klart", f"Valgte {len(self.sample_ids)} bilag fra markert populasjon.")

    def _open_quick(self):
        if not self.sample_ids:
            self._draw_quick()
            if not self.sample_ids: return
        df_all, cols = self.ctrl.df_clean, self.cols
        accounts = self._selected_accounts()
        fullt, internt, summer = frames_for_sample(df_all, cols, self.sample_ids, accounts)
        try:
            path = export_sample_to_temp_and_open(fullt, internt, summer)
            messagebox.showinfo("Åpnet", f"Eksport skrevet til midlertidig fil og åpnet:\n{path}")
        except Exception as e:
            messagebox.showerror("Eksportfeil", str(e))


def open_main(parent: tk.Tk):
    MainView(parent)
