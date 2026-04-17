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
    # --- Resultat ---
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
}


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
) -> dict[int, float]:
    """Returner mapping fra regnr → normalisert BRREG-beløp.

    Evaluerer **alle** RL-rader (detalj + sum) via alias-matching, og
    propagerer deretter direkte BRREG-verdier oppover i det aktive
    hierarkiet via ``compute_sumlinjer``. Rader uten direkte match og
    uten sumformel blir utelatt (blanke i GUI).
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
    for _, row in regn.iterrows():
        label = _norm_label(row.get("regnskapslinje"))
        key = _direct_match(label)
        if not key:
            continue
        val = _resolve_brreg_value(key, brreg_data)
        if val is None:
            continue
        try:
            regnr = int(row["regnr"])
        except (TypeError, ValueError, KeyError):
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


def add_brreg_columns(
    pivot_df: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    brreg_data: Optional[dict],
) -> pd.DataFrame:
    """Legg til BRREG-sammenligning på en eksisterende RL-pivot.

    Legger til kolonnene ``BRREG``, ``Avvik_brreg``, ``Avvik_brreg_pct``.
    Når ``brreg_data`` er None eller ingen regnskapslinjer matcher, blir
    kolonnene lagt til som tomme (None).
    """
    result = pivot_df.copy() if pivot_df is not None else pd.DataFrame()

    if "regnr" not in result.columns:
        result["BRREG"] = None
        result["Avvik_brreg"] = None
        result["Avvik_brreg_pct"] = None
        return result

    brreg_by_regnr = build_brreg_by_regnr(regnskapslinjer, brreg_data or {})
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
