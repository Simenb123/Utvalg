"""
ab_analyzers.py (façade)
------------------------
Kort modul som eksponerer A/B-funksjoner ved å videresende til
ab_matchers.py og ab_key_deviation.py. Holder denne filen kort og
stabil, og lar under-moduler være fokusert og testbare.
"""

from __future__ import annotations
import re
from typing import Final

# Matchere (beløp/fortegn/two-sum):
from ab_matchers import (
    match_same_amount,
    match_opposite_sign,
    match_two_sum,
)

# Fakturanr/part og avvik:
from ab_key_deviation import (
    normalize_invoice_series,
    match_invoice_equal,
    duplicates_invoice_per_party,
    key_amount_deviation,
    key_date_deviation,
)


def _sheet(name: str) -> str:
    """Excel-kompatibelt ark-navn (maks 31 tegn, forbudte tegn → '_')."""
    name = re.sub(r"[:\\/\?\*\[\]]", "_", str(name))[:31]
    return name or "Ark"


__all__ = [
    # matchere
    "match_same_amount",
    "match_opposite_sign",
    "match_two_sum",
    # faktura/avvik
    "normalize_invoice_series",
    "match_invoice_equal",
    "duplicates_invoice_per_party",
    "key_amount_deviation",
    "key_date_deviation",
    # hjelpe
    "_sheet",
]
