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

from .drill import (
    _resolve_drilldown_inputs,
    annotate_scope,
    extract_bilag_rows,
    konto_set_from_df,
    normalize_bilag_value,
    _first_existing_column,
)


def _open_supplier_transactions_popup(
    parent: Any,
    sub_df: pd.DataFrame,
    leverandør_navn: str,
    leverandør_orgnr: str,
    drill_master: Any,
    bilag_col: str,
) -> None:
    """Popup som lister alle transaksjoner mot en leverandør (året).

    Dobbeltklikk på en rad åpner det bilaget i en ny split-view.
    """
    if tk is None or ttk is None:
        return
    if sub_df is None or sub_df.empty:
        messagebox.showinfo(
            "Leverandør-transaksjoner",
            "Ingen transaksjoner mot denne leverandøren.",
        )
        return

    win = tk.Toplevel(parent)
    title_parts = []
    if leverandør_navn:
        title_parts.append(leverandør_navn)
    if leverandør_orgnr:
        title_parts.append(f"({leverandør_orgnr})")
    win.title("Transaksjoner mot " + " ".join(title_parts) if title_parts else "Leverandør-transaksjoner")

    try:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w = max(900, min(int(sw * 0.65), 1300))
        h = max(600, min(int(sh * 0.75), 900))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.minsize(800, 500)
    except Exception:
        pass

    # Topptekst med leverandør + sum-stats
    hdr = ttk.Frame(win, padding=(12, 10, 12, 4))
    hdr.pack(fill="x")
    title_label = ttk.Label(
        hdr,
        text=leverandør_navn or "(uten navn)",
        font=("TkDefaultFont", 12, "bold"),
        foreground="#1a4c7a",
    )
    title_label.pack(side="left", padx=(0, 14))
    if leverandør_orgnr:
        ttk.Label(hdr, text=f"Orgnr {leverandør_orgnr}", foreground="#888").pack(
            side="left", padx=(0, 14)
        )

    # Sortér etter dato (nyeste først)
    df = sub_df.copy()
    if "Dato" in df.columns:
        try:
            df["_sort_dato"] = pd.to_datetime(df["Dato"], errors="coerce", dayfirst=True)
            df = df.sort_values(by=["_sort_dato"], ascending=False, kind="mergesort")
            df = df.drop(columns=["_sort_dato"])
        except Exception:
            pass

    n_bilag = int(df[bilag_col].astype(str).nunique()) if bilag_col in df.columns else 0
    bel = pd.to_numeric(df.get("Beløp", 0), errors="coerce").fillna(0.0)
    sum_total = float(bel.sum())
    sum_pos = float(bel[bel > 0].sum())

    stats_frame = ttk.Frame(hdr)
    stats_frame.pack(side="right")
    for label, val, color in (
        ("Bilag", formatting.format_int_no(n_bilag), "#222"),
        ("Linjer", formatting.format_int_no(len(df)), "#222"),
        ("Sum debet", formatting.fmt_amount(sum_pos), "#1a4c7a"),
        ("Netto", formatting.fmt_amount(sum_total), "#222"),
    ):
        cell = ttk.Frame(stats_frame)
        cell.pack(side="left", padx=(0, 14))
        ttk.Label(cell, text=label, font=("TkDefaultFont", 8), foreground="#888").pack(anchor="w")
        ttk.Label(cell, text=val, font=("TkDefaultFont", 10, "bold"), foreground=color).pack(anchor="w")

    # Treeview
    from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
    import analyse_treewidths

    cols = ("Bilag", "Dato", "Konto", "Kontonavn", "Tekst", "Beløp", "MVA-kode")
    available_cols = [c for c in cols if c in df.columns]

    column_specs = []
    for c in available_cols:
        column_specs.append(
            ColumnSpec(
                id=c,
                heading=c,
                width=analyse_treewidths.default_column_width(c),
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=analyse_treewidths.column_anchor(c),
                stretch=False,
                visible_by_default=True,
                sortable=True,
            )
        )

    tree_frame = ttk.Frame(win, padding=(12, 4, 12, 12))
    tree_frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(
        tree_frame,
        columns=available_cols,
        show="headings",
        height=24,
        selectmode="browse",
    )
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="left", fill="y")

    try:
        ManagedTreeview(
            tree,
            view_id="bilag_split_supplier_transactions",
            pref_prefix="ui",
            column_specs=column_specs,
        )
    except Exception:
        pass

    try:
        tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    def _fmt(c: str, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and pd.isna(v):
            return ""
        if isinstance(v, str) and v.lower() == "nan":
            return ""
        if c == "Beløp":
            try:
                return formatting.fmt_amount(v)
            except Exception:
                return str(v)
        if c == "Dato":
            try:
                return formatting.fmt_date(v)
            except Exception:
                return str(v)
        return str(v)

    iid_to_bilag: dict[str, str] = {}
    for _, row in df.iterrows():
        tags = []
        try:
            if float(row.get("Beløp", 0)) < 0:
                tags.append("neg")
        except Exception:
            pass
        iid = tree.insert(
            "", "end",
            values=[_fmt(c, row.get(c)) for c in available_cols],
            tags=tuple(tags),
        )
        try:
            iid_to_bilag[iid] = str(row.get(bilag_col, ""))
        except Exception:
            pass

    def _open_selected_bilag(event: Any = None) -> None:
        sel = tree.selection()
        if not sel:
            return
        bilag_nr = iid_to_bilag.get(sel[0], "")
        if not bilag_nr:
            return
        try:
            open_bilag_split_view(
                drill_master,
                df_base=None,
                df_all=None,
                bilag_value=bilag_nr,
            )
        except Exception as exc:
            messagebox.showerror(
                "Kunne ikke åpne bilag",
                f"Feil ved åpning av bilag {bilag_nr}:\n{exc}",
                parent=win,
            )

    tree.bind("<Double-1>", _open_selected_bilag)
    tree.bind("<Return>", _open_selected_bilag)

    btn_row = ttk.Frame(win, padding=(12, 0, 12, 12))
    btn_row.pack(fill="x")
    ttk.Label(
        btn_row,
        text="Dobbeltklikk på en rad for å åpne bilaget.",
        foreground="#888",
        font=("TkDefaultFont", 9),
    ).pack(side="left")
    ttk.Button(btn_row, text="Lukk", command=win.destroy).pack(side="right")


def _open_kontroll_dialog(parent: Any, bilag_nr: str, rows: pd.DataFrame) -> None:
    """Modal dialog for å registrere haphazard-kontroll av et bilag.

    Brukeren velger konklusjon, kan legge til notat, og kan velge å
    arkivere PDF'en under ``documents/bilag/`` for senere referanse.
    """
    if tk is None or ttk is None:
        return
    from src.shared.ui.dialog import make_dialog
    from .haphazard_store import save_haphazard_test  # noqa: F401 (also imported in _save)
    from src.shared.document_control.voucher_index import find_and_extract_bilag

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

    # Regnr/Regnskapslinje fra konto via RL-mapping. Lagres med testen
    # slik at vi senere kan akkumulere kontroller per regnskapslinje
    # (f.eks. "alle haphazard-tester på RL 70 Annen driftskostnad").
    regnr_str = ""
    regnskapslinje_str = ""
    if konto_str:
        try:
            import regnskapslinje_mapping_service as _rl_svc
            _rl_ctx = _rl_svc.load_rl_mapping_context()
            _resolved = _rl_svc.resolve_accounts_to_rl([konto_str], context=_rl_ctx)
            if not _resolved.empty:
                regnr_val = _resolved.iloc[0].get("regnr")
                if regnr_val is not None and not pd.isna(regnr_val):
                    regnr_str = str(int(regnr_val))
                regnskapslinje_str = str(_resolved.iloc[0].get("regnskapslinje", "") or "")
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
    if regnr_str or regnskapslinje_str:
        rl_text = f"RL: {regnr_str}".strip()
        if regnskapslinje_str:
            rl_text += f" {regnskapslinje_str}"
        ttk.Label(info, text=rl_text).pack(anchor="w")
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
            from .haphazard_store import save_haphazard_test
            test = save_haphazard_test(
                client=client,
                year=year,
                bilag_nr=bilag_nr,
                konto=konto_str,
                kontonavn=kontonavn_str,
                regnr=regnr_str,
                regnskapslinje=regnskapslinje_str,
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

    # Adaptiv start-størrelse: 78 % bredde / 85 % høyde, sentrert. Mindre
    # enn 90 % gir luft rundt popupen og unngår at bilag med få rader får
    # massivt tomrom. A4-bilag er høye, så høyden prioriteres.
    try:
        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        win_w = max(1150, min(int(sw * 0.78), 1600))
        win_h = max(750, min(int(sh * 0.85), 1080))
        x = max(0, (sw - win_w) // 2)
        y = max(0, (sh - win_h) // 3)  # litt høyere enn midten — mer naturlig for høy popup
        top.geometry(f"{win_w}x{win_h}+{x}+{y}")
        top.minsize(1050, 680)
    except Exception:
        try:
            top.geometry("1400x880")
        except Exception:
            pass

    # Én konsolidert header-rad — bilag-info venstre, PDF-toolbar +
    # action-knapper høyre. Layouten gir maksimal vertikal plass til
    # PDF-en (A4-bilag er høye).
    hdr = ttk.Frame(top, padding=(12, 8, 12, 4))
    hdr.pack(fill="x")

    # Venstre side: bilag-tittel + sammendrag
    info_left = ttk.Frame(hdr)
    info_left.pack(side="left", anchor="w")

    # Bilag-nr som stor tittel
    ttk.Label(
        info_left,
        text=f"Bilag {bilag_norm}",
        font=("TkDefaultFont", 13, "bold"),
        foreground="#1a4c7a",
    ).pack(side="left", anchor="w", padx=(0, 14))

    # Sammendrag i kompakt form med fargekode
    summary_frame = ttk.Frame(info_left)
    summary_frame.pack(side="left", anchor="w")

    def _add_stat(parent, label: str, value: str, *, value_color: str = "#222") -> None:
        cell = ttk.Frame(parent)
        cell.pack(side="left", padx=(0, 16))
        ttk.Label(
            cell, text=label,
            font=("TkDefaultFont", 8),
            foreground="#888",
        ).pack(anchor="w")
        ttk.Label(
            cell, text=value,
            font=("TkDefaultFont", 10, "bold"),
            foreground=value_color,
        ).pack(anchor="w")

    _add_stat(summary_frame, "Rader", formatting.format_int_no(len(rows)))
    _add_stat(summary_frame, "Sum", formatting.fmt_amount(sum_all))
    sel_color = "#1a7a2a" if sum_sel else "#888"
    _add_stat(summary_frame, "I utvalg", formatting.fmt_amount(sum_sel), value_color=sel_color)
    mot_color = "#888" if not sum_mot else "#222"
    _add_stat(summary_frame, "Motposter", formatting.fmt_amount(sum_mot), value_color=mot_color)

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

    # Tree-høyden tilpasses antall rader (min 5, maks 14) — slik at små
    # bilag (3-5 rader) ikke får massivt tomrom og store bilag (50+) blir
    # scrollbare uten å sluke hele venstre kolonne. Tree-frame får IKKE
    # expand=True — i stedet legger vi en filler-frame nederst som suger
    # opp eventuell ekstra vertikal plass. Da ligger leverandør-panelene
    # rett under bilags-tabellen i stedet for å bli presset til bunnen.
    tree_height = min(max(len(rows), 5), 14)
    tree_frame = ttk.Frame(left)
    tree_frame.pack(fill="x")
    tree = ttk.Treeview(
        tree_frame,
        columns=all_col_ids,
        show="headings",
        height=tree_height,
        selectmode="browse",
    )
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

    # ── Leverandør-aktivitet (HB-stats for året) ──
    # Felles filter brukes både av stats-panel og transaksjons-popup, så de
    # alltid viser samme utvalg. Foretrekk Leverandørorgnr (sikker match);
    # fall tilbake til Leverandørnavn (case-insensitiv) hvis orgnr mangler.
    def _filter_supplier_transactions(src: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(src, pd.DataFrame) or src.empty:
            return pd.DataFrame()
        mask = pd.Series(False, index=src.index)
        if leverandør_orgnr and "Leverandørorgnr" in src.columns:
            mask = src["Leverandørorgnr"].astype(str).str.strip() == leverandør_orgnr
        if not mask.any() and leverandør_navn and "Leverandørnavn" in src.columns:
            mask = (
                src["Leverandørnavn"].astype(str).str.strip().str.casefold()
                == leverandør_navn.casefold()
            )
        return src[mask]

    if leverandør_navn or leverandør_orgnr:
        activity_panel = ttk.LabelFrame(
            left, text="Leverandør-aktivitet (året)", padding=8
        )
        activity_panel.pack(fill="x", pady=(8, 0))

        activity_text = tk.Text(
            activity_panel,
            height=4,
            wrap="word",
            relief="flat",
            borderwidth=0,
            font=("TkDefaultFont", 9),
            cursor="arrow",
            state="disabled",
        )
        activity_text.pack(fill="x")
        activity_text.tag_configure("key", foreground="#555555")
        activity_text.tag_configure("val", foreground="#111111")
        activity_text.tag_configure("dim", foreground="#888888")
        activity_text.tag_configure(
            "amount", foreground="#1a4c7a", font=("TkDefaultFont", 9, "bold")
        )

        def _activity_write(*parts: tuple[str, str]) -> None:
            try:
                activity_text.configure(state="normal")
                for text, tag in parts:
                    activity_text.insert("end", text, (tag,))
                activity_text.configure(state="disabled")
            except Exception:
                pass

        sub = _filter_supplier_transactions(df_all_res)
        if sub.empty:
            _activity_write(
                ("Kun dette bilaget mot leverandøren i år.", "dim"),
            )
        else:
            n_bilag = 0
            if bilag_col_res in sub.columns:
                try:
                    n_bilag = int(sub[bilag_col_res].astype(str).nunique())
                except Exception:
                    n_bilag = 0
            n_rows = len(sub)
            bel_sub = pd.to_numeric(sub.get("Beløp", 0), errors="coerce").fillna(0.0)

            # "Kost" = positive beløp på konto 4-7 (varekost, lønn, drift,
            # finans). Ekskluderer 24xx leverandørgjeld og 27xx MVA — de
            # er motposter, ikke selve kostnaden.
            if "Konto" in sub.columns:
                konto_str = sub["Konto"].astype(str)
                kost_mask = konto_str.str.startswith(("4", "5", "6", "7")) & (bel_sub > 0)
                sum_kost = float(bel_sub[kost_mask].sum())
            else:
                sum_kost = float(bel_sub[bel_sub > 0].sum())

            # Største enkelt-bilag (basert på sum kost per bilag)
            largest_bilag = ""
            largest_sum = 0.0
            try:
                if bilag_col_res in sub.columns and "Konto" in sub.columns:
                    kost_only = sub[
                        sub["Konto"].astype(str).str.startswith(("4", "5", "6", "7"))
                    ].copy()
                    if not kost_only.empty:
                        kost_only["_b"] = pd.to_numeric(
                            kost_only["Beløp"], errors="coerce"
                        ).fillna(0.0)
                        per_bilag = (
                            kost_only.groupby(bilag_col_res)["_b"].sum().abs().sort_values(ascending=False)
                        )
                        if not per_bilag.empty:
                            largest_bilag = str(per_bilag.index[0])
                            largest_sum = float(per_bilag.iloc[0])
            except Exception:
                pass

            dato_min, dato_max = "", ""
            if "Dato" in sub.columns:
                try:
                    dt = pd.to_datetime(
                        sub["Dato"], errors="coerce", dayfirst=True
                    ).dropna()
                    if not dt.empty:
                        dato_min = dt.min().strftime("%d.%m.%Y")
                        dato_max = dt.max().strftime("%d.%m.%Y")
                except Exception:
                    pass

            # Linje 1: bilag-count + linjer + periode
            _activity_write(
                ("Bilag: ", "key"),
                (formatting.format_int_no(n_bilag), "amount"),
                ("  |  Linjer: ", "key"),
                (formatting.format_int_no(n_rows), "val"),
            )
            if dato_min and dato_max:
                if dato_min == dato_max:
                    _activity_write(("  |  Dato: ", "key"), (dato_min, "val"))
                else:
                    _activity_write(
                        ("  |  Periode: ", "key"),
                        (f"{dato_min} – {dato_max}", "val"),
                    )
            _activity_write(("\n", "val"))

            # Linje 2: sum kost + snitt + største
            _activity_write(
                ("Sum kost: ", "key"),
                (formatting.fmt_amount(sum_kost), "amount"),
            )
            if n_bilag > 0 and sum_kost:
                snitt = sum_kost / n_bilag
                _activity_write(
                    ("  |  Snitt/bilag: ", "key"),
                    (formatting.fmt_amount(snitt), "val"),
                )
            if largest_bilag and largest_sum:
                _activity_write(
                    ("  |  Største: ", "key"),
                    (formatting.fmt_amount(largest_sum), "val"),
                    (f" (bilag {largest_bilag})", "dim"),
                )
            _activity_write(("\n", "val"))

            # Linje 3: top 3 konti (kun kost-konti 4-7)
            if "Konto" in sub.columns and "Kontonavn" in sub.columns:
                try:
                    kost_only = sub[
                        sub["Konto"].astype(str).str.startswith(("4", "5", "6", "7"))
                    ].copy()
                    if not kost_only.empty:
                        kost_only["_b"] = pd.to_numeric(
                            kost_only["Beløp"], errors="coerce"
                        ).fillna(0.0)
                        konto_grp = (
                            kost_only.groupby(["Konto", "Kontonavn"], dropna=False)["_b"]
                            .sum()
                            .sort_values(ascending=False)
                            .head(3)
                        )
                        if not konto_grp.empty:
                            _activity_write(("Mest brukte konti: ", "key"))
                            items = []
                            for (k, navn), s in konto_grp.items():
                                items.append(
                                    f"{k} {navn} ({formatting.fmt_amount(float(s))})"
                                )
                            _activity_write((" | ".join(items), "val"))
                except Exception:
                    pass

            # Knapp for å åpne full transaksjonsoversikt
            btn_row = ttk.Frame(activity_panel)
            btn_row.pack(fill="x", pady=(6, 0))
            ttk.Button(
                btn_row,
                text="Vis alle transaksjoner mot leverandør…",
                command=lambda: _open_supplier_transactions_popup(
                    top, sub, leverandør_navn, leverandør_orgnr, master, bilag_col_res
                ),
            ).pack(side="left")

    # Filler-frame helt nederst i venstre kolonne — suger opp eventuell
    # ekstra vertikal plass slik at tabellen + leverandør-panelene ligger
    # samlet øverst. Uten denne ble panelene presset til bunnen av popupen.
    ttk.Frame(left).pack(fill="both", expand=True)

    # ── HØYRE: PDF-preview (full høyde, ingen egen toolbar her) ──
    right = ttk.Frame(paned)
    try:
        paned.add(right, weight=3)
    except Exception:
        paned.add(right)

    preview_frame = None
    try:
        from src.shared.document_control.viewer import DocumentPreviewFrame
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
                from src.shared.document_control.voucher_index import find_and_extract_bilag
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
            # Auto-fit etter at canvas har fått størrelse — A4-bilag er
            # høye så fit-to-width gir best lesbarhet umiddelbart.
            try:
                top.after(150, preview_frame.fit_to_width)
            except Exception:
                pass

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
            from src.shared.document_control.voucher_index import find_and_extract_bilag
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

    # Sett sash-posisjon når PanedWindow har fått størrelse: ca. 37 %
    # til bilag-tabellen, 63 % til PDF-en. PDF-en prioriteres siden
    # A4-bilag trenger plass og en bredere PDF blir mye mer leselig
    # ved fit-to-width. Tabellen har færre default-kolonner enn TX-treet,
    # så den klarer seg fint på ~38 %.
    def _set_sash_position() -> None:
        try:
            top.update_idletasks()
            total_width = paned.winfo_width()
            if total_width > 200:
                paned.sashpos(0, int(total_width * 0.37))
        except Exception:
            pass

    try:
        top.after(50, _set_sash_position)
    except Exception:
        pass

    # Fokus på treet for tastatur-navigasjon
    try:
        children = tree.get_children()
        if children:
            tree.focus(children[0])
            tree.selection_set(children[0])
    except Exception:
        pass
