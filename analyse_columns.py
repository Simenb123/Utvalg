"""analyse_columns.py

Hjelpere for kolonne-konfigurasjon i Analyse-fanen.

Mål:
- La bruker velge synlige kolonner + rekkefølge for transaksjonslisten.
- Sikre at enkelte kolonner alltid er synlige/tilgjengelige ("pinned"/"required")
  slik at nøkkelfunksjoner (f.eks. bilagsdrilldown) ikke brytes.

Denne modulen er bevisst *GUI-fri* for å være enkel å teste.
"""

from __future__ import annotations

from typing import Sequence


def _clean_col_name(x: object) -> str:
    """Returner trimmet kolonnenavn, eller "" for None/ugyldig."""
    if x is None:
        return ""
    try:
        s = str(x)
    except Exception:
        return ""
    return s.strip()


def unique_preserve(items: Sequence[object]) -> list[str]:
    """Fjern duplikater og tomme strenger – bevar første forekomst."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = _clean_col_name(it)
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def normalize_tx_column_config(
    order: Sequence[object] | None,
    visible: Sequence[object] | None,
    *,
    all_cols: Sequence[object] | None = None,
    pinned: Sequence[str] = ("Konto", "Kontonavn"),
    required: Sequence[str] = ("Konto", "Kontonavn", "Bilag"),
) -> tuple[list[str], list[str]]:
    """Normaliser kolonnevalg for transaksjonslisten.

    Regler:
    - Tomme/ugyldige navn fjernes.
    - Duplikater fjernes (første forekomst vinner).
    - Pinned-kolonner flyttes til starten av rekkefølgen.
    - Required-kolonner tvinges inn som synlige.
    - Hvis all_cols er gitt filtreres ukjente kolonner bort
      (men pinned/required beholdes).

    Returnerer:
      (order_clean, visible_order)

    Der:
      - order_clean: full rekkefølge (kan inneholde kolonner som ikke er synlige)
      - visible_order: synlige kolonner i ønsket rekkefølge
    """

    order_list = unique_preserve(order or [])
    visible_list = unique_preserve(visible or [])

    allowed: set[str] | None = None
    if all_cols is not None:
        allowed = set(unique_preserve(all_cols))

    def _is_allowed(c: str) -> bool:
        if allowed is None:
            return True
        return (c in allowed) or (c in pinned) or (c in required)

    order_list = [c for c in order_list if _is_allowed(c)]
    visible_list = [c for c in visible_list if _is_allowed(c)]

    # Hvis rekkefølge mangler: bruk all_cols eller visible som fallback
    if not order_list:
        if all_cols is not None:
            order_list = [c for c in unique_preserve(all_cols) if _is_allowed(c)]
        else:
            order_list = list(visible_list)

    # Pinned først
    rest = [c for c in order_list if c not in pinned]
    order_clean = unique_preserve([*pinned, *rest])

    # Ensure required exists in order list (for stabil visning)
    for r in required:
        if _is_allowed(r) and r not in order_clean:
            order_clean.append(r)

    # Synlige = visible + required + pinned
    visible_set = set(visible_list)
    for c in (*pinned, *required):
        if _is_allowed(c):
            visible_set.add(c)

    visible_order = [c for c in order_clean if c in visible_set]

    # Worst-case: hvis alt ble filtrert bort, fall tilbake til order_clean
    if not visible_order:
        visible_order = list(order_clean)

    return order_clean, visible_order
