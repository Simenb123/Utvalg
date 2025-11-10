from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Dict, Any
import pandas as pd
from pathlib import Path
import tempfile

from session import get_dataset
from models import Columns
from formatting import parse_amount, parse_date, fmt_amount
import io_utils as iou
from ab_analysis import match_same_amount, two_sum_match
from ui_utils import apply_zebra, autosize_tree
from excel_export import export_selection
import ab_prefs as prefs

def _canon(s: str) -> str:
    s = (s or '').strip().lower()
    trans = str.maketrans({'æ':'ae','ø':'o','å':'a','-':'','_':'',' ':'','é':'e','ö':'o','ä':'a'})
    s = s.translate(trans)
    return ''.join(ch for ch in s if ch.isalnum())

def _find(headers, *aliases) -> str:
    lowmap = { _canon(h): h for h in headers }
    for a in aliases:
        ca = _canon(a)
        if ca in lowmap:
            return lowmap[ca]
    for a in aliases:
        ca = _canon(a)
        for k, orig in lowmap.items():
            if k.startswith(ca):
                return orig
    return ''

class ABPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent, padding=8)
        self.dfB: Optional[pd.DataFrame] = None
        self.cB = Columns()
        self.cA = Columns()
        self.pairs: Optional[pd.DataFrame] = None
        self.summary: Optional[pd.DataFrame] = None
        self.pairs_two_a2b: Optional[pd.DataFrame] = None
        self.summary_two_a2b: Optional[pd.DataFrame] = None
        self.pairs_two_b2a: Optional[pd.DataFrame] = None
        self.summary_two_b2a: Optional[pd.DataFrame] = None
        self.stats_last: Dict = {}
        self._current_preset: Optional[str] = None

        # Topp: last inn B
        top = ttk.LabelFrame(self, text="Datasett B"); top.pack(fill=tk.X)
        r1 = ttk.Frame(top); r1.pack(fill=tk.X)
        ttk.Button(r1, text="Åpne B…", command=self._open_b).pack(side=tk.LEFT)
        self.var_path = tk.StringVar(value="")
        ttk.Entry(r1, textvariable=self.var_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,8))
        ttk.Button(r1, text="Bygg B", command=self._build_b).pack(side=tk.RIGHT)

        self.map_frame = ttk.Frame(top); self.map_frame.pack(fill=tk.X, pady=(6,0))
        self.cbo_vars: Dict[str, tk.StringVar] = {}
        self.cbos: Dict[str, ttk.Combobox] = {}
        fields = ['konto','kontonavn','bilag','belop','dato','valutakode','kundenr','leverandornr']
        friendly = {'belop':'Beløp','valutakode':'Valutakode','kontonavn':'Kontonavn','kundenr':'Kundenr','leverandornr':'Leverandørnr'}
        for f in fields:
            row = ttk.Frame(self.map_frame); row.pack(fill=tk.X, pady=2)
            lab = friendly.get(f, f.capitalize())
            ttk.Label(row, text=f"{lab}:").pack(side=tk.LEFT, padx=(0,8))
            var = tk.StringVar()
            self.cbo_vars[f] = var
            cbo = ttk.Combobox(row, textvariable=var, state="readonly")
            cbo.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.cbos[f] = cbo

        # Presets (lagre/last/slett + import/eksport)
        pre = ttk.LabelFrame(self, text="Oppsett (presets)"); pre.pack(fill=tk.X, pady=(8,0))
        rpre = ttk.Frame(pre); rpre.pack(fill=tk.X)
        ttk.Label(rpre, text="Navn:").pack(side=tk.LEFT)
        self.var_preset = tk.StringVar()
        ttk.Entry(rpre, textvariable=self.var_preset, width=28).pack(side=tk.LEFT, padx=(6,8))
        ttk.Button(rpre, text="Lagre/oppdater", command=self._preset_save).pack(side=tk.LEFT)
        ttk.Button(rpre, text="Last", command=self._preset_load).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(rpre, text="Slett", command=self._preset_delete).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(rpre, text="Oppdater liste", command=self._preset_refresh).pack(side=tk.LEFT, padx=(12,0))
        ttk.Label(rpre, text="Tilgjengelige:").pack(side=tk.LEFT, padx=(12,4))
        self.var_preset_list = tk.StringVar(value="; ".join(prefs.list_presets()))
        ttk.Label(rpre, textvariable=self.var_preset_list).pack(side=tk.LEFT, expand=True, fill=tk.X)

        rpre2 = ttk.Frame(pre); rpre2.pack(fill=tk.X, pady=(4,0))
        ttk.Button(rpre2, text="Eksporter presets…", command=self._preset_export).pack(side=tk.LEFT)
        ttk.Button(rpre2, text="Importer presets…", command=self._preset_import).pack(side=tk.LEFT, padx=(6,0))

        # Midt: kontroller
        ctrl = ttk.LabelFrame(self, text="Krysshint A ↔ B"); ctrl.pack(fill=tk.X, pady=(8,0))
        self.var_opposite = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Motsatt fortegn (A + B ≈ 0)", variable=self.var_opposite).pack(side=tk.LEFT)
        ttk.Label(ctrl, text="Beløpstoleranse (± kr):").pack(side=tk.LEFT, padx=(12,0))
        self.var_tol_amount = tk.StringVar(value="0")
        ttk.Entry(ctrl, textvariable=self.var_tol_amount, width=10).pack(side=tk.LEFT, padx=(6,0))
        ttk.Label(ctrl, text="Beløpstoleranse %:").pack(side=tk.LEFT, padx=(12,0))
        self.var_tol_pct = tk.StringVar(value="0")
        ttk.Entry(ctrl, textvariable=self.var_tol_pct, width=6).pack(side=tk.LEFT, padx=(6,0))
        ttk.Label(ctrl, text="Datotoleranse (± dager):").pack(side=tk.LEFT, padx=(12,0))
        self.var_tol_days = tk.StringVar(value="0")
        ttk.Entry(ctrl, textvariable=self.var_tol_days, width=6).pack(side=tk.LEFT, padx=(6,0))
        # nøkkelkrav
        self.var_currency = tk.BooleanVar(value=False)
        self.var_customer = tk.BooleanVar(value=False)
        self.var_supplier = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Krev lik valutakode", variable=self.var_currency).pack(side=tk.LEFT, padx=(12,0))
        ttk.Checkbutton(ctrl, text="Krev lik Kundenr", variable=self.var_customer).pack(side=tk.LEFT, padx=(6,0))
        ttk.Checkbutton(ctrl, text="Krev lik Leverandørnr", variable=self.var_supplier).pack(side=tk.LEFT, padx=(6,0))
        # 1:1 dedup
        self.var_unique_1to1 = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Dedup 1:1 (ikke gjenbruk A/B)", variable=self.var_unique_1to1).pack(side=tk.LEFT, padx=(12,0))
        ttk.Button(ctrl, text="Likt beløp", command=self._run_same_amount).pack(side=tk.LEFT, padx=(12,0))
        ttk.Button(ctrl, text="Eksporter", command=self._export).pack(side=tk.LEFT, padx=(6,0))

        # Two-sum kontroller
        two = ttk.LabelFrame(self, text="Two-sum (to motposter ≈ én motpost)"); two.pack(fill=tk.X, pady=(8,0))
        ttk.Label(two, text="Retning:").pack(side=tk.LEFT)
        self.var_dir = tk.StringVar(value="A2B")
        ttk.Combobox(two, textvariable=self.var_dir, state="readonly", width=8, values=["A2B","B2A"]).pack(side=tk.LEFT, padx=(6,12))
        ttk.Label(two, text="Maks par per mål:").pack(side=tk.LEFT)
        self.var_cap = tk.IntVar(value=200)
        ttk.Entry(two, textvariable=self.var_cap, width=8).pack(side=tk.LEFT, padx=(6,12))
        self.var_dedup_per_target = tk.BooleanVar(value=True)
        ttk.Checkbutton(two, text="Ikke gjenbruk kildelinjer pr. mål", variable=self.var_dedup_per_target).pack(side=tk.LEFT, padx=(6,12))
        ttk.Button(two, text="Kjør two-sum", command=self._run_two_sum).pack(side=tk.LEFT)
        ttk.Button(two, text="Eksporter", command=self._export).pack(side=tk.LEFT, padx=(6,0))

        # Hurtigfilter på oppsummeringer + 'Åpne alle for valgt'
        fsum = ttk.LabelFrame(self, text="Hurtigfilter oppsummering"); fsum.pack(fill=tk.X, pady=(8,0))
        rfs1 = ttk.Frame(fsum); rfs1.pack(fill=tk.X)
        ttk.Label(rfs1, text="Beløp min:").pack(side=tk.LEFT)
        self.var_sum_min = tk.StringVar(); ttk.Entry(rfs1, textvariable=self.var_sum_min, width=12).pack(side=tk.LEFT, padx=(6,6))
        ttk.Label(rfs1, text="max:").pack(side=tk.LEFT)
        self.var_sum_max = tk.StringVar(); ttk.Entry(rfs1, textvariable=self.var_sum_max, width=12).pack(side=tk.LEFT, padx=(0,12))
        ttk.Button(rfs1, text="Filtrer (likt beløp)", command=self._apply_summary_filter_same).pack(side=tk.LEFT)
        ttk.Button(rfs1, text="Åpne alle par for valgt beløp", command=self._open_all_pairs_for_selected_summary_same).pack(side=tk.LEFT, padx=(6,0))
        ttk.Label(rfs1, text=" | ").pack(side=tk.LEFT, padx=(6,6))
        ttk.Button(rfs1, text="Filtrer (two-sum)", command=self._apply_summary_filter_two).pack(side=tk.LEFT)
        ttk.Button(rfs1, text="Åpne alle par for valgt mål", command=self._open_all_pairs_for_selected_summary_two).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(rfs1, text="Nullstill", command=self._clear_summary_filters).pack(side=tk.LEFT, padx=(12,0))

        # Nederst: visninger
        res = ttk.Panedwindow(self, orient=tk.HORIZONTAL); res.pack(fill=tk.BOTH, expand=True, pady=(8,0))
        left = ttk.Frame(res); right = ttk.Frame(res)
        res.add(left, weight=5); res.add(right, weight=7)

        ttk.Label(left, text="Oppsummering (likt beløp)").pack(anchor="w")
        self.tree_sum = ttk.Treeview(left, columns=("belop","a","b","par"), show="headings", height=10)
        for cid, title, w, anc in (("belop","Beløp",140,"e"),("a","Antall A",100,"e"),("b","Antall B",100,"e"),("par","Par",100,"e")):
            self.tree_sum.heading(cid, text=title); self.tree_sum.column(cid, width=w, anchor=anc)
        self.tree_sum.pack(fill=tk.BOTH, expand=True)
        apply_zebra(self.tree_sum)

        # Åpne i Excel (valgte) for par
        rbtn_pairs = ttk.Frame(right); rbtn_pairs.pack(fill=tk.X)
        ttk.Button(rbtn_pairs, text="Åpne i Excel (valgte)", command=self._open_pairs_selection_excel).pack(side=tk.RIGHT)

        ttk.Label(right, text="Par (likt beløp, utdrag)").pack(anchor="w")
        self.tree_pairs = ttk.Treeview(right, columns=("bilag_a","dato_a","konto_a","belop_a","valuta_a","kundenr_a","levnr_a","bilag_b","dato_b","konto_b","belop_b","valuta_b","kundenr_b","levnr_b","diff","dager"), show="headings", height=10)
        for cid, title, w, anc in (("bilag_a","Bilag A",120,"w"),("dato_a","Dato A",100,"w"),("konto_a","Konto A",90,"w"),("belop_a","Beløp A",110,"e"),("valuta_a","Valuta A",80,"w"),("kundenr_a","Kundenr A",100,"w"),("levnr_a","Lev.nr A",100,"w"),
                                   ("bilag_b","Bilag B",120,"w"),("dato_b","Dato B",100,"w"),("konto_b","Konto B",90,"w"),("belop_b","Beløp B",110,"e"),("valuta_b","Valuta B",80,"w"),("kundenr_b","Kundenr B",100,"w"),("levnr_b","Lev.nr B",100,"w"),("diff","Diff",110,"e"),("dager","Δ dager",80,"e")):
            self.tree_pairs.heading(cid, text=title); self.tree_pairs.column(cid, width=w, anchor=anc)
        self.tree_pairs.pack(fill=tk.BOTH, expand=True)
        apply_zebra(self.tree_pairs)
        self.tree_pairs.bind("<Double-1>", lambda _e: self._open_pairs_selection_excel())

        # Two-sum visninger
        res2 = ttk.Panedwindow(self, orient=tk.HORIZONTAL); res2.pack(fill=tk.BOTH, expand=True, pady=(8,0))
        left2 = ttk.Frame(res2); right2 = ttk.Frame(res2)
        res2.add(left2, weight=5); res2.add(right2, weight=7)

        ttk.Label(left2, text="Oppsummering (two-sum)").pack(anchor="w")
        self.tree_two_sum = ttk.Treeview(left2, columns=("mal","ant_mal","par"), show="headings", height=8)
        for cid, title, w, anc in (("mal","Målbeløp",140,"e"),("ant_mal","Antall mål",120,"e"),("par","Par",100,"e")):
            self.tree_two_sum.heading(cid, text=title); self.tree_two_sum.column(cid, width=w, anchor=anc)
        self.tree_two_sum.pack(fill=tk.BOTH, expand=True)
        apply_zebra(self.tree_two_sum)

        rbtn_two = ttk.Frame(right2); rbtn_two.pack(fill=tk.X)
        ttk.Button(rbtn_two, text="Åpne i Excel (valgte)", command=self._open_two_pairs_selection_excel).pack(side=tk.RIGHT)

        ttk.Label(right2, text="Par (two-sum, utdrag)").pack(anchor="w")
        self.tree_two_pairs = ttk.Treeview(right2, columns=(
            "s1_bilag","s1_konto","s1_belop","s1_valuta","s1_dato","s1_kundenr","s1_levnr",
            "s2_bilag","s2_konto","s2_belop","s2_valuta","s2_dato","s2_kundenr","s2_levnr",
            "dst_bilag","dst_konto","dst_belop","dst_valuta","dst_dato","dst_kundenr","dst_levnr","diff","dager"
        ), show="headings", height=8)
        for cid, title, w, anc in (
            ("s1_bilag","Kilde1 Bilag",120,"w"),("s1_konto","Kilde1 Konto",100,"w"),("s1_belop","Kilde1 Beløp",110,"e"),("s1_valuta","Kilde1 Valuta",80,"w"),("s1_dato","Kilde1 Dato",100,"w"),("s1_kundenr","Kilde1 Kundenr",100,"w"),("s1_levnr","Kilde1 Lev.nr",100,"w"),
            ("s2_bilag","Kilde2 Bilag",120,"w"),("s2_konto","Kilde2 Konto",100,"w"),("s2_belop","Kilde2 Beløp",110,"e"),("s2_valuta","Kilde2 Valuta",80,"w"),("s2_dato","Kilde2 Dato",100,"w"),("s2_kundenr","Kilde2 Kundenr",100,"w"),("s2_levnr","Kilde2 Lev.nr",100,"w"),
            ("dst_bilag","Mål Bilag",120,"w"),("dst_konto","Mål Konto",100,"w"),("dst_belop","Mål Beløp",110,"e"),("dst_valuta","Mål Valuta",80,"w"),("dst_dato","Mål Dato",100,"w"),("dst_kundenr","Mål Kundenr",100,"w"),("dst_levnr","Mål Lev.nr",100,"w"),
            ("diff","Diff",110,"e"),("dager","Δ dager",80,"e")):
            self.tree_two_pairs.heading(cid, text=title); self.tree_two_pairs.column(cid, width=w, anchor=anc)
        self.tree_two_pairs.pack(fill=tk.BOTH, expand=True)
        apply_zebra(self.tree_two_pairs)
        self.tree_two_pairs.bind("<Double-1>", lambda _e: self._open_two_pairs_selection_excel())

        self.lbl_info = ttk.Label(self, text=""); self.lbl_info.pack(anchor="w", pady=(6,0))

    # ---------- Presets ----------
    def _collect_preset_cfg(self) -> Dict[str, Any]:
        mapping = {k: v.get().strip() for k, v in self.cbo_vars.items()}
        cfg = {
            "mapping": mapping,
            "settings": {
                "opposite": bool(self.var_opposite.get()),
                "tol_amount": float(parse_amount(self.var_tol_amount.get() or "0") or 0.0),
                "tol_pct": float(self.var_tol_pct.get() or 0.0),
                "tol_days": int(self.var_tol_days.get() or 0) if (self.var_tol_days.get() or "").strip() else None,
                "currency": bool(self.var_currency.get()),
                "customer": bool(self.var_customer.get()),
                "supplier": bool(self.var_supplier.get()),
                "unique_1to1": bool(self.var_unique_1to1.get()),
                "direction": (self.var_dir.get() or "A2B"),
                "cap_per_target": int(self.var_cap.get() or 200),
                "dedup_per_target": bool(self.var_dedup_per_target.get()),
            }
        }
        return cfg

    def _apply_preset_cfg(self, cfg: Dict[str, Any]) -> None:
        mp = (cfg or {}).get("mapping", {})
        for k, v in mp.items():
            if k in self.cbo_vars:
                self.cbo_vars[k].set(str(v or ""))
        st = (cfg or {}).get("settings", {})
        def setv(var, val): 
            try: var.set(val)
            except Exception: pass
        setv(self.var_opposite, bool(st.get("opposite", True)))
        setv(self.var_tol_amount, str(st.get("tol_amount", 0)))
        setv(self.var_tol_pct, str(st.get("tol_pct", 0)))
        setv(self.var_tol_days, "" if st.get("tol_days", None) is None else str(st.get("tol_days")))
        setv(self.var_currency, bool(st.get("currency", False)))
        setv(self.var_customer, bool(st.get("customer", False)))
        setv(self.var_supplier, bool(st.get("supplier", False)))
        setv(self.var_unique_1to1, bool(st.get("unique_1to1", True)))
        setv(self.var_dir, st.get("direction", "A2B"))
        setv(self.var_cap, int(st.get("cap_per_target", 200)))
        setv(self.var_dedup_per_target, bool(st.get("dedup_per_target", True)))

    def _preset_refresh(self):
        self.var_preset_list.set("; ".join(prefs.list_presets()))

    def _preset_save(self):
        name = (self.var_preset.get() or "").strip()
        if not name:
            messagebox.showinfo("Preset", "Skriv inn et navn for preset.")
            return
        prefs.save_preset(name, self._collect_preset_cfg())
        self._current_preset = name
        self._preset_refresh()
        messagebox.showinfo("Preset", f"Lagret: {name}")

    def _preset_load(self):
        name = (self.var_preset.get() or "").strip()
        if not name:
            messagebox.showinfo("Preset", "Skriv inn navnet på preset som skal lastes.")
            return
        cfg = prefs.get_preset(name)
        if not cfg:
            messagebox.showinfo("Preset", f"Fant ikke preset: {name}")
            return
        self._apply_preset_cfg(cfg)
        self._current_preset = name
        messagebox.showinfo("Preset", f"Lastet: {name}")

    def _preset_delete(self):
        name = (self.var_preset.get() or "").strip()
        if not name:
            messagebox.showinfo("Preset", "Skriv inn navnet på preset som skal slettes.")
            return
        prefs.delete_preset(name)
        if self._current_preset == name:
            self._current_preset = None
        self._preset_refresh()
        messagebox.showinfo("Preset", f"Slettet: {name}")

    def _preset_export(self):
        path = filedialog.asksaveasfilename(title="Eksporter presets", defaultextension=".json", filetypes=[("JSON","*.json")], initialfile="ab_presets_export.json")
        if not path:
            return
        out = prefs.export_all(Path(path))
        messagebox.showinfo("Presets", f"Eksportert til: {out}")

    def _preset_import(self):
        path = filedialog.askopenfilename(title="Importer presets", filetypes=[("JSON","*.json"),("Alle","*.*")])
        if not path:
            return
        # spør om modus
        ans = messagebox.askyesno("Importer", "Vil du ERSTATTE eksisterende presets? (Ja = replace, Nei = merge)")
        n = prefs.import_merge(Path(path), replace=bool(ans))
        self._preset_refresh()
        messagebox.showinfo("Importer", f"Importert/oppdatert {n} presets.")

    # ---------- B-håndtering ----------
    def _open_b(self):
        path = filedialog.askopenfilename(title="Åpne datasett B", filetypes=[("Excel/CSV","*.xlsx *.xls *.csv"),("Alle","*.*")])
        if not path: return
        self.var_path.set(path)
        try:
            df = iou.read_any(path)
            headers = [str(c) for c in df.columns]
            for cbo in self.cbos.values():
                cbo["values"] = [""] + headers
            # gjetning
            self.cbo_vars['konto'].set(_find(headers, 'konto','account'))
            self.cbo_vars['kontonavn'].set(_find(headers, 'kontonavn','account description','accountname','accdesc','accname'))
            self.cbo_vars['bilag'].set(_find(headers, 'bilag','voucher','document','documentno','docno'))
            self.cbo_vars['belop'].set(_find(headers, 'belop','beløp','amount','netamount'))
            self.cbo_vars['dato'].set(_find(headers, 'dato','date','postingdate','transdate'))
            self.cbo_vars['valutakode'].set(_find(headers, 'valutakode','currency','currencycode','curr'))
            self.cbo_vars['kundenr'].set(_find(headers, 'kundenr','customerid','customerno','debitorno','kundenummer'))
            self.cbo_vars['leverandornr'].set(_find(headers, 'leverandornr','supplierid','supplierno','vendorid','vendorno','leverandornummer','creditorno'))
            self._dfB_raw = df
        except Exception as ex:
            messagebox.showerror("B", f"Lesing feilet: {ex}")

    def _build_b(self):
        if not hasattr(self, "_dfB_raw"):
            messagebox.showinfo("B", "Åpne en fil først.")
            return
        df = self._dfB_raw.copy()
        c = Columns()
        for f, var in self.cbo_vars.items():
            setattr(c, f, var.get().strip())
        # Normaliser beløp og dato
        if c.belop and c.belop in df.columns:
            df['_amt'] = df[c.belop].map(parse_amount); df[c.belop] = df['_amt']; df.drop(columns=['_amt'], inplace=True)
        if c.dato and c.dato in df.columns:
            df['_dt'] = df[c.dato].map(parse_date); df[c.dato] = df['_dt']; df.drop(columns=['_dt'], inplace=True)
        self.dfB, self.cB = df, c
        # dataset A info
        dfA, cA = get_dataset()
        self.cA = cA or Columns()
        a_rows = len(dfA) if dfA is not None else 0
        b_rows = len(df) if df is not None else 0
        self.lbl_info.config(text=self._status_text(prefix="B bygget"))
        messagebox.showinfo("B", "Datasett B er klart.")

    # ---------- Likt beløp ----------
    def _run_same_amount(self):
        dfA, cA = get_dataset()
        if dfA is None or cA is None:
            messagebox.showinfo("A/B", "Datasett A er ikke lastet (bygg datasett i hovedfanen).")
            return
        if self.dfB is None or not self.cB.belop:
            messagebox.showinfo("A/B", "Datasett B er ikke klart.")
            return
        tol_amt = parse_amount(self.var_tol_amount.get()) if self.var_tol_amount.get().strip() else 0.0
        try:
            tol_days = int(self.var_tol_days.get()) if self.var_tol_days.get().strip() else None
        except Exception:
            tol_days = None
        try:
            tol_pct = float(self.var_tol_pct.get() or 0.0)
        except Exception:
            tol_pct = 0.0

        try:
            pairs, summary, stats = match_same_amount(
                dfA, cA, self.dfB, self.cB,
                opposite=bool(self.var_opposite.get()),
                amount_tol=float(tol_amt or 0.0),
                amount_tol_pct=float(tol_pct or 0.0),
                date_tol_days=tol_days,
                require_currency_match=bool(self.var_currency.get()),
                require_customer_match=bool(self.var_customer.get()),
                require_supplier_match=bool(self.var_supplier.get()),
                unique_pairs=bool(self.var_unique_1to1.get()),
                max_pairs=300000
            )
        except Exception as ex:
            messagebox.showerror("A/B", f"Feil i analyse: {ex}")
            return

        self.pairs, self.summary = pairs, summary
        self.stats_last = stats or {}
        # vis oppsummering + par
        self._render_summary_same(summary)
        self._render_pairs_same(pairs)
        # Telemetri + preset
        tel = self.stats_last or {}
        self.lbl_info.config(text=self._status_text(extra=f"Likt beløp – Par: {0 if pairs is None else len(pairs):,} | Join={tel.get('joined',0):,}→{tel.get('after_sign',0):,}→{tel.get('after_amount',0):,}→{tel.get('after_currency/date/keys',0):,}→{tel.get('after_dedup',0):,} | {tel.get('elapsed_ms',0)} ms"))

    def _render_summary_same(self, summary: Optional[pd.DataFrame]):
        for iid in self.tree_sum.get_children(): self.tree_sum.delete(iid)
        if summary is not None and not summary.empty:
            view = self._apply_summary_filter_frame(summary, "Beløp")
            for idx, r in view.iterrows():
                self.tree_sum.insert("", tk.END, iid=str(idx), values=(fmt_amount(float(r['Beløp'])), int(r['Antall_A']), int(r['Antall_B']), int(r['Par'])))
            autosize_tree(self.tree_sum, sample=200)
        else:
            self.tree_sum.insert("", tk.END, values=("Ingen treff", "", "", ""))

    def _render_pairs_same(self, pairs: Optional[pd.DataFrame]):
        for iid in self.tree_pairs.get_children(): self.tree_pairs.delete(iid)
        if pairs is not None and not pairs.empty:
            show = pairs.head(1000)
            for idx, r in show.iterrows():
                self.tree_pairs.insert("", tk.END, iid=str(idx), values=(
                    str(r.get('Bilag_A','')), str(r.get('Dato_A','')), str(r.get('Konto_A','')), fmt_amount(float(r.get('Beløp_A',0))), str(r.get('Valuta_A','')), str(r.get('Kundenr_A','')), str(r.get('Leverandornr_A','')),
                    str(r.get('Bilag_B','')), str(r.get('Dato_B','')), str(r.get('Konto_B','')), fmt_amount(float(r.get('Beløp_B',0))), str(r.get('Valuta_B','')), str(r.get('Kundenr_B','')), str(r.get('Leverandornr_B','')),
                    fmt_amount(float(r.get('Diff',0))), ("" if pd.isna(r.get('Dager_diff', float('nan'))) else int(r.get('Dager_diff', 0)))
                ))
            autosize_tree(self.tree_pairs, sample=200)

    # ---------- Two-sum ----------
    def _run_two_sum(self):
        dfA, cA = get_dataset()
        if dfA is None or cA is None:
            messagebox.showinfo("A/B", "Datasett A er ikke lastet (bygg datasett i hovedfanen).")
            return
        if self.dfB is None or not self.cB.belop:
            messagebox.showinfo("A/B", "Datasett B er ikke klart.")
            return
        tol_amt = parse_amount(self.var_tol_amount.get()) if self.var_tol_amount.get().strip() else 0.0
        try:
            tol_days = int(self.var_tol_days.get()) if self.var_tol_days.get().strip() else None
        except Exception:
            tol_days = None
        try:
            tol_pct = float(self.var_tol_pct.get() or 0.0)
        except Exception:
            tol_pct = 0.0
        direction = (self.var_dir.get() or "A2B").upper()
        try:
            pairs, summary, stats = two_sum_match(
                dfA, cA, self.dfB, self.cB,
                direction=direction,
                opposite=bool(self.var_opposite.get()),
                amount_tol=float(tol_amt or 0.0),
                amount_tol_pct=float(tol_pct or 0.0),
                date_tol_days=tol_days,
                require_currency_match=bool(self.var_currency.get()),
                require_customer_match=bool(self.var_customer.get()),
                require_supplier_match=bool(self.var_supplier.get()),
                max_pairs_total=300000,
                max_pairs_per_target=int(self.var_cap.get() or 200),
                dedup_per_target=bool(self.var_dedup_per_target.get())
            )
        except Exception as ex:
            messagebox.showerror("A/B", f"Feil i two-sum: {ex}")
            return

        if direction == "A2B":
            self.pairs_two_a2b, self.summary_two_a2b = pairs, summary
        else:
            self.pairs_two_b2a, self.summary_two_b2a = pairs, summary

        # vis oppsummering + par for sist kjørte retning
        self._render_summary_two()
        self._render_pairs_two(direction, pairs)
        # Telemetri + preset
        self.lbl_info.config(text=self._status_text(extra=f"Two-sum – targets={stats.get('targets',0):,} | kandidater≈{stats.get('candidates_examined',0):,} | par rå={stats.get('pairs_raw',0):,} → dedup={stats.get('pairs_after_dedup',0):,} | {stats.get('elapsed_ms',0)} ms"))

    def _render_summary_two(self):
        for iid in self.tree_two_sum.get_children(): self.tree_two_sum.delete(iid)
        combo_summary = []
        if self.summary_two_a2b is not None and not self.summary_two_a2b.empty:
            s = self.summary_two_a2b.copy(); s['Retning'] = 'A2B'; combo_summary.append(s)
        if self.summary_two_b2a is not None and not self.summary_two_b2a.empty:
            s = self.summary_two_b2a.copy(); s['Retning'] = 'B2A'; combo_summary.append(s)
        if combo_summary:
            all_s = pd.concat(combo_summary, axis=0, ignore_index=True)
            view = self._apply_summary_filter_frame(all_s, "Mål")
            for idx, r in view.head(1000).iterrows():
                self.tree_two_sum.insert("", tk.END, iid=str(idx), values=(fmt_amount(float(r['Mål'])), int(r['Antall_mål']), int(r['Par'])))
            autosize_tree(self.tree_two_sum, sample=200)
        else:
            self.tree_two_sum.insert("", tk.END, values=("Ingen mål", "", ""))

    def _render_pairs_two(self, direction: str, pairs: Optional[pd.DataFrame]):
        for iid in self.tree_two_pairs.get_children(): self.tree_two_pairs.delete(iid)
        show = pairs.head(500) if (pairs is not None and not pairs.empty) else pd.DataFrame()
        if show is None or show.empty:
            return
        if direction == "A2B":
            for idx, r in show.iterrows():
                self.tree_two_pairs.insert("", tk.END, iid=str(idx), values=(
                    str(r.get('Bilag_A1','')), str(r.get('Konto_A1','')), fmt_amount(float(r.get('Beløp_A1',0))), str(r.get('Valuta_A1','')), str(r.get('Dato_A1','')), str(r.get('Kundenr_A1','')), str(r.get('Leverandornr_A1','')),
                    str(r.get('Bilag_A2','')), str(r.get('Konto_A2','')), fmt_amount(float(r.get('Beløp_A2',0))), str(r.get('Valuta_A2','')), str(r.get('Dato_A2','')), str(r.get('Kundenr_A2','')), str(r.get('Leverandornr_A2','')),
                    str(r.get('Bilag_B','')), str(r.get('Konto_B','')), fmt_amount(float(r.get('Beløp_B',0))), str(r.get('Valuta_B','')), str(r.get('Dato_B','')), str(r.get('Kundenr_B','')), str(r.get('Leverandornr_B','')),
                    fmt_amount(float(r.get('Diff',0))), ("" if pd.isna(r.get('Dager_diff', float('nan'))) else int(r.get('Dager_diff', 0)))
                ))
        else:
            for idx, r in show.iterrows():
                self.tree_two_pairs.insert("", tk.END, iid=str(idx), values=(
                    str(r.get('Bilag_B1','')), str(r.get('Konto_B1','')), fmt_amount(float(r.get('Beløp_B1',0))), str(r.get('Valuta_B1','')), str(r.get('Dato_B1','')), str(r.get('Kundenr_B1','')), str(r.get('Leverandornr_B1','')),
                    str(r.get('Bilag_B2','')), str(r.get('Konto_B2','')), fmt_amount(float(r.get('Beløp_B2',0))), str(r.get('Valuta_B2','')), str(r.get('Dato_B2','')), str(r.get('Kundenr_B2','')), str(r.get('Leverandornr_B2','')),
                    str(r.get('Bilag_A','')), str(r.get('Konto_A','')), fmt_amount(float(r.get('Beløp_A',0))), str(r.get('Valuta_A','')), str(r.get('Dato_A','')), str(r.get('Kundenr_A','')), str(r.get('Leverandornr_A','')),
                    fmt_amount(float(r.get('Diff',0))), ("" if pd.isna(r.get('Dager_diff', float('nan'))) else int(r.get('Dager_diff', 0)))
                ))
        autosize_tree(self.tree_two_pairs, sample=200)

    # ---------- Hurtigfilter for oppsummeringer ----------
    def _apply_summary_filter_frame(self, df: pd.DataFrame, value_col: str) -> pd.DataFrame:
        try:
            vmin = parse_amount(self.var_sum_min.get()) if self.var_sum_min.get().strip() else None
        except Exception:
            vmin = None
        try:
            vmax = parse_amount(self.var_sum_max.get()) if self.var_sum_max.get().strip() else None
        except Exception:
            vmax = None
        out = df
        if vmin is not None:
            out = out[out[value_col].abs() >= abs(vmin)]
        if vmax is not None:
            out = out[out[value_col].abs() <= abs(vmax)]
        return out

    def _apply_summary_filter_same(self):
        self._render_summary_same(self.summary)

    def _apply_summary_filter_two(self):
        self._render_summary_two()

    def _clear_summary_filters(self):
        self.var_sum_min.set(""); self.var_sum_max.set("")
        self._render_summary_same(self.summary)
        self._render_summary_two()

    # ---------- Åpne i Excel (valgte) ----------
    def _open_pairs_selection_excel(self):
        if self.pairs is None or self.pairs.empty:
            messagebox.showinfo("Excel", "Ingen par å eksportere.")
            return
        sel = self.tree_pairs.selection()
        if not sel:
            messagebox.showinfo("Excel", "Marker én eller flere rader i 'Par (likt beløp)'.")
            return
        idx = [int(iid) for iid in sel if str(iid).isdigit() and int(iid) in self.pairs.index]
        df = self.pairs.loc[idx].copy() if idx else self.pairs.head(0)
        tmp = Path(tempfile.gettempdir()) / "ab_valgte_par.xlsx"
        export_selection(tmp, {"Valgte_Par": df}, amount_cols=['Beløp_A','Beløp_B','Diff'], date_cols=['Dato_A','Dato_B'])

    def _open_two_pairs_selection_excel(self):
        active_pairs = self.pairs_two_a2b if self.var_dir.get().upper() == "A2B" else self.pairs_two_b2a
        if active_pairs is None or active_pairs.empty:
            messagebox.showinfo("Excel", "Ingen two-sum-par å eksportere.")
            return
        sel = self.tree_two_pairs.selection()
        if not sel:
            messagebox.showinfo("Excel", "Marker én eller flere rader i 'Par (two-sum)'.")
            return
        idx = [int(iid) for iid in sel if str(iid).isdigit() and int(iid) in active_pairs.index]
        df = active_pairs.loc[idx].copy() if idx else active_pairs.head(0)
        tmp = Path(tempfile.gettempdir()) / "ab_valgte_two_sum.xlsx"
        amt_cols = ['Beløp_A','Beløp_B','Beløp_A1','Beløp_A2','Beløp_B1','Beløp_B2','Diff']
        date_cols = ['Dato_A','Dato_B','Dato_A1','Dato_A2','Dato_B1','Dato_B2']
        export_selection(tmp, {"Valgte_TwoSum": df}, amount_cols=amt_cols, date_cols=date_cols)

    # ---------- Åpne alle par for valgt oppsummeringsrad ----------
    def _open_all_pairs_for_selected_summary_same(self):
        if self.summary is None or self.summary.empty or self.pairs is None or self.pairs.empty:
            messagebox.showinfo("Excel", "Ingen data i 'likt beløp'.")
            return
        sel = self.tree_sum.selection()
        if not sel:
            messagebox.showinfo("Excel", "Marker en rad i 'Oppsummering (likt beløp)'.")
            return
        idx = int(sel[0]) if str(sel[0]).isdigit() else None
        if idx is None or idx not in self.summary.index:
            messagebox.showinfo("Excel", "Valgt rad ikke funnet.")
            return
        key_val = float(self.summary.loc[idx, 'Beløp'])
        # avled nøkkel fra par (rund 2) og ev. opposite
        opp = bool(self.var_opposite.get())
        key_series = (self.pairs['Beløp_A'].abs() if opp else self.pairs['Beløp_A']).round(2)
        df = self.pairs.loc[key_series == round(key_val,2)].copy()
        if df.empty:
            messagebox.showinfo("Excel", "Ingen par for valgt beløp.")
            return
        tmp = Path(tempfile.gettempdir()) / "ab_par_for_belop.xlsx"
        export_selection(tmp, {"Par_for_belop": df}, amount_cols=['Beløp_A','Beløp_B','Diff'], date_cols=['Dato_A','Dato_B'])

    def _open_all_pairs_for_selected_summary_two(self):
        # hent aktiv retning og riktig summary/pairs
        direction = (self.var_dir.get() or "A2B").upper()
        if direction == "A2B":
            summary = self.summary_two_a2b; pairs = self.pairs_two_a2b; target_col = 'Beløp_B'
        else:
            summary = self.summary_two_b2a; pairs = self.pairs_two_b2a; target_col = 'Beløp_A'
        if summary is None or summary.empty or pairs is None or pairs.empty:
            messagebox.showinfo("Excel", "Ingen data i 'two-sum'.")
            return
        sel = self.tree_two_sum.selection()
        if not sel:
            messagebox.showinfo("Excel", "Marker en rad i 'Oppsummering (two-sum)'.")
            return
        idx = int(sel[0]) if str(sel[0]).isdigit() else None
        if idx is None or idx not in summary.index:
            messagebox.showinfo("Excel", "Valgt rad ikke funnet.")
            return
        mål = float(summary.loc[idx, 'Mål'])
        df = pairs.loc[pairs[target_col].round(2) == round(mål,2)].copy()
        if df.empty:
            messagebox.showinfo("Excel", "Ingen par for valgt mål.")
            return
        tmp = Path(tempfile.gettempdir()) / "ab_two_sum_for_mal.xlsx"
        amt_cols = ['Beløp_A','Beløp_B','Beløp_A1','Beløp_A2','Beløp_B1','Beløp_B2','Diff']
        date_cols = ['Dato_A','Dato_B','Dato_A1','Dato_A2','Dato_B1','Dato_B2']
        export_selection(tmp, {"TwoSum_for_mal": df}, amount_cols=amt_cols, date_cols=date_cols)

    # ---------- Statuslinje tekst ----------
    def _status_text(self, prefix: str = "", extra: str = "") -> str:
        dfA, _ = get_dataset()
        a_rows = 0 if dfA is None else len(dfA)
        b_rows = 0 if self.dfB is None else len(self.dfB)
        p = f"Preset: {self._current_preset}" if self._current_preset else "Preset: (ingen)"
        parts = [x for x in [prefix, f"A={a_rows:,}", f"B={b_rows:,}", p, extra] if x]
        return " | ".join(parts).replace(",", " ")