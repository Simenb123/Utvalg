"""Utilities for extracting a trial balance (saldobalanse) from a SAF-T file.

We only need MasterFiles/GeneralLedgerAccounts which should appear early in the
SAF-T file. This module therefore uses a streaming XML parser and stops after
MasterFiles has been processed, to avoid scanning the often huge
GeneralLedgerEntries section.

Output format matches the expectations in `trial_balance_reader.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd


@dataclass(frozen=True)
class SaftTrialBalanceRow:
    konto: str
    kontonavn: str
    ib: float
    ub: float
    netto: float


def _parse_amount(text: str | None) -> float:
    if text is None:
        return 0.0
    s = str(text).strip()
    if not s:
        return 0.0
    # SAF-T typically uses dot as decimal separator, but accept comma too.
    s = s.replace(" ", "")
    s = s.replace("\u00A0", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        # Last resort: extract number-ish substring
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _find_child_text(elem: ET.Element, tag_suffix: str) -> str | None:
    """Find first direct child whose tag ends with tag_suffix."""
    for child in list(elem):
        if child.tag.endswith(tag_suffix):
            return child.text
    return None


def _iter_general_ledger_accounts(xml_stream) -> list[SaftTrialBalanceRow]:
    rows: list[SaftTrialBalanceRow] = []

    # Stream parse; stop when MasterFiles ends.
    for event, elem in ET.iterparse(xml_stream, events=("end",)):
        tag = elem.tag

        if tag.endswith("GeneralLedgerAccount"):
            konto = (_find_child_text(elem, "AccountID") or "").strip()
            kontonavn = (_find_child_text(elem, "AccountDescription") or "").strip()

            # Balances (optional in some exports)
            od = _parse_amount(_find_child_text(elem, "OpeningDebitBalance"))
            oc = _parse_amount(_find_child_text(elem, "OpeningCreditBalance"))
            cd = _parse_amount(_find_child_text(elem, "ClosingDebitBalance"))
            cc = _parse_amount(_find_child_text(elem, "ClosingCreditBalance"))

            ib = od - oc
            ub = cd - cc
            netto = ub - ib

            if konto:
                rows.append(SaftTrialBalanceRow(konto=konto, kontonavn=kontonavn, ib=ib, ub=ub, netto=netto))

            elem.clear()

        elif tag.endswith("MasterFiles"):
            # We have finished scanning MasterFiles; accounts live here.
            break

    return rows


def extract_trial_balance_df_from_saft(saft_path: str | Path) -> pd.DataFrame:
    """Extract trial balance rows from a SAF-T (.zip or .xml) file.

    Returns a dataframe with columns: Konto, Kontonavn, IB, UB, Netto.
    """

    p = Path(saft_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            xml_candidates = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_candidates:
                raise ValueError("SAF-T zip contains no .xml file")

            # Prefer the largest xml file (common when zip contains schemas or other small xmls)
            xml_name = max(xml_candidates, key=lambda n: zf.getinfo(n).file_size)
            with zf.open(xml_name) as xml_stream:
                rows = _iter_general_ledger_accounts(xml_stream)
    else:
        # Assume plain xml
        with open(p, "rb") as xml_stream:
            rows = _iter_general_ledger_accounts(xml_stream)

    df = pd.DataFrame(
        [
            {
                "Konto": r.konto,
                "Kontonavn": r.kontonavn,
                "IB": r.ib,
                "UB": r.ub,
                "Netto": r.netto,
            }
            for r in rows
        ]
    )

    # Keep Konto as text to avoid Excel stripping leading zeros.
    if not df.empty:
        df["Konto"] = df["Konto"].astype(str)

    return df


def make_trial_balance_xlsx_from_saft(saft_path: str | Path, out_xlsx: str | Path) -> Path:
    """Create an .xlsx trial balance file derived from SAF-T."""

    df = extract_trial_balance_df_from_saft(saft_path)
    out = Path(out_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Always write a header, even if empty, for transparency.
    df.to_excel(out, index=False)
    return out
