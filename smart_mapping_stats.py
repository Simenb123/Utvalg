"""smart_mapping_stats.py

Internmodul for :mod:`smart_mapping`.

Hvorfor finnes denne filen?
--------------------------
`smart_mapping.py` vokste etter hvert over ~400 linjer. For å holde
kodebasen mer vedlikeholdbar (og gjøre endringer lav-risiko) er
statistikk- og scorelogikken flyttet hit.

Modulen:
- analyserer kolonneinnhold fra et lite sample (typisk 10–50 rader)
- beregner enkle statistikker per kolonne
- tilbyr score-funksjoner for å identifisere felter som:
  - Konto, Bilag, Beløp, Dato, Tekst
  - Kontonavn
  - Valuta, Valutabeløp
  - MVA-kode, MVA-prosent, MVA-beløp

Den er bevisst *best-effort* og brukes kun til å foreslå mapping i GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
import math
import re
from statistics import median
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


logger = logging.getLogger(__name__)


_EMPTY_STRINGS = {"", "nan", "none", "null", "nat"}
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_HAS_LETTER_RE = re.compile(r"[A-Za-zÆØÅæøå]")
_NUM_KEEP_RE = re.compile(r"[^0-9,\.\-\(\)]")


@dataclass(frozen=True)
class ColStats:
    idx: int
    name: str
    non_empty: int
    numeric_ratio: float
    int_ratio: float
    float_ratio: float
    decimal_ratio: float
    negative_ratio: float
    date_ratio: float
    currency_ratio: float
    text_ratio: float
    avg_len: float
    unique_ratio: float
    median_digits: Optional[float]
    between_0_100_ratio: float
    zero_ratio: float
    median_abs: Optional[float]
    max_abs: Optional[float]


def is_empty(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except Exception:
        pass

    if isinstance(v, str):
        return v.strip().lower() in _EMPTY_STRINGS
    return False


def try_parse_number(v: Any) -> Tuple[Optional[float], bool, bool, bool]:
    """Returner (num, int_like, has_decimal, is_negative)."""

    if v is None:
        return None, False, False, False

    if isinstance(v, bool):
        return float(int(v)), True, False, False

    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            f = float(v)
        except Exception:
            return None, False, False, False
        if isinstance(v, float) and math.isnan(f):
            return None, False, False, False
        int_like = abs(f - round(f)) < 1e-9
        has_decimal = not int_like
        return f, int_like, has_decimal, f < 0

    s = str(v).strip()
    if not s:
        return None, False, False, False
    if s.strip().lower() in _EMPTY_STRINGS:
        return None, False, False, False

    s = s.replace("\u00a0", " ").replace(" ", "")

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.endswith("-"):
        neg = True
        s = s[:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]

    s = _NUM_KEEP_RE.sub("", s)
    if not s:
        return None, False, False, False

    # Bestem desimalskilletegn
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            dec, thou = ",", "."
        else:
            dec, thou = ".", ","
        s = s.replace(thou, "")
        s = s.replace(dec, ".")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "")
            s = s.replace(",", ".")
    else:
        if s.count(".") > 1:
            parts = s.split(".")
            if len(parts[-1]) == 3:
                s = "".join(parts)
            else:
                s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        f = float(s)
    except Exception:
        return None, False, False, False

    f = -f if neg else f
    int_like = abs(f - round(f)) < 1e-9
    has_decimal = not int_like
    return f, int_like, has_decimal, f < 0


def try_parse_date(v: Any) -> bool:
    if v is None:
        return False

    if isinstance(v, (pd.Timestamp, datetime, date)):
        return True

    # Excel serial date
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            f = float(v)
        except Exception:
            return False
        if math.isnan(f):
            return False
        return 20000 <= f <= 80000

    s = str(v).strip()
    if not s or s.lower() in _EMPTY_STRINGS:
        return False

    if not any(ch in s for ch in ("-", ".", "/")):
        return False

    try:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
        return not pd.isna(dt)
    except Exception:
        return False


def digits_of_int_like(num: float) -> Optional[int]:
    try:
        n = int(abs(round(float(num))))
    except Exception:
        return None
    if n == 0:
        return 1
    return len(str(n))


def analyze_columns(headers: Sequence[str], sample_rows: Sequence[Sequence[Any]]) -> List[ColStats]:
    ncols = len(list(headers))
    if ncols <= 0:
        return []

    rows: List[List[Any]] = []
    for r in sample_rows:
        rr = list(r)
        if len(rr) < ncols:
            rr = rr + [None] * (ncols - len(rr))
        else:
            rr = rr[:ncols]
        rows.append(rr)

    out: List[ColStats] = []
    for idx, name in enumerate(headers):
        col_vals = [r[idx] for r in rows]
        non_empty_vals = [v for v in col_vals if not is_empty(v)]
        non_empty = len(non_empty_vals)

        if non_empty <= 0:
            out.append(
                ColStats(
                    idx=idx,
                    name=str(name),
                    non_empty=0,
                    numeric_ratio=0.0,
                    int_ratio=0.0,
                    float_ratio=0.0,
                    decimal_ratio=0.0,
                    negative_ratio=0.0,
                    date_ratio=0.0,
                    currency_ratio=0.0,
                    text_ratio=0.0,
                    avg_len=0.0,
                    unique_ratio=0.0,
                    median_digits=None,
                    between_0_100_ratio=0.0,
                    zero_ratio=0.0,
                    median_abs=None,
                    max_abs=None,
                )
            )
            continue

        num_count = 0
        int_like_count = 0
        float_count = 0
        decimal_count = 0
        neg_count = 0
        date_count = 0
        cur_count = 0
        text_count = 0
        between_0_100 = 0
        zero_count = 0

        lengths: List[int] = []
        unique_bucket: set[str] = set()
        digits: List[int] = []
        abs_nums: List[float] = []

        for v in non_empty_vals:
            s = str(v).strip()
            unique_bucket.add(s)
            lengths.append(len(s))

            if isinstance(v, str) and _CURRENCY_RE.match(v.strip()):
                cur_count += 1

            if try_parse_date(v):
                date_count += 1

            num, int_like, has_dec, is_neg = try_parse_number(v)
            if num is not None:
                num_count += 1
                abs_num = abs(float(num))
                abs_nums.append(abs_num)
                if abs_num < 1e-12:
                    zero_count += 1

                if int_like:
                    int_like_count += 1
                    d = digits_of_int_like(num)
                    if d is not None:
                        digits.append(d)
                else:
                    decimal_count += 1

                if isinstance(v, float):
                    float_count += 1
                elif isinstance(v, int):
                    pass
                else:
                    float_count += 1

                if is_neg:
                    neg_count += 1

                if 0 <= float(num) <= 100:
                    between_0_100 += 1

            if isinstance(v, str) and _HAS_LETTER_RE.search(v):
                if not _CURRENCY_RE.match(v.strip()):
                    text_count += 1

        numeric_ratio = num_count / non_empty
        int_ratio = int_like_count / non_empty
        float_ratio = float_count / non_empty
        decimal_ratio = decimal_count / non_empty
        negative_ratio = neg_count / non_empty
        date_ratio = date_count / non_empty
        currency_ratio = cur_count / non_empty
        text_ratio = text_count / non_empty
        avg_len = float(sum(lengths)) / max(1, len(lengths))
        unique_ratio = len(unique_bucket) / max(1, non_empty)
        between_0_100_ratio = between_0_100 / non_empty
        zero_ratio = (zero_count / num_count) if num_count else 0.0

        median_digits_val: Optional[float] = None
        if digits:
            try:
                median_digits_val = float(median(digits))
            except Exception:
                median_digits_val = None

        median_abs: Optional[float] = None
        max_abs: Optional[float] = None
        if abs_nums:
            try:
                median_abs = float(median(abs_nums))
            except Exception:
                median_abs = None
            try:
                max_abs = float(max(abs_nums))
            except Exception:
                max_abs = None

        out.append(
            ColStats(
                idx=idx,
                name=str(name),
                non_empty=non_empty,
                numeric_ratio=numeric_ratio,
                int_ratio=int_ratio,
                float_ratio=float_ratio,
                decimal_ratio=decimal_ratio,
                negative_ratio=negative_ratio,
                date_ratio=date_ratio,
                currency_ratio=currency_ratio,
                text_ratio=text_ratio,
                avg_len=avg_len,
                unique_ratio=unique_ratio,
                median_digits=median_digits_val,
                between_0_100_ratio=between_0_100_ratio,
                zero_ratio=zero_ratio,
                median_abs=median_abs,
                max_abs=max_abs,
            )
        )

    return out


# -----------------------------------------------------------------------------
# Små hjelpefunksjoner
# -----------------------------------------------------------------------------


def adjacency_bonus(idx: int, neighbor_idxs: Iterable[int], *, max_dist: int = 2, bonus: float = 1.0) -> float:
    """Gi bonus hvis kolonnen ligger nær en annen relevant kolonne."""

    n = list(neighbor_idxs)
    if not n:
        return 0.0

    try:
        dist = min(abs(int(idx) - int(x)) for x in n)
    except Exception:
        return 0.0

    if dist > max_dist:
        return 0.0

    # dist=0 -> 1.0*bonus, dist=max_dist -> ~0.33*bonus
    return float(bonus) * float(max_dist - dist + 1) / float(max_dist + 1)
