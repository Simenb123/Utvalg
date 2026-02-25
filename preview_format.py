"""preview_format.py

Formattering for "Forhåndsvisning" i Dataset-fanen.

Mål
---
Brukeren forventer at preview ligner mer på Excel-visningen:
  - Dato: dd.mm.yyyy (evt. med klokkeslett)
  - Tall/beløp: tusenskiller (mellomrom) og desimal-komma

Samtidig må vi unngå å "ødelegge" ID-kolonner (bilagsnr, konto), der
tusenskiller kan gjøre tallene vanskeligere å sammenligne mot original.

Denne modulen er uten Tk-avhengigheter slik at den kan enhetstestes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math
import re
from typing import Any, List, Optional, Sequence

import pandas as pd


_EMPTY_STRINGS = {"", "nan", "none", "null", "nat"}
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def _is_empty(v: Any) -> bool:
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


def _format_date_no(v: Any) -> str:
    if _is_empty(v):
        return ""
    if isinstance(v, pd.Timestamp):
        if pd.isna(v):
            return ""
        v = v.to_pydatetime()
    if isinstance(v, datetime):
        if v.hour == 0 and v.minute == 0 and v.second == 0 and v.microsecond == 0:
            return v.strftime("%d.%m.%Y")
        return v.strftime("%d.%m.%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    # fallback
    return str(v)


def _group_int_no(n: int) -> str:
    # tusenskiller som mellomrom
    return f"{n:,d}".replace(",", " ")


def _format_amount_no(num: float, *, decimals: int = 2) -> str:
    if num is None or (isinstance(num, float) and math.isnan(num)):
        return ""
    # Format med amerikansk locale først, så bytt skilletegn.
    s = f"{num:,.{decimals}f}"
    s = s.replace(",", " ").replace(".", ",")
    return s


def _format_number_plain(v: Any) -> str:
    if _is_empty(v):
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, (float, Decimal)):
        try:
            f = float(v)
        except Exception:
            return str(v)
        if math.isnan(f):
            return ""
        if abs(f - round(f)) < 1e-9:
            return str(int(round(f)))
        # Ikke bruk tusenskiller i "plain" – det kan forvirre ID-kolonner.
        # Men bytt til norsk desimal-komma for lesbarhet.
        s = f"{f:.6f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    return str(v)


def format_preview_value(v: Any, *, kind: str = "") -> str:
    """Formater en enkelt celleverdi for preview.

    kind:
        "date"   -> dd.mm.yyyy(/tid)
        "amount" -> tusenskiller + desimal-komma (2 desimaler)
        "id"     -> ingen tusenskiller
        ""       -> best-effort basert på datatype
    """
    if _is_empty(v):
        return ""

    kind = (kind or "").strip().lower()

    if kind == "date":
        return _format_date_no(v)

    if kind == "amount":
        # Prøv å tolke strenger som tall – men vi gjør det kun for amount,
        # fordi ID-kolonner ofte har leading zeros som må bevares.
        if isinstance(v, str):
            s = v.strip().replace("\u00a0", " ")
            if not s:
                return ""
            # Best-effort parse norsk/engelsk tall
            s2 = s.replace(" ", "")
            if s2.endswith("-"):
                s2 = "-" + s2[:-1]
            s2 = s2.replace(".", "").replace(",", ".") if s2.count(",") == 1 else s2
            try:
                num = float(s2)
            except Exception:
                return s
        else:
            try:
                num = float(v)
            except Exception:
                return str(v)
        return _format_amount_no(num, decimals=2)

    if kind == "id":
        return _format_number_plain(v)

    # Automatikk basert på type
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return _format_date_no(v)
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return _format_number_plain(v)

    return str(v)


@dataclass(frozen=True)
class ColumnKind:
    kind: str  # date/amount/id/text/generic


def infer_column_kinds(
    rows: Sequence[Sequence[Any]],
    *,
    header_row_idx0: Optional[int] = None,
) -> List[str]:
    """Best-effort: gjett visningsformat pr kolonne.

    Vi bruker kun for preview-visning (ikke parsing til datasett).

    Heuristikk
    ---------
    - date: mange date/datetime
    - amount: mange numeriske, og (negativt eller flyt/desimal)
    - id: numerisk og stort sett heltall (uten negative/flyt)
    """

    if not rows:
        return []

    # Finn maks bredde
    width = max((len(r) for r in rows), default=0)
    if width <= 0:
        return []

    # Bruk rader etter header som datagrunnlag når vi har en header-gjett.
    data_rows = list(rows)
    if header_row_idx0 is not None and 0 <= int(header_row_idx0) < len(rows) - 1:
        data_rows = list(rows[int(header_row_idx0) + 1 :])
        if not data_rows:
            data_rows = list(rows)

    # Normaliser til fast bredde
    norm_rows: List[List[Any]] = []
    for r in data_rows:
        rr = list(r)
        if len(rr) < width:
            rr = rr + [None] * (width - len(rr))
        else:
            rr = rr[:width]
        norm_rows.append(rr)

    kinds: List[str] = []
    for j in range(width):
        col = [r[j] for r in norm_rows]
        non_empty = [v for v in col if not _is_empty(v)]
        if len(non_empty) < 3:
            kinds.append("generic")
            continue

        date_like = 0
        num_like = 0
        float_like = 0
        neg_like = 0

        for v in non_empty:
            if isinstance(v, (pd.Timestamp, datetime, date)):
                date_like += 1
                continue

            if isinstance(v, bool):
                continue

            if isinstance(v, (int,)):
                num_like += 1
                if v < 0:
                    neg_like += 1
                continue

            if isinstance(v, (float, Decimal)):
                try:
                    f = float(v)
                except Exception:
                    continue
                if math.isnan(f):
                    continue
                num_like += 1
                float_like += 1
                if f < 0:
                    neg_like += 1
                continue

            if isinstance(v, str) and _CURRENCY_RE.match(v.strip()):
                continue

        n = len(non_empty)
        date_ratio = date_like / n
        num_ratio = num_like / n

        if date_ratio >= 0.60:
            kinds.append("date")
            continue

        if num_ratio >= 0.70 and (neg_like > 0 or float_like > 0):
            kinds.append("amount")
            continue

        if num_ratio >= 0.80 and neg_like == 0 and float_like == 0:
            kinds.append("id")
            continue

        kinds.append("generic")

    return kinds
