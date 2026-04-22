"""regnskap_export.py -- Eksport av arsregnskap (Excel, HTML, PDF).

Ekstrahert fra page_regnskap.py.  Hver funksjon tar ``page`` (RegnskapPage-instans)
som forste argument.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

try:
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore


def get_export_rl_df(page: Any) -> pd.DataFrame | None:
    """Hent regnskapslinje-DataFrame klar for eksport."""
    rl_df, _, _ = page._fetch_rl_df()
    if rl_df is None or rl_df.empty:
        return None
    # Merge UB_fjor — bruk _pivot_df_rl (RL-spesifikk), ikke _pivot_df_last
    # som kan være konto-pivot uten regnr.
    pivot_df = getattr(page._analyse_page, "_pivot_df_rl", None)
    if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
        rl_df = rl_df.copy()
        if "UB_fjor" not in rl_df.columns:
            m = pivot_df[["regnr", "UB_fjor"]].drop_duplicates(subset=["regnr"])
            rl_df = rl_df.merge(m, on="regnr", how="left")
    return rl_df


def on_export_excel(page: Any) -> None:
    if filedialog is None:
        return
    rl_df = get_export_rl_df(page)
    if rl_df is None:
        page._msg_no_data()
        return

    base = f"\u00c5rsregnskap {page._client} {page._year}".strip()
    safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
    path = filedialog.asksaveasfilename(
        parent=page,
        title="Lagre Excel-\u00e5rsregnskap",
        defaultextension=".xlsx",
        filetypes=[("Excel workbook", "*.xlsx"), ("Alle filer", "*.*")],
        initialfile=safe_base + ".xlsx",
    )
    if not path:
        return

    try:
        import regnskap_report
        sigs = page._get_signatories() if page._inkl_signatur_var.get() else None
        regnskap_report.save_report_excel(
            path, rl_df,
            notes_data=page._collect_notes_data(),
            client=page._client,
            year=page._year,
            framework=page._framework,
            custom_notes=page._custom_notes,
            include_cf=page._inkl_cf_var.get(),
            signatories=sigs,
        )
    except Exception as exc:
        if messagebox:
            messagebox.showerror("Eksport", f"Kunne ikke lage Excel-rapport:\n{exc}")
        log.exception("Excel export failed")
        return

    page._set_status(f"Excel lagret: {path}")
    try:
        import os
        os.startfile(path)
    except Exception:
        pass


def on_export_html(page: Any) -> None:
    if filedialog is None:
        return
    rl_df = get_export_rl_df(page)
    if rl_df is None:
        page._msg_no_data()
        return

    base = f"\u00c5rsregnskap {page._client} {page._year}".strip()
    safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
    path = filedialog.asksaveasfilename(
        parent=page,
        title="Lagre HTML-\u00e5rsregnskap",
        defaultextension=".html",
        filetypes=[("HTML-rapport", "*.html"), ("Alle filer", "*.*")],
        initialfile=safe_base + ".html",
    )
    if not path:
        return

    try:
        import regnskap_report
        sigs = page._get_signatories() if page._inkl_signatur_var.get() else None
        regnskap_report.save_report_html(
            path, rl_df,
            notes_data=page._collect_notes_data(),
            client=page._client,
            year=page._year,
            framework=page._framework,
            custom_notes=page._custom_notes,
            include_cf=page._inkl_cf_var.get(),
            signatories=sigs,
        )
    except Exception as exc:
        if messagebox:
            messagebox.showerror("Eksport", f"Kunne ikke lage HTML-rapport:\n{exc}")
        log.exception("HTML export failed")
        return

    page._set_status(f"HTML lagret: {path}")
    try:
        import webbrowser
        from pathlib import Path
        webbrowser.open(Path(path).as_uri())
    except Exception:
        pass


def on_export_pdf(page: Any) -> None:
    if filedialog is None:
        return
    rl_df = get_export_rl_df(page)
    if rl_df is None:
        page._msg_no_data()
        return

    base = f"\u00c5rsregnskap {page._client} {page._year}".strip()
    safe_base = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
    path = filedialog.asksaveasfilename(
        parent=page,
        title="Lagre PDF-\u00e5rsregnskap",
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf"), ("Alle filer", "*.*")],
        initialfile=safe_base + ".pdf",
    )
    if not path:
        return

    page._set_status("Genererer PDF\u2026")
    try:
        page.update_idletasks()
    except Exception:
        pass

    try:
        import regnskap_report
        sigs = page._get_signatories() if page._inkl_signatur_var.get() else None
        regnskap_report.save_report_pdf(
            path, rl_df,
            notes_data=page._collect_notes_data(),
            client=page._client,
            year=page._year,
            framework=page._framework,
            custom_notes=page._custom_notes,
            include_cf=page._inkl_cf_var.get(),
            signatories=sigs,
        )
    except Exception as exc:
        if messagebox:
            messagebox.showerror("Eksport", f"Kunne ikke lage PDF:\n{exc}")
        log.exception("PDF export failed")
        page._set_status("PDF-eksport feilet")
        return

    page._set_status(f"PDF lagret: {path}")
    try:
        import os
        os.startfile(path)
    except Exception:
        pass
