"""Regex patterns used by the document extraction engine.

This module holds *only* compiled regular expressions and the small
string fragments that build them. It has no dependencies on other
``document_engine`` modules — making it safe to import from anywhere
without circular-import worries.

Conventions
-----------
* Patterns consumed by scoring / extraction logic are compiled once at
  import time (``re.compile``). Callers should never re-compile.
* Patterns that are *composed into other patterns* (e.g.
  ``_NUMBER_FRAGMENT``, ``_TEXT_MONTH_NAMES``) are kept as plain strings.
* Field-matching patterns are grouped as ``_XXX_PATTERNS`` lists. Order
  matters: the first match wins absent a higher rank from the scorer
  (see ``engine._collect_ranked_candidates``).

Grouped by concern
------------------
1. Amount building blocks (``_NUMBER_FRAGMENT``)
2. Company / supplier
3. Amount fields (total / subtotal / VAT)
4. Dates
5. Invoice-number, orgnr, currency
6. Descriptive text (description, period)
7. Invoice-page classification (positive / negative signals)
8. Bilagsprint detection
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# 1. Amount building blocks
# ---------------------------------------------------------------------------
#
# Matches amounts in multiple formats:
#   Norwegian: 1 990,00 | 1.990,00 | 1990,00
#   English:   1,990.00 | 1990.00
#   No decimals: 1990 | 1 990 | 1.990  (limited to 9 integer digits)
#   Negative:  -500,00
#
# Anchored with (?<!\d) so the match cannot start inside a longer digit run.
# The alternatives are ordered by specificity — grouped-thousands-with-decimal
# first, plain integer last — so findall prefers the most structured form.
# Previously the pattern was r"-?\d[\d\s., ]*\d" which is greedy and
# unbounded; it could eat 50-digit table columns as one amount (e.g. a
# Tripletex monthly-overview day header "1 2 3 4 ... 31") and produce
# nonsense captures like "123456789...465216.00" for total_amount.
_NUMBER_FRAGMENT = (
    r"(?<!\d)-?(?:"
    r"\d{1,3}(?:[  .]\d{3})+,\d{1,2}"       # 213 855,00 / 1.234,56
    r"|\d{1,3}(?:,\d{3})+\.\d{1,2}"              # 213,855.00
    r"|\d{1,3}(?:[  .]\d{3})+"              # 213 855 / 1.234 (no decimal)
    r"|\d{1,9},\d{1,2}"                          # 1234,56
    r"|\d{1,9}\.\d{1,2}"                         # 1234.56
    r"|\d{1,9}"                                  # 12345 (max 9 digits)
    r")"
)


# ---------------------------------------------------------------------------
# 2. Company / supplier
# ---------------------------------------------------------------------------

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:AS|ASA|ENK|AB|OY|LTD|LLC|INC|GMBH|BV|SA|SPA)\b",
    re.IGNORECASE,
)

# Supplier label patterns.
#
# NOTE: "fra" (Norwegian for "from") used to be included in the first pattern
# together with "leverandør"/"supplier", but it matched any occurrence of the
# word "fra" in ordinary prose (e.g. "trekk fra eget betalingskort"), which
# captured garbage text as the supplier name.  It is now pulled out into its
# own pattern which REQUIRES an explicit delimiter (":" or "-") AND must be at
# the start of a line, so it only matches label-like constructs such as
# "Fra: Lyse Tele AS".
_SUPPLIER_LABEL_PATTERNS = [
    re.compile(r"(?im)\b(?:leverand[øo]r|supplier)\b\s*[:\-]?\s*(.+)$"),
    re.compile(r"(?im)\b(?:selger|seller)\b\s*[:\-]?\s*(.+)$"),
    re.compile(r"(?im)^\s*fra\s*[:\-]\s*(.+)$"),
]


# ---------------------------------------------------------------------------
# 3. Amount fields (total / subtotal / VAT)
# ---------------------------------------------------------------------------

_AMOUNT_PATTERNS = [
    re.compile(
        rf"(?is)\b(?:"
        rf"totalt\s+[åa]\s+betale"
        rf"|sum\s+[åa]\s+betale"
        rf"|bel[øo]p\s+[åa]\s+betale"
        rf"|amount\s+due"
        rf"|invoice\s+total"
        rf"|total\s+amount"
        rf"|payable\s+amount"
        rf"|til\s+betaling"
        rf"|[åa]\s+betale"
        rf"|sluttsum"
        rf"|sluttbel[øo]p"
        rf"|totalbel[øo]p"
        rf"|brutto(?:bel[øo]p|sum)?"
        rf"|totalt\s+inkl(?:usive)?\.?\s*mva"
        rf"|sum\s+inkl(?:usive)?\.?\s*mva"
        rf"|grand\s+total"
        rf"|total\s+due"
        rf")\b[^0-9\-]{{0,80}}({_NUMBER_FRAGMENT})"
    ),
    # Secondary: bare ``brutto`` when followed by a currency code or colon/NOK.
    # Tight window (≤20 chars) so it cannot slurp unrelated nearby numbers.
    # Ranked below pattern 0 via pattern_index penalty.
    re.compile(
        rf"(?is)\bbrutto\b[^0-9\-]{{0,20}}"
        rf"(?:NOK|SEK|DKK|EUR|USD|GBP|:)?\s*({_NUMBER_FRAGMENT})"
    ),
    re.compile(rf"(?is)\b(?:sum|total)\b[^0-9\-]{{0,40}}({_NUMBER_FRAGMENT})"),
]

_SUBTOTAL_PATTERNS = [
    re.compile(
        rf"(?is)\b(?:"
        rf"sum\s+eks(?:l|kl)\.?\s*mva"
        rf"|(?:bel[øo]p|sum)\s+eks(?:k?l)?\.?\s*mva"
        rf"|eks(?:k?l)?\.?\s*mva"
        rf"|subtotal"
        rf"|sub\-?total"
        rf"|netto(?:bel[øo]p)?"
        rf"|net\s+amount"
        rf"|net\s+total"
        rf"|tax\s+exclusive\s+amount"
        rf"|mva[\s\-]?grunnlag"
        rf"|avgiftsgrunnlag"
        rf"|skattegrunnlag"
        rf"|ordrebel[øo]p"
        rf"|ordresum"
        rf")\b[^0-9\-]{{0,60}}({_NUMBER_FRAGMENT})"
    ),
]

_VAT_PATTERNS = [
    # Explicit "MVA beløp" / "merverdiavgift beløp" labels — strongest signal
    re.compile(
        rf"(?is)\b(?:"
        rf"totalt\s+mva\s*bel[øo]p"
        rf"|mva[\s\-]*bel[øo]p"
        rf"|merverdiavgift\s*bel[øo]p"
        rf"|herav\s+mva"
        rf"|herav\s+merverdiavgift"
        rf")\b[^0-9\-]{{0,60}}({_NUMBER_FRAGMENT})"
    ),
    # Specific VAT-amount labels — allow wider context
    re.compile(
        rf"(?is)\b(?:merverdiavgift|tax\s+amount|vat\s+amount|sales\s+tax)"
        rf"\b[^0-9\-]{{0,60}}({_NUMBER_FRAGMENT})"
    ),
    # "mva:" or "vat:" immediately followed by the amount (colon/space only)
    re.compile(rf"(?is)\b(?:mva|vat)\s*[:\-]\s*({_NUMBER_FRAGMENT})"),
    # Generic "mva"/"vat" — tight window to avoid grabbing table base amounts
    re.compile(rf"(?is)\b(?:mva|vat)\b[^0-9\-]{{0,12}}({_NUMBER_FRAGMENT})"),
]


# ---------------------------------------------------------------------------
# 4. Dates
# ---------------------------------------------------------------------------

_TEXT_MONTH_NAMES = (
    "januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember"
    "|january|february|march|may|june|july|october|december"
)

_DATE_PATTERNS = [
    re.compile(
        r"(?im)\b(?:fakturadato|invoice\s+date|invoice\s+dt|dato)\b"
        r"[^0-9]{0,20}(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"
    ),
    re.compile(
        r"(?im)\b(?:fakturadato|invoice\s+date|invoice\s+dt|dato)\b"
        r".{0,20}(\d{1,2}\.?\s*(?:" + _TEXT_MONTH_NAMES + r")\s+\d{4})",
        re.IGNORECASE,
    ),
]

_DUE_DATE_PATTERNS = [
    re.compile(
        r"(?im)\b(?:forfallsdato|forfall|due\s+date)\b"
        r"[^0-9]{0,20}(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"
    ),
    re.compile(
        r"(?im)\b(?:forfallsdato|forfall|due\s+date)\b"
        r".{0,20}(\d{1,2}\.?\s*(?:" + _TEXT_MONTH_NAMES + r")\s+\d{4})",
        re.IGNORECASE,
    ),
]


# ---------------------------------------------------------------------------
# 5. Invoice-number, orgnr, currency
# ---------------------------------------------------------------------------

_INVOICE_NUMBER_PATTERNS = [
    re.compile(
        r"(?im)\b(?:faktura\s*nr\.?|fakturanr\.?|fakturanummer|invoice\s*(?:no|number|nr)\.?|vår\s+referanse)\b"
        r"[^A-Z0-9]{0,10}((?=[A-Z0-9\-\/]*[0-9])[A-Z0-9][A-Z0-9\-\/]{2,})"
    ),
    re.compile(
        r"(?im)\binvoice\b(?!\s*(?:date|due|dt))[^A-Z0-9]{0,10}((?=[A-Z0-9\-\/]*[0-9])[A-Z0-9][A-Z0-9\-\/]{2,})"
    ),
]

_ORGNR_PATTERNS = [
    re.compile(
        r"(?im)\b(?:foretaksregisteret|company\s*registration|registration\s*no\.?)\b"
        r"[^0-9A-Z]{0,30}(?:NO\s*)?((?:\d\s*){9})\s*(?:MVA|VAT)?"
    ),
    re.compile(r"(?im)\b(?:NO\s*)?((?:\d\s*){9})\s*(?:MVA|VAT)\b"),
    re.compile(
        r"(?im)\b(?:org(?:anisajons)?\.?\s*nr\.?|org\.?\s*no\.?)\b"
        r"[^0-9]{0,10}((?:\d\s*){9})"
    ),
]

_CURRENCY_PATTERNS = [
    re.compile(r"(?im)\b(NOK|SEK|DKK|EUR|USD|GBP)\b"),
]


# ---------------------------------------------------------------------------
# 6. Descriptive text (description, period)
# ---------------------------------------------------------------------------

_DESCRIPTION_PATTERNS = [
    re.compile(
        r"(?im)\b(?:beskrivelse|description|spesifikasjon|specification|ytelse|tjeneste)\b"
        r"\s*[:\-]?\s*(.{5,120})$"
    ),
    re.compile(
        r"(?im)\b(?:vedr(?:ørende)?|gjelder|ang(?:ående)?|ref(?:eranse)?\.?)\b"
        r"\s*[:\-]?\s*(.{5,120})$"
    ),
]

_PERIOD_PATTERNS = [
    re.compile(
        r"(?im)\b(?:periode|period|kontraktsperiode|leieperiode|abonnementsperiode)\b"
        r"\s*[:\-]?\s*(.{4,60})$"
    ),
    re.compile(
        r"(?im)\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*(?:[-–]\s*|til\s+)\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
    ),
]


# ---------------------------------------------------------------------------
# 7. Invoice-page classification signals
# ---------------------------------------------------------------------------
#
# Raw-string patterns (not compiled). Consumers call ``re.search`` ad-hoc.
# Positive: words that strongly suggest a real vendor invoice page.
# Negative: words that mark a Tripletex accounting cover page.

_INVOICE_PAGE_POSITIVE_PATTERNS = (
    r"\binvoice\b",
    r"\bfaktura\b",
    r"\binvoice\s+date\b",
    r"\bdue\s+date\b",
    r"\binvoice\s+due\s+date\b",
    r"\bterms\s+of\s+payment\b",
    r"\border\s+number\b",
    r"\bcustomer\s+number\b",
    r"\bour\s+ref\b",
    r"\biban\b",
    r"\bswift\b",
    r"\bforetaksregisteret\b",
    r"\btotal\s+amount\b",
    r"\bamount\s+due\b",
    r"\bbank\s+account\b",
)

_INVOICE_PAGE_NEGATIVE_PATTERNS = (
    r"\bbilag\s+nummer\b",
    r"\bkonteringssammendrag\b",
    r"\bopprettet\b",
    r"\bsist\s+endret\b",
    r"\bbilagsgrunnlag\b",
    r"\bregnskapslinjer\b",
)


# ---------------------------------------------------------------------------
# 8. Bilagsprint detection
# ---------------------------------------------------------------------------
#
# Consumed by ``_tag_bilagsprint_pages`` and ``_is_bilagsprint_segment``.
# A page is classified as a Tripletex accounting cover ("bilagsprint")
# when its combined text carries BOTH a "bilag nummer <digits>" marker
# AND a kontering-summary signal.

_BILAGSPRINT_NR_RE = re.compile(r"bilag\s+nummer\s+\d")
_BILAGSPRINT_SIGNAL_RE = re.compile(
    r"konteringssammendrag|sum\s+debet|sum\s+kredit|kontostrengen"
)
