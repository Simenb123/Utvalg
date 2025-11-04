from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict
import pandas as pd
import session
from models import Columns
from formatting import fmt_amount, fmt_int, parse_date
from views_selection_studio import ScopeCfg, BucketCfg, apply_scope, pivot_accounts, stratify
from excel_export import export_temp_excel

class UtvalgPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        self.df: pd.DataFrame | None = None
        self.cols: Columns | None = None
        self.initial_accounts: List[int] = []
        self.current_pop: pd.DataFrame | None = None
        self.underpops: Dict[str, pd.DataFrame] = {}
        self._build_ui()
        self.refresh_from_session()

    def load_initial(self, accounts: List[int]) -> None:
        self.initial_accounts = accounts or []
        expr = ",".join(sorted({str(a) for a in self.initial_accounts})) if self.initial_accounts else ""
        self.ent_accounts.delete(0, tk.END); self.ent_accounts.insert(0, expr)
        self._build_population()

    def refresh_from_session(self):
        df, cols = session.get_dataset()
        self.df, self.cols = df, cols
        self._toggle_placeholders()

    def _toggle_placeholders(self):
        if self.df is None or self.cols is None:
            self.placeholder.pack(fill=tk.BOTH, expand=True)
            self.main.pack_forget()
        else:
            self.placeholder.pack_forget()
            self.main.pack(fill=tk.BOTH, expand=True)

    def _build_ui(self):
        self.placeholder = ttk.Label(self, text="Ingen datasett i session. Gå til Datasett og bygg datasett.", foreground="#777")
        self.main = ttk.Frame(self)
        pan = ttk.Panedwindow(self.main, orient=tk.HORIZONTAL); pan.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        left = ttk.Frame(pan); right = ttk.Frame(pan); pan.add(left, weight=4); pan.add(right, weight=5)

        cfgf = ttk.LabelFrame(left, text="Populasjon – kriterier", padding=8); cfgf.pack(fill=tk.X)
        r1 = ttk.Frame(cfgf); r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Kontoer (6000-7999, 7210, 65*):", width=30).pack(side=tk.LEFT)
        self.ent_accounts = ttk.Entry(r1); self.ent_accounts.pack(side=tk.LEFT, fill=tk.X, expand=True)
        r2 = ttk.Frame(cfgf); r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="Retning:", width=30).pack(side=tk.LEFT)
        self.cbo_dir = ttk.Combobox(r2, state="readonly", width=12, values=["Alle","Debet","Kredit"]); self.cbo_dir.set("Alle")
        self.cbo_dir.pack(side=tk.LEFT, padx=(0,8))
        ttk.Label(r2, text="Beløp min/maks:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(r2, width=10); self.ent_min.pack(side=tk.LEFT, padx=4)
        self.ent_max = ttk.Entry(r2, width=10); self.ent_max.pack(side=tk.LEFT, padx=4)
        ttk.Label(r2, text="Terskel gjelder:").pack(side=tk.LEFT, padx=(8,4))
        self.cbo_apply = ttk.Combobox(r2, state="readonly", width=10, values=["Alle","Debet","Kredit"]); self.cbo_apply.set("Alle")
        self.cbo_apply.pack(side=tk.LEFT, padx=(0,8))
        self.var_abs = tk.BooleanVar(value=True); ttk.Checkbutton(r2, text="Bruk |beløp| ved 'Alle'", variable=self.var_abs).pack(side=tk.LEFT)
        r3 = ttk.Frame(cfgf); r3.pack(fill=tk.X, pady=2)
        ttk.Label(r3, text="Fra dato:", width=30).pack(side=tk.LEFT); self.ent_from = ttk.Entry(r3, width=12); self.ent_from.pack(side=tk.LEFT, padx=4)
        ttk.Label(r3, text="Til dato:").pack(side=tk.LEFT); self.ent_to = ttk.Entry(r3, width=12); self.ent_to.pack(side=tk.LEFT, padx=4)
        ttk.Button(r3, text="Bygg populasjon", command=self._build_population).pack(side=tk.RIGHT)

        self.lbl_badges = ttk.Label(left, text="Aktiv populasjon: –", foreground="#666"); self.lbl_badges.pack(fill=tk.X, padx=2, pady=(2,4))
        self.lbl_pop = ttk.Label(left, text="Populasjon: linjer=0, unike bilag=0, sum=0,00"); self.lbl_pop.pack(anchor="w", pady=(2,0))

        pvf = ttk.LabelFrame(left, text="Konto‑pivot (populasjon)", padding=6); pvf.pack(fill=tk.BOTH, expand=True, pady=(6,4))
        self.tree_acc = ttk.Treeview(pvf, columns=("konto","navn","linjer","sum"), show="headings")
        for cid, txt, w, anc in (("konto","Konto",100,"w"),("navn","Kontonavn",260,"w"),("linjer","Linjer",80,"e"),("sum","Sum",120,"e")):
            self.tree_acc.heading(cid, text=txt); self.tree_acc.column(cid, width=w, anchor=anc)
        self.tree_acc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ttk.Scrollbar(pvf, orient="vertical", command=self.tree_acc.yview).pack(side=tk.RIGHT, fill=tk.Y)

        upf = ttk.LabelFrame(right, text="Underpopulasjoner", padding=6); upf.pack(fill=tk.X)
        r4 = ttk.Frame(upf); r4.pack(fill=tk.X, pady=2)
        ttk.Label(r4, text="Navn:", width=8).pack(side=tk.LEFT); self.ent_up_name = ttk.Entry(r4, width=18); self.ent_up_name.pack(side=tk.LEFT, padx=(0,8)); self.ent_up_name.insert(0, "UP1")
        ttk.Label(r4, text="Kontoer:", width=10).pack(side=tk.LEFT); self.ent_up_accounts = ttk.Entry(r4); self.ent_up_accounts.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(r4, text="Beløp min/maks:").pack(side=tk.LEFT, padx=(8,4)); self.ent_up_min = ttk.Entry(r4, width=10); self.ent_up_min.pack(side=tk.LEFT)
        self.ent_up_max = ttk.Entry(r4, width=10); self.ent_up_max.pack(side=tk.LEFT, padx=(4,0)); ttk.Button(r4, text="Legg til/oppdater", command=self._add_update_underpop).pack(side=tk.LEFT, padx=6)

        self.tree_up = ttk.Treeview(upf, columns=("navn","linjer","bilag","sum"), show="headings", height=6)
        for cid, txt, w, anc in (("navn","Navn",140,"w"),("linjer","Linjer",90,"e"),("bilag","Unike bilag",110,"e"),("sum","Sum",120,"e")):
            self.tree_up.heading(cid, text=txt); self.tree_up.column(cid, width=w, anchor=anc)
        self.tree_up.pack(fill=tk.X, pady=(4,0))

        buck = ttk.LabelFrame(right, text="Stratifisering på gjeldende valg", padding=6); buck.pack(fill=tk.X, pady=(6,0))
        r5 = ttk.Frame(buck); r5.pack(fill=tk.X, pady=2)
        ttk.Label(r5, text="Antall bøtter:").pack(side=tk.LEFT); self.ent_nb = ttk.Entry(r5, width=8); self.ent_nb.insert(0, "0"); self.ent_nb.pack(side=tk.LEFT, padx=4)
        ttk.Label(r5, text="Metode:").pack(side=tk.LEFT, padx=(8,2)); self.cbo_method = ttk.Combobox(r5, state="readonly", width=10, values=["quantile","equal"]); self.cbo_method.set("quantile"); self.cbo_method.pack(side=tk.LEFT)
        ttk.Label(r5, text="Basis:").pack(side=tk.LEFT, padx=(8,2)); self.cbo_basis = ttk.Combobox(r5, state="readonly", width=10, values=["abs","signed"]); self.cbo_basis.set("abs"); self.cbo_basis.pack(side=tk.LEFT)
        ttk.Button(r5, text="Bygg bøtter", command=self._build_buckets).pack(side=tk.RIGHT)

        self.tree_b = ttk.Treeview(buck, columns=("range","bilag","sum"), show="headings", height=6)
        for cid, txt, w, anc in (("range","Beløpsintervall",320,"w"),("bilag","Unike bilag",120,"e"),("sum","Sum",120,"e")):
            self.tree_b.heading(cid, text=txt); self.tree_b.column(cid, width=w, anchor=anc)
        self.tree_b.pack(fill=tk.X, pady=(4,0))

        act = ttk.LabelFrame(right, text="Trekk og eksport", padding=6); act.pack(fill=tk.X, pady=(6,0))
        rr = ttk.Frame(act); rr.pack(fill=tk.X, pady=2)
        ttk.Label(rr, text="Antall bilag:").pack(side=tk.LEFT); self.ent_n = ttk.Entry(rr, width=8); self.ent_n.insert(0, "20"); self.ent_n.pack(side=tk.LEFT, padx=4)
        ttk.Label(rr, text="Seed:").pack(side=tk.LEFT, padx=(8,2)); self.ent_seed = ttk.Entry(rr, width=8); self.ent_seed.pack(side=tk.LEFT)
        ttk.Button(act, text="Trekk fra valgt (UP/Pop)", command=self._sample_from_current).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(act, text="Åpne i Excel (temp)", command=self._export_all_temp).pack(side=tk.RIGHT)

    def _parse_amount(self, s: str) -> Optional[float]:
        s = (s or "").strip()
        if not s: return None
        s2 = s.replace(" ", "").replace("kr", "").replace(".", "").replace(",", ".")
        try: return float(s2)
        except Exception: return None

    def _update_badges(self):
        parts = []
        parts.append(f"Retning={self.cbo_dir.get() or 'Alle'}")
        mn = self._parse_amount(self.ent_min.get()); mx = self._parse_amount(self.ent_max.get())
        if mn is not None or mx is not None:
            a = "Beløp=" + (f"≥{mn:.0f}" if mn is not None else "") + (".." if (mn is not None or mx is not None) else "") + (f"≤{mx:.0f}" if mx is not None else "")
            parts.append(a)
        parts.append(f"Terskel gjelder={self.cbo_apply.get() or 'Alle'}")
        parts.append("|beløp|=Ja" if self.var_abs.get() else "|beløp|=Nei")
        expr = (self.ent_accounts.get() or "").strip()
        if expr: parts.append(f"Kontoer={expr}")
        if (self.ent_from.get() or "").strip(): parts.append(f"Fra={self.ent_from.get().strip()}")
        if (self.ent_to.get() or "").strip(): parts.append(f"Til={self.ent_to.get().strip()}")
        self.lbl_badges.config(text="Aktiv populasjon: " + ("; ".join(parts) if parts else "–"))

    def _build_population(self):
        self.refresh_from_session()
        if self.df is None or self.cols is None:
            messagebox.showinfo("Ingen datasett", "Bygg/bruk datasett først."); return
        cfg = ScopeCfg(
            name="Populasjon",
            accounts_expr=self.ent_accounts.get().strip(), direction=self.cbo_dir.get().strip() or "Alle",
            min_amount=self._parse_amount(self.ent_min.get()), max_amount=self._parse_amount(self.ent_max.get()),
            apply_to=self.cbo_apply.get().strip() or "Alle", use_abs=True,
            date_from=parse_date(self.ent_from.get()), date_to=parse_date(self.ent_to.get())
        )
        self.current_pop = apply_scope(self.df, self.cols, cfg); self._update_badges(); self._refresh_pop_summary(); self._refresh_pop_pivot()

    def _refresh_pop_summary(self):
        if self.current_pop is None or self.current_pop.empty:
            self.lbl_pop.config(text="Populasjon: linjer=0, unike bilag=0, sum=0,00"); return
        c = self.cols; linjer = len(self.current_pop); bilag = self.current_pop[c.bilag].astype(str).nunique(); summ = float(self.current_pop[c.belop].sum())
        self.lbl_pop.config(text=f"Populasjon: linjer={fmt_int(linjer)}, unike bilag={fmt_int(bilag)}, sum={fmt_amount(summ)}")

    def _refresh_pop_pivot(self):
        for iid in self.tree_acc.get_children(): self.tree_acc.delete(iid)
        pv = pivot_accounts(self.current_pop, self.cols) if self.current_pop is not None else pd.DataFrame()
        if pv is None or pv.empty: return
        c = self.cols
        for _, r in pv.iterrows():
            self.tree_acc.insert("", tk.END, values=(str(r[c.konto]), str(r[c.kontonavn] or ""), fmt_int(int(r["Linjer"])), fmt_amount(float(r["Sum"])))

    def _add_update_underpop(self):
        if self.current_pop is None or self.current_pop.empty:
            messagebox.showinfo("Tom populasjon", "Bygg populasjon først."); return
        name = (self.ent_up_name.get().strip() or "UP1"); accexpr = self.ent_up_accounts.get().strip()
        miv = self._parse_amount(self.ent_up_min.get()); mav = self._parse_amount(self.ent_up_max.get())
        cfg = ScopeCfg(name=name, accounts_expr=accexpr, direction="Alle", min_amount=miv, max_amount=mav, apply_to="Alle", use_abs=True,
                       date_from=parse_date(self.ent_from.get()), date_to=parse_date(self.ent_to.get()))
        up = apply_scope(self.current_pop, self.cols, cfg); self.underpops[name] = up; self._refresh_underpop_list()

    def _refresh_underpop_list(self):
        for iid in self.tree_up.get_children(): self.tree_up.delete(iid)
        c = self.cols
        for name, d in self.underpops.items():
            linjer = len(d); bilag = d[c.bilag].astype(str).nunique() if not d.empty else 0; summ = float(d[c.belop].sum()) if not d.empty else 0.0
            self.tree_up.insert("", tk.END, iid=name, values=(name, fmt_int(linjer), fmt_int(bilag), fmt_amount(summ)))

    def _get_current_df(self) -> Optional[pd.DataFrame]:
        sel = self.tree_up.selection()
        return self.underpops.get(sel[0]) if sel else self.current_pop

    def _build_buckets(self):
        d = self._get_current_df()
        if d is None or d.empty:
            messagebox.showinfo("Ingen data", "Velg en underpopulasjon (eller populasjonen) med innhold."); return
        try: n = int(self.ent_nb.get().strip())
        except Exception: messagebox.showwarning("Bøtter", "Ugyldig antall bøtter."); return
        bcfg = BucketCfg(n=int(n), method=self.cbo_method.get(), basis=self.cbo_basis.get())
        tab = stratify(d, self.cols, bcfg)
        for iid in self.tree_b.get_children(): self.tree_b.delete(iid)
        for _, r in tab.iterrows():
            self.tree_b.insert("", tk.END, values=(str(r["Bucket"]), fmt_int(int(r["Unike bilag"])), fmt_amount(float(r["Sum"]))))

    def _sample_from_current(self):
        d = self._get_current_df()
        if d is None or d.empty:
            messagebox.showinfo("Ingen data", "Velg en underpopulasjon (eller populasjonen) med innhold."); return
        try: n = int(self.ent_n.get().strip())
        except Exception: messagebox.showwarning("Antall", "Ugyldig antall."); return
        seed = None; s = (self.ent_seed.get() or "").strip()
        if s:
            try: seed = int(s)
            except Exception: seed = None
        c = self.cols; unike = d[c.bilag].dropna().astype(str).drop_duplicates()
        if unike.empty: messagebox.showwarning("Ingen bilag", "Finner ingen bilagsnummer i datasettet."); return
        n = max(1, min(n, len(unike))); self.sample_ids = set(unike.sample(n=n, random_state=seed).tolist())
        messagebox.showinfo("Trekk klart", f"Valgte {n} bilag i gjeldende datasett.")

    def _export_all_temp(self):
        if self.current_pop is None or self.current_pop.empty:
            messagebox.showinfo("Tom populasjon", "Bygg populasjon først."); return
        sheets: Dict[str, pd.DataFrame] = {}; c = self.cols
        sheets["Populasjon"] = self.current_pop.copy(); sheets["Konto_pivot_pop"] = pivot_accounts(self.current_pop, c)
        d = self._get_current_df(); from views_selection_studio import BucketCfg as BCfg
        tab = stratify(d, c, BCfg(n=0))
        if tab is not None and not tab.empty: sheets["Buckets_valgt"] = tab
        for name, up in self.underpops.items():
            sheets[f"UP_{name}"] = up.copy(); sheets[f"Konto_pivot_{name}"] = pivot_accounts(up, c)
        if hasattr(self, "sample_ids") and self.sample_ids:
            valgte = self.current_pop[self.current_pop[c.bilag].astype(str).isin(self.sample_ids)].copy(); sheets["Trekk_bilag"] = valgte
        export_temp_excel(sheets, prefix="Utvalg_")
