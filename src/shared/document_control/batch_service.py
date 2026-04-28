"""document_control_batch_service

Batch document analysis: extract + analyse all bilag in a selection and
compare the extracted invoice data against the accounting entries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from document_control_app_service import (
    analyze_document_for_bilag,
    find_or_extract_bilag_document,
    save_document_review,
)
from document_engine.engine import normalize_bilag_key
from document_engine.format_utils import parse_amount_flexible


# ---------------------------------------------------------------------------
# Avvik classification
# ---------------------------------------------------------------------------

# Phrases that indicate a REAL discrepancy (not just an info message)
# Only flag genuine audit-relevant discrepancies: amount mismatches and
# date deviations.  Supplier name / invoice number not matching the
# accounting text is an extraction limitation, not a real audit finding.
_AVVIK_PHRASES = (
    "ble ikke direkte matchet",     # amount mismatch
    "avviker fra registrerte",      # date mismatch
    "Ingen bilagsrader",            # no data to control against
)


def _is_real_avvik(message: str) -> bool:
    return any(phrase in message for phrase in _AVVIK_PHRASES)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class BatchDocumentResult:
    bilag_nr: str
    status: str                         # "ok" | "avvik" | "ikke_funnet" | "feil"
    extracted_path: str = ""            # path to extracted sub-PDF, or ""
    supplier_name: str = ""             # from PDF
    invoice_number: str = ""            # from PDF
    invoice_date: str = ""              # from PDF
    invoice_total: float | None = None  # from PDF (total inkl. mva)
    accounting_net: float = 0.0         # algebraic sum of all accounting lines
    accounting_ref: float = 0.0         # best single-number reference amount (see _accounting_amounts)
    validation_messages: list[str] = field(default_factory=list)
    error_message: str = ""

    @property
    def amount_diff(self) -> float | None:
        """Difference: PDF total − accounting reference amount."""
        if self.invoice_total is None:
            return None
        return self.invoice_total - self.accounting_ref

    @property
    def status_label(self) -> str:
        labels = {
            "ok": "OK",
            "avvik": "Avvik",
            "ikke_funnet": "Ikke funnet",
            "feil": "Feil",
        }
        return labels.get(self.status, self.status)


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

_AMOUNT_COLS = ("Beløp", "Belop", "SumBeløp", "Amount", "Netto")


def run_batch_document_analysis(
    bilag_keys: list[str],
    *,
    client: str | None,
    year: str | None,
    df_all: pd.DataFrame,
    save_results: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[BatchDocumentResult]:
    """Extract and analyse every bilag in *bilag_keys*.

    Args:
        bilag_keys:  List of normalised bilag numbers to process.
        client:      Current client name.
        year:        Current year string.
        df_all:      Full accounting DataFrame (all bilag lines).
        save_results: If True, save each analysis result to the local store.
        progress_callback: Called as (current, total, bilag_nr) while running.

    Returns:
        List of BatchDocumentResult, one per bilag_nr.
    """
    total = len(bilag_keys)
    results: list[BatchDocumentResult] = []

    for idx, bilag_nr in enumerate(bilag_keys):
        if progress_callback:
            progress_callback(idx, total, bilag_nr)

        result = _process_one(bilag_nr, client=client, year=year, df_all=df_all, save=save_results)
        results.append(result)

    if progress_callback:
        progress_callback(total, total, "")

    return results


def _process_one(
    bilag_nr: str,
    *,
    client: str | None,
    year: str | None,
    df_all: pd.DataFrame,
    save: bool,
) -> BatchDocumentResult:
    """Process a single bilag: extract PDF, analyse, compute status."""
    bilag_key = normalize_bilag_key(bilag_nr)

    # Accounting figures for this bilag
    accounting_net, accounting_ref = _accounting_amounts(df_all, bilag_key)

    # Step 1: extract bilag PDF
    try:
        extracted_path = find_or_extract_bilag_document(
            bilag_key, client=client, year=year
        )
    except Exception as exc:
        return BatchDocumentResult(
            bilag_nr=bilag_nr,
            status="feil",
            accounting_net=accounting_net,
            accounting_ref=accounting_ref,
            error_message=str(exc),
        )

    if extracted_path is None:
        return BatchDocumentResult(
            bilag_nr=bilag_nr,
            status="ikke_funnet",
            accounting_net=accounting_net,
            accounting_ref=accounting_ref,
        )

    # Step 2: analyse extracted PDF
    df_bilag = _bilag_rows(df_all, bilag_key)
    try:
        analysis = analyze_document_for_bilag(extracted_path, df_bilag=df_bilag)
    except Exception as exc:
        return BatchDocumentResult(
            bilag_nr=bilag_nr,
            status="feil",
            extracted_path=str(extracted_path),
            accounting_net=accounting_net,
            accounting_ref=accounting_ref,
            error_message=str(exc),
        )

    # Step 3: extract key fields
    fields = analysis.fields or {}
    supplier_name = fields.get("supplier_name", "")
    invoice_number = fields.get("invoice_number", "")
    invoice_date = fields.get("invoice_date", "")
    invoice_total = _parse_amount(fields.get("total_amount", ""))

    # Step 4: determine status — only real discrepancies count as "avvik"
    all_msgs = list(analysis.validation_messages or [])
    msgs = [m for m in all_msgs if _is_real_avvik(m)]
    status = "avvik" if msgs else "ok"

    # Step 5: save
    if save:
        try:
            save_document_review(
                client=client,
                year=year,
                bilag=bilag_nr,
                file_path=str(extracted_path),
                field_values=fields,
                validation_messages=msgs,
                raw_text_excerpt=analysis.raw_text_excerpt or "",
                notes="",
                analysis=analysis,
            )
        except Exception:
            pass

    return BatchDocumentResult(
        bilag_nr=bilag_nr,
        status=status,
        extracted_path=str(extracted_path),
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        invoice_total=invoice_total,
        accounting_net=accounting_net,
        accounting_ref=accounting_ref,
        validation_messages=msgs,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bilag_rows(df: pd.DataFrame, bilag_key: str) -> pd.DataFrame:
    if df is None or df.empty or "Bilag" not in df.columns:
        return pd.DataFrame()
    mask = df["Bilag"].map(normalize_bilag_key) == bilag_key
    return df.loc[mask].copy()


def _accounting_amounts(df: pd.DataFrame, bilag_key: str) -> tuple[float, float]:
    """Return (accounting_net, accounting_reference) for a bilag.

    accounting_net       = algebraic sum of all lines.
    accounting_reference = invoice total (inkl. mva).

    Primary strategy — AP credit line (konto 2400-2499):
        The leverandørgjeld credit is always booked for exactly the full invoice
        amount, regardless of how many expense/periodisation lines there are.
        abs(sum of 2400 credits) is therefore the most reliable reference.

    Fallback (no Konto column or no AP lines):
        abs(net) when meaningfully non-zero, otherwise abs of largest single line.
    """
    rows = _bilag_rows(df, bilag_key)
    if rows.empty:
        return 0.0, 0.0
    amount_col = next((c for c in _AMOUNT_COLS if c in rows.columns), None)
    if amount_col is None:
        return 0.0, 0.0
    series = pd.to_numeric(rows[amount_col], errors="coerce").dropna()
    if series.empty:
        return 0.0, 0.0

    net = float(series.sum())

    # ── Primary: abs of AP credit (konto 2400-2499) ──────────────────────
    if "Konto" in rows.columns:
        ap_mask = rows["Konto"].astype(str).str.match(r"^24\d{2}$")
        if ap_mask.any():
            ap_vals = pd.to_numeric(rows.loc[ap_mask, amount_col], errors="coerce").dropna()
            # Normal supplier invoice: AP line is a credit (negative value)
            credits = ap_vals[ap_vals < 0]
            if not credits.empty:
                return net, float(credits.abs().sum())
            # Reversal: AP line is a debit (positive value)
            debits = ap_vals[ap_vals > 0]
            if not debits.empty:
                return net, float(debits.sum())

    # ── Fallback: use abs(net) or largest single line ─────────────────────
    abs_net = abs(net)
    if abs_net > 0.005:
        return net, abs_net
    # net ≈ 0 and no AP lines: use the largest absolute line value
    reference = float(series.abs().max()) if not series.empty else 0.0
    return net, reference


def _parse_amount(text: str) -> float | None:
    return parse_amount_flexible(text)
