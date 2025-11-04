from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Tuple
import pandas as pd

from session import get_dataset, has_dataset
from controller_core import DataControllerCore
from models import Columns
from formatting import fmt_amount, fmt_int, fmt_date, parse_amount, parse_date
from preferences import load_preferences
from ui_utils import enable_treeview_sort
from views_bilag_drill import VoucherDrill
from views_motpost_konto import KontoMotpostDialog
import bus

class AnalysePage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self._parent_notebook = parent
        self.ctrl = DataControllerCore()
        self.cols = Columns()
        self._df_acc_show: pd.DataFrame = pd.DataFrame()
        self._df_tx_show: pd.DataFrame = pd.DataFrame()

        # Filterlinje
        filt = ttk.Frame(self, padding=8); filt.pack(fill=tk.X)
        ttk.Label(filt, text="Søk (konto/kontonavn):").pack(side=tk.LEFT)
        self.var_search = tk.StringVar(); ent = ttk.Entry(filt, textvariable=self.var_search, width=24)
        ent.pack(side=tk.LEFT, padx=(6,12)); ent.bind("<KeyRelease>", lambda _e: self.refresh_view())

        pref = load_preferences(); self.var_dir = tk.StringVar(value=pref.default_direction or "Alle")
        ttk.Label(filt, text="Retning:").pack(side=tk.LEFT)
        self.cbo_dir = ttk.Combobox(filt, state="readonly", values=["Alle","Debet","Kredit"], width=8, textvariable=self.var_dir)
        self.cbo_dir.pack(side=tk.LEFT, padx=(6,12)); self.cbo_dir.bind("<<ComboboxSelected>>", lambda _e: self.refresh_view())

        ttk.Label(filt, text="Min beløp:").pack(side=tk.LEFT); self.ent_min = ttk.Entry(filt, width=10); self.ent_min.pack(side=tk.LEFT, padx=(4,6))
        ttk.Label(filt, text="Maks beløp:").pack(side=tk.LEFT); self.ent_max = ttk.Entry(filt, width=10); self.ent_max.pack(side=tk.LEFT, padx=(4,12))
        ttk.Label(filt, text="Fra dato:").pack(side=tk.LEFT); self.ent_from = ttk.Entry(filt, width=12); self.ent_from.pack(side=tk.LEFT, padx=(4,6))
        ttk.Label(filt, text="Til dato:").pack(side=tk.LEFT); self.ent_to = ttk.Entry(filt, width=12); self.ent_to.pack(side=tk.LEFT, padx=(4,12))
        ttk.Button(filt, text="Bruk", command=self.refresh_view).pack(side=tk.LEFT)

        # Badge-agg
        self.lbl_agg = ttk.Label(filt, text="Visning: linjer=0 | sum=0,00"); self.lbl_agg.pack(side=tk.LEFT, padx=(16,0))
        self.lbl_sel = ttk.Label(filt, text="Markert: linjer=0 | sum=0,00"); self.lbl_sel.pack(side=tk.LEFT, padx=(12,0))

        # Delt view
        split = ttk.Panedwindow(self, orient=tk.HORIZONTAL); split.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        left = ttk.Frame(split); split.add(left, weight=3)
        ttk.Label(left, text="Kontopivot (linjer & sum) – marker konto(er)").pack(anchor="w")
        self.tree_acc = ttk.Treeview(left, columns=("konto","navn","ant","sum"), show="headings", selectmode="extended")
        for cid, title, w, anc in (("konto","Kontonummer",120,"w"),("navn","Kontonavn",360,"w"),("ant","Linjer",100,"e"),("sum","Sum",140,"e")):
            self.tree_acc.heading(cid, text=title); self.tree_acc.column(cid, width=w, anchor=anc)
        self.tree_acc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ttk.Scrollbar(left, orient="vertical", command=self.tree_acc.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_acc.bind("<<TreeviewSelect>>", lambda _e: (self._update_marked_summary(), self._refresh_transactions()))
        enable_treeview_sort(self.tree_acc, {"konto":"int","navn":"text","ant":"int","sum":"amount"})

        right = ttk.Frame(split); split.add(right, weight=5)
        topbar = ttk.Frame(right); topbar.pack(fill=tk.X)
        ttk.Label(topbar, text="Transaksjoner for markerte kontoer").pack(side=tk.LEFT)
        ttk.Button(topbar, text="Motpost (konto→fordeling)", command=self._open_konto_motpost).pack(side=tk.RIGHT, padx=(4,0))
        ttk.Button(topbar, text="Til utvalg (fanen)", command=self._send_to_utvalg_tab).pack(side=tk.RIGHT, padx=(4,0))

        self.tree_tx = ttk.Treeview(right, columns=("dato","bilag","tekst","belop","konto"), show="headings")
        self.tree_tx.heading("dato", text="Dato"); self.tree_tx.column("dato", width=100, anchor="w")
        self.tree_tx.heading("bilag", text="Bilag"); self.tree_tx.column("bilag", width=120, anchor="w")
        self.tree_tx.heading("tekst", text="Tekst"); self.tree_tx.column("tekst", width=420, anchor="w")
        self.tree_tx.heading("belop", text="Beløp"); self.tree_tx.column("belop", width=120, anchor="e")
        self.tree_tx.heading("konto", text="Konto"); self.tree_tx.column("konto", width=80, anchor="e")
        self.tree_tx.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ttk.Scrollbar(right, orient="vertical", command=self.tree_tx.yview).pack(side=tk.RIGHT, fill=tk.Y)
        enable_treeview_sort(self.tree_tx, {"dato":"date","bilag":"text","tekst":"text","belop":"amount","konto":"int"})
        self.tree_tx.bind("<Double-1>", self._drill_voucher)

        self.placeholder = ttk.Label(self, text="Ingen datasett i session. Gå til Datasett‑fanen og klikk «Bygg datasett».", foreground="#777")
        self.placeholder.pack(fill=tk.X, padx=12)
        self.bind_all("<<DatasetReady>>", self._on_dataset_ready)

    def get_current_period(self) -> Tuple[object, object]:
        return parse_date(self.ent_from.get()), parse_date(self.ent_to.get())

    def refresh_from_session(self):
        if not has_dataset():
            self.placeholder.lift(); return
        self.placeholder.pack_forget()
        df, cols = get_dataset()
        if df is None or cols is None: return
        self.cols = cols; self.ctrl.init_prepared(df, cols); self.refresh_view()

    def _on_dataset_ready(self, _e=None):
        self.refresh_from_session()
        try:
            nb = self._parent_notebook
            if isinstance(nb, ttk.Notebook): nb.select(self)
        except Exception: pass

    def _parse_amount(self, s: str) -> Optional[float]:
        s = (s or "").strip()
        if not s: return None
        val = parse_amount(s); return None if val is None else float(val)

    def _selected_accounts(self) -> List[int]:
        out: List[int] = []
        for iid in self.tree_acc.selection():
            v = self.tree_acc.item(iid).get("values", [])
            if v:
                try: out.append(int(str(v[0])))
                except Exception: pass
        return out

    def refresh_view(self):
        if self.ctrl.df_clean is None: return
        self.ctrl.set_direction(self.var_dir.get()); self.ctrl.set_amount_basis("signed")
        self.ctrl.set_amount_range(self._parse_amount(self.ent_min.get()), self._parse_amount(self.ent_max.get()))
        self.ctrl.set_date_range(parse_date(self.ent_from.get()), parse_date(self.ent_to.get()))
        self.ctrl.rebuild_pivot()
        df_acc = self.ctrl.df_acc if self.ctrl.df_acc is not None else pd.DataFrame()

        q = (self.var_search.get() or "").strip().lower()
        if not df_acc.empty and q:
            mask = (df_acc[self.cols.konto].astype(str).str.startswith(q, na=False) |
                    df_acc[self.cols.kontonavn].astype(str).str.lower().str.contains(q, na=False))
            df_acc = df_acc[mask]

        for iid in self.tree_acc.get_children(): self.tree_acc.delete(iid)
        tot_linjer, tot_sum = 0, 0.0
        for _, r in df_acc.iterrows():
            konto = str(r[self.cols.konto]); navn = "" if pd.isna(r[self.cols.kontonavn]) else str(r[self.cols.kontonavn])
            ant = int(r.get("Antall", r.get("Linjer", 0))); sm = float(r["Sum"])
            self.tree_acc.insert("", tk.END, iid=f"{konto}|{navn}", values=(konto, navn, fmt_int(ant), fmt_amount(sm))); tot_linjer += ant; tot_sum += sm
        self._df_acc_show = df_acc.copy(); self.lbl_agg.config(text=f"Visning: linjer={fmt_int(tot_linjer)} | sum={fmt_amount(tot_sum)}")
        self._update_marked_summary(); self._refresh_transactions()

    def _update_marked_summary(self):
        if self._df_acc_show is None or self._df_acc_show.empty:
            self.lbl_sel.config(text="Markert: linjer=0 | sum=0,00"); return
        sel = set(self.tree_acc.selection())
        if not sel: self.lbl_sel.config(text="Markert: linjer=0 | sum=0,00"); return
        keycol = self._df_acc_show[self.cols.konto].astype(str) + "|" + self._df_acc_show[self.cols.kontonavn].astype(str)
        dfm = self._df_acc_show[keycol.isin(sel)]
        m_linjer = int(dfm.get("Antall", dfm.get("Linjer", 0)).sum()); m_sum = float(dfm["Sum"].sum()) if not dfm.empty else 0.0
        self.lbl_sel.config(text=f"Markert: linjer={fmt_int(m_linjer)} | sum={fmt_amount(m_sum)}")

    def _refresh_transactions(self):
        for iid in self.tree_tx.get_children(): self.tree_tx.delete(iid)
        df = self.ctrl.filtered_df()
        if df is None or df.empty: self._df_tx_show = pd.DataFrame(); return
        acc = self._selected_accounts()
        if not acc: self._df_tx_show = pd.DataFrame(); return
        c = self.cols; df = df[df[c.konto].astype("Int64").astype(int).isin(acc)].copy()
        col_dato = getattr(self.cols, "dato", None); col_txt = getattr(self.cols, "tekst", None)
        if col_dato and col_dato not in df.columns: col_dato = None
        if col_txt and col_txt not in df.columns: col_txt = None
        for _, r in df.iterrows():
            dato = fmt_date(r[col_dato]) if col_dato else ""; bilag = str(r[c.bilag]); tekst = str(r[col_txt]) if col_txt else ""
            belop = fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0); konto = str(r[c.konto])
            self.tree_tx.insert("", tk.END, values=(dato, bilag, tekst, belop, konto))
        self._df_tx_show = df

    def _send_to_utvalg_tab(self):
        acc = self._selected_accounts()
        if not acc: messagebox.showinfo("Utvalg", "Marker konto(er) i venstre tabell først."); return
        page = bus.get_utvalg_page()
        if page is None: messagebox.showwarning("Utvalg", "Finner ikke Utvalg-fanen."); return
        page.load_initial(acc)
        try:
            if isinstance(self._parent_notebook, ttk.Notebook): self._parent_notebook.select(page)
        except Exception: pass

    def _drill_voucher(self, _evt=None):
        sel = self.tree_tx.selection()
        if not sel: return
        bilag = self.tree_tx.item(sel[0]).get("values", ["",""])[1]
        if not bilag: return
        df = self.ctrl.filtered_df()
        if df is None or df.empty: return
        VoucherDrill(self.winfo_toplevel(), df=df, cols=self.ctrl.cols, bilag_id=bilag)

    def _open_konto_motpost(self):
        acc = self._selected_accounts()
        if len(acc) != 1: messagebox.showinfo("Motpost", "Velg nøyaktig én konto for motpost-fordeling."); return
        df = self.ctrl.filtered_df()
        if df is None or df.empty: messagebox.showinfo("Motpost", "Ingen transaksjoner i gjeldende filter."); return
        KontoMotpostDialog(self.winfo_toplevel(), df=df, cols=self.ctrl.cols, konto=acc[0])
