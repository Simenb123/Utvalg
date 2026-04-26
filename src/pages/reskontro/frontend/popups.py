"""reskontro_popups.py -- Popup-vinduer for reskontro.

Ekstrahert fra page_reskontro.py.
Alle funksjoner tar ``page`` som første parameter (ReskontroPage-instansen).
"""
from __future__ import annotations

import threading
from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import formatting
from ..backend.open_items import (
    _compute_open_items,
    _compute_open_items_with_confidence,
    _compute_aging_buckets,
    _match_open_against_period,
)


# Tag-konstanter (må matche page_reskontro.py)
_TAG_NEG      = "neg"
_TAG_HEADER   = "header"
_TAG_MVA_LINE = "mva_line"


def _get_make_popup(page: Any):
    """Hent _make_popup fra page_reskontro modulen."""
    from . import page as page_reskontro
    return page_reskontro._make_popup


def _get_setup_tree(page: Any):
    """Hent _setup_tree fra page_reskontro modulen."""
    from . import page as page_reskontro
    return page_reskontro._setup_tree


def open_bilag_popup(page: Any, bilag: str) -> None:
    """Vis popup med ALLE HB-linjer for bilag (inkl. MVA-linje på konto 27xx).

    Søker i hele datasettet (ikke kun reskontro-linjer), slik at
    motkonto, inntektslinje og MVA-linje vises med tilhørende MVA-kode.
    """
    from . import page as page_reskontro
    _make_popup = page_reskontro._make_popup
    _setup_tree = page_reskontro._setup_tree

    if page._df is None:
        return
    if "Bilag" not in page._df.columns:
        return

    # Søk i HELE datasettet — inkluderer alle kontolinjer, ikke bare reskontro
    mask = page._df["Bilag"].astype(str).str.strip() == bilag
    sub  = page._df[mask].copy()
    if sub.empty:
        return
    if "Dato" in sub.columns:
        sub = sub.sort_values("Dato")

    win = _make_popup(page,
                      title=f"Bilag {bilag}  —  alle HB-linjer (inkl. MVA-posteringer)",
                      geometry="960x340")

    cols = ("Dato", "Konto", "Kontonavn", "Tekst",
            "Beløp", "MVA-kode", "MVA-beløp", "Valuta")
    tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
    widths = {"Dato": 90, "Konto": 65, "Kontonavn": 170, "Tekst": 230,
              "Beløp": 110, "MVA-kode": 70, "MVA-beløp": 100, "Valuta": 55}
    right = {"Beløp", "MVA-beløp"}
    for c in cols:
        tree.heading(c, text=c, anchor="e" if c in right else "w")
        tree.column(c, width=widths.get(c, 90),
                    anchor="e" if c in right else "w",
                    stretch=c in ("Tekst", "Kontonavn"))
    tree.tag_configure(_TAG_NEG,      foreground="red")
    tree.tag_configure(_TAG_MVA_LINE, background="#F0FFF0")
    _setup_tree(tree, extended=True)

    vsb = ttk.Scrollbar(win, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(win, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)

    df_cols = list(sub.columns)

    def _v(col: str, row: Any, default: Any = "") -> Any:
        return row[col] if col in df_cols else default

    dec = page._detail_decimals()
    total = 0.0
    for _, row in sub.iterrows():
        dato     = str(_v("Dato",     row, ""))[:10]
        konto    = str(_v("Konto",    row, ""))
        knavn    = str(_v("Kontonavn",row, ""))
        tekst    = str(_v("Tekst",    row, ""))
        valuta   = str(_v("Valuta",   row, ""))
        mva_kode = str(_v("MVA-kode", row, ""))
        if mva_kode in ("nan", "None"):
            mva_kode = ""
        try:
            belop = float(_v("Beløp", row, 0.0))
        except (ValueError, TypeError):
            belop = 0.0
        try:
            mva_b_raw = _v("MVA-beløp", row, None)
            mva_b = float(mva_b_raw) if mva_b_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            mva_b = None

        total += belop
        has_mva = bool(mva_kode or (mva_b is not None and abs(mva_b) > 0.001))
        row_tags: list[str] = []
        if belop < 0:
            row_tags.append(_TAG_NEG)
        if has_mva:
            row_tags.append(_TAG_MVA_LINE)
        tree.insert("", "end", values=(
            dato, konto, knavn, tekst,
            formatting.fmt_amount(belop, dec),
            mva_kode,
            formatting.fmt_amount(mva_b, dec) if mva_b is not None else "",
            valuta,
        ), tags=tuple(row_tags))

    tree.insert("", "end", values=(
        "", "", "", f"\u03a3 {len(sub)} linjer",
        formatting.fmt_amount(total, dec),
        "", "", "",
    ), tags=(_TAG_HEADER,))

    dato_str = ""
    try:
        if "Dato" in df_cols:
            dato_str = f"  —  {str(sub['Dato'].iloc[0])[:10]}"
    except Exception:
        pass
    ttk.Label(win, text=f"Bilag {bilag}{dato_str}  •  netto {formatting.fmt_amount(total, dec)}",
              font=("TkDefaultFont", 9, "bold")).grid(
        row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 4))


