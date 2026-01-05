from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

from controller_export import export_to_excel
from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    confidence_factor,
    fmt_amount_no,
    fmt_int_no,
    format_interval_no,
    parse_amount,
    suggest_sample_size,
)

from stratifiering import stratify_bilag

try:
    from selection_studio_drill import open_drilldown
except Exception:
    open_drilldown = None


__all__ = [
    "SelectionStudio",
    # Re-export helpers for tests in this repo
    "PopulationMetrics",
    "compute_population_metrics",
    "format_interval_no",
    "build_source_text",
    "build_population_summary_text",
    "build_sample_summary_text",
    "suggest_sample_size",
    "parse_amount",
]


class SelectionStudio(ttk.Frame):
    """
    Utvalg (Selection Studio) - compact UI.

    Key idea:
      - Keep the main flow simple (less is more)
      - Provide "advanced" only when needed
      - Keep helper functions stable (tests rely on them)
    """

    def __init__(self, master: tk.Misc, *, on_commit_selection=None):
        super().__init__(master)
        self.on_commit_selection = on_commit_selection

        # Data
        self._df_all: pd.DataFrame | None = None
        self._df_base: pd.DataFrame | None = None  # filtered base
        self._df_bilag: pd.DataFrame | None = None  # bilag-summed df (for strata + sampling)
        self._df_sample: pd.DataFrame | None = None

        self._interval_map: dict[int, object] = {}
        self._removed_rows = 0
        self._removed_bilag = 0

        # UI state
        self.var_dir = tk.StringVar(value="Alle")
        self.var_from = tk.StringVar(value="")
        self.var_to = tk.StringVar(value="")
        self.var_use_abs = tk.BooleanVar(value=True)

        # Risk / assurance (backwards compat: keep risk_factor as 1-5 style int)
        self.var_risk = tk.IntVar(value=3)  # 3 = middels (legacy scale)
        self.var_risk_label = tk.StringVar(value="Middels")

        self.var_assurance = tk.StringVar(value="90%")  # internal percent string
        self.var_conf_label = tk.StringVar(value="Middels")  # UI friendly

        self.var_method = tk.StringVar(value="quantile")
        self.var_k = tk.IntVar(value=5)

        self.var_top_threshold = tk.StringVar(value="")
        self.var_sample_n = tk.IntVar(value=0)

        # Optional: formula inputs (kept in Avansert)
        self.var_tol_err = tk.StringVar(value="")
        self.var_exp_err = tk.StringVar(value="")

        self._refresh_job = None
        self._advanced_visible = False

        self._build_ui()
        self._wire_events()

    # ----------------
    # Public API
    # ----------------

    def load_data(self, df_all: pd.DataFrame, df_base: pd.DataFrame | None = None):
        self._df_all = df_all
        self._df_base = df_base if df_base is not None else df_all

        # label top
        self.lbl_source.config(text=build_source_text(self._df_base, self._df_all))

        self._schedule_refresh(clear_tables=True)

    # ----------------
    # UI
    # ----------------

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top info bar
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        top.grid_columnconfigure(0, weight=1)

        self.lbl_source = ttk.Label(top, text="Kilde: (ingen data)")
        self.lbl_source.grid(row=0, column=0, sticky="w")

        self.lbl_pop = ttk.Label(top, text="")
        self.lbl_pop.grid(row=0, column=1, sticky="e", padx=(12, 0))

        # Left plan panel
        plan = ttk.Frame(self, padding=8)
        plan.grid(row=1, column=0, sticky="nsw")
        plan.grid_columnconfigure(0, weight=1)

        ttk.Label(plan, text="Plan", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        r = 1
        ttk.Label(plan, text="Retning").grid(row=r, column=0, sticky="w")
        self.cmb_dir = ttk.Combobox(plan, textvariable=self.var_dir, values=("Alle", "Positiv", "Negativ"),
                                    state="readonly", width=12)
        self.cmb_dir.grid(row=r, column=0, sticky="w", pady=(2, 6))
        r += 1

        ttk.Label(plan, text="Beløp fra/til").grid(row=r, column=0, sticky="w")
        frm_amt = ttk.Frame(plan)
        frm_amt.grid(row=r + 1, column=0, sticky="w", pady=(2, 6))
        ttk.Entry(frm_amt, textvariable=self.var_from, width=10).grid(row=0, column=0, sticky="w")
        ttk.Label(frm_amt, text="til").grid(row=0, column=1, padx=6)
        ttk.Entry(frm_amt, textvariable=self.var_to, width=10).grid(row=0, column=2, sticky="w")
        r += 2

        ttk.Checkbutton(plan, text="Bruk absolutt beløp", variable=self.var_use_abs).grid(
            row=r, column=0, sticky="w", pady=(0, 8)
        )
        r += 1

        # Risk + confidence (simplified UI)
        ttk.Label(plan, text="Risiko").grid(row=r, column=0, sticky="w")
        self.cmb_risk = ttk.Combobox(
            plan,
            textvariable=self.var_risk_label,
            values=("Lav", "Middels", "Høy"),
            state="readonly",
            width=12,
        )
        self.cmb_risk.grid(row=r + 1, column=0, sticky="w", pady=(2, 6))
        r += 2

        ttk.Label(plan, text="Sikkerhet").grid(row=r, column=0, sticky="w")
        frm_conf = ttk.Frame(plan)
        frm_conf.grid(row=r + 1, column=0, sticky="w", pady=(2, 6))
        self.cmb_conf = ttk.Combobox(
            frm_conf,
            textvariable=self.var_conf_label,
            values=("Lav", "Middels", "Høy"),
            state="readonly",
            width=12,
        )
        self.cmb_conf.grid(row=0, column=0, sticky="w")
        ttk.Label(frm_conf, textvariable=self.var_assurance).grid(row=0, column=1, padx=(8, 0), sticky="w")
        r += 2

        self.lbl_reco = ttk.Label(plan, text="Forslag utvalg: –")
        self.lbl_reco.grid(row=r, column=0, sticky="w", pady=(4, 6))
        r += 1

        ttk.Label(plan, text="Utvalgsstørrelse").grid(row=r, column=0, sticky="w")
        frm_n = ttk.Frame(plan)
        frm_n.grid(row=r + 1, column=0, sticky="w", pady=(2, 6))
        ttk.Spinbox(frm_n, from_=0, to=9999, textvariable=self.var_sample_n, width=8).grid(row=0, column=0)
        ttk.Label(frm_n, text="(0 = auto)").grid(row=0, column=1, padx=(8, 0))
        r += 2

        self.btn_adv = ttk.Button(plan, text="Avansert ▸", command=self._toggle_advanced)
        self.btn_adv.grid(row=r, column=0, sticky="w", pady=(6, 6))
        r += 1

        self._adv_frame = ttk.Frame(plan)
        self._adv_frame.grid(row=r, column=0, sticky="ew")
        self._adv_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(self._adv_frame, text="Metode").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            self._adv_frame,
            textvariable=self.var_method,
            values=("quantile", "equal"),
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(self._adv_frame, text="Antall grupper (k)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(self._adv_frame, from_=2, to=25, textvariable=self.var_k, width=8).grid(
            row=1, column=1, sticky="w", pady=(6, 0)
        )

        ttk.Label(self._adv_frame, text="100% terskel (>=)").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(self._adv_frame, textvariable=self.var_top_threshold, width=12).grid(
            row=2, column=1, sticky="w", pady=(6, 0)
        )

        ttk.Label(self._adv_frame, text="Tolererbar feil").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self._adv_frame, textvariable=self.var_tol_err, width=12).grid(
            row=3, column=1, sticky="w", pady=(10, 0)
        )

        ttk.Label(self._adv_frame, text="Forventet feil").grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(self._adv_frame, textvariable=self.var_exp_err, width=12).grid(
            row=4, column=1, sticky="w", pady=(6, 0)
        )

        # start hidden
        self._adv_frame.grid_remove()

        # Buttons
        btns = ttk.Frame(plan)
        btns.grid(row=r + 1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Kjør utvalg", command=self._run_selection).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(btns, text="Legg i utvalg", command=self._commit_selection).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(btns, text="Eksporter Excel", command=self._export_excel).grid(row=0, column=2)

        # Right panel: notebook
        nb = ttk.Notebook(self)
        nb.grid(row=1, column=1, sticky="nsew", padx=(0, 8), pady=(0, 8))

        self.frm_groups = ttk.Frame(nb, padding=6)
        self.frm_sample = ttk.Frame(nb, padding=6)
        nb.add(self.frm_sample, text="Utvalg")
        nb.add(self.frm_groups, text="Grupper")

        # Sample tab
        self.frm_sample.grid_rowconfigure(2, weight=1)
        self.frm_sample.grid_columnconfigure(0, weight=1)

        self.lbl_sample = ttk.Label(self.frm_sample, text="Utvalg: (ingen bilag trukket)")
        self.lbl_sample.grid(row=0, column=0, sticky="w")

        frm_sample_btns = ttk.Frame(self.frm_sample)
        frm_sample_btns.grid(row=1, column=0, sticky="w", pady=(6, 6))

        self.btn_show_accounts = ttk.Button(frm_sample_btns, text="Vis kontoer", command=self._show_accounts_popup)
        self.btn_show_accounts.grid(row=0, column=0, padx=(0, 6))

        self.btn_drill = ttk.Button(frm_sample_btns, text="Drilldown", command=self._drilldown)
        self.btn_drill.grid(row=0, column=1)
        if open_drilldown is None:
            self.btn_drill.state(["disabled"])

        self.tree_sample = ttk.Treeview(
            self.frm_sample,
            columns=("Bilag", "Dato", "Tekst", "SumBeløp", "Gruppe", "Intervall", "Fulltext"),
            show="headings",
            height=18,
        )
        for col, w in [
            ("Bilag", 90),
            ("Dato", 90),
            ("Tekst", 360),
            ("SumBeløp", 120),
            ("Gruppe", 80),
            ("Intervall", 160),
            ("Fulltext", 220),
        ]:
            self.tree_sample.heading(col, text=col)
            self.tree_sample.column(col, width=w, anchor="w")
        self.tree_sample.grid(row=2, column=0, sticky="nsew")

        ysb = ttk.Scrollbar(self.frm_sample, orient="vertical", command=self.tree_sample.yview)
        self.tree_sample.configure(yscrollcommand=ysb.set)
        ysb.grid(row=2, column=1, sticky="ns")

        # Groups tab
        self.frm_groups.grid_rowconfigure(1, weight=1)
        self.frm_groups.grid_columnconfigure(0, weight=1)

        self.lbl_groups = ttk.Label(self.frm_groups, text="Grupper: –")
        self.lbl_groups.grid(row=0, column=0, sticky="w")

        self.tree_groups = ttk.Treeview(
            self.frm_groups,
            columns=("Gruppe", "Antall bilag", "SumBeløp", "Min", "Median", "Max", "Intervall"),
            show="headings",
            height=18,
        )
        for col, w in [
            ("Gruppe", 70),
            ("Antall bilag", 100),
            ("SumBeløp", 120),
            ("Min", 100),
            ("Median", 100),
            ("Max", 100),
            ("Intervall", 180),
        ]:
            self.tree_groups.heading(col, text=col)
            self.tree_groups.column(col, width=w, anchor="w")
        self.tree_groups.grid(row=1, column=0, sticky="nsew")

        ysb2 = ttk.Scrollbar(self.frm_groups, orient="vertical", command=self.tree_groups.yview)
        self.tree_groups.configure(yscrollcommand=ysb2.set)
        ysb2.grid(row=1, column=1, sticky="ns")

    def _wire_events(self):
        # When base filters change => refresh population + clear tables
        for v in (self.var_dir, self.var_from, self.var_to, self.var_use_abs):
            v.trace_add("write", lambda *_: self._schedule_refresh(clear_tables=True))

        # When parameters change => refresh derived + recompute reco
        for v in (self.var_risk, self.var_assurance, self.var_method, self.var_k, self.var_top_threshold,
                  self.var_tol_err, self.var_exp_err):
            v.trace_add("write", lambda *_: self._schedule_refresh(clear_tables=False))

        # UI combobox selection syncing
        self.cmb_risk.bind("<<ComboboxSelected>>", lambda e: self._sync_risk_from_label())
        self.cmb_conf.bind("<<ComboboxSelected>>", lambda e: self._sync_assurance_from_label())

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._adv_frame.grid()
            self.btn_adv.config(text="Avansert ▾")
        else:
            self._adv_frame.grid_remove()
            self.btn_adv.config(text="Avansert ▸")

    def _sync_risk_from_label(self):
        lbl = (self.var_risk_label.get() or "").strip().lower()
        # Map to legacy-ish 1-5 scale: 2/3/4 = lav/middels/høy
        if lbl.startswith("l"):
            self.var_risk.set(2)
        elif lbl.startswith("h"):
            self.var_risk.set(4)
        else:
            self.var_risk.set(3)

    def _sync_assurance_from_label(self):
        lbl = (self.var_conf_label.get() or "").strip().lower()
        if lbl.startswith("l"):
            self.var_assurance.set("80%")
        elif lbl.startswith("h"):
            self.var_assurance.set("95%")
        else:
            self.var_assurance.set("90%")

    # ----------------
    # Refresh pipeline
    # ----------------

    def _schedule_refresh(self, *, clear_tables: bool):
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(80, lambda: self._refresh(clear_tables=clear_tables))

    def _refresh(self, *, clear_tables: bool):
        self._refresh_job = None

        if self._df_all is None or self._df_base is None:
            return

        # Apply base filters
        df = self._df_base.copy()

        # Direction
        if "Beløp" in df.columns:
            belop = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
            if self.var_dir.get() == "Positiv":
                df = df[belop > 0]
            elif self.var_dir.get() == "Negativ":
                df = df[belop < 0]

        # Amount range
        lo = parse_amount(self.var_from.get())
        hi = parse_amount(self.var_to.get())
        if "Beløp" in df.columns and (lo is not None or hi is not None):
            belop = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
            x = belop.abs() if self.var_use_abs.get() else belop
            if lo is not None:
                df = df[x >= lo]
            if hi is not None:
                df = df[x <= hi]

        self._removed_rows = int(len(self._df_base) - len(df)) if self._df_base is not None else 0
        self._removed_bilag = 0
        if "Bilag" in self._df_base.columns and "Bilag" in df.columns:
            self._removed_bilag = int(self._df_base["Bilag"].nunique() - df["Bilag"].nunique())

        self._df_base = df

        metrics = compute_population_metrics(df)
        self.lbl_pop.config(text=build_population_summary_text(metrics, self._removed_rows, self._removed_bilag))

        # Recommended sample size (auto)
        cf = confidence_factor(self.var_risk.get(), self.var_assurance.get())
        pop_value = float(metrics.sum_abs)

        tol = parse_amount(self.var_tol_err.get())
        exp = parse_amount(self.var_exp_err.get())
        used_formula = bool(tol is not None and tol > 0 and pop_value > 0 and (tol - float(exp or 0.0)) > 0)

        reco = suggest_sample_size(
            metrics.bilag,
            risk_factor=self.var_risk.get(),
            assurance=self.var_assurance.get(),
            population_value=pop_value,
            tolerable_error=tol,
            expected_error=exp,
        )

        tag = "formel" if used_formula else "tommelfinger"
        self.lbl_reco.config(
            text=f"Forslag utvalg: {fmt_int_no(reco)} bilag | Konfidensfaktor: {fmt_amount_no(cf, 2)} ({tag})"
        )

        # If clear_tables: wipe tables + recompute stratification immediately
        if clear_tables:
            self._df_sample = None
            self._clear_tree(self.tree_sample)
            self.lbl_sample.config(text="Utvalg: (ingen bilag trukket)")

        # Build bilag-summed df for grouping/sampling
        self._df_bilag = self._build_bilag_df(df)

        # Stratify
        self._refresh_groups_table()

    def _build_bilag_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["Bilag", "Dato", "Tekst", "SumBeløp", "Fulltext"])

        cols = df.columns
        have_date = "Dato" in cols
        have_text = "Tekst" in cols

        g = df.groupby("Bilag", dropna=False)

        out = pd.DataFrame(
            {
                "Bilag": g.size().index,
                "SumBeløp": pd.to_numeric(g["Beløp"].sum(), errors="coerce").fillna(0.0).values
                if "Beløp" in cols
                else 0.0,
            }
        )

        if have_date:
            out["Dato"] = g["Dato"].first().values
        else:
            out["Dato"] = ""

        if have_text:
            out["Tekst"] = g["Tekst"].first().fillna("").values
            # Fulltext can be used later (concat)
            out["Fulltext"] = g["Tekst"].apply(lambda s: " | ".join([str(x) for x in s.dropna().astype(str)])).values
        else:
            out["Tekst"] = ""
            out["Fulltext"] = ""

        return out

    def _refresh_groups_table(self):
        self._clear_tree(self.tree_groups)
        df_b = self._df_bilag
        if df_b is None or df_b.empty:
            self.lbl_groups.config(text="Grupper: –")
            self._interval_map = {}
            return

        method = self.var_method.get()
        k = int(self.var_k.get() or 5)

        use_abs = bool(self.var_use_abs.get())
        values = df_b["SumBeløp"].abs() if use_abs else df_b["SumBeløp"]

        groups, interval_map, stats_df = stratify_bilag(values, method=method, k=k)
        self._interval_map = interval_map

        # Attach group
        tmp = df_b.copy()
        tmp["Gruppe"] = groups

        # Build table from stats_df (already computed in stratifiering)
        self.lbl_groups.config(text=f"Grupper: {k} ({method})")

        for _, row in stats_df.iterrows():
            gno = int(row["Gruppe"])
            n_bilag = int(row.get("Antall bilag", 0))
            s = float(row.get("SumBeløp", 0.0))
            mn = float(row.get("Min", 0.0))
            med = float(row.get("Median", 0.0))
            mx = float(row.get("Max", 0.0))
            interval = interval_map.get(gno, "")

            self.tree_groups.insert(
                "",
                "end",
                values=(
                    gno,
                    fmt_int_no(n_bilag),
                    fmt_amount_no(s, 2),
                    fmt_amount_no(mn, 2),
                    fmt_amount_no(med, 2),
                    fmt_amount_no(mx, 2),
                    format_interval_no(interval),
                ),
            )

    # ----------------
    # Actions
    # ----------------

    def _run_selection(self):
        df_b = self._df_bilag
        if df_b is None or df_b.empty:
            messagebox.showwarning("Utvalg", "Ingen bilag i grunnlaget.")
            return

        metrics = compute_population_metrics(self._df_base)
        n_total = int(self.var_sample_n.get() or 0)

        if n_total <= 0:
            tol = parse_amount(self.var_tol_err.get())
            exp = parse_amount(self.var_exp_err.get())
            n_total = suggest_sample_size(
                metrics.bilag,
                risk_factor=self.var_risk.get(),
                assurance=self.var_assurance.get(),
                population_value=float(metrics.sum_abs),
                tolerable_error=tol,
                expected_error=exp,
            )

        # 100% threshold
        threshold = parse_amount(self.var_top_threshold.get())
        if threshold is not None and threshold > 0:
            must = df_b[df_b["SumBeløp"].abs() >= threshold].copy()
        else:
            must = df_b.iloc[0:0].copy()

        # Remaining pool
        pool = df_b.drop(index=must.index, errors="ignore").copy()

        remaining = max(0, n_total - len(must))
        sample = must.copy()

        if remaining > 0 and not pool.empty:
            # Simple random sample by bilag row (not line)
            sample_rest = pool.sample(n=min(remaining, len(pool)), replace=False, random_state=42)
            sample = pd.concat([sample, sample_rest], ignore_index=True)

        # Add group + interval
        if self._interval_map:
            # We can compute groups again quickly
            use_abs = bool(self.var_use_abs.get())
            values = df_b["SumBeløp"].abs() if use_abs else df_b["SumBeløp"]
            groups, interval_map, _ = stratify_bilag(values, method=self.var_method.get(), k=int(self.var_k.get() or 5))
            df_b2 = df_b.copy()
            df_b2["Gruppe"] = groups
            sample = sample.merge(df_b2[["Bilag", "Gruppe"]], on="Bilag", how="left")
            sample["Intervall"] = sample["Gruppe"].apply(lambda g: format_interval_no(interval_map.get(int(g), "")))

        self._df_sample = sample
        self._render_sample()

    def _render_sample(self):
        self._clear_tree(self.tree_sample)

        if self._df_sample is None or self._df_sample.empty:
            self.lbl_sample.config(text="Utvalg: (ingen bilag trukket)")
            return

        self.lbl_sample.config(text=build_sample_summary_text(self._df_sample))

        for _, row in self._df_sample.iterrows():
            self.tree_sample.insert(
                "",
                "end",
                values=(
                    row.get("Bilag", ""),
                    row.get("Dato", ""),
                    row.get("Tekst", ""),
                    fmt_amount_no(row.get("SumBeløp", 0.0), 2),
                    row.get("Gruppe", ""),
                    row.get("Intervall", ""),
                    row.get("Fulltext", ""),
                ),
            )

    def _commit_selection(self):
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showwarning("Utvalg", "Ingen utvalg å legge til.")
            return

        if self.on_commit_selection is not None:
            self.on_commit_selection(self._df_sample.copy())

        messagebox.showinfo("Utvalg", "Utvalg lagt til.")

    def _export_excel(self):
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showwarning("Eksport", "Ingen utvalg å eksportere.")
            return
        try:
            export_to_excel(self._df_sample)
            messagebox.showinfo("Eksport", "Eksportert til Excel.")
        except Exception as e:
            messagebox.showerror("Eksportfeil", f"Kunne ikke eksportere.\n\n{e}")

    def _drilldown(self):
        if open_drilldown is None:
            return
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showwarning("Drilldown", "Kjør utvalg først.")
            return
        open_drilldown(self.winfo_toplevel(), df_sample=self._df_sample, df_all=self._df_all)

    def _show_accounts_popup(self):
        if self._df_base is None or self._df_base.empty or "Konto" not in self._df_base.columns:
            messagebox.showinfo("Kontoer", "Ingen kontoer tilgjengelig i grunnlaget.")
            return

        df = self._df_base.copy()
        # basic account aggregation
        belop = pd.to_numeric(df.get("Beløp", 0.0), errors="coerce").fillna(0.0)
        konto = pd.to_numeric(df["Konto"], errors="coerce")
        kontonavn = df.get("Kontonavn", pd.Series([""] * len(df))).fillna("")

        tmp = pd.DataFrame({"Konto": konto, "Kontonavn": kontonavn, "Beløp": belop, "Bilag": df.get("Bilag")})
        tmp = tmp.dropna(subset=["Konto"])

        g = tmp.groupby("Konto", dropna=False)
        out = pd.DataFrame(
            {
                "Konto": g.size().index.astype(int),
                "Kontonavn": g["Kontonavn"].first().values,
                "Rader": g.size().values,
                "Bilag": g["Bilag"].nunique().values if "Bilag" in tmp.columns else g.size().values,
                "Sum": g["Beløp"].sum().values,
            }
        ).sort_values("Sum", ascending=False)

        win = tk.Toplevel(self)
        win.title("Kontoer i grunnlaget")
        win.geometry("720x520")

        tree = ttk.Treeview(win, columns=("Konto", "Kontonavn", "Rader", "Bilag", "Sum"), show="headings")
        for col, w in [("Konto", 80), ("Kontonavn", 260), ("Rader", 80), ("Bilag", 80), ("Sum", 120)]:
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor="w")
        tree.pack(fill="both", expand=True)

        for _, r in out.iterrows():
            tree.insert(
                "",
                "end",
                values=(
                    int(r["Konto"]),
                    r["Kontonavn"],
                    fmt_int_no(r["Rader"]),
                    fmt_int_no(r["Bilag"]),
                    fmt_amount_no(r["Sum"], 2),
                ),
            )

    @staticmethod
    def _clear_tree(tree: ttk.Treeview):
        for item in tree.get_children():
            tree.delete(item)
