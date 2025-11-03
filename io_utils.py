# io_utils.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
import re
import numpy as np
import pandas as pd
import chardet

# ---------- Lesing (rå, uten header) ----------
def read_any(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suf = p.suffix.lower()
    if suf in {".xlsx", ".xls"}:
        return pd.read_excel(p, engine="openpyxl", header=None, dtype=str)
    if suf == ".csv":
        data = p.read_bytes()
        enc = (chardet.detect(data) or {}).get("encoding") or "utf-8-sig"
        for sep in (";", ",", "\t"):
            try:
                return pd.read_csv(p, sep=sep, encoding=enc, header=None, dtype=str)
            except Exception:
                continue
    raise ValueError("Støtter .xlsx/.xls/.csv")

# ---------- Header-detek­sjon + anvend ----------
def _is_numeric_like(x: str) -> bool:
    s = str(x or "").strip()
    for ch in " .,+-": s = s.replace(ch, "")
    return s.isdigit()

def detect_header_row(raw: pd.DataFrame, max_scan: int = 50) -> int:
    n = min(max_scan, len(raw))
    best_idx, best_score = 0, -1
    keywords = ["konto", "kontonummer", "kontonavn", "bilag", "beløp", "belop", "amount", "sum", "dato", "tekst"]
    for i in range(n):
        row = raw.iloc[i].astype(str).fillna("")
        non_numeric = sum(not _is_numeric_like(v) and v != "" for v in row)
        unique_vals = len(set(v.strip().lower() for v in row if v.strip()))
        key_hits = sum(1 for v in row for k in keywords if k in v.lower())
        score = non_numeric * 2 + unique_vals + key_hits * 3
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx

def apply_header(raw: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    cols = raw.iloc[header_idx].astype(str).fillna("").str.strip()
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for c in cols:
        base = c or "kol"
        cnt = seen.get(base, 0)
        new_cols.append(base if cnt == 0 else f"{base}_{cnt}")
        seen[base] = cnt + 1
    df = raw.iloc[header_idx + 1:].reset_index(drop=True)
    df.columns = new_cols
    return df

# ---------- Kolonnegjetting ----------
@dataclass
class Guess: konto:str=""; kontonavn:str=""; bilag:str=""; belop:str=""; dato:str=""; tekst:str=""; part:str=""

def guess_columns(cols: List[str]) -> Guess:
    low = [str(c).lower() for c in cols]
    def first(pats: list[str]) -> str:
        for c, l in zip(cols, low):
            for p in pats:
                if re.search(p, l): return c
        return ""
    return Guess(
        konto=first([r"\bkonto\b|kontonr|kontonummer|account ?(no|number)|gl ?account|hovedbokskonto"]),
        kontonavn=first([r"kontonavn|account ?name|beskrivelse|tekst|description|name"]),
        bilag=first([r"\bbilag\b|bilagsnr|voucher|dokument|dok\.? ?nr|document ?no|journal|invoice ?no|faktura"]),
        belop=first([r"bel[oø]p|amount|sum(?!mary)|debet|kredit|debit|credit|saldo|utgift|inntekt"]),
        dato=first([r"dato|date|trans(.*)date|post(.*)date|valuta(.*)dato|bilagsdato"]),
        tekst=first([r"tekst|beskrivelse|description|narrative|post(.*)text"]),
        part=first([r"part|kunde|leverand[oø]r|vendor|customer|counterparty|motsatt|motpart"]),
    )

# ---------- Konverteringer (norsk) ----------
def coerce_amount_series(s: pd.Series) -> pd.Series:
    def _one(x: str):
        t = str(x or "").strip().lower().replace("\u2212", "-").replace("–", "-")
        for tok in ("kr", "nok"): t = t.replace(tok, "")
        t = t.replace("\xa0", " ").replace(" ", "")
        if t == "": return np.nan
        if "," in t and "." in t:
            last = max(t.rfind(","), t.rfind("."))
            dec = t[last]; thou = "," if dec == "." else "."
            t = t.replace(thou, "").replace(dec, ".")
        elif "," in t:
            right = t.split(",")[-1]
            t = t.replace(",", ".") if len(right) <= 2 else t.replace(",", "")
        else:
            parts = t.split(".")
            if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]): t = "".join(parts)
        try: return float(t)
        except Exception: return np.nan
    return s.astype(str).map(_one).astype(float)

def coerce_account_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d+)", expand=False).astype("Int64")

def coerce_date_series(s: pd.Series) -> pd.Series:
    def _parse_one(v: str):
        t = str(v or "").strip()
        if t == "": return pd.NaT
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
            try: return pd.to_datetime(t, format=fmt, errors="raise")
            except Exception: pass
        return pd.to_datetime(t, errors="coerce", dayfirst=True)
    return s.map(_parse_one)
