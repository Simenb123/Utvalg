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


def _open_kontroll_dialog(parent: Any, bilag_nr: str, rows: pd.DataFrame) -> None:
    """Modal dialog for å registrere haphazard-kontroll av et bilag.

    Brukeren velger konklusjon, kan legge til notat, og kan velge å
    arkivere PDF'en under ``documents/bilag/`` for senere referanse.
    """
    if tk is None or ttk is None:
        return
    from src.shared.ui.dialog import make_dialog
    from selection_studio.haphazard_store import save_haphazard_test  # noqa: F401 (also imported in _save)
    from document_control_voucher_index import find_and_extract_bilag

    # Sammendrag fra første rad i utvalget (sum/største linje)
    konto_str = ""
    kontonavn_str = ""
    beløp_sum = 0.0
    dato_str = ""
    if not rows.empty:
        try:
            sel = rows[rows.get("I kontoutvalg", False) == True] if "I kontoutvalg" in rows.columns else rows
            if sel.empty:
                sel = rows
            konto_str = str(sel.iloc[0].get("Konto", ""))
            kontonavn_str = str(sel.iloc[0].get("Kontonavn", ""))
            beløp_sum = float(pd.to_numeric(sel.get("Beløp", 0), errors="coerce").fillna(0.0).sum())
            dato_str = str(sel.iloc[0].get("Dato", ""))
        except Exception:
            pass

    # Hent klient/år fra session
    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
        year = getattr(_session, "year", None) or ""
    except Exception:
        client = ""
        year = ""

    # Hent brukerens initialer hvis mulig
    granskede_av = ""
    try:
        import team_config
        user = team_config.current_user()
        if user is not None:
            granskede_av = (user.visena_initials or user.windows_user or "").strip()
    except Exception:
        pass

    if not client or not year:
        messagebox.showwarning(
            "Kontroller bilag",
            "Klient/år er ikke satt — kan ikke lagre kontroll.",
        )
        return

    dlg = make_dialog(
        parent,
        title=f"Kontroller bilag {bilag_nr}",
        width=480,
        height=420,
        modal=True,
    )

    body = ttk.Frame(dlg, padding=14)
    body.pack(fill="both", expand=True)

    # Sammendrag
    info = ttk.LabelFrame(body, text="Bilag", padding=8)
    info.pack(fill="x", pady=(0, 10))
    ttk.Label(info, text=f"Klient: {client} ({year})").pack(anchor="w")
    ttk.Label(info, text=f"Bilag: {bilag_nr}").pack(anchor="w")
    if konto_str:
        ttk.Label(info, text=f"Konto: {konto_str} {kontonavn_str}").pack(anchor="w")
    if dato_str:
        ttk.Label(info, text=f"Dato: {dato_str}").pack(anchor="w")
    ttk.Label(info, text=f"Sum: {formatting.fmt_amount(beløp_sum)}").pack(anchor="w")

    # Konklusjon
    ttk.Label(body, text="Konklusjon:").pack(anchor="w", pady=(4, 2))
    var_konklusjon = tk.StringVar(value="ok")
    konklusjon_row = ttk.Frame(body)
    konklusjon_row.pack(fill="x")
    ttk.Radiobutton(konklusjon_row, text="OK", variable=var_konklusjon, value="ok").pack(side="left", padx=(0, 12))
    ttk.Radiobutton(konklusjon_row, text="Avvik", variable=var_konklusjon, value="avvik").pack(side="left", padx=(0, 12))
    ttk.Radiobutton(konklusjon_row, text="Ikke konkluderende", variable=var_konklusjon, value="ikke_konkluderende").pack(side="left")

    # Notat
    ttk.Label(body, text="Notat (valgfritt):").pack(anchor="w", pady=(10, 2))
    txt_notat = tk.Text(body, height=5, wrap="word")
    txt_notat.pack(fill="both", expand=True)

    # Lagre PDF i klientarkivet?
    var_save_pdf = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        body,
        text="Lagre PDF i klientarkivet (documents/bilag/)",
        variable=var_save_pdf,
    ).pack(anchor="w", pady=(8, 0))

    # Bunn-knapper
    btn_row = ttk.Frame(dlg, padding=(14, 0, 14, 14))
    btn_row.pack(fill="x")

    def _save() -> None:
        konklusjon = var_konklusjon.get()
        notat = txt_notat.get("1.0", "end").strip()
        save_pdf = bool(var_save_pdf.get())

        pdf_path = None
        if save_pdf:
            try:
                pdf_path = find_and_extract_bilag(
                    bilag_nr,
                    client=client,
                    year=year,
                )
            except Exception:
                pdf_path = None
            if pdf_path is None:
                # Spør om brukeren vil lagre uten PDF
                if not messagebox.askyesno(
                    "Mangler PDF",
                    "Fant ingen PDF for bilaget. Lagre kontroll uten PDF?",
                    parent=dlg,
                ):
                    return
                save_pdf = False

        try:
            from selection_studio.haphazard_store import save_haphazard_test
            test = save_haphazard_test(
                client=client,
                year=year,
                bilag_nr=bilag_nr,
                konto=konto_str,
                kontonavn=kontonavn_str,
                beløp=beløp_sum,
                dato=dato_str,
                konklusjon=konklusjon,
                notat=notat,
                granskede_av=granskede_av,
                pdf_source_path=pdf_path if save_pdf else None,
                save_pdf=save_pdf,
            )
        except Exception as exc:
            messagebox.showerror(
                "Kunne ikke lagre",
                f"Feil ved lagring:\n{exc}",
                parent=dlg,
            )
            return

        msg = f"Kontroll lagret som {test.test_id}."
        if test.pdf_attached:
            msg += "\nPDF arkivert i documents/bilag/."
        messagebox.showinfo("Lagret", msg, parent=dlg)
        dlg.destroy()

    ttk.Button(btn_row, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(btn_row, text="Lagre", command=_save).pack(side="right")


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
        top.geometry("1500x800")
    except Exception:
        pass

    # Én konsolidert header-rad — bilag-info venstre, PDF-toolbar +
    # action-knapper høyre. Layouten gir maksimal vertikal plass til
    # PDF-en (A4-bilag er høye).
    hdr = ttk.Frame(top, padding=(10, 6, 10, 4))
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
    paned.pack(fill="both", expand=True, padx=10, pady=(2, 8))

    # ── VENSTRE: bilag-føringen ──
    left = ttk.Frame(paned)
    try:
        paned.add(left, weight=2)
    except Exception:
        paned.add(left)

    # Migrert til ManagedTreeview (playbook-mønster). Brukerens valg av
    # synlige kolonner, rekkefølge og bredder huskes mellom økter
    # (view_id="bilag_split"). Samme kolonneutvalg som TX-treet pluss
    # "I kontoutvalg" som første pinned-kolonne.
    from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
    import analyse_treewidths

    # Kolonner: "I kontoutvalg" (split-view-spesifikk) + alle TX-kolonnene
    # (minus "Bilag" siden alle rader i denne popupen har samme bilag-nr).
    _SPLIT_TX_COLS = (
        "Konto",
        "Kontonavn",
        "Dato",
        "Tekst",
        "Beløp",
        "Kunder",
        "Leverandør",
        "MVA-kode",
        "MVA-beløp",
        "MVA-prosent",
        "Valuta",
        "Valutabeløp",
    )
    # Default visible: smal pakke som dekker 90 % av bruksbehovet.
    # Resten kan slås på via høyreklikk-velgeren.
    _SPLIT_DEFAULT_VISIBLE = {
        "I kontoutvalg", "Konto", "Kontonavn", "Dato", "Tekst", "Beløp",
        "Kunder", "Leverandør",
    }

    column_specs = [
        ColumnSpec(
            id="I kontoutvalg",
            heading="I utvalg",
            width=70,
            minwidth=50,
            anchor="center",
            visible_by_default=True,
            pinned=True,
        ),
    ]
    for col in _SPLIT_TX_COLS:
        column_specs.append(
            ColumnSpec(
                id=col,
                heading=col,
                width=analyse_treewidths.default_column_width(col),
                minwidth=analyse_treewidths.column_minwidth(col),
                anchor=analyse_treewidths.column_anchor(col),
                stretch=False,
                visible_by_default=col in _SPLIT_DEFAULT_VISIBLE,
                sortable=True,
            )
        )

    all_col_ids = [spec.id for spec in column_specs]

    tree_frame = ttk.Frame(left)
    tree_frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(tree_frame, columns=all_col_ids, show="headings", height=20, selectmode="browse")
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="left", fill="y")

    try:
        managed = ManagedTreeview(
            tree,
            view_id="bilag_split",
            pref_prefix="ui",
            column_specs=column_specs,
        )
    except Exception:
        managed = None  # fallback: tabell virker uten ManagedTreeview-features

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
        if c == "Beløp" or c == "MVA-beløp" or c == "Valutabeløp":
            try:
                return formatting.fmt_amount(v)
            except Exception:
                return str(v)
        if c == "MVA-prosent":
            try:
                num = float(v)
                # Normaliser 0.25 → 25, behold heltall som 25
                if 0 < num <= 1:
                    num *= 100
                return formatting.format_number_no(num, decimals=0 if abs(num - round(num)) < 1e-9 else 2)
            except Exception:
                return str(v)
        if c == "Dato":
            try:
                return formatting.fmt_date(v)
            except Exception:
                return str(v)
        if c == "I kontoutvalg":
            return "✓" if bool(v) else ""
        return str(v)

    for _, row in rows.iterrows():
        tags = []
        if not bool(row.get("I kontoutvalg", False)):
            tags.append("scope_no")
        try:
            if float(row.get("Beløp", 0)) < 0:
                tags.append("neg")
        except Exception:
            pass
        # Insert posisjonelt mot tree["columns"] (= all_col_ids), ikke
        # bare displaycolumns — playbook-regelen for ManagedTreeview.
        tree.insert(
            "", "end",
            values=[fmt(c, row.get(c)) for c in all_col_ids],
            tags=tuple(tags),
        )

    # ── Leverandør-info-panel under bilag-tabellen ──
    # Henter Leverandørorgnr fra rader (SAF-T-import legger den på som
    # egen kolonne via saft_reader.look.supplier_orgnr). Slår opp BRREG
    # i bakgrunnstråd og viser MVA-registrert + bransje + warning hvis
    # MVA-fradrag (konto 27xx) er tatt på ikke-MVA-registrert leverandør.
    supplier_panel = ttk.LabelFrame(left, text="Leverandør / BRREG", padding=8)
    supplier_panel.pack(fill="x", pady=(8, 0))

    supplier_text = tk.Text(
        supplier_panel,
        height=6,
        wrap="word",
        relief="flat",
        borderwidth=0,
        font=("TkDefaultFont", 9),
        cursor="arrow",
        state="disabled",
    )
    supplier_text.pack(fill="x")
    supplier_text.tag_configure("key",  foreground="#555555")
    supplier_text.tag_configure("val",  foreground="#111111")
    supplier_text.tag_configure("ok",   foreground="#1a7a2a")
    supplier_text.tag_configure("bad",  foreground="#C75000")
    supplier_text.tag_configure("warn", foreground="#C75000", font=("TkDefaultFont", 9, "bold"))
    supplier_text.tag_configure("dim",  foreground="#888888")

    def _supplier_write(*parts: tuple[str, str]) -> None:
        try:
            supplier_text.configure(state="normal")
            for text, tag in parts:
                supplier_text.insert("end", text, (tag,))
            supplier_text.configure(state="disabled")
        except Exception:
            pass

    def _supplier_clear() -> None:
        try:
            supplier_text.configure(state="normal")
            supplier_text.delete("1.0", "end")
            supplier_text.configure(state="disabled")
        except Exception:
            pass

    # Hent leverandør-info fra første rad med Leverandør-data
    leverandør_navn = ""
    leverandør_orgnr = ""
    if "Leverandørnavn" in rows.columns:
        for v in rows["Leverandørnavn"]:
            if v and not pd.isna(v):
                leverandør_navn = str(v).strip()
                break
    if "Leverandørorgnr" in rows.columns:
        for v in rows["Leverandørorgnr"]:
            if v and not pd.isna(v):
                leverandør_orgnr = str(v).strip()
                break

    # MVA-fradrag-sjekk: ble fradrag tatt i dette bilaget?
    # To uavhengige signaler — begge gir True:
    #   1. MVA-kode er en eksplisitt fradrags-kode (1, 11, 13, 14, 15,
    #      81, 83, 86, 88, 91 — alle som starter med "Fradrag inngående"
    #      i SAF-T standardlisten). Den mest pålitelige indikatoren.
    #   2. Konto 271x/272x/273x (inngående MVA) er brukt — backup hvis
    #      MVA-kode ikke er på linjen.
    has_mva_fradrag = False
    fradrag_codes_used: list[str] = []
    if "MVA-kode" in rows.columns:
        try:
            from src.pages.mva.backend.codes import is_deduction_code
            for code in rows["MVA-kode"]:
                code_s = str(code or "").strip()
                if code_s and is_deduction_code(code_s):
                    has_mva_fradrag = True
                    if code_s not in fradrag_codes_used:
                        fradrag_codes_used.append(code_s)
        except Exception:
            pass
    if not has_mva_fradrag and "Konto" in rows.columns:
        for k in rows["Konto"]:
            ks = str(k or "")
            if ks.startswith("271") or ks.startswith("272") or ks.startswith("273"):
                has_mva_fradrag = True
                break

    if not leverandør_navn and not leverandør_orgnr:
        _supplier_write(("Ingen leverandør-info funnet på dette bilaget.", "dim"))
    else:
        # Vis det vi har umiddelbart
        if leverandør_navn:
            _supplier_write(("Leverandør: ", "key"), (leverandør_navn, "val"))
        if leverandør_orgnr:
            sep = "  |  " if leverandør_navn else ""
            _supplier_write((sep + "Orgnr: ", "key"), (leverandør_orgnr, "val"))
        _supplier_write(("\n", "val"))
        _supplier_write(("Henter BRREG-info...", "dim"))

        # Hent BRREG i bakgrunnstråd for å unngå at popup fryser
        def _fetch_brreg() -> None:
            enhet = None
            try:
                from src.shared.brreg.client import fetch_enhet, is_likely_exempt
                enhet = fetch_enhet(leverandør_orgnr) if leverandør_orgnr else None
            except Exception:
                enhet = None

            def _render() -> None:
                _supplier_clear()
                if not leverandør_orgnr:
                    _supplier_write(("Leverandør: ", "key"), (leverandør_navn, "val"), ("\n", "val"))
                    _supplier_write(("(Ingen orgnr på bilag — kan ikke slå opp BRREG)", "dim"))
                    return
                if enhet is None:
                    _supplier_write(("Leverandør: ", "key"), (leverandør_navn or "—", "val"))
                    _supplier_write(("  |  Orgnr: ", "key"), (leverandør_orgnr, "val"), ("\n", "val"))
                    _supplier_write(("Ikke funnet i Enhetsregisteret.", "bad"))
                    return

                navn = enhet.get("navn") or leverandør_navn or "—"
                _supplier_write(("Leverandør: ", "key"), (navn, "val"))
                _supplier_write(("  |  Orgnr: ", "key"), (leverandør_orgnr, "val"), ("\n", "val"))

                mva_reg = bool(enhet.get("registrertIMvaregisteret"))
                mva_txt = "✓ Ja" if mva_reg else "✗ Nei"
                _supplier_write(("MVA-registrert: ", "key"), (mva_txt, "ok" if mva_reg else "bad"))

                bransje_kode = enhet.get("naeringskode", "") or ""
                bransje_navn = enhet.get("naeringsnavn", "") or ""
                bransje = f"{bransje_kode} {bransje_navn}".strip() or "—"
                _supplier_write(("  |  Bransje: ", "key"), (bransje, "val"), ("\n", "val"))

                addr = enhet.get("forretningsadresse", "") or "—"
                _supplier_write(("Adresse: ", "key"), (addr, "val"), ("\n", "val"))

                # Status-flagg
                if enhet.get("konkurs"):
                    _supplier_write(("⚠ Konkurs", "bad"), ("\n", "val"))
                elif enhet.get("underAvvikling") or enhet.get("underTvangsavvikling"):
                    _supplier_write(("⚠ Under avvikling", "bad"), ("\n", "val"))

                # Bransje typisk unntatt MVA?
                exempt = False
                try:
                    exempt = is_likely_exempt(bransje_kode)
                except Exception:
                    pass
                if exempt:
                    _supplier_write(("⚠ Bransjen er typisk unntatt MVA", "warn"), ("\n", "val"))

                # KRITISK: MVA-fradrag på ikke-MVA-registrert leverandør
                if has_mva_fradrag and not mva_reg:
                    if fradrag_codes_used:
                        koder = ", ".join(fradrag_codes_used)
                        msg = (
                            f"⚠ MVA-fradrag-kode brukt ({koder}) på leverandør som "
                            "IKKE er MVA-registrert. Sjekk grundig."
                        )
                    else:
                        msg = (
                            "⚠ MVA-fradrag tatt (konto 27xx) på leverandør som "
                            "IKKE er MVA-registrert. Sjekk grundig."
                        )
                    _supplier_write((msg, "warn"))

            try:
                top.after(0, _render)
            except Exception:
                _render()

        try:
            import threading
            threading.Thread(target=_fetch_brreg, daemon=True).start()
        except Exception:
            _fetch_brreg()

    # ── HØYRE: PDF-preview (full høyde, ingen egen toolbar her) ──
    right = ttk.Frame(paned)
    try:
        paned.add(right, weight=3)
    except Exception:
        paned.add(right)

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

    # ── PDF-toolbar + action-knapper i SAMME header-rad ──
    # Pack-rekkefølgen er reversert siden side="right" stabler fra høyre.
    # Ønsket synlig rekkefølge (venstre→høyre):
    #   info ... ◄ [1/1] ► − + Tilpass | 📂 Åpne PDF  ✓ Kontroller bilag…
    # Action-knappene plasseres FØRST i pack-rekkefølge for å havne lengst
    # til høyre. PDF-toolbar pakkes etterpå og havner til venstre for dem.
    if preview_frame is not None:
        # 1. Action-knapper (lengst til høyre)
        ttk.Button(
            hdr,
            text="✓ Kontroller bilag…",
            command=lambda: _open_kontroll_dialog(top, bilag_norm, rows),
        ).pack(side="right", padx=(0, 0))

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

    # ── "Åpne PDF" (ekstern viewer) som ekstra header-knapp ──
    # Plasseres rett før "Kontroller bilag" i header. X i hjørnet
    # erstatter Lukk-knappen — ingen bunn-rad lenger.
    def _open_external() -> None:
        """Åpne PDF i systemets standard viewer."""
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
            messagebox.showerror("Åpne PDF", f"Feil:\n{exc}")
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
            messagebox.showerror("Åpne PDF", f"Kunne ikke åpne PDF:\n{exc}")

    if preview_frame is not None:
        # 2. Åpne PDF — neste høyre-pakkede havner til venstre for
        #    Kontroller bilag.
        ttk.Button(hdr, text="📂 Åpne PDF", command=_open_external).pack(side="right", padx=(0, 8))

        # 3. PDF-toolbar (page-nav + zoom) — pakkes etter action-knappene
        #    så de havner til venstre for dem. Reversert pack-rekkefølge
        #    siden side="right" stabler fra høyre kant.
        ttk.Button(hdr, text="Tilpass", command=preview_frame.fit_to_width, width=8).pack(side="right", padx=(4, 8))
        ttk.Button(hdr, text="+", command=preview_frame.zoom_in, width=2).pack(side="right")
        ttk.Button(hdr, text="−", command=preview_frame.zoom_out, width=2).pack(side="right")
        ttk.Button(hdr, text="►", command=preview_frame.show_next_page, width=3).pack(side="right", padx=(4, 0))
        ttk.Label(hdr, textvariable=preview_frame.var_page, width=8, anchor="center").pack(side="right", padx=2)
        ttk.Button(hdr, text="◄", command=preview_frame.show_previous_page, width=3).pack(side="right")

    # Fokus på treet for tastatur-navigasjon
    try:
        children = tree.get_children()
        if children:
            tree.focus(children[0])
            tree.selection_set(children[0])
    except Exception:
        pass
