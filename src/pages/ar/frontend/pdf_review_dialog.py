"""Review dialog for RF-1086 PDF import.

Shows PDF preview on the left and extracted shareholder data on the right.
User can click a shareholder row to jump to that page in the PDF and see
transaction details with control calculation.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from ..backend.pdf_parser import ParseResult, ShareholderRecord
from src.shared.document_control.viewer import DocumentPreviewFrame


def _fmt_n(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _fmt_kr(v: float) -> str:
    if v == 0:
        return ""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ,", ",")


class ArRegistryPdfReviewDialog(tk.Toplevel):
    """Modal dialog for reviewing parsed RF-1086 data before import."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        pdf_path: str | Path,
        parse_result: ParseResult,
    ) -> None:
        super().__init__(master)
        self.title("RF-1086 Aksjonærregisteroppgaven")
        self.geometry("1300x820")
        self.minsize(1000, 650)
        self.resizable(True, True)
        if os.name != "nt":
            self.transient(master.winfo_toplevel())

        self._pdf_path = Path(pdf_path)
        self._parse_result = parse_result
        self._shareholders = parse_result.shareholders
        self.result: bool = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        self._build_ui()

        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        hdr = self._parse_result.header
        year_prev = str(int(hdr.year) - 1) if hdr.year.isdigit() else "?"

        # ── Main paned window (horizontal) ──
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 0))

        # ── Left: PDF preview ──
        left = ttk.Frame(pw)
        pw.add(left, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self._preview = DocumentPreviewFrame(left)
        self._preview.grid(row=0, column=0, sticky="nsew")
        self._preview.load_file(self._pdf_path)
        self._preview.after(200, self._preview.fit_to_width)

        # ── Right: data panel ──
        right = ttk.Frame(pw)
        pw.add(right, weight=3)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)  # shareholder tree
        right.rowconfigure(2, weight=1)  # detail panel

        # Company summary
        info_frame = ttk.LabelFrame(right, text="Selskapsopplysninger", padding=6)
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        info_frame.columnconfigure(1, weight=1)

        labels = [
            ("Selskap:", f"{hdr.company_name}  ({hdr.company_orgnr})"),
            ("År:", hdr.year),
            ("Antall aksjer:", f"{_fmt_n(hdr.antall_aksjer_start)}  ({year_prev})  \u2192  {_fmt_n(hdr.antall_aksjer_end)}  ({hdr.year})"),
        ]
        for r, (lbl, val) in enumerate(labels):
            ttk.Label(info_frame, text=lbl, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 8))
            ttk.Label(info_frame, text=val).grid(row=r, column=1, sticky="w")

        # Shareholders treeview
        cols = ("id", "navn", "type", "start", "slutt", "kontroll", "side")
        self._tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")

        self._tree.heading("id", text="ID")
        self._tree.heading("navn", text="Navn")
        self._tree.heading("type", text="Type")
        self._tree.heading("start", text=f"Aksjer {year_prev}")
        self._tree.heading("slutt", text=f"Aksjer {hdr.year}")
        self._tree.heading("kontroll", text="Kontroll")
        self._tree.heading("side", text="Side")

        self._tree.column("id", width=100, minwidth=80)
        self._tree.column("navn", width=180, minwidth=100)
        self._tree.column("type", width=60, minwidth=50)
        self._tree.column("start", width=80, minwidth=50, anchor="e")
        self._tree.column("slutt", width=80, minwidth=50, anchor="e")
        self._tree.column("kontroll", width=55, minwidth=40, anchor="center")
        self._tree.column("side", width=40, minwidth=35, anchor="center")

        tree_frame = ttk.Frame(right)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        # Populate rows
        for sh in self._shareholders:
            kind_label = "Person" if sh.shareholder_kind == "person" else "Selskap"
            tilgang = sum(t.shares for t in sh.transactions if t.direction == "tilgang")
            avgang = sum(t.shares for t in sh.transactions if t.direction == "avgang")
            calc = sh.shares_start + tilgang - avgang
            ok = "OK" if calc == sh.shares_end else f"AVVIK ({calc})"
            self._tree.insert("", "end", values=(
                sh.shareholder_id,
                sh.shareholder_name,
                kind_label,
                _fmt_n(sh.shares_start),
                _fmt_n(sh.shares_end),
                ok,
                sh.page_number,
            ))

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # ── Detail panel (transactions + control) ──
        self._detail_pw = ttk.PanedWindow(right, orient="vertical")
        self._detail_pw.grid(row=2, column=0, sticky="nsew", pady=(4, 0))

        detail_frame = ttk.LabelFrame(right, text="Detaljer", padding=4)
        self._detail_pw.add(detail_frame, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)

        self._detail_header = ttk.Label(detail_frame, text="Velg en aksjonær for å se detaljer.", foreground="#667085")
        self._detail_header.grid(row=0, column=0, sticky="w", pady=(0, 4))

        # Transaction treeview
        tx_cols = ("retning", "type", "aksjer", "dato", "beloep")
        self._tx_tree = ttk.Treeview(detail_frame, columns=tx_cols, show="headings", selectmode="none", height=5)
        self._tx_tree.heading("retning", text="Retning")
        self._tx_tree.heading("type", text="Type")
        self._tx_tree.heading("aksjer", text="Aksjer")
        self._tx_tree.heading("dato", text="Dato")
        self._tx_tree.heading("beloep", text="Beløp")

        self._tx_tree.column("retning", width=60, minwidth=50)
        self._tx_tree.column("type", width=80, minwidth=50)
        self._tx_tree.column("aksjer", width=60, minwidth=40, anchor="e")
        self._tx_tree.column("dato", width=85, minwidth=70)
        self._tx_tree.column("beloep", width=100, minwidth=70, anchor="e")

        tx_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self._tx_tree.yview)
        self._tx_tree.configure(yscrollcommand=tx_scroll.set)
        self._tx_tree.grid(row=1, column=0, sticky="nsew")
        tx_scroll.grid(row=1, column=1, sticky="ns")

        # Control line
        self._control_label = ttk.Label(detail_frame, text="", font=("Segoe UI", 9))
        self._control_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Warnings
        warnings = self._parse_result.warnings
        if warnings:
            warn_frame = ttk.LabelFrame(right, text=f"Advarsler ({len(warnings)})", padding=4)
            warn_frame.grid(row=3, column=0, sticky="ew", pady=(4, 0))
            warn_frame.columnconfigure(0, weight=1)
            for w in warnings:
                ttk.Label(warn_frame, text=f"  {w}", foreground="#b54708", wraplength=500, anchor="w").grid(sticky="w")

        # Status bar
        n = len(self._shareholders)
        sum_end = sum(sh.shares_end for sh in self._shareholders)
        total_ok = sum_end == hdr.antall_aksjer_end
        status = f"Aksjonærer: {n}  |  Sum aksjer: {_fmt_n(sum_end)} / {_fmt_n(hdr.antall_aksjer_end)}"
        if not total_ok:
            status += "  (AVVIK)"
        self._status_var = tk.StringVar(value=status)
        status_lbl = ttk.Label(self, textvariable=self._status_var, foreground="#067647" if total_ok else "#b54708")
        status_lbl.grid(row=1, column=0, sticky="w", padx=8, pady=(2, 0))

        # ── Bottom buttons ──
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=8)
        btn_frame.columnconfigure(0, weight=1)

        ttk.Button(btn_frame, text="Avbryt", command=self._on_cancel).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(btn_frame, text="Importer", command=self._on_import, style="Accent.TButton").grid(row=0, column=2)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        values = self._tree.item(sel[0], "values")
        if not values:
            return

        # Navigate PDF
        try:
            page_nr = int(values[6])
            self._preview.show_page(page_nr)
        except (IndexError, ValueError):
            pass

        # Find the shareholder
        sh_id = values[0]
        sh = next((s for s in self._shareholders if s.shareholder_id == sh_id), None)
        if sh:
            self._show_detail(sh)

    def _show_detail(self, sh: ShareholderRecord) -> None:
        hdr = self._parse_result.header
        year_prev = str(int(hdr.year) - 1) if hdr.year.isdigit() else "?"

        # Header
        addr = f"{sh.address}, {sh.postal_code} {sh.postal_place}" if sh.address else ""
        header_text = f"{sh.shareholder_name}  ({sh.shareholder_id})"
        if addr:
            header_text += f"  —  {addr}"
        self._detail_header.config(text=header_text, foreground="")

        # Transactions
        self._tx_tree.delete(*self._tx_tree.get_children())
        for t in sh.transactions:
            retning = "Tilgang" if t.direction == "tilgang" else "Avgang"
            self._tx_tree.insert("", "end", values=(
                retning,
                t.trans_type,
                _fmt_n(t.shares),
                t.date,
                _fmt_kr(t.amount),
            ))

        # Control calculation
        tilgang = sum(t.shares for t in sh.transactions if t.direction == "tilgang")
        avgang = sum(t.shares for t in sh.transactions if t.direction == "avgang")
        calc_end = sh.shares_start + tilgang - avgang
        ok = calc_end == sh.shares_end

        ctrl = (
            f"Kontroll:  {_fmt_n(sh.shares_start)} ({year_prev})"
            f"  +  {_fmt_n(tilgang)} tilgang"
            f"  \u2212  {_fmt_n(avgang)} avgang"
            f"  =  {_fmt_n(calc_end)}"
        )
        if ok:
            ctrl += f"  (stemmer med {_fmt_n(sh.shares_end)})"
            self._control_label.config(text=ctrl, foreground="#067647")
        else:
            ctrl += f"  (PDF viser {_fmt_n(sh.shares_end)} — AVVIK)"
            self._control_label.config(text=ctrl, foreground="#b54708")

    def _on_import(self) -> None:
        self.result = True
        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.grab_release()
        self.destroy()
