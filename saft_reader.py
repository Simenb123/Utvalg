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
# Øk denne når saft_reader legger til nye felter, slik at SQLite-cachen
# invalideres automatisk og SAF-T-filer reparseres med ny kode.
READER_VERSION = "2"  # BalanceAccount IB/UB + RegistrationNumber + TaxRegistrationNumber

FALLBACK_CANON_FIELDS: list[str] = [
    "Konto",
    "Kontonavn",
    "Bilag",
    "Referanse",
    "Beløp",
    "Dato",
    "Tekst",
    "Kundenr",
    "Kundenavn",
    "Kundeorgnr",
    "KundeIB",
    "KundeUB",
    "KundeKonto",
    "KundeMvaReg",
    "Leverandørnr",
    "Leverandørnavn",
    "Leverandørorgnr",
    "LeverandørIB",
    "LeverandørUB",
    "LeverandørKonto",
    "LeverandørMvaReg",
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
    customer_orgnr: dict[str, str]        # CustomerID → RegistrationNumber (orgnr)
    supplier_orgnr: dict[str, str]        # SupplierID  → RegistrationNumber (orgnr)
    customer_ib: dict[str, float]         # CustomerID → IB (OpeningDebit - OpeningCredit)
    customer_ub: dict[str, float]         # CustomerID → UB (ClosingDebit - ClosingCredit)
    customer_balance_acct: dict[str, str] # CustomerID → BalanceAccount AccountID
    customer_tax_reg: dict[str, str]      # CustomerID → TaxRegistrationNumber
    supplier_ib: dict[str, float]
    supplier_ub: dict[str, float]
    supplier_balance_acct: dict[str, str]
    supplier_tax_reg: dict[str, str]


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


@dataclass(frozen=True)
class SaftHeader:
    """Metadata fra SAF-T Header."""
    software_company: str = ""
    software_id: str = ""
    software_version: str = ""


def read_saft_header(path: str | Path) -> SaftHeader:
    """Les SAF-T Header og returner programvareinformasjon.

    Streamer XML-en og stopper så snart Header er funnet, slik at vi
    ikke trenger å parse hele filen.
    """
    p = Path(path)
    if not p.exists():
        return SaftHeader()

    try:
        stream, _display = _open_saft_stream(p)
    except Exception:
        return SaftHeader()

    try:
        return _read_header_from_stream(stream)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _read_header_from_stream(stream: IO[bytes]) -> SaftHeader:
    """Intern: les Header-elementer fra XML-stream."""
    try:
        context = ET.iterparse(stream, events=("end",))
    except Exception:
        return SaftHeader()

    software_company = ""
    software_id = ""
    software_version = ""

    for _event, elem in context:
        tag = _local_name(elem.tag)

        if tag == "SoftwareCompanyName":
            software_company = _txt(elem)
        elif tag == "SoftwareID":
            software_id = _txt(elem)
        elif tag == "SoftwareVersion":
            software_version = _txt(elem)
        elif tag == "Header":
            # Vi har hele headeren — ingen grunn til å lese resten.
            elem.clear()
            break

        # Dersom vi treffer MasterFiles/GeneralLedgerEntries betyr det
        # at Header allerede er passert (eller ikke finnes).
        if tag in ("MasterFiles", "GeneralLedgerEntries"):
            elem.clear()
            break

    return SaftHeader(
        software_company=software_company,
        software_id=software_id,
        software_version=software_version,
    )


def detect_accounting_system(header: SaftHeader) -> str:
    """Forsøk å matche SAF-T header mot kjente regnskapssystemer.

    Returnerer systemnavnet fra ACCOUNTING_SYSTEMS-listen, eller tom streng
    dersom ingen match.
    """
    from mva_codes import ACCOUNTING_SYSTEMS

    # Bygg en søkestreng fra header-feltene
    search = f"{header.software_company} {header.software_id}".lower()
    if not search.strip():
        return ""

    # Prøv direkte match mot kjente systemer (case-insensitive)
    for system in ACCOUNTING_SYSTEMS:
        if system == "Annet" or system == "SAF-T Standard":
            continue
        if system.lower() in search:
            return system

    # Noen systemer bruker varianter i SAF-T-eksporten
    _ALIASES: dict[str, str] = {
        "tripletex": "Tripletex",
        "poweroffice": "PowerOffice GO",
        "xledger": "Xledger",
        "visma business": "Visma Business",
        "visma eaccounting": "Visma eAccounting",
        "visma global": "Visma Business",
        "fiken": "Fiken",
        "uni economy": "Uni Economy",
        "uni micro": "Uni Economy",
        "24sevenoffice": "24SevenOffice",
        "24seven": "24SevenOffice",
    }
    for alias, system in _ALIASES.items():
        if alias in search:
            return system

    return ""


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
    look = _Lookup(
        accounts={}, customers={}, suppliers={},
        customer_orgnr={}, supplier_orgnr={},
        customer_ib={}, customer_ub={},
        customer_balance_acct={}, customer_tax_reg={},
        supplier_ib={}, supplier_ub={},
        supplier_balance_acct={}, supplier_tax_reg={},
    )
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
                corgnr = _txt(elem.find(".//{*}RegistrationNumber"))
                if corgnr:
                    look.customer_orgnr.setdefault(cid, corgnr)
                # IB / UB fra BalanceAccount
                ba = elem.find(".//{*}BalanceAccount")
                if ba is not None:
                    look.customer_balance_acct.setdefault(
                        cid, _txt(ba.find(".//{*}AccountID")))
                    od = _safe_float(_txt(ba.find(".//{*}OpeningDebitBalance")))  or 0.0
                    oc = _safe_float(_txt(ba.find(".//{*}OpeningCreditBalance"))) or 0.0
                    cd = _safe_float(_txt(ba.find(".//{*}ClosingDebitBalance")))  or 0.0
                    cc = _safe_float(_txt(ba.find(".//{*}ClosingCreditBalance"))) or 0.0
                    look.customer_ib.setdefault(cid, od - oc)
                    look.customer_ub.setdefault(cid, cd - cc)
                # MVA-registrering direkte fra SAF-T
                tax_reg = _txt(elem.find(".//{*}TaxRegistrationNumber"))
                if tax_reg:
                    look.customer_tax_reg.setdefault(cid, tax_reg)
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
                sorgnr = _txt(elem.find(".//{*}RegistrationNumber"))
                if sorgnr:
                    look.supplier_orgnr.setdefault(sid, sorgnr)
                # IB / UB fra BalanceAccount
                ba = elem.find(".//{*}BalanceAccount")
                if ba is not None:
                    look.supplier_balance_acct.setdefault(
                        sid, _txt(ba.find(".//{*}AccountID")))
                    od = _safe_float(_txt(ba.find(".//{*}OpeningDebitBalance")))  or 0.0
                    oc = _safe_float(_txt(ba.find(".//{*}OpeningCreditBalance"))) or 0.0
                    cd = _safe_float(_txt(ba.find(".//{*}ClosingDebitBalance")))  or 0.0
                    cc = _safe_float(_txt(ba.find(".//{*}ClosingCreditBalance"))) or 0.0
                    look.supplier_ib.setdefault(sid, od - oc)
                    look.supplier_ub.setdefault(sid, cd - cc)
                # MVA-registrering direkte fra SAF-T
                tax_reg = _txt(elem.find(".//{*}TaxRegistrationNumber"))
                if tax_reg:
                    look.supplier_tax_reg.setdefault(sid, tax_reg)
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
    for col in ("Konto", "Bilag", "Referanse"):
        if col in df.columns:
            df[col] = df[col].astype(str)

    extras = [col for col in df.columns if col not in canon]
    return df[canon + extras]


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
    tref = (
        _txt(trx.find(".//{*}ReferenceNumber"))
        or _txt(trx.find(".//{*}DocumentNumber"))
        or _txt(trx.find(".//{*}DocumentNo"))
    )

    out: list[dict[str, Any]] = []

    debit_lines = trx.findall(".//{*}DebitLine")
    credit_lines = trx.findall(".//{*}CreditLine")

    for line in debit_lines:
        row = _parse_line(line, sign=1, tid=tid, tdate=tdate, tdesc=tdesc, look=look)
        if row is not None:
            if not row.get("Referanse"):
                row["Referanse"] = tref
            out.append(row)

    for line in credit_lines:
        row = _parse_line(line, sign=-1, tid=tid, tdate=tdate, tdesc=tdesc, look=look)
        if row is not None:
            if not row.get("Referanse"):
                row["Referanse"] = tref
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
                if not row.get("Referanse"):
                    row["Referanse"] = tref
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
    reference = (
        _txt(line.find(".//{*}ReferenceNumber"))
        or _txt(line.find(".//{*}DocumentNumber"))
        or _txt(line.find(".//{*}DocumentNo"))
    )

    _NaN = float("nan")
    return {
        "Konto":          acc,
        "Kontonavn":      look.accounts.get(acc, ""),
        "Bilag":          tid,
        "Referanse":      reference,
        "Beløp":          belop,
        "Dato":           tdate,
        "Tekst":          text,
        "Kundenr":        cust_id,
        "Kundenavn":      look.customers.get(cust_id, "")    if cust_id else "",
        "Kundeorgnr":     look.customer_orgnr.get(cust_id, "") if cust_id else "",
        "KundeIB":        look.customer_ib.get(cust_id, _NaN) if cust_id else _NaN,
        "KundeUB":        look.customer_ub.get(cust_id, _NaN) if cust_id else _NaN,
        "KundeKonto":     look.customer_balance_acct.get(cust_id, "") if cust_id else "",
        "KundeMvaReg":    "MVA" in look.customer_tax_reg.get(cust_id, "") if cust_id else False,
        "Leverandørnr":   supp_id,
        "Leverandørnavn": look.suppliers.get(supp_id, "")    if supp_id else "",
        "Leverandørorgnr": look.supplier_orgnr.get(supp_id, "") if supp_id else "",
        "LeverandørIB":   look.supplier_ib.get(supp_id, _NaN) if supp_id else _NaN,
        "LeverandørUB":   look.supplier_ub.get(supp_id, _NaN) if supp_id else _NaN,
        "LeverandørKonto": look.supplier_balance_acct.get(supp_id, "") if supp_id else "",
        "LeverandørMvaReg": "MVA" in look.supplier_tax_reg.get(supp_id, "") if supp_id else False,
        "MVA-kode":       tax_code,
        "MVA-beløp":      tax_amt,
        "MVA-prosent":    tax_pct,
        "Valuta":         cur,
        "Valutabeløp":    cur_amt,
    }
