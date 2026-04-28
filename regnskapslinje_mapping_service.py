"""regnskapslinje_mapping_service.py

Kanonisk RL-mapping-service for hele applikasjonen.

Denne modulen er den ene sannhetskilden for konto -> regnr ->
regnskapslinje-oppløsning. Den eier:

- lasting og normalisering av intervall-mapping fra ``regnskap_config``
- lasting og normalisering av regnskapslinjer fra ``regnskap_config``
- lasting av klientspesifikke konto-overrides fra
  ``regnskap_client_overrides``
- statusklassifisering: ``interval`` | ``override`` | ``unmapped`` |
  ``sumline``
- bygging av problem-/diagnoseobjekter (``RLMappingIssue``)
- enrichment med smartforslag fra ``regnskapslinje_suggest``

Analyse, Saldobalanse og Admin skal lese fra denne modulen i stedet for
å løse opp konto -> regnr lokalt.

Forholdet til ``analyse_mapping_service``: den modulen er i runde 1
beholdt som tynn fasade som videresender til denne servicen, slik at
eksisterende importer fortsatt virker.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Optional, Sequence

import logging

import pandas as pd

import regnskapslinje_suggest
from a07_feature import AccountUsageFeatures, build_account_usage_features
from src.shared.regnskap.mapping import (
    apply_account_overrides,
    apply_interval_mapping,
    normalize_intervals,
    normalize_regnskapslinjer,
)


log = logging.getLogger("app")


# ---------------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RLMappingIssue:
    """Kanonisk diagnose-objekt for én konto i RL-mappingen.

    Felt-for-felt kompatibel med eldre ``UnmappedAccountIssue`` slik at
    overgangen kan skje stegvis uten å bryte konsumenter.

    ``mapping_status`` er ett av:
      - ``interval``: konto ble truffet av et intervall i baseline-mapping
      - ``override``: klientoverride satte regnr eksplisitt
      - ``unmapped``: ingen intervall traff og ingen override eksisterer
      - ``sumline``: regnr peker på en sumpost (sumlinje), ikke en
        operasjonell leaf-linje — dette regnes som et problem
    """

    konto: str
    kontonavn: str
    kilde: str  # HB | SB | AO_ONLY  (datakilde, ikke mappingkilde)
    belop: float
    regnr: int | None
    regnskapslinje: str
    mapping_status: str
    mapping_source: str = ""  # interval | override | "" — hvor regnr-tildelingen kom fra
    suggested_regnr: int | None = None
    suggested_regnskapslinje: str = ""
    suggestion_reason: str = ""
    suggestion_source: str = ""
    confidence_bucket: str = ""
    suggestion_confidence: float | None = None
    sign_note: str = ""
    ib: float = 0.0
    movement: float = 0.0
    ub: float = 0.0

    @property
    def has_value(self) -> bool:
        return abs(float(self.belop or 0.0)) > 0.005

    @property
    def is_problem(self) -> bool:
        """En issue er et problem hvis statusen krever brukerhandling."""
        return self.mapping_status in {"unmapped", "sumline"}

    @property
    def has_suggestion_conflict(self) -> bool:
        """True hvis suggesteren foreslår en *annen* RL enn nåværende mapping.

        Brukes til å flagge rader i SB-treet og konflikt-panel i remap-
        dialogen. Krever at suggesteren har høy nok confidence (>= 0.7)
        for å unngå støy fra usikre forslag.
        """
        if self.suggested_regnr is None or self.regnr is None:
            return False
        if self.suggestion_confidence is None or float(self.suggestion_confidence) < 0.7:
            return False
        return int(self.suggested_regnr) != int(self.regnr)


@dataclass(frozen=True)
class RLAdminRow:
    """Eksplisitt RL-rad for Admin med både baseline, override og effektiv mapping.

    I motsetning til ``RLMappingIssue`` (som komprimerer baseline+override
    til et enkelt ``regnr``) holder denne raden hver kilde separat slik at
    Admin kan vise og styre den fulle beslutningskjeden.
    """

    konto: str
    kontonavn: str
    interval_regnr: int | None
    override_regnr: int | None
    effective_regnr: int | None
    effective_regnskapslinje: str
    mapping_status: str
    mapping_source: str
    is_sumline: bool
    suggested_regnr: int | None = None
    suggested_regnskapslinje: str = ""
    suggestion_reason: str = ""
    suggestion_source: str = ""
    confidence_bucket: str = ""
    suggestion_confidence: float | None = None
    sign_note: str = ""
    kilde: str = ""
    belop: float = 0.0
    ub: float = 0.0

    @property
    def has_value(self) -> bool:
        return abs(float(self.belop or 0.0)) > 0.005

    @property
    def is_problem(self) -> bool:
        return self.mapping_status in {"unmapped", "sumline"}


@dataclass(frozen=True)
class RLMappingContext:
    """Lastet og normalisert grunnlag for konto -> RL-oppløsning.

    Bygges én gang per (klient, år) og deles av alle konsumenter.
    Holder bare normaliserte tabeller og oppslagsstrukturer — ingen
    referanser til GUI eller AnalysePage.
    """

    intervals: pd.DataFrame  # normalisert: fra/til/regnr
    regnskapslinjer: pd.DataFrame  # normalisert: regnr/regnskapslinje/sumpost/...
    account_overrides: dict[str, int] = field(default_factory=dict)
    rl_name_by_regnr: dict[int, str] = field(default_factory=dict)
    sumline_regnr: frozenset[int] = field(default_factory=frozenset)
    client: str = ""
    year: str = ""

    @property
    def is_empty(self) -> bool:
        return self.intervals is None or self.intervals.empty or self.regnskapslinjer is None or self.regnskapslinjer.empty


# ---------------------------------------------------------------------------
# Lasting / normalisering
# ---------------------------------------------------------------------------


def load_rl_config_dataframes() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Last (intervals, regnskapslinjer) fra ``regnskap_config``.

    Offentlig loader-API for konsumenter som bare trenger rå tabeller
    (typisk Analyse-fanens preload). Bruk ``load_rl_mapping_context``
    når du trenger en full kontekst med klient-overrides og
    sumlinje-indeks.
    """
    return _safe_load_intervals(), _safe_load_regnskapslinjer()


