"""nokkeltall_engine.py — Beregn nøkkeltall fra regnskapslinje-pivot.

Tar inn en rl_df (regnr, regnskapslinje, IB, Endring, UB, Antall, og evt.
UB_fjor, Endring_fjor, Endring_pct) og returnerer beregnede nøkkeltall
gruppert etter kategori.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Nokkeltall:
    """Ett beregnet nøkkeltall."""
    id: str
    label: str
    category: str  # Lønnsomhet, Likviditet, Soliditet, Effektivitet
    value: float | None = None
    prev_value: float | None = None
    fmt: str = "pct"  # pct, decimal, amount, days

    @property
    def formatted(self) -> str:
        return _format_value(self.value, self.fmt)

    @property
    def formatted_prev(self) -> str:
        return _format_value(self.prev_value, self.fmt)

    @property
    def change_pct(self) -> float | None:
        if self.value is None or self.prev_value is None:
            return None
        if abs(self.prev_value) < 1e-9:
            return None
        return ((self.value - self.prev_value) / abs(self.prev_value)) * 100


@dataclass
class NokkeltallObservation:
    """Generisk vurdering av ett nøkkeltall mot tommelfingerregel."""
    metric_id: str
    label: str
    category: str  # Lønnsomhet | Likviditet | Soliditet
    severity: str  # "ok" | "watch" | "critical"
    actual_text: str
    benchmark_text: str
    message: str


@dataclass
class ReskontroRow:
    """Én rad i reskontro-tabell (kunde eller leverandør)."""
    nr: str
    navn: str
    ib: float
    debet: float
    kredit: float
    ub: float


@dataclass
class NokkeltallResult:
    """Samlet resultat fra nøkkeltallsberegning."""
    metrics: list[Nokkeltall] = field(default_factory=list)
    kpi_cards: list[dict] = field(default_factory=list)
    pl_summary: list[dict] = field(default_factory=list)
    bs_summary: list[dict] = field(default_factory=list)
    bs_eiendeler: list[dict] = field(default_factory=list)
    bs_ek_gjeld: list[dict] = field(default_factory=list)
    cost_breakdown: list[dict] = field(default_factory=list)
    bs_breakdown: list[dict] = field(default_factory=list)
    top_activity: list[dict] = field(default_factory=list)
    top_changes: dict = field(default_factory=lambda: {"increases": [], "decreases": []})
    concentration: list[dict] = field(default_factory=list)
    observations: list[NokkeltallObservation] = field(default_factory=list)
    reskontro_kunder_top_ub: list[ReskontroRow] = field(default_factory=list)
    reskontro_lev_top_ub: list[ReskontroRow] = field(default_factory=list)
    reskontro_kunder_top_debet: list[ReskontroRow] = field(default_factory=list)
    reskontro_lev_top_kredit: list[ReskontroRow] = field(default_factory=list)
    has_prev_year: bool = False
    client: str = ""
    year: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_value(value: float | None, fmt: str) -> str:
    if value is None:
        return "–"
    if fmt == "pct":
        return f"{value:.1f} %"
    if fmt == "decimal":
        return f"{value:.2f}"
    if fmt == "days":
        return f"{value:.0f}"
    # amount — hele kroner
    v = round(value)
    return f"{v:,}".replace(",", " ")


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    if abs(b) < 1e-9:
        return None
    return a / b


def _rl_value(lookup: dict[int, float], regnr: int) -> float | None:
    """Hent UB for et regnskapsnummer, None hvis mangler."""
    v = lookup.get(regnr)
    if v is None:
        return None
    return float(v)


def _is_credit_line(regnr: int) -> bool:
    """Regnskapslinjer som naturlig har kredittsaldo (negativ i SAF-T).

    Inntekter, resultatlinjer, egenkapital og gjeld lagres som negative
    verdier i SAF-T/HB. For visning og beregning normaliseres fortegnet
    slik at positive verdier = normalt (inntekt, overskudd, positiv EK).
    """
    if regnr <= 19:       # Driftsinntekter
        return True
    if regnr in (80, 135, 160, 280):  # Resultat, finansinntekter
        return True
    if regnr >= 700:      # Egenkapital og gjeld
        return True
    return False


def _build_lookup(rl_df: pd.DataFrame, col: str = "UB", *,
                  normalize_sign: bool = False) -> dict[int, float]:
    """Bygg oppslag regnr -> verdi fra rl_df.

    Med normalize_sign=True negeres kredittlinjer slik at verdiene
    blir visningsorienterte (positiv = normalt).
    """
    out: dict[int, float] = {}
    if rl_df is None or rl_df.empty:
        return out
    if col not in rl_df.columns:
        return out
    for _, row in rl_df.iterrows():
        try:
            regnr = int(float(row["regnr"]))
        except (ValueError, TypeError):
            continue
        try:
            val = float(row[col])
        except (ValueError, TypeError):
            continue
        if normalize_sign and _is_credit_line(regnr):
            val = -val
        out[regnr] = val
    return out


# ---------------------------------------------------------------------------
# Nøkkeltall-definisjoner
# ---------------------------------------------------------------------------

def _compute_metrics(ub: dict[int, float], ub_prev: dict[int, float] | None) -> list[Nokkeltall]:
    """Beregn nøkkeltall basert på UB-oppslag (og evt. forrige år)."""

    def _get(regnr: int) -> float | None:
        return _rl_value(ub, regnr)

    def _get_prev(regnr: int) -> float | None:
        if ub_prev is None:
            return None
        return _rl_value(ub_prev, regnr)

    def _metric(id: str, label: str, cat: str, val: float | None,
                prev: float | None = None, fmt: str = "pct") -> Nokkeltall:
        return Nokkeltall(id=id, label=label, category=cat, value=val,
                          prev_value=prev, fmt=fmt)

    # Hent regnskapslinjeverdier
    salg = _get(10)            # Salgsinntekt
    driftsinnt = _get(19)      # Sum driftsinntekter
    varekost = _get(20)        # Varekostnad
    lonnskost = _get(40)       # Lønnskostnad
    avskriving = _get(50)      # Avskrivning
    annen_drift = _get(70)     # Annen driftskostnad
    sum_driftskost = _get(79)  # Sum driftskostnader
    driftsres = _get(80)       # Driftsresultat
    finansinnt = _get(135)     # Sum finansinntekter
    finanskost = _get(145)     # Sum finanskostnader
    res_for_skatt = _get(160)  # Resultat før skattekostnad
    aarsres = _get(280)        # Årsresultat

    varige_dm = _get(555)      # Sum varige driftsmidler
    varelager = _get(605)      # Lager av varer
    kundefordr = _get(610)     # Kundefordringer
    bank = _get(655)           # Bankinnskudd
    omlopsmidler = _get(660)   # Sum omløpsmidler
    sum_eiendeler = _get(665)  # Sum eiendeler
    sum_ek = _get(715)         # Sum egenkapital
    avsetn_forpl = _get(735)   # Sum avsetning for forpliktelser
    annen_lang_gjeld = _get(760)  # Sum annen langsiktig gjeld
    levgjeld = _get(780)       # Leverandørgjeld
    kort_gjeld = _get(810)     # Sum kortsiktig gjeld
    sum_gjeld = _get(820)      # Sum gjeld

    # Forrige-år (for nøkkeltall som trenger gjennomsnitt)
    salg_p = _get_prev(10)
    driftsinnt_p = _get_prev(19)
    varekost_p = _get_prev(20)
    driftsres_p = _get_prev(80)
    res_for_skatt_p = _get_prev(160)
    aarsres_p = _get_prev(280)
    sum_eiendeler_p = _get_prev(665)
    sum_ek_p = _get_prev(715)
    omlopsmidler_p = _get_prev(660)
    kort_gjeld_p = _get_prev(810)
    sum_gjeld_p = _get_prev(820)
    lonnskost_p = _get_prev(40)
    annen_drift_p = _get_prev(70)
    kundefordr_p = _get_prev(610)
    varelager_p = _get_prev(605)
    levgjeld_p = _get_prev(780)

    # -- EBITDA --
    ebitda = None
    if driftsinnt is not None and sum_driftskost is not None and avskriving is not None:
        ebitda = driftsinnt - (sum_driftskost - avskriving)

    metrics: list[Nokkeltall] = []

    # ---- Lønnsomhet ----
    bf_kr = ((salg or 0) - (varekost or 0)
             if salg is not None else None)
    bf_kr_p = ((salg_p or 0) - (varekost_p or 0)
               if salg_p is not None else None)

    metrics.append(_metric("bruttofort_kr", "Bruttofortjeneste i kr",
                           "Lønnsomhet",
                           bf_kr, bf_kr_p, fmt="amount"))

    metrics.append(_metric("bruttofort_pct", "Bruttofortjeneste i %",
                           "Lønnsomhet",
                           _safe_div((salg or 0) - (varekost or 0), salg) * 100
                           if salg and abs(salg) > 1e-9 else None,
                           _safe_div((salg_p or 0) - (varekost_p or 0), salg_p) * 100
                           if salg_p and abs(salg_p) > 1e-9 else None))

    metrics.append(_metric("driftsmargin", "Driftsmargin",
                           "Lønnsomhet",
                           _safe_div(driftsres, driftsinnt) * 100
                           if driftsres is not None and driftsinnt else None,
                           _safe_div(driftsres_p, driftsinnt_p) * 100
                           if driftsres_p is not None and driftsinnt_p else None))

    metrics.append(_metric("nettoresmargin", "Nettoresultatmargin",
                           "Lønnsomhet",
                           _safe_div(aarsres, driftsinnt) * 100
                           if aarsres is not None and driftsinnt else None,
                           _safe_div(aarsres_p, driftsinnt_p) * 100
                           if aarsres_p is not None and driftsinnt_p else None))

    metrics.append(_metric("ebitda_pct", "EBITDA-margin",
                           "Lønnsomhet",
                           _safe_div(ebitda, driftsinnt) * 100
                           if ebitda is not None and driftsinnt else None))

    metrics.append(_metric("res_for_skatt_pct", "Resultat før skatt i % av inntekter",
                           "Lønnsomhet",
                           _safe_div(res_for_skatt, driftsinnt) * 100
                           if res_for_skatt is not None and driftsinnt else None,
                           _safe_div(res_for_skatt_p, driftsinnt_p) * 100
                           if res_for_skatt_p is not None and driftsinnt_p else None))

    # ---- Likviditet ----
    metrics.append(_metric("likv1", "Likviditetsgrad 1",
                           "Likviditet",
                           _safe_div(omlopsmidler, kort_gjeld),
                           _safe_div(omlopsmidler_p, kort_gjeld_p),
                           fmt="decimal"))

    metrics.append(_metric("likv2", "Likviditetsgrad 2",
                           "Likviditet",
                           _safe_div((omlopsmidler or 0) - (varelager or 0), kort_gjeld)
                           if omlopsmidler is not None and kort_gjeld else None,
                           _safe_div((omlopsmidler_p or 0) - (varelager_p or 0), kort_gjeld_p)
                           if omlopsmidler_p is not None and kort_gjeld_p else None,
                           fmt="decimal"))

    arb_kap = None
    arb_kap_p = None
    if omlopsmidler is not None and kort_gjeld is not None:
        arb_kap = omlopsmidler - kort_gjeld
    if omlopsmidler_p is not None and kort_gjeld_p is not None:
        arb_kap_p = omlopsmidler_p - kort_gjeld_p
    metrics.append(_metric("arb_kap", "Arbeidskapital",
                           "Likviditet", arb_kap, arb_kap_p, fmt="amount"))

    # ---- Soliditet ----
    metrics.append(_metric("ek_andel", "Egenkapitalandel",
                           "Soliditet",
                           _safe_div(sum_ek, sum_eiendeler) * 100
                           if sum_ek is not None and sum_eiendeler else None,
                           _safe_div(sum_ek_p, sum_eiendeler_p) * 100
                           if sum_ek_p is not None and sum_eiendeler_p else None))

    metrics.append(_metric("gjeldsgrad", "Gjeldsgrad",
                           "Soliditet",
                           _safe_div(sum_gjeld, sum_ek),
                           _safe_div(sum_gjeld_p, sum_ek_p),
                           fmt="decimal"))

    # ---- Effektivitet ----
    metrics.append(_metric("kundefordr_pct", "Kundefordringer i % av salg",
                           "Effektivitet",
                           _safe_div(kundefordr, salg) * 100
                           if kundefordr is not None and salg else None,
                           _safe_div(kundefordr_p, salg_p) * 100
                           if kundefordr_p is not None and salg_p else None))

    metrics.append(_metric("varelager_pct", "Varelager i % av varekostnad",
                           "Effektivitet",
                           _safe_div(varelager, varekost) * 100
                           if varelager is not None and varekost and abs(varekost) > 1e-9 else None,
                           _safe_div(varelager_p, varekost_p) * 100
                           if varelager_p is not None and varekost_p and abs(varekost_p) > 1e-9 else None))

    levgjeld_driftskost_p = (varekost_p or 0) + (annen_drift_p or 0)
    metrics.append(_metric("levgjeld_pct", "Leverandørgjeld i % av driftskostnader",
                           "Effektivitet",
                           _safe_div(levgjeld, (varekost or 0) + (annen_drift or 0)) * 100
                           if levgjeld is not None else None,
                           _safe_div(levgjeld_p, levgjeld_driftskost_p) * 100
                           if levgjeld_p is not None and abs(levgjeld_driftskost_p) > 1e-9 else None))

    metrics.append(_metric("lonn_pct", "Lønnskostnad i % av driftsinntekter",
                           "Effektivitet",
                           _safe_div(lonnskost, driftsinnt) * 100
                           if lonnskost is not None and driftsinnt else None,
                           _safe_div(lonnskost_p, driftsinnt_p) * 100
                           if lonnskost_p is not None and driftsinnt_p else None))

    metrics.append(_metric("annen_drift_pct", "Annen driftskostnad i % av driftsinntekter",
                           "Effektivitet",
                           _safe_div(annen_drift, driftsinnt) * 100
                           if annen_drift is not None and driftsinnt else None,
                           _safe_div(annen_drift_p, driftsinnt_p) * 100
                           if annen_drift_p is not None and driftsinnt_p else None))

    return metrics


# ---------------------------------------------------------------------------
# KPI-kort
# ---------------------------------------------------------------------------

def _build_kpi_cards(ub: dict[int, float], ub_prev: dict[int, float] | None) -> list[dict]:
    """Bygg KPI-kort med sentrale nøkkeltall (ikke beløp — de vises i tabellene)."""
    cards: list[dict] = []

    def _ratio_card(label: str, val: float | None, prev: float | None = None,
                    fmt: str = "pct") -> None:
        if val is None:
            return
        change = None
        if prev is not None and abs(prev) > 1e-9:
            change = ((val - prev) / abs(prev)) * 100
        cards.append({
            "label": label,
            "value": val,
            "formatted": _format_value(val, fmt),
            "prev": prev,
            "change_pct": change,
        })

    # Hent verdier
    salg = _rl_value(ub, 10)
    driftsinnt = _rl_value(ub, 19)
    varekost = _rl_value(ub, 20)
    driftsres = _rl_value(ub, 80)
    aarsres = _rl_value(ub, 280)
    omlopsmidler = _rl_value(ub, 660)
    sum_eiendeler = _rl_value(ub, 665)
    sum_ek = _rl_value(ub, 715)
    kort_gjeld = _rl_value(ub, 810)

    # Forrige år
    salg_p = _rl_value(ub_prev, 10) if ub_prev else None
    driftsinnt_p = _rl_value(ub_prev, 19) if ub_prev else None
    varekost_p = _rl_value(ub_prev, 20) if ub_prev else None
    driftsres_p = _rl_value(ub_prev, 80) if ub_prev else None
    sum_eiendeler_p = _rl_value(ub_prev, 665) if ub_prev else None
    sum_ek_p = _rl_value(ub_prev, 715) if ub_prev else None
    omlopsmidler_p = _rl_value(ub_prev, 660) if ub_prev else None
    kort_gjeld_p = _rl_value(ub_prev, 810) if ub_prev else None

    # Bruttofortjeneste
    bf = _safe_div((salg or 0) - (varekost or 0), salg) * 100 if salg and abs(salg) > 1e-9 else None
    bf_p = _safe_div((salg_p or 0) - (varekost_p or 0), salg_p) * 100 if salg_p and abs(salg_p) > 1e-9 else None
    _ratio_card("Bruttofortjeneste", bf, bf_p)

    # Driftsmargin
    dm = _safe_div(driftsres, driftsinnt) * 100 if driftsres is not None and driftsinnt else None
    dm_p = _safe_div(driftsres_p, driftsinnt_p) * 100 if driftsres_p is not None and driftsinnt_p else None
    _ratio_card("Driftsmargin", dm, dm_p)

    # Egenkapitalandel
    ek = _safe_div(sum_ek, sum_eiendeler) * 100 if sum_ek is not None and sum_eiendeler else None
    ek_p = _safe_div(sum_ek_p, sum_eiendeler_p) * 100 if sum_ek_p is not None and sum_eiendeler_p else None
    _ratio_card("Egenkapitalandel", ek, ek_p)

    # Likviditetsgrad 1
    l1 = _safe_div(omlopsmidler, kort_gjeld)
    l1_p = _safe_div(omlopsmidler_p, kort_gjeld_p)
    _ratio_card("Likviditetsgrad 1", l1, l1_p, fmt="decimal")

    return cards


# ---------------------------------------------------------------------------
# P&L og Balanse oppsummering
# ---------------------------------------------------------------------------

@dataclass
class RLMeta:
    """Metadata for regnskapslinjer fra config — single source of truth."""
    type_map: dict[int, str] = field(default_factory=dict)      # regnr → "PL" | "BS"
    sumpost_set: set[int] = field(default_factory=set)           # regnr som er sumposter
    order: list[int] = field(default_factory=list)               # regnr i config-rekkefølge
    names: dict[int, str] = field(default_factory=dict)          # regnr → navn fra config


def _load_rl_meta() -> RLMeta:
    """Last regnskapslinje-metadata fra config.

    Bruker regnskap_config (regnskapslinjer.xlsx) som eneste kilde for:
      - Resultat/Balanse-type
      - Sumpost-flagg
      - Rekkefølge (bevarer config-sortering)
      - Offisielle navn
    """
    meta = RLMeta()
    try:
        from regnskap_config import load_regnskapslinjer
        from regnskap_mapping import normalize_regnskapslinjer

        rl_cfg = load_regnskapslinjer()

        # Type (PL/BS) fra rå config
        for _, row in rl_cfg.iterrows():
            try:
                nr = int(float(row.get("nr", 0)))
            except (ValueError, TypeError):
                continue
            rb = str(row.get("resultat/balanse", "")).strip().lower()
            if "resultat" in rb:
                meta.type_map[nr] = "PL"
            elif "balanse" in rb:
                meta.type_map[nr] = "BS"

        # Sumpost + rekkefølge + navn fra normalisert config
        regn = normalize_regnskapslinjer(rl_cfg)
        for _, row in regn.iterrows():
            regnr = int(row["regnr"])
            meta.order.append(regnr)
            meta.names[regnr] = str(row.get("regnskapslinje", ""))
            if bool(row.get("sumpost", False)):
                meta.sumpost_set.add(regnr)
    except Exception:
        pass
    return meta


def _build_summary_lines(
    ub: dict[int, float],
    ub_prev: dict[int, float] | None,
    rl_names: dict[int, str],
    meta: RLMeta,
    *,
    line_type: str,
) -> list[dict]:
    """Bygg oppsummeringslinjer fra data, sortert etter config-rekkefølge.

    Bruker meta.type_map for å filtrere PL/BS — aldri hardkodet regnr-grense.
    Bevarer config-rekkefølgen via meta.order.
    """
    # Sorter etter config-rekkefølge; ukjente regnr plasseres til slutt
    order_idx = {regnr: i for i, regnr in enumerate(meta.order)}
    eligible = [r for r in ub if meta.type_map.get(r) == line_type]
    eligible.sort(key=lambda r: order_idx.get(r, 99999))

    lines: list[dict] = []
    for regnr in eligible:
        val = ub[regnr]
        prev = _rl_value(ub_prev, regnr) if ub_prev else None
        name = rl_names.get(regnr) or meta.names.get(regnr, f"RL {regnr}")
        is_sum = regnr in meta.sumpost_set
        change_pct = None
        change_amount = None
        if prev is not None:
            change_amount = val - prev
            if abs(prev) > 1e-9:
                change_pct = ((val - prev) / abs(prev)) * 100
        lines.append({
            "regnr": regnr,
            "name": name,
            "value": val,
            "formatted": _format_value(val, "amount"),
            "prev": prev,
            "prev_formatted": _format_value(prev, "amount") if prev is not None else None,
            "change_amount": change_amount,
            "change_amount_formatted": _format_value(change_amount, "amount") if change_amount is not None else None,
            "change_pct": change_pct,
            "is_sum": is_sum,
        })
    return lines


# ---------------------------------------------------------------------------
# Kostnadsfordeling (for kakediagram)
# ---------------------------------------------------------------------------

def _build_cost_breakdown(ub: dict[int, float]) -> list[dict]:
    """Kostnadsfordeling for kakediagram."""
    parts = [
        (20, "Varekostnad"),
        (40, "Lønnskostnad"),
        (50, "Avskrivning"),
        (70, "Annen driftskostnad"),
    ]
    items: list[dict] = []
    for regnr, label in parts:
        val = _rl_value(ub, regnr)
        if val is not None and abs(val) > 1e-9:
            items.append({"label": label, "value": abs(val)})
    return items


def _build_bs_breakdown(ub: dict[int, float]) -> list[dict]:
    """Balansefordeling for kakediagram: Eiendeler, EK, Gjeld."""
    items: list[dict] = []

    # Eiendeler-side: anleggsmidler + omløpsmidler
    anl = _rl_value(ub, 590)  # Sum anleggsmidler
    oml = _rl_value(ub, 660)  # Sum omløpsmidler
    sum_eien = _rl_value(ub, 665)  # Sum eiendeler

    # Fallback: hvis "Sum anleggsmidler" (590) ikke er i datasettet,
    # utled fra Sum eiendeler - Sum omløpsmidler. Dette dekker tilfeller
    # der kundens kontoplan bruker sub-sums (imm./varige/finans.) uten
    # eksplisitt totallinje 590.
    if (anl is None or abs(anl) < 1e-9) and sum_eien is not None and oml is not None:
        diff = abs(sum_eien) - abs(oml)
        if abs(diff) > 1e-9:
            anl = diff

    if anl is not None and abs(anl) > 1e-9:
        items.append({"label": "Anleggsmidler", "value": abs(anl), "side": "eiendeler"})
    if oml is not None and abs(oml) > 1e-9:
        items.append({"label": "Omløpsmidler", "value": abs(oml), "side": "eiendeler"})

    # Finansiering-side: EK + gjeld
    ek = _rl_value(ub, 715)   # Sum egenkapital
    kg = _rl_value(ub, 810)   # Sum kortsiktig gjeld
    sum_gjeld = _rl_value(ub, 820)  # Sum gjeld
    lang_gjeld = None
    if sum_gjeld is not None and kg is not None:
        lang_gjeld = abs(sum_gjeld) - abs(kg)
        if lang_gjeld < 1e-9:
            lang_gjeld = None

    if ek is not None and abs(ek) > 1e-9:
        items.append({"label": "Egenkapital", "value": abs(ek), "side": "finansiering"})
    if lang_gjeld is not None and abs(lang_gjeld) > 1e-9:
        items.append({"label": "Langsiktig gjeld", "value": abs(lang_gjeld), "side": "finansiering"})
    if kg is not None and abs(kg) > 1e-9:
        items.append({"label": "Kortsiktig gjeld", "value": abs(kg), "side": "finansiering"})

    return items


# ---------------------------------------------------------------------------
# Top aktivitet (transaksjoner / bilag)
# ---------------------------------------------------------------------------

def _build_top_activity(
    rl_df: pd.DataFrame,
    transactions_df: pd.DataFrame | None = None,
    n: int = 10,
    sumpost_set: set[int] | None = None,
) -> list[dict]:
    """Finn top-N regnskapslinjer etter bilagsvolum (faller tilbake til
    HB-linjer hvis ``Antall_bilag`` ikke er tilgjengelig)."""
    if rl_df is None or rl_df.empty:
        return []

    df = rl_df.copy()
    if "Antall" not in df.columns:
        return []

    try:
        df["_regnr"] = df["regnr"].astype(float).astype(int)
    except (ValueError, TypeError):
        return []
    if sumpost_set:
        df = df[~df["_regnr"].isin(sumpost_set)]

    use_bilag = "Antall_bilag" in df.columns and df["Antall_bilag"].sum() > 0
    count_col = "Antall_bilag" if use_bilag else "Antall"
    count_label = "bilag" if use_bilag else "transaksjoner"

    df = df[df[count_col] > 0]
    if df.empty:
        return []

    top = df.nlargest(n, count_col)
    max_count = int(top[count_col].max())
    items: list[dict] = []
    for _, row in top.iterrows():
        regnr = int(row["_regnr"])
        name = str(row.get("regnskapslinje", ""))
        count = int(row.get(count_col, 0))

        change_pct: float | None = None
        if "Endring_pct" in row.index:
            try:
                pct = float(row["Endring_pct"])
                if not pd.isna(pct):
                    change_pct = pct
            except (ValueError, TypeError):
                pass

        ub_val = float(row.get("UB", 0) or 0)
        if _is_credit_line(regnr):
            ub_val = -ub_val
            if change_pct is not None:
                change_pct = -change_pct
        items.append({
            "regnr": regnr,
            "name": name,
            "count": count,
            "count_label": count_label,
            "bar_pct": (count / max_count * 100) if max_count > 0 else 0.0,
            "ub": ub_val,
            "formatted_ub": _format_value(ub_val, "amount"),
            "change_pct": change_pct,
        })
    return items


def _build_top_changes(
    rl_df: pd.DataFrame,
    *,
    n: int = 5,
    sumpost_set: set[int] | None = None,
) -> dict:
    """Topp-N regnskapslinjer med største økning og reduksjon mot fjor
    (målt i absoluttverdi i NOK, etter fortegnsnormalisering)."""
    empty = {"increases": [], "decreases": []}
    if rl_df is None or rl_df.empty or "UB_fjor" not in rl_df.columns:
        return empty

    df = rl_df.copy()
    try:
        df["_regnr"] = df["regnr"].astype(float).astype(int)
    except (ValueError, TypeError):
        return empty
    if sumpost_set:
        df = df[~df["_regnr"].isin(sumpost_set)]
    if df.empty:
        return empty

    rows: list[dict] = []
    for _, row in df.iterrows():
        regnr = int(row["_regnr"])
        try:
            ub = float(row.get("UB", 0) or 0)
            ub_prev = float(row.get("UB_fjor", 0) or 0)
        except (ValueError, TypeError):
            continue
        if _is_credit_line(regnr):
            ub, ub_prev = -ub, -ub_prev
        diff = ub - ub_prev
        if abs(diff) < 1e-9:
            continue
        pct: float | None = None
        if abs(ub_prev) > 1e-9:
            pct = diff / abs(ub_prev) * 100
        rows.append({
            "regnr": regnr,
            "name": str(row.get("regnskapslinje", "")),
            "diff": diff,
            "formatted_diff": _format_value(diff, "amount"),
            "change_pct": pct,
        })

    if not rows:
        return empty

    increases = sorted([r for r in rows if r["diff"] > 0],
                       key=lambda r: r["diff"], reverse=True)[:n]
    decreases = sorted([r for r in rows if r["diff"] < 0],
                       key=lambda r: r["diff"])[:n]

    def _add_bar_pct(items: list[dict]) -> list[dict]:
        if not items:
            return items
        max_abs = max(abs(r["diff"]) for r in items) or 1.0
        for r in items:
            r["bar_pct"] = abs(r["diff"]) / max_abs * 100
        return items

    return {
        "increases": _add_bar_pct(increases),
        "decreases": _add_bar_pct(decreases),
    }


def _build_concentration(
    rl_df: pd.DataFrame,
    ub: dict[int, float],
) -> list[dict]:
    """Konsentrasjonsmål — hvor stor andel topp-X av totalen."""
    items: list[dict] = []

    # 1) Topp 3 driftsinntektslinjer / Sum driftsinntekter
    sum_inntekt = _rl_value(ub, 19)
    if sum_inntekt is not None and abs(sum_inntekt) > 1e-9:
        inntekt_range = range(1, 19)  # RL 1–18 er detaljnivå for driftsinntekter
        inntekter = [
            (int(r), abs(float(v)))
            for r, v in ub.items()
            if int(r) in inntekt_range and v is not None and abs(float(v)) > 1e-9
        ]
        inntekter.sort(key=lambda x: x[1], reverse=True)
        topp3 = sum(v for _, v in inntekter[:3])
        if abs(sum_inntekt) > 0:
            pct = topp3 / abs(sum_inntekt) * 100
            items.append({
                "label": "Topp 3 inntektslinjer",
                "detail": "av sum driftsinntekter",
                "value_pct": pct,
            })

    # 2) Topp 3 driftskostnadslinjer / Sum driftskostnader
    sum_kost = _rl_value(ub, 79)
    if sum_kost is not None and abs(sum_kost) > 1e-9:
        kost_range = range(20, 79)
        kostnader = [
            (int(r), abs(float(v)))
            for r, v in ub.items()
            if int(r) in kost_range and v is not None and abs(float(v)) > 1e-9
        ]
        kostnader.sort(key=lambda x: x[1], reverse=True)
        topp3 = sum(v for _, v in kostnader[:3])
        pct = topp3 / abs(sum_kost) * 100
        items.append({
            "label": "Topp 3 kostnadslinjer",
            "detail": "av sum driftskostnader",
            "value_pct": pct,
        })

    # 3) Topp 10 RL / totalt antall bilag — bare hvis bilag-tall finnes
    if rl_df is not None and not rl_df.empty and "Antall_bilag" in rl_df.columns:
        try:
            total = int(rl_df["Antall_bilag"].sum())
        except Exception:
            total = 0
        if total > 0:
            top10 = int(rl_df.nlargest(10, "Antall_bilag")["Antall_bilag"].sum())
            pct = top10 / total * 100
            items.append({
                "label": "Topp 10 regnskapslinjer",
                "detail": "av alle bilagsposteringer",
                "value_pct": pct,
            })

    return items


# ---------------------------------------------------------------------------
# Observasjoner (standardvurderinger mot generiske tommelfingerregler)
# ---------------------------------------------------------------------------

# Generiske terskler — ikke bransjespesifikke. Rekkefølgen her er også
# rekkefølgen observasjonene vises i på rapporten.
_THRESHOLDS: dict[str, dict] = {
    "driftsmargin": {
        "category": "Lønnsomhet",
        "critical_below": 0.0,
        "bench": "positiv",
        "msg": "Negativ driftsmargin betyr tap fra drift.",
    },
    "nettoresmargin": {
        "category": "Lønnsomhet",
        "critical_below": 0.0,
        "bench": "positiv",
        "msg": "Negativ nettoresultatmargin betyr tap for året.",
    },
    "likv1": {
        "category": "Likviditet",
        "critical_below": 1.0, "watch_below": 2.0,
        "bench": "≥ 2,0",
        "msg": "Omløpsmidler bør dekke kortsiktig gjeld minst to ganger.",
    },
    "likv2": {
        "category": "Likviditet",
        "critical_below": 1.0, "watch_below": 1.2,
        "bench": "≥ 1,2",
        "msg": "Likvide midler (ekskl. varelager) bør dekke kortsiktig gjeld.",
    },
    "arb_kap": {
        "category": "Likviditet",
        "critical_below": 0.0,
        "bench": "positiv",
        "msg": "Negativ arbeidskapital signaliserer likviditetspress.",
    },
    "ek_andel": {
        "category": "Soliditet",
        "critical_below": 20.0, "watch_below": 30.0,
        "bench": "≥ 30 %",
        "msg": "Egenkapitalandelen måler selskapets soliditet.",
    },
    "gjeldsgrad": {
        "category": "Soliditet",
        "watch_above": 3.0, "critical_above": 5.0,
        "bench": "≤ 3,0",
        "msg": "Høy gjeldsgrad betyr stor finansieringsrisiko.",
    },
}


def _classify_severity(value: float, cfg: dict) -> str:
    if "critical_below" in cfg and value < cfg["critical_below"]:
        return "critical"
    if "critical_above" in cfg and value > cfg["critical_above"]:
        return "critical"
    if "watch_below" in cfg and value < cfg["watch_below"]:
        return "watch"
    if "watch_above" in cfg and value > cfg["watch_above"]:
        return "watch"
    return "ok"


def _build_observations(metrics: list[Nokkeltall]) -> list[NokkeltallObservation]:
    by_id = {m.id: m for m in metrics}
    result: list[NokkeltallObservation] = []
    for metric_id, cfg in _THRESHOLDS.items():
        m = by_id.get(metric_id)
        if m is None or m.value is None:
            continue
        severity = _classify_severity(m.value, cfg)
        result.append(NokkeltallObservation(
            metric_id=metric_id,
            label=m.label,
            category=cfg["category"],
            severity=severity,
            actual_text=m.formatted,
            benchmark_text=cfg["bench"],
            message=cfg["msg"],
        ))
    return result


# ---------------------------------------------------------------------------
# Reskontro (kunder/leverandører — topp saldo og bevegelser)
# ---------------------------------------------------------------------------

def _has_reskontro_columns(df: pd.DataFrame | None, mode: str) -> bool:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    return nr_col in df.columns and df[nr_col].notna().any()


def _build_reskontro_rows(
    df: pd.DataFrame,
    *,
    mode: str,
) -> list[ReskontroRow]:
    """Bygg én rad per kunde/leverandør med ib/debet/kredit/ub.

    Fortegn normaliseres for visning: leverandører flippes slik at
    saldo vises som positiv gjeld (på linje med balansen).
    Debet/kredit følger rå SAF-T-konvensjon (debet = Beløp > 0).
    """
    nr_col   = "Kundenr"     if mode == "kunder" else "Leverandørnr"
    navn_col = "Kundenavn"   if mode == "kunder" else "Leverandørnavn"
    ib_col   = "KundeIB"     if mode == "kunder" else "LeverandørIB"
    ub_col   = "KundeUB"     if mode == "kunder" else "LeverandørUB"
    sign = 1.0 if mode == "kunder" else -1.0

    if nr_col not in df.columns:
        return []

    sub = df[df[nr_col].notna() & (df[nr_col].astype(str).str.strip() != "")].copy()
    if sub.empty:
        return []

    sub["__nr__"]   = sub[nr_col].astype(str).str.strip()
    sub["__navn__"] = (sub[navn_col].astype(str).str.strip()
                       if navn_col in sub.columns else "")
    sub["__belop__"] = (pd.to_numeric(sub["Beløp"], errors="coerce").fillna(0.0)
                        if "Beløp" in sub.columns
                        else pd.Series(0.0, index=sub.index))
    sub["__debet__"]  = sub["__belop__"].where(sub["__belop__"] > 0, 0.0)
    sub["__kredit__"] = (-sub["__belop__"]).where(sub["__belop__"] < 0, 0.0)

    has_saft_bal = (ib_col in sub.columns and sub[ib_col].notna().any()
                    and ub_col in sub.columns and sub[ub_col].notna().any())

    grp = sub.groupby("__nr__")
    navn = grp["__navn__"].first()
    debet = grp["__debet__"].sum()
    kredit = grp["__kredit__"].sum()

    if has_saft_bal:
        sub["__ib__"] = pd.to_numeric(sub[ib_col], errors="coerce")
        sub["__ub__"] = pd.to_numeric(sub[ub_col], errors="coerce")
        ib = grp["__ib__"].first().fillna(0.0)
        ub = grp["__ub__"].first().fillna(0.0)
    else:
        bev = grp["__belop__"].sum()
        ib = pd.Series(0.0, index=bev.index)
        ub = bev

    rows: list[ReskontroRow] = []
    for nr in ib.index:
        rows.append(ReskontroRow(
            nr=str(nr),
            navn=str(navn.get(nr, "") or ""),
            ib=sign * float(ib.get(nr, 0.0)),
            debet=float(debet.get(nr, 0.0)),
            kredit=float(kredit.get(nr, 0.0)),
            ub=sign * float(ub.get(nr, 0.0)),
        ))
    return rows


def _top_n(rows: list[ReskontroRow], *, key, n: int = 5) -> list[ReskontroRow]:
    filtered = [r for r in rows if abs(key(r)) > 0.01]
    return sorted(filtered, key=lambda r: abs(key(r)), reverse=True)[:n]


# ---------------------------------------------------------------------------
# Hovedfunksjon
# ---------------------------------------------------------------------------

def compute_nokkeltall(
    rl_df: pd.DataFrame,
    *,
    transactions_df: pd.DataFrame | None = None,
    reskontro_df: pd.DataFrame | None = None,
    client: str = "",
    year: str | int = "",
) -> NokkeltallResult:
    """Beregn nøkkeltall og bygg rapportdata.

    Parameters
    ----------
    rl_df : DataFrame med kolonner regnr, regnskapslinje, IB, Endring, UB,
            Antall, og evt. UB_fjor, Endring_fjor, Endring_pct
    transactions_df : Valgfri HB-transaksjoner (for bilagtelling)
    client, year : For rapportoverskrift
    """
    if rl_df is None or rl_df.empty:
        return NokkeltallResult(client=str(client), year=str(year))

    ub = _build_lookup(rl_df, "UB", normalize_sign=True)
    has_prev = "UB_fjor" in rl_df.columns
    ub_prev = _build_lookup(rl_df, "UB_fjor", normalize_sign=True) if has_prev else None

    # Regnskapslinje-metadata fra config (type, sumpost, rekkefølge, navn)
    meta = _load_rl_meta()

    # Navn fra data (overstyrer config-navn hvis dataen har egne)
    rl_names: dict[int, str] = {}
    for _, row in rl_df.iterrows():
        try:
            rl_names[int(float(row["regnr"]))] = str(row.get("regnskapslinje", ""))
        except (ValueError, TypeError):
            pass

    bs_all = _build_summary_lines(ub, ub_prev, rl_names, meta, line_type="BS")

    # Splitt balanse i Eiendeler vs EK+Gjeld ved "Sum eiendeler"-linjen
    bs_eiendeler: list[dict] = []
    bs_ek_gjeld: list[dict] = []
    split_found = False
    for line in bs_all:
        bs_eiendeler.append(line) if not split_found else bs_ek_gjeld.append(line)
        # Splitten er etter den overordnede "Sum eiendeler"-linjen,
        # IKKE sub-summer som "Sum immaterielle eiendeler".
        if line.get("is_sum") and not split_found:
            name_lc = line.get("name", "").lower().strip()
            if name_lc == "sum eiendeler":
                split_found = True

    metrics = _compute_metrics(ub, ub_prev)

    kunder_rows = (_build_reskontro_rows(reskontro_df, mode="kunder")
                   if _has_reskontro_columns(reskontro_df, "kunder") else [])
    lev_rows = (_build_reskontro_rows(reskontro_df, mode="leverandorer")
                if _has_reskontro_columns(reskontro_df, "leverandorer") else [])

    return NokkeltallResult(
        metrics=metrics,
        kpi_cards=_build_kpi_cards(ub, ub_prev),
        pl_summary=_build_summary_lines(ub, ub_prev, rl_names, meta,
                                        line_type="PL"),
        bs_summary=bs_all,
        bs_eiendeler=bs_eiendeler,
        bs_ek_gjeld=bs_ek_gjeld,
        cost_breakdown=_build_cost_breakdown(ub),
        bs_breakdown=_build_bs_breakdown(ub),
        top_activity=_build_top_activity(rl_df, transactions_df,
                                         sumpost_set=meta.sumpost_set),
        top_changes=_build_top_changes(rl_df, sumpost_set=meta.sumpost_set),
        concentration=_build_concentration(rl_df, ub),
        observations=_build_observations(metrics),
        reskontro_kunder_top_ub=_top_n(kunder_rows, key=lambda r: r.ub),
        reskontro_lev_top_ub=_top_n(lev_rows, key=lambda r: r.ub),
        reskontro_kunder_top_debet=_top_n(kunder_rows, key=lambda r: r.debet),
        reskontro_lev_top_kredit=_top_n(lev_rows, key=lambda r: r.kredit),
        has_prev_year=has_prev,
        client=str(client),
        year=str(year or ""),
    )
