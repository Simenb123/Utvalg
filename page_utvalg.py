# page_utvalg.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional, Tuple, Dict

import numpy as np
import pandas as pd

from models import Columns
from formatting import fmt_amount, fmt_int, fmt_date, parse_amount
from theme import stripe_tree
from export_utils import export_and_open


class UtvalgPage(ttk.Frame):
    """
    Egen fane for å bygge populasjon/underpopulasjoner (kvantiler), trekke bilag
    og eksportere. Bruk prepare(...) for å overføre utvalg fra Analyse.
    """

    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)

        self.cols = Columns()
        self.pop_df: pd.DataFrame = pd.DataFrame()
        self.segments: Dict[str, pd.DataFrame] = {}

        # Topp: filtreringsparametre/opsjoner for denne fanen
        bar = ttk.Frame(self, padding=8); bar.pack(fill=tk.X)
        ttk.Label(bar, text="Retning:").pack(side=tk.LEFT)
        self.var_dir = tk.StringVar(value="Alle")
        self.cbo_dir = ttk.Combobox(bar, state="readonly", width=8, values=["Alle", "Debet", "Kredit"], textvariable=self.var_dir)
        self.cbo_dir.pack(side=tk.LEFT, padx=(6,12))

        ttk.Label(bar, text="Min beløp:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(bar, width=12); self.ent_min.pack(side=tk.LEFT, padx=(4,6))
        ttk.Label(bar, text="Maks beløp:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(bar, width=12); self.ent_max.pack(side=tk.LEFT, padx=(4,12))

        self.var_abs = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Bruk absoluttbeløp i filter", variable=self.var_abs).pack(side=tk.LEFT)

        ttk.Button(bar, text="Oppdater", command=self._rebuild_population).pack(side=tk.LEFT, padx=(12,0))

        self.lbl_info = ttk.Label(bar, text="Ingen populasjon valgt enda.")
        self.lbl_info.pack(side=tk.LEFT, padx=(16,0))

        # Midt: segment- og transaksjonsvisning
        split = ttk.Panedwindow(self, orient=tk.HORIZONTAL); split.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6,8))

        left = ttk.Frame(split); split.add(left, weight=3)
        hdr = ttk.Frame(left); hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="Segmenter (Populasjon + ev. kvantiler)").pack(side=tk.LEFT)
        self.var_bins = tk.StringVar(value="Ingen")
        ttk.Label(hdr, text="  Kvantiler:").pack(side=tk.LEFT, padx=(8,2))
        self.cbo_bins = ttk.Combobox(hdr, state="readonly", width=8, values=["Ingen", 2,3,4,5,6,8,10], textvariable=self.var_bins)
        self.cbo_bins.pack(side=tk.LEFT)
        ttk.Button(hdr, text="Bygg kvantiler", command=self._build_quantiles).pack(side=tk.LEFT, padx=(6,0))

        self.tree_seg = ttk.Treeview(left, columns=("seg","linjer","sum","andel"), show="headings", selectmode="browse")
        self.tree_seg.heading("seg", text="Segment")
        self.tree_seg.heading("linjer", text="Linjer")
        self.tree_seg.heading("sum", text="Sum")
        self.tree_seg.heading("andel", text="Andel")
        self.tree_seg.column("seg", width=280, anchor="w")
        self.tree_seg.column("linjer", width=90, anchor="e")
        self.tree_seg.column("sum", width=120, anchor="e")
        self.tree_seg.column("andel", width=80, anchor="e")
        self.tree_seg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4,0))
        ttk.Scrollbar(left, orient="vertical", command=self.tree_seg.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_seg.bind("<<TreeviewSelect>>", lambda _e: self._refresh_tx())

        right = ttk.Frame(split); split.add(right, weight=6)
        ttk.Label(right, text="Transaksjoner i valgt segment").pack(anchor="w")
        self.tree_tx = ttk.Treeview(right, columns=("dato","bilag","tekst","belop","konto","navn"),
                                    show="headings", selectmode="extended")
        for c, t, w, a in (
            ("dato","Dato",100,"w"),
            ("bilag","Bilag",120,"w"),
            ("tekst","Tekst",420,"w"),
            ("belop","Beløp",120,"e"),
            ("konto","Konto",80,"e"),
            ("navn","Kontonavn",250,"w"),
        ):
            self.tree_tx.heading(c, text=t)
            self.tree_tx.column(c, width=w, anchor=a)
        self.tree_tx.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(right, orient="vertical", command=self.tree_tx.yview).pack(side=tk.RIGHT, fill=tk.Y)

        # Bunn: trekk/eksport
        foot = ttk.Frame(self, padding=8); foot.pack(fill=tk.X)
        ttk.Label(foot, text="Antall bilag:").pack(side=tk.LEFT)
        self.ent_n = ttk.Entry(foot, width=8); self.ent_n.insert(0, "20"); self.ent_n.pack(side=tk.LEFT, padx=(4,12))
        self.var_per_bucket = tk.BooleanVar(value=False)
        ttk.Checkbutton(foot, text="Trekk pr. bøtte (kvantil)", variable=self.var_per_bucket).pack(side=tk.LEFT)
        ttk.Label(foot, text="Seed:").pack(side=tk.LEFT, padx=(12,2))
        self.ent_seed = ttk.Entry(foot, width=10); self.ent_seed.pack(side=tk.LEFT, padx=(0,12))
        ttk.Button(foot, text="Trekk bilag", command=self._do_sample).pack(side=tk.LEFT)

        ttk.Button(foot, text="Eksporter til Excel (åpne)", command=self._export).pack(side=tk.RIGHT)

        # Intern state for sampling
        self.sample_ids: List[str] = []

    # -------------------- API --------------------
    def prepare(self,
                df: pd.DataFrame,
                cols: Columns,
                accounts: List[int],
                direction: str = "Alle",
                min_amount: Optional[float] = None,
                max_amount: Optional[float] = None,
                use_abs: bool = True) -> None:
        """Kalles fra hovedvindu når bruker trykker 'Til utvalg' i Analyse."""
        self.cols = cols
        self.var_dir.set(direction or "Alle")
        self.var_abs.set(bool(use_abs))
        self.ent_min.delete(0, tk.END); self.ent_max.delete(0, tk.END)
        if min_amount is not None: self.ent_min.insert(0, str(min_amount).replace(".", ","))
        if max_amount is not None: self.ent_max.insert(0, str(max_amount).replace(".", ","))

        # Bygg start-populasjon (konto + retning + beløpsintervall)
        df2 = df.copy()
        df2 = df2[df2[cols.konto].astype("Int64").astype(int).isin(accounts)]
        if direction.lower().startswith("debet"):
            df2 = df2[df2[cols.belop] > 0]
        elif direction.lower().startswith("kredit"):
            df2 = df2[df2[cols.belop] < 0]

        if min_amount is not None:
            df2 = df2[(df2[cols.belop].abs() if use_abs else df2[cols.belop]) >= float(min_amount)]
        if max_amount is not None:
            df2 = df2[(df2[cols.belop].abs() if use_abs else df2[cols.belop]) <= float(max_amount)]

        self.pop_df = df2.reset_index(drop=True)
        self._rebuild_segments_initial()
        self._refresh_tx()
        self.lbl_info.config(text=f"Populasjon = {fmt_int(len(self.pop_df))} linjer | sum {fmt_amount(float(self.pop_df[cols.belop].sum() if not self.pop_df.empty else 0.0))}")

    # -------------------- Logikk --------------------
    def _rebuild_population(self) -> None:
        if self.pop_df.empty or self.cols.belop == "":
            return
        # Reapplikér retning og intervall på original pop_df (NB: pop_df er allerede konto-filtrert)
        df2 = self.pop_df.copy()
        d = self.var_dir.get().lower()
        if d.startswith("debet"):
            df2 = df2[df2[self.cols.belop] > 0]
        elif d.startswith("kredit"):
            df2 = df2[df2[self.cols.belop] < 0]
        vmin = self._parse_amount(self.ent_min.get())
        vmax = self._parse_amount(self.ent_max.get())
        if vmin is not None:
            df2 = df2[(df2[self.cols.belop].abs() if self.var_abs.get() else df2[self.cols.belop]) >= vmin]
        if vmax is not None:
            df2 = df2[(df2[self.cols.belop].abs() if self.var_abs.get() else df2[self.cols.belop]) <= vmax]
        self.pop_df = df2.reset_index(drop=True)
        self._rebuild_segments_initial()
        self._refresh_tx()
        self.lbl_info.config(text=f"Populasjon = {fmt_int(len(self.pop_df))} linjer | sum {fmt_amount(float(self.pop_df[self.cols.belop].sum() if not self.pop_df.empty else 0.0))}")

    def _rebuild_segments_initial(self) -> None:
        # Nullstill segmenter og fyll "Populasjon"
        self.segments.clear()
        self.segments["Populasjon"] = self.pop_df.copy()
        self._fill_segment_tree()

    def _build_quantiles(self) -> None:
        if self.pop_df.empty:
            messagebox.showinfo("Kvantiler", "Populasjonen er tom."); return
        try:
            n = int(self.var_bins.get()) if str(self.var_bins.get()).isdigit() else 0
        except Exception:
            n = 0
        if n <= 0:
            # bare Populasjon
            self._rebuild_segments_initial()
            self._refresh_tx()
            return

        basis = self.pop_df[self.cols.belop].abs() if self.var_abs.get() else self.pop_df[self.cols.belop]
        qs = np.linspace(0, 1, n + 1)
        edges = list(basis.quantile(qs).values)
        # Sørg for strengt stigende kanter
        eps = 1e-9
        for i in range(1, len(edges)):
            if edges[i] <= edges[i-1]:
                edges[i] = edges[i-1] + eps

        cats = pd.cut(basis, bins=edges, include_lowest=True, right=True)
        self.segments.clear()
        self.segments["Populasjon"] = self.pop_df.copy()
        for i, cat in enumerate(sorted(cats.cat.categories, key=lambda x: x.left)):  # type: ignore[attr-defined]
            lab = f"Bøtte {i+1}: {fmt_amount(cat.left)} – {fmt_amount(cat.right)}"  # type: ignore[attr-defined]
            self.segments[lab] = self.pop_df[cats == cat].copy()

        self._fill_segment_tree()
        self._refresh_tx()

    def _fill_segment_tree(self) -> None:
        for iid in self.tree_seg.get_children(): self.tree_seg.delete(iid)
        total = len(self.pop_df)
        s_total = float(self.pop_df[self.cols.belop].sum() if not self.pop_df.empty else 0.0)
        for seg, df in self.segments.items():
            linjer = len(df)
            summen = float(df[self.cols.belop].sum() if not df.empty else 0.0)
            andel = (linjer / total) if total else 0.0
            self.tree_seg.insert("", tk.END, iid=seg, values=(seg, fmt_int(linjer), fmt_amount(summen), f"{andel:.1%}"))
        stripe_tree(self.tree_seg)
        # Velg "Populasjon" som default
        try:
            self.tree_seg.selection_set("Populasjon")
            self.tree_seg.focus("Populasjon")
        except Exception:
            pass

    def _refresh_tx(self) -> None:
        for iid in self.tree_tx.get_children(): self.tree_tx.delete(iid)
        sel = self.tree_seg.selection()
        key = sel[0] if sel else "Populasjon"
        df = self.segments.get(key, pd.DataFrame())
        c = self.cols
        if df.empty:
            return
        col_dato = c.dato if (c.dato and c.dato in df.columns) else None
        col_txt = c.tekst if (c.tekst and c.tekst in df.columns) else None
        for _, r in df.iterrows():
            dato = fmt_date(r[col_dato]) if col_dato else ""
            bilag = str(r[c.bilag])
            tekst = str(r[col_txt]) if col_txt else ""
            belop = fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0)
            konto = str(r[c.konto])
            navn = str(r[c.kontonavn] or "")
            self.tree_tx.insert("", tk.END, values=(dato, bilag, tekst, belop, konto, navn))
        stripe_tree(self.tree_tx)

    def _parse_amount(self, s: str) -> Optional[float]:
        a = parse_amount(s)
        return None if a is None else float(a)

    # -------------------- Trekk / Eksport --------------------
    def _do_sample(self) -> None:
        if self.pop_df.empty:
            messagebox.showinfo("Trekk", "Populasjonen er tom."); return
        try:
            n = max(1, int(str(self.ent_n.get()).strip()))
        except Exception:
            messagebox.showwarning("Trekk", "Ugyldig antall bilag."); return
        seed = None
        s_raw = (self.ent_seed.get() or "").strip()
        if s_raw:
            try:
                seed = int(s_raw)
            except Exception:
                seed = None

        c = self.cols
        rng = np.random.default_rng(seed)
        sample_ids: List[str] = []

        if self.var_per_bucket.get() and len(self.segments) > 1:
            # fordel ~likt pr. bøtte (hopper over "Populasjon")
            buckets = [k for k in self.segments.keys() if k != "Populasjon"]
            per = max(1, n // len(buckets))
            rest = n - per * len(buckets)
            for b in buckets:
                unike = self.segments[b][c.bilag].dropna().astype(str).drop_duplicates()
                k = min(per, len(unike))
                if k > 0:
                    sample_ids += rng.choice(unike.to_numpy(), size=k, replace=False).tolist()
            # eventuelt fyll på fra samlet populasjon
            if rest > 0:
                unike_pop = self.pop_df[c.bilag].dropna().astype(str).drop_duplicates()
                # fjern allerede valgte
                unike_pop = unike_pop[~unike_pop.isin(sample_ids)]
                k = min(rest, len(unike_pop))
                if k > 0:
                    sample_ids += rng.choice(unike_pop.to_numpy(), size=k, replace=False).tolist()
        else:
            unike = self.pop_df[c.bilag].dropna().astype(str).drop_duplicates()
            k = min(n, len(unike))
            sample_ids = rng.choice(unike.to_numpy(), size=k, replace=False).tolist() if k > 0 else []

        self.sample_ids = sample_ids
        messagebox.showinfo("Trekk klart", f"Valgte {len(sample_ids)} bilag i utvalget.")

    def _export(self) -> None:
        if not self.sample_ids:
            messagebox.showinfo("Eksport", "Trekk bilag først."); return
        c = self.cols
        uttak = self.pop_df[self.pop_df[c.bilag].astype(str).isin(self.sample_ids)].copy()
        oppsummering = (
            uttak.groupby(c.bilag)[c.belop]
                 .agg(Linjer="count", Sum="sum")
                 .reset_index()
                 .sort_values(c.bilag)
        )
        seg_oversikt = []
        for seg, df in self.segments.items():
            seg_oversikt.append({
                "Segment": seg,
                "Linjer": len(df),
                "Sum": float(df[c.belop].sum() if not df.empty else 0.0),
            })
        seg_df = pd.DataFrame(seg_oversikt)

        path = export_and_open({
            "Utvalg_transaksjoner": uttak,
            "Oppsummering_bilag": oppsummering,
            "Segmenter": seg_df,
        }, filename_hint="Bilag_utvalg")
        self.lbl_info.config(text=f"Eksportert: {path}")
