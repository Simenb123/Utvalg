from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
import re

import pandas as pd
import numpy as np
try:
    import chardet
except Exception:
    chardet = None

def read_any(path: Path | str) -> pd.DataFrame:
    p = Path(path)
    suf = p.suffix.lower()
    if suf in {".xlsx", ".xls"}:
        return pd.read_excel(p, engine="openpyxl", header=None, dtype=str)
    if suf == ".csv":
        for enc in ("utf-8-sig", "utf-8", "latin1"):
            for sep in (";", ","):
                try: return pd.read_csv(p, sep=sep, encoding=enc, header=None, dtype=str)
                except Exception: continue
        if chardet is not None:
            enc = chardet.detect(p.read_bytes()).get("encoding") or "latin1"
            for sep in (";", ","):
                try: return pd.read_csv(p, sep=sep, encoding=enc, header=None, dtype=str)
                except Exception: continue
    raise ValueError("Filen må være .xlsx, .xls eller .csv")

def detect_header_row(raw: pd.DataFrame, max_scan: int = 50) -> int:
    n = min(max_scan, len(raw))
    best_idx, best_score = 0, -1
    keywords = ["konto", "kontonummer", "kontonavn", "bilag", "beløp", "belop", "amount", "sum", "dato", "forfall", "periodeslutt", "periodestart"]
    def _is_numeric_like(x: str) -> bool:
        s = str(x or "").strip()
        for ch in " .,+-": s = s.replace(ch, "")
        return s.isdigit()
    for i in range(n):
        row = raw.iloc[i].astype(str).fillna("")
        non_numeric = sum(not _is_numeric_like(v) and v != "" for v in row)
        unique_vals = len(set(v.strip().lower() for v in row if v.strip()))
        key_hits = sum(1 for v in row for k in keywords if k in v.lower())
        score = non_numeric * 2 + unique_vals + key_hits * 3
        if score > best_score: best_score, best_idx = score, i
    return best_idx

def apply_header(raw: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    cols = raw.iloc[header_idx].astype(str).fillna("").str.strip()
    seen: dict[str, int] = {}; new_cols: list[str] = []
    for c in cols:
        base = c or "kol"; cnt = seen.get(base, 0)
        new_cols.append(base if cnt == 0 else f"{base}_{cnt}"); seen[base] = cnt + 1
    df = raw.iloc[header_idx + 1:].reset_index(drop=True); df.columns = new_cols; return df

@dataclass
class _Guess:
    konto: str = ""; kontonavn: str = ""; bilag: str = ""; belop: str = ""; dato: str = ""; tekst: str = ""; part: str = ""
    due: str = ""; periodestart: str = ""; periodeslutt: str = ""

def guess_columns(cols: List[str]) -> _Guess:
    low = [str(c).lower() for c in cols]
    def first(pats: list[str]) -> str:
        import re as _re
        for c, l in zip(cols, low):
            for p in pats:
                if _re.search(p, l): return c
        return ""
    g = _Guess(
        konto=first([r"\bkonto\b|konto.*nr|kontonummer|account ?no|acct ?no"]),
        kontonavn=first([r"kontonavn|account ?name|acct ?name|beskrivelse|tekst|description|name"]),
        bilag=first([r"\bbilag\b|voucher|dokument|dok\.? ?nr|document ?no|journal|voucher ?no|bilagsnr|faktura"]),
        belop=first([r"bel[oø]p|amount|sum(?!mary)|debet|kredit|debit|credit|saldo"]),
        dato=first([r"dato|date|trans\.? ?date|posting ?date|bokf|periode"]),
        tekst=first([r"tekst|beskrivelse|description|post ?text|line ?text|narrative|comment"]),
        part=first([r"part|kunde|leverand[oø]r|vendor|customer|client|kontrahent|counterparty|mottaker|avsender"]),
        due=first([r"forfall|forfallsdato|due ?date|forf\.? ?dato"]),
        periodestart=first([r"period(e|e-)?start|from ?period|start ?period|periode ?fra|periodestart|startdato"]),
        periodeslutt=first([r"period(e|e-)?slutt|to ?period|end ?period|periode ?til|periodeslutt|sluttdato"]),
    )
    if g.konto and not g.kontonavn:
        if any(c.strip().lower() == "konto" for c in cols):
            g.kontonavn = next((c for c in cols if c.strip().lower() == "konto"), g.kontonavn)
    return g

def coerce_amount_series(s: pd.Series) -> pd.Series:
    return (s.astype(str).str.replace("\u00A0","", regex=False).str.replace(" ", "", regex=False)
            .str.replace("kr","", case=False, regex=False).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            .apply(lambda x: np.nan if x == "" else x).astype(float))

def coerce_account_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d+)", expand=False).astype("Int64")

def coerce_date_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"": None})
    d1 = pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
    d2 = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    out = d1.fillna(d2); missing = out.isna()
    if missing.any(): out[missing] = pd.to_datetime(s[missing], errors="coerce", dayfirst=True)
    return out
