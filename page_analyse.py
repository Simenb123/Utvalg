from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Sequence, List, Optional, Dict, Tuple
import pandas as pd
import numpy as np
import importlib

pd.options.mode.chained_assignment = None

PRIORITY_TRANS_COLS = [
    "Konto","Kontonavn","Bilag","Dato","Beløp","Tekst",
    "Kundenr","Kundenavn","Leverandørnr","Leverandørnavn",
    "Valuta","Valutabeløp","MVA-kode","MVA-beløp","MVA-prosent"
]

try:
    from formatting import format_number_no, format_date_no
except Exception:
    def format_number_no(x, d=2):
        try: return f"{float(x):,.{d}f}".replace(",", " ").replace(".", ",")
        except Exception: return str(x)
    def format_date_no(x):
        try:
            ts = pd.to_datetime(x, errors="coerce")
            if pd.isna(ts): return ""
            return ts.strftime("%d.%m.%Y")
        except Exception: return ""

try:
    import preferences as prefs
except Exception:
    class _P:
        store = {}
        def get(self,k,default=None): return self.store.get(k, default)
        def set(self,k,v): self.store[k]=v
    prefs = _P()

from views_virtual_transactions import VirtualTransactionsPanel

try:
    from views_column_chooser import open_column_chooser
except Exception:
    def open_column_chooser(*_a, **_k):
        # Fallback: no dialog -> keep current columns
        return None

try:
    from ui_loading import LoadingOverlay
except Exception:
    class LoadingOverlay:
        def __init__(self, *_a, **_k): pass
        def busy(self, *_a, **_k):
            class _C:
                def __enter__(self_s): return None
                def __exit__(self_s, *e): return False
            return _C()

