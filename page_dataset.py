"""page_dataset.py

Dataset-fanen: innlesing og bygging av hovedbokdatasett.

Denne siden wrap'er DatasetPane, og legger på en enkel eksport-knapp som lar
bruker eksportere hele innlastede hovedbok (session.dataset) til Excel.

Mål:
- Knapp i GUI (Dataset-fanen) for 'Eksporter hovedbok til Excel'
- Alltid best-effort: hvis datasett mangler -> gi forståelig melding, ikke crash
- Tung eksport kjøres i bakgrunnstråd via LoadingOverlay (DatasetPane.loading)
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

import session
from dataset_export import export_hovedbok_to_excel
from dataset_pane import DatasetPane

logger = logging.getLogger(__name__)


class DatasetPage(ttk.Frame):
    """
    Dataset-fane som embedder DatasetPane i notebooken.

    Bruk:
        page = DatasetPage(notebook)
        notebook.add(page, text="Dataset")
    """

    def __init__(self, parent: tk.Misc, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        self._last_df: pd.DataFrame | None = None

        # DatasetPane forventer kun parent som argument.
        # Den tidligere koden brukte DatasetPane(self, "Dataset"),
        # men __init__ tar bare (self, parent), så vi fjerner tittelen her.
        self.dp = DatasetPane(self, on_dataset_ready=self._on_dataset_ready)
        self.dp.pack(fill="both", expand=True)

        # Eksport-linje nederst
        row = ttk.Frame(self)
        row.pack(fill="x", padx=8, pady=(0, 8))

        self.btn_export = ttk.Button(
            row,
            text="Eksporter hovedbok til Excel",
            command=self._export_hovedbok_clicked,
            state="disabled",
        )
        self.btn_export.pack(side="left")

        # Hvis bruker velger ny fil / endrer path, disable eksport igjen (best effort).
        self._install_path_watch()

    def _install_path_watch(self) -> None:
        try:
            # Tk 8.5+
            self.dp.path_var.trace_add("write", lambda *_a: self._set_export_enabled(False))
        except Exception:
            try:
                # Eldre API
                self.dp.path_var.trace("w", lambda *_a: self._set_export_enabled(False))  # type: ignore[attr-defined]
            except Exception:
                return

    def _set_export_enabled(self, enabled: bool) -> None:
        try:
            self.btn_export.configure(state=("normal" if enabled else "disabled"))
        except Exception:
            pass

    def _on_dataset_ready(self, df: pd.DataFrame) -> None:
        self._last_df = df
        self._set_export_enabled(True)

    def _export_hovedbok_clicked(self) -> None:
        df = self._last_df
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            df = getattr(session, "dataset", None)

        if not isinstance(df, pd.DataFrame) or df.empty:
            messagebox.showinfo(
                "Eksport",
                "Ingen datasett er lastet inn ennå. Klikk 'Bygg datasett' først.",
            )
            return

        # Foreslå filnavn basert på kildefil (om tilgjengelig) + timestamp
        src = ""
        try:
            src = (self.dp.path_var.get() or "").strip()
        except Exception:
            src = ""

        stem = ""
        if src:
            try:
                stem = Path(src).stem
            except Exception:
                stem = ""

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") if stem else ""
        if safe_stem:
            safe_stem = safe_stem[:40]
            initialfile = f"hovedbok_{safe_stem}_{stamp}.xlsx"
        else:
            initialfile = f"hovedbok_{stamp}.xlsx"

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Eksporter hovedbok til Excel",
            defaultextension=".xlsx",
            initialfile=initialfile,
            filetypes=[("Excel", "*.xlsx")],
        )
        if not out_path:
            return

        def _work() -> str:
            return export_hovedbok_to_excel(out_path, df, sheet_name="Hovedbok")

        def _done(saved_path: str) -> None:
            messagebox.showinfo("Eksport", f"Eksportert til Excel:\n{saved_path}")
            _open_file_best_effort(saved_path)

        def _err(exc: BaseException, tb: str) -> None:
            logger.exception("Feil ved eksport av hovedbok til Excel: %s", exc)
            try:
                print(tb)
            except Exception:
                pass
            messagebox.showerror("Eksport", f"Kunne ikke eksportere til Excel:\n{exc}")

        # Bruk LoadingOverlay fra DatasetPane for å unngå at GUI fryser på store filer
        try:
            self.dp.loading.run_async(
                "Eksporterer hovedbok til Excel…\nDette kan ta litt tid på store filer.",
                work=_work,
                on_done=_done,
                on_error=_err,
            )
        except Exception:
            # Fallback (best effort): kjør synkront
            try:
                saved = _work()
                _done(saved)
            except Exception as e:
                _err(e, "")


def _open_file_best_effort(path: str) -> None:
    """Best effort: åpne filen etter eksport (ikke kritisk om dette feiler)."""
    # Under pytest skal vi aldri forsøke å åpne eksterne programmer
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        logger.exception("Kunne ikke åpne eksportert Excel-fil")
