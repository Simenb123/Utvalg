# scope.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Iterable, Set
import re

import pandas as pd


@dataclass
class ScopeRule:
    name: str
    accounts_spec: str = ""          # "6000-7999, 7210, 73*"
    direction: str = "Alle"          # Alle | Debet | Kredit
    basis: str = "signed"            # signed | abs (grunnlag for beløpsfilter)
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    date_from: Optional[pd.Timestamp] = None
    date_to: Optional[pd.Timestamp] = None

    def normalized(self) -> "ScopeRule":
        d = (self.direction or "Alle").capitalize()
        if d not in ("Alle", "Debet", "Kredit"):
            d = "Alle"
        b = (self.basis or "signed").lower()
        if b not in ("signed", "abs"):
            b = "signed"
        return ScopeRule(
            name=self.name.strip() or "Uten navn",
            accounts_spec=(self.accounts_spec or "").strip(),
            direction=d,
            basis=b,
            min_amount=self.min_amount,
            max_amount=self.max_amount,
            date_from=self.date_from,
            date_to=self.date_to,
        )


def parse_accounts(spec: str, universe: Optional[Iterable[int]] = None) -> Set[int]:
    """
    Parser kontointervaller:
      - komma-separert liste
      - hvert element kan være '7210', '6000-6799', eller '73*'
    universe (valgfr.): begrens til kontoer som faktisk finnes.
    """
    if not spec:
        return set()

    parts = [p.strip() for p in spec.split(",") if p.strip()]
    out: Set[int] = set()
    uni_set = set(int(u) for u in universe) if universe is not None else None

    for p in parts:
        if re.fullmatch(r"\d+\s*-\s*\d+", p):
            a, b = re.split(r"\s*-\s*", p)
            try:
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                rng = range(lo, hi + 1)
                if uni_set is None:
                    out.update(rng)
                else:
                    out.update([x for x in rng if x in uni_set])
            except Exception:
                continue
        elif p.endswith("*") and re.fullmatch(r"\d+\*", p):
            if uni_set is not None:
                pref = p[:-1]
                out.update([x for x in uni_set if str(x).startswith(pref)])
        else:
            try:
                n = int(p)
                if (uni_set is None) or (n in uni_set):
                    out.add(n)
            except Exception:
                continue
    return out
