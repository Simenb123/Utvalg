"""page_driftsmidler.py — Driftsmiddelavstemming.

Automatisk kategorisering av DM-transaksjoner via motpostlogikk:
  - Motpost i avskrivningsrange → Avskrivning
  - Motpost i leverandør/bank   → Tilgang / Avgang
  - Motpost i salg/gevinst-tap  → Avgang
  - Annen DM-konto              → Omklassifisering
  - Alt annet                   → Ukjent

Avstemmer: IB + Tilgang - Avgang = UB (kostpris), kontrollert mot SB.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any

import pandas as pd

import analyse_treewidths
import formatting

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hjelpefunksjoner (gjenbruk fra page_statistikk-mønster)
# ---------------------------------------------------------------------------

def _get_konto_ranges(page: Any, regnr: int) -> list[tuple[int, int]]:
    """Hent kontorange for et regnr fra analyse-sidens intervaller."""
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    if intervals is None or (hasattr(intervals, "empty") and intervals.empty):
        return []
    leaf_set: set[int] = {regnr}
    if regnskapslinjer is not None and not (hasattr(regnskapslinjer, "empty") and regnskapslinjer.empty):
        try:
            from regnskap_mapping import expand_regnskapslinje_selection, normalize_regnskapslinjer
            regn = normalize_regnskapslinjer(regnskapslinjer)
            if bool(regn.loc[regn["regnr"].astype(int) == regnr, "sumpost"].any()):
                expanded = expand_regnskapslinje_selection(
                    regnskapslinjer=regnskapslinjer, selected_regnr=[regnr])
                if expanded:
                    leaf_set = set(expanded)
        except Exception as exc:
            log.warning("_get_konto_ranges: %s", exc)
    ranges: list[tuple[int, int]] = []
    try:
        for _, row in intervals.iterrows():
            if int(row["regnr"]) in leaf_set:
                ranges.append((int(row["fra"]), int(row["til"])))
    except Exception as exc:
        log.warning("_get_konto_ranges loop: %s", exc)
    return ranges


def _in_ranges(konto_num: float, ranges: list[tuple[int, int]]) -> bool:
    for fra, til in ranges:
        if fra <= konto_num <= til:
            return True
    return False


def _filter_sb(sb_df: pd.DataFrame, ranges: list[tuple[int, int]]) -> pd.DataFrame:
    """Filtrer saldobalanse til kontoer innenfor gitte ranges."""
    if sb_df is None or sb_df.empty or "konto" not in sb_df.columns:
        return pd.DataFrame(columns=["konto", "kontonavn", "ib", "ub"])
    sb = sb_df.copy()
    sb["_knum"] = pd.to_numeric(sb["konto"], errors="coerce")
    mask = pd.Series(False, index=sb.index)
    for fra, til in ranges:
        mask |= (sb["_knum"] >= fra) & (sb["_knum"] <= til)
    return sb.loc[mask].drop(columns=["_knum"])


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Transaksjonskategorisering
# ---------------------------------------------------------------------------

_LEVERANDOR_RANGES = [(2400, 2499)]
_BANK_RANGES = [(1900, 1999)]
_SALG_RANGES = [(3000, 3999)]
_GEVINST_TAP_RANGES = [(8000, 8199)]


def _build_range_mask(series: pd.Series, ranges: list[tuple[int, int]]) -> pd.Series:
    """Vektorisert sjekk om verdier er innenfor noen av rangene."""
    mask = pd.Series(False, index=series.index)
    for fra, til in ranges:
        mask |= (series >= fra) & (series <= til)
    return mask


def _classify_dm_transactions(
    df_all: pd.DataFrame,
    dm_ranges: list[tuple[int, int]],
    avskr_ranges: list[tuple[int, int]],
) -> pd.DataFrame:
    """Klassifiser DM-transaksjoner basert på motpost (vektorisert).

    Returnerer DataFrame med DM-transaksjonene pluss kolonner:
      _konto_num, _bilag, _belop, _motpost_konto, _motpost_navn, dm_kategori
    """
    if df_all is None or df_all.empty or "Konto" not in df_all.columns:
        return pd.DataFrame()

    df = df_all.copy()
    df["_konto_num"] = pd.to_numeric(df["Konto"], errors="coerce")
    df["_bilag"] = df["Bilag"].astype(str).str.strip()
    df["_belop"] = pd.to_numeric(df.get("Beløp", 0), errors="coerce").fillna(0.0)

    # Identifiser DM-rader (vektorisert)
    dm_mask = _build_range_mask(df["_konto_num"], dm_ranges)
    dm_df = df.loc[dm_mask].copy()
    if dm_df.empty:
        return pd.DataFrame()

    # Finn alle rader på bilag som inneholder DM-transaksjoner
    dm_bilags = dm_df["_bilag"].unique()
    all_on_bilags = df[df["_bilag"].isin(dm_bilags)].copy()

    # Filtrer ut DM-rader selv → bare motposter
    non_dm = all_on_bilags[~_build_range_mask(all_on_bilags["_konto_num"], dm_ranges)].copy()

    if non_dm.empty:
        dm_df["dm_kategori"] = "Ukjent"
        dm_df["_motpost_konto"] = ""
        dm_df["_motpost_navn"] = ""
        return dm_df

    # Klassifiser motposter vektorisert
    non_dm["_mp_avskr"] = _build_range_mask(non_dm["_konto_num"], avskr_ranges)
    non_dm["_mp_salg"] = _build_range_mask(non_dm["_konto_num"], _SALG_RANGES + _GEVINST_TAP_RANGES)
    non_dm["_mp_lev_bank"] = _build_range_mask(non_dm["_konto_num"], _LEVERANDOR_RANGES + _BANK_RANGES)
    non_dm["_mp_dm"] = _build_range_mask(non_dm["_konto_num"], dm_ranges)

    # Per bilag: aggreger motpost-flagg + ta første motpost-konto for visning
    bilag_flags = non_dm.groupby("_bilag", sort=False).agg(
        has_avskr=("_mp_avskr", "any"),
        has_salg=("_mp_salg", "any"),
        has_lev_bank=("_mp_lev_bank", "any"),
        has_dm=("_mp_dm", "any"),
        first_konto=("_konto_num", "first"),
        first_navn=("Kontonavn", "first"),
    )

    # Join flagg til DM-transaksjoner
    dm_df = dm_df.join(bilag_flags, on="_bilag", how="left")

    # Fyll NaN for bilag uten motposter
    for col in ("has_avskr", "has_salg", "has_lev_bank", "has_dm"):
        dm_df[col] = dm_df[col].fillna(False)

    # Vektorisert klassifisering med prioritet
    dm_df["dm_kategori"] = "Ukjent"
    dm_df.loc[dm_df["has_dm"], "dm_kategori"] = "Omklassifisering"
    # Lev/bank: Tilgang eller Avgang basert på fortegn
    lev_bank_mask = dm_df["has_lev_bank"]
    dm_df.loc[lev_bank_mask & (dm_df["_belop"] > 0), "dm_kategori"] = "Tilgang"
    dm_df.loc[lev_bank_mask & (dm_df["_belop"] <= 0), "dm_kategori"] = "Avgang"
    dm_df.loc[dm_df["has_salg"], "dm_kategori"] = "Avgang"
    dm_df.loc[dm_df["has_avskr"], "dm_kategori"] = "Avskrivning"

    # Motpost for visning
    dm_df["_motpost_konto"] = dm_df["first_konto"].apply(
        lambda v: str(int(v)) if pd.notna(v) else "")
    dm_df["_motpost_navn"] = dm_df["first_navn"].fillna("")

    # Rydd opp hjelpekolonner
    dm_df.drop(columns=["has_avskr", "has_salg", "has_lev_bank", "has_dm",
                         "first_konto", "first_navn"],
               inplace=True, errors="ignore")
    return dm_df


# ---------------------------------------------------------------------------
# Avstemmingsoppstilling
# ---------------------------------------------------------------------------

def _build_dm_reconciliation(
    sb_df: pd.DataFrame,
    classified_df: pd.DataFrame,
    dm_ranges: list[tuple[int, int]],
    regnr_555_ub: float | None = None,
) -> dict[str, Any]:
    """Bygg avstemming for varige driftsmidler."""
    result: dict[str, Any] = {
        "kostpris_ib": 0.0, "tilgang": 0.0, "avgang": 0.0,
        "kostpris_ub_beregnet": 0.0, "kostpris_ub_sb": 0.0, "kostpris_avvik": 0.0,
        "avskr_ib": 0.0, "avskr_aar": 0.0,
        "avskr_ub_beregnet": 0.0, "avskr_ub_sb": 0.0, "avskr_avvik": 0.0,
        "bokfort_verdi": 0.0, "regnr_555_ub": regnr_555_ub,
        "ukjente_tx": 0, "omklassifisering": 0.0,
        "tilgang_tx": 0, "avgang_tx": 0, "avskr_tx": 0,
        "kontoer": pd.DataFrame(),
    }

    dm_sb = _filter_sb(sb_df, dm_ranges)
    if dm_sb.empty:
        return result

    # Skille kostpris vs akk. avskrivning basert på UB-fortegn
    dm_sb["_ub"] = dm_sb["ub"].apply(_safe_float)
    dm_sb["_ib"] = dm_sb["ib"].apply(_safe_float)
    # Kostpriskonti: positiv UB (eller IB hvis UB=0)
    # Akk.avskr.konti: negativ UB
    dm_sb["_type"] = dm_sb.apply(
        lambda r: "Akk. avskr." if r["_ub"] < -0.01 or (abs(r["_ub"]) < 0.01 and r["_ib"] < -0.01)
        else "Kostpris", axis=1)

    kostpris_sb = dm_sb[dm_sb["_type"] == "Kostpris"]
    avskr_sb = dm_sb[dm_sb["_type"] == "Akk. avskr."]

    result["kostpris_ib"] = kostpris_sb["_ib"].sum()
    result["kostpris_ub_sb"] = kostpris_sb["_ub"].sum()
    result["avskr_ib"] = avskr_sb["_ib"].sum()
    result["avskr_ub_sb"] = avskr_sb["_ub"].sum()

    # Summér klassifiserte transaksjoner
    if classified_df is not None and not classified_df.empty:
        for kat in ("Tilgang", "Avgang", "Avskrivning", "Omklassifisering", "Ukjent"):
            mask = classified_df["dm_kategori"] == kat
            s = classified_df.loc[mask, "_belop"].sum()
            cnt = int(mask.sum())
            if kat == "Tilgang":
                result["tilgang"] = s
                result["tilgang_tx"] = cnt
            elif kat == "Avgang":
                result["avgang"] = s
                result["avgang_tx"] = cnt
            elif kat == "Avskrivning":
                result["avskr_aar"] = s
                result["avskr_tx"] = cnt
            elif kat == "Omklassifisering":
                result["omklassifisering"] = s
            elif kat == "Ukjent":
                result["ukjente_tx"] = cnt

    result["kostpris_ub_beregnet"] = result["kostpris_ib"] + result["tilgang"] + result["avgang"]
    result["kostpris_avvik"] = result["kostpris_ub_beregnet"] - result["kostpris_ub_sb"]

    result["avskr_ub_beregnet"] = result["avskr_ib"] + result["avskr_aar"]
    result["avskr_avvik"] = result["avskr_ub_beregnet"] - result["avskr_ub_sb"]

    result["bokfort_verdi"] = result["kostpris_ub_sb"] + result["avskr_ub_sb"]

    # Konto-oversikt for tab
    dm_sb_out = dm_sb[["konto", "ib", "ub", "_type"]].copy()
    if "kontonavn" in dm_sb.columns:
        dm_sb_out.insert(1, "kontonavn", dm_sb["kontonavn"])
    dm_sb_out["bevegelse"] = dm_sb_out["ub"].apply(_safe_float) - dm_sb_out["ib"].apply(_safe_float)
    result["kontoer"] = dm_sb_out

    return result


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

_TAG_HEADER = "header"
_FMT = formatting.fmt_amount


class DriftsmidlerPage(ttk.Frame):
    """Driftsmidler-fane med automatisk avstemming."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        self._analyse_page: Any = None
        self._reconciliation: dict[str, Any] | None = None
        self._classified_df: pd.DataFrame | None = None
        self._build_ui()

    # --- Public API ---

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session: Any = None, **_kw: Any) -> None:
        try:
            self.after(50, self._refresh)
        except Exception:
            self._refresh()

    def get_note_data(self) -> dict[str, str]:
        """Returnér data for auto-fylling av DRIFTSMIDLER_SPEC."""
        r = self._reconciliation
        if not r:
            return {}
        return {
            "dm_akk_01": _FMT(r["kostpris_ib"], 0),
            "dm_tilgang": _FMT(r["tilgang"], 0),
            "dm_avgang": _FMT(r["avgang"], 0),
            "dm_akk_31": _FMT(r["kostpris_ub_sb"], 0),
            "dm_avskr_01": _FMT(r["avskr_ib"], 0),
            "dm_avskr_aar": _FMT(r["avskr_aar"], 0),
            "dm_avskr_31": _FMT(r["avskr_ub_sb"], 0),
        }

    # --- UI ---

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Toolbar
        top = ttk.Frame(self, padding=(8, 6, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self._status_var = tk.StringVar(value="Laster...")
        ttk.Label(top, textvariable=self._status_var,
                  font=("TkDefaultFont", 9)).grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(
            row=0, column=1, padx=(8, 0))

        # Avstemming (LabelFrame)
        self._lf_recon = ttk.LabelFrame(self, text="Avstemming — varige driftsmidler",
                                        padding=(8, 4, 8, 6))
        self._lf_recon.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._lf_recon.columnconfigure(1, weight=1)

        self._recon_vars: dict[str, tk.StringVar] = {}
        rows = [
            ("header_kp", "KOSTPRIS", None),
            ("kostpris_ib", "Anskaffelseskost 01.01", ""),
            ("tilgang", "+ Tilgang", ""),
            ("avgang", "- Avgang", ""),
            ("kostpris_ub", "= Anskaffelseskost 31.12", ""),
            ("kostpris_ctrl", "  Kontroll (SB UB)", ""),
            ("sep1", None, None),
            ("header_av", "AKK. AVSKRIVNINGER", None),
            ("avskr_ib", "01.01", ""),
            ("avskr_aar", "+ Årets avskrivninger", ""),
            ("avskr_ub", "= 31.12", ""),
            ("avskr_ctrl", "  Kontroll (SB UB)", ""),
            ("sep2", None, None),
            ("bokfort", "BOKFØRT VERDI 31.12", ""),
            ("bokfort_ctrl", "  Kontroll (regnr 555)", ""),
        ]

        for i, (key, label, default) in enumerate(rows):
            if key.startswith("sep"):
                ttk.Separator(self._lf_recon, orient="horizontal").grid(
                    row=i, column=0, columnspan=3, sticky="ew", pady=3)
                continue
            if key.startswith("header"):
                ttk.Label(self._lf_recon, text=label,
                          font=("TkDefaultFont", 9, "bold")).grid(
                    row=i, column=0, columnspan=3, sticky="w", pady=(4, 1))
                continue
            ttk.Label(self._lf_recon, text=label).grid(
                row=i, column=0, sticky="w", padx=(12, 6))
            svar = tk.StringVar(value=default or "")
            self._recon_vars[key] = svar
            ttk.Label(self._lf_recon, textvariable=svar, anchor="e",
                      width=18).grid(row=i, column=1, sticky="e", padx=(0, 6))

        self._recon_info_var = tk.StringVar(value="")
        ttk.Label(self._lf_recon, textvariable=self._recon_info_var,
                  foreground="#555", font=("TkDefaultFont", 8)).grid(
            row=len(rows), column=0, columnspan=3, sticky="w", pady=(4, 0))

        # Tabs: Kontoer + Transaksjoner
        nb = ttk.Notebook(self)
        nb.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))

        # Tab: Kontoer
        tab_konto = ttk.Frame(nb)
        tab_konto.columnconfigure(0, weight=1)
        tab_konto.rowconfigure(0, weight=1)
        nb.add(tab_konto, text="Kontoer")

        konto_cols = ("Konto", "Kontonavn", "IB", "Bevegelse", "UB", "Type")
        self._tree_konto = ttk.Treeview(tab_konto, columns=konto_cols,
                                        show="headings", height=8)
        for c in konto_cols:
            anchor = analyse_treewidths.column_anchor(c)
            self._tree_konto.heading(c, text=c, anchor=anchor)
            self._tree_konto.column(
                c,
                width=analyse_treewidths.default_column_width(c),
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=anchor,
                stretch=c == "Kontonavn",
            )
        vsb_k = ttk.Scrollbar(tab_konto, orient="vertical",
                               command=self._tree_konto.yview)
        self._tree_konto.configure(yscrollcommand=vsb_k.set)
        self._tree_konto.grid(row=0, column=0, sticky="nsew")
        vsb_k.grid(row=0, column=1, sticky="ns")

        # Tab: Transaksjoner
        tab_tx = ttk.Frame(nb)
        tab_tx.columnconfigure(0, weight=1)
        tab_tx.rowconfigure(0, weight=1)
        nb.add(tab_tx, text="Transaksjoner")

        tx_cols = ("Bilag", "Dato", "Konto", "Kontonavn", "Tekst",
                   "Beløp", "Motpost", "Kategori")
        self._tree_tx = ttk.Treeview(tab_tx, columns=tx_cols,
                                     show="headings", height=12)
        for c in tx_cols:
            anchor = analyse_treewidths.column_anchor(c)
            self._tree_tx.heading(c, text=c, anchor=anchor)
            self._tree_tx.column(
                c,
                width=analyse_treewidths.default_column_width(c),
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=anchor,
                stretch=c == "Tekst",
            )
        self._tree_tx.tag_configure("tilgang", foreground="#1a7a2a")
        self._tree_tx.tag_configure("avgang", foreground="#C00000")
        self._tree_tx.tag_configure("avskrivning", foreground="#1a5fa8")
        self._tree_tx.tag_configure("ukjent", foreground="#C00000",
                                    background="#FFF8E1")
        self._tree_tx.tag_configure("omklassifisering", foreground="#666")

        vsb_t = ttk.Scrollbar(tab_tx, orient="vertical",
                               command=self._tree_tx.yview)
        self._tree_tx.configure(yscrollcommand=vsb_t.set)
        self._tree_tx.grid(row=0, column=0, sticky="nsew")
        vsb_t.grid(row=0, column=1, sticky="ns")

    # --- Data refresh ---

    def _refresh(self) -> None:
        page = self._analyse_page
        if page is None:
            self._status_var.set("Ikke koblet til Analyse-siden")
            return

        df_all = getattr(page, "_df_filtered", None)
        if df_all is None or (hasattr(df_all, "empty") and df_all.empty):
            self._status_var.set("Ingen transaksjonsdata lastet")
            return

        try:
            sb_df = page._get_effective_sb_df()
        except Exception:
            sb_df = getattr(page, "_rl_sb_df", None)

        dm_ranges = _get_konto_ranges(page, 555)
        avskr_ranges = _get_konto_ranges(page, 50)

        if not dm_ranges:
            self._status_var.set("Ingen kontorange for regnr 555 (varige driftsmidler)")
            return

        # Klassifiser transaksjoner
        classified = _classify_dm_transactions(df_all, dm_ranges, avskr_ranges)
        self._classified_df = classified

        # Hent regnr 555 UB fra pivot. Bruk _pivot_df_rl (RL-spesifikk),
        # ikke _pivot_df_last — sistnevnte kan være konto-pivot uten regnr.
        regnr_555_ub = None
        pivot_df = getattr(page, "_pivot_df_rl", None)
        if pivot_df is not None and not pivot_df.empty and "regnr" in pivot_df.columns:
            row_555 = pivot_df[pivot_df["regnr"].astype(int) == 555]
            if not row_555.empty and "UB" in row_555.columns:
                regnr_555_ub = _safe_float(row_555["UB"].iloc[0])

        # Bygg avstemming
        recon = _build_dm_reconciliation(sb_df, classified, dm_ranges,
                                         regnr_555_ub=regnr_555_ub)
        self._reconciliation = recon

        # Oppdater GUI
        n_kontoer = len(recon["kontoer"]) if isinstance(recon["kontoer"], pd.DataFrame) else 0
        n_tx = len(classified) if classified is not None and not classified.empty else 0
        self._status_var.set(
            f"Regnr 555 — {n_kontoer} kontoer — {n_tx} transaksjoner")

        self._populate_reconciliation(recon)
        self._populate_accounts(recon.get("kontoer", pd.DataFrame()))
        self._populate_transactions(classified)

    def _populate_reconciliation(self, r: dict[str, Any]) -> None:
        f = lambda v: _FMT(v, 0) if v is not None else "–"

        def _check(avvik: float) -> str:
            return "✓" if abs(avvik) < 1.0 else f"⚠ avvik {_FMT(avvik, 0)}"

        self._recon_vars["kostpris_ib"].set(f(r["kostpris_ib"]))
        self._recon_vars["tilgang"].set(
            f"{f(r['tilgang'])}   ({r['tilgang_tx']} tx)")
        self._recon_vars["avgang"].set(
            f"{f(r['avgang'])}   ({r['avgang_tx']} tx)")
        self._recon_vars["kostpris_ub"].set(f(r["kostpris_ub_beregnet"]))
        self._recon_vars["kostpris_ctrl"].set(
            f"{f(r['kostpris_ub_sb'])}   {_check(r['kostpris_avvik'])}")

        self._recon_vars["avskr_ib"].set(f(r["avskr_ib"]))
        self._recon_vars["avskr_aar"].set(
            f"{f(r['avskr_aar'])}   ({r['avskr_tx']} tx)")
        self._recon_vars["avskr_ub"].set(f(r["avskr_ub_beregnet"]))
        self._recon_vars["avskr_ctrl"].set(
            f"{f(r['avskr_ub_sb'])}   {_check(r['avskr_avvik'])}")

        self._recon_vars["bokfort"].set(f(r["bokfort_verdi"]))
        regnr_ub = r.get("regnr_555_ub")
        if regnr_ub is not None:
            diff = abs(r["bokfort_verdi"] - regnr_ub)
            self._recon_vars["bokfort_ctrl"].set(
                f"{f(regnr_ub)}   {_check(diff)}")
        else:
            self._recon_vars["bokfort_ctrl"].set("–")

        # Info
        parts = []
        if r["ukjente_tx"] > 0:
            parts.append(f"⚠ {r['ukjente_tx']} transaksjoner ikke klassifisert")
        if abs(r["omklassifisering"]) > 0.01:
            parts.append(f"Omklassifisering: {_FMT(r['omklassifisering'], 0)}")
        self._recon_info_var.set("  |  ".join(parts) if parts else "")

    def _populate_accounts(self, df: pd.DataFrame) -> None:
        tree = self._tree_konto
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            tree.insert("", "end", values=(
                str(row.get("konto", "")),
                str(row.get("kontonavn", "")),
                _FMT(_safe_float(row.get("ib")), 0),
                _FMT(_safe_float(row.get("bevegelse")), 0),
                _FMT(_safe_float(row.get("ub")), 0),
                str(row.get("_type", "")),
            ))

    def _populate_transactions(self, df: pd.DataFrame) -> None:
        tree = self._tree_tx
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            return

        tag_map = {
            "Tilgang": "tilgang", "Avgang": "avgang",
            "Avskrivning": "avskrivning", "Ukjent": "ukjent",
            "Omklassifisering": "omklassifisering",
        }

        # Bruk .itertuples() for raskere iterasjon (5-10x vs iterrows)
        cols = {c: i for i, c in enumerate(df.columns)}
        for tup in df.itertuples(index=False):
            kat = str(tup[cols["dm_kategori"]]) if "dm_kategori" in cols else ""
            tag = tag_map.get(kat, "")
            motpost = str(tup[cols["_motpost_konto"]]) if "_motpost_konto" in cols else ""
            motpost_navn = str(tup[cols["_motpost_navn"]]) if "_motpost_navn" in cols else ""
            motpost_str = f"{motpost} {motpost_navn}".strip() if motpost else ""
            bilag = str(tup[cols["_bilag"]]) if "_bilag" in cols else str(tup[cols.get("Bilag", 0)])
            dato = str(tup[cols["Dato"]])[:10] if "Dato" in cols else ""

            tree.insert("", "end", values=(
                bilag, dato,
                str(tup[cols.get("Konto", 0)]),
                str(tup[cols.get("Kontonavn", 0)]) if "Kontonavn" in cols else "",
                str(tup[cols.get("Tekst", 0)]) if "Tekst" in cols else "",
                _FMT(tup[cols["_belop"]]) if "_belop" in cols else "",
                motpost_str,
                kat,
            ), tags=(tag,) if tag else ())
