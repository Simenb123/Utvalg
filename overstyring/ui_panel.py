from __future__ import annotations

import math
import numbers
from datetime import date, datetime


from dataclasses import dataclass
from typing import Any, Optional, Tuple, List, Dict


def _fmt_number_no(n: float, decimals: int = 2) -> str:
    """Formatter tall i norsk stil: mellomrom som tusenskille og komma som desimalskille."""
    try:
        s = f"{float(n):,.{decimals}f}"
    except Exception:
        return str(n)
    # Python bruker ',' som tusenskille og '.' som desimalskille -> bytt
    s = s.replace(",", "X").replace(".", ",").replace("X", " ")
    if decimals > 0:
        # Gjør visningen litt ryddigere når tall ender på ,00 / ,0 osv.
        while s.endswith("0"):
            s = s[:-1]
        if s.endswith(","):
            s = s[:-1]
    return s


def _fmt_int_no(n: int) -> str:
    try:
        s = f"{int(n):,d}"
    except Exception:
        return str(n)
    return s.replace(",", " ")


def _safe_int_str(v: Any) -> str:
    """Returner verdi som heltallsstreng uten tusenskille.

    Brukes for ID-kolonner som f.eks. "Bilag" og "Konto" der tusenskille
    ("13 913") kan gjøre identifikatorer vanskeligere å lese.
    """

    if v is None:
        return ""

    # Vanlige NA-varianter
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass

    if isinstance(v, bool):
        return "1" if v else "0"

    # Strenger kan inneholde mellomrom/komma o.l.
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() in {"nan", "none"}:
            return ""

        # Fjern NBSP og vanlige mellomrom
        s2 = s.replace("\xa0", " ").replace(" ", "")

        # Norsk format: 1.234,56 -> 1234.56
        if "," in s2 and "." in s2:
            s2 = s2.replace(".", "").replace(",", ".")
        elif "," in s2:
            s2 = s2.replace(",", ".")
        else:
            # Hvis punktum brukes som tusenskille (10.000 / 1.000.000)
            import re

            if re.fullmatch(r"\d{1,3}(\.\d{3})+", s2):
                s2 = s2.replace(".", "")

        try:
            f = float(s2)
        except Exception:
            return s

        if math.isnan(f) or math.isinf(f):
            return ""
        return str(int(round(f)))

    # Tall
    try:
        f = float(v)
    except Exception:
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return ""
    return str(int(round(f)))


