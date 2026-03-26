"""analyse_columns.py

Hjelpere for kolonne-konfigurasjon i Analyse-fanen.

Maal:
- La bruker velge synlige kolonner og rekkefolge for transaksjonslisten.
- Samle like felter under ett visningsnavn, slik at kolonnevelgeren ikke
  viser dubletter som "Konto"/"konto" og "MVA-kode"/"mva-kode".
- Sikre at enkelte kolonner alltid er synlige/tilgjengelige ("pinned"/"required")
  slik at nokkelfunksjoner (f.eks. bilagsdrilldown) ikke brytes.

Denne modulen er bevisst GUI-fri for aa vaere enkel aa teste.
"""

from __future__ import annotations

import re
from typing import Sequence


def _clean_col_name(x: object) -> str:
    """Returner trimmet kolonnenavn, eller tom streng for ugyldige verdier."""
    if x is None:
        return ""
    try:
        s = str(x)
    except Exception:
        return ""
    return s.strip()


def _column_lookup_key(name: object) -> str:
    s = _clean_col_name(name).lower()
    if not s:
        return ""
    s = (
        s.replace("ø", "o")
        .replace("æ", "ae")
        .replace("å", "a")
    )
    return re.sub(r"[^a-z0-9]+", "", s)


_DISPLAY_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "Konto": ("Konto", "konto"),
    "Kontonavn": ("Kontonavn", "kontonavn"),
    "Dato": ("Dato", "dato"),
    "Bilag": ("Bilag", "bilag"),
    "Beløp": ("Beløp", "Belop", "beløp", "belop"),
    "Tekst": ("Tekst", "tekst"),
    "Kunder": ("Kunder", "kunder"),
    "Kundenr": ("Kundenr", "kundenr", "KundeNr", "kunde_nr", "Customer", "customer"),
    "Kundenavn": ("Kundenavn", "kundenavn", "CustomerName", "customername"),
    "Leverandørnr": ("Leverandørnr", "Leverandornr", "leverandørnr", "leverandornr"),
    "Leverandørnavn": ("Leverandørnavn", "Leverandornavn", "leverandørnavn", "leverandornavn"),
    "MVA-kode": ("MVA-kode", "MVA kode", "Mva", "mva", "mva-kode", "mva_kode"),
    "MVA-beløp": ("MVA-beløp", "MVA-belop", "mva-beløp", "mva-belop", "mva_belop"),
    "MVA-prosent": ("MVA-prosent", "mva-prosent", "mva_prosent"),
    "Valuta": ("Valuta", "valuta"),
    "Valutabeløp": ("Valutabeløp", "Valutabelop", "valutabeløp", "valutabelop"),
}

_DISPLAY_ALIAS_LOOKUP: dict[str, str] = {}
for _display_name, _aliases in _DISPLAY_ALIAS_GROUPS.items():
    for _alias in (_display_name, *_aliases):
        _DISPLAY_ALIAS_LOOKUP[_column_lookup_key(_alias)] = _display_name


def canonicalize_display_column_name(x: object) -> str:
    """Normaliser kjente kolonnenavn til en kanonisk visningsvariant."""
    s = _clean_col_name(x)
    if not s:
        return ""
    return _DISPLAY_ALIAS_LOOKUP.get(_column_lookup_key(s), s)


def candidate_source_columns(display_name: object) -> list[str]:
    """Returner sannsynlige kildesøyler for et visningsnavn."""
    canonical = canonicalize_display_column_name(display_name)
    if not canonical:
        return []
    aliases = _DISPLAY_ALIAS_GROUPS.get(canonical, ())
    return unique_preserve([canonical, *aliases])


def unique_preserve(items: Sequence[object], *, canonicalize: bool = False) -> list[str]:
    """Fjern duplikater og tomme strenger, og bevar første forekomst."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = canonicalize_display_column_name(it) if canonicalize else _clean_col_name(it)
        if not s:
            continue
        key = _column_lookup_key(s) if canonicalize else s
        if key in seen:
            continue
        seen.add(key)
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
    - Alias og duplikater fjernes (første forekomst vinner).
    - Pinned-kolonner flyttes til starten av rekkefølgen.
    - Required-kolonner tvinges inn som synlige.
    - Hvis ``all_cols`` er gitt filtreres ukjente kolonner bort
      (men pinned/required beholdes).

    Returnerer:
      ``(order_clean, visible_order)``
    """

    pinned_clean = tuple(unique_preserve(pinned, canonicalize=True))
    required_clean = tuple(unique_preserve(required, canonicalize=True))
    order_list = unique_preserve(order or [], canonicalize=True)
    visible_list = unique_preserve(visible or [], canonicalize=True)

    allowed: set[str] | None = None
    if all_cols is not None:
        allowed = set(unique_preserve(all_cols, canonicalize=True))

    def _is_allowed(c: str) -> bool:
        if allowed is None:
            return True
        return (c in allowed) or (c in pinned_clean) or (c in required_clean)

    order_list = [c for c in order_list if _is_allowed(c)]
    visible_list = [c for c in visible_list if _is_allowed(c)]

    if not order_list:
        if all_cols is not None:
            order_list = [c for c in unique_preserve(all_cols, canonicalize=True) if _is_allowed(c)]
        else:
            order_list = list(visible_list)

    rest = [c for c in order_list if c not in pinned_clean]
    order_clean = unique_preserve([*pinned_clean, *rest], canonicalize=True)

    for r in required_clean:
        if _is_allowed(r) and r not in order_clean:
            order_clean.append(r)

    visible_set = set(visible_list)
    for c in (*pinned_clean, *required_clean):
        if _is_allowed(c):
            visible_set.add(c)

    visible_order = [c for c in order_clean if c in visible_set]
    if not visible_order:
        visible_order = list(order_clean)

    return order_clean, visible_order
