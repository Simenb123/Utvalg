# -*- coding: utf-8 -*-
"""smart_mapping_scoring.py

Score-funksjoner (heuristikk) for :mod:`smart_mapping`.

Dette er en intern modul. Den er separert fra `smart_mapping_stats.py` for å
holde filene mindre og mer oversiktlige.
"""

from __future__ import annotations

from typing import Optional

from smart_mapping_stats import ColStats


def score_konto(c: ColStats) -> float:
    if c.non_empty < 3:
        return 0.0
    if c.numeric_ratio < 0.60 or c.int_ratio < 0.60:
        return 0.0
    if c.median_digits is None:
        return 0.0

    # Konto er ofte 4 siffer. Score etter avstand til 4.
    digit_score = max(0.0, 1.0 - (abs(c.median_digits - 4.0) / 4.0))
    repetition_bonus = max(0.0, 1.0 - c.unique_ratio) * 0.20
    return c.int_ratio * 2.0 + digit_score + repetition_bonus


def score_bilag(c: ColStats) -> float:
    if c.non_empty < 3:
        return 0.0
    if c.numeric_ratio < 0.60 or c.int_ratio < 0.60:
        return 0.0
    if c.median_digits is None:
        return 0.0
    if c.median_digits < 5:
        return 0.0

    digit_score = min(1.0, (c.median_digits - 4.0) / 6.0)
    return c.int_ratio * 2.0 + digit_score + c.unique_ratio * 0.50


def score_money_amount(c: ColStats) -> float:
    """Score for beløpskolonner (penger).

    Denne er mer konservativ enn en ren "numeric"-test for å unngå
    at koder (f.eks. MVA-kode) feiltolkes som beløp.
    """

    if c.non_empty < 3:
        return 0.0
    if c.numeric_ratio < 0.70:
        return 0.0
    if c.date_ratio > 0.35:
        return 0.0

    score = c.numeric_ratio * 2.0
    score += c.negative_ratio * 0.60
    score += max(c.float_ratio, c.decimal_ratio) * 0.60

    # Straff veldig "id-lik" kolonner: nesten bare heltall, høy unikhet.
    if c.int_ratio > 0.90 and c.negative_ratio == 0.0 and max(c.float_ratio, c.decimal_ratio) == 0.0:
        if c.median_digits and c.median_digits >= 5 and c.unique_ratio > 0.80:
            score -= 0.80

    # Straff små kode-kolonner (f.eks. MVA-kode/avdeling/segment)
    if c.int_ratio > 0.90 and max(c.float_ratio, c.decimal_ratio) == 0.0:
        if (c.median_digits is not None and c.median_digits <= 2.5) and c.between_0_100_ratio > 0.85:
            score -= 0.90

    return max(0.0, score)


def score_date(c: ColStats) -> float:
    if c.non_empty < 3:
        return 0.0
    if c.date_ratio < 0.60:
        return 0.0
    return c.date_ratio * 3.0


def score_text(c: ColStats) -> float:
    if c.non_empty < 3:
        return 0.0
    if c.text_ratio < 0.50:
        return 0.0
    len_bonus = min(1.0, c.avg_len / 30.0)
    return c.text_ratio * 2.0 + len_bonus


def score_kontonavn(c: ColStats) -> float:
    """Score for kontonavn/kontobeskrivelse.

    Kjennetegn (typisk):
    - tekstlig (bokstaver)
    - ofte repetert (lavere unique_ratio) sammenlignet med Tekst
    - moderat lengde
    """

    if c.non_empty < 3:
        return 0.0
    if c.text_ratio < 0.50:
        return 0.0

    # Hvis mye numerisk/dato: sannsynligvis ikke et navn
    if c.numeric_ratio > 0.40:
        return 0.0
    if c.date_ratio > 0.35:
        return 0.0

    repetition = max(0.0, 1.0 - c.unique_ratio)
    # Preferer ca 10–30 tegn
    target_len = 18.0
    len_score = max(0.0, 1.0 - (abs(c.avg_len - target_len) / 35.0))
    # Lange tekstfelt (posteringstekst) har ofte høy unikhet.
    score = c.text_ratio * 1.2 + repetition * 1.8 + len_score
    return max(0.0, score)


def score_currency(c: ColStats) -> float:
    if c.non_empty < 3:
        return 0.0
    if c.currency_ratio < 0.60:
        return 0.0
    return c.currency_ratio * 3.0


def score_mva_rate(c: ColStats) -> float:
    """Score for MVA-prosent (mva-sats).

    Vi er bevisst konservative for å unngå at dimensjoner som
    *avdeling/prosjekt/segment* feiltolkes som MVA-sats.

    Typiske satser i Norge er 25 %, 15 % og 12 % (evt. 0 %), og enkelte
    systemer lagrer satsen som brøk (0.25) i stedet for prosent (25).
    """

    if c.non_empty < 3:
        return 0.0
    if c.numeric_ratio < 0.70:
        return 0.0
    if c.between_0_100_ratio < 0.80:
        return 0.0
    if c.max_abs is None:
        return 0.0

    name = (c.name or "").strip().lower()

    # Avvis typiske dimensjonskolonner hvis headernavnet tyder på det.
    # Hvis header faktisk inneholder mva/vat/tax, lar vi tallverdiene avgjøre.
    if name and ("mva" not in name and "vat" not in name and "tax" not in name):
        for bad in ("avdeling", "prosjekt", "segment", "koststed", "kostnadssted", "ansvar", "produsent"):
            if bad in name:
                return 0.0

    max_abs = float(c.max_abs)

    # Typiske MVA-satser (Norge) – både som prosent og som brøk.
    typical_percent = (25.0, 15.0, 12.0, 10.0, 8.0, 6.0, 5.0)
    typical_fraction = (0.25, 0.15, 0.12, 0.10, 0.08, 0.06, 0.05)

    def _close(val: float, targets: tuple[float, ...], tol: float) -> bool:
        return any(abs(val - t) <= tol for t in targets)

    if max_abs <= 1.5:
        # Brøk (0.25 osv). 1.0 er sjelden en reell MVA-sats i hovedbok.
        if not _close(max_abs, typical_fraction, tol=0.02):
            return 0.0
    else:
        # Prosent (25 osv). Vi begrenser oss til "sannsynlige" satser.
        if max_abs < 5.0 or max_abs > 35.0:
            return 0.0
        if not _close(max_abs, typical_percent, tol=0.75):
            return 0.0

    uniq_bonus = max(0.0, 1.0 - c.unique_ratio) * 0.50
    score = c.numeric_ratio * 2.0 + c.between_0_100_ratio + uniq_bonus

    # Liten boost hvis header faktisk nevner mva/vat/tax.
    if "mva" in name or "vat" in name or "tax" in name:
        score += 0.50

    return score

def score_mva_code(c: ColStats) -> float:
    """Score for MVA-kode.

    MVA-koder er ofte små heltall (0..25), få ulike verdier og høy numerisk ratio.
    """

    if c.non_empty < 3:
        return 0.0
    if c.numeric_ratio < 0.80 or c.int_ratio < 0.75:
        return 0.0
    if c.between_0_100_ratio < 0.90:
        return 0.0

    # Typisk 1–2 siffer
    if c.median_digits is None:
        return 0.0
    if c.median_digits > 2.5:
        return 0.0

    uniq_bonus = max(0.0, 1.0 - c.unique_ratio) * 0.90
    return c.int_ratio * 1.6 + c.between_0_100_ratio * 0.6 + uniq_bonus
