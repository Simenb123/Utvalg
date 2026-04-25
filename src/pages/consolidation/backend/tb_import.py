"""consolidation.tb_import – Importer saldobalanse per selskap.

Wrapper rundt eksisterende trial_balance_reader og saft_trial_balance.
Normaliserer output til felles kolonnenavn: konto, kontonavn, ib, ub, netto.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import CompanyTB

logger = logging.getLogger(__name__)

# Kanoniske kolonnenavn for konsoliderings-TB
CANONICAL_COLS = ["konto", "kontonavn", "ib", "ub", "netto"]


def _detect_source_type(path: Path) -> str:
    """Gjett kildetype basert paa filendelse."""
    suffix = path.suffix.lower()
    if suffix in (".xml", ".zip"):
        return "saft"
    if suffix == ".csv":
        return "csv"
    return "excel"


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliser kolonnenavn til lowercase kanonisk form."""
    col_map = {}
    for col in df.columns:
        lower = str(col).strip().lower()
        if lower in CANONICAL_COLS:
            col_map[col] = lower

    if col_map:
        df = df.rename(columns=col_map)

    # Sikre at alle kanoniske kolonner finnes
    for c in CANONICAL_COLS:
        if c not in df.columns:
            if c in ("ib", "ub", "netto"):
                df[c] = 0.0
            else:
                df[c] = ""

    # Tving typer
    df["konto"] = df["konto"].astype(str).str.strip()
    df["kontonavn"] = df["kontonavn"].astype(str).str.strip()
    for c in ("ib", "ub", "netto"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Deriver manglende verdier — samme logikk som trial_balance_reader.
    # Hvis bare netto finnes (IB=0, UB=0, Netto!=0): sett UB = IB + Netto.
    has_ib = (df["ib"].abs() > 0.005).any()
    has_ub = (df["ub"].abs() > 0.005).any()
    has_netto = (df["netto"].abs() > 0.005).any()

    if not has_ub and has_netto:
        df["ub"] = df["ib"] + df["netto"]
    elif not has_netto and has_ib and has_ub:
        df["netto"] = df["ub"] - df["ib"]

    # Fjern rader uten kontonummer
    df = df[df["konto"].str.len() > 0].copy()

    return df[CANONICAL_COLS]


def validate_tb(df: pd.DataFrame) -> list[str]:
    """Validate a normalized TB DataFrame and return warnings.

    This function is used by both the direct import path (SAF-T) and
    the preview import path (Excel/CSV) to ensure consistent quality checks.
    """
    warnings: list[str] = []

    # Check for IB values — important for consolidation quality
    if "ib" in df.columns:
        has_ib = (df["ib"].abs() > 0.005).any()
        if not has_ib:
            warnings.append(
                "Ingen IB-verdier funnet — dette er kun netto-/bevegelsesdata, "
                "ikke en fullstendig saldobalanse. UB settes lik Netto."
            )

    # Check for non-numeric account numbers
    if "konto" in df.columns:
        non_digit = df[~df["konto"].str.match(r"^\d+$")]
        if len(non_digit) > 0:
            warnings.append(
                f"{len(non_digit)} konto(er) med ikke-numerisk kontonummer."
            )

    # Check for empty account names
    if "kontonavn" in df.columns:
        empty_names = (df["kontonavn"].str.strip() == "").sum()
        if empty_names > 0:
            warnings.append(f"{empty_names} konto(er) uten kontonavn.")

    # Check for all-zero rows (possible junk data)
    numeric_cols = [c for c in ("ib", "ub", "netto") if c in df.columns]
    if numeric_cols:
        all_zero = (df[numeric_cols].abs() < 0.005).all(axis=1).sum()
        if all_zero > len(df) * 0.5 and len(df) > 5:
            warnings.append(
                f"{all_zero} av {len(df)} rader har kun nullverdier."
            )

    return warnings


def import_company_tb(
    file_path: str | Path,
    company_name: str,
    *,
    sheet_name: Optional[str] = None,
) -> tuple[CompanyTB, pd.DataFrame, list[str]]:
    """Importer TB fra fil og normaliser.

    Returnerer (CompanyTB-metadata, normalisert DataFrame, advarsler).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Filen finnes ikke: {path}")

    source_type = _detect_source_type(path)
    warnings: list[str] = []

    if source_type == "saft":
        from saft_trial_balance import extract_trial_balance_df_from_saft
        df = extract_trial_balance_df_from_saft(path)
    else:
        from trial_balance_reader import read_trial_balance
        df = read_trial_balance(path, sheet_name=sheet_name)

    df = _normalize_columns(df)
    warnings.extend(validate_tb(df))

    has_ib = (df["ib"].abs() > 0.005).any()

    company = CompanyTB(
        name=company_name.strip(),
        source_file=path.name,
        source_type=source_type,
        row_count=len(df),
        has_ib=bool(has_ib),
    )

    logger.info(
        "Imported %s: %d rows, has_ib=%s, source=%s",
        company_name, len(df), has_ib, source_type,
    )

    return company, df, warnings
