"""SAF‑T → CSV importer for Utvalg.

This module lives inside the Utvalg repo so the GUI can accept a SAF‑T file
directly (typically a .zip), parse it, and cache a generated transactions CSV
that Utvalg can load as a normal dataset.

What gets produced
------------------
Only one CSV is produced: a SAF‑T-like ``transactions.csv`` with the same
columns used by the original SAFT parser project.

Why that format?
----------------
Utvalg already handles this format nicely via column mapping:
    - AccountID / AccountDescription
    - VoucherNo
    - Amount
    - TransactionDate
    - Description
    - CustomerID / SupplierID etc.

Performance / UX
----------------
Parsing can take time for large files, so we:
    - stream XML with iterparse
    - stream rows to CSV
    - cache results in a stable cache directory so repeated imports are fast
"""

from __future__ import annotations

import csv
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import IO, Any, Dict, Iterable, Iterator, Optional


try:
    # lxml is faster and more robust, but we also support stdlib ElementTree.
    from lxml import etree as ET  # type: ignore
except Exception:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore


# Bump this when the CSV extraction logic/format changes, to avoid reusing
# stale cached files created by older versions.
CACHE_FORMAT_VERSION = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_saft_file(path: str | os.PathLike[str]) -> bool:
    """Heuristic check for SAF‑T input (zip/xml)."""

    p = Path(path)
    if not p.exists() or not p.is_file():
        return False
    suf = p.suffix.lower()
    return suf in {".zip", ".xml", ".gz", ".gzip"}


def get_default_cache_dir() -> Path:
    """Return a user-writable cache directory.

    On Windows we prefer %LOCALAPPDATA%/Utvalg/saft_cache.
    Otherwise we fall back to the system temp dir.
    """

    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "Utvalg" / "saft_cache"
    return Path(tempfile.gettempdir()) / "utvalg_saft_cache"


def ensure_transactions_csv(
    saft_path: Path,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """Ensure that a parsed transactions CSV exists for ``saft_path``.

    Returns the cached CSV path.
    """

    saft_path = Path(saft_path)
    if cache_dir is None:
        cache_dir = get_default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    sig = _signature_for_path(saft_path)
    stem = _safe_stem(saft_path.stem)
    out_csv = cache_dir / f"transactions_{stem}_{sig}.csv"
    if out_csv.exists() and not force:
        return out_csv

    tmp_csv = out_csv.with_suffix(out_csv.suffix + ".tmp")
    if tmp_csv.exists():
        try:
            tmp_csv.unlink()
        except Exception:
            pass

    try:
        with _open_saft_xml(saft_path) as fh:
            _parse_saft_xml_to_csv(fh, tmp_csv)
        # Atomic-ish replace
        tmp_csv.replace(out_csv)
    finally:
        if tmp_csv.exists():
            # If parsing failed, clean up partial file.
            try:
                tmp_csv.unlink()
            except Exception:
                pass

    return out_csv


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _signature_for_path(p: Path) -> str:
    st = p.stat()
    h = sha1(
        f"{CACHE_FORMAT_VERSION}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8"),
        usedforsecurity=False,
    )
    return h.hexdigest()[:10]