def _safe_load_intervals() -> pd.DataFrame | None:
    try:
        import src.shared.regnskap.config as regnskap_config

        return regnskap_config.load_kontoplan_mapping()
    except Exception as exc:
        log.debug("Intervall-mapping ikke tilgjengelig: %s", exc)
        return None


def _safe_load_regnskapslinjer() -> pd.DataFrame | None:
    try:
        import src.shared.regnskap.config as regnskap_config

        return regnskap_config.load_regnskapslinjer()
    except Exception as exc:
        log.debug("Regnskapslinjer ikke tilgjengelig: %s", exc)
        return None


def _safe_load_account_overrides(client: str | None, year: str | None) -> dict[str, int]:
    if not client:
        return {}
    try:
        import src.shared.regnskap.client_overrides as regnskap_client_overrides

        return regnskap_client_overrides.load_account_overrides(client, year=year)
    except Exception as exc:
        log.debug("Klientoverstyringer ikke tilgjengelig for %s/%s: %s", client, year, exc)
        return {}


def _normalize_or_empty_intervals(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["fra", "til", "regnr"])
    try:
        return normalize_intervals(df)
    except Exception as exc:
        log.warning("normalize_intervals feilet: %s", exc)
        return pd.DataFrame(columns=["fra", "til", "regnr"])


def _normalize_or_empty_regnskapslinjer(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["regnr", "regnskapslinje", "sumpost", "formel"])
    try:
        return normalize_regnskapslinjer(df)
    except Exception as exc:
        log.warning("normalize_regnskapslinjer feilet: %s", exc)
        return pd.DataFrame(columns=["regnr", "regnskapslinje", "sumpost", "formel"])