def show_open_items_popup(page: Any) -> None:
    """Vis popup med åpne (ubetalte) fakturaer for valgt kunde/leverandør."""
    from . import page as page_reskontro
    _make_popup = page_reskontro._make_popup
    _setup_tree = page_reskontro._setup_tree

    if not page._selected_nr or page._df is None:
        return

    # Get UB and IB for confidence check
    ub_val = ib_val = None
    if page._master_df is not None:
        row_m = page._master_df[page._master_df["nr"].astype(str) == page._selected_nr]
        if not row_m.empty:
            ub_val = float(row_m["ub"].iloc[0])
            ib_val = float(row_m["ib"].iloc[0])

    result_df, confidence = _compute_open_items_with_confidence(
        page._df, nr=page._selected_nr, mode=page._mode, ub=ub_val, ib=ib_val)
    if result_df.empty:
        return

    dec      = page._detail_decimals()
    mode_str = "Kunde" if page._mode == "kunder" else "Leverandør"
    navn     = page._navn_for_nr(page._selected_nr)
    title_str = f"{mode_str} {page._selected_nr}" + (f"  —  {navn}" if navn else "")

    open_df   = result_df[result_df["Status"] == "✗ Åpen"]
    closed_df = result_df[result_df["Status"] == "✓ Betalt"]
    sum_open  = float(open_df["Gjenstår"].sum()) if not open_df.empty else 0.0

    win = _make_popup(page, title=f"Åpne poster  —  {title_str}", geometry="940x440")

    ttk.Label(
        win,
        text=(f"✗ {len(open_df)} åpne fakturaer   ✓ {len(closed_df)} betalt i samme år   "
              f"|   Sum åpne: {formatting.fmt_amount(sum_open, dec)}"),
        font=("TkDefaultFont", 9, "bold"),
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2))

    conf_color = {"høy": "#1a7a2a", "middels": "#8B4500", "lav": "#C00000"}.get(
        confidence["level"], "#666")
    ttk.Label(
        win,
        text=(f"{confidence['symbol']} {confidence['message']}"
              if confidence["message"] else
              "FIFO-prinsipp: eldste fakturaer antas betalt først."),
        foreground=conf_color, font=("TkDefaultFont", 8),
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

    # Vis alle fakturaer — åpne øverst, betalte nederst
    cols = ("Status", "Dato", "Bilag", "Tekst", "Fakturabeløp",
            "Betalt (i år)", "Gjenstår")
    tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
    widths = {"Status": 80, "Dato": 90, "Bilag": 80, "Tekst": 280,
              "Fakturabeløp": 120, "Betalt (i år)": 120, "Gjenstår": 120}
    right_cols = {"Fakturabeløp", "Betalt (i år)", "Gjenstår"}
    for c in cols:
        tree.heading(c, text=c, anchor="e" if c in right_cols else "w")
        tree.column(c, width=widths.get(c, 90),
                    anchor="e" if c in right_cols else "w",
                    stretch=c in ("Tekst",))
    tree.tag_configure("open",    foreground="#C00000", background="#FFF0F0")
    tree.tag_configure("partial", foreground="#8B4500")
    tree.tag_configure("closed",  foreground="#1a7a2a")
    tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                       font=("TkDefaultFont", 9, "bold"))
    _setup_tree(tree, extended=True)

    vsb = ttk.Scrollbar(win, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(win, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=2, column=0, sticky="nsew")
    vsb.grid(row=2, column=1, sticky="ns")
    hsb.grid(row=3, column=0, sticky="ew")
    win.rowconfigure(2, weight=1)
    win.columnconfigure(0, weight=1)

    for _, row in result_df.iterrows():
        status  = str(row["Status"])
        betalt  = row.get("Betalt (i år)")
        gjenst  = row.get("Gjenstår")
        tag = "open" if status == "✗ Åpen" else ("partial" if status == "~ Delvis betalt" else "closed")
        tree.insert("", "end", values=(
            status,
            str(row.get("Dato", ""))[:10],
            str(row.get("Bilag", "")),
            str(row.get("Tekst", "")),
            formatting.fmt_amount(row.get("Fakturabeløp"), dec),
            formatting.fmt_amount(betalt, dec) if betalt is not None else "",
            formatting.fmt_amount(gjenst, dec) if gjenst is not None else "",
        ), tags=(tag,))

    tree.insert("", "end", values=(
        "", "", "", f"\u03a3 {len(open_df)} åpne  /  {len(closed_df)} betalt",
        formatting.fmt_amount(result_df["Fakturabeløp"].sum(), dec),
        "", formatting.fmt_amount(sum_open, dec),
    ), tags=(_TAG_HEADER,))

    btns = ttk.Frame(win)
    btns.grid(row=4, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 6))
    if page._subsequent_df is not None:
        ttk.Button(
            btns, text=f"Matcher mot {page._subsequent_label[:30]}\u2026",
            command=page._show_subsequent_match_popup,
        ).pack(side="left")
    ttk.Button(btns, text="Lukk", command=win.destroy).pack(side="right")