def _safe_stem(stem: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    if len(s) > 60:
        s = s[:60]
    return s or "saft"


def _open_saft_xml(path: Path) -> IO[bytes]:
    """Return a binary file-handle for the SAF‑T XML.

    - If ``path`` is a zip, we open the largest .xml file inside.
    - If ``path`` is an xml, we open it directly.

    The caller is responsible for closing the returned handle.
    """

    path = Path(path)
    suf = path.suffix.lower()

    if suf == ".zip":
        zf = zipfile.ZipFile(path, "r")
        # Pick the largest XML in the archive.
        xml_members = [
            i
            for i in zf.infolist()
            if (not i.is_dir()) and i.filename.lower().endswith(".xml")
        ]
        if not xml_members:
            zf.close()
            raise FileNotFoundError("Fant ingen .xml-filer i SAF‑T zip.")
        best = max(xml_members, key=lambda i: i.file_size)
        fh = zf.open(best, "r")
        # Wrap to ensure zipfile handle lives as long as the file.
        return _ZipWrappedFile(zf, fh)

    # Plain XML
    return path.open("rb")


@dataclass
class _ZipWrappedFile:
    """Helper that closes the underlying ZipFile when the member is closed."""

    zf: zipfile.ZipFile
    fh: IO[bytes]

    def read(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return self.fh.read(*args, **kwargs)

    def close(self) -> None:
        try:
            self.fh.close()
        finally:
            self.zf.close()

    def __enter__(self) -> "_ZipWrappedFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __iter__(self):  # pragma: no cover
        return iter(self.fh)


def _lname(tag: str) -> str:
    """Local name (strip XML namespace)."""

    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _text(el) -> str:
    t = el.text
    if t is None:
        return ""
    return t.strip()


def _safe_float(x: str) -> float:
    if x is None:
        return 0.0
    s = str(x).strip().replace("\xa0", " ")
    # Remove regular spaces (often used as thousands separators)
    s = s.replace(" ", "")
    if not s:
        return 0.0
    # Handle Norwegian/European number formats.
    # If both separators are present, assume last separator is the decimal.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # 1.234,56 -> 1234.56
            s = s.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 -> 1234.56
            s = s.replace(",", "")
    elif s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


TRANSACTIONS_COLUMNS = [
    "RecordID",
    "VoucherID",
    "VoucherNo",
    "JournalID",
    "TransactionDate",
    "PostingDate",
    "DueDate",
    "DocumentNumber",
    "AccountID",
    "AccountDescription",
    "Description",
    "Debit",
    "Credit",
    "Amount",
    "CurrencyCode",
    "AmountCurrency",
    "CustomerID",
    "CustomerName",
    "SupplierID",
    "SupplierName",
    "TaxCode",
    "TaxPercentage",
    "TaxAmount",
    "Period",
    "Year",
    "SourceID",
    "SourceType",
    "SourceDescription",
    "ReferenceNo",
    "BatchID",
    "SystemEntryDate",
    "GL_Stats",
    "GL_Overview",
    "NS_Mapping",
    "AR_Recon",
    "AP_Recon",
]


def _parse_saft_xml_to_csv(xml_fh: IO[bytes], out_csv: Path) -> None:
    """Parse SAF‑T XML and write transactions CSV (streaming)."""

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    accounts: dict[str, str] = {}
    customers: dict[str, str] = {}
    suppliers: dict[str, str] = {}

    # Current context
    in_masterfiles = False
    in_gl_entries = False
    in_line = False
    path: list[str] = []  # tag stack (namespace-stripped)
    current_account: dict[str, str] | None = None
    current_customer: dict[str, str] | None = None
    current_supplier: dict[str, str] | None = None

    current_journal_id: str = ""
    current_voucher_id: str = ""
    current_voucher_no: str = ""
    current_transaction: dict[str, str] = {}
    current_line: dict[str, str] = {}
    record_id = 0

    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=TRANSACTIONS_COLUMNS, extrasaction="ignore")
        writer.writeheader()

        # ElementTree iterparse yields (event, elem)
        for event, elem in ET.iterparse(xml_fh, events=("start", "end")):
            tag = _lname(getattr(elem, "tag", ""))

            if event == "start":
                path.append(tag)
                if tag == "MasterFiles":
                    in_masterfiles = True
                elif tag == "GeneralLedgerEntries":
                    in_gl_entries = True

                if in_masterfiles:
                    if tag == "Account":
                        current_account = {}
                    elif tag == "Customer":
                        current_customer = {}
                    elif tag == "Supplier":
                        current_supplier = {}

                if in_gl_entries:
                    if tag == "Journal":
                        current_journal_id = ""
                    elif tag == "Transaction":
                        current_transaction = {}
                        current_voucher_id = ""
                        current_voucher_no = ""
                    elif tag == "Line":
                        current_line = {}
                        in_line = True

            else:  # end
                parent = path[-2] if len(path) >= 2 else ""
                txt = _text(elem)

                # SAF-T amounts are often wrapped like:
                #   <DebitAmount><Amount>123.45</Amount></DebitAmount>
                # In that case, the <DebitAmount> element itself only contains whitespace.
                # We therefore capture the nested <Amount> value using the parent tag context.
                if (
                    in_gl_entries
                    and in_line
                    and current_line is not None
                    and tag == "Amount"
                    and parent in {"DebitAmount", "CreditAmount", "DebitTaxAmount", "CreditTaxAmount"}
                ):
                    if current_line.get(parent) in (None, ""):
                        current_line[parent] = txt

                if in_masterfiles and current_account is not None:
                    if tag in {"AccountID", "AccountDescription"}:
                        current_account[tag] = txt
                    elif tag == "Account":
                        acc_id = current_account.get("AccountID", "")
                        if acc_id:
                            accounts[acc_id] = current_account.get("AccountDescription", "")
                        current_account = None

                if in_masterfiles and current_customer is not None:
                    if tag in {"CustomerID", "CustomerName"}:
                        current_customer[tag] = txt
                    elif tag == "Customer":
                        cid = current_customer.get("CustomerID", "")
                        if cid:
                            customers[cid] = current_customer.get("CustomerName", "")
                        current_customer = None

                if in_masterfiles and current_supplier is not None:
                    if tag in {"SupplierID", "SupplierName"}:
                        current_supplier[tag] = txt
                    elif tag == "Supplier":
                        sid = current_supplier.get("SupplierID", "")
                        if sid:
                            suppliers[sid] = current_supplier.get("SupplierName", "")
                        current_supplier = None

                if tag == "MasterFiles":
                    in_masterfiles = False

                # General Ledger Entries parsing
                if in_gl_entries:
                    if tag == "JournalID":
                        current_journal_id = txt

                    # Transaction-level fields
                    if tag in {
                        "TransactionID",
                        "TransactionDate",
                        "PostingDate",
                        "DueDate",
                        "Period",
                        "Year",
                        "SystemEntryDate",
                    }:
                        current_transaction[tag] = txt
                        if tag == "TransactionID":
                            current_voucher_id = txt
                            current_voucher_no = txt

                    # Norwegian SAF-T often uses GLPostingDate instead of PostingDate.
                    if tag == "GLPostingDate":
                        current_transaction["PostingDate"] = txt

                    # DocumentNumber can be under SourceDocumentID/InvoiceNo etc in some files.
                    if tag == "DocumentNumber":
                        current_transaction["DocumentNumber"] = txt

                    # Line-level fields
                    line_fields = {
                        "RecordID",
                        "AccountID",
                        "Description",
                        "DebitAmount",
                        "CreditAmount",
                        "TaxCode",
                        "TaxPercentage",
                        "TaxBase",
                        "TaxAmount",
                        "DebitTaxAmount",
                        "CreditTaxAmount",
                        "CurrencyCode",
                        "AmountCurrency",
                        "CustomerID",
                        "SupplierID",
                        "SourceID",
                        "SourceType",
                        "SourceDescription",
                        "ReferenceNo",
                        "BatchID",
                    }
                    amount_container_tags = {
                        "DebitAmount",
                        "CreditAmount",
                        "DebitTaxAmount",
                        "CreditTaxAmount",
                        "TaxAmount",
                        "AmountCurrency",
                    }

                    if tag in line_fields:
                        # Don't clobber values captured from nested <Amount> with empty whitespace text.
                        if tag in amount_container_tags and not txt:
                            current_line.setdefault(tag, current_line.get(tag, ""))
                        else:
                            current_line[tag] = txt

                    if tag == "Line":
                        record_id += 1
                        in_line = False

                        debit = _safe_float(current_line.get("DebitAmount", ""))
                        credit = _safe_float(current_line.get("CreditAmount", ""))
                        amount = debit - credit

                        # Tax amount can be split into DebitTaxAmount/CreditTaxAmount.
                        tax_amount: Any = current_line.get("TaxAmount", "")
                        if current_line.get("DebitTaxAmount") or current_line.get("CreditTaxAmount"):
                            tax_amount = _safe_float(current_line.get("DebitTaxAmount", "")) - _safe_float(
                                current_line.get("CreditTaxAmount", "")
                            )

                        acc_id = current_line.get("AccountID", "")
                        acc_desc = accounts.get(acc_id, "")

                        cust_id = current_line.get("CustomerID", "")
                        supp_id = current_line.get("SupplierID", "")

                        tx_date = current_transaction.get("TransactionDate", "")
                        posting_date = current_transaction.get("PostingDate", "") or tx_date

                        row: Dict[str, Any] = {c: "" for c in TRANSACTIONS_COLUMNS}
                        row.update(
                            {
                                "RecordID": record_id,
                                "VoucherID": current_voucher_id,
                                "VoucherNo": current_voucher_no,
                                "JournalID": current_journal_id,
                                "TransactionDate": tx_date,
                                "PostingDate": posting_date,
                                "DueDate": current_transaction.get("DueDate", ""),
                                "DocumentNumber": current_transaction.get("DocumentNumber", ""),
                                "AccountID": acc_id,
                                "AccountDescription": acc_desc,
                                "Description": current_line.get("Description", ""),
                                "Debit": debit,
                                "Credit": credit,
                                "Amount": amount,
                                "CurrencyCode": current_line.get("CurrencyCode", ""),
                                "AmountCurrency": current_line.get("AmountCurrency", ""),
                                "CustomerID": cust_id,
                                "CustomerName": customers.get(cust_id, ""),
                                "SupplierID": supp_id,
                                "SupplierName": suppliers.get(supp_id, ""),
                                "TaxCode": current_line.get("TaxCode", ""),
                                "TaxPercentage": current_line.get("TaxPercentage", ""),
                                "TaxAmount": tax_amount,
                                "Period": current_transaction.get("Period", ""),
                                "Year": current_transaction.get("Year", ""),
                                "SourceID": current_line.get("SourceID", ""),
                                "SourceType": current_line.get("SourceType", ""),
                                "SourceDescription": current_line.get("SourceDescription", ""),
                                "ReferenceNo": current_line.get("ReferenceNo", ""),
                                "BatchID": current_line.get("BatchID", ""),
                                "SystemEntryDate": current_transaction.get("SystemEntryDate", ""),
                            }
                        )
                        writer.writerow(row)

                        current_line = {}
                        in_line = False

                    elif tag == "Transaction":
                        current_transaction = {}
                        current_voucher_id = ""
                        current_voucher_no = ""

                if tag == "GeneralLedgerEntries":
                    in_gl_entries = False

                # Pop tag stack (paired with push on "start")
                if path:
                    path.pop()

                # Memory cleanup for lxml to keep RAM stable.
                try:
                    elem.clear()  # type: ignore[attr-defined]
                    while elem.getprevious() is not None:  # type: ignore[attr-defined]
                        del elem.getparent()[0]  # type: ignore[attr-defined]
                except Exception:
                    # stdlib ElementTree doesn't have getprevious/getparent
                    pass