def load_rl_mapping_context(
    client: str | None = None,
    year: str | None = None,
    *,
    intervals: pd.DataFrame | None = None,
    regnskapslinjer: pd.DataFrame | None = None,
    account_overrides: Mapping[str, int] | None = None,
) -> RLMappingContext:
    """Bygg en kanonisk ``RLMappingContext``.

    Kallere kan injisere ``intervals``/``regnskapslinjer``/
    ``account_overrides`` for å unngå disk-IO (typisk i tester eller når
    AnalysePage allerede har preloaded dataene). Hvis ikke gitt lastes
    de fra ``regnskap_config`` og ``regnskap_client_overrides``.
    """
    raw_intervals = intervals if intervals is not None else _safe_load_intervals()
    raw_regnskapslinjer = regnskapslinjer if regnskapslinjer is not None else _safe_load_regnskapslinjer()
    norm_intervals = _normalize_or_empty_intervals(raw_intervals)
    norm_regn = _normalize_or_empty_regnskapslinjer(raw_regnskapslinjer)

    overrides: dict[str, int] = {}
    if account_overrides is not None:
        for konto, regnr in account_overrides.items():
            konto_s = str(konto or "").strip()
            if not konto_s:
                continue
            try:
                overrides[konto_s] = int(regnr)
            except Exception:
                continue
    else:
        overrides = _safe_load_account_overrides(client, str(year) if year else None)

    rl_names: dict[int, str] = {}
    sumlines: set[int] = set()
    if not norm_regn.empty:
        for _, row in norm_regn.iterrows():
            regnr_val = row.get("regnr")
            if pd.isna(regnr_val):
                continue
            try:
                rid = int(regnr_val)
            except Exception:
                continue
            rl_names[rid] = str(row.get("regnskapslinje", "") or "")
            if bool(row.get("sumpost", False)):
                sumlines.add(rid)

    return RLMappingContext(
        intervals=norm_intervals,
        regnskapslinjer=norm_regn,
        account_overrides=overrides,
        rl_name_by_regnr=rl_names,
        sumline_regnr=frozenset(sumlines),
        client=str(client or ""),
        year=str(year or ""),
    )


# ---------------------------------------------------------------------------
# Oppslag
# ---------------------------------------------------------------------------


def resolve_accounts_to_rl(
    accounts: Iterable[str],
    *,
    context: RLMappingContext,
) -> pd.DataFrame:
    """Returner DataFrame[konto, regnr, regnskapslinje, mapping_status, source].

    ``mapping_status`` følger samme regler som ``RLMappingIssue``:

      - ``override``: klient-override satte regnr
      - ``interval``: intervalltreff fra baseline
      - ``sumline``: regnr peker på en sumpost
      - ``unmapped``: ingen intervalltreff og ingen override

    ``source`` er ``override`` eller ``interval`` (interval brukes også
    når en interval-truffet konto havner på en sumpost).
    """
    konto_list = [str(k or "").strip() for k in accounts]
    konto_list = [k for k in konto_list if k]
    out_cols = ["konto", "regnr", "regnskapslinje", "mapping_status", "source"]

    if not konto_list:
        return pd.DataFrame(columns=out_cols)

    # Distinkt oppslag, men preserve første rekkefølge
    seen: set[str] = set()
    unique: list[str] = []
    for konto in konto_list:
        if konto in seen:
            continue
        seen.add(konto)
        unique.append(konto)

    interval_regnr_by_konto: dict[str, int | None] = {}
    if context.intervals is not None and not context.intervals.empty:
        probe = pd.DataFrame({"konto": unique})
        mapped = apply_interval_mapping(probe, context.intervals, konto_col="konto").mapped
        for _, row in mapped.iterrows():
            konto = str(row.get("konto", "") or "")
            regnr_val = row.get("regnr")
            interval_regnr_by_konto[konto] = int(regnr_val) if pd.notna(regnr_val) else None

    rows: list[dict[str, Any]] = []
    for konto in unique:
        override_regnr = context.account_overrides.get(konto)
        interval_regnr = interval_regnr_by_konto.get(konto)

        if override_regnr is not None:
            regnr = int(override_regnr)
            source = "override"
        elif interval_regnr is not None:
            regnr = int(interval_regnr)
            source = "interval"
        else:
            rows.append(
                {
                    "konto": konto,
                    "regnr": pd.NA,
                    "regnskapslinje": "",
                    "mapping_status": "unmapped",
                    "source": "",
                }
            )
            continue

        if regnr in context.sumline_regnr:
            status = "sumline"
        elif source == "override":
            status = "override"
        else:
            status = "interval"

        rows.append(
            {
                "konto": konto,
                "regnr": regnr,
                "regnskapslinje": context.rl_name_by_regnr.get(regnr, ""),
                "mapping_status": status,
                "source": source,
            }
        )

    out = pd.DataFrame(rows, columns=out_cols)
    out["regnr"] = out["regnr"].astype("Int64")
    return out


# ---------------------------------------------------------------------------
# Issue-bygging
# ---------------------------------------------------------------------------


