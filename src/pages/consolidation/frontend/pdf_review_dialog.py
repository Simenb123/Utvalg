"""Review-dialog for PDF-assisterte regnskapslinjeforslag."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd


def review_pdf_line_suggestions(parent, suggestions: pd.DataFrame) -> pd.DataFrame | None:
    """Vis forslag og returner eksplisitt godkjente rader."""
    if suggestions is None or suggestions.empty:
        return pd.DataFrame()

    dlg = _PdfLineReviewDialog(parent, suggestions)
    return dlg.show()


class _PdfLineReviewDialog(tk.Toplevel):
    def __init__(self, parent, suggestions: pd.DataFrame) -> None:
        super().__init__(parent)
        self.title("PDF-forslag til regnskapslinjer")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        self._suggestions = suggestions.reset_index(drop=True).copy()
        self._result: pd.DataFrame | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        info = ttk.Label(
            self,
            text="Velg radene som skal lagres som regnskapslinje-grunnlag.",
        )
        info.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("regnr", "regnskapslinje", "ub", "confidence", "source_page", "match_status", "source_text")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        headings = {
            "regnr": "Regnr",
            "regnskapslinje": "Regnskapslinje",
            "ub": "UB",
            "confidence": "Score",
            "source_page": "Side",
            "match_status": "Status",
            "source_text": "Kildetekst",
        }
        widths = {
            "regnr": 70,
            "regnskapslinje": 220,
            "ub": 110,
            "confidence": 70,
            "source_page": 60,
            "match_status": 110,
            "source_text": 380,
        }
        for col in cols:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w" if col in {"regnskapslinje", "source_text", "match_status"} else "e")
        tree.tag_configure("suggested", background="#E2F1EB")
        tree.tag_configure("low_confidence", background="#FFF4D6")
        tree.grid(row=0, column=0, sticky="nsew")
        self._tree = tree

        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)

        for idx, (_, row) in enumerate(self._suggestions.iterrows()):
            tag = str(row.get("match_status", "") or "") or ""
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    int(row.get("regnr", 0) or 0),
                    str(row.get("regnskapslinje", "") or ""),
                    float(row.get("ub", 0.0) or 0.0),
                    float(row.get("confidence", 0.0) or 0.0),
                    row.get("source_page", ""),
                    tag,
                    str(row.get("source_text", "") or ""),
                ),
                tags=(tag,) if tag else (),
            )
            if tag == "suggested":
                tree.selection_add(str(idx))

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        ttk.Button(btns, text="Velg alle forslag", command=self._select_recommended).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Avbryt", command=self._on_cancel).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Lagre markerte", command=self._on_confirm).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _select_recommended(self) -> None:
        self._tree.selection_remove(*self._tree.selection())
        for idx, (_, row) in enumerate(self._suggestions.iterrows()):
            if str(row.get("match_status", "") or "") == "suggested":
                self._tree.selection_add(str(idx))

    def _on_cancel(self) -> None:
        self._result = None
        self.grab_release()
        self.destroy()

    def _on_confirm(self) -> None:
        selected = [int(iid) for iid in self._tree.selection()]
        if not selected:
            self._result = pd.DataFrame(columns=self._suggestions.columns)
        else:
            result = self._suggestions.iloc[selected].copy()
            result["review_status"] = "approved"
            self._result = result.reset_index(drop=True)
        self.grab_release()
        self.destroy()

    def show(self) -> pd.DataFrame | None:
        self.wait_window()
        return self._result
