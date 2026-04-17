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
        "kontobetegnelse",
        "kontotekst",
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
        "inngående saldo",
        "inngaaende",
        "opening",
        "openingbalance",
        "opening balance",
        "startbalance",
        "saldo i fjor",
        "saldoifjor",
        "saldo forrige år",
        "forrige år",
        "prior year",
        "prioryear",
    ],
    "ub": [
        "ub",
        "utgående",
        "utgaaende",
        "closing",
        "closingbalance",
        "closing balance",
        "endbalance",
        "endelig",
        "sluttbalanse",
        "saldo i år",
        "saldoiår",
        "saldo i aar",
        "saldoiaar",
        "saldo dette år",
        "this year",
        "current year",
    ],
    "netto": [
        "netto",
        "movement",
        "endring",
        "period",
        "periode",
        "change",
        "delta",
        "årets bevegelse",
        "aarets bevegelse",
        "årets endring",
        "aarets endring",
        "periodens bevegelse",
        "bevegelse",
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
        df = _read_sheet_with_detected_header(p, sn, max_rows=max_rows)
    else:
        # CSV/TXT – forsøk å lese med litt fleksibilitet
        df = pd.read_csv(p, nrows=max_rows, sep=None, engine="python")

    df = _clean_frame(df)
    if df.empty:
        raise ValueError("Saldobalanse-filen ga ingen data (tomt ark/fil).")

    # Try year-aware inference first so that Maestro-like files
    # ("Endelig 2024", "Saldo 2023") resolve without manual mapping.
    try:
        cols, _ = infer_columns_with_year_detection(df)
    except ValueError:
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
    # Defensiv: hvis netto og ub (eller ib) peker på samme kolonne, drop netto
    # — ellers ville _deriveringen nedenfor maske ut UB-verdien.
    netto_col = cols.netto
    if netto_col and (netto_col == cols.ub or netto_col == cols.ib):
        netto_col = None
    netto = _to_amount_series(df[netto_col]) if netto_col else None

    # Debet/kredit (ofte begge positive) → netto = debet - kredit
    if netto is None and cols.debet and cols.kredit and cols.debet in df.columns and cols.kredit in df.columns:
        deb = _to_amount_series(df[cols.debet]).fillna(0.0)
        kred = _to_amount_series(df[cols.kredit]).fillna(0.0)
        # Kredit skal være negativt fortegn i GUI
        netto = deb - kred

    # Deriver manglende — sørg for at alle tre (ib, ub, netto) er tilgjengelig.
    # Spesialtilfelle: kun netto er kjent (f.eks. fra debet/kredit uten IB/UB).
    # Da antar vi IB=0 og UB=netto, som er en TB-snapshot av periodens bevegelse.
    if ib is None and ub is None and netto is not None:
        ib = pd.Series([0.0] * len(df), dtype="float64")
        ub = netto.copy()

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
    # Mange regnskapssystemer (f.eks. Way) bruker sammensatte konto-IDer
    # som "1941PKEY18820865" der de første sifrene er kontonummeret og
    # suffiksen er en intern nøkkel. Vi bruker kun det ledende tallprefiks.
    m = re.match(r"(\d+)", s)
    if not m:
        return ""
    return m.group(1)


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


# ---------------------------------------------------------------------------
# Header-robust sheet reading (handles title rows above the real header)
# ---------------------------------------------------------------------------

def _read_sheet_with_detected_header(
    path: "str | Path",
    sheet_name: "str | int | None",
    *,
    max_rows: Optional[int] = None,
) -> "pd.DataFrame":
    """Les ark med header=None, finn headerrad, bygg ren DataFrame.

    Fallback til standard `pd.read_excel(header=0)` hvis detektoren
    ikke finner en plausibel headerrad.
    """
    import pandas as pd

    try:
        from excel_import_heuristics import detect_header_row_df, clean_header_cell
    except Exception:
        detect_header_row_df = None  # type: ignore[assignment]
        clean_header_cell = None  # type: ignore[assignment]

    sn = 0 if sheet_name is None else sheet_name

    if detect_header_row_df is None:
        return pd.read_excel(path, sheet_name=sn, nrows=max_rows)

    try:
        raw = pd.read_excel(path, sheet_name=sn, header=None)
    except Exception:
        return pd.read_excel(path, sheet_name=sn, nrows=max_rows)

    idx = detect_header_row_df(raw)
    if idx is None:
        return pd.read_excel(path, sheet_name=sn, nrows=max_rows)

    header_row = raw.iloc[idx].tolist()
    if clean_header_cell is not None:
        new_cols = [clean_header_cell(v, i) for i, v in enumerate(header_row)]
    else:
        new_cols = [str(v) if v is not None else f"Unnamed: {i}"
                    for i, v in enumerate(header_row)]

    body = raw.iloc[idx + 1 :].reset_index(drop=True)
    body.columns = new_cols

    if max_rows is not None and len(body) > max_rows:
        body = body.head(max_rows).copy()
    return body


# ---------------------------------------------------------------------------
# Year-number column detection (e.g. "2025" → UB, "2024" → IB)
# ---------------------------------------------------------------------------

_FORELOBIG_KEYWORDS = ("foreløpig", "forelopig", "korreksjon", "korrigering", "midlertidig", "preliminary")
_UB_KEYWORDS = ("endelig", "closing", "ub", "sluttbalanse", "sluttsaldo", "utgående", "utgaaende")
_IB_KEYWORDS = ("ib", "opening", "inngående", "inngaaende", "åpningsbalanse", "apningsbalanse")
# "saldo" er kontekstavhengig: det betyr UB i nåværende år, IB når året er tidligere.
_SALDO_KEYWORDS = ("saldo",)
_NETTO_KEYWORDS = ("endring", "bevegelse", "movement", "netto", "change", "delta")


def _classify_year_column(header: str) -> Tuple[Optional[int], Optional[str]]:
    """Klassifiser et header-navn som (år, rolle).

    Rolle ∈ {"ub", "ib", "netto", "skip", None}.
    - "skip" markerer kolonner som eksplisitt er urelevante
      (foreløpig/korreksjon) og skal ignoreres selv om de har år.
    - None betyr at headeren ikke ser ut som en år-kolonne i det hele tatt.
    """
    s = str(header).strip()
    if not s:
        return None, None

    m = re.search(r"(19|20)\d{2}", s)
    if not m:
        return None, None
    year = int(m.group(0))

    low = s.lower().replace("_", " ")

    # Eksplisitt "forkastet"-status vinner: urelevante kolonner filtreres helt bort.
    if any(k in low for k in _FORELOBIG_KEYWORDS):
        return year, "skip"

    if any(k in low for k in _UB_KEYWORDS):
        return year, "ub"
    if any(k in low for k in _IB_KEYWORDS):
        return year, "ib"
    if any(k in low for k in _NETTO_KEYWORDS):
        return year, "netto"
    if any(k in low for k in _SALDO_KEYWORDS):
        # "Saldo 2024" i en 2024-fil er UB; i fjoråret er det IB.
        # Denne nyansen avgjøres av _detect_year_columns via sortert rekkefølge.
        return year, "saldo"

    # Bare et årstall uten rolle-keyword
    return year, None


def _detect_year_columns(
    columns: Iterable[str],
) -> Dict[str, str]:
    """Detect year-columns and map them to canonical {ib, ub, netto}.

    Bruker `_classify_year_column` slik at embedded-year-kolonner som
    "Endelig 2024" eller "Saldo 2023" også oppdages, ikke bare rene
    årstall som "2024".

    Regel:
      - Hvis rolle-keyword finnes, respekteres rollen eksplisitt
        ("Endelig 2024" → ub, "Endring fra fjoråret" krever eget år).
      - "Skip"-kolonner (foreløpig/korreksjon) filtreres bort.
      - "Saldo {år}": eldste år → ib, nyeste år → ub.
      - For kolonner uten rolle-keyword beholdes gammel heuristikk:
        eldste år = ib, nyeste år = ub (krever nøyaktig to slike).
    """
    classified: List[Tuple[int, str, Optional[str]]] = []  # (year, original_col, role)
    plain_year: List[Tuple[int, str]] = []

    for c in columns:
        year, role = _classify_year_column(c)
        if year is None:
            continue
        if role == "skip":
            continue
        if role is None:
            plain_year.append((year, c))
        else:
            classified.append((year, c, role))

    result: Dict[str, str] = {}

    # 1) Eksplisitte roller — velg vinner pr. (år, rolle) via prioritet.
    #    "ub"/"ib" vinner over "saldo", "saldo" vinner over "netto".
    priority = {"ub": 4, "ib": 4, "saldo": 3, "netto": 2}
    by_role: Dict[Tuple[int, str], str] = {}
    for year, col, role in classified:
        key = (year, role)
        if key not in by_role:
            by_role[key] = col

    # Oppløs "saldo": bruk kronologi på saldo-kolonner for å avgjøre ib vs ub.
    #   - To eller flere saldo-kolonner: eldste = ib, nyeste = ub.
    #   - Én saldo-kolonne + en nyere eksplisitt ub-kolonne: saldo = ib.
    #   - Én saldo-kolonne uten nyere ub: saldo = ub (f.eks. en enslig
    #     "Saldo 2024" i et 2024-datasett).
    saldo_cols = [(y, c) for (y, r), c in by_role.items() if r == "saldo"]
    saldo_years = sorted({y for y, _ in saldo_cols})
    explicit_ub_years = sorted(
        [y for (y, r), _ in by_role.items() if r == "ub"]
    )
    newest_ub_year = explicit_ub_years[-1] if explicit_ub_years else None
    for year, col in saldo_cols:
        if len(saldo_years) >= 2:
            resolved_role = "ib" if year == saldo_years[0] else "ub"
        elif newest_ub_year is not None and year < newest_ub_year:
            # Eneste saldo-kolonne ligger før det nyeste ub-året → ib
            resolved_role = "ib"
        else:
            resolved_role = "ub"
        by_role.setdefault((year, resolved_role), col)
    # Fjern rå "saldo"-nøkler
    by_role = {k: v for k, v in by_role.items() if k[1] != "saldo"}

    # 2) Fallback: kun årstall uten rolle-keyword. Gammel regel
    #    (eldste→ib, nyeste→ub) — men bare hvis vi ikke allerede
    #    har en eksplisitt ub/ib.
    if plain_year:
        plain_year.sort(key=lambda t: t[0])
        if len(plain_year) >= 2:
            ib_year, ib_col = plain_year[0]
            ub_year, ub_col = plain_year[-1]
            by_role.setdefault((ib_year, "ib"), ib_col)
            by_role.setdefault((ub_year, "ub"), ub_col)
        # Et enslig år uten rolle-keyword er for tvetydig — ignoreres
        # (opprinnelig kontrakt; brukeren kan alias-mappe manuelt).

    # 3) Plukk én kolonne pr. kanonisk rolle.
    #    For ub/ib: velg nyeste/eldste år hvis flere finnes.
    ub_candidates = sorted(
        [(y, c) for (y, r), c in by_role.items() if r == "ub"], key=lambda t: t[0]
    )
    ib_candidates = sorted(
        [(y, c) for (y, r), c in by_role.items() if r == "ib"], key=lambda t: t[0]
    )
    netto_candidates = sorted(
        [(y, c) for (y, r), c in by_role.items() if r == "netto"], key=lambda t: t[0]
    )

    if ub_candidates:
        result[ub_candidates[-1][1]] = "ub"
    if ib_candidates:
        result[ib_candidates[0][1]] = "ib"
    if netto_candidates:
        # Velg netto fra samme år som UB hvis mulig
        ub_year = ub_candidates[-1][0] if ub_candidates else None
        chosen = None
        if ub_year is not None:
            for y, c in netto_candidates:
                if y == ub_year:
                    chosen = c
                    break
        if chosen is None:
            chosen = netto_candidates[-1][1]
        # Ikke la netto overskrive ub/ib
        if chosen not in result:
            result[chosen] = "netto"

    return result


# ---------------------------------------------------------------------------
# Raw reading (for preview dialogs — no normalization)
# ---------------------------------------------------------------------------

def read_raw_trial_balance(
    path: str | Path,
    *,
    sheet_name: Optional[str] = None,
    max_rows: int = 50,
) -> "pd.DataFrame":
    """Read a TB file without normalizing — returns the raw DataFrame.

    Useful for preview dialogs where the user needs to see and correct
    column mappings before committing to a full import.
    """
    import pandas as pd

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        sn = sheet_name or _guess_sheet_name(p)
        df = _read_sheet_with_detected_header(p, sn, max_rows=max_rows)
    else:
        df = pd.read_csv(p, nrows=max_rows, sep=None, engine="python")

    return _clean_frame(df)


def infer_columns_with_year_detection(
    df: "pd.DataFrame",
) -> tuple["TrialBalanceColumns", Dict[str, str]]:
    """Like infer_trial_balance_columns but also tries year-column detection.

    Returns (columns, year_map) where year_map is the result of
    _detect_year_columns (may be empty).

    If standard alias matching fails to find IB/UB but year columns exist,
    the year columns are used as fallback.
    """
    year_map = _detect_year_columns(df.columns)

    # Hvis vi har detektert eksplisitte år-kolonner, foretrekk dem framfor
    # ren alias-matching. Dette beskytter mot tilfeller der alias-matching
    # kunne tilordnet "Foreløpig 2024" til UB før _classify_year_column
    # filtrerte bort "foreløpig" som skip.
    if year_map:
        rename = {orig: canonical for orig, canonical in year_map.items()}
        df2 = df.rename(columns=rename)
        try:
            cols = infer_trial_balance_columns(df2)
        except ValueError:
            # Konto/kontonavn manglet i renamed versjon — fall tilbake på
            # standard inferens uten rename.
            cols = infer_trial_balance_columns(df)
            return cols, year_map

        reverse = {v: k for k, v in rename.items()}
        return TrialBalanceColumns(
            konto=cols.konto,
            kontonavn=cols.kontonavn,
            ib=reverse.get(cols.ib, cols.ib) if cols.ib else None,
            ub=reverse.get(cols.ub, cols.ub) if cols.ub else None,
            netto=reverse.get(cols.netto, cols.netto) if cols.netto else None,
            debet=cols.debet,
            kredit=cols.kredit,
        ), year_map

    # Ingen år-kolonner — bruk standard inferens.
    cols = infer_trial_balance_columns(df)
    return cols, year_map