def _fmt_date_no(v: Any) -> str:
    if isinstance(v, pd.Timestamp):
        v = v.to_pydatetime()
    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    # Fall back: prøv å parse via pandas
    try:
        dt = pd.to_datetime(v, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            return ""
        return dt.to_pydatetime().strftime("%d.%m.%Y")
    except Exception:
        return str(v)


def _is_amount_col(col: str) -> bool:
    c = col.lower()
    return any(k in c for k in ["beløp", "belop", "sum", "netto", "abs", "maks", "min", "terskel", "nivå", "roundbase"])


def _is_count_col(col: str) -> bool:
    c = col.lower()
    return ("antall" in c) or c.endswith("nunique")


def _fmt_cell(col: str, v: Any) -> str:
    """Formatterer celler i Treeview på en mer lesbar måte (NO-format)."""
    if v is None or pd.isna(v):
        return ""

    col_l = col.lower()

    # Dato
    if "dato" in col_l:
        return _fmt_date_no(v)

    # Bool
    if isinstance(v, bool):
        return "Ja" if v else "Nei"

    # Typiske ID-kolonner
    if col in ("Bilag", "Konto", "Kundenr", "Leverandørnr"):
        return _safe_int_str(v)

    # Tall (inkl. numpy-typer)
    if isinstance(v, numbers.Number):
        # Antall / Nunique osv. skal vises som heltall
        if col_l.startswith("antall") or "antall" in col_l or "nunique" in col_l or col_l.endswith("nuniq"):
            return _safe_int_str(v)

        x = float(v)
        # Vis uten desimaler dersom heltall (typisk for kroner)
        if abs(x - round(x)) < 1e-9:
            return _fmt_number_no(x, decimals=0)
        return _fmt_number_no(x, decimals=2)

    # Tall som tekst (f.eks. "348240.0")
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return ""
        try:
            x = float(s.replace(" ", "").replace("\u00A0", "").replace(",", "."))
            if abs(x - round(x)) < 1e-9:
                return _fmt_number_no(x, decimals=0)
            return _fmt_number_no(x, decimals=2)
        except Exception:
            return s

    return str(v)


import os
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from .core import CheckResult, resolve_core_columns
from .registry import CheckSpec, get_override_check_specs
from .ui_params import build_param_widgets, read_param_values


try:
    # I denne kodebasen ligger ofte moduler flatt i prosjektroten
    from views_virtual_transactions import VirtualTransactionsPanel  # type: ignore
except Exception:  # pragma: no cover
    VirtualTransactionsPanel = None  # type: ignore


@dataclass
class _ViewState:
    spec: CheckSpec
    params: dict[str, Any]
    result: CheckResult


class OverrideChecksPanel(ttk.Frame):
    """
    UI-panel som lar brukeren kjøre overstyrings-kontroller og se resultatet.

    Bevisst design:
      - Backend (pandas) er i overstyring/core.py + checks_*.py
      - Denne klassen er kun UI og orchestrering
    """

    def __init__(self, master: tk.Misc, df_all: pd.DataFrame, cols: Any | None = None) -> None:
        super().__init__(master)
        self._df_all = df_all
        self._cols = cols

        self._specs = get_override_check_specs()
        self._spec_by_title = {s.title: s for s in self._specs}
        self._current: _ViewState | None = None
        self._results_cache: dict[str, CheckResult] = {}

        self._colmap, _missing = resolve_core_columns(df_all, cols=cols, strict=False)
        self._bilag_col = self._colmap.get("bilag", "")

        # --- Top controls
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text="Kontroll:").pack(side="left")
        self._check_var = tk.StringVar(value=self._specs[0].title if self._specs else "")
        self._check_combo = ttk.Combobox(
            top,
            textvariable=self._check_var,
            values=[s.title for s in self._specs],
            state="readonly",
            width=30,
        )
        self._check_combo.pack(side="left", padx=(6, 10))
        self._check_combo.bind("<<ComboboxSelected>>", self._on_check_selected)

        self._run_btn = ttk.Button(top, text="Kjør", command=self._run_selected_check)
        self._run_btn.pack(side="left")

        self._export_btn = ttk.Button(top, text="Eksporter Excel", command=self._export_current)
        self._export_btn.pack(side="left", padx=(8, 0))

        # --- Params
        self._params_frame = ttk.Labelframe(self, text="Parametre")
        self._params_frame.pack(fill="x", padx=8, pady=(0, 6))

        self._param_vars: dict[str, tuple[str, tk.Variable]] = {}
        self._rebuild_params()

        # --- Summary + lines split
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=6)

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        # Summary label
        self._summary_info = tk.StringVar(value="Ingen resultat ennå.")
        ttk.Label(left, textvariable=self._summary_info).pack(anchor="w", pady=(0, 4))

        # Summary tree (i egen ramme, så vi ikke blander pack og grid)
        left_tree = ttk.Frame(left)
        left_tree.pack(fill="both", expand=True)

        self._summary_tree = ttk.Treeview(left_tree, show="headings", selectmode="extended")

        # Vertikal + horisontal scroll for å unngå at kolonner komprimeres
        # når det er mange felter i sammendraget.
        sb_y = ttk.Scrollbar(left_tree, orient="vertical", command=self._summary_tree.yview)
        sb_x = ttk.Scrollbar(left_tree, orient="horizontal", command=self._summary_tree.xview)
        self._summary_tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        left_tree.grid_rowconfigure(0, weight=1)
        left_tree.grid_columnconfigure(0, weight=1)
        self._summary_tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        self._summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)
        self._summary_tree.bind("<Double-1>", self._on_summary_double_click)

        # Lines area (VirtualTransactionsPanel if available)
        ttk.Label(right, text="Linjer").pack(anchor="w", pady=(0, 4))

        if VirtualTransactionsPanel is not None:
            self._lines_panel = VirtualTransactionsPanel(
                right,
                on_row_dblclick=self._on_lines_double_click,
                height=18,
            )
            self._lines_panel.pack(fill="both", expand=True)
        else:
            self._lines_panel = None
            self._lines_tree = ttk.Treeview(right, show="headings", selectmode="extended")
            self._lines_tree.pack(fill="both", expand=True, side="left")
            sb2 = ttk.Scrollbar(right, orient="vertical", command=self._lines_tree.yview)
            sb2.pack(fill="y", side="right")
            self._lines_tree.configure(yscrollcommand=sb2.set)
            self._lines_tree.bind("<Double-1>", lambda _e: self._on_lines_double_click())

        # Bottom buttons
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bottom, text="Drilldown", command=self._drilldown_selected).pack(side="right")

    # ---------- UI helpers ----------

    def _rebuild_params(self) -> None:
        for child in self._params_frame.winfo_children():
            child.destroy()

        spec = self._spec_by_title.get(self._check_var.get())
        if not spec:
            return

        frm = ttk.Frame(self._params_frame)
        frm.pack(fill="x", padx=6, pady=6)
        self._param_vars = build_param_widgets(frm, list(spec.params))

    def _on_check_selected(self, _evt: object) -> None:
        self._rebuild_params()

    def _run_selected_check(self) -> None:
        spec = self._spec_by_title.get(self._check_var.get())
        if not spec:
            messagebox.showerror("Overstyring", "Ingen kontroll valgt.")
            return

        params = read_param_values(self._param_vars)

        try:
            res = spec.runner(self._df_all, self._cols, params, self._results_cache)
        except Exception as e:
            messagebox.showerror("Overstyring", f"Kontrollen feilet:\n{e}")
            return

        self._results_cache[spec.id] = res
        self._current = _ViewState(spec=spec, params=params, result=res)

        self._render_result(res)

    def _render_result(self, res: CheckResult) -> None:
        if res.summary_df is None or res.summary_df.empty:
            self._summary_info.set("Ingen treff.")
            self._populate_summary_tree(pd.DataFrame())
            self._set_lines_df(pd.DataFrame())
            return

        self._summary_info.set(f"Bilag: {len(res.summary_df)} | Linjer: {len(res.lines_df)}")
        self._populate_summary_tree(res.summary_df)

        # Velg første rad automatisk
        if self._summary_tree.get_children():
            first = self._summary_tree.get_children()[0]
            self._summary_tree.selection_set(first)
            self._summary_tree.focus(first)
            self._summary_tree.see(first)

    def _populate_summary_tree(self, df: pd.DataFrame) -> None:
        """Fyller venstre tabell (bilag-sammendrag)."""

        self._summary_tree.delete(*self._summary_tree.get_children())
        if df is None or df.empty:
            return

        cols = list(df.columns)
        self._summary_tree["columns"] = cols
        self._summary_tree["show"] = "headings"

        # Sett opp kolonner:
        #  - Tall høyrejusteres
        #  - Dato venstrejusteres
        #  - Kolonnebredde estimeres fra innhold (første ~200 rader) så
        #    vi unngår at "DatoMin"/"DatoMax" osv. klippes.
        for c in cols:
            self._summary_tree.heading(c, text=c)

            cname = c.lower()
            is_date = "dato" in cname
            is_amount = _is_amount_col(c)
            is_count = _is_count_col(c)

            # Enkel numerikkdeteksjon (fallback)
            try:
                is_numeric_dtype = pd.api.types.is_numeric_dtype(df[c])
            except Exception:
                is_numeric_dtype = False

            is_numeric = (is_amount or is_count or is_numeric_dtype) and not is_date
            anchor = "e" if is_numeric else "w"

            # Estimer bredde fra formatterte verdier
            sample = df[c].head(200)
            max_len = max(4, len(c))
            for v in sample:
                try:
                    s = _fmt_cell(c, v)
                except Exception:
                    s = str(v)
                max_len = max(max_len, len(s))

            # Grov pixels-per-tegn (Tkinter varierer litt, men dette gir bedre
            # resultat enn kun header-lengde).
            width = max_len * 7 + 24
            if is_date:
                width = max(width, 110)
            if is_numeric:
                width = max(width, 90)

            # Clamp
            width = max(70, min(int(width), 340))

            # Viktig: stretch=False + horisontal scroll gjør at kolonner ikke
            # krymper til uleselige bredder.
            self._summary_tree.column(c, anchor=anchor, width=width, stretch=False)

        # Sett inn rader (formatter tall og datoer i norsk stil)
        for i, row in df.iterrows():
            values: list[str] = []
            for c in cols:
                v = row.get(c)
                values.append(_fmt_cell(c, v))
            self._summary_tree.insert("", "end", iid=str(i), values=values)
    def _selected_bilags(self) -> list[str]:
        if not self._current or self._current.result.summary_df is None or self._current.result.summary_df.empty:
            return []

        df = self._current.result.summary_df
        if "Bilag" not in df.columns:
            return []

        sel = self._summary_tree.selection()
        if not sel:
            return []

        # iid er indeks i df (se _populate_summary_tree)
        bilags: list[str] = []
        for iid in sel:
            try:
                idx = int(iid)
            except Exception:
                continue
            if 0 <= idx < len(df):
                bilags.append(str(df.iloc[idx]["Bilag"]))
        return [b for b in bilags if b and b.lower() != "nan"]

    def _on_summary_select(self, _evt: object) -> None:
        self._update_lines_for_selection()

    def _update_lines_for_selection(self) -> None:
        if not self._current:
            self._set_lines_df(pd.DataFrame())
            return

        bilags = self._selected_bilags()
        if not bilags:
            self._set_lines_df(pd.DataFrame())
            return

        lines = self._current.result.lines_df
        if lines is None or lines.empty or not self._bilag_col or self._bilag_col not in lines.columns:
            self._set_lines_df(pd.DataFrame())
            return

        # Vis linjer for alle valgte bilag (union)
        s = lines[self._bilag_col].astype("string")
        mask = s.isin([str(b) for b in bilags])
        lines_sel = lines[mask].copy()

        # (Valgfritt) begrens for å unngå at UI henger
        max_rows = 5000
        if len(lines_sel) > max_rows:
            lines_sel = lines_sel.head(max_rows).copy()
            self._summary_info.set(self._summary_info.get() + f" | (viser {max_rows} første linjer)")

        self._set_lines_df(lines_sel)

    def _set_lines_df(self, df: pd.DataFrame) -> None:
        if VirtualTransactionsPanel is not None and getattr(self, "_lines_panel", None) is not None:
            # Litt mer lesbar kolonne-rekkefølge + brukervennlige navn på interne kolonner
            df_show = df
            rename_map: dict[str, str] = {}
            if "__IsRound__" in df_show.columns:
                rename_map["__IsRound__"] = "Rund linje"
            if "__RoundBase__" in df_show.columns:
                rename_map["__RoundBase__"] = "Rundhetsnivå"
            if rename_map:
                df_show = df_show.rename(columns=rename_map)

            pinned: list[str] = []
            for c in (
                "Bilag",
                "Dato",
                "Konto",
                "Kontonavn",
                "Beløp",
                "Debet",
                "Kredit",
                "Tekst",
                "Kunder",
                "Kunde",
                "Kundenavn",
                "Leverandør",
                "Leverandørnavn",
                "Rund linje",
                "Rundhetsnivå",
            ):
                if c in df_show.columns and c not in pinned:
                    pinned.append(c)

            self._lines_panel.set_dataframe(df_show, pinned=pinned)  # type: ignore[attr-defined]
            return

        # Fallback tree
        tree: ttk.Treeview = getattr(self, "_lines_tree", None)
        if tree is None:
            return

        for item in tree.get_children():
            tree.delete(item)

        if df is None or df.empty:
            tree["columns"] = []
            return

        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120, anchor="w")

        for i, row in df.iterrows():
            values = [row.get(c, "") for c in cols]
            tree.insert("", "end", iid=str(i), values=values)

    # ---------- actions ----------

    def _drilldown_selected(self) -> None:
        bilags = self._selected_bilags()
        if not bilags:
            messagebox.showinfo("Overstyring", "Ingen bilag valgt.")
            return
        self._open_bilag_drill(bilags[0])

    def _on_summary_double_click(self, _evt: object) -> None:
        bilags = self._selected_bilags()
        if not bilags:
            return
        self._open_bilag_drill(bilags[0])

    def _on_lines_double_click(self) -> None:
        # Hvis vi dobbelklikker på en linje, prøv å åpne bilaget for den linja
        if not self._bilag_col:
            return

        # VirtualTransactionsPanel har sin egen tree: bruk selection via event? Vi holder oss til valgt bilag i summary.
        bilags = self._selected_bilags()
        if bilags:
            self._open_bilag_drill(bilags[0])

    def _open_bilag_drill(self, bilag_value: str) -> None:
        try:
            from selection_studio_drill import open_bilag_drill_dialog  # type: ignore
        except Exception as e:  # pragma: no cover
            messagebox.showerror("Overstyring", f"Drilldown er ikke tilgjengelig: {e}")
            return

        try:
            df_base = self._current.result.lines_df if self._current else self._df_all
            open_bilag_drill_dialog(
                master=self.winfo_toplevel(),
                df_base=df_base,
                df_all=self._df_all,
                bilag_value=bilag_value,
                bilag_col=self._bilag_col or "Bilag",
            )
        except Exception as e:
            messagebox.showerror("Overstyring", f"Kunne ikke åpne drilldown: {e}")

    def _export_current(self) -> None:
        if not self._current:
            messagebox.showinfo("Overstyring", "Ingen resultat å eksportere.")
            return

        try:
            from excel_export import export_temp_excel  # type: ignore
        except Exception as e:  # pragma: no cover
            messagebox.showerror("Overstyring", f"Excel-eksport er ikke tilgjengelig: {e}")
            return

        res = self._current.result
        if res.summary_df is None or res.summary_df.empty:
            messagebox.showinfo("Overstyring", "Ingen treff å eksportere.")
            return

        try:
            path = export_temp_excel(
                {
                    "Sammendrag": res.summary_df,
                    "Linjer": res.lines_df,
                },
                prefix="Overstyring_",
            )
        except Exception as e:
            messagebox.showerror("Overstyring", f"Eksport feilet: {e}")
            return

        # Åpne fil (Windows)
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("Overstyring", f"Excel-fil lagret:\n{path}")
