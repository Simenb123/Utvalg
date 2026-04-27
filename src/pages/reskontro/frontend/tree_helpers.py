"""reskontro_tree_helpers.py — Treeview-hjelpere og byggere for Reskontro.

Pure helpers — ingen klasse-tilstand. Brukes av [page_reskontro.py](page_reskontro.py).

- `_make_popup`, `_setup_tree`: felles Treeview-oppsett (sortering, copy/paste).
- Kolonne- og tag-konstanter for master/detail/open-items/subseq/payments-trær.
- `_has_reskontro_data`, `_build_master`, `_build_detail`: data-byggere.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None  # type: ignore

try:
    from src.shared.ui.treeview_sort import enable_treeview_sorting as _enable_sort
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
_TAG_MOTPOST  = "motpost"   # motpost-linje (innrykket under hovedtransaksjon)

# Visningsnavn i høyrepanelene (må matche verdier i comboboxene)
_UPPER_VIEW_ALLE   = "Alle transaksjoner"
_UPPER_VIEW_APNE   = "\u00c5pne poster"
_LOWER_VIEW_BRREG  = "BRREG-info"
_LOWER_VIEW_NESTE  = "Transaksjoner neste periode"
_LOWER_VIEW_BETALT = "Betalinger"

_OPEN_ITEMS_COLS = (
    "Status", "Dato", "Bilag", "FakturaNr", "Tekst",
    "Fakturabeløp", "Betalt (i år)", "Gjenstår",
)
_SUBSEQ_COLS = (
    "Dato", "Bilag", "Konto", "Kontonavn", "Tekst",
    "Beløp", "MVA-kode", "MVA-beløp", "Referanse",
)
_PAYMENTS_COLS = (
    "Status", "FakturaBilag", "FakturaNr",
    "Betaling dato", "Betaling bilag", "Betaling tekst",
    "Betalt beløp", "Resterende",
)

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
