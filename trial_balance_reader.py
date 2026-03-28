from __future__ import annotations

"""Lesing og normalisering av saldobalanse / trial balance.

Mål:
 - Robust mot litt ulike kolonnenavn fra ulike systemer
 - Standardiserer til interne kolonnenavn:
     konto (str), kontonavn (str), ib (float), ub (float), netto (float)
 - Debet = positivt, Kredit = negativt (netto).

Denne modulen er bevisst *uavhengig* av GUI-kode.
"""

from dataclasses import dataclass
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


log = logging.getLogger("app")


@dataclass(frozen=True)
class TrialBalanceColumns:
    konto: str
    kontonavn: Optional[str]
    ib: Optional[str]
    ub: Optional[str]
    netto: Optional[str]
    debet: Optional[str]
    kredit: Optional[str]


_COL_ALIASES: Dict[str, List[str]] = {
    "konto": [
        "konto",
        "kontonr",
        "kontonummer",
        "account",
        "accountid",
        "account_id",
        "account no",
        "account number",
    ],
    "kontonavn": [
        "kontonavn",
        "konto navn",
        "beskrivelse",
        "tekst",
        "navn",
        "accountdescription",
        "account description",
        "description",
        "accountname",
        "account name",
    ],
    "ib": [
        "ib",
        "ingående",
        "inngående",
        "opening",
        "openingbalance",
        "opening balance",
        "startbalance",
    ],
    "ub": [
        "ub",
        "utgående",
        "utgaaende",
        "closing",
        "closingbalance",
        "closing balance",
        "endbalance",
        "sluttbalanse",
    ],
    "netto": [
        "netto",
        "movement",
        "endring",
        "period",
        "periode",
        "change",
        "delta",
    ],
    "debet": ["debet", "debit"],
    "kredit": ["kredit", "credit"],
}


