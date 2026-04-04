"""page_reskontro.py — Reskontro fane.

Viser kunde- og leverandørtransaksjoner fra SAF-T / HB-data,
med integrert BRREG-sjekk (Enhetsregisteret + Regnskapsregisteret).

Layout:
  - Toolbar: toggle Kunder / Leverandører, søkefelt, BRREG-knapp, eksport
  - Venstre panel: liste med IB/Bevegelse/UB + MVA-reg, Status, Bransje
  - Høyre panel (øverst): transaksjoner for valgt post
  - Høyre panel (nederst): BRREG-detaljer for valgt post
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import formatting

try:
    from ui_treeview_sort import enable_treeview_sorting as _enable_sort
except Exception:
    _enable_sort = None  # type: ignore


# ---------------------------------------------------------------------------
# Treeview-hjelpere: sortering + copy-paste
# ---------------------------------------------------------------------------

def _make_popup(master: Any, *, title: str, geometry: str = "960x400") -> Any:
    """Lag et standard Toplevel-vindu: transient, Escape-lukking, sentrert."""
    win = tk.Toplevel(master)
    win.title(title)
    win.geometry(geometry)
    win.resizable(True, True)
    try:
        win.transient(master.winfo_toplevel())
    except Exception:
        pass
    win.bind("<Escape>", lambda _e: win.destroy())
    win.bind("<Control-w>", lambda _e: win.destroy())
    return win


def _setup_tree(tree: Any, *, extended: bool = False) -> None:
    """Wire klikk-for-sortering, Ctrl+C (TSV-kopi) og Ctrl+A (velg alle).

    Kalles etter at tree er ferdig konfigurert med kolonner og headings.
    ``extended=True`` endrer selectmode til 'extended' (flervalg).
    """
    if tree is None:
        return
    if extended:
        try:
            tree.configure(selectmode="extended")
        except Exception:
            pass
    if _enable_sort is not None:
        try:
            _enable_sort(tree)
        except Exception:
            pass

    def _copy_selection(event: Any = None) -> None:
        sel = tree.selection()
        if not sel:
            return
        all_cols: list[str] = list(tree["columns"])
        try:
            disp = list(tree["displaycolumns"])
            if disp and disp[0] != "#all":
                all_cols = disp
        except Exception:
            pass
        col_idx = {c: i for i, c in enumerate(tree["columns"])}
        lines: list[str] = ["\t".join(
            str(tree.heading(c).get("text", c)) for c in all_cols)]
        for iid in sel:
            vals = tree.item(iid, "values")
            row = [str(vals[col_idx[c]]) if col_idx.get(c, -1) < len(vals) else ""
                   for c in all_cols]
            lines.append("\t".join(row))
        try:
            tree.clipboard_clear()
            tree.clipboard_append("\n".join(lines))
        except Exception:
            pass

    def _select_all(event: Any = None) -> None:
        try:
            tree.selection_set(tree.get_children(""))
        except Exception:
            pass

    tree.bind("<Control-c>", _copy_selection)
    tree.bind("<Control-C>", _copy_selection)
    tree.bind("<Control-a>", _select_all)
    tree.bind("<Control-A>", _select_all)


# ---------------------------------------------------------------------------
# Kolonner — master
# ---------------------------------------------------------------------------

_COL_NR      = "Nr"
_COL_NAVN    = "Navn"
_COL_ORGNR   = "Org.nr"
_COL_KONTO   = "Konto"
_COL_ANT     = "Trans."
_COL_IB      = "IB"
_COL_BEV     = "Bevegelse"
_COL_UB      = "UB"
_COL_MVA     = "MVA-reg"
_COL_STATUS  = "Status"
_COL_BRANSJE = "Bransje"

_MASTER_COLS = (
    _COL_NR, _COL_NAVN, _COL_ORGNR, _COL_KONTO, _COL_ANT,
    _COL_IB, _COL_BEV, _COL_UB,
    _COL_MVA, _COL_STATUS, _COL_BRANSJE,
)

_DETAIL_COLS = (
    "Dato", "Bilag", "Konto", "Kontonavn",
    "Tekst", "Beløp", "MVA-kode", "MVA-beløp", "Referanse", "Valuta",
)
_TAG_MVA_LINE = "mva_line"  # transaksjonsrad som har MVA-kode

# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

_TAG_NEG          = "neg"
_TAG_HEADER       = "header"
_TAG_ZERO         = "zero"
_TAG_BRREG_WARN   = "brreg_warn"     # konkurs / avvikling / slettet
_TAG_MVA_WARN     = "mva_warn"       # ikke MVA-registrert, men med saldo
_TAG_MVA_FRADRAG  = "mva_fradrag"    # leverandør har MVA-fradrag men er ikke MVA-reg.


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _has_reskontro_data(df: Any) -> bool:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    cols = set(df.columns)
    return "Kundenr" in cols or "Leverandørnr" in cols


def _build_master(
    df: pd.DataFrame, *, mode: str, year: int | None = None
) -> pd.DataFrame:
    """Bygg sammendragstabell per kunde/leverandør.

    IB / UB hentes primært fra SAF-T master-data (KundeIB/KundeUB eller
    LeverandørIB/LeverandørUB) — disse er autoritative og leses direkte fra
    <BalanceAccount> i SAF-T XML.  Bevegelse = sum av transaksjoner i year.

    Fallback (f.eks. HB-import uten SAF-T balanse-data):
      IB = sum transaksjoner med år < year
      Bevegelse = sum transaksjoner med år == year
      UB = IB + Bevegelse
    """
    nr_col    = "Kundenr"      if mode == "kunder" else "Leverandørnr"
    navn_col  = "Kundenavn"    if mode == "kunder" else "Leverandørnavn"
    orgnr_col = "Kundeorgnr"   if mode == "kunder" else "Leverandørorgnr"
    ib_col    = "KundeIB"      if mode == "kunder" else "LeverandørIB"
    ub_col    = "KundeUB"      if mode == "kunder" else "LeverandørUB"
    konto_col = "KundeKonto"   if mode == "kunder" else "LeverandørKonto"
    mva_col   = "KundeMvaReg"  if mode == "kunder" else "LeverandørMvaReg"

    empty = pd.DataFrame(
        columns=["nr", "navn", "orgnr", "antall", "ib", "bev", "ub",
                 "konto", "saft_mva_reg", "has_mva_tx"])
    if nr_col not in df.columns:
        return empty

    sub = df[
        df[nr_col].notna() & (df[nr_col].astype(str).str.strip() != "")
    ].copy()
    if sub.empty:
        return empty

    sub["__nr__"]    = sub[nr_col].astype(str).str.strip()
    sub["__navn__"]  = (sub[navn_col].astype(str).str.strip()
                        if navn_col in sub.columns else "")
    sub["__orgnr__"] = (sub[orgnr_col].astype(str).str.strip()
                        if orgnr_col in sub.columns else "")
    sub["__belop__"] = (pd.to_numeric(sub["Beløp"], errors="coerce").fillna(0.0)
                        if "Beløp" in sub.columns
                        else pd.Series(0.0, index=sub.index))
    sub["__konto__"] = (sub[konto_col].astype(str).str.strip()
                        if konto_col in sub.columns else "")
    sub["__mvareg__"] = (sub[mva_col].fillna(False).astype(bool)
                         if mva_col in sub.columns
                         else pd.Series(False, index=sub.index))

    grp = sub.groupby("__nr__")

    # Pre-compute: om noen transaksjoner har MVA-beløp (inngående fradrag)
    if "MVA-beløp" in sub.columns:
        sub["__mva_belop__"] = pd.to_numeric(sub["MVA-beløp"], errors="coerce").fillna(0.0)
        _mva_tx_flag = (
            sub.groupby("__nr__")["__mva_belop__"]
            .apply(lambda x: (x.abs() > 0.01).any())
            .rename("has_mva_tx")
        )
    else:
        _mva_tx_flag = None

    # SAF-T autoritative balanser — tilgjengelig hvis kolonnen finnes og
    # minst én rad har en ikke-NaN-verdi (0 er gyldig IB-verdi).
    has_saft_bal = (ib_col in sub.columns and sub[ib_col].notna().any())
    if has_saft_bal:
        sub["__ib__"] = pd.to_numeric(sub[ib_col], errors="coerce")
        sub["__ub__"] = pd.to_numeric(sub[ub_col], errors="coerce")
        grp_ib = grp["__ib__"].first().rename("ib")
        grp_ub = grp["__ub__"].first().rename("ub")

        base = pd.DataFrame({
            "nr":     grp["__nr__"].first(),
            "navn":   grp["__navn__"].first(),
            "orgnr":  grp["__orgnr__"].first(),
            "antall": grp["__nr__"].count(),
            "konto":  grp["__konto__"].first(),
            "saft_mva_reg": grp["__mvareg__"].first(),
        }).reset_index(drop=True)
        base = base.join(grp_ib, on="nr").join(grp_ub, on="nr")
        base["ib"]  = base["ib"].fillna(0.0)
        base["ub"]  = base["ub"].fillna(0.0)
        # Bevegelse = UB − IB (netto endring i perioden, samme som Audit Helper)
        base["bev"] = base["ub"] - base["ib"]
    else:
        # Fallback: beregn IB/UB fra transaksjoner
        if year is not None and "Dato" in sub.columns:
            dato = pd.to_datetime(sub["Dato"], errors="coerce")
            sub["__year__"] = dato.dt.year
            ib_mask  = sub["__year__"] < year
            bev_mask = sub["__year__"] == year
            grp_ib  = sub[ib_mask].groupby("__nr__")["__belop__"].sum().rename("ib")
            grp_bev = sub[bev_mask].groupby("__nr__")["__belop__"].sum().rename("bev")
            base = pd.DataFrame({
                "nr":     grp["__nr__"].first(),
                "navn":   grp["__navn__"].first(),
                "orgnr":  grp["__orgnr__"].first(),
                "antall": grp["__nr__"].count(),
                "konto":  grp["__konto__"].first(),
                "saft_mva_reg": grp["__mvareg__"].first(),
            }).reset_index(drop=True)
            base = base.join(grp_ib, on="nr").join(grp_bev, on="nr")
            base["ib"]  = base["ib"].fillna(0.0)
            base["bev"] = base["bev"].fillna(0.0)
            base["ub"]  = base["ib"] + base["bev"]
        else:
            tot = grp["__belop__"].sum()
            base = pd.DataFrame({
                "nr":     grp["__nr__"].first(),
                "navn":   grp["__navn__"].first(),
                "orgnr":  grp["__orgnr__"].first(),
                "antall": grp["__nr__"].count(),
                "konto":  grp["__konto__"].first(),
                "saft_mva_reg": grp["__mvareg__"].first(),
                "ib":     0.0,
                "bev":    tot,
                "ub":     tot,
            }).reset_index(drop=True)

    base["orgnr"]       = base["orgnr"].fillna("").replace("nan", "")
    base["konto"]       = base["konto"].fillna("").replace("nan", "")
    base["saft_mva_reg"] = base["saft_mva_reg"].fillna(False)
    if _mva_tx_flag is not None:
        base = base.join(_mva_tx_flag, on="nr")
        base["has_mva_tx"] = base["has_mva_tx"].fillna(False)
    else:
        base["has_mva_tx"] = False
    base = base.sort_values(
        "nr", key=lambda s: pd.to_numeric(s, errors="coerce").fillna(999_999))
    return base


def _build_detail(df: pd.DataFrame, *, nr: str, mode: str) -> pd.DataFrame:
    """Hent transaksjoner for én kunde/leverandør, sortert på dato."""
    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in df.columns:
        return pd.DataFrame()
    mask = df[nr_col].astype(str).str.strip() == nr
    sub = df[mask].copy()
    if not sub.empty and "Dato" in sub.columns:
        sub = sub.sort_values("Dato")
    return sub


def _brreg_status_text(enhet: dict) -> str:
    """Kort statustekst for master-listen."""
    flags = []
    if enhet.get("slettedato"):
        flags.append("Slettet")
    if enhet.get("konkurs"):
        flags.append("Konkurs")
    if enhet.get("underTvangsavvikling"):
        flags.append("Tvangsavvikling")
    if enhet.get("underAvvikling"):
        flags.append("Avvikling")
    return "  ".join(f"\u26a0 {f}" for f in flags) if flags else "\u2713 Aktiv"


def _brreg_has_risk(enhet: dict) -> bool:
    return any(enhet.get(k) for k in (
        "konkurs", "underAvvikling", "underTvangsavvikling")) or bool(
        enhet.get("slettedato"))


def _fmt_nok(val: float | None, decimals: int = 0) -> str:
    """Formater regnskapstall. Standard uten desimaler (heltall)."""
    if val is None:
        return "—"
    return formatting.fmt_amount(val, decimals)


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{val:.1f} %"


def _compute_nokkeltall(regnsk: dict) -> list[tuple[str, str, str]]:
    """Beregn nøkkeltall fra regnskapstall.

    Returnerer liste av (label, verdi_str, risiko_tag) der risiko_tag er
    "ok", "warn" eller "bad".
    """
    rows: list[tuple[str, str, str]] = []
    if not regnsk:
        return rows

    def _g(k: str) -> float | None:
        v = regnsk.get(k)
        return float(v) if v is not None else None

    omloep     = _g("sum_omloepsmidler")
    kgj        = _g("kortsiktig_gjeld")
    ek         = _g("sum_egenkapital")
    eiendeler  = _g("sum_eiendeler")
    aarsres    = _g("aarsresultat")
    driftsinnt = _g("driftsinntekter")
    sum_gjeld  = _g("sum_gjeld")

    # Likviditetsgrad 1 (current ratio)
    if omloep is not None and kgj and kgj != 0:
        lg1 = omloep / kgj
        tag = "ok" if lg1 >= 1.5 else ("warn" if lg1 >= 1.0 else "bad")
        rows.append(("Likviditetsgrad 1", f"{lg1:.2f}", tag))

    # Arbeidskapital
    if omloep is not None and kgj is not None:
        ak = omloep - kgj
        tag = "ok" if ak >= 0 else "bad"
        rows.append(("Arbeidskapital", _fmt_nok(ak), tag))

    # Egenkapitalandel
    if ek is not None and eiendeler and eiendeler != 0:
        eka = ek / eiendeler * 100
        tag = "ok" if eka >= 30 else ("warn" if eka >= 10 else "bad")
        rows.append(("Egenkapitalandel", _fmt_pct(eka), tag))
    elif ek is not None and ek < 0:
        rows.append(("Egenkapital", "⚠ Negativ", "bad"))

    # Gjeldsgrad
    if ek is not None and ek > 0 and sum_gjeld is not None:
        gg = sum_gjeld / ek
        tag = "ok" if gg <= 3 else ("warn" if gg <= 5 else "bad")
        rows.append(("Gjeldsgrad", f"{gg:.2f}", tag))

    # Resultatmargin
    if aarsres is not None and driftsinnt and driftsinnt != 0:
        margin = aarsres / driftsinnt * 100
        tag = "ok" if margin >= 5 else ("warn" if margin >= 0 else "bad")
        rows.append(("Resultatmargin", _fmt_pct(margin), tag))
    elif aarsres is not None and aarsres < 0:
        rows.append(("Årsresultat", "⚠ Negativt resultat", "bad"))

    return rows


# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------
# Åpne poster — matching-logikk
# ---------------------------------------------------------------------------

def _is_invoice_tekst(tekst: str) -> bool:
    t = tekst.lower()
    return any(k in t for k in ("faktura", "invoice", "kreditnota", "credit note"))


def _is_payment_tekst(tekst: str) -> bool:
    t = tekst.lower()
    return any(k in t for k in (
        "betaling", "innbetaling", "betalt", "payment", "avregning",
        "utbetaling", "remittering",
    ))


_RE_FAKTURA_NR = re.compile(
    r'(?:faktura\s+(?:nummer\s+)?|kreditnota\s+|invoice\s+(?:number\s+)?)(\d{4,})',
    re.IGNORECASE,
)


def _extract_faktura_nr(tekst: str) -> str | None:
    """Trekk ut faktura-nummeret fra en tekst-streng.

    Eksempler:
      "Faktura nummer 23660 til Veidekke..."  → "23660"
      "Betaling for faktura 23660 kontonummer..." → "23660"
      "Kreditnota 12345"                      → "12345"
    Returnerer None hvis ingen match.
    """
    m = _RE_FAKTURA_NR.search(tekst)
    return m.group(1) if m else None


def _compute_open_items(
    df: pd.DataFrame, *, nr: str, mode: str
) -> pd.DataFrame:
    """Identifiser åpne (ubetalte) fakturaer for én kunde/leverandør.

    Matching-strategi:
      1. Trekk ut faktura-nummeret fra tekst på hver transaksjonslinje.
         - Faktura-linje:  "Faktura nummer 23660 til..." → fnr="23660"
         - Betalings-linje: "Betaling for faktura 23660..." → fnr="23660"
      2. Grupper faktura-linjer per bilag (én faktura = ett bilag).
         Nøkkelen for matching er det UTTRUKNE faktura-nummeret (fnr),
         IKKE bilag-nummeret (som er forskjellig fra faktura-nummeret).
      3. Betalinger matchet via fnr fra tekst.
         Fallback: Referanse-feltet, eller bilag-nr i betalings-tekst.
      4. Faktura-status:
         - Gjenstår ≈ 0  → «✓ Betalt»
         - 0 < betalt < 100 %  → «~ Delvis betalt»
         - Ingen betaling funnet → «✗ Åpen»

    Returnerer DataFrame med én rad per faktura-bilag:
      Bilag, FakturaNr, Dato, Tekst, Fakturabeløp, Betalt (i år), Gjenstår, Status
    """
    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in df.columns:
        return pd.DataFrame()
    sub = df[df[nr_col].astype(str).str.strip() == nr].copy()
    if sub.empty:
        return pd.DataFrame()

    sub["__belop__"] = pd.to_numeric(
        sub["Beløp"] if "Beløp" in sub.columns else 0,
        errors="coerce").fillna(0.0)
    sub["__bilag__"] = (sub["Bilag"].astype(str).str.strip()
                        if "Bilag" in sub.columns else "")
    sub["__ref__"]   = (sub["Referanse"].fillna("").astype(str).str.strip()
                        if "Referanse" in sub.columns else "")
    sub["__tekst__"] = (sub["Tekst"].fillna("").astype(str)
                        if "Tekst" in sub.columns else "")
    sub["__dato__"]  = (sub["Dato"].astype(str).str[:10]
                        if "Dato" in sub.columns else "")
    sub["__fnr__"]   = sub["__tekst__"].apply(_extract_faktura_nr)

    is_pay = sub["__tekst__"].apply(_is_payment_tekst)
    is_inv = sub["__tekst__"].apply(_is_invoice_tekst)

    if mode == "kunder":
        inv_sign = sub["__belop__"] > 0.01
        pay_sign = sub["__belop__"] < -0.01
    else:
        inv_sign = sub["__belop__"] < -0.01
        pay_sign = sub["__belop__"] > 0.01

    # Invoice rows: invoice tekst with correct sign, OR correct sign without payment tekst
    inv_mask = (is_inv & inv_sign) | (inv_sign & ~is_pay)
    # Payment rows: payment tekst with correct sign
    pay_mask = is_pay & pay_sign

    invoice_rows = sub[inv_mask]
    payment_rows = sub[pay_mask]

    # --- Build payment lookup: fnr → accumulated paid amount ---
    # Each payment row has __fnr__ = the faktura-nr it references in its tekst
    pay_by_fnr: dict[str, float] = {}
    for _, pr in payment_rows.iterrows():
        fnr = pr["__fnr__"]
        if fnr:
            pay_by_fnr[fnr] = pay_by_fnr.get(fnr, 0.0) + float(pr["__belop__"])
        # Also index by Referanse (if numeric) as fallback
        ref = pr["__ref__"]
        if ref and ref.isdigit() and len(ref) >= 4:
            pay_by_fnr.setdefault(ref, 0.0)
            pay_by_fnr[ref] += float(pr["__belop__"])

    # --- Group invoice rows by bilag ---
    inv_by_bilag: dict[str, dict] = {}
    for _, ir in invoice_rows.iterrows():
        bilag = ir["__bilag__"]
        if bilag not in inv_by_bilag:
            inv_by_bilag[bilag] = {
                "bilag": bilag,
                "dato":  ir["__dato__"],
                "tekst": ir["__tekst__"],
                "fnr":   ir["__fnr__"],
                "total": 0.0,
            }
        inv_by_bilag[bilag]["total"] += float(ir["__belop__"])
        if inv_by_bilag[bilag]["fnr"] is None and ir["__fnr__"] is not None:
            inv_by_bilag[bilag]["fnr"] = ir["__fnr__"]

    # --- Compute paid / remaining per invoice ---
    rows: list[dict] = []
    for bilag, bg in sorted(inv_by_bilag.items(), key=lambda x: x[1]["dato"]):
        fnr   = bg["fnr"]
        total = bg["total"]
        paid  = 0.0

        # Primary: match by faktura-nr extracted from tekst
        if fnr and fnr in pay_by_fnr:
            paid = pay_by_fnr[fnr]
        # Fallback: betalinger som refererer til selve bilag-nummeret
        if abs(paid) < 0.001 and bilag in pay_by_fnr:
            paid = pay_by_fnr[bilag]

        remaining = total + paid   # paid is negative for AR → reduces balance

        if abs(remaining) < 0.01:
            status = "✓ Betalt"
        elif abs(paid) > 0.001:
            status = "~ Delvis betalt"
        else:
            status = "✗ Åpen"

        rows.append({
            "Bilag":         bilag,
            "FakturaNr":     fnr or "",
            "Dato":          bg["dato"],
            "Tekst":         bg["tekst"],
            "Fakturabeløp":  total,
            "Betalt (i år)": paid if abs(paid) > 0.001 else None,
            "Gjenstår":      remaining,
            "Status":        status,
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    order  = {"✗ Åpen": 0, "~ Delvis betalt": 1, "✓ Betalt": 2}
    result["__sort__"] = result["Status"].map(order).fillna(3)
    return result.sort_values(["__sort__", "Dato"]).drop(columns="__sort__").reset_index(drop=True)


def _match_open_against_period(
    open_invoices: pd.DataFrame,
    subseq_df: pd.DataFrame,
    *,
    nr: str,
    mode: str,
) -> pd.DataFrame:
    """Match åpne fakturaer (fra _compute_open_items) mot etterfølgende periode.

    Kun fakturaer med Status = «✗ Åpen» tas med.
    Matching mot etterfølgende periode:
      a) Betalings Referanse = faktura-bilag
      b) Faktura-bilag finnes i betalingens Tekst

    Returnerer DataFrame:
      Status, Bilag, Dato, Tekst, Gjenstår (år N),
      Betalt dato, Betalt beløp, Resterende
    """
    if open_invoices.empty:
        return pd.DataFrame()

    open_only = open_invoices[open_invoices["Status"] == "✗ Åpen"]
    if open_only.empty:
        return pd.DataFrame()

    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in subseq_df.columns:
        # Etterfølgende fil har ingen reskontro-kolonne — matcher kun på bilag/tekst
        subseq_sub = subseq_df.copy()
    else:
        subseq_sub = subseq_df[
            subseq_df[nr_col].astype(str).str.strip() == str(nr)].copy()

    subseq_sub["__s_belop__"] = pd.to_numeric(
        subseq_sub["Beløp"] if "Beløp" in subseq_sub.columns else 0,
        errors="coerce").fillna(0.0)
    subseq_sub["__s_ref__"]  = (
        subseq_sub["Referanse"].fillna("").astype(str).str.strip()
        if "Referanse" in subseq_sub.columns else "")
    subseq_sub["__s_tekst__"] = (
        subseq_sub["Tekst"].fillna("").astype(str)
        if "Tekst" in subseq_sub.columns else "")
    subseq_sub["__s_dato__"]  = (
        subseq_sub["Dato"].astype(str).str[:10]
        if "Dato" in subseq_sub.columns else "")

    # Pre-compute faktura_nr for all subsequent rows (to avoid recomputing per invoice)
    subseq_sub["__s_fnr__"] = subseq_sub["__s_tekst__"].apply(_extract_faktura_nr)

    rows: list[dict] = []
    for _, inv_row in open_only.iterrows():
        inv_bilag  = str(inv_row["Bilag"])
        inv_fnr    = str(inv_row.get("FakturaNr", "") or "")
        gjenstar_n = float(inv_row["Gjenstår"])

        paid = pd.DataFrame()
        if not subseq_sub.empty:
            candidates = pd.DataFrame()

            # a) Match via faktura-nr fra tekst: etterfølgende betaling som
            #    refererer til samme faktura-nr som denne fakturaen.
            if inv_fnr:
                m_fnr = subseq_sub[subseq_sub["__s_fnr__"] == inv_fnr]
                candidates = pd.concat([candidates, m_fnr])

            # b) Referanse-felt = faktura-bilag eller faktura-nr
            if inv_fnr:
                m_ref = subseq_sub[subseq_sub["__s_ref__"] == inv_fnr]
                candidates = pd.concat([candidates, m_ref])
            m_ref2 = subseq_sub[subseq_sub["__s_ref__"] == inv_bilag]
            candidates = pd.concat([candidates, m_ref2])

            # c) Fallback: faktura-bilag i tekst
            if len(inv_bilag) >= 4:
                m_txt = subseq_sub[
                    subseq_sub["__s_tekst__"].str.contains(
                        inv_bilag, na=False, regex=False)]
                candidates = pd.concat([candidates, m_txt])

            if not candidates.empty:
                candidates = candidates.drop_duplicates()
                # Behold kun betalings-rader
                paid = candidates[candidates["__s_tekst__"].apply(_is_payment_tekst)]

        paid_belop = float(paid["__s_belop__"].sum()) if not paid.empty else 0.0
        paid_dato  = (str(paid["__s_dato__"].min())
                      if not paid.empty else "")
        resterende = gjenstar_n + paid_belop

        if abs(resterende) < 0.01:
            status = "✓ Betalt"
        elif abs(paid_belop) > 0.001:
            status = "~ Delvis betalt"
        else:
            status = "✗ Fortsatt åpen"

        rows.append({
            "Status":          status,
            "Bilag":           inv_bilag,
            "Dato":            str(inv_row.get("Dato", ""))[:10],
            "Tekst":           str(inv_row.get("Tekst", "")),
            "Gjenstår (år N)": gjenstar_n,
            "Betalt dato":     paid_dato,
            "Betalt beløp":    paid_belop if abs(paid_belop) > 0.001 else None,
            "Resterende":      resterende,
        })

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    order  = {"✗ Fortsatt åpen": 0, "~ Delvis betalt": 1, "✓ Betalt": 2}
    result["__sort__"] = result["Status"].map(order).fillna(3)
    return result.sort_values(["__sort__", "Dato"]).drop(columns="__sort__")


# ---------------------------------------------------------------------------

class ReskontroPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, master: Any = None) -> None:
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            return

        self._df: pd.DataFrame | None = None
        self._master_df: pd.DataFrame | None = None
        self._mode: str = "kunder"
        self._selected_nr: str = ""
        self._filter_var: Any = None

        # BRREG: {orgnr: {"enhet": dict|None, "regnskap": dict|None}}
        self._brreg_data: dict[str, dict] = {}
        # intern_nr → orgnr
        self._orgnr_map: dict[str, str] = {}
        # Etterfølgende periode SAF-T (lastet inn av bruker for matching)
        self._subsequent_df: pd.DataFrame | None = None
        self._subsequent_label: str = ""

        if tk is None:
            return

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def refresh_from_session(self, session: Any = None) -> None:
        import session as _session
        df = getattr(_session, "dataset", None)
        self._df = df if _has_reskontro_data(df) else None
        self._refresh_all()

    # ------------------------------------------------------------------
    # UI-bygging
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")

        ttk.Label(tb, text="Reskontro",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))

        self._mode_var = tk.StringVar(value="kunder")
        ttk.Radiobutton(tb, text="Kunder", variable=self._mode_var,
                        value="kunder",
                        command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(tb, text="Leverandører", variable=self._mode_var,
                        value="leverandorer",
                        command=self._on_mode_change).pack(side="left",
                                                           padx=(6, 12))

        ttk.Label(tb, text="Søk:").pack(side="left")
        self._filter_var = tk.StringVar()
        search = ttk.Entry(tb, textvariable=self._filter_var, width=22)
        search.pack(side="left", padx=(4, 8))
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        ttk.Button(tb, text="Oppdater",
                   command=self.refresh_from_session,
                   width=10).pack(side="left")

        self._brreg_btn = ttk.Button(
            tb, text="BRREG-sjekk\u2026",
            command=self._start_brreg_sjekk, width=14)
        self._brreg_btn.pack(side="left", padx=(6, 0))

        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y",
                                                   padx=(8, 8), pady=2)

        self._hide_zero_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tb, text="Skjul nullposter",
                        variable=self._hide_zero_var,
                        command=self._apply_filter).pack(side="left")

        self._decimals_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tb, text="Desimaler",
                        variable=self._decimals_var,
                        command=self._on_decimals_toggle).pack(side="left",
                                                                padx=(6, 0))

        self._alle_trans_btn = ttk.Button(
            tb, text="Alle trans.", command=self._show_all_transactions,
            width=10)
        self._alle_trans_btn.pack(side="left", padx=(6, 0))

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 0))

        # Statuslinje nederst
        self.rowconfigure(2, weight=0)
        status_bar = ttk.Frame(self, relief="sunken", padding=(4, 1))
        status_bar.grid(row=2, column=0, sticky="ew")
        self._status_lbl = ttk.Label(status_bar, text="", foreground="#555",
                                     font=("TkDefaultFont", 8))
        self._status_lbl.pack(side="left")

        # ---- Venstre: master-liste ----
        left = ttk.Frame(pane)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pane.add(left, weight=1)

        self._master_tree = self._make_master_tree(left)
        self._master_tree.grid(row=0, column=0, sticky="nsew")
        vsb1 = ttk.Scrollbar(left, orient="vertical",
                              command=self._master_tree.yview)
        vsb1.grid(row=0, column=1, sticky="ns")
        hsb1 = ttk.Scrollbar(left, orient="horizontal",
                              command=self._master_tree.xview)
        hsb1.grid(row=1, column=0, sticky="ew")
        self._master_tree.configure(yscrollcommand=vsb1.set,
                                    xscrollcommand=hsb1.set)
        self._master_tree.bind("<<TreeviewSelect>>", self._on_master_select)

        # Sum-rad: IB / Bevegelse / UB totalt + avstemming
        sum_f = ttk.Frame(left, padding=(2, 2))
        sum_f.grid(row=2, column=0, columnspan=2, sticky="ew")
        sum_f.columnconfigure(1, weight=1)
        ttk.Label(sum_f, text="Sum:", font=("TkDefaultFont", 8, "bold"),
                  foreground="#333").grid(row=0, column=0, sticky="w", padx=(2, 6))
        self._sum_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                                   foreground="#333")
        self._sum_lbl.grid(row=0, column=1, sticky="w")
        self._recon_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                                     foreground="#777")
        self._recon_lbl.grid(row=0, column=2, sticky="e", padx=(12, 2))

        # ---- Høyre: transaksjoner + BRREG-panel ----
        right = ttk.Frame(pane)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(3, weight=1)
        pane.add(right, weight=2)

        detail_hdr = ttk.Frame(right)
        detail_hdr.grid(row=0, column=0, columnspan=2, sticky="ew",
                        padx=4, pady=(4, 2))
        detail_hdr.columnconfigure(0, weight=1)
        self._detail_lbl = ttk.Label(
            detail_hdr, text="Velg en post for å se transaksjoner",
            font=("TkDefaultFont", 9, "bold"))
        self._detail_lbl.grid(row=0, column=0, sticky="w")
        self._open_items_btn = ttk.Button(
            detail_hdr, text="Åpne poster",
            command=self._show_open_items_popup, width=12)
        self._open_items_btn.grid(row=0, column=1, padx=(6, 0))
        self._subseq_btn = ttk.Button(
            detail_hdr, text="Etterfølgende periode\u2026",
            command=self._open_subsequent_period, width=22)
        self._subseq_btn.grid(row=0, column=2, padx=(4, 0))

        self._detail_tree = self._make_detail_tree(right)
        self._detail_tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0))
        vsb2 = ttk.Scrollbar(right, orient="vertical",
                              command=self._detail_tree.yview)
        vsb2.grid(row=1, column=1, sticky="ns")
        hsb2 = ttk.Scrollbar(right, orient="horizontal",
                              command=self._detail_tree.xview)
        hsb2.grid(row=2, column=0, sticky="ew", padx=(4, 0))
        self._detail_tree.configure(yscrollcommand=vsb2.set,
                                    xscrollcommand=hsb2.set)

        # BRREG-infopanel
        self._brreg_frame = ttk.LabelFrame(
            right, text="BRREG-info", padding=(4, 4))
        self._brreg_frame.grid(row=3, column=0, columnspan=2,
                                sticky="nsew", padx=4, pady=(4, 0))
        self._brreg_frame.rowconfigure(0, weight=1)
        self._brreg_frame.columnconfigure(0, weight=1)
        self._brreg_info_labels: dict[str, tk.StringVar] = {}
        self._build_brreg_panel()

    def _make_master_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_MASTER_COLS, show="headings",
                             selectmode="browse")
        tree.heading(_COL_NR,      text="Nr",        anchor="w")
        tree.heading(_COL_NAVN,    text="Navn",       anchor="w")
        tree.heading(_COL_ORGNR,   text="Org.nr",     anchor="w")
        tree.heading(_COL_KONTO,   text="Konto",      anchor="w")
        tree.heading(_COL_ANT,     text="Trans.",     anchor="e")
        tree.heading(_COL_IB,      text="IB",         anchor="e")
        tree.heading(_COL_BEV,     text="Bevegelse",  anchor="e")
        tree.heading(_COL_UB,      text="UB",         anchor="e")
        tree.heading(_COL_MVA,     text="MVA-reg",    anchor="center")
        tree.heading(_COL_STATUS,  text="Status",     anchor="w")
        tree.heading(_COL_BRANSJE, text="Bransje",    anchor="w")

        tree.column(_COL_NR,      width=70,  anchor="w",      stretch=False)
        tree.column(_COL_NAVN,    width=180, anchor="w",      stretch=True)
        tree.column(_COL_ORGNR,   width=90,  anchor="w",      stretch=False)
        tree.column(_COL_KONTO,   width=55,  anchor="w",      stretch=False)
        tree.column(_COL_ANT,     width=55,  anchor="e",      stretch=False)
        tree.column(_COL_IB,      width=110, anchor="e",      stretch=False)
        tree.column(_COL_BEV,     width=110, anchor="e",      stretch=False)
        tree.column(_COL_UB,      width=110, anchor="e",      stretch=False)
        tree.column(_COL_MVA,     width=75,  anchor="center", stretch=False)
        tree.column(_COL_STATUS,  width=110, anchor="w",      stretch=False)
        tree.column(_COL_BRANSJE, width=200, anchor="w",      stretch=True)

        tree.tag_configure(_TAG_NEG,        foreground="red")
        tree.tag_configure(_TAG_ZERO,       foreground="#888888")
        tree.tag_configure(_TAG_BRREG_WARN,  foreground="#8B0000",
                           background="#FFF3CD")
        tree.tag_configure(_TAG_MVA_WARN,    background="#FFF8E1")
        tree.tag_configure(_TAG_MVA_FRADRAG, foreground="#8B4500",
                           background="#FDEBD0")
        _setup_tree(tree)
        return tree

    def _make_detail_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_DETAIL_COLS, show="headings",
                             selectmode="extended")
        widths = {
            "Dato": 90, "Bilag": 80, "Konto": 70, "Kontonavn": 170,
            "Tekst": 240, "Beløp": 110, "MVA-kode": 70, "MVA-beløp": 100,
            "Referanse": 80, "Valuta": 55,
        }
        right_cols = {"Beløp", "MVA-beløp"}
        for col in _DETAIL_COLS:
            tree.heading(col, text=col,
                         anchor="e" if col in right_cols else "w")
            tree.column(col, width=widths.get(col, 90),
                        anchor="e" if col in right_cols else "w",
                        stretch=col in ("Tekst", "Kontonavn"))
        tree.tag_configure(_TAG_NEG,      foreground="red")
        tree.tag_configure(_TAG_HEADER,   background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_MVA_LINE, background="#F0FFF0")
        tree.bind("<Double-1>", self._on_detail_double_click)
        tree.bind("<Return>",   self._on_detail_double_click)
        tree.bind("<<TreeviewSelect>>", self._on_detail_select)
        tree.bind("<Button-3>", self._on_detail_right_click)
        _setup_tree(tree, extended=True)
        return tree

    def _detail_decimals(self) -> int:
        """Returnerer antall desimaler for detaljvisning basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _master_decimals(self) -> int:
        """Returnerer antall desimaler for master-listen basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _on_detail_double_click(self, event: Any) -> None:
        """Dobbeltklikk på transaksjon → vis alle linjer for samme bilag."""
        tree = self._detail_tree
        item = tree.identify_row(event.y)
        if not item:
            return
        vals = tree.item(item, "values")
        if not vals or len(vals) < 2:
            return
        bilag = str(vals[1]).strip()
        if not bilag or bilag == "":
            return
        self._open_bilag_popup(bilag)

    def _open_bilag_popup(self, bilag: str) -> None:
        """Vis popup med ALLE HB-linjer for bilag (inkl. MVA-linje på konto 27xx).

        Søker i hele datasettet (ikke kun reskontro-linjer), slik at
        motkonto, inntektslinje og MVA-linje vises med tilhørende MVA-kode.
        """
        if self._df is None:
            return
        if "Bilag" not in self._df.columns:
            return

        # Søk i HELE datasettet — inkluderer alle kontolinjer, ikke bare reskontro
        mask = self._df["Bilag"].astype(str).str.strip() == bilag
        sub  = self._df[mask].copy()
        if sub.empty:
            return
        if "Dato" in sub.columns:
            sub = sub.sort_values("Dato")

        win = _make_popup(self,
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

        dec = self._detail_decimals()
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

    def _build_brreg_panel(self) -> None:
        """Bygg tk.Text-basert BRREG-panel med farge-tags."""
        f = self._brreg_frame

        self._brreg_text = tk.Text(
            f, state="disabled", wrap="word",
            font=("TkDefaultFont", 9),
            relief="flat", borderwidth=0,
            height=8, cursor="arrow",
        )
        vsb = ttk.Scrollbar(f, orient="vertical", command=self._brreg_text.yview)
        self._brreg_text.configure(yscrollcommand=vsb.set)
        self._brreg_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Tags
        bg = self._brreg_text.cget("background")
        self._brreg_text.tag_configure("heading",  font=("TkDefaultFont", 9, "bold"), foreground="#1a4c7a")
        self._brreg_text.tag_configure("key",      foreground="#555555")
        self._brreg_text.tag_configure("val",      foreground="#111111")
        self._brreg_text.tag_configure("warn",     foreground="#C75000")
        self._brreg_text.tag_configure("ok",       foreground="#1a7a2a")
        self._brreg_text.tag_configure("bad",      foreground="#C75000")
        self._brreg_text.tag_configure("dim",      foreground="#888888")

        self._clear_brreg_panel()

    def _brreg_write(self, *parts: tuple[str, str]) -> None:
        """Hjelpemetode: sett inn (tekst, tag)-par i _brreg_text."""
        t = self._brreg_text
        t.configure(state="normal")
        for text, tag in parts:
            t.insert("end", text, tag)
        t.configure(state="disabled")

    def _clear_brreg_panel(self) -> None:
        t = self._brreg_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")
        self._brreg_write(
            ("— kjør BRREG-sjekk for å hente data —", "dim"),
        )

    def _update_brreg_panel(self, orgnr: str) -> None:
        """Fyll BRREG-panelet med data for valgt orgnr."""
        t = self._brreg_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")

        def w(*parts: tuple[str, str]) -> None:
            self._brreg_write(*parts)

        def kv(key: str, val: str, val_tag: str = "val") -> None:
            w((f"  {key}: ", "key"), (val + "\n", val_tag))

        if not orgnr or orgnr not in self._brreg_data:
            msg = "Ikke hentet — trykk BRREG-sjekk" if orgnr else "— velg en post —"
            w((msg, "dim"))
            return

        rec    = self._brreg_data[orgnr]
        enhet  = rec.get("enhet") or {}
        regnsk = rec.get("regnskap") or {}

        # --- Firmainformasjon ---
        w(("Firmainformasjon\n", "heading"))
        kv("Orgnr", orgnr)

        if not enhet:
            kv("Status", "Ikke funnet i Enhetsregisteret", "bad")
            return

        try:
            import brreg_client as _brreg
            exempt = _brreg.is_likely_exempt(enhet.get("naeringskode", ""))
        except Exception:
            exempt = False

        status_txt = _brreg_status_text(enhet)
        status_tag = "bad" if any(
            enhet.get(k) for k in ("konkurs", "underAvvikling", "underTvangsavvikling")
        ) else "ok"
        kv("Status", status_txt, status_tag)

        mva_reg = enhet.get("registrertIMvaregisteret", False)
        mva_txt = "✓ Ja" if mva_reg else "✗ Nei"
        kv("MVA-registrert", mva_txt, "ok" if mva_reg else "bad")
        kv("Org.form", enhet.get("organisasjonsform", "") or "—")
        kv("Adresse", enhet.get("forretningsadresse", "") or "—")

        nk = enhet.get("naeringskode", "")
        nn = enhet.get("naeringsnavn", "")
        bransje_txt = f"{nk} {nn}".strip() if nk else nn
        kv("Bransje", bransje_txt or "—")
        if exempt:
            w(("  ⚠ Bransjen er typisk unntatt MVA\n", "warn"))

        if not regnsk:
            w(("\nRegnskap\n", "heading"))
            w(("  Ikke tilgjengelig\n", "dim"))
            return

        # --- Resultatregnskap ---
        valuta  = regnsk.get("valuta", "NOK")
        fra     = regnsk.get("fra_dato", "")[:10]
        til     = regnsk.get("til_dato", "")[:10]
        aar     = regnsk.get("regnskapsaar", "")
        periode = f"{fra} – {til}" if fra and til else aar
        w((f"\nResultatregnskap {aar}  ({valuta}  {periode})\n", "heading"))

        def _r(key: str, label: str, val_tag: str = "val") -> None:
            v = regnsk.get(key)
            kv(label, _fmt_nok(v) if v is not None else "—", val_tag)

        _r("driftsinntekter",    "Driftsinntekter")
        _r("driftskostnader",    "Driftskostnader")
        _r("driftsresultat",     "Driftsresultat")
        w(("  —\n", "dim"))
        _r("finansinntekter",    "Finansinntekter")
        _r("finanskostnader",    "Finanskostnader")
        _r("netto_finans",       "Netto finans")
        w(("  —\n", "dim"))
        _r("resultat_for_skatt", "Res. før skatt")

        aarsres_v = regnsk.get("aarsresultat")
        driftsinnt_v = regnsk.get("driftsinntekter")
        aarsres_tag = "val"
        if aarsres_v is not None and aarsres_v < 0:
            aarsres_tag = "bad"
        _r("aarsresultat", "Årsresultat", aarsres_tag)

        rev_txt = regnsk.get("revisorberetning", "")
        if regnsk.get("ikke_revidert") or regnsk.get("fravalg_revisjon"):
            kv("Revisjon", rev_txt, "warn")
        else:
            kv("Revisjon", rev_txt, "ok")

        # --- Balanse ---
        w((f"\nBalanse ({aar})\n", "heading"))
        _r("sum_anleggsmidler",  "Anleggsmidler")
        _r("sum_omloepsmidler",  "Omløpsmidler")
        _r("sum_eiendeler",      "Sum eiendeler")
        w(("  —\n", "dim"))

        ek_v = regnsk.get("sum_egenkapital")
        ek_tag = "bad" if (ek_v is not None and ek_v < 0) else "val"
        _r("sum_egenkapital",    "Egenkapital", ek_tag)
        w(("  —\n", "dim"))
        _r("langsiktig_gjeld",   "Langsiktig gjeld")
        _r("kortsiktig_gjeld",   "Kortsiktig gjeld")
        _r("sum_gjeld",          "Sum gjeld")

        # --- Nøkkeltall ---
        nokkeltall = _compute_nokkeltall(regnsk)
        if nokkeltall:
            w(("\nNøkkeltall\n", "heading"))
            risk_map = {"ok": "ok", "warn": "warn", "bad": "bad"}
            for label, verdi, risiko in nokkeltall:
                tag = risk_map.get(risiko, "val")
                kv(label, verdi, tag)

        # --- Risikovurdering (kun kunder med åpen saldo) ---
        has_ub = False
        try:
            if self._master_df is not None and "nr" in self._master_df.columns:
                sel_nr = self._selected_nr
                if sel_nr:
                    row_m = self._master_df[self._master_df["nr"].astype(str) == sel_nr]
                    if not row_m.empty:
                        ub_val = float(row_m["ub"].iloc[0])
                        has_ub = abs(ub_val) > 0.01
        except Exception:
            pass

        if has_ub and self._mode == "kunder":
            w(("\nRisikovurdering — tapsavsetning\n", "heading"))
            if _brreg_has_risk(enhet):
                w(("  ⚠ Konkurs/avvikling — vurder 100 % avsetning\n", "bad"))
            else:
                risk_signals = []
                if ek_v is not None and ek_v < 0:
                    risk_signals.append("Negativ egenkapital")
                omloep_v = regnsk.get("sum_omloepsmidler")
                kgj_v    = regnsk.get("kortsiktig_gjeld")
                if omloep_v is not None and kgj_v and kgj_v != 0:
                    lg1 = omloep_v / kgj_v
                    if lg1 < 1.0:
                        risk_signals.append(f"Likviditetsgrad {lg1:.2f} < 1,0")
                if aarsres_v is not None and aarsres_v < 0:
                    risk_signals.append("Negativt årsresultat")
                if risk_signals:
                    w(("  ⚠ Risikosignaler:\n", "warn"))
                    for s in risk_signals:
                        w((f"    • {s}\n", "warn"))
                else:
                    w(("  ✓ Ingen umiddelbare risikosignaler\n", "ok"))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _on_decimals_toggle(self) -> None:
        """Re-render master og detail med ny desimal-innstilling."""
        self._apply_filter()
        if self._selected_nr:
            self._populate_detail(self._selected_nr)

    def _on_mode_change(self) -> None:
        self._mode = self._mode_var.get()
        self._selected_nr = ""
        self._detail_tree.delete(*self._detail_tree.get_children())
        self._detail_lbl.configure(text="Velg en post for å se transaksjoner")
        self._clear_brreg_panel()
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._detail_tree.delete(*self._detail_tree.get_children())
        self._detail_lbl.configure(text="Velg en post for å se transaksjoner")
        self._clear_brreg_panel()

        if not _has_reskontro_data(self._df):
            self._master_tree.delete(*self._master_tree.get_children())
            self._status_lbl.configure(
                text="Ingen kunde-/leverandørdata. "
                     "Last inn en SAF-T-fil (zip/xml).")
            return

        import session as _session
        year_str = getattr(_session, "year", None)
        year = int(year_str) if year_str else None
        self._master_df = _build_master(self._df, mode=self._mode, year=year)

        # Bygg orgnr-kart
        if "orgnr" in self._master_df.columns:
            self._orgnr_map = {
                str(r["nr"]): str(r["orgnr"])
                for _, r in self._master_df.iterrows()
                if str(r.get("orgnr", "")).strip()
            }
        else:
            self._orgnr_map = {}

        self._apply_filter()

    def _apply_filter(self) -> None:
        if self._master_df is None:
            return
        q = (self._filter_var.get().strip().lower()
             if self._filter_var else "")
        hide_zero = bool(getattr(self, "_hide_zero_var", None)
                         and self._hide_zero_var.get())
        dec = self._master_decimals()

        tree = self._master_tree
        # Bevar scroll-posisjon og valgt rad ved filter-refresh
        _prev_sel  = tree.selection()
        _prev_yview = tree.yview()[0] if tree.get_children() else 0.0
        tree.delete(*tree.get_children())

        shown = 0
        n_mva_warn_shown  = 0
        n_mva_fradrag     = 0
        sum_ib = sum_bev = sum_ub = 0.0

        for _, row in self._master_df.iterrows():
            nr   = str(row["nr"])
            navn = str(row["navn"])
            ant  = int(row["antall"])
            ib   = float(row["ib"])
            bev  = float(row["bev"])
            ub   = float(row["ub"])

            # orgnr må hentes FØR søke-filteret (brukes i søket)
            orgnr = self._orgnr_map.get(nr, "")

            if q and q not in nr.lower() and q not in navn.lower() \
                    and q not in orgnr.lower():
                continue

            # Skjul poster der alt er 0
            if hide_zero and abs(ib) < 0.01 and abs(bev) < 0.01 and abs(ub) < 0.01:
                continue

            # --- MVA: SAF-T er primærkilde, BRREG er override ---
            saft_mva  = bool(row.get("saft_mva_reg", False))
            has_mva_tx = bool(row.get("has_mva_tx", False))
            brec      = self._brreg_data.get(orgnr, {}) if orgnr else {}
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
            elif (mva_reg is False and self._mode == "leverandorer"
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
            konto_disp = str(row.get("konto", "")) if "konto" in self._master_df.columns else ""
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
        if hasattr(self, "_sum_lbl"):
            self._sum_lbl.configure(text=sum_txt)

        # --- Avstemming: bevegelse i reskontro vs. konto-bevegelse i full df ---
        if hasattr(self, "_recon_lbl"):
            recon_txt = ""
            try:
                konto = ""
                if self._master_df is not None and "konto" in self._master_df.columns:
                    kontoes = (self._master_df["konto"]
                               .replace("", None).dropna().unique())
                    if len(kontoes) == 1:
                        konto = str(kontoes[0])
                if konto and self._df is not None and "Konto" in self._df.columns:
                    konto_bev = pd.to_numeric(
                        self._df.loc[
                            self._df["Konto"].astype(str).str.strip() == konto,
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
            self._recon_lbl.configure(text=recon_txt)

        # --- Statuslinje ---
        mode_label = "kunder" if self._mode == "kunder" else "leverandører"
        q_suffix   = f"  (filter: '{self._filter_var.get().strip()}')" if q else ""
        n_brreg    = len(self._brreg_data)
        parts      = [f"{shown} {mode_label}"]
        if n_brreg:
            parts.append(f"{n_brreg} BRREG-sjekket")
        if n_mva_fradrag:
            parts.append(f"\u26a0 {n_mva_fradrag} MVA-fradrag uten reg.")
        if n_mva_warn_shown:
            parts.append(f"\u2717 {n_mva_warn_shown} ikke MVA-reg.")
        self._status_lbl.configure(
            text=("  \u2022  ".join(parts)) + q_suffix)

        # Gjenopprett scroll-posisjon og valgt rad etter filter-refresh
        if _prev_yview > 0:
            self.after(0, lambda y=_prev_yview: tree.yview_moveto(y))
        if _prev_sel:
            still_there = [s for s in _prev_sel if tree.exists(s)]
            if still_there:
                tree.selection_set(still_there)
                tree.see(still_there[0])


    def _on_master_select(self, _event: Any = None) -> None:
        sel = self._master_tree.selection()
        if not sel:
            return
        self._selected_nr = sel[0]
        self._populate_detail(self._selected_nr)
        orgnr = self._orgnr_map.get(self._selected_nr, "")
        self._update_brreg_panel(orgnr)

    def _on_detail_select(self, _event: Any = None) -> None:
        """Oppdater statuslinje med antall markerte rader og sum beløp."""
        sel = self._detail_tree.selection()
        n = len(sel)
        if n <= 1:
            return  # Statuslinja settes av andre metoder ved enkeltvalg
        # Beregn sum av Beløp-kolonnen for markerte rader
        belop_idx = list(_DETAIL_COLS).index("Beløp") if "Beløp" in _DETAIL_COLS else -1
        total = 0.0
        if belop_idx >= 0:
            for iid in sel:
                vals = self._detail_tree.item(iid, "values")
                if vals and belop_idx < len(vals):
                    try:
                        raw = str(vals[belop_idx]).replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace(",", ".")
                        total += float(raw)
                    except (ValueError, TypeError):
                        pass
        dec = self._detail_decimals()
        self._status_lbl.configure(
            text=f"Markert: {n} rader  |  Beløp: {formatting.fmt_amount(total, dec)}")

    def _on_detail_right_click(self, event: Any) -> None:
        """Høyreklikk-kontekstmeny på detaljrader."""
        tree = self._detail_tree
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
                command=lambda b=bilag: self._open_bilag_popup(b))
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
            command=self._show_open_items_popup)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _populate_detail(self, nr: str) -> None:
        tree = self._detail_tree
        tree.delete(*tree.get_children())

        if self._df is None:
            return

        sub = _build_detail(self._df, nr=nr, mode=self._mode)
        if sub.empty:
            return

        cols = list(sub.columns)

        def _v(col: str, row: Any, default: Any = "") -> Any:
            return row[col] if col in cols else default

        total = 0.0
        debet = 0.0
        kredit = 0.0
        dec = self._detail_decimals()
        for _, row in sub.iterrows():
            dato      = str(_v("Dato",      row, ""))[:10]
            bilag     = str(_v("Bilag",     row, ""))
            konto     = str(_v("Konto",     row, ""))
            knavn     = str(_v("Kontonavn", row, ""))
            tekst     = str(_v("Tekst",     row, ""))
            ref       = str(_v("Referanse", row, ""))
            valuta    = str(_v("Valuta",    row, ""))
            mva_kode  = str(_v("MVA-kode",  row, ""))
            if mva_kode in ("nan", "None"):
                mva_kode = ""
            try:
                belop = float(_v("Beløp", row, 0.0))
            except (ValueError, TypeError):
                belop = 0.0
            try:
                mva_belop_raw = _v("MVA-beløp", row, None)
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

        navn = ""
        try:
            navn_col = "Kundenavn" if self._mode == "kunder" else "Leverandørnavn"
            if navn_col in cols:
                navn = str(sub[navn_col].iloc[0])
        except Exception:
            pass

        mode_str = "Kunde" if self._mode == "kunder" else "Leverandør"
        lbl = f"{mode_str} {nr}"
        if navn:
            lbl += f"  \u2014  {navn}"
        lbl += f"  ({len(sub)} transaksjoner, UB {formatting.fmt_amount(total)})"
        self._detail_lbl.configure(text=lbl)
        self._status_lbl.configure(
            text=(f"Markert: 1 rad  |  Beløp: {formatting.fmt_amount(total, dec)}"
                  f"  \u2022  D: {formatting.fmt_amount(debet, dec)}"
                  f"  K: {formatting.fmt_amount(kredit, dec)}"))

    # ------------------------------------------------------------------
    # Åpne poster
    # ------------------------------------------------------------------

    def _navn_for_nr(self, nr: str) -> str:
        """Returner kundenavn/leverandørnavn for et internt nr-nummer."""
        try:
            navn_col = "Kundenavn" if self._mode == "kunder" else "Leverandørnavn"
            nr_col   = "Kundenr"   if self._mode == "kunder" else "Leverandørnr"
            if self._df is not None and nr_col in self._df.columns:
                mask = self._df[nr_col].astype(str).str.strip() == nr
                rows = self._df[mask]
                if not rows.empty and navn_col in rows.columns:
                    return str(rows[navn_col].iloc[0])
        except Exception:
            pass
        return ""

    def _show_open_items_popup(self) -> None:
        """Vis popup med åpne (ubetalte) fakturaer for valgt kunde/leverandør."""
        if not self._selected_nr or self._df is None:
            return

        result_df = _compute_open_items(
            self._df, nr=self._selected_nr, mode=self._mode)
        if result_df.empty:
            return

        dec      = self._detail_decimals()
        mode_str = "Kunde" if self._mode == "kunder" else "Leverandør"
        navn     = self._navn_for_nr(self._selected_nr)
        title_str = f"{mode_str} {self._selected_nr}" + (f"  —  {navn}" if navn else "")

        open_df   = result_df[result_df["Status"] == "✗ Åpen"]
        closed_df = result_df[result_df["Status"] == "✓ Betalt"]
        sum_open  = float(open_df["Gjenstår"].sum()) if not open_df.empty else 0.0

        win = _make_popup(self, title=f"Åpne poster  —  {title_str}", geometry="940x440")

        ttk.Label(
            win,
            text=(f"✗ {len(open_df)} åpne fakturaer   ✓ {len(closed_df)} betalt i samme år   "
                  f"|   Sum åpne: {formatting.fmt_amount(sum_open, dec)}"),
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 2))
        ttk.Label(
            win,
            text=("Matching: faktura-bilag mot betalings-bilag via faktura-nr i Tekst.  "
                  "Åpne poster = fakturaer uten tilsvarende betaling i samme periode."),
            foreground="#666", font=("TkDefaultFont", 8),
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
        if self._subsequent_df is not None:
            ttk.Button(
                btns, text=f"Matcher mot {self._subsequent_label[:30]}\u2026",
                command=self._show_subsequent_match_popup,
            ).pack(side="left")
        ttk.Button(btns, text="Lukk", command=win.destroy).pack(side="right")

    def _open_subsequent_period(self) -> None:
        """Last inn SAF-T for etterfølgende periode og match mot åpne poster."""
        try:
            from tkinter import filedialog
        except Exception:
            return

        path = filedialog.askopenfilename(
            parent=self,
            title="Velg SAF-T for etterfølgende periode (zip/xml)",
            filetypes=[
                ("SAF-T filer", "*.zip *.xml"),
                ("Alle filer",  "*.*"),
            ],
        )
        if not path:
            return

        self._subseq_btn.configure(state="disabled", text="Laster\u2026")

        def _load() -> None:
            try:
                import saft_reader as _sr
                df2 = _sr.read_saft_ledger(path)
                import os
                label = os.path.basename(path)
                self.after(0, lambda: self._on_subseq_loaded(df2, label))
            except Exception as exc:
                log.exception("Etterfølgende SAF-T lasting feilet: %s", exc)
                self.after(0, lambda e=exc: (
                    self._subseq_btn.configure(
                        state="normal",
                        text="Etterfølgende periode\u2026"),
                    self._status_lbl.configure(
                        text=f"Feil ved lasting: {e}"),
                ))

        import threading as _thr
        _thr.Thread(target=_load, daemon=True).start()

    def _on_subseq_loaded(self, df2: pd.DataFrame, label: str) -> None:
        self._subsequent_df    = df2
        self._subsequent_label = label
        self._subseq_btn.configure(
            state="normal",
            text=f"Matcher: {label[:20]}\u2026")
        self._status_lbl.configure(
            text=f"Etterfølgende periode lastet: {label}")
        # Hvis en post allerede er valgt, åpne matching direkte
        if self._selected_nr:
            self._show_subsequent_match_popup()

    def _show_subsequent_match_popup(self) -> None:
        """Vis popup med matching av åpne poster mot etterfølgende periode."""
        if not self._selected_nr or self._df is None or self._subsequent_df is None:
            return

        open_invoices = _compute_open_items(
            self._df, nr=self._selected_nr, mode=self._mode)
        if open_invoices.empty:
            return

        result_df = _match_open_against_period(
            open_invoices, self._subsequent_df,
            nr=self._selected_nr, mode=self._mode)

        dec  = self._detail_decimals()
        navn = self._navn_for_nr(self._selected_nr)

        win = _make_popup(
            self,
            title=(f"Åpne poster vs {self._subsequent_label}  —  "
                   f"{'Kunde' if self._mode == 'kunder' else 'Leverandør'} "
                   f"{self._selected_nr}{' — ' + navn if navn else ''}"),
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
                  f"Matchet mot: {self._subsequent_label}   |   "
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

    def _show_all_transactions(self) -> None:
        """Vis alle transaksjoner for gjeldende modus i detaljpanelet."""
        if self._df is None:
            return

        nr_col   = "Kundenr"   if self._mode == "kunder" else "Leverandørnr"
        if nr_col not in self._df.columns:
            return

        sub = self._df[self._df[nr_col].notna()].copy()
        if not sub.empty and "Dato" in sub.columns:
            sub = sub.sort_values(["Dato", nr_col])

        tree = self._detail_tree
        tree.delete(*tree.get_children())

        cols = list(sub.columns)

        def _v(col: str, row: Any, default: Any = "") -> Any:
            return row[col] if col in cols else default

        total = debet = kredit = 0.0
        dec = self._detail_decimals()
        for _, row in sub.iterrows():
            dato     = str(_v("Dato",      row, ""))[:10]
            bilag    = str(_v("Bilag",     row, ""))
            konto    = str(_v("Konto",     row, ""))
            knavn    = str(_v("Kontonavn", row, ""))
            tekst    = str(_v("Tekst",     row, ""))
            ref      = str(_v("Referanse", row, ""))
            valuta   = str(_v("Valuta",    row, ""))
            mva_kode = str(_v("MVA-kode",  row, ""))
            if mva_kode in ("nan", "None"):
                mva_kode = ""
            try:
                belop = float(_v("Beløp", row, 0.0))
            except (ValueError, TypeError):
                belop = 0.0
            total += belop
            if belop >= 0:
                debet += belop
            else:
                kredit += belop
            tags_row: list[str] = []
            if belop < 0:
                tags_row.append(_TAG_NEG)
            if mva_kode:
                tags_row.append(_TAG_MVA_LINE)
            tree.insert("", "end", values=(
                dato, bilag, konto, knavn, tekst,
                formatting.fmt_amount(belop, dec), mva_kode, "", ref, valuta,
            ), tags=tuple(tags_row))

        tree.insert("", "end", values=(
            "", "", "", "",
            (f"\u03a3 {len(sub)} trans.  "
             f"D: {formatting.fmt_amount(debet, dec)}  "
             f"K: {formatting.fmt_amount(kredit, dec)}"),
            formatting.fmt_amount(total, dec),
            "", "", "", "",
        ), tags=(_TAG_HEADER,))

        mode_str = "kunder" if self._mode == "kunder" else "leverandører"
        self._detail_lbl.configure(
            text=f"Alle {mode_str}  ({len(sub)} transaksjoner, netto {formatting.fmt_amount(total)})")

    # ------------------------------------------------------------------
    # BRREG-sjekk
    # ------------------------------------------------------------------

    def _start_brreg_sjekk(self) -> None:
        """Start bakgrunnstråd som henter BRREG-data for alle synlige poster."""
        if self._master_df is None or self._master_df.empty:
            return

        orgnrs = [
            orgnr for orgnr in self._orgnr_map.values()
            if orgnr and len(orgnr) == 9 and orgnr.isdigit()
        ]
        if not orgnrs:
            self._status_lbl.configure(
                text="Ingen gyldige orgnumre i data. "
                     "Krever SAF-T-fil med RegistrationNumber.")
            return

        self._brreg_btn.configure(state="disabled", text="Henter\u2026")
        total = len(set(orgnrs))
        self._status_lbl.configure(
            text=f"BRREG: henter 0\u202f/\u202f{total}\u2026")

        def _progress(done: int, tot: int) -> None:
            self.after(0, lambda d=done, t=tot: self._status_lbl.configure(
                text=f"BRREG: henter {d}\u202f/\u202f{t}\u2026"))

        def _run() -> None:
            try:
                import brreg_client as _brreg
                results = _brreg.fetch_many(
                    list(set(orgnrs)),
                    progress_cb=_progress,
                    include_regnskap=True,
                )
                self.after(0, lambda r=results: self._on_brreg_done(r))
            except Exception as exc:
                log.exception("BRREG-sjekk feilet: %s", exc)
                self.after(0, lambda: (
                    self._brreg_btn.configure(
                        state="normal", text="BRREG-sjekk\u2026"),
                    self._status_lbl.configure(
                        text=f"BRREG feilet: {exc}"),
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_brreg_done(self, results: dict) -> None:
        """Kalles fra main-tråden når BRREG-henting er ferdig."""
        self._brreg_data.update(results)
        self._apply_filter()
        self._brreg_btn.configure(state="normal", text="BRREG-sjekk\u2026")

        n_ok    = sum(1 for v in results.values() if v.get("enhet"))
        n_total = len(results)
        n_warn  = sum(
            1 for v in results.values()
            if _brreg_has_risk(v.get("enhet") or {}))
        n_no_mva = sum(
            1 for v in results.values()
            if v.get("enhet")
            and not (v["enhet"] or {}).get("registrertIMvaregisteret"))

        parts = [f"BRREG: {n_ok}/{n_total} hentet"]
        if n_warn:
            parts.append(f"\u26a0 {n_warn} med risiko")
        if n_no_mva:
            parts.append(f"\u2717 {n_no_mva} ikke MVA-reg.")
        self._status_lbl.configure(text="  \u2022  ".join(parts))

        # Oppdater BRREG-panelet for valgt rad
        if self._selected_nr:
            orgnr = self._orgnr_map.get(self._selected_nr, "")
            if orgnr:
                self._update_brreg_panel(orgnr)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_excel(self) -> None:
        try:
            import session as _session
            import analyse_export_excel as _xls
            client     = getattr(_session, "client", None) or ""
            year       = str(getattr(_session, "year", "") or "")
            mode_label = "kunder" if self._mode == "kunder" else "leverandorer"
            path = _xls.open_save_dialog(
                title="Eksporter Reskontro",
                default_filename=(
                    f"reskontro_{mode_label}_{client}_{year}.xlsx"
                ).strip("_"),
                master=self,
            )
            if not path:
                return
            master_sheet = _xls.treeview_to_sheet(
                self._master_tree,
                title="Oversikt",
                heading=(
                    f"Reskontro \u2014 "
                    f"{'Kunder' if self._mode == 'kunder' else 'Leverand\u00f8rer'}"
                ),
                bold_tags=(_TAG_HEADER,),
                bg_tags={
                    _TAG_NEG:        "FFEBEE",
                    _TAG_BRREG_WARN: "FFF3CD",
                    _TAG_MVA_WARN:   "FFF8E1",
                },
            )
            detail_sheet = _xls.treeview_to_sheet(
                self._detail_tree,
                title="Transaksjoner",
                heading=f"Transaksjoner: {self._selected_nr}",
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_NEG: "FFEBEE"},
            )
            _xls.export_and_open(
                path, [master_sheet, detail_sheet],
                title="Reskontro", client=client, year=year)
        except Exception as exc:
            log.exception("Reskontro Excel-eksport feilet: %s", exc)
