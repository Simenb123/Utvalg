"""Bilag split-view: bilag-rader til venstre, PDF-preview til høyre.

Gjenbruker:
- ``selection_studio.drill`` for bilag-rad-bygging (utvalg-flagging,
  motpart-utleding, sortering)
- ``document_control_voucher_index.find_and_extract_bilag`` for å hente
  PDF-stien fra voucher-indeksen (PowerOffice-ZIP eller Tripletex-PDF)
- ``document_control_viewer.DocumentPreviewFrame`` for selve PDF-
  rendringen (page-nav, zoom, fit-to-width — basert på pymupdf)

Åpnes som alternativ til ``open_bilag_drill_dialog`` når brukeren vil
se bilag-føringen og selve bilag-PDF-en side-ved-side. Hvis ingen PDF
finnes for bilaget, vises bare en informativ melding på høyre side
(brukeren får fortsatt full nytte av venstre rute).
"""
from __future__ import annotations

import os
import sys
import subprocess
from typing import Any, Optional

import pandas as pd

import formatting

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

from selection_studio.drill import (
    _resolve_drilldown_inputs,
    annotate_scope,
    extract_bilag_rows,
    konto_set_from_df,
    normalize_bilag_value,
    _first_existing_column,
)


def open_bilag_split_view(
    master: Any,
    df_base: Optional[pd.DataFrame] = None,
    df_all: Optional[pd.DataFrame] = None,
    bilag_value: Any = None,
    # Backwards-compatible aliases (samme mønster som open_bilag_drill_dialog)
    preset_bilag: Any = None,
    bilag: Any = None,
    bilag_id: Any = None,
    selected_bilag: Any = None,
    bilag_col: str = "Bilag",
    **_ignored_kwargs: Any,
) -> None:
    """Åpne split-view popup med bilag-rader + PDF side-ved-side."""
    df_base_res, df_all_res, bilag_res, bilag_col_res = _resolve_drilldown_inputs(
        master,
        df_base,
        df_all,
        bilag_value,
        preset_bilag=preset_bilag,
        bilag=bilag,
        bilag_id=bilag_id,
        selected_bilag=selected_bilag,
        bilag_col=bilag_col,
    )

    if tk is None or ttk is None:
        raise RuntimeError("Tkinter er ikke tilgjengelig i dette miljøet.")

    source_df = df_all_res if isinstance(df_all_res, pd.DataFrame) and not df_all_res.empty else df_base_res
    bilag_norm = normalize_bilag_value(bilag_res)

    rows = extract_bilag_rows(source_df, bilag_norm, bilag_col=bilag_col_res)
    if rows.empty:
        messagebox.showinfo("Bilag", f"Fant ingen rader for bilag: {bilag_norm}")
        return

    konto_set = konto_set_from_df(df_base_res, konto_col="Konto")
    rows = annotate_scope(rows, konto_set, konto_col="Konto")

    motpart_col = _first_existing_column(
        rows,
        ["Kunder", "Kunde", "Kundenavn", "Leverandør", "Leverandørnavn", "Motpart", "Navn"],
    )
    rows["Motpart"] = rows[motpart_col] if motpart_col else ""

    if "Dato" in rows.columns:
        try:
            _d = pd.to_datetime(rows["Dato"], errors="coerce", dayfirst=True)
            rows = (
                rows.assign(_sort_dato=_d)
                .sort_values(by=["_sort_dato"], kind="mergesort")
                .drop(columns=["_sort_dato"])
            )
        except Exception:
            pass

    bel = pd.to_numeric(rows.get("Beløp", 0), errors="coerce").fillna(0.0)
    sum_all = float(bel.sum())
    sum_sel = float(bel[rows["I kontoutvalg"]].sum()) if "I kontoutvalg" in rows.columns else 0.0
    sum_mot = float(bel[~rows["I kontoutvalg"]].sum()) if "I kontoutvalg" in rows.columns else 0.0

    # Bygg dialog
    top = tk.Toplevel(master)
    top.title(f"Bilag {bilag_norm}")
    try:
        top.geometry("1500x700")
    except Exception:
        pass

    # Header
    hdr = ttk.Frame(top, padding=(10, 8, 10, 4))
    hdr.pack(fill="x")
    ttk.Label(
        hdr,
        text=(
            f"Bilag: {bilag_norm}  |  Rader: {formatting.format_int_no(len(rows))}  |  "
            f"Sum: {formatting.fmt_amount(sum_all)}  |  "
            f"I kontoutvalg: {formatting.fmt_amount(sum_sel)}  |  "
            f"Motposter: {formatting.fmt_amount(sum_mot)}"
        ),
    ).pack(side="left", anchor="w")

    # Split-pane: venstre = bilag-rader, høyre = PDF-preview
    paned = ttk.PanedWindow(top, orient="horizontal")
    paned.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    # ── VENSTRE: bilag-føringen ──
    left = ttk.Frame(paned)
    try:
        paned.add(left, weight=2)
    except Exception:
        paned.add(left)

    desired_cols = ["I kontoutvalg", "Dato", "Konto", "Kontonavn", "Beløp", "Tekst", "Motpart"]
    cols = [c for c in desired_cols if c in rows.columns]

    tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
    vsb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="left", fill="y")

    def col_width(c: str) -> int:
        return {
            "I kontoutvalg": 100,
            "Dato": 90,
            "Konto": 70,
            "Kontonavn": 200,
            "Beløp": 100,
            "Tekst": 280,
            "Motpart": 180,
        }.get(c, 120)

    for c in cols:
        tree.heading(c, text=c)
        anchor = "e" if c == "Beløp" else "w"
        tree.column(c, width=col_width(c), anchor=anchor, stretch=False)

    try:
        tree.tag_configure("scope_no", foreground="#666666")
        tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    def fmt(c: str, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and pd.isna(v):
            return ""
        if isinstance(v, str) and v.lower() == "nan":
            return ""
        if c == "Beløp":
            return formatting.fmt_amount(v)
        if c == "Dato":
            try:
                return formatting.fmt_date(v)
            except Exception:
                return str(v)
        if c == "I kontoutvalg":
            return "Ja" if bool(v) else "Nei"
        return str(v)

    for _, row in rows.iterrows():
        tags = []
        if "I kontoutvalg" in cols and not bool(row.get("I kontoutvalg", False)):
            tags.append("scope_no")
        try:
            if float(row.get("Beløp", 0)) < 0:
                tags.append("neg")
        except Exception:
            pass
        tree.insert("", "end", values=[fmt(c, row.get(c)) for c in cols], tags=tuple(tags))

    # ── HØYRE: PDF-preview ──
    right = ttk.Frame(paned)
    try:
        paned.add(right, weight=3)
    except Exception:
        paned.add(right)

    # Toolbar med page-nav + zoom — settes ABOVE preview-frame
    pdf_toolbar = ttk.Frame(right)
    pdf_toolbar.pack(fill="x", pady=(0, 4))

    preview_frame = None
    try:
        from document_control_viewer import DocumentPreviewFrame
        preview_frame = DocumentPreviewFrame(right, show_toolbar=False)
        preview_frame.pack(fill="both", expand=True)
    except Exception as exc:
        ttk.Label(
            right,
            text=f"PDF-visning ikke tilgjengelig:\n{exc}",
            foreground="#999",
        ).pack(padx=20, pady=20)

    if preview_frame is not None:
        ttk.Button(pdf_toolbar, text="◄", command=preview_frame.show_previous_page, width=3).pack(side="left")
        ttk.Label(pdf_toolbar, textvariable=preview_frame.var_page, width=8, anchor="center").pack(side="left", padx=2)
        ttk.Button(pdf_toolbar, text="►", command=preview_frame.show_next_page, width=3).pack(side="left", padx=(0, 8))
        ttk.Button(pdf_toolbar, text="−", command=preview_frame.zoom_out, width=2).pack(side="left")
        ttk.Button(pdf_toolbar, text="+", command=preview_frame.zoom_in, width=2).pack(side="left")
        ttk.Button(pdf_toolbar, text="Tilpass", command=preview_frame.fit_to_width, width=8).pack(side="left", padx=(4, 0))

        # Last bilag-PDF i bakgrunnen — find_and_extract_bilag kan ta tid
        # første gang (utpakking fra ZIP). Bruk after_idle for å unngå
        # at popupen henger før den vises.
        def _load_pdf() -> None:
            try:
                import session as _session
                client = getattr(_session, "client", None)
                year = getattr(_session, "year", None)
            except Exception:
                client = None
                year = None
            try:
                from document_control_voucher_index import find_and_extract_bilag
                pdf_path = find_and_extract_bilag(
                    bilag_norm,
                    client=str(client) if client else None,
                    year=str(year) if year else None,
                )
            except Exception as exc:
                pdf_path = None
                preview_frame.var_status.set(f"Feil ved PDF-oppslag: {exc}")
                return
            if pdf_path is None:
                preview_frame.var_status.set(
                    f"Ingen PDF funnet for bilag {bilag_norm}. "
                    "Last inn voucher-arkiv via Dokumenter-fanen."
                )
                return
            preview_frame.load_file(str(pdf_path))

        try:
            top.after_idle(_load_pdf)
        except Exception:
            _load_pdf()

    # Bunn-knapper
    btn_row = ttk.Frame(top, padding=(10, 4, 10, 10))
    btn_row.pack(fill="x")

    def _open_external() -> None:
        """Åpne PDF i systemets standard viewer (samme som drill.py)."""
        try:
            import session as _session
            client = getattr(_session, "client", None)
            year = getattr(_session, "year", None)
        except Exception:
            client = None
            year = None
        try:
            from document_control_voucher_index import find_and_extract_bilag
            pdf_path = find_and_extract_bilag(
                bilag_norm,
                client=str(client) if client else None,
                year=str(year) if year else None,
            )
        except Exception as exc:
            messagebox.showerror("Se bilag", f"Feil:\n{exc}")
            return
        if pdf_path is None:
            messagebox.showinfo("Bilag ikke funnet", f"Ingen PDF for bilag {bilag_norm}.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(pdf_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(pdf_path)])
            else:
                subprocess.Popen(["xdg-open", str(pdf_path)])
        except Exception as exc:
            messagebox.showerror("Se bilag", f"Kunne ikke åpne PDF:\n{exc}")

    ttk.Button(btn_row, text="📂 Åpne i ekstern viewer", command=_open_external).pack(side="left")
    ttk.Button(btn_row, text="Lukk", command=top.destroy).pack(side="right")

    # Fokus på treet for tastatur-navigasjon
    try:
        children = tree.get_children()
        if children:
            tree.focus(children[0])
            tree.selection_set(children[0])
    except Exception:
        pass