def _group_hb(df_hb: pd.DataFrame | None) -> pd.DataFrame:
    if df_hb is None or not isinstance(df_hb, pd.DataFrame) or df_hb.empty:
        return pd.DataFrame(columns=["konto", "kontonavn_hb", "hb_sum"])
    if "Konto" not in df_hb.columns:
        return pd.DataFrame(columns=["konto", "kontonavn_hb", "hb_sum"])
    work = pd.DataFrame({"konto": df_hb["Konto"].astype(str).str.strip()})
    work["kontonavn_hb"] = (
        df_hb["Kontonavn"].fillna("").astype(str) if "Kontonavn" in df_hb.columns else ""
    )
    if "Beløp" in df_hb.columns:
        work["hb_sum"] = pd.to_numeric(df_hb["Beløp"], errors="coerce").fillna(0.0)
    else:
        work["hb_sum"] = 0.0
    return work.groupby("konto", as_index=False).agg(
        kontonavn_hb=("kontonavn_hb", "first"),
        hb_sum=("hb_sum", "sum"),
    )


def _group_sb(sb_df: pd.DataFrame | None) -> pd.DataFrame:
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return pd.DataFrame(columns=["konto", "kontonavn_sb", "sb_ub", "sb_ib", "exists_in_sb"])
    col_map: dict[str, str] = {}
    for c in sb_df.columns:
        cl = str(c).strip().lower()
        if cl == "konto":
            col_map["konto"] = c
        elif cl == "kontonavn":
            col_map["kontonavn"] = c
        elif cl == "ub":
            col_map["ub"] = c
        elif cl == "ib":
            col_map["ib"] = c
    konto_col = col_map.get("konto")
    if not konto_col:
        return pd.DataFrame(columns=["konto", "kontonavn_sb", "sb_ub", "sb_ib", "exists_in_sb"])
    work = pd.DataFrame({"konto": sb_df[konto_col].astype(str).str.strip()})
    work["kontonavn_sb"] = (
        sb_df[col_map["kontonavn"]].fillna("").astype(str)
        if "kontonavn" in col_map
        else ""
    )
    work["sb_ub"] = pd.to_numeric(sb_df[col_map["ub"]], errors="coerce").fillna(0.0) if "ub" in col_map else 0.0
    work["sb_ib"] = pd.to_numeric(sb_df[col_map["ib"]], errors="coerce").fillna(0.0) if "ib" in col_map else 0.0
    out = work.groupby("konto", as_index=False).agg(
        kontonavn_sb=("kontonavn_sb", "first"),
        sb_ub=("sb_ub", "sum"),
        sb_ib=("sb_ib", "sum"),
    )
    out["exists_in_sb"] = True
    return out


def build_rl_mapping_issues(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    context: RLMappingContext,
    include_ao: bool = False,
) -> list[RLMappingIssue]:
    """Bygg standardiserte mapping-issues for alle kontoer i HB+SB.

    Bruker ``context`` for konto -> regnr-oppløsning. Hvis context er
    tom (ikke importerte regnskapslinjer/intervaller) markeres alle
    kontoer som ``unmapped``.
    """
    hb_grouped = _group_hb(hb_df)
    sb_grouped = _group_sb(effective_sb_df)
    base = hb_grouped.merge(sb_grouped, how="outer", on="konto")
    if base.empty:
        return []

    for col in ("kontonavn_hb", "kontonavn_sb"):
        if col in base.columns:
            base[col] = base[col].fillna("").astype(str)
    for col in ("hb_sum", "sb_ub", "sb_ib"):
        if col in base.columns:
            base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0.0)
    if "exists_in_sb" not in base.columns:
        base["exists_in_sb"] = False
    base["exists_in_sb"] = base["exists_in_sb"].fillna(False).astype(bool)
    base["exists_in_hb"] = (
        base["konto"].isin(set(hb_grouped["konto"].astype(str)))
        if not hb_grouped.empty
        else False
    )
    base["kontonavn"] = base["kontonavn_hb"].where(
        base["kontonavn_hb"].str.strip() != "", base["kontonavn_sb"]
    ).fillna("")
    base["belop"] = base["sb_ub"].where(base["exists_in_sb"], base["hb_sum"]).fillna(0.0)

    accounts = base["konto"].astype(str).str.strip().tolist()
    resolution = resolve_accounts_to_rl(accounts, context=context)
    res_by_konto: dict[str, dict[str, Any]] = {}
    for _, row in resolution.iterrows():
        res_by_konto[str(row["konto"])] = {
            "regnr": int(row["regnr"]) if pd.notna(row["regnr"]) else None,
            "regnskapslinje": str(row.get("regnskapslinje", "") or ""),
            "mapping_status": str(row.get("mapping_status", "") or "unmapped"),
            "mapping_source": str(row.get("source", "") or ""),
        }

    issues: list[RLMappingIssue] = []
    for _, row in base.iterrows():
        konto = str(row.get("konto", "") or "").strip()
        if not konto:
            continue
        if bool(row.get("exists_in_hb", False)):
            kilde = "HB"
        elif include_ao and bool(row.get("exists_in_sb", False)):
            kilde = "AO_ONLY"
        else:
            kilde = "SB"

        resolved = res_by_konto.get(
            konto,
            {"regnr": None, "regnskapslinje": "", "mapping_status": "unmapped", "mapping_source": ""},
        )

        sb_ub = float(row.get("sb_ub", 0.0) or 0.0)
        hb_sum = float(row.get("hb_sum", 0.0) or 0.0)
        sb_ib = float(row.get("sb_ib", 0.0) or 0.0)
        eff_ub = sb_ub if bool(row.get("exists_in_sb", False)) else hb_sum
        movement = eff_ub - sb_ib

        issues.append(
            RLMappingIssue(
                konto=konto,
                kontonavn=str(row.get("kontonavn", "") or ""),
                kilde=kilde,
                belop=float(row.get("belop", 0.0) or 0.0),
                regnr=resolved["regnr"],
                regnskapslinje=resolved["regnskapslinje"],
                mapping_status=resolved["mapping_status"],
                mapping_source=resolved["mapping_source"],
                ib=sb_ib,
                movement=movement,
                ub=eff_ub,
            )
        )
    return issues


