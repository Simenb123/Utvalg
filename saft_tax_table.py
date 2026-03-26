"""Ekstraher TaxTable (MVA-kodetabell) fra SAF-T-fil.

Streaming-parser som bare leser MasterFiles og stopper etterpå,
slik at den store GeneralLedgerEntries-seksjonen aldri lastes inn.

Mønsteret følger saft_trial_balance.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TaxCodeEntry:
    code: str
    description: str
    percentage: float
    standard_code: str  # StandardTaxCode fra SAF-T – tom streng om ikke tilgjengelig


def _parse_percentage(text: str | None) -> float:
    if text is None:
        return 0.0
    s = str(text).strip()
    if not s:
        return 0.0
    s = s.replace(" ", "").replace("\u00A0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _find_child_text(elem: ET.Element, tag_suffix: str) -> str | None:
    """Finn tekst for første barn-element som slutter med *tag_suffix*."""
    for child in list(elem):
        if child.tag.endswith(tag_suffix):
            return child.text
    return None


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _iter_tax_table(xml_stream) -> list[TaxCodeEntry]:
    entries: list[TaxCodeEntry] = []

    for event, elem in ET.iterparse(xml_stream, events=("end",)):
        local = _local_tag(elem.tag)

        if local == "TaxCodeDetails":
            code = (_find_child_text(elem, "TaxCode") or "").strip()
            if not code:
                elem.clear()
                continue

            description = (_find_child_text(elem, "Description") or "").strip()
            percentage = _parse_percentage(_find_child_text(elem, "TaxPercentage"))
            standard_code = (_find_child_text(elem, "StandardTaxCode") or "").strip()

            entries.append(TaxCodeEntry(
                code=code,
                description=description,
                percentage=percentage,
                standard_code=standard_code,
            ))
            elem.clear()

        elif local == "MasterFiles":
            # Alt vi trenger er i MasterFiles — stopp her.
            break

        elif local in ("GeneralLedgerAccounts", "Customers", "Suppliers",
                        "TaxTable", "AnalysisTypeTable"):
            elem.clear()

    return entries


def extract_tax_table(saft_path: str | Path) -> list[TaxCodeEntry]:
    """Ekstraher TaxTable fra en SAF-T-fil (.zip eller .xml).

    Returnerer liste med TaxCodeEntry.  Tom liste om filen ikke
    inneholder TaxTable.
    """
    p = Path(saft_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            xml_candidates = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_candidates:
                raise ValueError("SAF-T zip inneholder ingen .xml-fil")
            xml_name = max(xml_candidates, key=lambda n: zf.getinfo(n).file_size)
            with zf.open(xml_name) as xml_stream:
                return _iter_tax_table(xml_stream)
    else:
        with open(p, "rb") as xml_stream:
            return _iter_tax_table(xml_stream)
