"""
header_detection.py

Ren logikk for å gjette hvilken rad som er header (kolonnenavn) i en
importert hovedboksfil.

Bruk:
    from header_detection import detect_header_row

    header_row_idx = detect_header_row(rows)
    # rows er en liste av rader, der hver rad er en liste av celleverdier.

Design-prinsipp:
- Vi ser typisk på de første 10–20 radene.
- En header-rad har:
    * Mange ikke-tomme celler
    * Mye tekst / "etiketter"
    * Lite rene tall
- Vi velger raden med høyest "header-score".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Union


Cell = Union[str, int, float, None]


@dataclass
class HeaderCandidate:
    row_index: int
    non_empty: int
    text_cells: int
    numeric_cells: int
    score: float


def _is_empty(value: Cell) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and (value != value):  # NaN
        return True
    text = str(value).strip()
    return text == ""


def _is_numeric(value: Cell) -> bool:
    if value is None:
        return False
    text = str(value).strip().replace(" ", "").replace("\xa0", "")
    if not text:
        return False
    # Tillat tusenskiller og komma som desimal
    text = text.replace(".", "").replace(",", ".")
    try:
        float(text)
        return True
    except ValueError:
        return False


def _score_row(row_index: int, row: Sequence[Cell]) -> HeaderCandidate:
    non_empty = 0
    text_cells = 0
    numeric_cells = 0

    for cell in row:
        if _is_empty(cell):
            continue
        non_empty += 1
        if _is_numeric(cell):
            numeric_cells += 1
        else:
            text_cells += 1

    # Enkel heuristikk:
    # - Vi liker mange ikke-tomme celler
    # - Vi liker at det er mer tekst enn tall (etiketter)
    # - Vi straffer rader som nesten bare er tall
    if non_empty == 0:
        score = 0.0
    else:
        text_ratio = text_cells / max(non_empty, 1)
        numeric_ratio = numeric_cells / max(non_empty, 1)
        score = (
            non_empty
            + text_cells * 2.0
            + text_ratio * 5.0
            - numeric_ratio * 2.0
        )

    return HeaderCandidate(
        row_index=row_index,
        non_empty=non_empty,
        text_cells=text_cells,
        numeric_cells=numeric_cells,
        score=score,
    )


def detect_header_row(
    rows: Sequence[Sequence[Cell]],
    max_lookahead: int = 20,
    min_non_empty: int = 2,
) -> Optional[int]:
    """
    Gjetter hvilken rad som er header.

    Parametre:
        rows:
            En sekvens av rader (som lister/tupler av celleverdier).
        max_lookahead:
            Hvor mange rader vi maks vurderer fra toppen.
        min_non_empty:
            Minimum antall ikke-tomme celler for at en rad skal
            vurderes som seriøs kandidat.

    Returnerer:
        Indeks (0-basert) på den raden som antas å være header,
        eller None hvis vi ikke finner noe fornuftig.

    Viktig:
        Denne funksjonen KASTER ALDRI – worst case returnerer den None,
        slik at kallende kode kan falle tilbake til rad 0 som header.
    """
    if not rows:
        return None

    candidates: List[HeaderCandidate] = []

    limit = min(len(rows), max_lookahead)
    for i in range(limit):
        row = rows[i]
        candidate = _score_row(i, row)
        if candidate.non_empty >= min_non_empty:
            candidates.append(candidate)

    if not candidates:
        return None

    # Velg raden med høyest score
    best = max(candidates, key=lambda c: c.score)

    # Hvis den beste raden har veldig lav score, kan vi returnere None
    # for å signalisere at vi er usikre.
    if best.score <= 0:
        return None

    return best.row_index