def read_trial_balance(
    path: str | Path,
    *,
    sheet_name: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> "pd.DataFrame":
    """Les og normaliser saldobalanse.

    Args:
        path: Filsti til .xlsx/.xlsm/.xls eller .csv/.txt
        sheet_name: Excel-ark. Hvis None forsøkes det å velge et sannsynlig ark.
        max_rows: Begrens antall rader (nyttig for preview). None = alle.
    """

    import pandas as pd

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        sn = sheet_name or _guess_sheet_name(p)
        df = pd.read_excel(p, sheet_name=sn, nrows=max_rows)
    else:
        # CSV/TXT – forsøk å lese med litt fleksibilitet
        df = pd.read_csv(p, nrows=max_rows, sep=None, engine="python")

    df = _clean_frame(df)
    if df.empty:
        raise ValueError("Saldobalanse-filen ga ingen data (tomt ark/fil).")

    cols = infer_trial_balance_columns(df)
    out = _standardize(df, cols)
    return out


def infer_trial_balance_columns(df: "pd.DataFrame") -> TrialBalanceColumns:
    """Gjetter kolonner basert på header-navn.

    Vi baserer oss primært på kolonnenavn (ikke innhold), for å være deterministisk.
    """

    import pandas as pd

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df må være en pandas.DataFrame")

    col_norm = {c: _norm_header(c) for c in df.columns}

    def pick(required_key: str, *, optional: bool = False) -> Optional[str]:
        best: Tuple[int, Optional[str]] = (0, None)
        for col, n in col_norm.items():
            score = _score_aliases(n, _COL_ALIASES.get(required_key, []))
            if score > best[0]:
                best = (score, col)
        if best[1] is None and not optional:
            raise ValueError(f"Fant ikke nødvendig kolonne for '{required_key}'. Kolonner: {list(df.columns)}")
        return best[1]

    konto = pick("konto")
    kontonavn = pick("kontonavn", optional=True)
    ib = pick("ib", optional=True)
    ub = pick("ub", optional=True)
    netto = pick("netto", optional=True)

    # Hvis både debet og kredit finnes, kan vi bruke dem som netto.
    debet = pick("debet", optional=True)
    kredit = pick("kredit", optional=True)

    if ub is None and netto is None and (debet is None or kredit is None):
        raise ValueError(
            "Fant ikke UB/netto (eller debet+kredit). Trenger minst én av: UB, Netto/Endring eller Debet+Kredit."
        )

    return TrialBalanceColumns(
        konto=konto,
        kontonavn=kontonavn,
        ib=ib,
        ub=ub,
        netto=netto,
        debet=debet,
        kredit=kredit,
    )


def _guess_sheet_name(path: Path) -> str:
    """Velg et sannsynlig ark for saldobalanse."""

    try:
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
    except Exception:
        # Fallback: pandas default er første ark
        return 0  # type: ignore[return-value]

    if not names:
        return 0  # type: ignore[return-value]

    def score(name: str) -> int:
        n = _norm_header(name)
        s = 0
        if "trial" in n:
            s += 5
        if "balance" in n:
            s += 5
        if "sald" in n:
            s += 5
        if "tb" == n:
            s += 3
        if "account" in n:
            s -= 1
        return s

    best = max(names, key=score)
    return best


def _clean_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd

    if df is None:
        return pd.DataFrame()
    df2 = df.copy()
    # Fjern helt tomme rader/kolonner
    df2 = df2.dropna(axis=0, how="all").dropna(axis=1, how="all")
    # Trim kolonnenavn
    df2.columns = [str(c).strip() for c in df2.columns]
    return df2


def _standardize(df: "pd.DataFrame", cols: TrialBalanceColumns) -> "pd.DataFrame":
    import pandas as pd

    out = pd.DataFrame()
    out["konto"] = df[cols.konto].map(_normalize_konto)
    if cols.kontonavn and cols.kontonavn in df.columns:
        out["kontonavn"] = df[cols.kontonavn].astype(str).fillna("").map(lambda s: s.strip())
    else:
        out["kontonavn"] = ""

    ib = _to_amount_series(df[cols.ib]) if cols.ib else None
    ub = _to_amount_series(df[cols.ub]) if cols.ub else None
    netto = _to_amount_series(df[cols.netto]) if cols.netto else None

    # Debet/kredit (ofte begge positive) → netto = debet - kredit
    if netto is None and cols.debet and cols.kredit and cols.debet in df.columns and cols.kredit in df.columns:
        deb = _to_amount_series(df[cols.debet]).fillna(0.0)
        kred = _to_amount_series(df[cols.kredit]).fillna(0.0)
        # Kredit skal være negativt fortegn i GUI
        netto = deb - kred

    # Deriver manglende
    if netto is None and ib is not None and ub is not None:
        netto = ub.fillna(0.0) - ib.fillna(0.0)
    if ub is None and ib is not None and netto is not None:
        ub = ib.fillna(0.0) + netto.fillna(0.0)
    if ib is None and ub is not None and netto is not None:
        ib = ub.fillna(0.0) - netto.fillna(0.0)

    out["ib"] = (ib if ib is not None else pd.Series([0.0] * len(out))).astype("float64")
    out["ub"] = (ub if ub is not None else pd.Series([0.0] * len(out))).astype("float64")
    out["netto"] = (netto if netto is not None else (out["ub"] - out["ib"])).astype("float64")

    # Dropp rader uten konto
    out = out.loc[out["konto"].astype(str).str.len() > 0].copy()
    out["konto"] = out["konto"].astype(str)

    # Fjern evt. "nan" kontonavn
    out["kontonavn"] = out["kontonavn"].replace({"nan": "", "None": ""})

    return out.reset_index(drop=True)


def _normalize_konto(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() == "nan":
        return ""
    # Fjern alt bortsett fra siffer
    digits = re.findall(r"\d+", s)
    if not digits:
        return ""
    return "".join(digits)


def _to_amount_series(series: "pd.Series") -> "pd.Series":
    import pandas as pd

    if series is None:
        return pd.Series([], dtype="float64")

    # Shortcut for numeriske kolonner
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype("float64")

    return series.map(_parse_amount).astype("float64")


def _parse_amount(v: object) -> float:
    """Robust tall-parsing (NO/EU/US).

    Støtter:
      - "1 234,56"
      - "1.234,56"
      - "1,234.56"
      - "-1234" / "(1234)"
    """

    if v is None:
        return float("nan")
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return float("nan")

    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return float("nan")

    # Negativ med parentes
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]

    # Fjern valuta/tekst
    s = re.sub(r"[^0-9,\.\-\s]", "", s)
    s = s.strip()

    # Fjern mellomrom som tusenskiller
    s = s.replace(" ", "")

    # Hvis både ',' og '.' finnes: avgjør desimalskilletegn som siste forekomst
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # EU: 1.234,56
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # US: 1,234.56
            s = s.replace(",", "")
    else:
        # Bare ',' → desimal
        if "," in s and "." not in s:
            s = s.replace(",", ".")

        # Bare '.' kan være tusenskiller hvis mange grupper
        if s.count(".") > 1:
            s = s.replace(".", "")

    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return float("nan")


def _norm_header(h: object) -> str:
    s = str(h).strip().lower()
    s = re.sub(r"\s+", " ", s)
    # fjern skilletegn
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return s.replace(" ", "")


def _score_aliases(norm: str, aliases: Sequence[str]) -> int:
    if not norm:
        return 0
    best = 0
    for a in aliases:
        an = _norm_header(a)
        if norm == an:
            best = max(best, 100)
        elif norm.startswith(an):
            best = max(best, 50)
        elif an in norm:
            best = max(best, 10)
    return best
