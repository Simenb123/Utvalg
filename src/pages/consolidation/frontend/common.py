"""Shared pure helpers for the consolidation page modules."""

from __future__ import annotations

import pandas as pd

from ..backend.models import AssociateCase
from src.shared.ui.managed_treeview import ColumnSpec

SOURCE_LABELS = {
    "excel": "TB-fil",
    "csv": "TB-fil",
    "saft": "SAF-T TB",
    "session": "Session TB",
    "session-sb": "SAF-T SB",
    "client_store_sb": "Klientliste SB",
    "rl_excel": "Regnskapslinjer",
    "rl_csv": "Regnskapslinjer",
    "pdf_regnskap": "PDF-regnskap",
}
SOURCE_TYPES_WITH_IB_HINT = {
    "excel",
    "csv",
    "saft",
    "session",
    "session-sb",
    "client_store_sb",
}

DETAIL_TB_COLUMN_SPECS = [
    ColumnSpec("konto", "Konto", width=80, pinned=True),
    ColumnSpec("kontonavn", "Kontonavn", width=140, stretch=True),
    ColumnSpec("regnr", "Regnr", width=55, anchor="e"),
    ColumnSpec("rl_navn", "Regnskapslinje", width=150, stretch=True),
    ColumnSpec("ib", "IB", width=80, anchor="e"),
    ColumnSpec("netto", "Bevegelse", width=80, anchor="e"),
    ColumnSpec("ub", "UB", width=80, anchor="e"),
]

DETAIL_LINE_COLUMN_SPECS = [
    ColumnSpec("regnr", "Regnr", width=60, pinned=True, anchor="e"),
    ColumnSpec("rl_navn", "Regnskapslinje", width=170, pinned=True, stretch=True),
    ColumnSpec("source_rl", "Kildelinje", width=180, stretch=True),
    ColumnSpec("ub", "UB", width=90, anchor="e"),
    ColumnSpec("source_page", "Side", width=55, anchor="e"),
    ColumnSpec("status", "Status", width=90),
    ColumnSpec("confidence", "Treff", width=70, anchor="e"),
]

MAPPING_REVIEW_KEYWORDS = (
    "dispon",
    "disposition",
    "dividend",
    "udbytte",
    "utbytte",
    "egenkap",
    "equity",
    "aarets resultat",
    "arets resultat",
)


def reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def source_display(source_type: str, has_ib: bool) -> str:
    label = SOURCE_LABELS.get(source_type, source_type or "ukjent")
    if source_type in SOURCE_TYPES_WITH_IB_HINT and not has_ib:
        label += " (kun netto)"
    return label


def fmt_no(value: float, decimals: int = 0) -> str:
    if abs(value) < 0.005 and decimals == 0:
        return "0"
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}" if decimals > 0 else f"{round(abs(value)):,}"
    formatted = formatted.replace(",", " ").replace(".", ",")
    return sign + formatted


def normalize_mapping_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return (
        text.replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
        .replace("Ã¦", "ae")
        .replace("Ã¸", "oe")
        .replace("Ã¥", "aa")
        .replace("Ã£Â¦", "ae")
        .replace("Ã£Â¸", "oe")
        .replace("Ã£Â¥", "aa")
    )


def is_line_basis_company(company: object | None) -> bool:
    if company is None:
        return False
    return str(getattr(company, "basis_type", "tb") or "tb").strip().lower() == "regnskapslinje"


def format_count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if int(count) == 1 else plural}"


def format_filtered_count_label(shown: int, total: int, singular: str, plural: str) -> str:
    noun = singular if int(total) == 1 else plural
    return f"{shown}/{total} {noun} (0-linjer skjult)"


def format_company_row_count(company: object | None) -> str:
    count = int(getattr(company, "row_count", 0) or 0) if company is not None else 0
    if is_line_basis_company(company):
        return format_count_label(count, "linje", "linjer")
    return format_count_label(count, "konto", "kontoer")


def build_detail_meta_text(company: object | None, basis: pd.DataFrame | None = None) -> str:
    if company is None:
        return ""
    source_label = source_display(
        str(getattr(company, "source_type", "") or ""),
        bool(getattr(company, "has_ib", False)),
    )
    count = int(len(basis.index)) if isinstance(basis, pd.DataFrame) else int(getattr(company, "row_count", 0) or 0)
    if is_line_basis_company(company):
        parts = ["Regnskapslinje-grunnlag", source_label, format_count_label(count, "linje", "linjer")]
        if isinstance(basis, pd.DataFrame) and "review_status" in basis.columns:
            try:
                statuses = basis["review_status"].fillna("").astype(str).str.strip().str.lower()
                approved = int((statuses == "approved").sum())
            except Exception:
                approved = 0
            if approved > 0:
                parts.append(f"{approved} godkjent")
        return " | ".join(parts)
    return " | ".join(["TB-grunnlag", source_label, format_count_label(count, "konto", "kontoer")])


def normalize_entity_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def associate_case_status_label(
    case: AssociateCase | None,
    *,
    has_duplicate_company: bool = False,
) -> str:
    if case is None:
        return "Ingen sak valgt"
    if has_duplicate_company:
        return "Konflikt"
    status = str(getattr(case, "status", "") or "draft").strip().lower()
    if status == "generated":
        return "Klar"
    if status == "stale":
        return "Oppdater"
    return "Utkast"


def detect_mapping_review_accounts(
    mapped_df: pd.DataFrame,
    regnr_to_name: dict[int, str],
) -> tuple[set[str], list[str]]:
    review_accounts: set[str] = set()
    review_details: list[str] = []
    if mapped_df is None or mapped_df.empty:
        return review_accounts, review_details
    for _, row in mapped_df.iterrows():
        regnr_raw = row.get("regnr")
        try:
            regnr = int(regnr_raw) if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan") else None
        except (TypeError, ValueError):
            regnr = None
        if regnr is None or regnr >= 295:
            continue
        konto = str(row.get("konto", "") or "").strip()
        kontonavn = str(row.get("kontonavn", "") or "").strip()
        if not konto:
            continue
        ib = pd.to_numeric(pd.Series([row.get("ib", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        ub = pd.to_numeric(pd.Series([row.get("ub", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        netto = pd.to_numeric(pd.Series([row.get("netto", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        if abs(float(ib)) <= 0.005 and abs(float(ub)) <= 0.005 and abs(float(netto)) <= 0.005:
            continue
        if not any(keyword in normalize_mapping_text(kontonavn) for keyword in MAPPING_REVIEW_KEYWORDS):
            continue
        review_accounts.add(konto)
        rl_name = str(row.get("regnskapslinje", "") or regnr_to_name.get(regnr, "") or "")
        review_details.append(f"{konto} {kontonavn} -> {regnr} {rl_name}".strip())
    return review_accounts, review_details
