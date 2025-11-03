# views_selection_studio.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List

import pandas as pd

from session import get_dataset
from controller_selection import SelectionController
from models import Columns
from formatting import fmt_amount
from scope import parse_accounts
from controller_sample import frames_for_sample, export_sample_to_excel, export_sample_to_temp_and_open
from preferences import load_preferences
from ui_utils import enable_treeview_sort


class SelectionStudio:
    def __init__(self, parent: tk.Tk | tk.Toplevel, initial_accounts: Optional[List[int]] = None):
        df, cols = get_dataset()
        if df is None or cols is None:
            messagebox.showinfo("Datasett", "Ingen datasett er valgt. Åpne 'Datasett' og trykk 'Bruk datasett' først.")
            return

        self.ctrl = SelectionController(df, cols)

        self.win = tk.Toplevel(parent)
        self.win.title("Utvalgsstudio – stratifisering og uttrekk")
        self.win.geometry("1120x820")

        top = ttk.LabelFrame(self.win, text="Populasjon", padding=8)
        top.pack(fill=tk.X, padx=8, pady=(8,0))

        ttk.Label(top, text="Kontointervall(er):").pack(side=tk.LEFT)
        self.ent_spec = ttk.Entry(top, width=32)
        self.ent_spec.pack(side=tk.LEFT, padx=(6,10))
        if initial_accounts:
            self.ent_spec.insert(0, self._compress_accounts(initial_accounts))

        ttk.Label(top, text="Retning:").pack(side=tk.LEFT)
        self.cbo_dir = ttk.Combobox(top, state="readonly", values=["Alle","Debet","Kredit"], width=8)
        # standard fra Innstillinger
        self.cbo_dir.set((load_preferences().default_direction or "Alle"))
        self.cbo_dir.pack(side=tk.LEFT, padx=(6,10))

        ttk.Label(top, text="Beløpsfilter på:").pack(side=tk.LEFT)
        self.var_basis = tk.StringVar(value="abs")
        ttk.Radiobutton(top, text="ABS(|beløp|)", value="abs", variable=self.var_basis).pack(side=tk.LEFT)
        ttk.Radiobutton(top, text="Signert",      value="signed", variable=self.var_basis).pack(side=tk.LEFT, padx=(6,0))

        ttk.Label(top, text="Min:").pack(side=tk.LEFT, padx=(12,0))
        self.ent_min = ttk.Entry(top, width=12); self.ent_min.pack(side=tk.LEFT, padx=(2,6))
        ttk.Label(top, text="Maks:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(top, width=12); self.ent_max.pack(side=tk.LEFT, padx=(2,10))

        ttk.Button(top, text="Bygg populasjon", command=self._rebuild).pack(side=tk.RIGHT)

        strat = ttk.LabelFrame(self.win, text="Stratifisering av populasjon", padding=8)
        strat.pack(fill=tk.X, padx=8, pady=(8,0))
        ttk.Label(strat, text="Metode:").pack(side=tk.LEFT)
        self.cbo_method = ttk.Combobox(strat, state="readonly", values=["quantile","equal"], width=10)
        self.cbo_method.set("quantile"); self.cbo_method.pack(side=tk.LEFT, padx=(6,10))
        ttk.Label(strat, text="Antall intervaller:").pack(side=tk.LEFT)
        self.spin_bins = tk.Spinbox(strat, from_=2, to=20, width=6)
        self.spin_bins.delete(0, tk.END); self.spin_bins.insert(0, "7")
        self.spin_bins.pack(side=tk.LEFT, padx=(6,10))
        ttk.Button(strat, text="Oppdater", command=self._refresh_buckets).pack(side=tk.RIGHT)

        frame = ttk.Frame(self.win); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8,0))
        self.tree = ttk.Treeview(frame, columns=("fra","til","linjer","unik","sum","sumabs","andel"), show="headings")
        for cid, text, w, a in (
            ("fra","Fra",120,"e"),("til","Til",120,"e"),("linjer","Linjer",100,"e"),
            ("unik","Unike bilag",120,"e"),("sum","Sum (netto)",140,"e"),
            ("sumabs","Sum (|beløp|)",140,"e"),("andel","Andel linjer",110,"e")
        ):
            self.tree.heading(cid, text=text); self.tree.column(cid, width=w, anchor=a)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview).pack(side=tk.RIGHT, fill=tk.Y)

        # Aktiver sortering
        enable_treeview_sort(self.tree, {
            "fra":"amount", "til":"amount", "linjer":"int", "unik":"int",
            "sum":"amount", "sumabs":"amount", "andel":"float"
        })

        bottom = ttk.LabelFrame(self.win, text="Trekk og eksport", padding=8)
        bottom.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(bottom, text="Antall bilag å trekke:").pack(side=tk.LEFT)
        self.spin_n = tk.Spinbox(bottom, from_=1, to=100000, width=8)
        self.spin_n.delete(0, tk.END); self.spin_n.insert(0, "20"); self.spin_n.pack(side=tk.LEFT, padx=(6,10))
        ttk.Label(bottom, text="Fordeling:").pack(side=tk.LEFT)
        self.cbo_alloc = ttk.Combobox(bottom, state="readonly", values=["equal","prop"], width=10)
        self.cbo_alloc.set("equal"); self.cbo_alloc.pack(side=tk.LEFT, padx=(6,10))
        ttk.Label(bottom, text="Seed:").pack(side=tk.LEFT)
        self.ent_seed = ttk.Entry(bottom, width=10); self.ent_seed.pack(side=tk.LEFT, padx=(6,10))
        ttk.Button(bottom, text="Trekk bilag", command=self._draw).pack(side=tk.LEFT, padx=(10,0))
        ttk.Button(bottom, text="Åpne i Excel nå", command=self._open_now).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Eksporter utvalg …", command=self._export).pack(side=tk.RIGHT, padx=(0,8))

        self.lbl_pop = ttk.Label(self.win, text="Populasjon: linjer=0 | sum=0,00")
        self.lbl_pop.pack(anchor="w", padx=8, pady=(0,8))

        self.sample_ids: List[str] = []
        self._rebuild()

    # ---------- helpers ----------
    def _compress_accounts(self, acc: List[int]) -> str:
        if not acc: return ""
        s = sorted(set(int(a) for a in acc))
        ranges = []
        start = prev = s[0]
        for x in s[1:]:
            if x == prev + 1:
                prev = x; continue
            ranges.append((start, prev)); start = prev = x
        ranges.append((start, prev))
        return ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in ranges)

    def _parse_amount(self, txt: str):
        t = (txt or "").strip().replace(" ", "").replace("kr","")
        if not t: return None
        t = t.replace(".", "").replace(",", ".")
        try: return float(t)
        except Exception: return None

    # ---------- actions ----------
    def _rebuild(self):
        self.ctrl.state.accounts_spec = self.ent_spec.get().strip()
        self.ctrl.state.direction = self.cbo_dir.get()
        self.ctrl.state.basis = self.var_basis.get()
        self.ctrl.state.min_amount = self._parse_amount(self.ent_min.get())
        self.ctrl.state.max_amount = self._parse_amount(self.ent_max.get())
        self._refresh_buckets()

    def _refresh_buckets(self):
        try:
            self.ctrl.state.method = self.cbo_method.get()
            self.ctrl.state.bins = int(self.spin_bins.get())
        except Exception:
            self.ctrl.state.method = "quantile"; self.ctrl.state.bins = 7

        df = self.ctrl.filtered_df()
        if df is None or df.empty:
            for iid in self.tree.get_children(): self.tree.delete(iid)
            self.lbl_pop.config(text="Populasjon: linjer=0 | sum=0,00")
            return

        tab, _cats = self.ctrl.build_buckets()
        for iid in self.tree.get_children(): self.tree.delete(iid)

        total = int(tab["Linjer"].sum()) if not tab.empty else 0
        for _, r in tab.iterrows():
            andel = (100.0 * (r["Linjer"] / total)) if total else 0.0
            self.tree.insert("", tk.END, values=(
                fmt_amount(float(r["Fra"])), fmt_amount(float(r["Til"])),
                f"{int(r['Linjer']):,}", f"{int(r['Unike bilag']):,}",
                fmt_amount(float(r["Sum (netto)"])), fmt_amount(float(r["Sum (|beløp|)"])),
                f"{andel:,.2f} %"
            ))

        sum_net = float(df[self.ctrl.cols.belop].sum())
        self.lbl_pop.config(text=f"Populasjon: linjer={len(df):,} | sum={fmt_amount(sum_net)}")

    def _draw(self):
        try: n = int(self.spin_n.get())
        except Exception:
            messagebox.showwarning("Antall", "Ugyldig antall.")
            return
        seed_txt = self.ent_seed.get().strip()
        self.ctrl.state.seed = int(seed_txt) if seed_txt else None
        picks = self.ctrl.draw_sample(n_total=n, per_bucket=self.cbo_alloc.get())
        if picks.empty:
            messagebox.showinfo("Tomt", "Fant ingen bilag å trekke."); return
        self.sample_ids = picks.astype(str).tolist()
        messagebox.showinfo("Trekk", f"Trakk {len(self.sample_ids)} bilag fra populasjonen.")

    def _export(self):
        if not self.sample_ids:
            messagebox.showinfo("Ingen trekk", "Trekk bilag først."); return
        df, cols = get_dataset(); assert df is not None and cols is not None
        accounts = parse_accounts(self.ctrl.state.accounts_spec, df[cols.konto].dropna().astype("Int64").astype(int).unique().tolist())
        fullt, internt, summer = frames_for_sample(df, cols, self.sample_ids, accounts)
        path = filedialog.asksaveasfilename(
            title="Lagre utvalg (Excel)", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Bilag_uttrekk_{len(self.sample_ids)}.xlsx", parent=self.win
        )
        if not path: return
        try:
            export_sample_to_excel(path, fullt, internt, summer)
            messagebox.showinfo("Lagret", f"Eksportert til\n{path}")
        except Exception as e:
            messagebox.showerror("Eksportfeil", str(e))

    def _open_now(self):
        if not self.sample_ids:
            self._draw()
            if not self.sample_ids:
                return
        df, cols = get_dataset(); assert df is not None and cols is not None
        accounts = parse_accounts(self.ctrl.state.accounts_spec, df[cols.konto].dropna().astype("Int64").astype(int).unique().tolist())
        fullt, internt, summer = frames_for_sample(df, cols, self.sample_ids, accounts)
        try:
            path = export_sample_to_temp_and_open(fullt, internt, summer)
            messagebox.showinfo("Åpnet", f"Eksport skrevet til midlertidig fil og åpnet:\n{path}")
        except Exception as e:
            messagebox.showerror("Eksportfeil", str(e))
