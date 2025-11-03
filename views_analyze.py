from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from models import AnalysisConfig


def open_analysis_dialog(parent, current: AnalysisConfig | None) -> AnalysisConfig | None:
    cfg = AnalysisConfig() if current is None else current

    win = tk.Toplevel(parent)
    win.title("Analyser – oppsett")
    win.geometry("560x560")
    win.grab_set()

    # --- Enkeltlinjeanalyser ---
    dup_var = tk.IntVar(value=1 if cfg.include_duplicates_doc_account else 0)
    rnd_var = tk.IntVar(value=1 if cfg.include_round_amounts else 0)
    per_var = tk.IntVar(value=1 if cfg.include_out_of_period else 0)

    topbox = ttk.LabelFrame(win, text="Enkeltlinjer", padding=8)
    topbox.pack(fill=tk.X, padx=8, pady=(10, 6))
    ttk.Checkbutton(topbox, text="Duplikat dok.nr + konto", variable=dup_var).pack(anchor="w")
    ttk.Checkbutton(topbox, text="Runde beløp (enkeltlinjer)", variable=rnd_var).pack(anchor="w")
    ttk.Checkbutton(topbox, text="Dato utenfor periode (krever datokolonne og periode)", variable=per_var).pack(anchor="w")

    # Runde beløp parametre
    frmR = ttk.LabelFrame(win, text="Runde beløp – parametre", padding=8)
    frmR.pack(fill=tk.X, padx=8, pady=6)
    ttk.Label(frmR, text="Basiser (komma-separert):").grid(row=0, column=0, sticky="w")
    ent_bases = ttk.Entry(frmR, width=34)
    ent_bases.grid(row=0, column=1, sticky="w", padx=6)
    ent_bases.insert(0, ",".join(str(b) for b in cfg.round_bases))
    ttk.Label(frmR, text="Toleranse ± (kr):").grid(row=1, column=0, sticky="w", pady=(6,0))
    ent_tol = ttk.Entry(frmR, width=12); ent_tol.grid(row=1, column=1, sticky="w", padx=6, pady=(6,0))
    ent_tol.insert(0, str(cfg.round_tolerance))

    # --- Outliers ---
    out_var = tk.IntVar(value=1 if cfg.include_outliers else 0)
    frmO = ttk.LabelFrame(win, text="Outliers (uvanlige transaksjoner)", padding=8)
    frmO.pack(fill=tk.X, padx=8, pady=6)

    ttk.Checkbutton(frmO, text="Inkluder outliers", variable=out_var).grid(row=0, column=0, sticky="w", columnspan=2)
    ttk.Label(frmO, text="Metode:").grid(row=1, column=0, sticky="w")
    cb_m = ttk.Combobox(frmO, state="readonly", values=["MAD", "IQR"], width=10)
    cb_m.grid(row=1, column=1, sticky="w", padx=(6,0)); cb_m.set(cfg.outlier_method or "MAD")

    ttk.Label(frmO, text="Terskel:").grid(row=2, column=0, sticky="w", pady=(6,0))
    ent_thr = ttk.Entry(frmO, width=12); ent_thr.grid(row=2, column=1, sticky="w", padx=(6,0), pady=(6,0))
    ent_thr.insert(0, str(cfg.outlier_threshold))

    ttk.Label(frmO, text="Gruppering:").grid(row=3, column=0, sticky="w", pady=(6,0))
    cb_grp = ttk.Combobox(frmO, state="readonly", values=["Global", "Konto", "Part", "Konto+Part"], width=12)
    cb_grp.grid(row=3, column=1, sticky="w", padx=(6,0), pady=(6,0))
    cb_grp.set(cfg.outlier_group_by or "Konto")

    ttk.Label(frmO, text="Min rader pr. gruppe:").grid(row=4, column=0, sticky="w", pady=(6,0))
    ent_min = ttk.Entry(frmO, width=12); ent_min.grid(row=4, column=1, sticky="w", padx=(6,0), pady=(6,0))
    ent_min.insert(0, str(cfg.outlier_min_group_size))

    ttk.Label(frmO, text="Basis:").grid(row=5, column=0, sticky="w", pady=(6,0))
    cb_basis = ttk.Combobox(frmO, state="readonly", values=["abs", "signed"], width=10)
    cb_basis.grid(row=5, column=1, sticky="w", padx=(6,0), pady=(6,0))
    cb_basis.set(cfg.outlier_basis or "abs")

    # --- Runde beløp – andelsanalyse ---
    rs_var = tk.IntVar(value=1 if cfg.include_round_share_by_group else 0)
    frmRS = ttk.LabelFrame(win, text="Runde beløp – andel per gruppe", padding=8)
    frmRS.pack(fill=tk.X, padx=8, pady=6)

    ttk.Checkbutton(frmRS, text="Inkluder andelsanalyse", variable=rs_var).grid(row=0, column=0, sticky="w", columnspan=2)
    ttk.Label(frmRS, text="Gruppering:").grid(row=1, column=0, sticky="w", pady=(6,0))
    cb_rgrp = ttk.Combobox(frmRS, state="readonly", values=["Konto", "Part", "Måned"], width=12)
    cb_rgrp.grid(row=1, column=1, sticky="w", padx=(6,0), pady=(6,0))
    cb_rgrp.set(cfg.round_share_group_by or "Konto")

    ttk.Label(frmRS, text="Terskel andel (0–1):").grid(row=2, column=0, sticky="w", pady=(6,0))
    ent_rthr = ttk.Entry(frmRS, width=12); ent_rthr.grid(row=2, column=1, sticky="w", padx=(6,0), pady=(6,0))
    ent_rthr.insert(0, str(cfg.round_share_threshold))

    ttk.Label(frmRS, text="Min rader pr. gruppe:").grid(row=3, column=0, sticky="w", pady=(6,0))
    ent_rmin = ttk.Entry(frmRS, width=12); ent_rmin.grid(row=3, column=1, sticky="w", padx=(6,0), pady=(6,0))
    ent_rmin.insert(0, str(cfg.round_share_min_rows))

    # OK/Avbryt
    out_box = {}

    def _parse_bases(s: str):
        vals = []
        for t in (s or "").split(","):
            t = t.strip()
            if not t:
                continue
            try:
                v = int(t)
                if v > 0:
                    vals.append(v)
            except Exception:
                continue
        return tuple(vals) if vals else (1000, 500, 100)

    def ok():
        new = AnalysisConfig(
            include_duplicates_doc_account=bool(dup_var.get()),
            include_round_amounts=bool(rnd_var.get()),
            include_out_of_period=bool(per_var.get()),
            round_bases=_parse_bases(ent_bases.get()),
            round_tolerance=float((ent_tol.get() or "0").replace(",", ".")),

            include_outliers=bool(out_var.get()),
            outlier_method=str(cb_m.get() or "MAD"),
            outlier_threshold=float((ent_thr.get() or "0").replace(",", ".")),
            outlier_group_by=str(cb_grp.get() or "Konto"),
            outlier_min_group_size=int(ent_min.get() or 20),
            outlier_basis=str(cb_basis.get() or "abs"),

            include_round_share_by_group=bool(rs_var.get()),
            round_share_group_by=str(cb_rgrp.get() or "Konto"),
            round_share_threshold=float((ent_rthr.get() or "0.3").replace(",", ".")),
            round_share_min_rows=int(ent_rmin.get() or 20),
        )
        out_box["cfg"] = new
        win.destroy()

    ttk.Button(win, text="OK", command=ok).pack(side=tk.RIGHT, padx=10, pady=10)
    ttk.Button(win, text="Avbryt", command=win.destroy).pack(side=tk.RIGHT, pady=10)
    win.wait_window()
    return out_box.get("cfg")
