"""reskontro_report_engine.py — Beregningsmotor for reskontrorapporten.

Tar rå SAF-T/HB-data (samme DataFrame som `ReskontroPage` bruker) og bygger et
strukturert `ReskontroReport`-objekt som kan rendres til HTML/PDF/Excel.

Motoren dekker både kunder og leverandører via `mode`-parameteren. Design og
fortegnskonvensjoner er felles:

  - Kunder: positiv UB = kundens gjeld til selskapet.
  - Leverandører: vi flipper fortegn på IB/UB og debet/kredit internt slik at
    UB presenteres som positiv gjeld til leverandør (speiler balansen) og
    "topp debet-bevegelse" betyr største utbetalinger.

Ingen avhengigheter til Tk/Excel/HTML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence

import pandas as pd

Mode = Literal["kunder", "leverandorer"]


# ---------------------------------------------------------------------------
# Dataklasser
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PartyRow:
    """Én rad per kunde/leverandør med nøkkeltall for perioden."""
    nr: str
    navn: str
    orgnr: str
    antall: int
    ib: float
    debet: float
    kredit: float
    ub: float
    dager_siden_siste: Optional[int] = None  # None hvis ingen transaksjon / ingen dato
    snitt_bilag: float = 0.0
    hb_konto: str = ""


@dataclass(frozen=True)
class TransactionRow:
    """Én enkelttransaksjon — brukes for topp-N størst enkelpost."""
    dato: str
    bilag: str
    konto: str
    motkonto: str
    tekst: str
    nr: str  # Kundenr/Leverandørnr
    navn: str
    belop: float


@dataclass(frozen=True)
class HbAccountRow:
    """En HB-konto (reskontrokonto) med sum-data."""
    konto: str
    kontonavn: str
    antall: int
    ib: float
    bevegelse: float
    ub: float


@dataclass(frozen=True)
class MotpostRow:
    """Motpostkonto som opptrer mot reskontrokontoene."""
    konto: str
    kontonavn: str
    antall: int
    sum_belop: float
    andel_pct: float


@dataclass(frozen=True)
class AgingBucket:
    label: str
    sum_gjenstar: float
    antall: int


@dataclass
class ReskontroReport:
    """Strukturert rapportinnhold, klar for rendering."""
    mode: Mode
    client: str = ""
    year: str = ""
    reference_date: str = ""  # YYYY-MM-DD, brukes for aldersanalyse

    # KPI
    kpi: dict = field(default_factory=dict)

    # HB-kontoer reskontroen består av
    hb_accounts: list[HbAccountRow] = field(default_factory=list)
    hb_reconciliation: dict = field(default_factory=dict)

    # Topp-lister (N konfigurerbar, default 10)
    top_ub: list[PartyRow] = field(default_factory=list)
    top_signed_bevegelse: list[PartyRow] = field(default_factory=list)  # kredit for kunder / debet for lev
    top_activity: list[PartyRow] = field(default_factory=list)  # |debet| + |kredit|
    top_transactions: list[TransactionRow] = field(default_factory=list)

    # "Motsatt fortegn"-poster: kunder med negativ UB / lev med positiv UB
    counter_balance_rows: list[PartyRow] = field(default_factory=list)

    # Motpost-analyse
    motpost_debet: list[MotpostRow] = field(default_factory=list)
    motpost_kredit: list[MotpostRow] = field(default_factory=list)

    # Konsentrasjon
    concentration: dict = field(default_factory=dict)

    # Aldersanalyse
    aging: list[AgingBucket] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Kolonne-konvensjoner
# ---------------------------------------------------------------------------

def _cols(mode: Mode) -> dict[str, str]:
    if mode == "kunder":
        return {
            "nr": "Kundenr",
            "navn": "Kundenavn",
            "orgnr": "Kundeorgnr",
            "ib": "KundeIB",
            "ub": "KundeUB",
            "konto": "KundeKonto",
        }
    return {
        "nr": "Leverandørnr",
        "navn": "Leverandørnavn",
        "orgnr": "Leverandørorgnr",
        "ib": "LeverandørIB",
        "ub": "LeverandørUB",
        "konto": "LeverandørKonto",
    }


def _sign(mode: Mode) -> float:
    """Fortegn for visning: leverandører flippes slik at UB vises positiv."""
    return 1.0 if mode == "kunder" else -1.0


# ---------------------------------------------------------------------------
# Filtrering
# ---------------------------------------------------------------------------

def _filter_to_reskontro(df: pd.DataFrame, *, mode: Mode) -> pd.DataFrame:
    """Behold kun rader som tilhører valgte reskontrotype (har nr)."""
    c = _cols(mode)
    if c["nr"] not in df.columns:
        return df.iloc[0:0].copy()
    mask = df[c["nr"]].notna() & (df[c["nr"]].astype(str).str.strip() != "")
    return df.loc[mask].copy()


# ---------------------------------------------------------------------------
# Parti-rader (kunder/leverandører — speiler _build_master)
# ---------------------------------------------------------------------------

def _build_party_rows(
    df: pd.DataFrame, *, mode: Mode, reference_date: str = ""
) -> list[PartyRow]:
    c = _cols(mode)
    sign = _sign(mode)
    if c["nr"] not in df.columns:
        return []

    sub = _filter_to_reskontro(df, mode=mode)
    if sub.empty:
        return []

    sub["__nr__"] = sub[c["nr"]].astype(str).str.strip()
    sub["__navn__"] = (
        sub[c["navn"]].astype(str).str.strip()
        if c["navn"] in sub.columns else ""
    )
    sub["__orgnr__"] = (
        sub[c["orgnr"]].astype(str).str.strip()
        if c["orgnr"] in sub.columns else ""
    )
    sub["__belop__"] = (
        pd.to_numeric(sub["Beløp"], errors="coerce").fillna(0.0)
        if "Beløp" in sub.columns else pd.Series(0.0, index=sub.index)
    )
    sub["__konto__"] = (
        sub[c["konto"]].astype(str).str.strip()
        if c["konto"] in sub.columns else ""
    )
    sub["__dato__"] = (
        pd.to_datetime(sub["Dato"], errors="coerce")
        if "Dato" in sub.columns else pd.NaT
    )

    # Debet/kredit på rå SAF-T-konvensjon (uavhengig av sign-flip for visning)
    sub["__debet__"] = sub["__belop__"].where(sub["__belop__"] > 0, 0.0)
    sub["__kredit__"] = (-sub["__belop__"]).where(sub["__belop__"] < 0, 0.0)

    grp = sub.groupby("__nr__", sort=False)

    has_saft_bal = (
        c["ib"] in sub.columns and sub[c["ib"]].notna().any()
        and c["ub"] in sub.columns and sub[c["ub"]].notna().any()
    )
    if has_saft_bal:
        sub["__ib__"] = pd.to_numeric(sub[c["ib"]], errors="coerce")
        sub["__ub__"] = pd.to_numeric(sub[c["ub"]], errors="coerce")
        ib_s = grp["__ib__"].first().fillna(0.0)
        ub_s = grp["__ub__"].first().fillna(0.0)
    else:
        bev = grp["__belop__"].sum()
        ib_s = pd.Series(0.0, index=bev.index)
        ub_s = bev

    navn_s = grp["__navn__"].first()
    orgnr_s = grp["__orgnr__"].first()
    konto_s = grp["__konto__"].first()
    antall_s = grp["__nr__"].count()
    debet_s = grp["__debet__"].sum()
    kredit_s = grp["__kredit__"].sum()

    # Siste dato per nr — dager siden siste transaksjon
    ref_ts: Optional[pd.Timestamp] = None
    if reference_date:
        try:
            ref_ts = pd.to_datetime(reference_date[:10])
        except Exception:
            ref_ts = None

    if ref_ts is not None:
        siste_dato = grp["__dato__"].max()
    else:
        siste_dato = None

    rows: list[PartyRow] = []
    for nr in navn_s.index:
        ant = int(antall_s.loc[nr])
        deb = float(debet_s.loc[nr])
        kre = float(kredit_s.loc[nr])
        brutto = deb + kre
        snitt = (brutto / ant) if ant else 0.0

        dager: Optional[int] = None
        if siste_dato is not None and ref_ts is not None:
            sd = siste_dato.loc[nr]
            if pd.notna(sd):
                try:
                    dager = int((ref_ts - pd.Timestamp(sd)).days)
                except Exception:
                    dager = None

        rows.append(PartyRow(
            nr=str(nr),
            navn=str(navn_s.loc[nr] or "").strip(),
            orgnr=str(orgnr_s.loc[nr] or "").strip().replace("nan", ""),
            antall=ant,
            ib=float(ib_s.loc[nr]) * sign,
            debet=deb,
            kredit=kre,
            ub=float(ub_s.loc[nr]) * sign,
            dager_siden_siste=dager,
            snitt_bilag=snitt,
            hb_konto=str(konto_s.loc[nr] or "").strip().replace("nan", ""),
        ))
    return rows


# ---------------------------------------------------------------------------
# Topp-N
# ---------------------------------------------------------------------------

def _top_by(rows: Sequence[PartyRow], *, key, n: int, min_abs: float = 0.01) -> list[PartyRow]:
    filtered = [r for r in rows if abs(key(r)) > min_abs]
    return sorted(filtered, key=lambda r: abs(key(r)), reverse=True)[:n]


def _top_transactions(
    df: pd.DataFrame, *, mode: Mode, n: int
) -> list[TransactionRow]:
    """Topp-N enkelttransaksjoner etter |beløp|."""
    c = _cols(mode)
    sub = _filter_to_reskontro(df, mode=mode)
    if sub.empty or "Beløp" not in sub.columns:
        return []

    sub = sub.copy()
    sub["__belop__"] = pd.to_numeric(sub["Beløp"], errors="coerce").fillna(0.0)
    sub["__abs__"] = sub["__belop__"].abs()
    top = sub.nlargest(n, "__abs__")

    out: list[TransactionRow] = []
    for _, row in top.iterrows():
        out.append(TransactionRow(
            dato=str(row.get("Dato", ""))[:10],
            bilag=str(row.get("Bilag", "")).strip(),
            konto=str(row.get("Konto", "")).strip(),
            motkonto=str(row.get("Motkonto", "")).strip() if "Motkonto" in sub.columns else "",
            tekst=str(row.get("Tekst", "") or "").strip(),
            nr=str(row.get(c["nr"], "")).strip(),
            navn=str(row.get(c["navn"], "") or "").strip() if c["navn"] in sub.columns else "",
            belop=float(row["__belop__"]),
        ))
    return out


# ---------------------------------------------------------------------------
# HB-kontoer reskontroen består av
# ---------------------------------------------------------------------------

def _build_hb_accounts(df: pd.DataFrame, *, mode: Mode) -> list[HbAccountRow]:
    """Aggregér per reskontrokonto (HB-kontoen posten ligger på)."""
    c = _cols(mode)
    sub = _filter_to_reskontro(df, mode=mode)
    if sub.empty:
        return []

    if "Konto" not in sub.columns:
        konto_source = c["konto"] if c["konto"] in sub.columns else None
        if konto_source is None:
            return []
        sub = sub.assign(Konto=sub[konto_source])

    sub = sub.copy()
    sub["__konto__"] = sub["Konto"].astype(str).str.strip()
    sub["__belop__"] = pd.to_numeric(sub.get("Beløp", 0), errors="coerce").fillna(0.0)
    if "Kontonavn" in sub.columns:
        sub["__kontonavn__"] = sub["Kontonavn"].fillna("").astype(str)
    else:
        sub["__kontonavn__"] = ""

    sign = _sign(mode)
    grp = sub.groupby("__konto__", sort=True)
    rows: list[HbAccountRow] = []
    for konto, g in grp:
        if not konto:
            continue
        # IB/UB hentes fra SAF-T balanser (party-nivå) — aggreger til konto:
        # summer party-IB/UB per konto som har denne HB-kontoen
        ib_col = c["ib"]
        ub_col = c["ub"]
        if ib_col in g.columns and g[ib_col].notna().any():
            # Tell hver kunde/lev én gang (first per nr)
            g_unique = g.drop_duplicates(subset=[c["nr"]]) if c["nr"] in g.columns else g
            ib = float(pd.to_numeric(g_unique[ib_col], errors="coerce").fillna(0.0).sum()) * sign
            ub = float(pd.to_numeric(g_unique[ub_col], errors="coerce").fillna(0.0).sum()) * sign
        else:
            bev = float(g["__belop__"].sum()) * sign
            ib = 0.0
            ub = bev
        bev_sum = float(g["__belop__"].sum()) * sign
        kontonavn = str(g["__kontonavn__"].iloc[0] or "").strip()
        rows.append(HbAccountRow(
            konto=str(konto),
            kontonavn=kontonavn,
            antall=int(len(g)),
            ib=ib,
            bevegelse=bev_sum,
            ub=ub,
        ))
    rows.sort(key=lambda r: abs(r.ub), reverse=True)
    return rows


def _build_hb_reconciliation(
    hb_accounts: list[HbAccountRow],
    *,
    sb_df: Optional[pd.DataFrame],
    mode: Mode,
) -> dict:
    """Sammenlign sum reskontro-UB mot HB/SB-UB for samme kontoer.

    sb_df forventes å ha kolonner 'konto' og 'ub' (normalisert trial balance).
    """
    reskontro_ub = sum(r.ub for r in hb_accounts)
    sign = _sign(mode)

    sb_ub = 0.0
    sb_found: list[str] = []
    sb_missing: list[str] = []
    if sb_df is not None and isinstance(sb_df, pd.DataFrame) and not sb_df.empty:
        sb_work = sb_df.copy()
        # Tolerere både 'konto'/'ub' (trial_balance_reader) og 'Konto'/'UB'
        konto_col = next((c for c in sb_work.columns if str(c).strip().lower() == "konto"), None)
        ub_col = next((c for c in sb_work.columns if str(c).strip().lower() == "ub"), None)
        if konto_col and ub_col:
            sb_work[konto_col] = sb_work[konto_col].astype(str).str.strip()
            sb_work[ub_col] = pd.to_numeric(sb_work[ub_col], errors="coerce").fillna(0.0)
            for hb in hb_accounts:
                match = sb_work.loc[sb_work[konto_col] == hb.konto, ub_col]
                if not match.empty:
                    sb_ub += float(match.sum()) * sign
                    sb_found.append(hb.konto)
                else:
                    sb_missing.append(hb.konto)

    diff = reskontro_ub - sb_ub if sb_found else 0.0
    return {
        "reskontro_ub": reskontro_ub,
        "sb_ub": sb_ub,
        "diff": diff,
        "found_accounts": sb_found,
        "missing_accounts": sb_missing,
        "has_sb": bool(sb_found),
    }


# ---------------------------------------------------------------------------
# Motpost-analyse
# ---------------------------------------------------------------------------

def _build_motpost(
    df: pd.DataFrame, *, mode: Mode, side: Literal["debet", "kredit"], top: int = 10
) -> list[MotpostRow]:
    """Aggregér motpostkontoer på debet- eller kreditsiden av reskontrobilag.

    Metode: filtrer bilag med reskontrotransaksjoner. For hvert slikt bilag
    sjekk alle andre linjer (ikke-reskontro) og aggregér etter konto på den
    ønskede siden.

    For kunder:
      - debet-motpost = postering med Beløp > 0 som ikke er reskontro (typisk
        kan være dubious — vanligvis sjelden, f.eks. refusjoner eller
        interne omposteringer). NB: vi bruker rå fortegn.
      - kredit-motpost = postering med Beløp < 0 (typisk salgsinntekt 3xxx +
        MVA 2700 når reskontro debiteres, eller bank 1920 når reskontro
        krediteres).

    Det mest intuitive i praksis: for kunder viser "debet-motposter" hva
    som reduserer fordringen (bank-innbetalinger på kreditsiden av bilaget
    matcher debet på kunde), og vice versa. Vi regner begge retninger ved å
    se på faktisk bilag-struktur.
    """
    if "Bilag" not in df.columns or "Beløp" not in df.columns or "Konto" not in df.columns:
        return []

    c = _cols(mode)
    nr_col = c["nr"]
    if nr_col not in df.columns:
        return []

    df_work = df.copy()
    df_work["__bilag__"] = df_work["Bilag"].astype(str).str.strip()
    df_work["__belop__"] = pd.to_numeric(df_work["Beløp"], errors="coerce").fillna(0.0)
    df_work["__konto__"] = df_work["Konto"].astype(str).str.strip()
    df_work["__is_resk__"] = (
        df_work[nr_col].notna()
        & (df_work[nr_col].astype(str).str.strip() != "")
    )

    # Bilag som inneholder minst én reskontro-linje
    resk_bilag = set(df_work.loc[df_work["__is_resk__"], "__bilag__"].unique())
    if not resk_bilag:
        return []

    # Finn retning av reskontro-linjene per bilag — "motposten" skal være
    # motsatt fortegn
    resk_by_bilag = (
        df_work.loc[df_work["__is_resk__"] & df_work["__bilag__"].isin(resk_bilag)]
        .groupby("__bilag__")["__belop__"].sum()
    )

    # Motposter = linjer som IKKE er reskontro, i bilag som har reskontro
    mot = df_work.loc[
        (~df_work["__is_resk__"]) & df_work["__bilag__"].isin(resk_bilag)
    ].copy()
    if mot.empty:
        return []

    if side == "debet":
        mask = mot["__belop__"] > 0
    else:
        mask = mot["__belop__"] < 0

    mot = mot.loc[mask]
    if mot.empty:
        return []

    if "Kontonavn" in mot.columns:
        mot["__kontonavn__"] = mot["Kontonavn"].fillna("").astype(str)
    else:
        mot["__kontonavn__"] = ""

    grp = mot.groupby("__konto__", sort=False)
    agg = pd.DataFrame({
        "antall": grp.size(),
        "sum_belop": grp["__belop__"].sum(),
        "kontonavn": grp["__kontonavn__"].first().fillna(""),
    }).reset_index()

    total = float(agg["sum_belop"].abs().sum()) or 1.0
    agg = agg.sort_values("sum_belop", key=lambda s: s.abs(), ascending=False).head(top)

    out: list[MotpostRow] = []
    for _, row in agg.iterrows():
        out.append(MotpostRow(
            konto=str(row["__konto__"]),
            kontonavn=str(row["kontonavn"] or ""),
            antall=int(row["antall"]),
            sum_belop=float(row["sum_belop"]),
            andel_pct=float(abs(row["sum_belop"]) / total * 100.0),
        ))
    _ = resk_by_bilag  # reserved for future use
    return out


# ---------------------------------------------------------------------------
# Konsentrasjon & KPI
# ---------------------------------------------------------------------------

def _build_concentration(rows: list[PartyRow]) -> dict:
    """HHI + topp 5 andel av total UB (|UB|)."""
    totals = [abs(r.ub) for r in rows]
    total = sum(totals)
    if total < 1e-9:
        return {"total_ub": 0.0, "hhi": 0.0, "top5_pct": 0.0, "top10_pct": 0.0, "count": len(rows)}

    shares = sorted([(t / total) for t in totals], reverse=True)
    hhi = sum(s * s for s in shares) * 10000.0  # 0–10000
    top5 = sum(shares[:5]) * 100.0
    top10 = sum(shares[:10]) * 100.0
    return {
        "total_ub": total,
        "hhi": hhi,
        "top5_pct": top5,
        "top10_pct": top10,
        "count": len(rows),
    }


def _build_kpi(
    rows: list[PartyRow],
    df: pd.DataFrame,
    *,
    mode: Mode,
) -> dict:
    total_ub = sum(r.ub for r in rows)
    aktive = [r for r in rows if abs(r.ub) > 0.01]
    total_tx = int(sum(r.antall for r in rows))
    total_debet = sum(r.debet for r in rows)
    total_kredit = sum(r.kredit for r in rows)

    c = _cols(mode)
    sub = _filter_to_reskontro(df, mode=mode)
    antall_bilag = 0
    if "Bilag" in sub.columns:
        antall_bilag = int(sub["Bilag"].astype(str).str.strip().nunique())

    mva_tx = 0
    mva_belop = 0.0
    if "MVA-beløp" in sub.columns:
        m = pd.to_numeric(sub["MVA-beløp"], errors="coerce").fillna(0.0)
        mva_tx = int((m.abs() > 0.01).sum())
        mva_belop = float(m.sum())

    snitt_ub = (total_ub / len(aktive)) if aktive else 0.0

    label_party = "kunder" if mode == "kunder" else "leverandører"
    return {
        "label_party": label_party,
        "antall_total": len(rows),
        "antall_aktive": len(aktive),
        "total_ub": total_ub,
        "total_debet": total_debet,
        "total_kredit": total_kredit,
        "total_transaksjoner": total_tx,
        "antall_bilag": antall_bilag,
        "snitt_ub_aktive": snitt_ub,
        "mva_tx": mva_tx,
        "mva_belop": mva_belop,
    }


# ---------------------------------------------------------------------------
# Aldersanalyse — aggregert over alle åpne poster
# ---------------------------------------------------------------------------

def _build_aging_all(
    df: pd.DataFrame, *, mode: Mode, rows: list[PartyRow], reference_date: str
) -> list[AgingBucket]:
    """Beregn aldersfordeling på tvers av alle kunder/leverandører.

    Bruker reskontro_open_items._compute_open_items + _compute_aging_buckets.
    """
    if not reference_date:
        return []
    try:
        from .open_items import (
            _compute_open_items,
            _compute_aging_buckets,
        )
    except Exception:
        return []

    labels = ["0–30 d", "31–60 d", "61–90 d", "91–180 d", ">180 d"]
    totals = {lbl: [0.0, 0] for lbl in labels}

    for r in rows:
        if abs(r.ub) < 0.01:
            continue
        # _compute_open_items forventer rå (uflippet) UB
        raw_ub = r.ub * _sign(mode)
        items_df = _compute_open_items(df, nr=r.nr, mode=mode, ub=raw_ub)
        if items_df is None or items_df.empty:
            continue
        items = items_df.to_dict(orient="records")
        buckets = _compute_aging_buckets(items, reference_date=reference_date)
        for lbl, s, cnt in buckets:
            if lbl in totals:
                totals[lbl][0] += float(s) * _sign(mode)  # flipp for leverandører
                totals[lbl][1] += int(cnt)

    return [AgingBucket(label=lbl, sum_gjenstar=totals[lbl][0], antall=totals[lbl][1])
            for lbl in labels]


# ---------------------------------------------------------------------------
# Hovedfunksjon
# ---------------------------------------------------------------------------

def compute_reskontro_report(
    df: pd.DataFrame,
    *,
    mode: Mode,
    client: str = "",
    year: str | int = "",
    reference_date: str = "",
    sb_df: Optional[pd.DataFrame] = None,
    top_n: int = 10,
    include_aging: bool = True,
    include_motpost: bool = True,
) -> ReskontroReport:
    """Beregn full reskontrorapport.

    Parameters
    ----------
    df : SAF-T/HB-transaksjoner med kolonner Bilag, Dato, Konto, Kontonavn,
         Beløp, Tekst, og Kundenr/Leverandørnr + relaterte felt.
    mode : "kunder" eller "leverandorer".
    reference_date : Balansedato for aldersanalyse (YYYY-MM-DD). Tom streng
                     hopper over aldersanalyse og "dager siden siste".
    sb_df : Valgfri trial balance for HB-avstemming (kolonner konto/ub).
    top_n : Antall rader i topp-lister (default 10).
    """
    report = ReskontroReport(
        mode=mode,
        client=str(client or ""),
        year=str(year or ""),
        reference_date=reference_date,
    )

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return report

    c = _cols(mode)
    if c["nr"] not in df.columns:
        return report

    rows = _build_party_rows(df, mode=mode, reference_date=reference_date)
    report.kpi = _build_kpi(rows, df, mode=mode)

    report.hb_accounts = _build_hb_accounts(df, mode=mode)
    report.hb_reconciliation = _build_hb_reconciliation(
        report.hb_accounts, sb_df=sb_df, mode=mode
    )

    report.top_ub = _top_by(rows, key=lambda r: r.ub, n=top_n)
    if mode == "kunder":
        report.top_signed_bevegelse = _top_by(rows, key=lambda r: r.kredit, n=top_n)
    else:
        report.top_signed_bevegelse = _top_by(rows, key=lambda r: r.debet, n=top_n)
    report.top_activity = _top_by(rows, key=lambda r: r.debet + r.kredit, n=top_n)
    report.top_transactions = _top_transactions(df, mode=mode, n=top_n)

    # Motpostpart — kunder med negativ UB / lev med positiv UB (etter flipp)
    if mode == "kunder":
        cb = [r for r in rows if r.ub < -0.01]
    else:
        cb = [r for r in rows if r.ub < -0.01]
    report.counter_balance_rows = sorted(cb, key=lambda r: r.ub)[:top_n]

    if include_motpost:
        report.motpost_debet = _build_motpost(df, mode=mode, side="debet", top=top_n)
        report.motpost_kredit = _build_motpost(df, mode=mode, side="kredit", top=top_n)

    report.concentration = _build_concentration(rows)

    if include_aging and reference_date:
        report.aging = _build_aging_all(
            df, mode=mode, rows=rows, reference_date=reference_date
        )

    return report
