# -*- coding: utf-8 -*-
"""smart_mapping.py

Intelligent (best-effort) mappingforslag for Dataset-fanen.

Hensikt
-------
Bruker velger en hovedbok-/bilagsjournal-fil og programmet forsøker å
foreslå kolonnekart (mapping) automatisk.

Kilder til "intelligens":
1) Header-match (alias + tidligere læring fra .ml_map.json)
2) Innholdsheuristikk på et lite sample (typisk 10–50 rader)

Modulen er bevisst konservativ: vi fyller kun felter vi har rimelig
tillit til. Bruker kan alltid overstyre i GUI.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
import logging

import ml_map_utils

import smart_mapping_scoring as smc
import smart_mapping_stats as sms


logger = logging.getLogger(__name__)


def _suggest_from_headers(headers: List[str], *, ml: Optional[dict] = None) -> Dict[str, str]:
    """Foreslå mapping basert på header-navn og eventuell tidligere læring."""

    # 1) Alias/header-match
    base = ml_map_utils.suggest_mapping(headers) or {}

    # 2) Tidligere læring (ml_map.json) for samme/liknende headers
    try:
        if ml is None:
            ml = ml_map_utils.load_ml_map()
        learned = ml_map_utils.suggest_from_history(headers, ml)
        if learned:
            # learned vinner hvis den peker på en eksisterende kolonne
            for canon, src in learned.items():
                if src in headers:
                    base[canon] = src
    except Exception:
        # Ikke kritisk – bare best effort
        pass

    # Fjern evt. "unknown" / tomme
    return {k: v for k, v in base.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def _idx_by_name(stats: Sequence[sms.ColStats]) -> Dict[str, int]:
    return {c.name: c.idx for c in stats}


def _pick_best(
    stats: Sequence[sms.ColStats],
    used_cols: set[str],
    score_fn: Callable[[sms.ColStats], float],
    *,
    min_score: float,
    neighbor_idxs: Optional[Iterable[int]] = None,
    neighbor_bonus: float = 1.0,
    neighbor_max_dist: int = 2,
    require_neighbor: bool = False,
) -> Optional[str]:
    """Velg beste kolonne, med opsjonell nærhetsbonus."""

    n_idxs = list(neighbor_idxs or [])
    if require_neighbor and not n_idxs:
        return None

    best_name: Optional[str] = None
    best_score = float(min_score)

    for c in stats:
        if c.name in used_cols:
            continue
        s = float(score_fn(c))
        if n_idxs:
            s += sms.adjacency_bonus(c.idx, n_idxs, max_dist=neighbor_max_dist, bonus=neighbor_bonus)
        if s > best_score:
            best_score = s
            best_name = c.name

    return best_name


def suggest_mapping_intelligent(
    headers: Sequence[str],
    sample_rows: Optional[Sequence[Sequence[Any]]] = None,
    *,
    ml: Optional[dict] = None,
) -> Optional[Dict[str, str]]:
    """Returner et *best-effort* mappingforslag.

    Args:
        headers: Kolonnenavn slik de vises i filen (etter normalisering).
        sample_rows: Et lite utvalg rader (liste av lister) for innholdsanalyse.
        ml: Valgfritt pre-lest ml_map-objekt (for testing).

    Returns:
        dict {kanonisk_felt: kilde_kolonne} eller None hvis vi ikke finner
        nok signal til å i det minste mappe Konto/Bilag/Beløp.
    """

    headers_list = [str(h) for h in headers]
    if not headers_list:
        return None

    out: Dict[str, str] = _suggest_from_headers(headers_list, ml=ml)

    if not sample_rows:
        return out or None

    # Innholdsanalyse
    try:
        stats = sms.analyze_columns(headers_list, sample_rows)
    except Exception:
        logger.exception("Kunne ikke analysere sample for smart mapping")
        return out or None

    used = set(out.values())
    idx_map = _idx_by_name(stats)

    def add(field: str, name: Optional[str]) -> None:
        """Legg til mapping hvis feltet mangler.

        Viktig: vi skal ikke overstyre header-/historikk-gjett.
        """

        if field in out:
            return
        if not name:
            return
        out[field] = name
        used.add(name)

    # --- Prioritert rekkefølge (lav risiko) ---
    add("Konto", _pick_best(stats, used, smc.score_konto, min_score=1.70))
    add("Bilag", _pick_best(stats, used, smc.score_bilag, min_score=1.70))
    add("Beløp", _pick_best(stats, used, smc.score_money_amount, min_score=1.50))
    add("Dato", _pick_best(stats, used, smc.score_date, min_score=1.50))
    add("Tekst", _pick_best(stats, used, smc.score_text, min_score=1.20))
    # Kontonavn etter Tekst (for å unngå å stjele den eneste tekstkolonnen)
    add("Kontonavn", _pick_best(stats, used, smc.score_kontonavn, min_score=1.60))

    # Valuta/MVA krever ofte "kontekst" – vi foreslår kun hvis signalet er tydelig.
    add("Valuta", _pick_best(stats, used, smc.score_currency, min_score=1.50))
    add("MVA-prosent", _pick_best(stats, used, smc.score_mva_rate, min_score=2.00))

    # MVA-kode: best hvis den ligger nær MVA-prosent.
    mva_rate_idx = idx_map.get(out.get("MVA-prosent", ""))
    add(
        "MVA-kode",
        _pick_best(
            stats,
            used,
            smc.score_mva_code,
            min_score=2.10,
            neighbor_idxs=[mva_rate_idx] if mva_rate_idx is not None else None,
            neighbor_bonus=1.20,
            require_neighbor=True,
        ),
    )

    # Valutabeløp: kun hvis vi allerede har funnet Valuta.
    valuta_idx = idx_map.get(out.get("Valuta", ""))
    add(
        "Valutabeløp",
        _pick_best(
            stats,
            used,
            smc.score_money_amount,
            min_score=2.60,
            neighbor_idxs=[valuta_idx] if valuta_idx is not None else None,
            neighbor_bonus=1.40,
            require_neighbor=True,
        ),
    )

    # MVA-beløp: kun hvis vi har funnet MVA-kode eller MVA-prosent.
    mva_neighbor_idxs: List[int] = []
    for key in ("MVA-kode", "MVA-prosent"):
        ix = idx_map.get(out.get(key, ""))
        if ix is not None:
            mva_neighbor_idxs.append(ix)

    def _score_mva_amount(c: sms.ColStats) -> float:
        base = smc.score_money_amount(c)
        if base <= 0.0:
            return 0.0
        # MVA-beløp har ofte mange nuller
        base += float(c.zero_ratio) * 0.40
        return base

    add(
        "MVA-beløp",
        _pick_best(
            stats,
            used,
            _score_mva_amount,
            min_score=2.40,
            neighbor_idxs=mva_neighbor_idxs if mva_neighbor_idxs else None,
            neighbor_bonus=1.20,
            require_neighbor=True,
        ),
    )

    # Sikkerhetsnett: vi må i det minste ha Konto/Bilag/Beløp, ellers er forslaget ubrukelig.
    required = {"Konto", "Bilag", "Beløp"}
    if not required.issubset(out.keys()):
        return None

    return out