def build_admin_rl_rows(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    context: RLMappingContext,
    include_ao: bool = False,
    enrich: bool = False,
    rulebook_document: dict[str, Any] | None = None,
    usage_features: dict[str, AccountUsageFeatures] | None = None,
    historical_overrides: dict[str, int] | None = None,
    owned_companies: list[regnskapslinje_suggest.OwnedCompany] | None = None,
) -> list[RLAdminRow]:
    """Bygg Admin-rader med eksplisitt baseline + override + effektiv mapping.

    Returnerer én rad per konto i HB+SB med tre uavhengige regnr-felt:
    intervall (baseline), override (klient), og effektiv (faktisk
    valgt). ``mapping_status`` og ``mapping_source`` følger samme
    taksonomi som ``RLMappingIssue``.
    """
    issues = build_rl_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        context=context,
        include_ao=include_ao,
    )
    if enrich:
        issues = enrich_rl_mapping_issues_with_suggestions(
            issues,
            regnskapslinjer=context.regnskapslinjer,
            usage_features=usage_features,
            historical_overrides=historical_overrides,
            rulebook_document=rulebook_document,
            owned_companies=owned_companies,
        )

    accounts = [issue.konto for issue in issues]
    interval_regnr_by_konto: dict[str, int | None] = {}
    if accounts and context.intervals is not None and not context.intervals.empty:
        probe = pd.DataFrame({"konto": accounts})
        mapped = apply_interval_mapping(probe, context.intervals, konto_col="konto").mapped
        for _, row in mapped.iterrows():
            konto = str(row.get("konto", "") or "")
            regnr_val = row.get("regnr")
            interval_regnr_by_konto[konto] = (
                int(regnr_val) if pd.notna(regnr_val) else None
            )

    rows: list[RLAdminRow] = []
    for issue in issues:
        interval_regnr = interval_regnr_by_konto.get(issue.konto)
        override_val = context.account_overrides.get(issue.konto)
        override_regnr = int(override_val) if override_val is not None else None
        effective_regnr = issue.regnr
        is_sumline = (
            effective_regnr is not None and effective_regnr in context.sumline_regnr
        )
        rows.append(
            RLAdminRow(
                konto=issue.konto,
                kontonavn=issue.kontonavn,
                interval_regnr=interval_regnr,
                override_regnr=override_regnr,
                effective_regnr=effective_regnr,
                effective_regnskapslinje=issue.regnskapslinje,
                mapping_status=issue.mapping_status,
                mapping_source=issue.mapping_source,
                is_sumline=is_sumline,
                suggested_regnr=issue.suggested_regnr,
                suggested_regnskapslinje=issue.suggested_regnskapslinje,
                suggestion_reason=issue.suggestion_reason,
                suggestion_source=issue.suggestion_source,
                confidence_bucket=issue.confidence_bucket,
                suggestion_confidence=issue.suggestion_confidence,
                sign_note=issue.sign_note,
                kilde=issue.kilde,
                belop=issue.belop,
                ub=issue.ub,
            )
        )
    return rows


