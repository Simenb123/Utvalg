"""Scoping engine - klassifiser regnskapslinjer mot vesentlighetsgrenser.

Ren logikk, ingen UI eller database. Tar inn data fra eksisterende moduler
og returnerer klassifiserings- og scoping-resultat per regnskapslinje.

Klassifiseringsregler (fra ISA 320):
  - Belop >= PM  ->  "vesentlig"  (full revisjonshandling)
  - SUM <= Belop < PM  ->  "moderat"  (begrenset/analytisk revisjon)
  - Belop < SUM  ->  "ikke_vesentlig"  (ingen/minimal revisjon)
  - Manuelt flagget  ->  "manuell"  (spesiell oppmerksomhet)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ScopingLine:
    regnr: str
    regnskapslinje: str
    line_type: str = ""              # "BS" | "PL"
    amount: float = 0.0              # UB i ar
    amount_prior: float | None = None  # UB i fjor
    change_amount: float | None = None  # Endring i belop vs UB i fjor
    change_pct: float | None = None     # Endring i % vs UB i fjor
    pct_of_pm: float = 0.0            # |belop| / PM (i %)
    classification: str = ""          # vesentlig | moderat | ikke_vesentlig | manuell
    auto_classification: str = ""     # Alltid beregnet, uavhengig av manuell overstyring
    scoping: str = ""                 # "inn" | "ut" | ""
    rationale: str = ""               # Begrunnelse
    audit_action: str = ""            # Revisjonshandling (fritekst)
    action_count: int = 0             # Antall CRM-handlinger matchet
    has_ib_ub_avvik: bool = False
    is_summary: bool = False          # Sumpost - ikke del av scoping-beregning
    manual: bool = False              # True hvis scoping er manuelt satt (ikke auto)


@dataclass
class ScopingResult:
    lines: list[ScopingLine] = field(default_factory=list)
    om: float = 0.0
    pm: float = 0.0
    sum_threshold: float = 0.0
    scoped_out_total: float = 0.0
    aggregation_ok: bool = True


def classify_line(amount: float, pm: float, sum_threshold: float) -> str:
    """Auto-klassifiser basert på vesentlighetsgrenser."""
    if pm <= 0:
        return ""
    abs_amount = abs(amount)
    if abs_amount >= pm:
        return "vesentlig"
    if abs_amount >= sum_threshold:
        return "moderat"
    return "ikke_vesentlig"


def _coerce_optional_amount(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _change_amount(current: float, prior: float | None) -> float | None:
    if prior is None:
        return None
    return current - prior


def _change_pct(current: float, prior: float | None) -> float | None:
    if prior is None:
        return None
    if abs(prior) < 1e-9:
        return 0.0 if abs(current) < 1e-9 else 100.0
    return round((current - prior) / abs(prior) * 100, 1)


def _pct_of_pm(amount: float, pm: float) -> float:
    if pm <= 0:
        return 0.0
    return round(abs(amount) / pm * 100, 1)


def build_scoping(
    rl_pivot: pd.DataFrame,
    materiality: dict | None = None,
    *,
    action_counts: dict[str, int] | None = None,
    ib_ub_avvik: set[str] | None = None,
    overrides: dict[str, dict] | None = None,
    summary_regnr: set[str] | None = None,
    auto_suggestions: dict[str, str] | None = None,
) -> ScopingResult:
    """Bygg scoping-resultat fra regnskapslinje-pivot og vesentlighetsdata.

    Parameters
    ----------
    rl_pivot : DataFrame
        Fra ``build_rl_pivot()`` med kolonnene: regnr, regnskapslinje, IB, UB,
        Endring, Antall, og eventuelt UB_fjor/Endring_fjor/Endring_pct.
    materiality : dict
        Fra ``materiality_store.load_state()`` - bruker ``active_materiality``.
    action_counts : dict, optional
        regnr (str) -> antall CRM-handlinger.
    ib_ub_avvik : set, optional
        Sett med regnr (str) som har IB/UB-avvik.
    overrides : dict, optional
        regnr (str) -> {scoping, rationale, classification} for manuelle overstyringer.
    auto_suggestions : dict, optional
        regnr (str) -> "ut" — automatisk foreslått scope-ut fra
        ``compute_auto_scope_out``. Brukes kun for linjer som ikke har
        manuell overstyring; manuell vinner alltid.
    """
    om = 0.0
    pm = 0.0
    sum_threshold = 0.0
    if materiality:
        am = materiality.get("active_materiality") or {}
        om = float(am.get("overall_materiality", 0) or 0)
        pm = float(am.get("performance_materiality", 0) or 0)
        sum_threshold = float(am.get("clearly_trivial", 0) or 0)

    action_counts = action_counts or {}
    ib_ub_avvik = ib_ub_avvik or set()
    overrides = overrides or {}
    auto_suggestions = auto_suggestions or {}

    lines: list[ScopingLine] = []

    if rl_pivot is None or rl_pivot.empty:
        return ScopingResult(om=om, pm=pm, sum_threshold=sum_threshold)

    type_map: dict[str, str] = {}
    summary_set: set[str] = set()
    try:
        from regnskap_config import load_regnskapslinjer
        from regnskap_mapping import normalize_regnskapslinjer

        rl_cfg = load_regnskapslinjer()
        for _, row in rl_cfg.iterrows():
            nr = str(row.get("nr", "")).strip()
            rb = str(row.get("resultat/balanse", "")).strip().lower()
            if "resultat" in rb:
                type_map[nr] = "PL"
            elif "balanse" in rb:
                type_map[nr] = "BS"

        regn = normalize_regnskapslinjer(rl_cfg)
        for _, row in regn.iterrows():
            if bool(row.get("sumpost", False)):
                summary_set.add(str(int(row["regnr"])))
    except Exception:
        pass

    if summary_regnr:
        summary_set |= summary_regnr

    for _, row in rl_pivot.iterrows():
        regnr = str(int(row.get("regnr", 0)))
        regnskapslinje = str(row.get("regnskapslinje", ""))
        ub = float(row.get("UB", 0) or 0)
        ub_fjor = _coerce_optional_amount(row.get("UB_fjor", None))

        line_type = type_map.get(regnr, "")
        is_sum = regnr in summary_set
        auto_class = "" if is_sum else classify_line(ub, pm, sum_threshold)

        ovr = overrides.get(regnr, {})
        classification = "" if is_sum else (ovr.get("classification", "") or auto_class)
        # Manuell overstyring vinner over auto-forslag. Sumposter får
        # aldri scoping. Hvis override ikke har 'scoping'-nøkkel,
        # prøver vi auto_suggestions.
        manual_scoping = ovr.get("scoping", "")
        manual_flag = False
        if is_sum:
            scoping = ""
        elif manual_scoping:
            scoping = manual_scoping
            manual_flag = True
        else:
            scoping = auto_suggestions.get(regnr, "")
        rationale = "" if is_sum else ovr.get("rationale", "")
        audit_action = "" if is_sum else ovr.get("audit_action", "")

        line = ScopingLine(
            regnr=regnr,
            regnskapslinje=regnskapslinje,
            line_type=line_type,
            amount=ub,
            amount_prior=ub_fjor,
            change_amount=_change_amount(ub, ub_fjor),
            change_pct=_change_pct(ub, ub_fjor),
            pct_of_pm=_pct_of_pm(ub, pm) if not is_sum else 0.0,
            classification=classification,
            auto_classification=auto_class,
            scoping=scoping,
            rationale=rationale,
            audit_action=audit_action,
            action_count=action_counts.get(regnr, 0),
            has_ib_ub_avvik=regnr in ib_ub_avvik,
            is_summary=is_sum,
            manual=manual_flag,
        )
        lines.append(line)

    lines.sort(key=lambda l: int(l.regnr) if l.regnr.isdigit() else 9999)

    scoped_out_total = sum(abs(l.amount) for l in lines if l.scoping == "ut" and not l.is_summary)
    aggregation_ok = scoped_out_total < om if om > 0 else True

    return ScopingResult(
        lines=lines,
        om=om,
        pm=pm,
        sum_threshold=sum_threshold,
        scoped_out_total=scoped_out_total,
        aggregation_ok=aggregation_ok,
    )


# =====================================================================
# Auto-scope-out — greedy algoritme per PL/BS, cap ved PM
# =====================================================================


def compute_auto_scope_out(
    lines: list[ScopingLine],
    pm: float,
) -> dict[str, str]:
    """Beregn automatisk scope-ut-forslag per regnskapslinje.

    Algoritme (se POPUP_STANDARD / scoping-diskusjon):
      - Behandle PL og BS hver for seg
      - Filtrer til kandidater: is_summary=False og |amount| < pm
      - Sortér kandidatene stigende på absoluttverdi (minste først)
      - Greedy-akkumuler: mark som "ut" så lenge akkumulert sum pluss
        neste linje ≤ pm. Så snart neste linje ville pushe over,
        stopp — den linjen og alle større blir *ikke* scoped ut.
      - Linjer med |amount| ≥ pm er aldri kandidater (alltid i scope).

    Returnerer en dict ``{regnr: "ut" | ""}`` for alle ikke-sumlinjer,
    slik at calleren kan merge resultatet inn i en større scoping-
    tilstand. Linjer som ikke er i returnert dict skal behandles som
    "inn" (default).

    Ved pm ≤ 0 returneres en tom dict (ingen auto-scoping).
    """
    if pm <= 0:
        return {}

    result: dict[str, str] = {}

    for group in ("PL", "BS"):
        # Filtrer til kandidater og sortér stigende på |amount|.
        candidates = [
            ln for ln in lines
            if not ln.is_summary
            and (ln.line_type or "").upper() == group
            and abs(ln.amount) < pm
        ]
        candidates.sort(key=lambda ln: abs(ln.amount))

        cumulative = 0.0
        for ln in candidates:
            size = abs(ln.amount)
            if cumulative + size > pm:
                # Denne linjen og alle større forblir IN scope.
                break
            result[ln.regnr] = "ut"
            cumulative += size

    return result


def scoped_out_totals_by_group(lines: list[ScopingLine]) -> dict[str, float]:
    """Summér |amount| per gruppe (PL, BS) for linjer markert scoping='ut'.

    Brukes av UI-en til å vise hvor mye som er scoped ut per gruppe og
    varsle hvis aggregatet overstiger PM. Sumposter ekskluderes.
    """
    totals: dict[str, float] = {"PL": 0.0, "BS": 0.0}
    for ln in lines:
        if ln.is_summary or ln.scoping != "ut":
            continue
        group = (ln.line_type or "").upper()
        if group in totals:
            totals[group] += abs(ln.amount)
    return totals
