"""analyse_sb_konto_details.py — Kontodetaljer-dialog (primær flate for én konto).

Utskilt fra page_analyse_sb.py. Innholder parser-hjelpere, datasamler og
show_kontodetaljer_dialog som åpner den store dialogen for én konto.
Kryss-seksjon-referanser (til review/remap-helpere) hentes lazily via
page_analyse_sb for å unngå sirkulære importer.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _parse_norwegian_number(text: str | float | int | None) -> float | None:
    """Tolk en tallstreng i norsk format (tusenskilletegn + komma)."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        try:
            if text != text:  # NaN
                return None
            return float(text)
        except Exception:
            return None
    s = str(text).strip()
    if not s or s == "—":
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    s = s.replace("\xa0", "").replace(" ", "")
    s = s.replace("−", "-")  # unicode minus
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        pass
    try:
        val = float(s)
    except Exception:
        return None
    return -val if neg else val


def _fmt_nok(value: float | None) -> str:
    if value is None:
        return "—"
    try:
        text = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    except Exception:
        return str(value)
    return text


def _resolve_raw_kontonavn(*, page: Any, konto: str) -> str:
    """Finn rått kontonavn fra `_rl_sb_df` — aldri det pyntede displaynavnet.

    Brukes av dialoger og eksport slik at kommentar/ikon fra SB-listens
    visningstekst (se `display_name` i SB-oppbyggingen) ikke lekker inn
    i formell dokumentasjon.
    """
    try:
        sb_df = getattr(page, "_rl_sb_df", None)
        if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
            return ""
        from analyse_sb_refresh import _resolve_sb_columns
        cols = _resolve_sb_columns(sb_df)
        kc, nc = cols.get("konto"), cols.get("kontonavn")
        if not kc or not nc:
            return ""
        m = sb_df[sb_df[kc].astype(str) == str(konto)]
        if m.empty:
            return ""
        return str(m.iloc[0].get(nc, "") or "").strip()
    except Exception:
        return ""


def _collect_konto_details(*, page: Any, konto: str) -> dict[str, str]:
    """Hent ut infosammendrag for en konto fra SB-treets rad + oppslag.

    Returnerer et dict med strenger slik de vises i GUI-en (allerede formatert).
    `kontonavn` er alltid rått navn fra datasettet — ikke pyntet display.
    """
    details: dict[str, str] = {
        "konto": str(konto), "kontonavn": "", "gruppe": "",
        "ib": "", "endring": "", "ub": "", "ub_fjor": "", "antall": "",
    }

    tree = getattr(page, "_sb_tree", None)
    if tree is not None:
        try:
            for iid in tree.get_children(""):
                vals = tree.item(iid, "values")
                if not vals:
                    continue
                if str(vals[0]).strip() != str(konto).strip():
                    continue
                # Rekkefølge: Konto, Kontonavn(display), OK, Vedlegg, Gruppe, IB, Endring, UB, UB_fjor, Antall
                # Merk: vals[1] er pyntet displaytekst — kontonavn hentes rått fra SB-df under.
                details["gruppe"]    = str(vals[4]) if len(vals) > 4 else ""
                details["ib"]        = str(vals[5]) if len(vals) > 5 else ""
                details["endring"]   = str(vals[6]) if len(vals) > 6 else ""
                details["ub"]        = str(vals[7]) if len(vals) > 7 else ""
                details["ub_fjor"]   = str(vals[8]) if len(vals) > 8 else ""
                details["antall"]    = str(vals[9]) if len(vals) > 9 else ""
                break
        except Exception:
            pass

    details["kontonavn"] = _resolve_raw_kontonavn(page=page, konto=konto)

    # Regnskapslinje (regnr + navn) — lazy import for å unngå sirkulær import
    import page_analyse_sb as _ps
    _resolve_regnr_by_konto = _ps._resolve_regnr_by_konto

    try:
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[str(konto)])
        info = rbk.get(str(konto))
        if info:
            details["regnr"] = str(int(info[0]))
            details["regnskapslinje"] = str(info[1])
    except Exception:
        pass
    details.setdefault("regnr", "")
    details.setdefault("regnskapslinje", "")

    return details


