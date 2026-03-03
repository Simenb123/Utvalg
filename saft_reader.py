"""SAF-T (Financial) reader.

Dette er en best-effort parser for SAF-T Financial (Norsk SAF-T) som henter
ut en hovedbok-lignende tabell.

Mål:
- Gjøre det mulig å bruke SAF-T (.xml eller .zip) direkte i Utvalg.
- Returnere en pandas DataFrame med samme "kanoniske" kolonner som resten av appen.

Parseren er bevisst konservativ:
- Den prøver å finne vanlige feltnavn fra SAF-T (uavhengig av XML-namespace).
- Den bruker sign-konvensjon: DebitLine = +beløp, CreditLine = -beløp.

Denne modulen har ingen GUI-avhengigheter og kan testes isolert.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Optional
import xml.etree.ElementTree as ET

import pandas as pd

logger = logging.getLogger(__name__)


# Hold samme feltsett som resten av appen.
FALLBACK_CANON_FIELDS: list[str] = [
    "Konto",
    "Kontonavn",
    "Bilag",
    "Beløp",
    "Dato",
    "Tekst",
    "Kundenr",
    "Kundenavn",
    "Leverandørnr",
    "Leverandørnavn",
    "MVA-kode",
    "MVA-beløp",
    "MVA-prosent",
    "Valuta",
    "Valutabeløp",
]


def _canon_fields() -> list[str]:
    """Returner kanoniske felter fra ml_map_utils hvis tilgjengelig."""

    try:
        from ml_map_utils import canonical_fields

        fields = canonical_fields()
        if isinstance(fields, list) and fields:
            return fields
    except Exception:
        pass
    return FALLBACK_CANON_FIELDS


def is_saft_path(path: str | Path) -> bool:
    p = str(path).lower().strip()
    return p.endswith(".zip") or p.endswith(".xml")


@dataclass(frozen=True)
class _Lookup:
    accounts: dict[str, str]
    customers: dict[str, str]
    suppliers: dict[str, str]


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _txt(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    if elem.text is None:
        return ""
    return elem.text.strip()


def _safe_float(text: str) -> Optional[float]:
    """Parse float robust for SAF-T numeric fields."""

    t = (text or "").strip()
    if not t:
        return None
    # SAF-T bruker vanligvis punktum, men vi tåler komma.
    t = t.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def _open_saft_stream(path: Path) -> tuple[IO[bytes], str]:
    """Åpne SAF-T som bytes-stream.

    Returnerer (stream, display_name)

    NB: Når path er zip må ZipFile holdes åpen så lenge stream brukes.
    Vi løser dette ved å lese xml-fila til bytes i minnet (best effort).
    """

    if path.suffix.lower() == ".xml":
        return path.open("rb"), path.name

    if path.suffix.lower() != ".zip":
        raise ValueError(f"Ukjent SAF-T filtype: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        # Velg første .xml (preferer AuditFile) hvis flere.
        xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            raise ValueError("ZIP inneholder ingen .xml")

        def score(name: str) -> tuple[int, int]:
            low = name.lower()
            # AuditFile/AuditFile.xml får høy score
            prio = 0
            if "audit" in low:
                prio -= 10
            if "financial" in low:
                prio -= 5
            return (prio, -len(name))

        xml_names.sort(key=score)
        chosen = xml_names[0]
        data = zf.read(chosen)
        # Bruk BytesIO slik at vi kan lukke zip.
        import io

        return io.BytesIO(data), Path(chosen).name


def read_saft_ledger(path: str | Path) -> pd.DataFrame:
    """Les SAF-T (Financial) og returner DataFrame med kanoniske kolonner."""

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    stream, display = _open_saft_stream(p)
    try:
        df = _read_saft_stream(stream)
    finally:
        try:
            stream.close()
        except Exception:
            pass

    df.attrs["source"] = str(p)
    df.attrs["source_name"] = display
    return df


def _read_saft_stream(stream: IO[bytes]) -> pd.DataFrame:
    """Intern: les fra stream."""

    canon = _canon_fields()
    look = _Lookup(accounts={}, customers={}, suppliers={})
    rows: list[dict[str, Any]] = []

    # iterparse gir lavere minnebruk enn full parse.
    # Vi bruker kun 'end' events.
    try:
        context = ET.iterparse(stream, events=("end",))
    except Exception as e:
        raise ValueError(f"Kunne ikke lese XML: {e}")

    for _event, elem in context:
        tag = _local_name(elem.tag)

        if tag == "Account":
            acc_id = _txt(elem.find(".//{*}AccountID"))
            if acc_id:
                acc_name = _txt(elem.find(".//{*}AccountDescription")) or _txt(elem.find(".//{*}Description"))
                look.accounts.setdefault(acc_id, acc_name)
            elem.clear()
            continue

        if tag == "Customer":
            cid = _txt(elem.find(".//{*}CustomerID"))
            if cid:
                cname = (
                    _txt(elem.find(".//{*}CompanyName"))
                    or _txt(elem.find(".//{*}CustomerName"))
                    or _txt(elem.find(".//{*}Name"))
                )
                look.customers.setdefault(cid, cname)
            elem.clear()
            continue

        if tag == "Supplier":
            sid = _txt(elem.find(".//{*}SupplierID"))
            if sid:
                sname = (
                    _txt(elem.find(".//{*}CompanyName"))
                    or _txt(elem.find(".//{*}SupplierName"))
                    or _txt(elem.find(".//{*}Name"))
                )
                look.suppliers.setdefault(sid, sname)
            elem.clear()
            continue

        if tag == "Transaction":
            rows.extend(_parse_transaction(elem, look))
            elem.clear()
            continue

    if not rows:
        return pd.DataFrame(columns=canon)

    df = pd.DataFrame(rows)

    # Sørg for at alle kanoniske kolonner finnes.
    for col in canon:
        if col not in df.columns:
            df[col] = ""

    # Enkle typer
    if "Beløp" in df.columns:
        df["Beløp"] = pd.to_numeric(df["Beløp"], errors="coerce")

    if "Dato" in df.columns:
        # SAF-T TransactionDate er normalt ISO (YYYY-MM-DD).
        df["Dato"] = pd.to_datetime(df["Dato"], errors="coerce", dayfirst=False)

    # Konto/Bilag skal være str for konsistent oppførsel.
    for col in ("Konto", "Bilag"):
        if col in df.columns:
            df[col] = df[col].astype(str)

    return df[canon]


def _parse_transaction(trx: ET.Element, look: _Lookup) -> list[dict[str, Any]]:
    tid = (
        _txt(trx.find(".//{*}TransactionID"))
        or _txt(trx.find(".//{*}TransactionNo"))
        or _txt(trx.find(".//{*}SourceID"))
    )
    tdate = (
        _txt(trx.find(".//{*}TransactionDate"))
        or _txt(trx.find(".//{*}SystemEntryDate"))
        or _txt(trx.find(".//{*}Period"))
    )
    tdesc = _txt(trx.find(".//{*}Description")) or _txt(trx.find(".//{*}TransactionDescription"))

    out: list[dict[str, Any]] = []

    debit_lines = trx.findall(".//{*}DebitLine")
    credit_lines = trx.findall(".//{*}CreditLine")

    for line in debit_lines:
        row = _parse_line(line, sign=1, tid=tid, tdate=tdate, tdesc=tdesc, look=look)
        if row is not None:
            out.append(row)

    for line in credit_lines:
        row = _parse_line(line, sign=-1, tid=tid, tdate=tdate, tdesc=tdesc, look=look)
        if row is not None:
            out.append(row)

    # Fallback: Noen SAF-T eksportører bruker <Line> med DebitAmount/CreditAmount
    # (i stedet for DebitLine/CreditLine).
    if not debit_lines and not credit_lines:
        for line in trx.findall(".//{*}Line"):
            sign = 1
            if line.find(".//{*}CreditAmount") is not None or _txt(line.find(".//{*}CreditAmount/{*}Amount")):
                sign = -1
            elif line.find(".//{*}DebitAmount") is not None or _txt(line.find(".//{*}DebitAmount/{*}Amount")):
                sign = 1
            else:
                ind = (
                    _txt(line.find(".//{*}DebitCreditIndicator"))
                    or _txt(line.find(".//{*}DebitCreditCode"))
                    or ""
                ).strip().upper()
                if ind.startswith("C"):
                    sign = -1
            row = _parse_line(line, sign=sign, tid=tid, tdate=tdate, tdesc=tdesc, look=look)
            if row is not None:
                out.append(row)

    return out



def _parse_line(
    line: ET.Element,
    *,
    sign: int,
    tid: str,
    tdate: str,
    tdesc: str,
    look: _Lookup,
) -> Optional[dict[str, Any]]:
    acc = _txt(line.find(".//{*}AccountID"))
    if not acc:
        return None

    ldesc = _txt(line.find(".//{*}Description"))
    text = ldesc or tdesc

    # Amount
    if sign >= 0:
        amt_text = _txt(line.find(".//{*}DebitAmount/{*}Amount"))
        cur = _txt(line.find(".//{*}DebitAmount/{*}CurrencyCode"))
        cur_amt_text = _txt(line.find(".//{*}DebitAmount/{*}CurrencyAmount"))
    else:
        amt_text = _txt(line.find(".//{*}CreditAmount/{*}Amount"))
        cur = _txt(line.find(".//{*}CreditAmount/{*}CurrencyCode"))
        cur_amt_text = _txt(line.find(".//{*}CreditAmount/{*}CurrencyAmount"))

    amt = _safe_float(amt_text)
    belop = (amt * sign) if amt is not None else None

    cur_amt = _safe_float(cur_amt_text)

    # Customer/Supplier
    cust_id = _txt(line.find(".//{*}CustomerID"))
    supp_id = _txt(line.find(".//{*}SupplierID"))

    # Tax info (best effort)
    tax_code = _txt(line.find(".//{*}TaxInformation/{*}TaxCode")) or _txt(line.find(".//{*}TaxCode"))
    tax_pct = (
        _txt(line.find(".//{*}TaxInformation/{*}TaxPercentage"))
        or _txt(line.find(".//{*}TaxInformation/{*}TaxPercent"))
        or _txt(line.find(".//{*}TaxPercentage"))
    )
    tax_amt_text = _txt(line.find(".//{*}TaxInformation/{*}TaxAmount/{*}Amount")) or _txt(
        line.find(".//{*}TaxAmount/{*}Amount")
    )
    tax_amt = _safe_float(tax_amt_text)

    return {
        "Konto": acc,
        "Kontonavn": look.accounts.get(acc, ""),
        "Bilag": tid,
        "Beløp": belop,
        "Dato": tdate,
        "Tekst": text,
        "Kundenr": cust_id,
        "Kundenavn": look.customers.get(cust_id, "") if cust_id else "",
        "Leverandørnr": supp_id,
        "Leverandørnavn": look.suppliers.get(supp_id, "") if supp_id else "",
        "MVA-kode": tax_code,
        "MVA-beløp": tax_amt,
        "MVA-prosent": tax_pct,
        "Valuta": cur,
        "Valutabeløp": cur_amt,
    }
