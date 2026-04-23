"""page_documents.py — Dokumenter-fane for Utvalg.

Viser eksporterte dokumenter fra klientens exports/-mappe
(…/clients/<klient>/years/<år>/exports/).

Oppdateres automatisk når klient/år endres via refresh_from_session().
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional
import tkinter as tk

# Filtyper med ikon-tekst og lesbart navn
_FILETYPES: list[tuple[tuple[str, ...], str]] = [
    ((".pdf",),           "PDF"),
    ((".xlsx", ".xls"),   "Excel"),
    ((".html", ".htm"),   "HTML"),
    ((".json",),          "JSON"),
    ((".csv",),           "CSV"),
    ((".docx", ".doc"),   "Word"),
    ((".txt",),           "Tekst"),
]

_COLUMNS = (
    ("Navn",      350, "w"),
    ("Type",       70, "w"),
    ("Dato",      130, "w"),
    ("Størrelse",  80, "e"),
)


def _file_type_label(path: Path) -> str:
    ext = path.suffix.lower()
    for exts, label in _FILETYPES:
        if ext in exts:
            return label
    return ext.lstrip(".").upper() or "Fil"


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _format_mtime(mtime: float) -> str:
    try:
        return datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


class DocumentsPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._exports_path: Optional[Path] = None
        self._client: str = ""
        self._year: str = ""
        self._build_ui()

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- Topplinje ---
        top = ttk.Frame(self, padding=(8, 6, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Eksporterte dokumenter", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self._path_var = tk.StringVar(value="Ingen klient lastet")
        ttk.Label(top, textvariable=self._path_var, foreground="#555").grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(top, text="Åpne mappe", command=self._open_folder).grid(
            row=0, column=3, padx=(4, 0)
        )

        # --- Treeview ---
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = tuple(c[0] for c in _COLUMNS)
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  selectmode="browse")
        for name, width, anchor in _COLUMNS:
            self._tree.heading(name, text=name,
                               command=lambda c=name: self._sort_by(c))
            self._tree.column(name, width=width, anchor=anchor, stretch=(name == "Navn"))

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<Double-1>", lambda _e: self._open_selected())
        self._tree.bind("<Return>", lambda _e: self._open_selected())

        # --- Bunnlinje ---
        bot = ttk.Frame(self, padding=(8, 2, 8, 6))
        bot.grid(row=2, column=0, sticky="ew")
        self._status_var = tk.StringVar(value="")
        ttk.Label(bot, textvariable=self._status_var, foreground="#555").pack(side=tk.LEFT)
        ttk.Button(bot, text="Åpne valgt", command=self._open_selected).pack(side=tk.RIGHT)

        self._sort_col: str = "Dato"
        self._sort_rev: bool = True

    # ------------------------------------------------------------------
    # Session

    def refresh_from_session(self, session: object, **_kw: object) -> None:
        client = str(getattr(session, "client", "") or "").strip()
        year   = str(getattr(session, "year",   "") or "").strip()
        if client == self._client and year == self._year:
            return
        self._client = client
        self._year   = year
        self._update_path()
        self._refresh()

    def _update_path(self) -> None:
        if self._client and self._year:
            try:
                import client_store
                self._exports_path = client_store.exports_dir(self._client, year=self._year)
                self._path_var.set(str(self._exports_path))
            except Exception as exc:
                self._exports_path = None
                self._path_var.set(f"Feil: {exc}")
        else:
            self._exports_path = None
            self._path_var.set("Ingen klient lastet")

    # ------------------------------------------------------------------
    # Vis filer

    def _refresh(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

        if self._exports_path is None:
            self._status_var.set("Ingen mappe valgt")
            return

        if not self._exports_path.exists():
            self._status_var.set("Mappen er tom (ingen eksporter ennå)")
            return

        files = [
            f for f in sorted(self._exports_path.iterdir())
            if f.is_file() and not f.name.startswith(".")
        ]

        if not files:
            self._status_var.set("Ingen filer i mappen ennå")
            return

        for f in files:
            try:
                stat = f.stat()
            except Exception:
                continue
            self._tree.insert(
                "", tk.END,
                values=(
                    f.name,
                    _file_type_label(f),
                    _format_mtime(stat.st_mtime),
                    _format_size(stat.st_size),
                ),
                tags=(str(f),),
            )

        self._do_sort(self._sort_col, self._sort_rev)
        self._status_var.set(f"{len(files)} fil{'er' if len(files) != 1 else ''}")

    def _sort_by(self, col: str) -> None:
        rev = not self._sort_rev if col == self._sort_col else False
        self._sort_col = col
        self._sort_rev = rev
        self._do_sort(col, rev)

    def _do_sort(self, col: str, reverse: bool) -> None:
        col_idx = {c[0]: i for i, c in enumerate(_COLUMNS)}
        idx = col_idx.get(col, 0)
        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        items.sort(reverse=reverse)
        for rank, (_, k) in enumerate(items):
            self._tree.move(k, "", rank)

    # ------------------------------------------------------------------
    # Handlinger

    def _selected_path(self) -> Optional[Path]:
        sel = self._tree.selection()
        if not sel:
            return None
        tags = self._tree.item(sel[0], "tags")
        if not tags:
            return None
        return Path(tags[0])

    def _open_selected(self) -> None:
        p = self._selected_path()
        if p is None:
            return
        if not p.exists():
            messagebox.showwarning("Fil ikke funnet",
                                   f"Filen finnes ikke lenger:\n{p}", parent=self)
            self._refresh()
            return
        _open_file(str(p))

    def _open_folder(self) -> None:
        if self._exports_path is None:
            return
        self._exports_path.mkdir(parents=True, exist_ok=True)
        _open_file(str(self._exports_path))


def _open_file(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass
