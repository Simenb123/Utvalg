"""Match CRM audit actions to regnskapslinjer (financial statement lines).

Matching strategy (in priority order):
1. Numeric prefix: action "010 Detaljkontroll..." → regnr 10
2. Known aliases: "ADK" → regnr 70, "Varelager" → regnr 605
3. Fuzzy name match: "Salgsinntekter" ≈ "Salgsinntekt" (regnr 10)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Sequence

from crmsystem_actions import AuditAction


@dataclass
class RegnskapslinjeInfo:
    nr: str = ""               # e.g. "10", "605"
    regnskapslinje: str = ""   # e.g. "Salgsinntekt"


@dataclass
class ActionMatch:
    action: AuditAction
    regnr: str = ""            # matched regnskapslinje nr
    regnskapslinje: str = ""   # matched regnskapslinje name
    match_method: str = ""     # "prefix" | "alias" | "fuzzy" | ""
    confidence: float = 0.0    # 0.0-1.0


# ---------------------------------------------------------------------------
# Known aliases — maps keywords in action names to regnr
# ---------------------------------------------------------------------------

_ALIAS_MAP: dict[str, str] = {
    "adk": "70",
    "andre driftskostnader": "70",
    "annen driftskostnad": "70",
    "driftskostnader": "70",
    "varelager": "605",
    "varekostnad": "20",
    "varekjøp": "20",
    "salgsinntekt": "10",
    "salgsinntekter": "10",
    "kundefordring": "610",
    "kundefordringer": "610",
    "leverandørgjeld": "780",
    "bank": "655",
    "likvider": "655",
    "bankinnskudd": "655",
    "lønn": "40",
    "lønnskostnad": "40",
    "utlønning": "40",
    "lønnsanalyse": "40",
    "feriepenger": "40",
    "egenkapital": "715",
    "aksjekapital": "670",
    "pensjon": "720",
    "pensjonsmidler": "720",
    "pensjonsforpliktelser": "720",
    "skatt": "785",
    "skattetrekk": "785",
    "mva": "790",
    "merverdiavgift": "790",
    "avskrivning": "50",
    "driftsmidler": "550",
    "aksjer": "585",
    "obligasjoner": "590",
    "renteinntekt": "110",
    "rentekostnad": "145",
    "finansinntekt": "115",
    "finanskostnad": "150",
    "nedskrivning": "60",
    "goodwill": "525",
    "periodisering": "",  # too generic, skip
}

# Regex to find a numeric prefix like "010", "605", "70" at start of procedure name
_RE_NUMERIC_PREFIX = re.compile(r"^0*(\d{2,3})\b")

# Regex to find a 3-digit number anywhere that looks like a regnr
_RE_REGNR_ANYWHERE = re.compile(r"\b0*(\d{2,3})\b")


def _normalize(text: str) -> str:
    """Lowercase, strip, remove common noise."""
    return text.lower().strip()


def _extract_prefix_regnr(procedure_name: str) -> str | None:
    """Try to extract a regnr from the start of a procedure name like '010 Salg...'."""
    m = _RE_NUMERIC_PREFIX.match(procedure_name.strip())
    if m:
        return m.group(1).lstrip("0") or "0"
    return None


def match_actions_to_regnskapslinjer(
    actions: Sequence[AuditAction],
    regnskapslinjer: Sequence[RegnskapslinjeInfo],
    *,
    min_fuzzy_score: float = 0.55,
) -> list[ActionMatch]:
    """Match each action to its best regnskapslinje.

    Returns one ActionMatch per action. Unmatched actions have empty regnr.
    """
    # Build lookup structures
    regnr_set = {rl.nr for rl in regnskapslinjer}
    regnr_by_name: dict[str, RegnskapslinjeInfo] = {}
    for rl in regnskapslinjer:
        regnr_by_name[_normalize(rl.regnskapslinje)] = rl

    # Normalized names for fuzzy matching
    rl_names = [_normalize(rl.regnskapslinje) for rl in regnskapslinjer]

    results: list[ActionMatch] = []

    for action in actions:
        match = ActionMatch(action=action)
        proc = action.procedure_name

        # 1. Try numeric prefix
        prefix_nr = _extract_prefix_regnr(proc)
        if prefix_nr and prefix_nr in regnr_set:
            rl = next((r for r in regnskapslinjer if r.nr == prefix_nr), None)
            if rl:
                match.regnr = rl.nr
                match.regnskapslinje = rl.regnskapslinje
                match.match_method = "prefix"
                match.confidence = 1.0
                results.append(match)
                continue

        # 2. Try known aliases — procedure name has priority over area name
        proc_lower = _normalize(proc)
        area_lower = _normalize(action.area_name)

        # Search procedure name first; only fall back to area name if no hit
        for source in [proc_lower, area_lower]:
            best_alias_len = 0
            for alias, nr in _ALIAS_MAP.items():
                if not nr or nr not in regnr_set:
                    continue
                if alias in source and len(alias) > best_alias_len:
                    rl = next((r for r in regnskapslinjer if r.nr == nr), None)
                    if rl:
                        best_alias_len = len(alias)
                        match.regnr = rl.nr
                        match.regnskapslinje = rl.regnskapslinje
                        match.match_method = "alias"
                        match.confidence = 0.85
            if match.regnr:
                break  # procedure match wins, don't check area

        if match.regnr:
            results.append(match)
            continue

        # 3. Try fuzzy name matching against regnskapslinje names
        # Use both procedure name and area name as candidates
        search_terms = [proc_lower, area_lower]
        best_score = 0.0
        best_rl: RegnskapslinjeInfo | None = None

        for term in search_terms:
            if not term:
                continue
            # Clean the term — remove numeric prefixes and common words
            clean = re.sub(r"^\d{2,3}\s+", "", term)
            clean = re.sub(r"\b(detaljkontroll|kontroll|test av|analyse|avsetning|periodisering|tett nr|endelig)\b", "", clean)
            clean = clean.strip(" -/")
            if len(clean) < 3:
                continue

            matches = difflib.get_close_matches(clean, rl_names, n=1, cutoff=min_fuzzy_score)
            if matches:
                score = difflib.SequenceMatcher(None, clean, matches[0]).ratio()
                if score > best_score:
                    best_score = score
                    best_rl = regnr_by_name.get(matches[0])

        if best_rl and best_score >= min_fuzzy_score:
            match.regnr = best_rl.nr
            match.regnskapslinje = best_rl.regnskapslinje
            match.match_method = "fuzzy"
            match.confidence = round(best_score, 2)

        results.append(match)

    return results


def group_by_regnskapslinje(
    matches: Sequence[ActionMatch],
) -> dict[str, list[ActionMatch]]:
    """Group matched actions by regnr. Key "" = unmatched."""
    groups: dict[str, list[ActionMatch]] = {}
    for m in matches:
        key = m.regnr or ""
        groups.setdefault(key, []).append(m)
    return groups
