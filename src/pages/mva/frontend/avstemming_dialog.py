"""MVA-avstemming-dialog: sammenlign hovedbok MVA mot Skatteetaten.

Klassisk revisjonformat med faner:
1. Avstemming — én pivottabell (HB utgående/inngående/netto vs innrapportert)
2. MVA per kode — detaljert pivot med avgift OG grunnlag per termin
3. Kontroller — automatiske sjekker med drilldown til bilagstransaksjoner

Åpnes fra Handlinger-menyen i Analyse-fanen.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    filedialog = None  # type: ignore

import formatting

log = logging.getLogger(__name__)

# Kolonner vi viser i drilldown-detaljer
_DRILL_COLS = ("Bilag", "Konto", "Kontonavn", "Dato", "Tekst", "Beløp", "MVA-kode", "MVA-beløp")


def open_mva_avstemming(parent: tk.Misc, page: Any) -> None:
    """Åpne MVA-avstemmingsdialog."""
    import pandas as pd
    from ..backend import avstemming as mva_avstemming
    import src.shared.regnskap.client_overrides as regnskap_client_overrides
    from page_analyse_mva import build_mva_pivot

    # Hent filtrert data
    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        if messagebox is not None:
            messagebox.showwarning("MVA-avstemming", "Ingen data å analysere.")
        return

    # Hent klient-info
    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
        year = getattr(_session, "year", None) or ""
    except Exception:
        client = ""
        year = ""

    # Bygg MVA-pivot fra filtrert data (med klient-mapping aktivert)
    mva_pivot = build_mva_pivot(df_filtered, client=str(client) or None)

    # Kjør kontroller
    kontroller = mva_avstemming.build_mva_kontroller(df_filtered)

    win = tk.Toplevel(parent)
    win.title("MVA-avstemming")
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("1150x750")

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)

    # ---- Header ----
    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 6))

    ttk.Label(
        header,
        text=f"MVA-avstemming  —  {client}  {year}",
        font=("TkDefaultFont", 11, "bold"),
    ).pack(side="left")

    import_info_var = tk.StringVar(value="")
    ttk.Label(header, textvariable=import_info_var, foreground="#666").pack(side="right")

    # ---- Font ----
    try:
        import tkinter.font as tkfont
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
    except Exception:
        bold = None

    # ---- Notebook med faner ----
    notebook = ttk.Notebook(outer)
    notebook.pack(fill="both", expand=True, pady=(0, 6))

    # =======================================================================
    # FANE 1: Avstemming
    # =======================================================================
    tab_avstemming = ttk.Frame(notebook, padding=4)
    notebook.add(tab_avstemming, text=" Avstemming ")

    # Forklaring
    ttk.Label(
        tab_avstemming,
        text="Sammenligning av netto MVA iflg. hovedbok mot innrapportert MVA iflg. Skatteetaten, per termin.",
        foreground="#666",
    ).pack(anchor="w", pady=(0, 4))

    cols = ("Post", "T1", "T2", "T3", "T4", "T5", "T6", "Sum")
    tree = ttk.Treeview(tab_avstemming, columns=cols, show="headings", height=12)
    tree.heading("Post", text="", anchor="w")
    tree.column("Post", width=240, anchor="w")
    for c in cols[1:]:
        tree.heading(c, text=c, anchor="e")
        tree.column(c, width=115, anchor="e")
    tree.pack(fill="both", expand=True)

    _configure_tags(tree, bold)

    # =======================================================================
    # FANE 2: MVA per kode (avgift + grunnlag)
    # =======================================================================
    tab_detail = ttk.Frame(notebook, padding=4)
    notebook.add(tab_detail, text=" MVA per kode ")

    ttk.Label(
        tab_detail,
        text="Beregnet avgift og grunnlag (bokført beløp) per MVA-kode per termin. Dobbeltklikk for transaksjoner.",
        foreground="#666",
    ).pack(anchor="w", pady=(0, 4))

    det_cols = (
        "MVA-kode", "Beskrivelse",
        "T1", "T2", "T3", "T4", "T5", "T6", "Sum",
        "G_T1", "G_T2", "G_T3", "G_T4", "G_T5", "G_T6", "G_Sum",
    )
    det_tree = ttk.Treeview(tab_detail, columns=det_cols, show="headings", height=12)
    det_tree.heading("MVA-kode", text="Kode", anchor="center")
    det_tree.column("MVA-kode", width=50, anchor="center")
    det_tree.heading("Beskrivelse", text="Beskrivelse", anchor="w")
    det_tree.column("Beskrivelse", width=170, anchor="w")

    for c in ["T1", "T2", "T3", "T4", "T5", "T6", "Sum"]:
        det_tree.heading(c, text=f"Avgift {c}", anchor="e")
        det_tree.column(c, width=85, anchor="e")
    for c in ["G_T1", "G_T2", "G_T3", "G_T4", "G_T5", "G_T6", "G_Sum"]:
        label = c.replace("G_", "Grl. ")
        det_tree.heading(c, text=label, anchor="e")
        det_tree.column(c, width=85, anchor="e")

    det_xscroll = ttk.Scrollbar(tab_detail, orient="horizontal", command=det_tree.xview)
    det_tree.configure(xscrollcommand=det_xscroll.set)
    det_tree.pack(fill="both", expand=True)
    det_xscroll.pack(fill="x")

    _configure_tags(det_tree, bold)

    # Dobbeltklikk på MVA-kode → drilldown
    def _on_det_dblclick(_event):
        sel = det_tree.selection()
        if not sel:
            return
        vals = det_tree.item(sel[0], "values")
        code = str(vals[0]).strip() if vals else ""
        if not code:
            return
        # Finn alle transaksjoner med denne MVA-koden
        mva_col = _find_col(df_filtered, ["MVA-kode", "mva-kode"])
        if not mva_col:
            return
        mask = df_filtered[mva_col].astype(str).str.strip() == code
        subset = df_filtered.loc[mask]
        _open_drilldown(win, f"Transaksjoner med MVA-kode {code}", subset, bold)

    det_tree.bind("<Double-1>", _on_det_dblclick)

    # =======================================================================
    # FANE 3: Kontroller
    # =======================================================================
    tab_kontroller = ttk.Frame(notebook, padding=4)
    notebook.add(tab_kontroller, text=" Kontroller ")

    ttk.Label(
        tab_kontroller,
        text="Automatiske kontroller. Dobbeltklikk på K2/K3-rader for å se bilagsdetaljer.",
        foreground="#666",
    ).pack(anchor="w", pady=(0, 4))

    # K-oppsummering
    k_summary_frame = ttk.LabelFrame(tab_kontroller, text="Kontroll-oppsummering", padding=6)
    k_summary_frame.pack(fill="x", pady=(0, 6))

    k_sum_cols = ("Kontroll", "Status", "Differanse", "Kommentar")
    k_sum_tree = ttk.Treeview(k_summary_frame, columns=k_sum_cols, show="headings", height=4)
    k_sum_tree.heading("Kontroll", text="Kontroll", anchor="w")
    k_sum_tree.column("Kontroll", width=280, anchor="w")
    k_sum_tree.heading("Status", text="Status", anchor="center")
    k_sum_tree.column("Status", width=60, anchor="center")
    k_sum_tree.heading("Differanse", text="Differanse", anchor="e")
    k_sum_tree.column("Differanse", width=110, anchor="e")
    k_sum_tree.heading("Kommentar", text="Kommentar", anchor="w")
    k_sum_tree.column("Kommentar", width=500, anchor="w")
    k_sum_tree.pack(fill="x")

    try:
        k_sum_tree.tag_configure("avvik", foreground="#C0392B", font=bold)
        k_sum_tree.tag_configure("merk", foreground="#E67E22", font=bold)
        k_sum_tree.tag_configure("ok", foreground="#27AE60")
    except Exception:
        try:
            k_sum_tree.tag_configure("avvik", foreground="#C0392B")
            k_sum_tree.tag_configure("merk", foreground="#E67E22")
            k_sum_tree.tag_configure("ok", foreground="#27AE60")
        except Exception:
            pass

    # K1: Salg vs grunnlag per termin
    k1_frame = ttk.LabelFrame(
        tab_kontroller,
        text="K1: Salgsinntekter (konto 3000-3999) vs grunnlag for utgående MVA-koder",
        padding=6,
    )
    k1_frame.pack(fill="x", pady=(0, 6))

    k1_cols = ("Termin", "Salgsinntekter (3xxx)", "Grunnlag utg. MVA", "Differanse")
    k1_tree = ttk.Treeview(k1_frame, columns=k1_cols, show="headings", height=8)
    for c in k1_cols:
        k1_tree.heading(c, text=c, anchor="e" if c != "Termin" else "center")
        k1_tree.column(c, width=160 if c != "Termin" else 70, anchor="e" if c != "Termin" else "center")
    k1_tree.pack(fill="x")
    _configure_tags(k1_tree, bold)

    # K2/K3 side-by-side med riktige kolonner og drilldown
    k_detail_frame = ttk.Frame(tab_kontroller)
    k_detail_frame.pack(fill="both", expand=True, pady=(0, 4))

    # -- K2 --
    k2_frame = ttk.LabelFrame(k_detail_frame, text="K2: Salgskontoer (3xxx) uten MVA-kode", padding=4)
    k2_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))

    k2_cols = ("Bilag", "Konto", "Kontonavn", "Dato", "Beløp", "Tekst")
    k2_tree = ttk.Treeview(k2_frame, columns=k2_cols, show="headings", height=6)
    k2_tree.heading("Bilag", text="Bilag", anchor="w")
    k2_tree.column("Bilag", width=60, anchor="w")
    k2_tree.heading("Konto", text="Konto", anchor="w")
    k2_tree.column("Konto", width=55, anchor="w")
    k2_tree.heading("Kontonavn", text="Kontonavn", anchor="w")
    k2_tree.column("Kontonavn", width=100, anchor="w")
    k2_tree.heading("Dato", text="Dato", anchor="center")
    k2_tree.column("Dato", width=80, anchor="center")
    k2_tree.heading("Beløp", text="Beløp", anchor="e")
    k2_tree.column("Beløp", width=90, anchor="e")
    k2_tree.heading("Tekst", text="Tekst", anchor="w")
    k2_tree.column("Tekst", width=120, anchor="w")
    k2_tree.pack(fill="both", expand=True)

    # -- K3 --
    k3_frame = ttk.LabelFrame(k_detail_frame, text="K3: Andre kontoer med utg. salgs-MVA", padding=4)
    k3_frame.pack(side="left", fill="both", expand=True)

    k3_cols = ("Bilag", "Konto", "Kontonavn", "MVA", "Dato", "Beløp", "Tekst")
    k3_tree = ttk.Treeview(k3_frame, columns=k3_cols, show="headings", height=6)
    k3_tree.heading("Bilag", text="Bilag", anchor="w")
    k3_tree.column("Bilag", width=60, anchor="w")
    k3_tree.heading("Konto", text="Konto", anchor="w")
    k3_tree.column("Konto", width=55, anchor="w")
    k3_tree.heading("Kontonavn", text="Kontonavn", anchor="w")
    k3_tree.column("Kontonavn", width=90, anchor="w")
    k3_tree.heading("MVA", text="MVA", anchor="center")
    k3_tree.column("MVA", width=40, anchor="center")
    k3_tree.heading("Dato", text="Dato", anchor="center")
    k3_tree.column("Dato", width=80, anchor="center")
    k3_tree.heading("Beløp", text="Beløp", anchor="e")
    k3_tree.column("Beløp", width=90, anchor="e")
    k3_tree.heading("Tekst", text="Tekst", anchor="w")
    k3_tree.column("Tekst", width=110, anchor="w")
    k3_tree.pack(fill="both", expand=True)

    # ---- State ----
    state: dict[str, Any] = {"skatt": None}

    def _compute_hb_values(pivot):
        """Beregn HB utgående/inngående/netto per termin fra pivot."""
        hb = {"utg": {}, "inn": {}, "netto": {}}
        if pivot is None or pivot.empty or "direction" not in pivot.columns:
            for t in range(1, 7):
                hb["utg"][t] = 0.0
                hb["inn"][t] = 0.0
                hb["netto"][t] = 0.0
            return hb

        utg_mask = pivot["direction"] == "utgående"
        inn_mask = pivot["direction"] == "inngående"

        for t in range(1, 7):
            col = f"T{t}"
            if col not in pivot.columns:
                hb["utg"][t] = 0.0
                hb["inn"][t] = 0.0
            else:
                hb["utg"][t] = abs(pivot.loc[utg_mask, col].sum())
                hb["inn"][t] = abs(pivot.loc[inn_mask, col].sum())
            hb["netto"][t] = hb["utg"][t] - hb["inn"][t]
        return hb

    def _fmt(val):
        return formatting.fmt_amount(val) if val else ""

    def _vals(label, data_dict):
        return (label,) + tuple(_fmt(data_dict.get(t, 0.0)) for t in range(1, 7)) + (
            _fmt(sum(data_dict.get(t, 0.0) for t in range(1, 7))),
        )

    def _refresh_main_tree():
        """Fyll avstemmingsfanen."""
        for item in tree.get_children():
            tree.delete(item)

        hb = _compute_hb_values(mva_pivot)
        skatt = state["skatt"]

        # Seksjon: Hovedbok
        tree.insert("", "end", values=("Iflg. hovedbok",) + ("",) * 7, tags=("section",))
        tree.insert("", "end", values=_vals("  Utgående MVA", hb["utg"]))
        tree.insert("", "end", values=_vals("  Inngående MVA", hb["inn"]))
        tree.insert("", "end", values=_vals("  Netto MVA", hb["netto"]), tags=("netto",))

        tree.insert("", "end", values=("",) * 8, tags=("blank",))

        # Seksjon: Skatteetaten
        tree.insert("", "end", values=("Iflg. Skatteetaten",) + ("",) * 7, tags=("section",))
        if skatt:
            innrapp = {t: skatt.mva_per_termin.get(t, 0.0) for t in range(1, 7)}
            tree.insert("", "end", values=_vals("  Innrapportert MVA", innrapp))
        else:
            tree.insert("", "end", values=("  (Importer kontoutskrift)",) + ("",) * 7)

        tree.insert("", "end", values=("",) * 8, tags=("blank",))

        # Differanse
        if skatt:
            diff = {}
            for t in range(1, 7):
                diff[t] = hb["netto"][t] - skatt.mva_per_termin.get(t, 0.0)
            has_avvik = any(abs(diff[t]) > 1.0 for t in range(1, 7))
            tag = "avvik" if has_avvik else "ok"
            tree.insert("", "end", values=_vals("Differanse", diff), tags=(tag,))
        else:
            tree.insert("", "end", values=("Differanse",) + ("—",) * 7)

    def _refresh_detail_tree():
        """Fyll MVA per kode-fanen med avgift OG grunnlag."""
        for item in det_tree.get_children():
            det_tree.delete(item)

        if mva_pivot is None or mva_pivot.empty:
            return

        for _, row in mva_pivot.iterrows():
            code = str(row.get("MVA-kode", ""))
            desc = str(row.get("Beskrivelse", ""))
            direction = str(row.get("direction", ""))

            avgift_vals = []
            for t in range(1, 7):
                val = row.get(f"T{t}", 0.0)
                avgift_vals.append(_fmt(val))
            avgift_vals.append(_fmt(row.get("Sum", 0.0)))

            grl_vals = []
            for t in range(1, 7):
                val = row.get(f"G_T{t}", 0.0)
                grl_vals.append(_fmt(val))
            grl_vals.append(_fmt(row.get("G_Sum", 0.0)))

            tags: tuple = ()
            if direction in ("_summary", "_netto"):
                tags = ("sumline",)

            det_tree.insert(
                "", "end",
                values=(code, desc, *avgift_vals, *grl_vals),
                tags=tags,
            )

    def _refresh_kontroller():
        """Fyll kontroller-fanen."""
        # K-oppsummering
        for item in k_sum_tree.get_children():
            k_sum_tree.delete(item)
        for s in kontroller.summary:
            tag = "avvik" if s["Status"] == "AVVIK" else ("merk" if s["Status"] == "MERK" else "ok")
            k_sum_tree.insert("", "end", values=(
                s["Kontroll"],
                s["Status"],
                _fmt(s.get("Differanse", 0)),
                s["Kommentar"],
            ), tags=(tag,))

        # K1: Salg vs grunnlag
        for item in k1_tree.get_children():
            k1_tree.delete(item)
        if not kontroller.salg_vs_grunnlag.empty:
            for _, row in kontroller.salg_vs_grunnlag.iterrows():
                termin = str(row.get("Termin", ""))
                diff = row.get("Differanse", 0)
                tag = "section" if termin == "Sum" else ("avvik" if abs(float(diff or 0)) > 1.0 else "")
                k1_tree.insert("", "end", values=(
                    termin,
                    _fmt(row.get("Salgsinntekter (3xxx)", 0)),
                    _fmt(row.get("Grunnlag utg. MVA", 0)),
                    _fmt(diff),
                ), tags=(tag,) if tag else ())

        # K2: Salgskontoer uten MVA — med alle relevante kolonner
        for item in k2_tree.get_children():
            k2_tree.delete(item)
        if not kontroller.salg_uten_mva.empty:
            _fill_kontroll_tree(k2_tree, kontroller.salg_uten_mva, k2_cols)
        else:
            k2_tree.insert("", "end", values=("", "Ingen", "funn", "", "", ""))

        # K3: Andre kontoer med utg. MVA
        for item in k3_tree.get_children():
            k3_tree.delete(item)
        if not kontroller.andre_med_utg_mva.empty:
            _fill_kontroll_tree(k3_tree, kontroller.andre_med_utg_mva, k3_cols)
        else:
            k3_tree.insert("", "end", values=("", "Ingen", "funn", "", "", "", ""))

    # Drilldown ved dobbeltklikk på K2/K3
    def _on_k2_dblclick(_event):
        _drilldown_from_tree(k2_tree, kontroller.salg_uten_mva, "K2: Salgstransaksjoner uten MVA-kode")

    def _on_k3_dblclick(_event):
        _drilldown_from_tree(k3_tree, kontroller.andre_med_utg_mva, "K3: Andre kontoer med utgående salgs-MVA")

    def _drilldown_from_tree(src_tree, src_df, title):
        """Åpne drilldown for valgt rad — vis hele bilaget."""
        sel = src_tree.selection()
        if not sel or src_df is None or src_df.empty:
            return
        # Finn rad-indeks i source df
        idx = src_tree.index(sel[0])
        if idx >= len(src_df):
            return
        row = src_df.iloc[idx]
        bilag = row.get("Bilag", "")
        konto = str(row.get("Konto", row.iloc[0] if len(row) > 0 else ""))

        # Finn alle transaksjoner med samme bilag
        if bilag and "Bilag" in df_filtered.columns:
            mask = df_filtered["Bilag"].astype(str) == str(bilag)
            subset = df_filtered.loc[mask]
            drill_title = f"{title}  —  Bilag {bilag}"
        else:
            # Fallback: vis alle transaksjoner for denne kontoen
            mask = df_filtered["Konto"].astype(str) == konto
            subset = df_filtered.loc[mask]
            drill_title = f"{title}  —  Konto {konto}"

        _open_drilldown(win, drill_title, subset, bold)

    k2_tree.bind("<Double-1>", _on_k2_dblclick)
    k3_tree.bind("<Double-1>", _on_k3_dblclick)

    def _import_file():
        path = filedialog.askopenfilename(
            parent=win,
            title="Velg Skatteetatens kontoutskrift",
            filetypes=[
                ("Excel-filer", "*.xlsx *.xls"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        try:
            data = mva_avstemming.parse_skatteetaten_kontoutskrift(
                path, year=year if year else None
            )
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror("MVA-avstemming", f"Feil ved lesing:\n{exc}")
            return

        state["skatt"] = data

        if client:
            try:
                regnskap_client_overrides.save_kontoutskrift_path(client, path)
            except Exception:
                log.debug("Kunne ikke lagre kontoutskrift-sti")

        label = (
            f"Kontoutskrift: {data.company} ({data.org_nr})"
            if data.org_nr
            else f"Importert: {Path(path).name}"
        )
        import_info_var.set(label)
        _refresh_main_tree()

    def _try_load_saved():
        """Forsøk å laste tidligere lagret kontoutskrift."""
        if not client:
            return
        saved_path = regnskap_client_overrides.load_kontoutskrift_path(client)
        if not saved_path or not Path(saved_path).exists():
            return
        try:
            data = mva_avstemming.parse_skatteetaten_kontoutskrift(
                saved_path, year=year if year else None
            )
            state["skatt"] = data
            label = (
                f"Kontoutskrift: {data.company} ({data.org_nr})"
                if data.org_nr
                else f"Lagret: {Path(saved_path).name}"
            )
            import_info_var.set(label)
        except Exception:
            log.debug("Kunne ikke laste lagret kontoutskrift: %s", saved_path)

    def _export():
        if mva_pivot is None or mva_pivot.empty:
            if messagebox is not None:
                messagebox.showinfo("MVA-avstemming", "Ingen data å eksportere.")
            return

        recon = None
        if state["skatt"]:
            recon = mva_avstemming.build_reconciliation(mva_pivot, state["skatt"])

        export_path = filedialog.asksaveasfilename(
            parent=win,
            title="Lagre MVA-avstemming",
            defaultextension=".xlsx",
            filetypes=[("Excel-filer", "*.xlsx")],
            initialfile=f"MVA-avstemming {client} {year}.xlsx",
        )
        if not export_path:
            return

        try:
            from ..backend import avstemming_excel as mva_avstemming_excel
            mva_avstemming_excel.write_mva_avstemming_excel(
                export_path,
                mva_pivot=mva_pivot,
                reconciliation=recon,
                kontroller=kontroller,
                client=client,
                year=year,
                skatteetaten=state.get("skatt"),
            )
            if messagebox is not None:
                messagebox.showinfo("MVA-avstemming", f"Eksportert til:\n{export_path}")
        except Exception as exc:
            log.exception("Excel-eksport feilet")
            if messagebox is not None:
                messagebox.showerror("MVA-avstemming", f"Eksport feilet:\n{exc}")

    # ---- Knapperekke ----
    bottom = ttk.Frame(outer)
    bottom.pack(fill="x")

    ttk.Button(bottom, text="Importer kontoutskrift…", command=_import_file).pack(side="left", padx=(0, 8))
    ttk.Button(bottom, text="Eksporter til Excel…", command=_export).pack(side="left")
    ttk.Button(bottom, text="Lukk", command=win.destroy).pack(side="right")

    # ---- Initialiser ----
    _try_load_saved()
    _refresh_main_tree()
    _refresh_detail_tree()
    _refresh_kontroller()

    win.wait_window()


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _fill_kontroll_tree(tree: ttk.Treeview, df, col_ids: tuple, max_rows: int = 300) -> None:
    """Fyll en kontroll-treeview med data fra DataFrame, mapper kolonner intelligent."""
    import pandas as pd

    for i, (_, row) in enumerate(df.iterrows()):
        if i >= max_rows:
            overflow = ("", f"… +{len(df) - max_rows} rader") + ("",) * (len(col_ids) - 2)
            tree.insert("", "end", values=overflow)
            break

        vals = []
        for col_id in col_ids:
            # Finn matchende kolonne i DataFrame
            val = _get_row_val(row, col_id, df.columns)
            if col_id == "Beløp":
                val = formatting.fmt_amount(val)
            elif col_id == "Dato":
                val = str(val)[:10] if val else ""
            else:
                val = str(val) if val and str(val) not in ("nan", "None", "NaT") else ""
            vals.append(val)
        tree.insert("", "end", values=tuple(vals))


def _get_row_val(row, col_id: str, columns):
    """Hent verdi fra en rad, prøver ulike kolonnenavn."""
    # Direkte match
    if col_id in row.index:
        return row[col_id]
    # Case-insensitive
    lower_map = {str(c).lower(): c for c in columns}
    actual = lower_map.get(col_id.lower())
    if actual and actual in row.index:
        return row[actual]
    # Alias
    aliases = {
        "MVA": ["MVA-kode", "mva-kode"],
        "Beløp": ["Beløp", "beløp", "Belop"],
    }
    for alias in aliases.get(col_id, []):
        if alias in row.index:
            return row[alias]
    return ""


def _open_drilldown(parent, title: str, df, bold=None) -> None:
    """Åpne et drilldown-vindu som viser bilagstransaksjoner."""
    import pandas as pd

    if df is None or df.empty:
        return

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.resizable(True, True)
    win.geometry("1000x450")

    frame = ttk.Frame(win, padding=8)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 4))
    ttk.Label(frame, text=f"{len(df)} transaksjoner", foreground="#666").pack(anchor="w", pady=(0, 4))

    # Velg kolonner å vise (de som finnes i data)
    show_cols = [c for c in _DRILL_COLS if c in df.columns]
    if not show_cols:
        show_cols = list(df.columns[:8])

    tree = ttk.Treeview(frame, columns=show_cols, show="headings", height=15)
    for c in show_cols:
        tree.heading(c, text=c, anchor="w" if c not in ("Beløp", "MVA-beløp") else "e")
        w = 70
        if c in ("Tekst", "Kontonavn"):
            w = 180
        elif c in ("Beløp", "MVA-beløp"):
            w = 100
        elif c == "Dato":
            w = 85
        elif c in ("Bilag", "Konto", "MVA-kode"):
            w = 65
        tree.column(c, width=w, anchor="w" if c not in ("Beløp", "MVA-beløp") else "e")
    tree.pack(fill="both", expand=True)

    yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    # Plasser scrollbar ved siden av tree
    tree.pack_forget()
    tree.pack(side="left", fill="both", expand=True)
    yscroll.pack(side="right", fill="y")

    # Fyll med data (maks 500 rader)
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= 500:
            tree.insert("", "end", values=(f"… +{len(df) - 500} rader",) + ("",) * (len(show_cols) - 1))
            break
        vals = []
        for c in show_cols:
            val = row.get(c, "")
            if c in ("Beløp", "MVA-beløp"):
                val = formatting.fmt_amount(val)
            elif c == "Dato":
                val = str(val)[:10] if val else ""
            else:
                val = str(val) if val and str(val) not in ("nan", "None", "NaT") else ""
            vals.append(val)
        tree.insert("", "end", values=tuple(vals))

    # Sum-linje i bunnen
    belop_col = "Beløp" if "Beløp" in df.columns else None
    if belop_col:
        total = pd.to_numeric(df[belop_col], errors="coerce").sum()
        ttk.Label(
            frame,
            text=f"Sum beløp: {formatting.fmt_amount(total)}",
            font=("TkDefaultFont", 9, "bold") if bold else ("TkDefaultFont", 9),
        ).pack(anchor="e", pady=(4, 0))

    ttk.Button(win, text="Lukk", command=win.destroy).pack(side="right", padx=8, pady=6)


def _find_col(df, candidates: list[str]) -> str:
    """Finn første matchende kolonnenavn."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        actual = lower_map.get(cand.lower())
        if actual:
            return actual
    return ""


def _configure_tags(tree, bold=None):
    """Sett standard tags for et Treeview."""
    try:
        if bold:
            tree.tag_configure("section", font=bold, background="#EDF1F5")
            tree.tag_configure("netto", font=bold)
            tree.tag_configure("sumline", font=bold, background="#EDF1F5")
            tree.tag_configure("avvik", foreground="#C0392B", font=bold)
        else:
            tree.tag_configure("section", background="#EDF1F5")
            tree.tag_configure("netto", background="#F5F5F5")
            tree.tag_configure("sumline", background="#EDF1F5")
            tree.tag_configure("avvik", foreground="#C0392B")
        tree.tag_configure("ok", foreground="#27AE60")
        tree.tag_configure("blank", background="#FFFFFF")
    except Exception:
        pass