class AnalysePage(ttk.Frame):
    def __init__(self, master, controller=None, bus=None, **kwargs):
        super().__init__(master, **kwargs)
        self.controller=controller; self.bus=bus
        self.loading = LoadingOverlay(self)
        self._df = pd.DataFrame(); self._filtered = pd.DataFrame()
        self._dataset_version = 0
        self._prepared_version = -1
        self._pivot_cache_key: Optional[tuple] = None
        self._pivot_cache_df: Optional[pd.DataFrame] = None
        self._pivot_sort_col="Konto"; self._pivot_sort_asc=True
        self._apply_job_id: Optional[str] = None
        self._display_limit = int(prefs.get("analyse.display_limit", 200) or 200)
        self._last_session_df_id: Optional[int] = None
        self._last_session_len: Optional[int] = None
        self._build_ui(); self._wire_bus(); self.after(350, self._autoload_from_session)

    def _build_ui(self):
        self.columnconfigure(0, weight=1); self.rowconfigure(2, weight=1)
        bar = ttk.Frame(self); bar.grid(row=0,column=0,sticky="ew",padx=6,pady=(6,2))
        ttk.Label(bar,text="Søk:").pack(side="left")
        self.ent_search = ttk.Entry(bar, width=28); self.ent_search.pack(side="left", padx=(4,8))
        self.ent_search.bind("<KeyRelease>", lambda e: self._schedule_apply())
        self.ent_search.bind("<Return>", lambda e: self._schedule_apply(force_now=True))

        ttk.Label(bar,text="Retning:").pack(side="left")
        self.cmb_dir = ttk.Combobox(bar, values=["Alle","D","K"], width=6, state="readonly")
        self.cmb_dir.set("Alle"); self.cmb_dir.pack(side="left", padx=(4,8))
        self.cmb_dir.bind("<<ComboboxSelected>>", lambda e: self._schedule_apply())

        ttk.Label(bar,text="Kontoserier:").pack(side="left", padx=(12,0))
        self._series_vars=[tk.BooleanVar(value=False) for _ in range(9)]
        for i,var in enumerate(self._series_vars, start=1):
            cb=ttk.Checkbutton(bar, text=str(i), variable=var, command=self._schedule_apply)
            cb.pack(side="left")

        ttk.Label(bar,text="Vis:").pack(side="left", padx=(12,4))
        self.cmb_limit = ttk.Combobox(bar, values=["100","200","500","1000","Alle"], width=6, state="readonly")
        self.cmb_limit.set("200" if self._display_limit>0 else "Alle")
        self.cmb_limit.pack(side="left", padx=(0,8))
        self.cmb_limit.bind("<<ComboboxSelected>>", self._on_limit_changed)

        ttk.Button(bar, text="Nullstill", command=self._reset_filters).pack(side="left")
        ttk.Button(bar, text="Bruk filtre", command=lambda: self._schedule_apply(force_now=True)).pack(side="left", padx=(8,0))
        ttk.Button(bar, text="Til utvalg", command=self._send_to_selection).pack(side="left", padx=(8,0))

        self.pin_menu_btn = ttk.Menubutton(bar, text="Pinned kolonner"); self.pin_menu=tk.Menu(self.pin_menu_btn, tearoff=False)
        self.pin_menu_btn["menu"]=self.pin_menu; self.pin_menu_btn.pack(side="right", padx=(12,8))
        self.btn_cols = ttk.Button(bar, text="Kolonner…", command=self._open_column_chooser); self.btn_cols.pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal"); body.grid(row=2,column=0,sticky="nsew", padx=2, pady=6)
        left = ttk.Frame(body); left.columnconfigure(0, weight=1); left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Pivot pr. konto").grid(row=0,column=0,sticky="w")
        self.pivot = ttk.Treeview(left, columns=["Konto","Kontonavn","Sum","Antall"], show="headings", selectmode="extended", takefocus=True)
        for c,w in [("Konto",110),("Kontonavn",300),("Sum",120),("Antall",80)]:
            self.pivot.heading(c, text=c, command=(lambda col=c: self._on_pivot_heading(col)))
            self.pivot.column(c, width=w, anchor=("e" if c in ("Sum","Antall") else "w"))
        self.pivot.grid(row=1,column=0,sticky="nsew", padx=6, pady=6)

        right = ttk.Frame(body); right.columnconfigure(0, weight=1); right.rowconfigure(2, weight=1)
        ttk.Label(right, text="Transaksjoner").grid(row=0, column=0, sticky="w")
        self.lbl_summary = ttk.Label(right, text="Oppsummering: rader=0 | sum=0,00 (viser 0)")
        self.lbl_summary.grid(row=1, column=0, sticky="w", padx=6, pady=(0,2))
        self.trans = VirtualTransactionsPanel(right, columns=PRIORITY_TRANS_COLS)
        self.trans.grid(row=2,column=0,sticky="nsew", padx=6, pady=6)
        body.add(left, weight=1); body.add(right, weight=2)
        status = ttk.Frame(self); status.grid(row=3,column=0,sticky="ew", padx=6, pady=(0,6))
        self.lbl_status = ttk.Label(status, text="Transaksjoner: 0 rader"); self.lbl_status.pack(side="left")
        self._refresh_pinned_menu()
        self.pivot.bind("<<TreeviewSelect>>", lambda e: self._refresh_summary())

    def _on_limit_changed(self, *_):
        val = self.cmb_limit.get()
        self._display_limit = 0 if val=="Alle" else int(val)
        try: prefs.set("analyse.display_limit", self._display_limit)
        except Exception: pass
        self._render_transactions_only()
        self._refresh_summary()

    def _reset_filters(self):
        try: self.ent_search.delete(0, tk.END)
        except Exception: pass
        try: self.cmb_dir.set("Alle")
        except Exception: pass
        for v in self._series_vars:
            try: v.set(False)
            except Exception: pass
        self._pivot_sort_col = "Konto"; self._pivot_sort_asc = True
        self._schedule_apply(force_now=True)

    def _refresh_pinned_menu(self):
        self.pin_menu.delete(0,"end")
        def toggler(col):
            def _():
                cur = list(prefs.get("analyse.pinned", []) or [])
                if col in cur: cur.remove(col)
                else: cur.append(col)
                prefs.set("analyse.pinned", cur)
                self._reapply_columns_from_prefs()
            return _
        for c in PRIORITY_TRANS_COLS:
            var=tk.BooleanVar(value=(c in (prefs.get("analyse.pinned", []) or [])))
            self.pin_menu.add_checkbutton(label=c, variable=var, command=toggler(c))

    def _open_column_chooser(self):
        all_cols = self.trans.get_visible_columns()
        order = prefs.get("analyse.columns.order", []) or PRIORITY_TRANS_COLS
        order = [c for c in order if c in all_cols] + [c for c in all_cols if c not in order]
        visible = prefs.get("analyse.columns.visible", []) or [c for c in order]
        result = open_column_chooser(self, all_cols=all_cols, visible_cols=visible, initial_order=order)
        if result:
            new_order, new_visible = result
            prefs.set("analyse.columns.order", new_order)
            prefs.set("analyse.columns.visible", new_visible)
            self._reapply_columns_from_prefs()

    def _reapply_columns_from_prefs(self):
        order = prefs.get("analyse.columns.order", []) or PRIORITY_TRANS_COLS
        visible = prefs.get("analyse.columns.visible", []) or order
        pins = prefs.get("analyse.pinned", []) or []
        self.trans.set_dataframe(self._filtered, pinned=pins, prefer_order=order, visible=visible, limit=self._display_limit)
        self._refresh_summary()

    def _wire_bus(self):
        try:
            if self.bus is None or not hasattr(self.bus,"on"): return
            for ev in ["DATASET_BUILT","DATASET_UPDATED","DATASET_READY"]:
                self.bus.on(ev, self._on_dataset_event)
        except Exception: pass

    def _autoload_from_session(self):
        df,_ = self._try_dataset_from_session()
        if isinstance(df, pd.DataFrame) and not df.empty:
            if id(df) != self._last_session_df_id or len(df) != (self._last_session_len or -1):
                self._last_session_df_id = id(df); self._last_session_len = len(df)
                self._set_dataset(df)
        self.after(4000, self._autoload_from_session)

    def refresh_from_session(self):
        df,_ = self._try_dataset_from_session()
        if isinstance(df, pd.DataFrame) and not df.empty:
            if id(df) != self._last_session_df_id or len(df) != (self._last_session_len or -1):
                self._last_session_df_id = id(df); self._last_session_len = len(df)
                self._set_dataset(df)

    def _on_dataset_event(self, payload: Any=None):
        df = None
        if isinstance(payload, pd.DataFrame): df = payload
        elif isinstance(payload, dict):
            for k in ["df","dataset","dataframe","dataset_df","built_df"]:
                if isinstance(payload.get(k), pd.DataFrame): df = payload[k]; break
        if isinstance(df, pd.DataFrame):
            self._last_session_df_id = id(df); self._last_session_len = len(df)
            self._set_dataset(df)

    def _try_dataset_from_session(self) -> Tuple[Optional[pd.DataFrame], str]:
        try: sm=importlib.import_module("session")
        except Exception: return (None,"")
        for key in ["dataset","df","dataframe","dataset_df","built_df","current_df"]:
            v = getattr(sm, key, None)
            if isinstance(v, pd.DataFrame) and len(v)>0: return v, f"session.{key}"
        return (None,"")

    def _set_dataset(self, df: pd.DataFrame):
        with self.loading.busy("Bygger pivot..."):
            df2 = df.copy()
            self._df = df2
            self._dataset_version += 1
            self._prepare_df(self._df)
            self.apply_filters()

    def _prepare_df(self, df: pd.DataFrame):
        if "Beløp" in df.columns and "_abs_beløp" not in df.columns:
            try:
                df["Beløp"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
            except Exception: pass
            try:
                df["_abs_beløp"] = np.abs(df["Beløp"].astype(float))
            except Exception:
                df["_abs_beløp"] = np.nan

        if "Konto" in df.columns and "_serie" not in df.columns:
            s = df["Konto"].astype(str)
            digit = s.str.extract(r'(\d)', expand=False).fillna("")
            digit = digit.where(digit.isin(list("123456789")), other="")
            df["_serie"] = pd.Categorical(digit, categories=list("123456789"))

        if "_search" not in df.columns:
            df["_search"] = ""

        for c in ["Konto","Kontonavn"]:
            if c in df.columns:
                try: df[c] = df[c].astype("category")
                except Exception: pass

    def _schedule_apply(self, force_now: bool=False):
        if self._apply_job_id is not None:
            try: self.after_cancel(self._apply_job_id)
            except Exception: pass
            self._apply_job_id = None
        if force_now:
            self.apply_filters(); return
        self._apply_job_id = self.after(150, self.apply_filters)

    def _current_filter_state(self) -> tuple:
        series_tup = tuple(v.get() for v in self._series_vars)
        return (self._dataset_version,
                self.ent_search.get().strip().lower(),
                self.cmb_dir.get(),
                series_tup)

    def _series_filter_mask(self, df: pd.DataFrame) -> pd.Series:
        if not any(v.get() for v in self._series_vars):
            return pd.Series(True, index=df.index)
        sels = {str(i) for i,v in enumerate(self._series_vars, start=1) if v.get()}
        ser = df.get("_serie")
        if ser is None:
            return pd.Series(True, index=df.index)
        return ser.astype(str).isin(sels)

    def apply_filters(self):
        with self.loading.busy("Oppdaterer visning..."):
            if self._df is None or self._df.empty:
                self._filtered = pd.DataFrame()
                self._render_transactions_only(); self._refresh_status(); self._refresh_summary(); return

            state = self._current_filter_state()
            df = self._df

            q = state[1]
            if q and (df["_search"] == "").all():
                cols = [c for c in ["Tekst","Konto","Kontonavn","Bilag"] if c in df.columns]
                if cols:
                    s = pd.Series("", index=df.index, dtype="object")
                    for c in cols:
                        s = s.str.cat(df[c].astype(str).str.lower().fillna(""), sep=" ")
                    df["_search"] = s

            if q:
                mask = df["_search"].str.contains(q, na=False, regex=False)
                df2 = df.loc[mask]
            else:
                df2 = df

            d = state[2]
            if "Beløp" in df2.columns:
                if d == "D": df2 = df2[df2["Beløp"] > 0]
                elif d == "K": df2 = df2[df2["Beløp"] < 0]

            df2 = df2[self._series_filter_mask(df2)]

            self._filtered = df2
            self._build_pivot_cached(df2, state)
            self._render_transactions_only()

            self._refresh_status(); self._refresh_summary()

    def _build_pivot_cached(self, df: pd.DataFrame, state_key: tuple):
        if df is None or df.empty or "Beløp" not in df.columns or "Konto" not in df.columns:
            for iid in self.pivot.get_children(""): self.pivot.delete(iid)
            return
        if self._pivot_cache_key == state_key and isinstance(self._pivot_cache_df, pd.DataFrame):
            grp = self._pivot_cache_df
        else:
            grp = df.groupby(["Konto","Kontonavn"], observed=True, as_index=False)["Beløp"].agg(Sum="sum", Antall="count")
            self._pivot_cache_key = state_key
            self._pivot_cache_df = grp

        col, asc = self._pivot_sort_col, self._pivot_sort_asc
        if col == "Konto":
            try:
                tmp = grp.assign(_k = pd.to_numeric(grp["Konto"].astype(str).str.extract(r'(\d+)')[0], errors="coerce"))
                grp = tmp.sort_values(["_k","Kontonavn"], ascending=[asc, True], kind="mergesort").drop(columns=["_k"])
            except Exception:
                grp = grp.sort_values(["Konto","Kontonavn"], ascending=[asc, True], kind="mergesort")
        elif col in ("Kontonavn","Sum","Antall"):
            grp = grp.sort_values([col,"Antall"], ascending=[asc, False], kind="mergesort")

        self.pivot.delete(*self.pivot.get_children(""))
        add = self.pivot.insert
        for _, r in grp.iterrows():
            add("", "end", values=[r.get("Konto",""), r.get("Kontonavn",""), format_number_no(r.get("Sum",0.0),2), int(r.get("Antall",0))])

    def _on_pivot_heading(self, col: str):
        self._pivot_sort_asc = not self._pivot_sort_asc if self._pivot_sort_col == col else (col not in ("Sum","Antall"))
        self._pivot_sort_col = col
        self._build_pivot_cached(self._filtered, self._current_filter_state())
        self._refresh_summary()

    def _render_transactions_only(self):
        order = prefs.get("analyse.columns.order", []) or PRIORITY_TRANS_COLS
        visible = prefs.get("analyse.columns.visible", []) or order
        pins = prefs.get("analyse.pinned", []) or []
        self.trans.set_dataframe(self._filtered, pinned=pins, prefer_order=order, visible=visible, limit=self._display_limit)

    def _refresh_status(self):
        n = len(self._filtered) if isinstance(self._filtered, pd.DataFrame) else 0
        s = ""
        try:
            if n and "Beløp" in self._filtered.columns:
                s_val = float(self._filtered["Beløp"].astype(float).sum())
                s = format_number_no(s_val,2)
        except Exception: s = ""
        txt = f"Transaksjoner: {n:,} rader".replace(",", " ")
        if s: txt += f" | Sum: {s}"
        self.lbl_status.configure(text=txt)

    def _refresh_summary(self):
        df = self._filtered
        if df is None or df.empty:
            self.lbl_summary.configure(text="Oppsummering: rader=0 | sum=0,00 (viser 0)"); return
        sel = self.pivot.selection()
        if sel:
            acc = set()
            for iid in sel:
                vals = self.pivot.item(iid, "values")
                if vals: acc.add(str(vals[0]))
            dd = df[df["Konto"].astype(str).isin(acc)]
        else:
            dd = df
        n = len(dd)
        s_val = float(dd["Beløp"].astype(float).sum()) if "Beløp" in dd.columns else 0.0
        shown = min(self._display_limit or n, n)
        self.lbl_summary.configure(text=f"Oppsummering: rader={n:,} | sum={format_number_no(s_val,2)} (viser {shown:,})".replace(",", " "))

    def _send_to_selection(self):
        sel = self.pivot.selection()
        accounts = []
        for iid in sel:
            vals = self.pivot.item(iid, "values")
            if vals: accounts.append(str(vals[0]))
        if not accounts:
            accounts = [self.pivot.item(i, "values")[0] for i in self.pivot.get_children("")]
        try:
            if self.bus and hasattr(self.bus, "emit"):
                self.bus.emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})
            import session as SM
            s = getattr(SM,"SELECTION",{}) or {}
            s["accounts"] = accounts; s["version"] = int(s.get("version",0))+1; SM.SELECTION = s
            messagebox.showinfo("Utvalg", f"Overførte {len(accounts)} kontoer til Utvalg.")
        except Exception:
            pass
