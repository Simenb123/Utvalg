"""page_consolidation.py — Konsolidering MVP arbeidsflate.

Layout (Analyse-lignende):
  Toolbar:  [Importer selskap] [Kjoer konsolidering] [Eksporter]
  Status:   "N selskaper | M elimineringer | Siste run: ..."
  Venstre:  [Selskaper] [Eliminering]  (tabs)
  Hoeyre:   [Detalj]    [Resultat]     (tabs)
  Statuslinje: Konsolidering | Klient / Aar | TB-only
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import session
from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
)
from consolidation import storage, tb_import

logger = logging.getLogger(__name__)


class ConsolidationPage(ttk.Frame):  # type: ignore[misc]
    """Hovedside for konsolidering MVP."""

    def __init__(self, master=None):
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            self._status_var = None
            return

        self._project: Optional[ConsolidationProject] = None
        self._company_tbs: dict[str, pd.DataFrame] = {}
        self._mapped_tbs: dict[str, pd.DataFrame] = {}
        self._result_df: Optional[pd.DataFrame] = None

        self._status_var = tk.StringVar(value="Velg klient og aar for aa starte.")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Toolbar ---
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ttk.Button(toolbar, text="Importer selskap", command=self._on_import_company).pack(
            side="left", padx=(0, 4),
        )
        self._btn_use_session_tb = ttk.Button(
            toolbar, text="Bruk aktiv SB", command=self._on_use_session_tb,
        )
        self._btn_use_session_tb.pack(side="left", padx=(0, 4))
        self._btn_use_session_tb.pack_forget()  # skjult til SB er tilgjengelig

        self._btn_run = ttk.Button(toolbar, text="Kjoer konsolidering", command=self._on_run)
        self._btn_run.pack(side="left", padx=(0, 4))
        self._btn_export = ttk.Button(toolbar, text="Eksporter", command=self._on_export)
        self._btn_export.pack(side="left", padx=(0, 4))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        ttk.Label(toolbar, textvariable=self._status_var).pack(side="left")

        # --- Main paned area ---
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        # Left: tabs Selskaper / Eliminering
        left_nb = ttk.Notebook(pw)
        self._left_nb = left_nb

        # Tab: Selskaper
        frm_companies = ttk.Frame(left_nb)
        left_nb.add(frm_companies, text="Selskaper")
        self._tree_companies = self._make_company_tree(frm_companies)

        # Tab: Eliminering
        frm_elim = ttk.Frame(left_nb)
        left_nb.add(frm_elim, text="Eliminering")
        self._build_elimination_tab(frm_elim)

        pw.add(left_nb, weight=3)

        # Right: tabs Detalj / Resultat
        right_nb = ttk.Notebook(pw)
        self._right_nb = right_nb

        # Tab: Detalj
        frm_detail = ttk.Frame(right_nb)
        right_nb.add(frm_detail, text="Detalj")
        self._tree_detail = self._make_detail_tree(frm_detail)

        # Tab: Resultat
        frm_result = ttk.Frame(right_nb)
        right_nb.add(frm_result, text="Resultat")
        self._tree_result = self._make_result_tree(frm_result)

        pw.add(right_nb, weight=5)

        # --- Statuslinje ---
        status_bar = ttk.Frame(self)
        status_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._lbl_statusbar = ttk.Label(
            status_bar, text="Konsolidering | TB-only", anchor="w",
        )
        self._lbl_statusbar.pack(fill="x")

    # ------------------------------------------------------------------
    # Treeview builders
    # ------------------------------------------------------------------

    def _make_company_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        cols = ("name", "source", "rows", "mapping")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        tree.heading("name", text="Selskap")
        tree.heading("source", text="Kilde")
        tree.heading("rows", text="Rader")
        tree.heading("mapping", text="Mapping")
        tree.column("name", width=160)
        tree.column("source", width=80)
        tree.column("rows", width=60, anchor="e")
        tree.column("mapping", width=80)
        tree.tag_configure("done", background="#E2F1EB")
        tree.tag_configure("review", background="#FCEBD9")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tree.bind("<<TreeviewSelect>>", self._on_company_select)
        tree.bind("<Delete>", self._on_delete_company)
        tree.bind("<Return>", self._on_company_select)

        # Hoeyreklikk-meny
        self._company_menu = tk.Menu(tree, tearoff=0)
        self._company_menu.add_command(label="Vis detalj", command=self._on_company_select)
        self._company_menu.add_command(label="Importer paa nytt", command=self._on_reimport_company)
        self._company_menu.add_separator()
        self._company_menu.add_command(label="Slett selskap", command=self._on_delete_company)
        tree.bind("<Button-3>", self._on_company_right_click)
        return tree

    def _make_detail_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        cols = ("konto", "kontonavn", "regnr", "ib", "ub", "netto")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            tree.heading(c, text=c.capitalize())
            w = 140 if c == "kontonavn" else 80
            anchor = "w" if c == "kontonavn" else "e"
            tree.column(c, width=w, anchor=anchor)
        tree.tag_configure("review", background="#FCEBD9")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Ctrl+C kopiering
        tree.bind("<Control-c>", lambda e: self._copy_tree_to_clipboard(tree))
        return tree

    def _make_result_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=(), show="headings", selectmode="browse")
        tree.tag_configure("sumline", background="#EDF1F5")
        tree.tag_configure("sumline_major", background="#E0E4EA")
        tree.tag_configure("neg", foreground="red")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Ctrl+C kopiering
        tree.bind("<Control-c>", lambda e: self._copy_tree_to_clipboard(tree))
        return tree

    # ------------------------------------------------------------------
    # Elimination tab
    # ------------------------------------------------------------------

    def _build_elimination_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=4)
        ttk.Button(top, text="Ny journal", command=self._on_new_journal).pack(side="left")
        ttk.Button(top, text="Slett journal", command=self._on_delete_journal).pack(side="left", padx=(4, 0))

        cols_j = ("name", "lines", "balance")
        self._tree_journals = ttk.Treeview(parent, columns=cols_j, show="headings", height=6)
        self._tree_journals.heading("name", text="Journal")
        self._tree_journals.heading("lines", text="Linjer")
        self._tree_journals.heading("balance", text="Balanse")
        self._tree_journals.column("name", width=140)
        self._tree_journals.column("lines", width=50, anchor="e")
        self._tree_journals.column("balance", width=90)
        self._tree_journals.tag_configure("warning", background="#FCEBD9")
        self._tree_journals.tag_configure("done", background="#E2F1EB")
        self._tree_journals.pack(fill="x", padx=4)
        self._tree_journals.bind("<<TreeviewSelect>>", self._on_journal_select)
        self._tree_journals.bind("<Delete>", lambda e: self._on_delete_journal())

        sep = ttk.Separator(parent, orient="horizontal")
        sep.pack(fill="x", padx=4, pady=4)

        line_bar = ttk.Frame(parent)
        line_bar.pack(fill="x", padx=4)
        ttk.Button(line_bar, text="Legg til linje", command=self._on_add_elim_line).pack(side="left")
        ttk.Button(line_bar, text="Slett linje", command=self._on_delete_elim_line).pack(side="left", padx=(4, 0))

        self._elim_balance_var = tk.StringVar(value="")
        ttk.Label(line_bar, textvariable=self._elim_balance_var).pack(side="right")

        cols_l = ("regnr", "company", "amount", "desc")
        self._tree_elim_lines = ttk.Treeview(parent, columns=cols_l, show="headings")
        self._tree_elim_lines.heading("regnr", text="Regnr")
        self._tree_elim_lines.heading("company", text="Selskap")
        self._tree_elim_lines.heading("amount", text="Beloep")
        self._tree_elim_lines.heading("desc", text="Beskrivelse")
        self._tree_elim_lines.column("regnr", width=60, anchor="e")
        self._tree_elim_lines.column("company", width=120)
        self._tree_elim_lines.column("amount", width=100, anchor="e")
        self._tree_elim_lines.column("desc", width=160)
        self._tree_elim_lines.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        self._tree_elim_lines.bind("<Delete>", lambda e: self._on_delete_elim_line())

    # ------------------------------------------------------------------
    # Session / project loading
    # ------------------------------------------------------------------

    def refresh_from_session(self, sess: object) -> None:
        if not self._tk_ok or self._status_var is None:
            return

        client = str(getattr(sess, "client", "") or "").strip()
        year = str(getattr(sess, "year", "") or "").strip()

        if not client or not year:
            self._status_var.set("Velg klient og aar for aa starte.")
            self._project = None
            self._update_session_tb_button(sess)
            return

        self._lbl_statusbar.configure(text=f"Konsolidering | {client} / {year} | TB-only")

        proj = storage.load_project(client, year)
        if proj is not None:
            self._project = proj
            self._load_company_tbs()
            self._compute_mapping_status()
            self._refresh_company_tree()
            self._refresh_journal_tree()
            self._update_status()
        else:
            self._project = None
            self._company_tbs.clear()
            self._mapped_tbs.clear()
            self._tree_companies.delete(*self._tree_companies.get_children())
            self._tree_journals.delete(*self._tree_journals.get_children())
            self._tree_elim_lines.delete(*self._tree_elim_lines.get_children())
            self._status_var.set(
                f"{client} / {year} — ingen konsolideringsprosjekt. "
                "Importer et selskap for aa starte."
            )

        self._update_session_tb_button(sess)

    def _ensure_project(self) -> ConsolidationProject:
        if self._project is not None:
            return self._project

        client = str(getattr(session, "client", "") or "").strip()
        year = str(getattr(session, "year", "") or "").strip()
        if not client or not year:
            raise RuntimeError("Klient/aar er ikke valgt.")

        self._project = ConsolidationProject(client=client, year=year)
        storage.save_project(self._project)
        return self._project

    def _update_session_tb_button(self, sess: object) -> None:
        """Show/hide 'Bruk aktiv SB' button based on session.tb_df availability."""
        tb = getattr(sess, "tb_df", None)
        has_tb = tb is not None and isinstance(tb, pd.DataFrame) and not tb.empty

        # Check if session TB is already imported as a company
        already_imported = False
        if has_tb and self._project is not None:
            for c in self._project.companies:
                if c.source_type == "session":
                    already_imported = True
                    break

        if has_tb and not already_imported:
            self._btn_use_session_tb.pack(side="left", padx=(0, 4), before=self._btn_run)
        else:
            self._btn_use_session_tb.pack_forget()

    def _on_use_session_tb(self) -> None:
        """Import the active session TB as a company."""
        tb = getattr(session, "tb_df", None)
        if tb is None or (isinstance(tb, pd.DataFrame) and tb.empty):
            messagebox.showinfo("Saldobalanse", "Ingen aktiv saldobalanse i session.")
            return

        client = str(getattr(session, "client", "") or "").strip()
        if not client:
            messagebox.showwarning("Saldobalanse", "Velg klient foerst.")
            return

        name = simpledialog.askstring(
            "Selskapsnavn",
            "Skriv inn selskapsnavn for aktiv saldobalanse:",
            initialvalue=client,
        )
        if not name:
            return

        proj = self._ensure_project()

        company = CompanyTB(
            name=name,
            source_type="session",
            source_file="aktiv saldobalanse",
            row_count=len(tb),
            has_ib=bool("ib" in tb.columns and tb["ib"].notna().any()),
        )
        proj.companies.append(company)
        self._company_tbs[company.company_id] = tb
        storage.save_company_tb(proj.client, proj.year, company.company_id, tb)
        storage.save_project(proj)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._update_status()

        # Hide the button now that TB is imported
        self._btn_use_session_tb.pack_forget()

    def _load_company_tbs(self) -> None:
        self._company_tbs.clear()
        if self._project is None:
            return
        for c in self._project.companies:
            tb = storage.load_company_tb(
                self._project.client, self._project.year, c.company_id,
            )
            if tb is not None:
                self._company_tbs[c.company_id] = tb

    # ------------------------------------------------------------------
    # Mapping status
    # ------------------------------------------------------------------

    def _compute_mapping_status(self) -> None:
        """Beregn mapping-status per selskap (proesentandel mappede kontoer)."""
        self._mapped_tbs.clear()
        self._mapping_pct: dict[str, int] = {}
        self._mapping_unmapped: dict[str, list[str]] = {}

        if self._project is None:
            return

        try:
            from consolidation.mapping import map_company_tb, load_shared_config
            intervals, regnskapslinjer = load_shared_config()
        except Exception:
            # Config mangler — alle selskaper faar "—"
            for c in self._project.companies:
                self._mapping_pct[c.company_id] = -1
            return

        for c in self._project.companies:
            tb = self._company_tbs.get(c.company_id)
            if tb is None or tb.empty:
                self._mapping_pct[c.company_id] = -1
                continue
            overrides = self._project.mapping_config.company_overrides.get(c.company_id)
            try:
                mapped_df, unmapped = map_company_tb(
                    tb, overrides, intervals=intervals, regnskapslinjer=regnskapslinjer,
                )
                self._mapped_tbs[c.company_id] = mapped_df
                self._mapping_unmapped[c.company_id] = unmapped
                total = len(mapped_df)
                mapped_count = mapped_df["regnr"].notna().sum()
                self._mapping_pct[c.company_id] = int(mapped_count * 100 / total) if total > 0 else 0
            except Exception:
                self._mapping_pct[c.company_id] = -1

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        if self._project is None:
            return
        nc = len(self._project.companies)
        ne = len(self._project.eliminations)
        last_run = ""
        if self._project.runs:
            from datetime import datetime
            r = self._project.runs[-1]
            last_run = f" | Siste run: {datetime.fromtimestamp(r.run_at).strftime('%H:%M')}"
        self._status_var.set(f"{nc} selskaper | {ne} elimineringer{last_run}")

    def _refresh_company_tree(self) -> None:
        tree = self._tree_companies
        tree.delete(*tree.get_children())
        if self._project is None:
            return
        for c in self._project.companies:
            pct = self._mapping_pct.get(c.company_id, -1)
            if pct < 0:
                mapping_text = "—"
                tag = ()
            elif pct >= 100:
                mapping_text = "100%"
                tag = ("done",)
            else:
                mapping_text = f"{pct}%"
                tag = ("review",) if pct < 90 else ()

            tree.insert("", "end", iid=c.company_id, values=(
                c.name, c.source_type, c.row_count, mapping_text,
            ), tags=tag)

    def _refresh_journal_tree(self) -> None:
        tree = self._tree_journals
        tree.delete(*tree.get_children())
        self._tree_elim_lines.delete(*self._tree_elim_lines.get_children())
        self._elim_balance_var.set("")
        if self._project is None:
            return
        for j in self._project.eliminations:
            if j.is_balanced:
                bal_text = "OK"
                tag = ("done",)
            else:
                bal_text = f"Ubalanse ({j.net:,.0f})"
                tag = ("warning",)
            tree.insert("", "end", iid=j.journal_id, values=(
                j.name, len(j.lines), bal_text,
            ), tags=tag)

    def _refresh_elim_lines(self, journal: EliminationJournal) -> None:
        tree = self._tree_elim_lines
        tree.delete(*tree.get_children())
        name_map = {}
        if self._project:
            name_map = {c.company_id: c.name for c in self._project.companies}
        for i, line in enumerate(journal.lines):
            tree.insert("", "end", iid=str(i), values=(
                line.regnr,
                name_map.get(line.company_id, line.company_id[:12]),
                f"{line.amount:,.2f}",
                line.description,
            ))
        # Vis balanseindikator
        if journal.is_balanced:
            self._elim_balance_var.set("Balansert")
        else:
            self._elim_balance_var.set(f"Netto: {journal.net:,.2f}")

    def _show_company_detail(self, company_id: str) -> None:
        """Vis selskapets TB i Detalj-fanen (med mapping-status)."""
        tree = self._tree_detail
        tree.delete(*tree.get_children())

        # Bruk mapped TB hvis tilgjengelig, ellers raa TB
        tb = self._mapped_tbs.get(company_id) or self._company_tbs.get(company_id)
        if tb is None:
            return

        unmapped = set(self._mapping_unmapped.get(company_id, []))
        self._right_nb.select(0)

        for _, row in tb.iterrows():
            regnr = row.get("regnr", "")
            konto = str(row.get("konto", ""))
            tag = ("review",) if konto in unmapped else ()
            tree.insert("", "end", values=(
                konto,
                row.get("kontonavn", ""),
                int(regnr) if pd.notna(regnr) else "",
                f"{float(row.get('ib', 0)):,.2f}",
                f"{float(row.get('ub', 0)):,.2f}",
                f"{float(row.get('netto', 0)):,.2f}",
            ), tags=tag)

    def _show_result(self, result_df: pd.DataFrame) -> None:
        """Vis konsolideringsresultat i Resultat-fanen."""
        tree = self._tree_result
        tree.delete(*tree.get_children())

        meta_cols = {"regnr", "regnskapslinje", "sumpost", "formel"}
        data_cols = [c for c in result_df.columns if c not in meta_cols]
        all_cols = ["regnr", "regnskapslinje"] + data_cols

        tree["columns"] = all_cols
        tree.heading("regnr", text="Nr")
        tree.heading("regnskapslinje", text="Regnskapslinje")
        tree.column("regnr", width=50, anchor="e")
        tree.column("regnskapslinje", width=160, anchor="w")
        for dc in data_cols:
            tree.heading(dc, text=dc)
            tree.column(dc, width=100, anchor="e")

        for _, row in result_df.iterrows():
            is_sum = bool(row.get("sumpost", False))
            vals = [int(row["regnr"]), row["regnskapslinje"]]
            any_neg = False
            for dc in data_cols:
                v = row.get(dc, 0.0)
                if pd.notna(v):
                    fv = float(v)
                    vals.append(f"{fv:,.2f}")
                    if fv < -0.005:
                        any_neg = True
                else:
                    vals.append("")

            tags = []
            if is_sum:
                tags.append("sumline")
            if any_neg and not is_sum:
                tags.append("neg")
            tree.insert("", "end", values=vals, tags=tuple(tags))

        self._right_nb.select(1)

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _copy_tree_to_clipboard(self, tree: ttk.Treeview) -> None:
        """Kopier alle synlige rader som TSV til clipboard."""
        lines = []
        cols = tree["columns"]
        lines.append("\t".join(str(tree.heading(c, "text")) for c in cols))
        for iid in tree.get_children():
            vals = tree.item(iid, "values")
            lines.append("\t".join(str(v) for v in vals))
        text = "\n".join(lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Right-click
    # ------------------------------------------------------------------

    def _on_company_right_click(self, event) -> None:
        iid = self._tree_companies.identify_row(event.y)
        if iid:
            self._tree_companies.selection_set(iid)
            self._company_menu.post(event.x_root, event.y_root)

    def _on_reimport_company(self) -> None:
        """Importer TB paa nytt for valgt selskap."""
        sel = self._tree_companies.selection()
        if not sel or self._project is None:
            return
        company = self._project.find_company(sel[0])
        if company is None:
            return

        path = filedialog.askopenfilename(
            title=f"Reimporter TB for {company.name}",
            filetypes=[
                ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        try:
            _, df, warnings = tb_import.import_company_tb(path, company.name)
        except Exception as exc:
            messagebox.showerror("Importfeil", str(exc))
            return

        if warnings:
            messagebox.showwarning("Import-advarsler", "\n".join(warnings))

        company.source_file = Path(path).name
        company.row_count = len(df)
        company.has_ib = bool((df["ib"].abs() > 0.005).any()) if "ib" in df.columns else False
        self._company_tbs[company.company_id] = df
        storage.save_company_tb(
            self._project.client, self._project.year, company.company_id, df,
        )
        storage.save_project(self._project)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._show_company_detail(company.company_id)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_company_select(self, _event=None) -> None:
        sel = self._tree_companies.selection()
        if sel:
            self._show_company_detail(sel[0])

    def _on_delete_company(self, _event=None) -> None:
        sel = self._tree_companies.selection()
        if not sel or self._project is None:
            return
        cid = sel[0]
        company = self._project.find_company(cid)
        if company is None:
            return
        if not messagebox.askyesno("Slett selskap", f"Slett {company.name}?"):
            return
        self._project.companies = [c for c in self._project.companies if c.company_id != cid]
        self._company_tbs.pop(cid, None)
        self._mapped_tbs.pop(cid, None)
        self._mapping_pct.pop(cid, None)
        storage.delete_company_tb(self._project.client, self._project.year, cid)
        storage.save_project(self._project)
        self._refresh_company_tree()
        self._tree_detail.delete(*self._tree_detail.get_children())
        self._update_status()

    def _on_import_company(self) -> None:
        path = filedialog.askopenfilename(
            title="Importer saldobalanse",
            filetypes=[
                ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        name = simpledialog.askstring(
            "Selskapsnavn",
            "Skriv inn selskapsnavn:",
            initialvalue=Path(path).stem,
        )
        if not name:
            return

        try:
            company, df, warnings = tb_import.import_company_tb(path, name)
        except Exception as exc:
            messagebox.showerror("Importfeil", str(exc))
            return

        if warnings:
            messagebox.showwarning("Import-advarsler", "\n".join(warnings))

        proj = self._ensure_project()
        proj.companies.append(company)
        self._company_tbs[company.company_id] = df
        storage.save_company_tb(proj.client, proj.year, company.company_id, df)
        storage.save_project(proj)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._update_status()

    def _on_journal_select(self, _event=None) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal:
            self._refresh_elim_lines(journal)

    def _on_new_journal(self) -> None:
        name = simpledialog.askstring(
            "Ny elimineringsjournal",
            "Journalnavn:",
            initialvalue="Ny eliminering",
        )
        if not name:
            return

        proj = self._ensure_project()
        journal = EliminationJournal(name=name)
        proj.eliminations.append(journal)
        storage.save_project(proj)
        self._refresh_journal_tree()
        self._update_status()

    def _on_delete_journal(self) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        jid = sel[0]
        journal = self._project.find_journal(jid)
        if journal is None:
            return
        if not messagebox.askyesno("Slett journal", f"Slett '{journal.name}'?"):
            return
        self._project.eliminations = [
            j for j in self._project.eliminations if j.journal_id != jid
        ]
        storage.save_project(self._project)
        self._refresh_journal_tree()
        self._update_status()

    def _on_add_elim_line(self) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal is None:
            return

        company_names = {c.company_id: c.name for c in self._project.companies}
        if not company_names:
            messagebox.showwarning("Ingen selskaper", "Importer minst ett selskap foerst.")
            return

        # Samle-dialog: "regnr ; beloep ; selskap ; beskrivelse"
        company_hint = ", ".join(company_names.values())
        raw = simpledialog.askstring(
            "Ny elimineringslinje",
            f"Regnr ; Beloep ; Selskap ; Beskrivelse\n"
            f"Selskaper: {company_hint}\n"
            f"Eksempel: 3000 ; -500000 ; {list(company_names.values())[0]} ; Interco salg",
        )
        if not raw:
            return

        parts = [p.strip() for p in raw.split(";")]
        if len(parts) < 2:
            messagebox.showerror("Feil", "Skriv minst: regnr ; beloep")
            return

        try:
            regnr = int(parts[0])
        except ValueError:
            messagebox.showerror("Feil", "Regnr maa vaere et heltall.")
            return

        try:
            amount = float(parts[1].replace(",", ".").replace(" ", ""))
        except ValueError:
            messagebox.showerror("Feil", "Ugyldig beloep.")
            return

        # Match selskap
        company_id = list(company_names.keys())[0]
        if len(parts) >= 3 and parts[2]:
            needle = parts[2].lower()
            for cid, cname in company_names.items():
                if needle in cname.lower() or needle in cid.lower():
                    company_id = cid
                    break

        desc = parts[3] if len(parts) >= 4 else ""

        line = EliminationLine(
            regnr=regnr, company_id=company_id, amount=amount, description=desc,
        )
        journal.lines.append(line)
        storage.save_project(self._project)
        self._refresh_journal_tree()
        self._refresh_elim_lines(journal)

    def _on_delete_elim_line(self) -> None:
        sel_j = self._tree_journals.selection()
        sel_l = self._tree_elim_lines.selection()
        if not sel_j or not sel_l or self._project is None:
            return
        journal = self._project.find_journal(sel_j[0])
        if journal is None:
            return
        try:
            idx = int(sel_l[0])
            if 0 <= idx < len(journal.lines):
                journal.lines.pop(idx)
                storage.save_project(self._project)
                self._refresh_journal_tree()
                self._refresh_elim_lines(journal)
        except (ValueError, IndexError):
            pass

    def _on_run(self) -> None:
        if self._project is None:
            messagebox.showwarning("Konsolidering", "Ingen prosjekt. Importer minst ett selskap.")
            return
        if len(self._project.companies) < 1:
            messagebox.showwarning("Konsolidering", "Importer minst ett selskap foerst.")
            return

        from consolidation.engine import run_consolidation
        from consolidation.mapping import ConfigNotLoadedError

        try:
            result_df, run_result = run_consolidation(self._project, self._company_tbs)
        except ConfigNotLoadedError as exc:
            messagebox.showerror("Konfigurasjon mangler", str(exc))
            return
        except ValueError as exc:
            messagebox.showerror("Feil", str(exc))
            return
        except Exception as exc:
            logger.exception("Konsolidering feilet")
            messagebox.showerror("Feil", f"Konsolidering feilet:\n{exc}")
            return

        self._result_df = result_df
        self._project.runs.append(run_result)
        storage.save_project(self._project)

        if run_result.warnings:
            messagebox.showwarning("Advarsler", "\n".join(run_result.warnings))

        self._show_result(result_df)
        self._update_status()

    def _on_export(self) -> None:
        if self._result_df is None or self._project is None:
            messagebox.showwarning("Eksport", "Kjoer konsolidering foerst.")
            return

        from consolidation.export import save_consolidation_workbook

        path = filedialog.asksaveasfilename(
            title="Eksporter konsolidering",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"konsolidering_{self._project.client}_{self._project.year}.xlsx",
        )
        if not path:
            return

        run_result = self._project.runs[-1] if self._project.runs else None
        if run_result is None:
            return

        try:
            out = save_consolidation_workbook(
                path,
                result_df=self._result_df,
                companies=self._project.companies,
                eliminations=self._project.eliminations,
                mapped_tbs=self._company_tbs,
                run_result=run_result,
                client=self._project.client,
                year=self._project.year,
            )
            messagebox.showinfo("Eksport", f"Lagret til:\n{out}")
        except Exception as exc:
            logger.exception("Export failed")
            messagebox.showerror("Eksportfeil", str(exc))