def show_kontodetaljer_dialog(*, page: Any, konto: str, kontonavn: str = "") -> None:
    """Åpne samlet Kontodetaljer-dialog (primær flate for én konto).

    Kombinerer konto-info, OK-markering, kommentar og vedlegg i ett
    resizable vindu. Bygger på eksisterende lagringsmodeller — ingen
    ny datamodell introduseres.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return

    # Lazy oppslag av kryss-seksjon-helpere (review + remap seksjoner)
    import page_analyse_sb as _ps
    _session_client_year = _ps._session_client_year
    _refresh_sb_after_review_change = _ps._refresh_sb_after_review_change
    _open_path = _ps._open_path
    _resolve_regnr_by_konto = _ps._resolve_regnr_by_konto

    client, year = _session_client_year()
    if not client or not year:
        return

    import src.shared.regnskap.client_overrides as _rco
    from pathlib import Path as _Path

    konto = str(konto).strip()
    if not konto:
        return

    details = _collect_konto_details(page=page, konto=konto)
    # Alltid rått kontonavn — ikke stol på displaytekst fra treeview
    kontonavn = details.get("kontonavn", "") or kontonavn

    dlg = tk.Toplevel(page)
    dlg.title(f"Kontodetaljer — {konto} {kontonavn}".strip())
    dlg.resizable(True, True)
    dlg.minsize(900, 560)

    # ---------- Infosammendrag (rad 1) ----------
    info_frame = ttk.LabelFrame(dlg, text="Konto")
    info_frame.pack(padx=12, pady=(12, 4), fill="x")

    rl_label = f"{details.get('regnr', '')} {details.get('regnskapslinje', '')}".strip() or "—"
    info_rows = [
        ("Konto", f"{konto}  {kontonavn}"),
        ("Regnskapslinje", rl_label),
        ("Gruppe", details.get("gruppe") or "—"),
        ("IB", details.get("ib") or "—"),
        ("Endring", details.get("endring") or "—"),
        ("UB", details.get("ub") or "—"),
        ("UB i fjor", details.get("ub_fjor") or "—"),
        ("Antall", details.get("antall") or "—"),
    ]
    for i, (lbl, val) in enumerate(info_rows):
        r, c = i // 4, (i % 4) * 2
        ttk.Label(info_frame, text=f"{lbl}:", foreground="#666").grid(
            row=r, column=c, sticky="w", padx=(8, 4), pady=2)
        ttk.Label(info_frame, text=val).grid(
            row=r, column=c + 1, sticky="w", padx=(0, 12), pady=2)
    for c in range(8):
        info_frame.columnconfigure(c, weight=1 if c % 2 == 1 else 0)

    # OK-status + sekundær handlingsstripe
    ok_frame = ttk.Frame(dlg)
    ok_frame.pack(padx=12, pady=(0, 4), fill="x")
    ok_var = tk.StringVar()

    def _refresh_ok_label() -> None:
        review = _rco.load_account_review(client, year)
        entry = review.get(konto, {}) or {}
        is_ok = bool(entry.get("ok"))
        if is_ok:
            by = str(entry.get("ok_by", "") or "").strip()
            at = str(entry.get("ok_at", "") or "").strip()
            # Kort dato (YYYY-MM-DD) fra ISO-tidsstempel
            at_short = at.split("T")[0] if at else ""
            parts = ["OK ✓"]
            if by and at_short:
                parts.append(f"— {by}, {at_short}")
            elif by:
                parts.append(f"— {by}")
            elif at_short:
                parts.append(f"— {at_short}")
            ok_var.set(" ".join(parts))
        else:
            ok_var.set("Ikke markert OK")
        ok_btn.configure(text=("Fjern OK" if is_ok else "Merk som OK"))

    ttk.Label(ok_frame, text="Status:", foreground="#666").pack(side="left", padx=(8, 4))
    ttk.Label(ok_frame, textvariable=ok_var, font=("TkDefaultFont", 10, "bold")
              ).pack(side="left")

    def _toggle_ok() -> None:
        review = _rco.load_account_review(client, year)
        is_ok = bool(review.get(konto, {}).get("ok"))
        _rco.set_accounts_ok(client, year, [konto], not is_ok)
        _refresh_ok_label()
        _refresh_sb_after_review_change(page)

    ok_btn = ttk.Button(ok_frame, text="Merk som OK", command=_toggle_ok)
    ok_btn.pack(side="right", padx=(0, 8))

    def _do_export_workpaper() -> None:
        """Eksporter revisjonsunderlag: mappe med PDF + primær kildefil."""
        try:
            import account_workpaper_pdf as _awp
            import client_store as _cs
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Kunne ikke laste eksport-modul:\n{exc}", parent=dlg,
            )
            return
        review = {}
        try:
            review = _rco.load_account_review(client, year).get(konto, {}) or {}
        except Exception:
            pass
        payload = _awp.AccountWorkpaperData(
            client=client,
            year=str(year),
            konto=konto,
            kontonavn=kontonavn,
            regnr=str(details.get("regnr", "") or ""),
            regnskapslinje=str(details.get("regnskapslinje", "") or ""),
            ib=str(details.get("ib", "") or ""),
            endring=str(details.get("endring", "") or ""),
            ub=str(details.get("ub", "") or ""),
            ub_fjor=str(details.get("ub_fjor", "") or ""),
            antall=str(details.get("antall", "") or ""),
            ok=bool(review.get("ok")),
            comment=_rco.load_comments(client).get("accounts", {}).get(konto, "") or "",
            attachments=_load_atts(),
            ub_evidence=_load_evidence(),
        )
        try:
            dest_dir = _cs.exports_dir(client, year=str(year))
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Kunne ikke finne eksportmappe:\n{exc}", parent=dlg,
            )
            return
        try:
            result = _awp.export_account_workpaper_package(
                data=payload, dest_dir=dest_dir, year=str(year),
            )
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Eksport feilet:\n{exc}", parent=dlg,
            )
            return
        if result.source_included:
            msg = (
                f"Revisjonsunderlag lagret:\n{result.folder}\n\n"
                f"- {result.pdf_path.name}\n"
                f"- {result.source_path.name}\n\n"
                "Åpne mappen nå?"
            )
        else:
            msg = (
                f"Revisjonsunderlag lagret:\n{result.folder}\n\n"
                f"- {result.pdf_path.name}\n"
                "(Kildefil var ikke tilgjengelig og ble ikke kopiert.)\n\n"
                "Åpne mappen nå?"
            )
        if messagebox.askyesno("Eksport", msg, parent=dlg):
            _open_path(str(result.folder))

    ttk.Button(
        ok_frame, text="Eksporter revisjonsunderlag…",
        command=_do_export_workpaper,
    ).pack(side="right", padx=(0, 6))

    # ---------- Delt visning: samlet venstreside ↔ preview (høyre) ----------
    try:
        from document_control_viewer import (
            DocumentPreviewFrame,
            preview_target_from_ub_evidence,
        )
    except Exception:
        DocumentPreviewFrame = None  # type: ignore[assignment]
        preview_target_from_ub_evidence = None  # type: ignore[assignment]

    paned = ttk.Panedwindow(dlg, orient="horizontal")
    paned.pack(padx=12, pady=(4, 6), fill="both", expand=True)

    # Venstre: vertikal PanedWindow med Kommentar (øverst), Vedlegg, UB-kontroll
    left_paned = ttk.Panedwindow(paned, orient="vertical")
    paned.add(left_paned, weight=1)

    # -- Preview-panel (høyre) --
    right_frame = ttk.Frame(paned)
    paned.add(right_frame, weight=1)

    preview: Any = None
    if DocumentPreviewFrame is not None:
        try:
            preview = DocumentPreviewFrame(right_frame)
            preview.pack(fill="both", expand=True)
        except Exception:
            preview = None
    if preview is None:
        ttk.Label(
            right_frame,
            text="Forhåndsvisning er ikke tilgjengelig i dette miljøet.",
            foreground="#888",
        ).pack(padx=8, pady=8)

    # ---------- Kommentar (øverst) ----------
    c_frame = ttk.LabelFrame(left_paned, text="Kommentar")
    left_paned.add(c_frame, weight=2)

    current_comment = _rco.load_comments(client).get("accounts", {}).get(konto, "")
    c_inner = ttk.Frame(c_frame)
    c_inner.pack(padx=8, pady=(8, 4), fill="both", expand=True)
    c_txt = tk.Text(c_inner, wrap="word", padx=6, pady=6, undo=True, height=6)
    c_scroll = ttk.Scrollbar(c_inner, orient="vertical", command=c_txt.yview)
    c_txt.configure(yscrollcommand=c_scroll.set)
    c_txt.pack(side="left", fill="both", expand=True)
    c_scroll.pack(side="right", fill="y")
    c_txt.insert("1.0", current_comment)

    c_btn_row = ttk.Frame(c_frame)
    c_btn_row.pack(padx=8, pady=(0, 8), fill="x")

    def _save_comment(_event: Any = None) -> str:
        text = c_txt.get("1.0", "end").strip()
        try:
            _rco.save_comment(client, kind="accounts", key=konto, text=text)
        except Exception as exc:
            messagebox.showerror("Kommentar",
                                 f"Kunne ikke lagre kommentar:\n{exc}", parent=dlg)
            return "break"
        try:
            refresh_views = getattr(page, "_refresh_analysis_views_after_adjustment_change", None)
            if callable(refresh_views):
                refresh_views()
        except Exception:
            pass
        return "break"

    ttk.Button(c_btn_row, text="Lagre kommentar", command=_save_comment).pack(side="right")

    # ---------- Vedlegg (midten) ----------
    v_frame = ttk.LabelFrame(left_paned, text="Vedlegg")
    left_paned.add(v_frame, weight=1)

    v_tree_frame = ttk.Frame(v_frame)
    v_tree_frame.pack(padx=8, pady=(8, 4), fill="both", expand=True)

    v_cols = ("label", "path", "storage", "added_at", "status")
    v_tree = ttk.Treeview(v_tree_frame, columns=v_cols, show="headings",
                          height=6, selectmode="browse")
    v_tree.heading("label", text="Navn")
    v_tree.heading("path", text="Sti")
    v_tree.heading("storage", text="Lagring")
    v_tree.heading("added_at", text="Lagt til")
    v_tree.heading("status", text="Status")
    v_tree.column("label", width=160, anchor="w")
    v_tree.column("path", width=240, anchor="w")
    v_tree.column("storage", width=100, anchor="center")
    v_tree.column("added_at", width=120, anchor="w")
    v_tree.column("status", width=70, anchor="center")
    v_scroll_att = ttk.Scrollbar(v_tree_frame, orient="vertical", command=v_tree.yview)
    v_tree.configure(yscrollcommand=v_scroll_att.set)
    v_tree.pack(side="left", fill="both", expand=True)
    v_scroll_att.pack(side="right", fill="y")

    empty_lbl = ttk.Label(v_frame, text="Ingen vedlegg — bruk 'Legg til vedlegg…' nederst.",
                          foreground="#888")

    def _storage_label(row: dict) -> str:
        s = str(row.get("storage", "external") or "external").lower()
        return "Utvalg-lager" if s == "managed" else "Ekstern"

    def _load_atts() -> list[dict]:
        try:
            return _rco.list_account_attachments(client, year, konto)
        except Exception:
            return []

    def _fill_atts() -> None:
        for iid in v_tree.get_children(""):
            v_tree.delete(iid)
        rows = _load_atts()
        for row in rows:
            p = row.get("path", "")
            exists = False
            try:
                exists = _Path(p).exists()
            except Exception:
                pass
            v_tree.insert("", "end", values=(
                row.get("label", "") or _Path(p).name,
                p, _storage_label(row),
                row.get("added_at", ""),
                "" if exists else "Mangler",
            ))
        if not rows:
            empty_lbl.pack(pady=(0, 8))
        else:
            empty_lbl.pack_forget()
        _refresh_ub_tab()

    def _selected_att_path() -> str:
        sel = v_tree.selection()
        if not sel:
            return ""
        vals = v_tree.item(sel[0], "values")
        return str(vals[1]) if vals and len(vals) > 1 else ""

    def _selected_att_row() -> dict | None:
        p = _selected_att_path()
        if not p:
            return None
        for row in _load_atts():
            if str(row.get("path", "")) == p:
                return row
        return None

    def _on_att_select(_event: Any = None) -> None:
        p = _selected_att_path()
        if not p or preview is None:
            return
        try:
            if not _Path(p).exists():
                return
            preview.load_file(p)
        except Exception:
            return
        # Forsøk automatisk UB-forslag som del av normalflyten.
        # Planlagt oppførsel: ikke overskriv manuelt bevis, ingen feildialog
        # ved manglende treff – bare rolig hint i UB-kontroll.
        _try_auto_on_attachment_select(p)

    def _do_att_open() -> None:
        p = _selected_att_path()
        if not p:
            return
        if not _Path(p).exists():
            messagebox.showinfo("Vedlegg", f"Filen finnes ikke lenger:\n{p}", parent=dlg)
            return
        _open_path(p)

    def _do_att_open_folder() -> None:
        p = _selected_att_path()
        if not p:
            return
        folder = str(_Path(p).parent)
        if not _Path(folder).exists():
            messagebox.showinfo("Vedlegg", f"Mappen finnes ikke:\n{folder}", parent=dlg)
            return
        _open_path(folder)

    def _do_att_add() -> None:
        try:
            from tkinter import filedialog
        except Exception:
            return
        paths = filedialog.askopenfilenames(
            parent=dlg, title=f"Velg vedlegg for {konto} {kontonavn}".strip())
        if not paths:
            return
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[konto])
        try:
            _rco.add_account_attachments(client, year, [konto], list(paths),
                                         regnr_by_konto=rbk)
        except Exception as exc:
            messagebox.showerror("Vedlegg", f"Kunne ikke lagre vedlegg:\n{exc}", parent=dlg)
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    def _do_att_remove() -> None:
        p = _selected_att_path()
        if not p:
            return
        if not messagebox.askyesno("Fjern kobling",
                                   f"Fjerne koblingen til:\n{p}?", parent=dlg):
            return
        try:
            _rco.remove_account_attachment(client, year, konto, p)
        except Exception:
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    def _do_att_migrate() -> None:
        row = _selected_att_row()
        if not row:
            return
        if str(row.get("storage", "external")).lower() == "managed":
            messagebox.showinfo("Utvalg-lager",
                                "Vedlegget er allerede lagret i Utvalg-lager.",
                                parent=dlg)
            return
        src = str(row.get("path", ""))
        if not src or not _Path(src).exists():
            messagebox.showinfo("Utvalg-lager",
                                f"Kan ikke migrere — kildefilen finnes ikke:\n{src}",
                                parent=dlg)
            return
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[konto])
        rl_info = rbk.get(konto)
        if not rl_info:
            messagebox.showinfo("Utvalg-lager",
                                f"Fant ikke regnskapslinje for konto {konto}.",
                                parent=dlg)
            return
        try:
            _rco.migrate_attachment_to_managed(client, year, konto, src,
                                               regnr=rl_info[0],
                                               regnskapslinje=rl_info[1])
        except Exception as exc:
            messagebox.showerror("Utvalg-lager",
                                 f"Migrering feilet:\n{exc}", parent=dlg)
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    v_tree.bind("<<TreeviewSelect>>", _on_att_select)
    v_tree.bind("<Double-1>", lambda _e: _do_att_open())
    v_tree.bind("<Return>", lambda _e: _do_att_open())
    v_tree.bind("<Delete>", lambda _e: _do_att_remove())

    v_btn_row = ttk.Frame(v_frame)
    v_btn_row.pack(padx=8, pady=(0, 8), fill="x")
    ttk.Button(v_btn_row, text="Legg til vedlegg…", command=_do_att_add).pack(side="left")
    ttk.Button(v_btn_row, text="Åpne", command=_do_att_open).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Åpne mappe", command=_do_att_open_folder
               ).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Kopier inn i Utvalg-lager",
               command=_do_att_migrate).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Fjern kobling", command=_do_att_remove
               ).pack(side="left", padx=(6, 0))

    # ---------- UB-kontroll (nederst) ----------
    ub_frame = ttk.LabelFrame(left_paned, text="UB-kontroll")
    left_paned.add(ub_frame, weight=2)

    expected_ub_value = _parse_norwegian_number(details.get("ub", ""))

    ub_info = ttk.Frame(ub_frame)
    ub_info.pack(padx=8, pady=(8, 4), fill="x")
    ub_info.columnconfigure(1, weight=1)

    var_expected = tk.StringVar(value=details.get("ub", "") or "—")
    var_evidence_label = tk.StringVar(value="—")
    var_evidence_page = tk.StringVar(value="—")
    var_raw = tk.StringVar(value="")
    var_doc_value = tk.StringVar(value="—")
    var_avvik = tk.StringVar(value="—")
    var_status = tk.StringVar(value="Ikke kontrollert")
    var_source = tk.StringVar(value="—")
    var_note = tk.StringVar(value="")

    def _row(r: int, label: str, var: tk.StringVar, *, bold: bool = False) -> None:
        ttk.Label(ub_info, text=label, foreground="#666").grid(
            row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        lbl = ttk.Label(ub_info, textvariable=var)
        if bold:
            try:
                lbl.configure(font=("TkDefaultFont", 10, "bold"))
            except Exception:
                pass
        lbl.grid(row=r, column=1, sticky="w", pady=2)

    _row(0, "Forventet UB (fra analyse):", var_expected, bold=True)
    _row(1, "Valgt bevis:", var_evidence_label)
    _row(2, "Side:", var_evidence_page)
    _row(3, "Kilde:", var_source)
    _row(4, "Avvik (dok − analyse):", var_avvik, bold=True)
    _row(5, "Status:", var_status, bold=True)

    raw_row = ttk.Frame(ub_frame)
    raw_row.pack(padx=8, pady=(4, 4), fill="x")
    ttk.Label(raw_row, text="Verdi fra dokument (rå):", foreground="#666"
              ).pack(side="left", padx=(0, 6))
    raw_entry = ttk.Entry(raw_row, textvariable=var_raw, width=24)
    raw_entry.pack(side="left")
    ttk.Label(raw_row, text="→ tolket:", foreground="#666"
              ).pack(side="left", padx=(8, 4))
    ttk.Label(raw_row, textvariable=var_doc_value).pack(side="left")

    note_row = ttk.Frame(ub_frame)
    note_row.pack(padx=8, pady=(4, 4), fill="x")
    ttk.Label(note_row, text="Notat:", foreground="#666"
              ).pack(side="left", padx=(0, 6))
    ttk.Entry(note_row, textvariable=var_note).pack(side="left", fill="x", expand=True)

    # Rolig fallback-hint: vises kun når auto-søk feilet uten å lagre noe
    var_hint = tk.StringVar(value="")
    hint_lbl = ttk.Label(ub_frame, textvariable=var_hint, foreground="#888")
    hint_lbl.pack(padx=8, pady=(0, 4), fill="x")

    ub_btn_row = ttk.Frame(ub_frame)
    ub_btn_row.pack(padx=8, pady=(4, 8), fill="x")

    def _set_hint(text: str = "") -> None:
        var_hint.set(text)

    def _load_evidence() -> dict | None:
        try:
            return _rco.load_ub_evidence(client, year, konto)
        except Exception:
            return None

    def _compute_status(
        doc_value: float | None, expected: float | None
    ) -> tuple[str, float | None]:
        if doc_value is None or expected is None:
            return "unchecked", None
        avvik = round(float(doc_value) - float(expected), 2)
        status = "match" if abs(avvik) < 0.5 else "mismatch"
        return status, avvik

    def _status_text(status: str) -> str:
        return {
            "match": "OK — verdi stemmer",
            "mismatch": "Avvik",
            "unchecked": "Ikke kontrollert",
        }.get(status, "Ikke kontrollert")

    def _source_text(source: str) -> str:
        return {
            "manual": "Manuell markering",
            "auto": "Automatisk forslag",
        }.get(str(source or "").strip().lower(), "—")

    def _refresh_ub_tab() -> None:
        ev = _load_evidence()
        if ev is None:
            var_evidence_label.set("—")
            var_evidence_page.set("—")
            var_raw.set("")
            var_doc_value.set("—")
            var_avvik.set("—")
            var_status.set("Ikke kontrollert")
            var_source.set("—")
            var_note.set("")
            return
        # Bevis finnes: nullstill eventuell auto-fallback-hint
        _set_hint("")
        var_evidence_label.set(str(ev.get("attachment_label") or _Path(str(ev.get("attachment_path", ""))).name))
        var_evidence_page.set(str(ev.get("page") or "—"))
        var_raw.set(str(ev.get("raw_value") or ""))
        nv = ev.get("normalized_value")
        if nv is None:
            parsed = _parse_norwegian_number(str(ev.get("raw_value") or ""))
        else:
            try:
                parsed = float(nv)
            except Exception:
                parsed = None
        var_doc_value.set(_fmt_nok(parsed) if parsed is not None else "—")
        status, avvik = _compute_status(parsed, expected_ub_value)
        var_avvik.set(_fmt_nok(avvik) if avvik is not None else "—")
        var_status.set(_status_text(status))
        var_source.set(_source_text(str(ev.get("source", ""))))
        var_note.set(str(ev.get("note") or ""))

    def _on_raw_changed(*_args: Any) -> None:
        parsed = _parse_norwegian_number(var_raw.get())
        var_doc_value.set(_fmt_nok(parsed) if parsed is not None else "—")
        status, avvik = _compute_status(parsed, expected_ub_value)
        var_avvik.set(_fmt_nok(avvik) if avvik is not None else "—")
        var_status.set(_status_text(status))

    var_raw.trace_add("write", _on_raw_changed)

    def _focus_ub_evidence() -> None:
        ev = _load_evidence()
        if not ev or preview is None:
            return
        path = str(ev.get("attachment_path") or "")
        try:
            if path and _Path(path).exists():
                preview.load_file(path)
                if preview_target_from_ub_evidence is not None:
                    target = preview_target_from_ub_evidence(ev, label="UB")
                    if target is not None:
                        preview.set_highlight(target)
        except Exception:
            pass

    def _attempt_auto_find(path: str) -> dict | None:
        """Forsøk automatisk UB-deteksjon i PDF. Returnerer match-dict eller None.

        Returnerer kun noe når kildedokumentet er en PDF som appen allerede
        kan forhåndsvise. Bilder og andre filtyper støttes ikke i v1.
        """
        if preview is None or expected_ub_value is None:
            return None
        try:
            from document_control_viewer import preview_kind_for_path
            if preview_kind_for_path(path) != "pdf":
                return None
        except Exception:
            return None
        try:
            preview.load_file(path)
        except Exception:
            return None
        try:
            return preview.find_ub_match(expected_ub_value)
        except Exception:
            return None

    def _try_auto_on_attachment_select(path: str) -> None:
        """Kjør stille auto-UB-forslag når vedlegg velges.

        Regler:
        - Bare PDF. For bilder/uspesifisert: rolig hint, ingen dialog.
        - Overskriv aldri manuelt bevis på samme vedlegg.
        - Ved entydig treff: lagre evidence (source="auto") og highlight.
        - Ved tvetydig/manglende: rolig hint i UB-kontroll, ingen dialog.
        """
        if expected_ub_value is None or preview is None:
            return
        try:
            from document_control_viewer import preview_kind_for_path
            kind = preview_kind_for_path(path)
        except Exception:
            kind = "unsupported"
        if kind != "pdf":
            _set_hint("Automatisk UB-søk støttes foreløpig bare for PDF.")
            return

        prior = _load_evidence() or {}
        prior_source = str(prior.get("source") or "").lower()
        prior_path = str(prior.get("attachment_path") or "")
        same_attachment = prior_path == path
        if prior_source == "manual" and prior.get("bbox") and same_attachment:
            # Manuelt bevis på samme vedlegg — ikke rør, bare highlight.
            _focus_ub_evidence()
            return

        match = _attempt_auto_find(path)
        if match is None:
            _set_hint("Fant ikke sikkert treff — bruk 'Marker manuelt'.")
            return

        row = _selected_att_row() or {}
        normalized = match.get("normalized_value")
        status, _avvik = _compute_status(
            float(normalized) if normalized is not None else None,
            expected_ub_value,
        )
        new_ev = {
            "attachment_path": path,
            "attachment_label": row.get("label") or _Path(path).name,
            "page": int(match.get("page") or 1),
            "bbox": list(match.get("bbox") or []),
            "raw_value": str(match.get("raw_value") or ""),
            "normalized_value": normalized,
            "status": status,
            "source": "auto",
            "note": (prior.get("note") if same_attachment else "") or "",
        }
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception:
            _set_hint("Kunne ikke lagre automatisk UB-forslag.")
            return
        _set_hint("")
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _set_selected_as_primary() -> None:
        row = _selected_att_row()
        if not row:
            messagebox.showinfo(
                "Primært UB-bevis",
                "Velg et vedlegg i Vedlegg-fanen først.",
                parent=dlg,
            )
            return
        path = str(row.get("path") or "")
        if not path:
            return
        prior = _load_evidence() or {}
        prior_source = str(prior.get("source") or "").lower()
        prior_path = str(prior.get("attachment_path") or "")
        same_attachment = prior_path == path

        # Prøv automatisk forslag først hvis det er trygt (ingen manuell
        # markering skal overskrives uten eksplisitt handling).
        auto: dict | None = None
        may_auto = (
            not prior  # ingen eksisterende
            or prior_source == "auto"
            or (prior_source == "manual" and not same_attachment)  # nytt vedlegg
        ) and (not prior.get("bbox") or prior_source != "manual" or not same_attachment)
        if may_auto:
            auto = _attempt_auto_find(path)

        if auto is not None:
            raw_value = str(auto.get("raw_value") or "")
            normalized = auto.get("normalized_value")
            status, _avvik = _compute_status(
                float(normalized) if normalized is not None else None,
                expected_ub_value,
            )
            new_ev = {
                "attachment_path": path,
                "attachment_label": row.get("label") or _Path(path).name,
                "page": int(auto.get("page") or 1),
                "bbox": list(auto.get("bbox") or []),
                "raw_value": raw_value,
                "normalized_value": normalized,
                "status": status,
                "source": "auto",
                "note": var_note.get() or (prior.get("note") if same_attachment else ""),
            }
        else:
            # Fallback: gjenbruk eksisterende bevis for samme vedlegg, ellers tomt.
            keep = prior if same_attachment else {}
            new_ev = {
                "attachment_path": path,
                "attachment_label": row.get("label") or _Path(path).name,
                "page": keep.get("page") or 1,
                "bbox": keep.get("bbox"),
                "raw_value": keep.get("raw_value") or var_raw.get(),
                "normalized_value": keep.get("normalized_value"),
                "status": keep.get("status") or "unchecked",
                "source": keep.get("source") or "manual",
                "note": var_note.get() or keep.get("note") or "",
            }

        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _find_ub_auto_explicit() -> None:
        """Eksplisitt 'Finn UB automatisk' — overstyrer også manuelt bevis hvis bruker bekrefter."""
        ev = _load_evidence() or {}
        path = str(ev.get("attachment_path") or "")
        if not path:
            row = _selected_att_row()
            if row:
                path = str(row.get("path") or "")
        if not path:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Velg et vedlegg i Vedlegg-listen først.",
                parent=dlg,
            )
            return

        try:
            from document_control_viewer import preview_kind_for_path
            kind = preview_kind_for_path(path)
        except Exception:
            kind = "unsupported"
        if kind != "pdf":
            messagebox.showinfo(
                "Finn UB automatisk",
                "Automatisk søk støttes foreløpig bare for PDF.",
                parent=dlg,
            )
            return
        if expected_ub_value is None:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Forventet UB er ikke tilgjengelig fra analysen.",
                parent=dlg,
            )
            return

        existing_source = str(ev.get("source") or "").lower()
        if existing_source == "manual" and ev.get("bbox"):
            if not messagebox.askyesno(
                "Finn UB automatisk",
                "Det finnes allerede et manuelt markert bevis. Vil du la "
                "automatisk forslag overstyre dette?",
                parent=dlg,
            ):
                return

        match = _attempt_auto_find(path)
        if not match:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Fant ikke et entydig treff. Bruk 'Marker manuelt' i stedet.",
                parent=dlg,
            )
            return

        normalized = match.get("normalized_value")
        status, _avvik = _compute_status(
            float(normalized) if normalized is not None else None,
            expected_ub_value,
        )
        new_ev = {
            "attachment_path": path,
            "attachment_label": ev.get("attachment_label") or _Path(path).name,
            "page": int(match.get("page") or 1),
            "bbox": list(match.get("bbox") or []),
            "raw_value": str(match.get("raw_value") or ""),
            "normalized_value": normalized,
            "status": status,
            "source": "auto",
            "note": var_note.get() or ev.get("note") or "",
        }
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _start_marking() -> None:
        if preview is None:
            messagebox.showinfo(
                "Marker UB-felt",
                "Forhåndsvisning er ikke tilgjengelig.",
                parent=dlg,
            )
            return
        ev = _load_evidence()
        path = ""
        if ev:
            path = str(ev.get("attachment_path") or "")
        if not path:
            row = _selected_att_row()
            if row:
                path = str(row.get("path") or "")
        if not path or not _Path(path).exists():
            messagebox.showinfo(
                "Marker UB-felt",
                "Velg et vedlegg i Vedlegg-fanen eller sett et primært bevis først.",
                parent=dlg,
            )
            return
        try:
            preview.load_file(path)
        except Exception:
            pass

        def _on_marked(page_no: int, bbox: tuple[float, float, float, float]) -> None:
            ev_now = _load_evidence() or {}
            row = _selected_att_row()
            label = (
                ev_now.get("attachment_label")
                or (row.get("label") if row else None)
                or _Path(path).name
            )
            new_ev = {
                "attachment_path": path,
                "attachment_label": label,
                "page": int(page_no),
                "bbox": list(bbox),
                "raw_value": ev_now.get("raw_value") or var_raw.get(),
                "normalized_value": ev_now.get("normalized_value"),
                "status": "unchecked",
                "source": "manual",
                "note": var_note.get(),
            }
            try:
                _rco.save_ub_evidence(client, year, konto, new_ev)
            except Exception as exc:
                messagebox.showerror("UB-bevis",
                                     f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
                return
            _refresh_ub_tab()
            _refresh_sb_after_review_change(page)

        try:
            preview.start_marking(_on_marked, label="UB")
        except Exception:
            pass

    def _use_marked_value() -> None:
        parsed = _parse_norwegian_number(var_raw.get())
        ev = _load_evidence()
        if not ev:
            messagebox.showinfo(
                "Bruk markert verdi",
                "Lagre et UB-bevis (marker UB-felt) før du registrerer verdi.",
                parent=dlg,
            )
            return
        status, _avvik = _compute_status(parsed, expected_ub_value)
        new_ev = dict(ev)
        new_ev["raw_value"] = var_raw.get().strip()
        new_ev["normalized_value"] = parsed
        new_ev["status"] = status
        new_ev["note"] = var_note.get()
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)

    def _clear_evidence() -> None:
        if not messagebox.askyesno(
            "Fjern UB-bevis",
            "Vil du fjerne UB-bevis for denne kontoen?",
            parent=dlg,
        ):
            return
        try:
            _rco.clear_ub_evidence(client, year, konto)
        except Exception:
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        if preview is not None:
            try:
                preview.set_highlight(None)
            except Exception:
                pass

    ttk.Button(ub_btn_row, text="Bruk som primært bevis",
               command=_set_selected_as_primary).pack(side="left")
    ttk.Button(ub_btn_row, text="Finn UB automatisk",
               command=_find_ub_auto_explicit).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Marker manuelt",
               command=_start_marking).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Bruk registrert verdi",
               command=_use_marked_value).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Gå til UB-bevis",
               command=_focus_ub_evidence).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Fjern markering",
               command=_clear_evidence).pack(side="left", padx=(6, 0))

    # Ingen `Lukk`-knapp i hovedvinduet — vindus-X og Escape lukker dialogen.

    # ---------- Tastatur ----------
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.bind("<Control-Return>", _save_comment)

    _refresh_ok_label()
    _fill_atts()
    _refresh_ub_tab()

    # Hvis bevis finnes ved åpning: last vedlegg i preview og fokuser bevis
    _focus_ub_evidence()

    def _apply_sash_ratio() -> None:
        """Sett sash slik at preview (høyre) får ~65% av bredden."""
        try:
            total = paned.winfo_width()
            if total > 200:
                paned.sashpos(0, int(total * 0.35))
        except Exception:
            pass

    dlg.update_idletasks()
    try:
        w, h = 1320, 780
        x = page.winfo_rootx() + max(0, (page.winfo_width() - w) // 2)
        y = page.winfo_rooty() + max(0, (page.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass
    # Kjør sash-justering etter geometry er satt (Tkinter trenger en runde
    # for at winfo_width() skal gjenspeile ny vindusstørrelse).
    dlg.after(50, _apply_sash_ratio)
    c_txt.focus_set()