def set_account_override(
    client: str,
    konto: str,
    regnr: int,
    *,
    year: str | None = None,
) -> Any:
    """Sett (opprett/oppdater) en konto-override for klienten.

    Tynn wrapper over ``regnskap_client_overrides.set_account_override``
    slik at Admin og andre konsumenter kun har Ã©n service-inngang for
    RL-mutasjoner.
    """
    import src.shared.regnskap.client_overrides as regnskap_client_overrides

    return regnskap_client_overrides.set_account_override(
        str(client), str(konto), int(regnr), year=year
    )


def clear_account_override(
    client: str,
    konto: str,
    *,
    year: str | None = None,
) -> Any:
    """Fjern en konto-override for klienten.

    Tynn wrapper over ``regnskap_client_overrides.remove_account_override``.
    """
    import src.shared.regnskap.client_overrides as regnskap_client_overrides

    return regnskap_client_overrides.remove_account_override(
        str(client), str(konto), year=year
    )


def enrich_rl_mapping_issues_with_suggestions(
    issues: list[RLMappingIssue],
    *,
    regnskapslinjer: pd.DataFrame | None,
    usage_features: dict[str, AccountUsageFeatures] | None = None,
    historical_overrides: dict[str, int] | None = None,
    rulebook_document: dict[str, Any] | None = None,
    owned_companies: list[regnskapslinje_suggest.OwnedCompany] | None = None,
) -> list[RLMappingIssue]:
    """Berik *alle* issues med smartforslag fra ``regnskapslinje_suggest``.

    Tidligere kjørte denne kun for problem-issues (unmapped/sumline). Nå
    kjører den også for ``interval``- og ``override``-mappede kontoer slik
    at vi kan oppdage konflikter — kontoer der suggesteren foreslår en
    annen RL enn nåværende mapping (se ``RLMappingIssue.has_suggestion_conflict``).

    Performance: ``build_candidates(...)`` heves ut av loopen og gjenbrukes
    for alle issues, slik at vi ikke betaler tokenisering per konto.

    ``owned_companies`` brukes til AR-basert akronym-bonus — kontoer som
    matcher et eid selskap (fullt navn eller akronym) får sterk bonus mot
    560/575/585 avhengig av eierskapsgrad.
    """
    if not issues:
        return []
    candidates = regnskapslinje_suggest.build_candidates(
        regnskapslinjer, rulebook_document=rulebook_document
    )
    out: list[RLMappingIssue] = []
    for issue in issues:
        suggestion = regnskapslinje_suggest.suggest_with_candidates(
            candidates,
            konto=issue.konto,
            kontonavn=issue.kontonavn,
            ib=issue.ib,
            movement=issue.movement,
            ub=issue.ub,
            usage=(usage_features or {}).get(issue.konto),
            historical_regnr=(historical_overrides or {}).get(issue.konto),
            owned_companies=owned_companies,
        )
        if suggestion is None:
            out.append(issue)
            continue
        out.append(
            replace(
                issue,
                suggested_regnr=suggestion.regnr,
                suggested_regnskapslinje=suggestion.regnskapslinje,
                suggestion_reason=suggestion.reason,
                suggestion_source=suggestion.source,
                confidence_bucket=suggestion.confidence_bucket,
                suggestion_confidence=suggestion.confidence,
                sign_note=suggestion.sign_note,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Filtre / oppsummering
# ---------------------------------------------------------------------------


def problem_rl_mapping_issues(
    issues: list[RLMappingIssue],
    *,
    include_zero: bool = False,
) -> list[RLMappingIssue]:
    out: list[RLMappingIssue] = []
    for issue in issues:
        if not issue.is_problem:
            continue
        if include_zero or issue.has_value:
            out.append(issue)
    return out


def get_problem_rl_accounts(issues: list[RLMappingIssue]) -> list[str]:
    return [issue.konto for issue in problem_rl_mapping_issues(issues, include_zero=False)]


def summarize_rl_mapping_issues(
    issues: list[RLMappingIssue],
    *,
    include_zero: bool = False,
) -> str:
    """Bygg én tekstlinje for banner/statuslinje."""
    problems = problem_rl_mapping_issues(issues, include_zero=include_zero)
    if not problems:
        return ""
    sample = ", ".join(issue.konto for issue in problems[:5])
    if len(problems) > 5:
        sample += ", ..."
    count = len(problems)
    noun = "konto" if count == 1 else "kontoer"
    suggestion_count = sum(1 for issue in problems if issue.suggested_regnr is not None)
    suffix = f" | {suggestion_count} med smartforslag" if suggestion_count else ""
    return f"{count} {noun} mangler regnskapslinje eller er mappet til sumpost ({sample}){suffix}"


@dataclass(frozen=True)
class RLMappingStatusSummary:
    """Aggregert RL-statussammendrag for diagnose-flater (Admin)."""

    total: int
    interval_count: int
    override_count: int
    unmapped_count: int
    sumline_count: int
    problem_count: int
    suggestion_count: int


def summarize_rl_status(
    issues: list[RLMappingIssue],
    *,
    include_zero: bool = False,
) -> RLMappingStatusSummary:
    """Tell antall issues per status — brukes av Admin-statusvisningen."""
    total = 0
    interval = 0
    override = 0
    unmapped = 0
    sumline = 0
    problem = 0
    suggestions = 0
    for issue in issues:
        if not include_zero and not issue.has_value:
            continue
        total += 1
        status = issue.mapping_status
        if status == "interval":
            interval += 1
        elif status == "override":
            override += 1
        elif status == "unmapped":
            unmapped += 1
        elif status == "sumline":
            sumline += 1
        if issue.is_problem:
            problem += 1
        if issue.suggested_regnr is not None:
            suggestions += 1
    return RLMappingStatusSummary(
        total=total,
        interval_count=interval,
        override_count=override,
        unmapped_count=unmapped,
        sumline_count=sumline,
        problem_count=problem,
        suggestion_count=suggestions,
    )


# ---------------------------------------------------------------------------
# Bekvemshelpere for AnalysePage-konsumenter
# ---------------------------------------------------------------------------


def _history_overrides_by_account(client: str | None, year: int | None) -> dict[str, int]:
    if not client or not year:
        return {}
    try:
        import src.shared.regnskap.client_overrides as regnskap_client_overrides

        return regnskap_client_overrides.load_prior_year_overrides(client, str(year))
    except Exception:
        return {}


def _load_owned_companies_for_client(
    client: str | None,
    year: int | None,
) -> list[regnskapslinje_suggest.OwnedCompany]:
    """Last selskaper klienten eier (fra AR/aksjonærregisteret).

    Brukes som hint av regnskapslinje_suggest til å gi bonus-score til
    investerings-kontoer (560/575/585) når kontonavnet matcher et eid
    selskap eller akronymet av det.

    Bruker ``get_client_ownership_overview`` (ikke
    ``list_owned_companies``) slik at vi får med «videreførte»
    eierandeler som ligger i ``accepted_owned_base`` snarere enn i
    rå-registeret. Dette samsvarer med visningen i AR-fanen.

    Returnerer tom liste hvis AR ikke har data for klient/år.
    """
    if not client or not year:
        return []
    try:
        import src.pages.ar.backend.store as ar_store
    except Exception:
        return []
    try:
        overview = ar_store.get_client_ownership_overview(str(client), str(year))
    except Exception:
        return []
    rows = overview.get("owned_companies") if isinstance(overview, dict) else None
    if not isinstance(rows, list):
        return []

    out: list[regnskapslinje_suggest.OwnedCompany] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            name = str(row.get("company_name", "") or "").strip()
            if not name:
                continue
            pct_raw = row.get("ownership_pct", 0.0)
            pct = float(pct_raw) if pct_raw is not None else 0.0
            out.append(
                regnskapslinje_suggest.OwnedCompany(
                    name=name,
                    acronym=regnskapslinje_suggest.company_acronym(name),
                    ownership_pct=pct,
                    suggested_regnr=regnskapslinje_suggest.ownership_pct_to_regnr(pct),
                )
            )
        except Exception:
            continue
    return out


def context_from_page(page: Any) -> RLMappingContext:
    """Bygg ``RLMappingContext`` fra en AnalysePage som har preloadet
    ``_rl_intervals`` og ``_rl_regnskapslinjer`` på seg.

    Bruker session.client/year for klient-overrides hvis tilgjengelig.
    """
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    client: str | None = None
    year: str | None = None
    overrides: dict[str, int] | None = None
    try:
        import session as _session

        client = getattr(_session, "client", None) or None
        year_val = getattr(_session, "year", None)
        year = str(year_val) if year_val else None
    except Exception:
        client = None
        year = None
    if client:
        overrides = _safe_load_account_overrides(client, year)
    return load_rl_mapping_context(
        client=client,
        year=year,
        intervals=intervals,
        regnskapslinjer=regnskapslinjer,
        account_overrides=overrides,
    )


def build_page_admin_rl_rows(
    page: Any,
    *,
    use_filtered_hb: bool = False,
) -> list[RLAdminRow]:
    """Bygg Admin-rader for en AnalysePage med smartforslag inkludert.

    Samler context, HB/SB, usage-features og historikk fra siden, og
    delegerer row-assemblyen til den kanoniske
    ``build_admin_rl_rows``-funksjonen. Selve rekonstruksjonen av
    baseline/override/effektiv mapping skjer dermed kun ett sted.
    """
    hb_df = (
        getattr(page, "_df_filtered", None)
        if use_filtered_hb
        else getattr(page, "dataset", None)
    )
    try:
        effective_sb = page._get_effective_sb_df()
    except Exception:
        effective_sb = getattr(page, "_rl_sb_df", None)
    try:
        include_ao = bool(page._include_ao_enabled())
    except Exception:
        include_ao = False

    context = context_from_page(page)

    usage_features: dict[str, AccountUsageFeatures] = {}
    dataset = getattr(page, "dataset", None)
    if isinstance(dataset, pd.DataFrame) and not dataset.empty:
        try:
            usage_features = build_account_usage_features(dataset)
        except Exception:
            usage_features = {}

    year_int: int | None = None
    try:
        if context.year:
            year_int = int(str(context.year).strip())
    except Exception:
        year_int = None

    return build_admin_rl_rows(
        hb_df=hb_df if isinstance(hb_df, pd.DataFrame) else None,
        effective_sb_df=effective_sb if isinstance(effective_sb, pd.DataFrame) else None,
        context=context,
        include_ao=include_ao,
        enrich=True,
        rulebook_document=regnskapslinje_suggest.load_rulebook_document(),
        usage_features=usage_features,
        historical_overrides=_history_overrides_by_account(context.client or None, year_int),
        owned_companies=_load_owned_companies_for_client(context.client or None, year_int),
    )


def build_page_rl_mapping_issues(
    page: Any,
    *,
    use_filtered_hb: bool = False,
) -> list[RLMappingIssue]:
    """Bygg + berik RL-mapping-issues for en AnalysePage.

    Bruker ``context_from_page`` for å laste konteksten og
    ``enrich_rl_mapping_issues_with_suggestions`` for berikelse.
    """
    hb_df = (
        getattr(page, "_df_filtered", None)
        if use_filtered_hb
        else getattr(page, "dataset", None)
    )
    try:
        effective_sb = page._get_effective_sb_df()
    except Exception:
        effective_sb = getattr(page, "_rl_sb_df", None)
    try:
        include_ao = bool(page._include_ao_enabled())
    except Exception:
        include_ao = False

    context = context_from_page(page)

    issues = build_rl_mapping_issues(
        hb_df=hb_df if isinstance(hb_df, pd.DataFrame) else None,
        effective_sb_df=effective_sb if isinstance(effective_sb, pd.DataFrame) else None,
        context=context,
        include_ao=include_ao,
    )

    usage_features: dict[str, AccountUsageFeatures] = {}
    dataset = getattr(page, "dataset", None)
    if isinstance(dataset, pd.DataFrame) and not dataset.empty:
        try:
            usage_features = build_account_usage_features(dataset)
        except Exception:
            usage_features = {}

    year_int: int | None = None
    try:
        if context.year:
            year_int = int(str(context.year).strip())
    except Exception:
        year_int = None

    return enrich_rl_mapping_issues_with_suggestions(
        issues,
        regnskapslinjer=context.regnskapslinjer,
        usage_features=usage_features,
        historical_overrides=_history_overrides_by_account(context.client or None, year_int),
        rulebook_document=regnskapslinje_suggest.load_rulebook_document(),
        owned_companies=_load_owned_companies_for_client(context.client or None, year_int),
    )
