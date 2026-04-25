"""page_ar_import_detail_dialog.py — read-only dialog for persisted RF-1086 imports.

Utskilt fra page_ar.py. Inneholder kun dialog-klassen.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..backend.formatters import _fmt_currency, _fmt_pct, _fmt_thousand, _safe_text


class _ImportDetailDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, detail: dict) -> None:
        super().__init__(master)
        self._detail = detail or {}
        header = self._detail.get("header") or {}
        reg_year = _safe_text(header.get("register_year")) or _safe_text(header.get("target_year"))
        company = _safe_text(header.get("company_name")) or _safe_text(header.get("company_orgnr"))
        self.title(f"Importdetaljer — {company} ({reg_year})")
        self.geometry("1100x720")
        self.minsize(900, 560)
        self.resizable(True, True)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        self._build_header(header)
        self._build_shareholders()
        self._build_transactions()
        self._build_buttons(header)

        self.grab_set()
        self.focus_set()

    def _build_header(self, header: dict) -> None:
        info = ttk.LabelFrame(self, text="Importinfo", padding=6)
        info.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        info.columnconfigure(1, weight=1)

        company = _safe_text(header.get("company_name"))
        orgnr = _safe_text(header.get("company_orgnr"))
        reg_year = _safe_text(header.get("register_year"))
        target_year = _safe_text(header.get("target_year"))
        source = _safe_text(header.get("source_file"))
        imported_at = _safe_text(header.get("imported_at_utc"))[:19]
        sh_count = int(header.get("shareholders_count") or 0)

        rows = [
            ("Selskap:", f"{company}  ({orgnr})" if orgnr else company),
            ("Registerår:", reg_year + (f"  (klientår {target_year})" if target_year and target_year != reg_year else "")),
            ("Importert:", imported_at or "-"),
            ("Kildefil:", source or "-"),
            ("Aksjonærer:", _fmt_thousand(sh_count)),
        ]
        for r, (lbl, val) in enumerate(rows):
            ttk.Label(info, text=lbl, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 8))
            ttk.Label(info, text=val, wraplength=900, justify="left").grid(row=r, column=1, sticky="w")

    def _build_shareholders(self) -> None:
        frame = ttk.LabelFrame(self, text="Aksjonærer", padding=4)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("id", "navn", "type", "start", "slutt", "pct_start", "pct_end", "side")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        headings = [
            ("id", "ID", 110),
            ("navn", "Navn", 220),
            ("type", "Type", 70),
            ("start", "Aksjer start", 100),
            ("slutt", "Aksjer slutt", 100),
            ("pct_start", "% start", 80),
            ("pct_end", "% slutt", 80),
            ("side", "Side", 50),
        ]
        for cid, text, width in headings:
            tree.heading(cid, text=text)
            anchor = "e" if cid in {"start", "slutt", "pct_start", "pct_end"} else ("center" if cid == "side" else "w")
            tree.column(cid, width=width, anchor=anchor)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")

        self._tree_sh = tree
        self._sh_by_iid: dict[str, dict] = {}

        for idx, sh in enumerate(self._detail.get("shareholders") or [], start=1):
            iid = f"sh-{idx}"
            self._sh_by_iid[iid] = sh
            kind = _safe_text(sh.get("shareholder_kind")) or "-"
            kind_label = "Person" if kind == "person" else ("Selskap" if kind == "company" else kind)
            tree.insert("", "end", iid=iid, values=(
                _safe_text(sh.get("shareholder_id")),
                _safe_text(sh.get("shareholder_name")),
                kind_label,
                _fmt_thousand(int(sh.get("shares_start") or 0)),
                _fmt_thousand(int(sh.get("shares_end") or 0)),
                _fmt_pct(sh.get("ownership_pct_start") or 0.0),
                _fmt_pct(sh.get("ownership_pct_end") or 0.0),
                int(sh.get("page_number") or 0) or "",
            ))

        tree.bind("<<TreeviewSelect>>", self._on_sh_select)

    def _build_transactions(self) -> None:
        frame = ttk.LabelFrame(self, text="Transaksjoner", padding=4)
        frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self._tx_header = ttk.Label(frame, text="Velg en aksjonær for å se transaksjoner.", foreground="#667085")
        self._tx_header.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cols = ("retning", "type", "aksjer", "dato", "beloep")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="none", height=6)
        for cid, text, width, anchor in [
            ("retning", "Retning", 80, "w"),
            ("type", "Type", 110, "w"),
            ("aksjer", "Aksjer", 80, "e"),
            ("dato", "Dato", 100, "w"),
            ("beloep", "Beløp", 120, "e"),
        ]:
            tree.heading(cid, text=text)
            tree.column(cid, width=width, anchor=anchor)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")

        self._tree_tx = tree

    def _build_buttons(self, header: dict) -> None:
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, sticky="ew", padx=6, pady=8)
        btn_frame.columnconfigure(0, weight=1)

        stored = _safe_text(header.get("stored_file_path"))
        self._stored_path = stored
        state = "normal" if stored and Path(stored).exists() else "disabled"
        ttk.Button(
            btn_frame, text="Åpne kilde-PDF", command=self._open_source,
            state=state,
        ).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(btn_frame, text="Lukk", command=self.destroy).grid(row=0, column=2)

    def _on_sh_select(self, _event=None) -> None:
        sel = self._tree_sh.selection()
        self._tree_tx.delete(*self._tree_tx.get_children())
        if not sel:
            self._tx_header.config(text="Velg en aksjonær for å se transaksjoner.")
            return
        sh = self._sh_by_iid.get(sel[0]) or {}
        name = _safe_text(sh.get("shareholder_name"))
        sh_id = _safe_text(sh.get("shareholder_id"))
        self._tx_header.config(text=f"{name}  ({sh_id})" if sh_id else name)

        by_ref = self._detail.get("by_ref") or {}
        ref = ""
        if sh_id:
            ref = f"id:{sh_id}"
        elif name:
            ref = f"name:{name.casefold()}"
        entry = by_ref.get(ref) or {}
        for tx in entry.get("transactions") or []:
            direction = _safe_text(tx.get("direction"))
            retning = "Tilgang" if direction == "tilgang" else ("Avgang" if direction == "avgang" else direction)
            self._tree_tx.insert("", "end", values=(
                retning,
                _safe_text(tx.get("trans_type")),
                _fmt_thousand(int(tx.get("shares") or 0)),
                _safe_text(tx.get("date")),
                _fmt_currency(float(tx.get("amount") or 0.0)),
            ))

    def _open_source(self) -> None:
        path = self._stored_path
        if not path:
            return
        try:
            import os
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("AR", f"Kunne ikke åpne PDF:\n{exc}")

    def show(self) -> None:
        self.wait_window(self)
