"""brreg_mapping_config.py — persistens for BRREG-linje → regnr-mapping.

Brukeren mapper BRREG-kanoniske linjer (f.eks. ``salgsinntekt``) til egne
regnr (f.eks. 10). Mapping persisteres som JSON og brukes av
``brreg_rl_comparison`` som en eksplisitt overstyring av alias-matching.

Lagringsformat:

    {
      "version": 1,
      "mappings": {
        "salgsinntekt": 10,
        "sum_eiendeler": 665,
        "finansinntekter": null
      }
    }

``null`` betyr "deaktiver alias-fallback for denne BRREG-nøkkelen" — nyttig
når RL-strukturen ikke har en naturlig målrad og vi ikke vil at alias skal
plassere verdien et semantisk feil sted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import classification_config


_FILENAME = "brreg_rl_mapping.json"
_SCHEMA_VERSION = 1


def resolve_brreg_mapping_path() -> Path:
    """Returnerer stien til JSON-filen som holder mappingen."""
    return classification_config.repo_dir() / _FILENAME


def _coerce_mapping(raw: Any) -> dict[str, int | None]:
    """Valider og normaliser lagrede mappinger. ``None`` = deaktivert alias."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int | None] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if value is None:
            out[key.strip()] = None
            continue
        try:
            regnr = int(value)
        except (TypeError, ValueError):
            continue
        out[key.strip()] = regnr
    return out


def load_brreg_rl_mapping() -> dict[str, int | None]:
    """Les mapping fra JSON. Returnerer tom dict hvis fil mangler/er korrupt."""
    document = classification_config.load_json(
        resolve_brreg_mapping_path(), fallback={}
    )
    if not isinstance(document, dict):
        return {}
    return _coerce_mapping(document.get("mappings"))


def save_brreg_rl_mapping(mapping: dict[str, int | None]) -> Path:
    """Skriv mapping til JSON. Returnerer lagringsstien."""
    cleaned = _coerce_mapping(mapping)
    document = {"version": _SCHEMA_VERSION, "mappings": cleaned}
    return classification_config.save_json(
        resolve_brreg_mapping_path(), document
    )


def suggest_mapping_from_aliases(
    regnskapslinjer: Any,
) -> dict[str, int]:
    """Foreslår ``{brreg_key: regnr}`` basert på alias-matching mot RL-df.

    Brukes i admin-GUI for å pre-fylle mapping-tabellen slik at brukeren ser
    hvilke BRREG-linjer som allerede ville truffet via alias (uten mapping).
    Første alias-treff vinner; duplikate BRREG-nøkler ignoreres.
    """
    import brreg_rl_comparison as _brc

    try:
        import pandas as _pd
    except Exception:
        return {}
    if not isinstance(regnskapslinjer, _pd.DataFrame) or regnskapslinjer.empty:
        return {}

    cols = {str(c).strip().lower(): c for c in regnskapslinjer.columns}
    nr_col = cols.get("regnr") or cols.get("nr")
    navn_col = cols.get("regnskapslinje") or cols.get("navn")
    if not nr_col or not navn_col:
        return {}

    suggestions: dict[str, int] = {}
    for _, row in regnskapslinjer.iterrows():
        try:
            regnr = int(row[nr_col])
        except (TypeError, ValueError, KeyError):
            continue
        label = _brc._norm_label(row.get(navn_col))
        key = _brc._direct_match(label)
        if not key or key in suggestions:
            continue
        suggestions[key] = regnr
    return suggestions


def list_brreg_keys() -> list[tuple[str, str]]:
    """Returnerer ``[(brreg_key, human_label), ...]`` for alle kjente nøkler.

    ``human_label`` er første alias for nøkkelen (første bokstav stor) — ment
    som en lesbar beskrivelse i admin-GUI.
    """
    import brreg_rl_comparison as _brc

    out: list[tuple[str, str]] = []
    for key, cfg in _brc._BRREG_KEYS.items():
        aliases = cfg.get("aliases") or []
        label = aliases[0] if aliases else key.replace("_", " ")
        label = str(label).strip()
        if label:
            label = label[0].upper() + label[1:]
        out.append((key, label))
    out.sort(key=lambda pair: pair[0])
    return out
