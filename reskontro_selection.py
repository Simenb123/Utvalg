"""reskontro_selection.py — Seleksjon, filtrering og populering av trær.

Modulfunksjoner som tar `page` (ReskontroPage) som første argument.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import pandas as pd

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None  # type: ignore

import formatting
from reskontro_brreg_helpers import _brreg_has_risk, _brreg_status_text
from reskontro_open_items import (
    _compute_open_items_with_confidence,
    _match_open_against_period,
)
from reskontro_tree_helpers import (
    _DETAIL_COLS,
    _LOWER_VIEW_BETALT,
    _LOWER_VIEW_BRREG,
    _LOWER_VIEW_NESTE,
    _TAG_BRREG_WARN,
    _TAG_HEADER,
    _TAG_MVA_FRADRAG,
    _TAG_MVA_LINE,
    _TAG_MVA_WARN,
    _TAG_NEG,
    _TAG_ZERO,
    _UPPER_VIEW_APNE,
    _build_detail,
    _build_master,
    _has_reskontro_data,
)

log = logging.getLogger(__name__)


def on_decimals_toggle(page) -> None:
    """Re-render master og detail med ny desimal-innstilling."""
    page._apply_filter()
    if page._selected_nr:
        page._refresh_upper_panel()
        page._refresh_lower_panel()


def on_mode_change(page) -> None:
    page._mode = page._mode_var.get()
    page._selected_nr = ""
    page._detail_tree.delete(*page._detail_tree.get_children())
    page._open_items_tree.delete(*page._open_items_tree.get_children())
    page._subseq_tree.delete(*page._subseq_tree.get_children())
    page._payments_tree.delete(*page._payments_tree.get_children())
    page._detail_lbl.configure(text="Velg en post for å se transaksjoner")
    page._clear_brreg_panel()
    page._refresh_all()


def refresh_all(page) -> None:
    page._detail_tree.delete(*page._detail_tree.get_children())
    page._open_items_tree.delete(*page._open_items_tree.get_children())
    page._subseq_tree.delete(*page._subseq_tree.get_children())
    page._payments_tree.delete(*page._payments_tree.get_children())
    page._detail_lbl.configure(text="Velg en post for å se transaksjoner")
    page._clear_brreg_panel()
    try:
        page._refresh_lower_panel()
    except Exception:
        pass

    if not _has_reskontro_data(page._df):
        page._master_tree.delete(*page._master_tree.get_children())
        page._status_lbl.configure(
            text="Ingen kunde-/leverandørdata. "
                 "Last inn en SAF-T-fil (zip/xml).")
        return

    import session as _session
    year_str = getattr(_session, "year", None)
    year = int(year_str) if year_str else None
    page._master_df = _build_master(page._df, mode=page._mode, year=year)

    # Bygg orgnr-kart
    if "orgnr" in page._master_df.columns:
        page._orgnr_map = {
            str(r["nr"]): str(r["orgnr"])
            for _, r in page._master_df.iterrows()
            if str(r.get("orgnr", "")).strip()
        }
    else:
        page._orgnr_map = {}

    page._apply_filter()


def apply_filter(page) -> None:
    if page._master_df is None:
        return
    q = (page._filter_var.get().strip().lower()
         if page._filter_var else "")
    hide_zero = bool(getattr(page, "_hide_zero_var", None)
                     and page._hide_zero_var.get())
    dec = page._master_decimals()

    tree = page._master_tree
    # Bevar scroll-posisjon og valgt rad ved filter-refresh
    _prev_sel  = tree.selection()
    _prev_yview = tree.yview()[0] if tree.get_children() else 0.0
    tree.delete(*tree.get_children())

    shown = 0
    n_mva_warn_shown  = 0
    n_mva_fradrag     = 0
    sum_ib = sum_bev = sum_ub = 0.0

    for _, row in page._master_df.iterrows():
        nr   = str(row["nr"])
        navn = str(row["navn"])
        ant  = int(row["antall"])
        ib   = float(row["ib"])
        bev  = float(row["bev"])
        ub   = float(row["ub"])

        # orgnr må hentes FØR søke-filteret (brukes i søket)
        orgnr = page._orgnr_map.get(nr, "")

        if q and q not in nr.lower() and q not in navn.lower() \
                and q not in orgnr.lower():
            continue

        # Skjul poster der alt er 0
        if hide_zero and abs(ib) < 0.01 and abs(bev) < 0.01 and abs(ub) < 0.01:
            continue

        # --- MVA: SAF-T er primærkilde, BRREG er override ---
        saft_mva  = bool(row.get("saft_mva_reg", False))
        has_mva_tx = bool(row.get("has_mva_tx", False))
        brec      = page._brreg_data.get(orgnr, {}) if orgnr else {}
        enhet     = brec.get("enhet") or {} if brec else {}

        if enhet:
            mva_reg     = enhet.get("registrertIMvaregisteret", False)
            mva_txt     = "\u2713 BRREG" if mva_reg else "\u2717 BRREG"
            status_txt  = _brreg_status_text(enhet)
            nk  = enhet.get("naeringskode", "")
            nn  = enhet.get("naeringsnavn", "")
            bransje_txt = (f"{nk} {nn}".strip() if nk else nn)[:40]
        elif saft_mva:
            mva_txt     = "\u2713 SAF-T"
            status_txt  = ""
            bransje_txt = ""
            mva_reg     = True
        else:
            mva_txt     = ""
            status_txt  = ""
            bransje_txt = ""
            mva_reg     = None

        tags: list[str] = []
        if enhet and _brreg_has_risk(enhet):
            tags.append(_TAG_BRREG_WARN)
        elif (mva_reg is False and page._mode == "leverandorer"
              and has_mva_tx):
            # Leverandør ikke MVA-reg., men det er ført MVA-fradrag
            tags.append(_TAG_MVA_FRADRAG)
            n_mva_fradrag += 1
        elif mva_reg is False and abs(ub) > 0.01:
            tags.append(_TAG_MVA_WARN)
            n_mva_warn_shown += 1

        if not tags:
            if abs(ub) < 0.01:
                tags.append(_TAG_ZERO)
            elif ub < 0:
                tags.append(_TAG_NEG)

        orgnr_disp = orgnr if orgnr else ""
        konto_disp = str(row.get("konto", "")) if "konto" in page._master_df.columns else ""
        tree.insert("", "end", iid=nr,
                    values=(
                        nr, navn, orgnr_disp, konto_disp, ant,
                        formatting.fmt_amount(ib,  dec),
                        formatting.fmt_amount(bev, dec),
                        formatting.fmt_amount(ub,  dec),
                        mva_txt, status_txt, bransje_txt,
                    ),
                    tags=tuple(tags))
        shown += 1
        sum_ib  += ib
        sum_bev += bev
        sum_ub  += ub

    # --- Sum-rad ---
    sum_txt = (
        f"IB {formatting.fmt_amount(sum_ib, dec)}"
        f"   Bev. {formatting.fmt_amount(sum_bev, dec)}"
        f"   UB {formatting.fmt_amount(sum_ub, dec)}"
    )
    if hasattr(page, "_sum_lbl"):
        page._sum_lbl.configure(text=sum_txt)

    # --- Avstemming: bevegelse i reskontro vs. konto-bevegelse i full df ---
    if hasattr(page, "_recon_lbl"):
        recon_txt = ""
        try:
            konto = ""
            if page._master_df is not None and "konto" in page._master_df.columns:
                kontoes = (page._master_df["konto"]
                           .replace("", None).dropna().unique())
                if len(kontoes) == 1:
                    konto = str(kontoes[0])
            if konto and page._df is not None and "Konto" in page._df.columns:
                konto_bev = pd.to_numeric(
                    page._df.loc[
                        page._df["Konto"].astype(str).str.strip() == konto,
                        "Beløp"
                    ], errors="coerce"
                ).sum()
                avvik = sum_bev - konto_bev
                recon_txt = (
                    f"Konto {konto}: "
                    f"Bev. RS={formatting.fmt_amount(sum_bev, dec)}, "
                    f"Konto={formatting.fmt_amount(konto_bev, dec)}, "
                    f"Avvik={formatting.fmt_amount(avvik, dec)}"
                    + ("  \u2713" if abs(avvik) < 0.01 else "  \u26a0")
                )
        except Exception:
            pass
        page._recon_lbl.configure(text=recon_txt)

    # --- Statuslinje ---
    mode_label = "kunder" if page._mode == "kunder" else "leverandører"
    q_suffix   = f"  (filter: '{page._filter_var.get().strip()}')" if q else ""
    n_brreg    = len(page._brreg_data)
    parts      = [f"{shown} {mode_label}"]
    if n_brreg:
        parts.append(f"{n_brreg} BRREG-sjekket")
    if n_mva_fradrag:
        parts.append(f"\u26a0 {n_mva_fradrag} MVA-fradrag uten reg.")
    if n_mva_warn_shown:
        parts.append(f"\u2717 {n_mva_warn_shown} ikke MVA-reg.")
    page._status_lbl.configure(
        text=("  \u2022  ".join(parts)) + q_suffix)

    # Gjenopprett scroll-posisjon og valgt rad etter filter-refresh
    if _prev_yview > 0:
        page.after(0, lambda y=_prev_yview: tree.yview_moveto(y))
    if _prev_sel:
        still_there = [s for s in _prev_sel if tree.exists(s)]
        if still_there:
            tree.selection_set(still_there)
            tree.see(still_there[0])


def on_master_select(page, _event: Any = None) -> None:
    sel = page._master_tree.selection()
    if not sel:
        return
    page._selected_nr = sel[0]
    page._refresh_upper_panel()
    orgnr = page._orgnr_map.get(page._selected_nr, "")
    # BRREG: hent automatisk hvis ikke cachet
    if (page._lower_view_var.get() == _LOWER_VIEW_BRREG
            and orgnr and orgnr not in page._brreg_data):
        page._auto_fetch_brreg_single(orgnr)
    else:
        page._refresh_lower_panel()


def auto_fetch_brreg_single(page, orgnr: str) -> None:
    """Hent BRREG-data for ett enkelt orgnr i bakgrunn og oppdater panelet."""
    if not orgnr or len(orgnr) != 9 or not orgnr.isdigit():
        page._update_brreg_panel(orgnr)
        return
    page._brreg_write(("Henter BRREG-data\u2026", "dim"))

    def _run() -> None:
        try:
            import brreg_client as _brreg
            enhet = _brreg.fetch_enhet(orgnr)
            regnskap = _brreg.fetch_regnskap(orgnr)
            result = {"enhet": enhet, "regnskap": regnskap}
            page.after(0, lambda: page._on_single_brreg_done(orgnr, result))
        except Exception as exc:
            log.warning("Auto BRREG-henting feilet for %s: %s", orgnr, exc)
            page.after(0, lambda: page._update_brreg_panel(orgnr))

    threading.Thread(target=_run, daemon=True).start()


def on_single_brreg_done(page, orgnr: str, result: dict) -> None:
    """Kalles når enkelt BRREG-henting er ferdig."""
    page._brreg_data[orgnr] = result
    if page._lower_view_var.get() == _LOWER_VIEW_BRREG:
        page._update_brreg_panel(orgnr)
    # Oppdater master-treet for å vise MVA/status/bransje
    page._apply_filter()


def on_detail_select(page, _event: Any = None) -> None:
    """Oppdater statuslinje med antall markerte rader og sum beløp."""
    sel = page._detail_tree.selection()
    n = len(sel)
    if n <= 1:
        return  # Statuslinja settes av andre metoder ved enkeltvalg
    # Beregn sum av Beløp-kolonnen for markerte rader
    belop_idx = list(_DETAIL_COLS).index("Beløp") if "Beløp" in _DETAIL_COLS else -1
    total = 0.0
    if belop_idx >= 0:
        for iid in sel:
            vals = page._detail_tree.item(iid, "values")
            if vals and belop_idx < len(vals):
                try:
                    raw = str(vals[belop_idx]).replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace(",", ".")
                    total += float(raw)
                except (ValueError, TypeError):
                    pass
    dec = page._detail_decimals()
    page._status_lbl.configure(
        text=f"Markert: {n} rader  |  Beløp: {formatting.fmt_amount(total, dec)}")


def on_detail_right_click(page, event: Any) -> None:
    """Høyreklikk-kontekstmeny på detaljrader."""
    tree = page._detail_tree
    iid = tree.identify_row(event.y)
    if iid and iid not in tree.selection():
        tree.selection_set(iid)
        tree.focus(iid)
    sel = tree.selection()
    if not sel:
        return

    vals = tree.item(sel[0], "values")
    bilag = str(vals[1]).strip() if len(vals) > 1 else ""

    menu = tk.Menu(tree, tearoff=0)
    if bilag:
        menu.add_command(
            label=f"Åpne bilag {bilag}  (alle HB-linjer)",
            command=lambda b=bilag: page._open_bilag_popup(b))
        menu.add_separator()
    menu.add_command(
        label=f"Kopier {'rad' if len(sel) == 1 else str(len(sel)) + ' rader'}  (Ctrl+C)",
        command=lambda: tree.event_generate("<Control-c>"))
    menu.add_command(
        label="Velg alle  (Ctrl+A)",
        command=lambda: tree.selection_set(tree.get_children("")))
    menu.add_separator()
    menu.add_command(
        label="Åpne poster for valgt kunde/leverandør",
        command=page._show_open_items_popup)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def populate_detail(page, nr: str) -> None:
    """Flat transaksjonsliste (Ã©n rad per transaksjon) for valgt nr."""
    tree = page._detail_tree
    tree.delete(*tree.get_children())

    if page._df is None:
        return

    sub = _build_detail(page._df, nr=nr, mode=page._mode)
    if sub.empty:
        page._update_detail_header(nr, n_tx=0, total=0.0)
        return

    def _v_any(col: str, row: Any, default: Any = "") -> Any:
        try:
            val = row[col]
            if val is None or (isinstance(val, float) and str(val) == "nan"):
                return default
            return val
        except (KeyError, IndexError):
            return default

    total = 0.0
    debet = 0.0
    kredit = 0.0
    dec = page._detail_decimals()
    for _, row in sub.iterrows():
        dato      = str(_v_any("Dato",      row, ""))[:10]
        bilag     = str(_v_any("Bilag",     row, ""))
        konto     = str(_v_any("Konto",     row, ""))
        knavn     = str(_v_any("Kontonavn", row, ""))
        tekst     = str(_v_any("Tekst",     row, ""))
        ref       = str(_v_any("Referanse", row, ""))
        valuta    = str(_v_any("Valuta",    row, ""))
        mva_kode  = str(_v_any("MVA-kode",  row, ""))
        if mva_kode in ("nan", "None"):
            mva_kode = ""
        try:
            belop = float(_v_any("Beløp", row, 0.0))
        except (ValueError, TypeError):
            belop = 0.0
        try:
            mva_belop_raw = _v_any("MVA-beløp", row, None)
            mva_belop = float(mva_belop_raw) if mva_belop_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            mva_belop = None

        total += belop
        if belop >= 0:
            debet += belop
        else:
            kredit += belop

        has_mva = bool(mva_kode or (mva_belop is not None and abs(mva_belop) > 0.001))
        tags: list[str] = []
        if belop < 0:
            tags.append(_TAG_NEG)
        if has_mva:
            tags.append(_TAG_MVA_LINE)

        tree.insert("", "end", values=(
            dato, bilag, konto, knavn, tekst,
            formatting.fmt_amount(belop, dec),
            mva_kode,
            formatting.fmt_amount(mva_belop, dec) if mva_belop is not None else "",
            ref, valuta,
        ), tags=tuple(tags))

    tree.insert("", "end", values=(
        "", "", "", "",
        (f"\u03a3 {len(sub)} trans.  "
         f"D: {formatting.fmt_amount(debet, dec)}  "
         f"K: {formatting.fmt_amount(kredit, dec)}"),
        formatting.fmt_amount(total, dec),
        "", "", "", "",
    ), tags=(_TAG_HEADER,))

    page._update_detail_header(nr, n_tx=len(sub), total=total)
    page._status_lbl.configure(
        text=(f"Markert: 1 rad  |  Beløp: {formatting.fmt_amount(total, dec)}"
              f"  \u2022  D: {formatting.fmt_amount(debet, dec)}"
              f"  K: {formatting.fmt_amount(kredit, dec)}"))


def update_detail_header(page, nr: str, *, n_tx: int, total: float) -> None:
    navn = page._navn_for_nr(nr)
    mode_str = "Kunde" if page._mode == "kunder" else "Leverandør"
    lbl = f"{mode_str} {nr}"
    if navn:
        lbl += f"  \u2014  {navn}"
    ub_display = total
    if page._master_df is not None:
        row_m = page._master_df[page._master_df["nr"].astype(str) == nr]
        if not row_m.empty:
            ub_display = float(row_m["ub"].iloc[0])
    lbl += f"  ({n_tx} transaksjoner, UB {formatting.fmt_amount(ub_display)})"
    page._detail_lbl.configure(text=lbl)


def on_upper_view_change(page) -> None:
    view = page._upper_view_var.get()
    if view == _UPPER_VIEW_APNE:
        page._detail_tree_frame.grid_remove()
        page._open_items_frame.grid(row=0, column=0, sticky="nsew")
    else:
        page._open_items_frame.grid_remove()
        page._detail_tree_frame.grid(row=0, column=0, sticky="nsew")
    page._refresh_upper_panel()


def on_lower_view_change(page) -> None:
    page._refresh_lower_panel()


def refresh_upper_panel(page) -> None:
    """Render innhold i øvre høyrepanel basert på valgt visning."""
    view = page._upper_view_var.get()
    nr = page._selected_nr
    if view == _UPPER_VIEW_APNE:
        page._populate_open_items_inline(nr)
    else:
        if nr:
            page._populate_detail(nr)
        else:
            page._detail_tree.delete(*page._detail_tree.get_children())
            page._detail_lbl.configure(
                text="Velg en post for å se transaksjoner")


def refresh_lower_panel(page) -> None:
    """Render innhold i nedre høyrepanel basert på valgt visning."""
    view = page._lower_view_var.get()

    # Skjul alle, vis valgt
    for fr in (page._brreg_frame, page._subseq_frame, page._payments_frame):
        try:
            fr.grid_remove()
        except Exception:
            pass

    # Kontekstuell "Last inn etterfølgende periode…"-knapp
    need_subseq = view in (_LOWER_VIEW_NESTE, _LOWER_VIEW_BETALT)
    has_subseq = page._subsequent_df is not None and not page._subsequent_df.empty
    try:
        if need_subseq and not has_subseq:
            page._load_subseq_btn.grid(
                row=0, column=3, sticky="e", padx=(6, 0))
        else:
            page._load_subseq_btn.grid_remove()
    except Exception:
        pass

    if view == _LOWER_VIEW_BRREG:
        page._brreg_frame.grid(row=0, column=0, sticky="nsew")
        orgnr = page._orgnr_map.get(page._selected_nr, "") if page._selected_nr else ""
        page._update_brreg_panel(orgnr)
    elif view == _LOWER_VIEW_NESTE:
        page._subseq_frame.grid(row=0, column=0, sticky="nsew")
        page._populate_subseq_tree(page._selected_nr)
    elif view == _LOWER_VIEW_BETALT:
        page._payments_frame.grid(row=0, column=0, sticky="nsew")
        page._populate_payments_tree(page._selected_nr)


def populate_open_items_inline(page, nr: str) -> None:
    """Render åpne poster for valgt nr direkte i øvre tree."""
    tree = page._open_items_tree
    tree.delete(*tree.get_children())

    if not nr:
        page._detail_lbl.configure(
            text="Velg en post for å se åpne poster")
        return
    if page._df is None or page._master_df is None:
        return

    ub = 0.0
    ib = 0.0
    row_m = page._master_df[page._master_df["nr"].astype(str) == nr]
    if not row_m.empty:
        ub = float(row_m["ub"].iloc[0])
        ib = float(row_m["ib"].iloc[0])

    result_df, conf = _compute_open_items_with_confidence(
        page._df, nr=nr, mode=page._mode, ub=ub, ib=ib)

    dec = page._detail_decimals()
    n_open = 0
    sum_open = 0.0
    for _, r in result_df.iterrows():
        status = str(r.get("Status", ""))
        dato   = str(r.get("Dato", ""))[:10]
        bilag  = str(r.get("Bilag", ""))
        fnr    = str(r.get("FakturaNr", "") or "")
        tekst  = str(r.get("Tekst", ""))
        try:
            fakt   = float(r.get("Fakturabeløp", 0) or 0)
            betalt = float(r.get("Betalt (i år)", 0) or 0)
            gjen   = float(r.get("Gjenstår", 0) or 0)
        except (ValueError, TypeError):
            fakt = betalt = gjen = 0.0

        tags: list[str] = []
        if gjen < 0:
            tags.append(_TAG_NEG)

        tree.insert("", "end", values=(
            status, dato, bilag, fnr, tekst,
            formatting.fmt_amount(fakt, dec),
            formatting.fmt_amount(betalt, dec),
            formatting.fmt_amount(gjen, dec),
        ), tags=tuple(tags))

        if "\u00c5pen" in status or "Delvis" in status:
            n_open += 1
            sum_open += gjen

    tree.insert("", "end", values=(
        "", "", "", "", f"\u03a3 {n_open} åpne",
        "", "", formatting.fmt_amount(sum_open, dec),
    ), tags=(_TAG_HEADER,))

    navn = page._navn_for_nr(nr)
    mode_str = "Kunde" if page._mode == "kunder" else "Leverandør"
    lbl = f"{mode_str} {nr}"
    if navn:
        lbl += f"  \u2014  {navn}"
    lbl += (f"  ({len(result_df)} linjer, {n_open} åpne, "
            f"UB {formatting.fmt_amount(ub)})")
    if conf:
        lbl += f"  — tillit: {conf.get('level', '')}"
    page._detail_lbl.configure(text=lbl)


def populate_subseq_tree(page, nr: str) -> None:
    """Render transaksjoner for valgt nr i etterfølgende periode."""
    tree = page._subseq_tree
    tree.delete(*tree.get_children())

    if page._subsequent_df is None or page._subsequent_df.empty:
        page._subseq_empty_lbl.configure(
            text="Ingen etterfølgende periode er lastet.")
        return
    if not nr:
        page._subseq_empty_lbl.configure(
            text="Velg en post til venstre for å se transaksjoner i "
                 f"etterfølgende periode ({page._subsequent_label}).")
        return

    sub = _build_detail(page._subsequent_df, nr=nr, mode=page._mode)
    if sub.empty:
        page._subseq_empty_lbl.configure(
            text=(f"Ingen transaksjoner for {nr} i etterfølgende "
                  f"periode ({page._subsequent_label})."))
        return
    page._subseq_empty_lbl.configure(
        text=f"Etterfølgende periode: {page._subsequent_label}  "
             f"({len(sub)} transaksjoner)")

    def _v(col: str, row: Any, default: Any = "") -> Any:
        try:
            val = row[col]
            if val is None or (isinstance(val, float) and str(val) == "nan"):
                return default
            return val
        except (KeyError, IndexError):
            return default

    dec = page._detail_decimals()
    total = 0.0
    for _, row in sub.iterrows():
        dato  = str(_v("Dato",      row, ""))[:10]
        bilag = str(_v("Bilag",     row, ""))
        konto = str(_v("Konto",     row, ""))
        knavn = str(_v("Kontonavn", row, ""))
        tekst = str(_v("Tekst",     row, ""))
        ref   = str(_v("Referanse", row, ""))
        mva_kode = str(_v("MVA-kode", row, ""))
        if mva_kode in ("nan", "None"):
            mva_kode = ""
        try:
            belop = float(_v("Beløp", row, 0.0))
        except (ValueError, TypeError):
            belop = 0.0
        try:
            mva_raw = _v("MVA-beløp", row, None)
            mva_belop = float(mva_raw) if mva_raw not in (None, "", "nan") else None
        except (ValueError, TypeError):
            mva_belop = None
        total += belop

        tags: list[str] = []
        if belop < 0:
            tags.append(_TAG_NEG)
        if mva_kode or (mva_belop is not None and abs(mva_belop) > 0.001):
            tags.append(_TAG_MVA_LINE)

        tree.insert("", "end", values=(
            dato, bilag, konto, knavn, tekst,
            formatting.fmt_amount(belop, dec),
            mva_kode,
            formatting.fmt_amount(mva_belop, dec) if mva_belop is not None else "",
            ref,
        ), tags=tuple(tags))

    tree.insert("", "end", values=(
        "", "", "", "", f"\u03a3 {len(sub)} trans.",
        formatting.fmt_amount(total, dec), "", "", "",
    ), tags=(_TAG_HEADER,))


def populate_payments_tree(page, nr: str) -> None:
    """Render matchede betalinger for åpne poster."""
    tree = page._payments_tree
    tree.delete(*tree.get_children())

    if page._subsequent_df is None or page._subsequent_df.empty:
        page._payments_empty_lbl.configure(
            text="Ingen etterfølgende periode er lastet — "
                 "matching krever at neste SAF-T er lastet inn.")
        return
    if not nr:
        page._payments_empty_lbl.configure(
            text="Velg en post til venstre for å se matchede betalinger.")
        return
    if page._df is None or page._master_df is None:
        return

    ub = 0.0
    ib = 0.0
    row_m = page._master_df[page._master_df["nr"].astype(str) == nr]
    if not row_m.empty:
        ub = float(row_m["ub"].iloc[0])
        ib = float(row_m["ib"].iloc[0])

    open_df, _ = _compute_open_items_with_confidence(
        page._df, nr=nr, mode=page._mode, ub=ub, ib=ib)
    if open_df.empty:
        page._payments_empty_lbl.configure(
            text=f"Ingen åpne poster for {nr} — ingenting å matche.")
        return

    matched = _match_open_against_period(
        open_df, page._subsequent_df, nr=nr, mode=page._mode)
    if matched.empty:
        page._payments_empty_lbl.configure(
            text=f"Ingen matchende betalinger i {page._subsequent_label} "
                 f"for åpne poster på {nr}.")
        return

    page._payments_empty_lbl.configure(
        text=f"Matchet mot: {page._subsequent_label}  "
             f"({len(matched)} linjer)")

    dec = page._detail_decimals()
    sum_betalt = 0.0
    sum_rest = 0.0
    for _, r in matched.iterrows():
        status = str(r.get("Status", ""))
        f_bilag = str(r.get("Bilag", ""))
        f_nr    = str(r.get("FakturaNr", "") or "")
        p_dato  = str(r.get("Betalt dato", "") or "")
        p_bilag = str(r.get("Betalt bilag", "") or "")
        p_tekst = str(r.get("Tekst", ""))
        try:
            p_belop = float(r.get("Betalt beløp") or 0.0)
            rest   = float(r.get("Resterende") or 0.0)
        except (ValueError, TypeError):
            p_belop = 0.0
            rest = 0.0

        tags: list[str] = []
        if rest < 0:
            tags.append(_TAG_NEG)

        tree.insert("", "end", values=(
            status, f_bilag, f_nr, p_dato, p_bilag, p_tekst,
            formatting.fmt_amount(p_belop, dec),
            formatting.fmt_amount(rest, dec),
        ), tags=tuple(tags))
        sum_betalt += p_belop
        sum_rest += rest

    tree.insert("", "end", values=(
        "", "", "", "", "", f"\u03a3 {len(matched)} linjer",
        formatting.fmt_amount(sum_betalt, dec),
        formatting.fmt_amount(sum_rest, dec),
    ), tags=(_TAG_HEADER,))


def navn_for_nr(page, nr: str) -> str:
    """Returner kundenavn/leverandørnavn for et internt nr-nummer."""
    try:
        navn_col = "Kundenavn" if page._mode == "kunder" else "Leverandørnavn"
        nr_col   = "Kundenr"   if page._mode == "kunder" else "Leverandørnr"
        if page._df is not None and nr_col in page._df.columns:
            mask = page._df[nr_col].astype(str).str.strip() == nr
            rows = page._df[mask]
            if not rows.empty and navn_col in rows.columns:
                return str(rows[navn_col].iloc[0])
    except Exception:
        pass
    return ""
