"""reskontro_export.py — Excel- og PDF-eksport for reskontro.

Modulfunksjoner som tar `page` (ReskontroPage) som første argument.
"""

from __future__ import annotations

import logging

from .tree_helpers import (
    _TAG_BRREG_WARN,
    _TAG_HEADER,
    _TAG_MVA_WARN,
    _TAG_NEG,
    _UPPER_VIEW_ALLE,
    _UPPER_VIEW_APNE,
    _has_reskontro_data,
)

log = logging.getLogger(__name__)


def export_excel(page) -> None:
    try:
        import session as _session
        import analyse_export_excel as _xls
        client     = getattr(_session, "client", None) or ""
        year       = str(getattr(_session, "year", "") or "")
        mode_label = "kunder" if page._mode == "kunder" else "leverandorer"
        path = _xls.open_save_dialog(
            title="Eksporter Reskontro",
            default_filename=(
                f"reskontro_{mode_label}_{client}_{year}.xlsx"
            ).strip("_"),
            master=page,
        )
        if not path:
            return
        master_sheet = _xls.treeview_to_sheet(
            page._master_tree,
            title="Oversikt",
            heading=(
                f"Reskontro \u2014 "
                f"{'Kunder' if page._mode == 'kunder' else 'Leverand\u00f8rer'}"
            ),
            bold_tags=(_TAG_HEADER,),
            bg_tags={
                _TAG_NEG:        "FFEBEE",
                _TAG_BRREG_WARN: "FFF3CD",
                _TAG_MVA_WARN:   "FFF8E1",
            },
        )
        # Eksporter treet som faktisk er synlig i øvre høyrepanel —
        # brukeren forventer at det de ser er det de får.
        upper_view = ""
        try:
            upper_view = page._upper_view_var.get()
        except Exception:
            upper_view = _UPPER_VIEW_ALLE
        if upper_view == _UPPER_VIEW_APNE:
            upper_tree  = page._open_items_tree
            upper_title = "Åpne poster"
            upper_head  = f"Åpne poster: {page._selected_nr}"
        else:
            upper_tree  = page._detail_tree
            upper_title = "Transaksjoner"
            upper_head  = f"Transaksjoner: {page._selected_nr}"
        detail_sheet = _xls.treeview_to_sheet(
            upper_tree,
            title=upper_title,
            heading=upper_head,
            bold_tags=(_TAG_HEADER,),
            bg_tags={_TAG_NEG: "FFEBEE"},
        )
        _xls.export_and_open(
            path, [master_sheet, detail_sheet],
            title="Reskontro", client=client, year=year)
    except Exception as exc:
        log.exception("Reskontro Excel-eksport feilet: %s", exc)


def export_pdf_report(page) -> None:
    from tkinter import filedialog, messagebox
    if not _has_reskontro_data(page._df):
        messagebox.showinfo(
            "Reskontrorapport",
            "Ingen reskontrodata er lastet. Last inn en SAF-T-fil først.",
            parent=page,
        )
        return
    try:
        import session as _session
        from ..backend.report_engine import compute_reskontro_report
        from ..backend.report_html import save_report_pdf

        client = getattr(_session, "client", None) or ""
        year = str(getattr(_session, "year", "") or "")

        sb_df = None
        try:
            from page_analyse_rl import load_sb_for_session
            sb_df = load_sb_for_session()
        except Exception:
            sb_df = None

        reference_date = ""
        if year:
            reference_date = f"{year}-12-31"

        report = compute_reskontro_report(
            page._df,
            mode=page._mode,
            client=client,
            year=year,
            reference_date=reference_date,
            sb_df=sb_df,
            top_n=10,
        )

        mode_label = "kunder" if page._mode == "kunder" else "leverandorer"
        default_name = f"reskontrorapport_{mode_label}_{client}_{year}.pdf".strip("_")
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Lagre reskontrorapport som PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return

        saved = save_report_pdf(path, report, top_n=10)
        try:
            import os
            os.startfile(saved)
        except Exception:
            pass
    except ImportError as exc:
        messagebox.showerror(
            "Reskontrorapport",
            f"Playwright mangler: {exc}",
            parent=page,
        )
    except Exception as exc:
        log.exception("Reskontrorapport PDF-eksport feilet: %s", exc)
        messagebox.showerror(
            "Reskontrorapport",
            f"Kunne ikke generere PDF:\n{exc}",
            parent=page,
        )
