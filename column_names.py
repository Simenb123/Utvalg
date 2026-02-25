"""column_names.py

Felles hjelpere for kolonnenavn i Utvalg.

Problem
-------
I praksis forekommer det ofte at enkelte kolonner mangler header (tom celle),
spesielt i Excel/CSV-eksporter. Både UI (mapping-rullgardiner) og
dataset_build_fast må likevel kunne referere til kolonnen på en stabil måte.

Løsning
--------
Vi normaliserer kolonnenavn slik:

* Tom/None/"Unnamed: x" => "kolX" (1-indeksert, slik forhåndsvisning viser)
* Doble navn dedupliseres med suffiks " (2)", " (3)", ...

Dette gjør at:
  - brukeren kan mappe også blanke kolonner
  - mapping kan lagres/gjenbrukes
  - byggekoden kan bruke `usecols` robust uten å knekke når header er tom.
"""

from __future__ import annotations

from typing import Any, Iterable, List

import re


_PANDAS_UNNAMED_RE = re.compile(r"^Unnamed:\s*\d+(?:_level_\d+)?$", re.IGNORECASE)


def _is_blank_like(s: str) -> bool:
    s2 = (s or "").strip().lower()
    return s2 in {"", "nan", "nat", "none", "null"}


def _clean_name(raw: Any, idx_1based: int, *, placeholder_prefix: str) -> str:
    if raw is None:
        s = ""
    else:
        try:
            s = str(raw)
        except Exception:
            s = ""

    # normaliser NBSP og whitespace
    s = s.replace("\u00a0", " ").strip()

    if _is_blank_like(s) or _PANDAS_UNNAMED_RE.match(s):
        return f"{placeholder_prefix}{idx_1based}"

    return s


def make_safe_unique_column_names(
    raw_names: Iterable[Any],
    *,
    placeholder_prefix: str = "kol",
) -> List[str]:
    """Lag stabile, unike kolonnenavn.

    Parametre
    ---------
    raw_names:
        Opprinnelige kolonnenavn (fra Excel/CSV/pandas/openpyxl).
    placeholder_prefix:
        Prefiks for genererte navn ved tom header. Default "kol" gir
        "kol1", "kol2", ...
    """

    cleaned: List[str] = [
        _clean_name(v, i, placeholder_prefix=placeholder_prefix)
        for i, v in enumerate(list(raw_names), start=1)
    ]

    used: set[str] = set()
    out: List[str] = []
    for name in cleaned:
        candidate = name
        if candidate in used:
            n = 2
            while True:
                cand2 = f"{name} ({n})"
                if cand2 not in used:
                    candidate = cand2
                    break
                n += 1
        used.add(candidate)
        out.append(candidate)

    return out


def is_generated_placeholder(name: str, *, placeholder_prefix: str = "kol") -> bool:
    """True hvis `name` ser ut som en generert kolonneplassholder (kolX)."""

    s = (name or "").strip().lower()
    if not s.startswith(placeholder_prefix.lower()):
        return False
    tail = s[len(placeholder_prefix) :]
    return tail.isdigit() and int(tail) > 0