def show_saldoliste_popup(page: Any) -> None:
    """Vis saldoliste — alle åpne poster på tvers av kunder/leverandører."""
    from . import page as page_reskontro
    _make_popup = page_reskontro._make_popup
    _setup_tree = page_reskontro._setup_tree

    if page._df is None or page._master_df is None or page._master_df.empty:
        return

    mode = page._mode
    dec = page._detail_decimals()
    mode_str = "Kunder" if mode == "kunder" else "Leverandører"

    win = _make_popup(page, title=f"Saldoliste \u2014 {mode_str}", geometry="1200x620")

    # --- Progress ---
    progress_frame = ttk.Frame(win)
    progress_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
    progress_lbl = ttk.Label(progress_frame, text="Beregner åpne poster\u2026")
    progress_lbl.pack(side="left")
    progress_bar = ttk.Progressbar(progress_frame, mode="determinate", length=300)
    progress_bar.pack(side="left", padx=(8, 0))

    # --- Summary (populated after computation) ---
    summary_lbl = ttk.Label(win, text="", font=("TkDefaultFont", 9, "bold"))
    summary_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 2))
    conf_lbl = ttk.Label(win, text="", foreground="#666", font=("TkDefaultFont", 8))
    conf_lbl.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

    # --- Tree ---
    cols = ("Nr", "Navn", "Bilag", "FakturaNr", "Dato", "Tekst",
            "Fakturabeløp", "Gjenstår", "UB", "Alder", "Tillit")
    tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
    widths = {"Nr": 60, "Navn": 150, "Bilag": 70, "FakturaNr": 80,
              "Dato": 85, "Tekst": 200, "Fakturabeløp": 110,
              "Gjenstår": 110, "UB": 100, "Alder": 55, "Tillit": 45}
    right_cols = {"Fakturabeløp", "Gjenstår", "UB", "Alder"}
    for c in cols:
        tree.heading(c, text=c, anchor="e" if c in right_cols else "w")
        tree.column(c, width=widths.get(c, 80),
                    anchor="e" if c in right_cols else "w",
                    stretch=c in ("Tekst", "Navn"))
    tree.tag_configure("open", foreground="#C00000", background="#FFF0F0")
    tree.tag_configure("partial", foreground="#8B4500")
    tree.tag_configure("low_conf", foreground="#C00000", background="#FFF8E1")
    tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                       font=("TkDefaultFont", 9, "bold"))
    _setup_tree(tree, extended=True)

    vsb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(win, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=3, column=0, sticky="nsew")
    vsb.grid(row=3, column=1, sticky="ns")
    hsb.grid(row=4, column=0, sticky="ew")
    win.rowconfigure(3, weight=1)
    win.columnconfigure(0, weight=1)

    # --- Aging frame (populated after computation) ---
    aging_frame = ttk.LabelFrame(
        win, text="Aldersfordeling (indikativ \u2014 basert på fakturadato)",
        padding=(4, 4))
    aging_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 2))

    # --- Buttons ---
    btns = ttk.Frame(win)
    btns.grid(row=6, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 6))
    ttk.Button(btns, text="Lukk", command=win.destroy).pack(side="right")

    # --- Reference date for aging ---
    reference_date = ""
    if "Dato" in page._df.columns:
        try:
            reference_date = str(page._df["Dato"].max())[:10]
        except Exception:
            pass

    # --- Background computation ---
    master_df = page._master_df.copy()
    df_snapshot = page._df

    def _compute():
        from datetime import datetime

        all_open: list[dict] = []
        conf_counts = {"høy": 0, "middels": 0, "lav": 0, "ukjent": 0}

        nrs = list(master_df["nr"].astype(str))
        total = len(nrs)

        for i, nr in enumerate(nrs):
            row_m = master_df[master_df["nr"].astype(str) == nr]
            ub_val = float(row_m["ub"].iloc[0]) if not row_m.empty else None
            ib_val = float(row_m["ib"].iloc[0]) if not row_m.empty else None
            navn = str(row_m["navn"].iloc[0]) if not row_m.empty else ""

            result_df, confidence = _compute_open_items_with_confidence(
                df_snapshot, nr=nr, mode=mode, ub=ub_val, ib=ib_val)

            ub_for_check = ub_val if ub_val is not None else 0.0

            if not result_df.empty:
                open_rows = result_df[result_df["Status"] != "✓ Betalt"]
                if open_rows.empty:
                    continue

                conf_counts[confidence["level"]] = conf_counts.get(confidence["level"], 0) + 1
                for _, row in open_rows.iterrows():
                    all_open.append({
                        "Nr": nr, "Navn": navn,
                        "Bilag": str(row.get("Bilag", "")),
                        "FakturaNr": str(row.get("FakturaNr", "")),
                        "Dato": str(row.get("Dato", ""))[:10],
                        "Tekst": str(row.get("Tekst", "")),
                        "Fakturabeløp": float(row.get("Fakturabeløp", 0)),
                        "Gjenstår": float(row.get("Gjenstår", 0)),
                        "Status": str(row.get("Status", "")),
                        "_conf_level": confidence["level"],
                        "_ub": ub_for_check,
                    })

            if i % 3 == 0 or i == total - 1:
                pct = int((i + 1) / total * 100) if total else 100
                try:
                    page.after(0, lambda p=pct, ii=i + 1, t=total: (
                        progress_bar.configure(value=p),
                        progress_lbl.configure(text=f"Beregner: {ii}/{t}\u2026")))
                except Exception:
                    pass

        page.after(0, lambda: _populate(all_open, conf_counts))

    def _populate(all_open: list[dict], conf_counts: dict):
        from datetime import datetime

        # Hide progress
        progress_frame.grid_forget()

        # Summary
        n_open = len(all_open)
        n_customers = len({r["Nr"] for r in all_open})
        sum_open = sum(r["Gjenstår"] for r in all_open)
        summary_lbl.configure(
            text=(f"✗ {n_open} åpne poster ({n_customers} "
                  f"{'kunder' if mode == 'kunder' else 'leverandører'})   "
                  f"|   Sum åpne: {formatting.fmt_amount(sum_open, dec)}"))

        # Confidence summary
        parts = []
        for lvl, sym in [("høy", "✓"), ("middels", "~"), ("lav", "⚠")]:
            cnt = conf_counts.get(lvl, 0)
            if cnt:
                parts.append(f"{sym} {cnt} {lvl}")
        conf_lbl.configure(
            text=f"FIFO-metode  |  {',  '.join(parts)}" if parts else "FIFO-metode")

        # Populate tree
        try:
            ref_dt = datetime.strptime(reference_date[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            ref_dt = None

        for item in sorted(all_open, key=lambda r: (r["Nr"], r["Dato"])):
            alder_str = ""
            if ref_dt:
                try:
                    inv_dt = datetime.strptime(item["Dato"][:10], "%Y-%m-%d")
                    alder_str = str((ref_dt - inv_dt).days)
                except (ValueError, TypeError):
                    pass
            conf_sym = {"høy": "✓", "middels": "~", "lav": "⚠"}.get(
                item["_conf_level"], "?")
            tag = "open" if item["Status"] == "✗ Åpen" else "partial"
            if item["_conf_level"] == "lav":
                tag = "low_conf"
            tree.insert("", "end", values=(
                item["Nr"], item["Navn"], item["Bilag"],
                item["FakturaNr"], item["Dato"], item["Tekst"],
                formatting.fmt_amount(item["Fakturabeløp"], dec),
                formatting.fmt_amount(item["Gjenstår"], dec),
                formatting.fmt_amount(item["_ub"], dec),
                alder_str, conf_sym,
            ), tags=(tag,))

        # Sum row
        tree.insert("", "end", values=(
            "", "", "", "",
            f"\u03a3 {n_open} åpne poster", "",
            "", formatting.fmt_amount(sum_open, dec), "", "", "",
        ), tags=(_TAG_HEADER,))

        # Aging
        aging = _compute_aging_buckets(all_open, reference_date=reference_date)
        if aging:
            ref_lbl = ttk.Label(
                aging_frame,
                text=f"Referansedato: {reference_date}",
                foreground="#666", font=("TkDefaultFont", 8))
            ref_lbl.pack(side="top", anchor="w")

            bucket_row = ttk.Frame(aging_frame)
            bucket_row.pack(side="top", fill="x", pady=(2, 0))
            for label, amount, count in aging:
                f = ttk.Frame(bucket_row, relief="groove", padding=(8, 2))
                f.pack(side="left", padx=(0, 6), fill="x", expand=True)
                ttk.Label(f, text=label,
                          font=("TkDefaultFont", 8, "bold")).pack()
                color = "#C00000" if "180" in label or "91" in label else "#333"
                ttk.Label(f, text=f"{count} stk  {formatting.fmt_amount(amount, dec)}",
                          foreground=color).pack()

    threading.Thread(target=_compute, daemon=True).start()


def show_subsequent_match_popup(page: Any) -> None:
    """Vis popup med matching av åpne poster mot etterfølgende periode."""
    from . import page as page_reskontro
    _make_popup = page_reskontro._make_popup
    _setup_tree = page_reskontro._setup_tree

    if not page._selected_nr or page._df is None or page._subsequent_df is None:
        return

    ub_val = 0.0
    if page._master_df is not None:
        row_m = page._master_df[page._master_df["nr"].astype(str) == page._selected_nr]
        if not row_m.empty:
            ub_val = float(row_m["ub"].iloc[0])

    open_invoices = _compute_open_items(
        page._df, nr=page._selected_nr, mode=page._mode, ub=ub_val)
    if open_invoices.empty:
        return

    result_df = _match_open_against_period(
        open_invoices, page._subsequent_df,
        nr=page._selected_nr, mode=page._mode)

    dec  = page._detail_decimals()
    navn = page._navn_for_nr(page._selected_nr)

    win = _make_popup(
        page,
        title=(f"Åpne poster vs {page._subsequent_label}  —  "
               f"{'Kunde' if page._mode == 'kunder' else 'Leverandør'} "
               f"{page._selected_nr}{' — ' + navn if navn else ''}"),
        geometry="1020x440",
    )

    if not result_df.empty:
        n_paid    = (result_df["Status"] == "✓ Betalt").sum()
        n_partial = (result_df["Status"] == "~ Delvis betalt").sum()
        n_open    = (result_df["Status"] == "✗ Fortsatt åpen").sum()
        sum_rest  = float(result_df["Resterende"].sum())
    else:
        n_paid = n_partial = n_open = 0
        sum_rest = 0.0

    n_all_open = len(open_invoices[open_invoices["Status"] == "✗ Åpen"])
    ttk.Label(
        win,
        text=(f"År N: {n_all_open} åpne fakturaer   |   "
              f"Matchet mot: {page._subsequent_label}   |   "
              f"✓ {n_paid} betalt   ~ {n_partial} delvis   ✗ {n_open} fortsatt åpen   |   "
              f"Resterende: {formatting.fmt_amount(sum_rest, dec)}"),
        font=("TkDefaultFont", 9, "bold"),
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 4))

    cols = ("Status", "Dato", "Bilag", "Tekst",
            "Gjenstår (år N)", "Betalt dato", "Betalt beløp", "Resterende")
    tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
    widths = {"Status": 130, "Dato": 90, "Bilag": 80, "Tekst": 240,
              "Gjenstår (år N)": 120, "Betalt dato": 90,
              "Betalt beløp": 120, "Resterende": 120}
    right_cols = {"Gjenstår (år N)", "Betalt beløp", "Resterende"}
    for c in cols:
        tree.heading(c, text=c, anchor="e" if c in right_cols else "w")
        tree.column(c, width=widths.get(c, 90),
                    anchor="e" if c in right_cols else "w",
                    stretch=c in ("Tekst",))
    tree.tag_configure("paid",    foreground="#1a7a2a")
    tree.tag_configure("partial", foreground="#8B4500")
    tree.tag_configure("open",    foreground="#C00000", background="#FFF0F0")
    tree.tag_configure(_TAG_HEADER, background="#E8EFF7",
                       font=("TkDefaultFont", 9, "bold"))
    _setup_tree(tree, extended=True)

    vsb = ttk.Scrollbar(win, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(win, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=1, column=0, sticky="nsew")
    vsb.grid(row=1, column=1, sticky="ns")
    hsb.grid(row=2, column=0, sticky="ew")
    win.rowconfigure(1, weight=1)
    win.columnconfigure(0, weight=1)

    status_tag_map = {
        "✓ Betalt":         "paid",
        "~ Delvis betalt":  "partial",
        "✗ Fortsatt åpen":  "open",
    }

    for _, row in result_df.iterrows():
        status      = str(row.get("Status", ""))
        dato        = str(row.get("Dato", ""))[:10]
        bilag       = str(row.get("Bilag", ""))
        tekst       = str(row.get("Tekst", ""))
        gjenstar_n  = row.get("Gjenstår (år N)")
        bet_dato    = str(row.get("Betalt dato", ""))[:10]
        bet_belop   = row.get("Betalt beløp")
        resterende  = row.get("Resterende")

        tree.insert("", "end", values=(
            status, dato, bilag, tekst,
            formatting.fmt_amount(gjenstar_n, dec) if gjenstar_n is not None else "",
            bet_dato,
            formatting.fmt_amount(bet_belop, dec) if bet_belop is not None else "",
            formatting.fmt_amount(resterende, dec) if resterende is not None else "",
        ), tags=(status_tag_map.get(status, ""),))

    btns = ttk.Frame(win)
    btns.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 6))
    ttk.Button(btns, text="Lukk", command=win.destroy).pack(side="right")
