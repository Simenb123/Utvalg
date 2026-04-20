"""BRREG-sammenligning for RL-pivot i Analyse-fanen.

Ren beregningsmodul — ingen GUI-avhengigheter.

Mapper BRREG-regnskap (fra ``brreg_client.fetch_regnskap``) til regnskaps-
linje-pivot. Sammenligningen evaluerer **hele aktive RL-oppsettet**, ikke
bare sumposter:

1. Normaliser aktivt RL-oppsett og matche etiketter mot et kanonisk
   BRREG-linjesett via aliaser.
2. Fyll direkte BRREG-verdier på linjer som matcher.
3. Kjør ``compute_sumlinjer`` over det aktive hierarkiet slik at
   sumlinjer i klientens oppsett får verdier propagert oppover.
4. Linjer som verken har direkte match eller kan summeres fra barn
   forblir blanke (None).

BRREG-tall er returnert som positive tall fra API-et. RL-griden bruker
norsk T-kontokonvensjon der inntekter, EK og gjeld er negative. Fortegnet
justeres derfor per kanonisk nøkkel slik at ``Avvik`` er direkte
sammenlignbart.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

import pandas as pd

log = logging.getLogger("app")


# ---------------------------------------------------------------------------
# Kanonisk BRREG-linjesett
# ---------------------------------------------------------------------------
# Hver nøkkel beskriver:
#   sign:     +1 = RL-fortegn er positivt (kostnader, eiendeler)
#             -1 = RL-fortegn er negativt (inntekter, EK, gjeld, resultat)
#   aliases:  normaliserte RL-navn (se _norm_label) som matcher denne nøkkelen
#   formula:  (valgfri) liste av andre kanoniske nøkler som summeres til
#             denne når direkte BRREG-verdi mangler
_BRREG_KEYS: dict[str, dict] = {
    # --- Resultat — aggregat ---
    "driftsinntekter": {
        "sign": -1,
        "aliases": [
            "driftsinntekter",
            "sum driftsinntekter",
            "sum salgs- og driftsinntekter",
        ],
    },
    "driftskostnader": {
        "sign": +1,
        "aliases": [
            "driftskostnader",
            "sum driftskostnader",
        ],
    },
    # --- Resultat — detaljposter ---
    "salgsinntekt": {
        "sign": -1,
        "aliases": [
            "salgsinntekt",
            "salgsinntekter",
            "driftsinntekt",
        ],
    },
    "annen_driftsinntekt": {
        "sign": -1,
        "aliases": [
            "annen driftsinntekt",
            "annen driftsinntekter",
            "andre driftsinntekter",
            "ovrig driftsinntekt",
        ],
    },
    "varekostnad": {
        "sign": +1,
        "aliases": [
            "varekostnad",
            "varekostnader",
            "kostnad solgte varer",
        ],
    },
    "loennskostnad": {
        "sign": +1,
        "aliases": [
            "lonnskostnad",
            "lonnskostnader",
            "personalkostnad",
            "personalkostnader",
        ],
    },
    "avskrivning": {
        "sign": +1,
        "aliases": [
            "avskrivning",
            "avskrivninger",
            "avskrivning pa varige driftsmidler og immaterielle eiendeler",
            "avskrivninger pa varige driftsmidler og immaterielle eiendeler",
        ],
    },
    "nedskrivning": {
        "sign": +1,
        "aliases": [
            "nedskrivning",
            "nedskrivninger",
            "nedskrivning av varige driftsmidler og immaterielle eiendeler",
        ],
    },
    "annen_driftskostnad": {
        "sign": +1,
        "aliases": [
            "annen driftskostnad",
            "annen driftskostnader",
            "andre driftskostnader",
            "ovrig driftskostnad",
        ],
    },
    "driftsresultat": {
        "sign": -1,
        "aliases": ["driftsresultat"],
    },
    "finansinntekter": {
        "sign": -1,
        "aliases": [
            "finansinntekter",
            "sum finansinntekter",
            "annen finansinntekt",
            "annen renteinntekt",
        ],
    },
    "finanskostnader": {
        "sign": +1,
        "aliases": [
            "finanskostnader",
            "sum finanskostnader",
            "annen finanskostnad",
            "annen rentekostnad",
        ],
    },
    "netto_finans": {
        "sign": -1,
        "aliases": [
            "netto finans",
            "netto finansposter",
            "resultat av finansposter",
            "sum finansposter",
        ],
    },
    "resultat_for_skatt": {
        "sign": -1,
        "aliases": [
            "resultat for skatt",
            "resultat for skattekostnad",
            "ordinart resultat for skattekostnad",
            "resultat for skattekostnad ordinart",
        ],
    },
    "aarsresultat": {
        "sign": -1,
        "aliases": ["arsresultat", "arets resultat"],
    },
    # --- Resultat — ekstra / skatt / total (optional fra oppstillingsplan) ---
    "skattekostnad": {
        "sign": +1,
        "aliases": [
            "skattekostnad",
            "skatt",
            "sum skattekostnad",
            "arets skattekostnad",
            "ordinart resultat skattekostnad",
            "skattekostnad pa ordinart resultat",
        ],
    },
    "ekstraordinaere_poster": {
        "sign": -1,
        "aliases": [
            "ekstraordinaere poster",
            "ekstraordinare poster",
            "sum ekstraordinaere poster",
            "ekstraordinart resultat",
        ],
    },
    "totalresultat": {
        "sign": -1,
        "aliases": ["totalresultat", "sum totalresultat"],
    },
    # --- Finanskostnad — detalj (optional) ---
    "rentekostnad_samme_konsern": {
        "sign": +1,
        "aliases": [
            "rentekostnad til foretak i samme konsern",
            "rentekostnader til foretak i samme konsern",
            "rentekostnad samme konsern",
            "rentekostnader konsern",
        ],
    },
    "annen_rentekostnad": {
        "sign": +1,
        "aliases": [
            "annen rentekostnad",
            "andre rentekostnader",
            "annen rente",
            "rentekostnader",
        ],
    },
    # --- Balanse — eiendeler ---
    "sum_anleggsmidler": {
        "sign": +1,
        "aliases": ["sum anleggsmidler", "anleggsmidler"],
    },
    "sum_omloepsmidler": {
        "sign": +1,
        "aliases": ["sum omlopsmidler", "omlopsmidler"],
    },
    "sum_eiendeler": {
        "sign": +1,
        "aliases": ["sum eiendeler", "eiendeler"],
    },
    # --- Balanse — EK ---
    "sum_innskutt_egenkapital": {
        "sign": -1,
        "aliases": [
            "sum innskutt egenkapital",
            "innskutt egenkapital",
        ],
    },
    "sum_opptjent_egenkapital": {
        "sign": -1,
        "aliases": [
            "sum opptjent egenkapital",
            "opptjent egenkapital",
            "annen egenkapital",
        ],
        "formula": ["sum_egenkapital", "-sum_innskutt_egenkapital"],
    },
    "sum_egenkapital": {
        "sign": -1,
        "aliases": ["sum egenkapital", "egenkapital"],
        "formula": ["sum_innskutt_egenkapital", "sum_opptjent_egenkapital"],
    },
    # --- Balanse — gjeld ---
    "langsiktig_gjeld": {
        "sign": -1,
        "aliases": [
            "sum langsiktig gjeld",
            "langsiktig gjeld",
        ],
    },
    "kortsiktig_gjeld": {
        "sign": -1,
        "aliases": [
            "sum kortsiktig gjeld",
            "kortsiktig gjeld",
        ],
    },
    "sum_gjeld": {
        "sign": -1,
        "aliases": ["sum gjeld"],
        "formula": ["langsiktig_gjeld", "kortsiktig_gjeld"],
    },
    "sum_egenkapital_og_gjeld": {
        "sign": -1,
        "aliases": [
            "sum egenkapital og gjeld",
            "sum ek og gjeld",
        ],
        "formula": ["sum_egenkapital", "sum_gjeld"],
    },
    # --- Balanse — detalj-poster (optional fra BRREG oppstillingsplan) ---
    "goodwill": {
        "sign": +1,
        "aliases": ["goodwill"],
    },
    "sum_varer": {
        "sign": +1,
        "aliases": [
            "sum varer",
            "varelager",
            "sum varelager",
            "varer",
            "lager",
        ],
    },
    "sum_fordringer": {
        "sign": +1,
        "aliases": [
            "sum fordringer",
            "fordringer",
        ],
    },
    "sum_investeringer": {
        "sign": +1,
        "aliases": [
            "sum investeringer",
            "investeringer",
            "kortsiktige investeringer",
            "sum kortsiktige investeringer",
        ],
    },
    "sum_bankinnskudd_og_kontanter": {
        "sign": +1,
        "aliases": [
            "sum bankinnskudd og kontanter",
            "bankinnskudd og kontanter",
            "bankinnskudd kontanter o l",
            "bankinnskudd kontanter og lignende",
            "bankinnskudd",
            "kontanter og bankinnskudd",
            "kontanter",
        ],
    },
}


# Tilgjengelighet i BRREG's åpne API (data.brreg.no/regnskapsregisteret/regnskap).
# - "sum": garantert populert når selskapet har levert årsregnskap
# - "detail": optional fra oppstillingsplan. Sjelden populert i gratis-API —
#   for de fleste AS er disse tomme selv ved oppstillingsplan "store".
#   Detalj-tall finnes i selskapets XBRL-innlevering (ikke offentlig REST).
_DETAIL_KEYS: frozenset[str] = frozenset({
    "salgsinntekt", "annen_driftsinntekt",
    "varekostnad", "loennskostnad",
    "avskrivning", "nedskrivning", "annen_driftskostnad",
    "skattekostnad", "ekstraordinaere_poster", "totalresultat",
    "rentekostnad_samme_konsern", "annen_rentekostnad",
    "goodwill", "sum_varer", "sum_fordringer",
    "sum_investeringer", "sum_bankinnskudd_og_kontanter",
})


def availability(key: str) -> str:
    """Returner "sum" eller "detail" for en BRREG-nøkkel."""
    return "detail" if key in _DETAIL_KEYS else "sum"


# Alias → kanonisk nøkkel (bygges én gang ved import)
_ALIAS_INDEX: dict[str, str] = {}
for _key, _spec in _BRREG_KEYS.items():
    for _alias in _spec.get("aliases", []):
        _ALIAS_INDEX[_alias] = _key


def _norm_label(s: object) -> str:
    """Normaliser RL-etikett for alias-matching.

    - fjern ``Σ`` / ``∑`` og leading/trailing whitespace
    - lowercase
    - fold norske tegn (æ→a, ø→o, å→a)
    - komprimer whitespace og fjern punktum/parenteser
    """
    if s is None:
        return ""
    text = str(s).replace("Σ", "").replace("∑", "").strip().lower()
    if not text:
        return ""
    # Fold norske diakritika deterministisk
    replacements = [
        ("æ", "a"),
        ("ø", "o"),
        ("å", "a"),
        ("ö", "o"),
        ("ä", "a"),
        ("é", "e"),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(".", " ").replace(",", " ")
    text = re.sub(r"[()\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _brreg_value(key: str, brreg_data: dict) -> Optional[float]:
    """Hent BRREG-verdi for kanonisk nøkkel, med formelfallback."""
    raw = brreg_data.get(key)
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass

    formula = _BRREG_KEYS.get(key, {}).get("formula")
    if not formula:
        return None

    total = 0.0
    got_any = False
    for term in formula:
        sign = -1.0 if term.startswith("-") else 1.0
        term_key = term.lstrip("-+")
        val = _brreg_value(term_key, brreg_data)
        if val is None:
            return None
        total += sign * val
        got_any = True
    return total if got_any else None


def _resolve_brreg_value(key: str, brreg_data: dict) -> Optional[float]:
    """Returner BRREG-verdi med RL-fortegn applisert."""
    val = _brreg_value(key, brreg_data)
    if val is None:
        return None
    sign = _BRREG_KEYS.get(key, {}).get("sign", +1)
    return val * sign


def _direct_match(label: str) -> Optional[str]:
    """Alias → kanonisk nøkkel for én normalisert etikett."""
    if not label:
        return None
    if label in _ALIAS_INDEX:
        return _ALIAS_INDEX[label]
    # Fjern "sum " / tall-prefiks og prøv igjen
    stripped = re.sub(r"^(sum|total)\s+", "", label).strip()
    if stripped and stripped in _ALIAS_INDEX:
        return _ALIAS_INDEX[stripped]
    return None


def build_brreg_by_regnr(
    regnskapslinjer: pd.DataFrame,
    brreg_data: dict,
    *,
    rl_mapping: Optional[dict[str, int]] = None,
) -> dict[int, float]:
    """Returner mapping fra regnr → normalisert BRREG-beløp.

    Evaluerer **alle** RL-rader (detalj + sum) via alias-matching, og
    propagerer deretter direkte BRREG-verdier oppover i det aktive
    hierarkiet via ``compute_sumlinjer``. Rader uten direkte match og
    uten sumformel blir utelatt (blanke i GUI).

    ``rl_mapping`` (valgfri): eksplisitt overstyring fra admin-GUI, på
    formen ``{brreg_key: regnr}``. Vinner over alias-matching. Hvis
    ``None`` brukes ingen overstyring (anropere som vil laste fra
    konfig, må gjøre det selv før kallet).
    """
    if regnskapslinjer is None or regnskapslinjer.empty or not isinstance(brreg_data, dict):
        return {}

    try:
        from regnskap_mapping import (
            normalize_regnskapslinjer,
            compute_sumlinjer,
            expand_regnskapslinje_selection,
        )
        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception as exc:
        log.warning("build_brreg_by_regnr: normalize_regnskapslinjer feilet: %s", exc)
        return {}

    direct: dict[int, float] = {}
    overridden_regnrs: set[int] = set()
    mapped_brreg_keys: set[str] = set()

    # Eksplisitt GUI-mapping vinner: fyll disse først og ikke la alias
    # overskrive dem.
    for brreg_key, regnr in (rl_mapping or {}).items():
        if not isinstance(brreg_key, str) or brreg_key not in _BRREG_KEYS:
            continue
        try:
            regnr_int = int(regnr)
        except (TypeError, ValueError):
            continue
        # BRREG-nøkkelen er "brukt opp" av mapping selv om verdien mangler
        # i brreg_data — vi vil ikke la alias omplassere den.
        mapped_brreg_keys.add(brreg_key)
        val = _resolve_brreg_value(brreg_key, brreg_data)
        if val is None:
            # Detalj-nøkler leveres sjelden av BRREG's åpne API — gjør det
            # sporbart hvorfor en mappet linje er blank i Analyse.
            log.debug(
                "BRREG-mapping %s→regnr %d: verdi mangler i API-svar "
                "(%s-nivå, ikke rapportert av selskapet)",
                brreg_key, regnr_int, availability(brreg_key),
            )
            continue
        direct[regnr_int] = val
        overridden_regnrs.add(regnr_int)

    # Alias-matching (fall-back) — overskriver ikke rader som mapping
    # allerede har dekket, og ignorerer BRREG-nøkler som er brukt av
    # mapping (så én BRREG-verdi ikke dukker opp to steder).
    for _, row in regn.iterrows():
        try:
            regnr = int(row["regnr"])
        except (TypeError, ValueError, KeyError):
            continue
        if regnr in overridden_regnrs:
            continue
        label = _norm_label(row.get("regnskapslinje"))
        key = _direct_match(label)
        if not key or key in mapped_brreg_keys:
            continue
        val = _resolve_brreg_value(key, brreg_data)
        if val is None:
            continue
        direct[regnr] = val

    if not direct:
        return {}

    # Propager via aktivt RL-hierarki: direkte-matchede verdier fungerer
    # som "leaf"-verdier, compute_sumlinjer fyller inn sumlinjer der alle
    # underliggende leaf-linjer har direkte match.
    try:
        propagated = compute_sumlinjer(base_values=dict(direct), regnskapslinjer=regn)
    except Exception as exc:
        log.warning("build_brreg_by_regnr: compute_sumlinjer feilet: %s", exc)
        propagated = dict(direct)

    # Behold kun propagerte sumposter der alle underliggende leaves er
    # dekket av direkte matcher — ellers er "verdien" bare en 0.0-fallback
    # fra compute_sumlinjer og skal ikke vises.
    out = dict(direct)
    sum_regnr = [
        int(r)
        for r in regn.loc[regn["sumpost"].astype(bool), "regnr"].tolist()
    ]
    for sreg in sum_regnr:
        if sreg in out:
            continue
        if sreg not in propagated:
            continue
        try:
            leaves = expand_regnskapslinje_selection(
                regnskapslinjer=regn, selected_regnr=[sreg]
            )
        except Exception:
            continue
        leaves = [int(x) for x in leaves if x is not None]
        if not leaves:
            continue
        if not all(leaf in direct for leaf in leaves):
            continue
        out[sreg] = float(propagated[sreg])
    return out


def _select_year_payload(brreg_data: Optional[dict], year: Optional[int]) -> dict:
    """Velg riktig års-dict fra brreg_data.

    - Uten `year`: eksisterende oppførsel (toppnivå = nyeste år).
    - Med `year`: bruk `brreg_data["years"][year]` hvis tilgjengelig.

    Returnerer tom dict når ingen data matcher, slik at anropssiden kan
    forenkle fallback-logikk.
    """
    if not isinstance(brreg_data, dict):
        return {}
    if year is None:
        return brreg_data
    years = brreg_data.get("years")
    if isinstance(years, dict):
        year_data = years.get(year) or years.get(str(year))
        if isinstance(year_data, dict):
            return year_data
    return {}


_UNSET: Any = object()


def add_brreg_columns(
    pivot_df: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    brreg_data: Optional[dict],
    *,
    year: Optional[int] = None,
    rl_mapping: Any = _UNSET,
) -> pd.DataFrame:
    """Legg til BRREG-sammenligning på en eksisterende RL-pivot.

    Legger til kolonnene ``BRREG``, ``Avvik_brreg``, ``Avvik_brreg_pct``.
    Når ``brreg_data`` er None eller ingen regnskapslinjer matcher, blir
    kolonnene lagt til som tomme (None).

    ``year`` (valgfri): plukker et spesifikt år fra `brreg_data["years"]`.
    Uten år brukes toppnivået (nyeste — bakoverkompatibelt).

    ``rl_mapping`` (valgfri): eksplisitt ``{brreg_key: regnr}``-mapping.
    Hvis ikke angitt, lastes brukerens mapping via
    ``brreg_mapping_config.load_brreg_rl_mapping()``. Send ``{}`` for å
    eksplisitt deaktivere.
    """
    result = pivot_df.copy() if pivot_df is not None else pd.DataFrame()

    if "regnr" not in result.columns:
        result["BRREG"] = None
        result["Avvik_brreg"] = None
        result["Avvik_brreg_pct"] = None
        return result

    if rl_mapping is _UNSET:
        try:
            import brreg_mapping_config
            rl_mapping = brreg_mapping_config.load_brreg_rl_mapping()
        except Exception as exc:
            log.debug("brreg_mapping_config ikke tilgjengelig: %s", exc)
            rl_mapping = {}

    payload = _select_year_payload(brreg_data, year)
    brreg_by_regnr = build_brreg_by_regnr(
        regnskapslinjer, payload, rl_mapping=rl_mapping or None,
    )
    if not brreg_by_regnr:
        result["BRREG"] = None
        result["Avvik_brreg"] = None
        result["Avvik_brreg_pct"] = None
        return result

    try:
        regnr_int = result["regnr"].astype(int)
    except Exception:
        regnr_int = pd.Series([None] * len(result), index=result.index)

    result["BRREG"] = regnr_int.map(
        lambda r: brreg_by_regnr.get(int(r)) if pd.notna(r) else None
    )

    ub = pd.to_numeric(result.get("UB"), errors="coerce")
    brreg_num = pd.to_numeric(result["BRREG"], errors="coerce")
    result["Avvik_brreg"] = ub - brreg_num
    mask_nan = result["BRREG"].isna()
    result.loc[mask_nan, "Avvik_brreg"] = None

    def _pct(ub_val: float, br_val: float) -> Optional[float]:
        if br_val is None or pd.isna(br_val):
            return None
        if abs(br_val) < 0.01:
            return None
        if ub_val is None or pd.isna(ub_val):
            return None
        return (ub_val - br_val) / abs(br_val) * 100.0

    result["Avvik_brreg_pct"] = [
        _pct(
            ub.iloc[i] if i < len(ub) else None,
            brreg_num.iloc[i] if i < len(brreg_num) else None,
        )
        for i in range(len(result))
    ]
    return result
