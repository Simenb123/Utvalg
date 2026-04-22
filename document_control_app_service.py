from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import os
import re

import pandas as pd

from document_engine.engine import analyze_document as engine_analyze_document
from document_engine.engine import normalize_bilag_key
from document_engine.finder import build_search_terms, suggest_documents
from document_engine.format_utils import parse_amount_flexible
from document_engine.models import DocumentAnalysisResult, SupplierProfile, VoucherContext
from document_control_store import (
    LocalJsonProfileRepository,
    export_supplier_profiles as export_profiles_to_json,
    import_supplier_profiles as import_profiles_from_json,
    load_document_record,
    save_document_record,
)

try:
    import client_store

    _HAS_CLIENT_STORE = True
except Exception:
    client_store = None
    _HAS_CLIENT_STORE = False


TEXT_COLUMNS = ("Tekst", "Beskrivelse", "Dokumenttekst", "Bilagstekst", "Description")
DATE_COLUMNS = ("Dato", "Dokumentdato", "Bokf.dato", "InvoiceDate")
AMOUNT_COLUMNS = ("Beløp", "Belop", "Amount", "Netto", "SumBeløp", "SumBelop")
STOPWORDS = {
    "faktura",
    "invoice",
    "mva",
    "sum",
    "beløp",
    "belop",
    "betaling",
    "betalinger",
    "til",
    "fra",
    "med",
    "uten",
}


class LocalClientStoreDocumentSourceResolver:
    def resolve(self, *, client: str | None, year: str | None) -> list[tuple[Path, str]]:
        roots: list[tuple[Path, str]] = []
        if not _HAS_CLIENT_STORE or client_store is None:
            return roots

        client_name = (client or "").strip()
        year_text = (year or "").strip()
        if not client_name or not year_text:
            return roots

        try:
            year_root = client_store.years_dir(client_name, year=year_text)
            _append_root(roots, year_root, "årsmappe")
        except Exception:
            pass

        for dtype in ("hb", "sb"):
            try:
                version = client_store.get_active_version(client_name, year=year_text, dtype=dtype)
            except Exception:
                version = None
            if version is None:
                continue

            stored_path_text = str(getattr(version, "path", "") or "").strip()
            if stored_path_text:
                stored_path = Path(stored_path_text).expanduser()
                if stored_path.exists():
                    _append_root(roots, stored_path.parent, f"{dtype}-versjon")

            source_path_text = str(((getattr(version, "meta", {}) or {}).get("source_path") or "")).strip()
            if not source_path_text:
                continue
            source_path = Path(source_path_text).expanduser()
            if source_path.exists():
                _append_root(roots, source_path.parent, f"{dtype}-kilde")
                if source_path.parent.parent != source_path.parent:
                    _append_root(roots, source_path.parent.parent, f"{dtype}-kilde overordnet")
        return roots


def build_voucher_context(df_bilag: pd.DataFrame | None) -> VoucherContext | None:
    if df_bilag is None or df_bilag.empty:
        return None

    bilag = ""
    for column in ("Bilag", "Bilagsnr", "Voucher", "VoucherNo"):
        if column in df_bilag.columns and not df_bilag[column].empty:
            bilag = normalize_bilag_key(df_bilag[column].iloc[0])
            break

    texts: list[str] = []
    for column in TEXT_COLUMNS:
        if column in df_bilag.columns:
            texts.extend(_normalize_whitespace(value) for value in df_bilag[column].dropna().astype(str).tolist())

    dates: list[str] = []
    for column in DATE_COLUMNS:
        if column in df_bilag.columns:
            dates.extend(_normalize_date_text(str(value)) for value in df_bilag[column].dropna().tolist())

    amounts: list[float] = []
    for column in AMOUNT_COLUMNS:
        if column in df_bilag.columns:
            parsed = [_parse_amount(value) for value in df_bilag[column].tolist()]
            amounts = [value for value in parsed if value is not None]
            if amounts:
                break

    return VoucherContext(
        bilag=bilag,
        row_count=len(df_bilag),
        texts=[value for value in texts if value],
        dates=[value for value in dates if value],
        amounts=amounts,
        metadata={"columns": list(df_bilag.columns)},
    )


def analyze_document_for_bilag(
    file_path: str | Path,
    *,
    df_bilag: pd.DataFrame | None = None,
    repository: LocalJsonProfileRepository | None = None,
) -> DocumentAnalysisResult:
    repository = repository or LocalJsonProfileRepository()
    voucher_context = build_voucher_context(df_bilag)
    profiles = repository.load_profiles()
    return engine_analyze_document(file_path, voucher_context=voucher_context, profiles=profiles)


def suggest_documents_for_bilag(
    *,
    client: str | None,
    year: str | None,
    bilag: str,
    df_bilag: pd.DataFrame,
    resolver: LocalClientStoreDocumentSourceResolver | None = None,
) -> list[Any]:
    resolver = resolver or LocalClientStoreDocumentSourceResolver()
    search_roots = resolver.resolve(client=client, year=year)
    if not search_roots:
        return []

    raw_texts: list[str] = []
    for column in TEXT_COLUMNS:
        if column in df_bilag.columns:
            raw_texts.extend(str(value) for value in df_bilag[column].dropna().tolist())

    token_counter: dict[str, int] = {}
    numeric_tokens: dict[str, int] = {}
    for text in raw_texts:
        for token in re.findall(r"[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå0-9\-]{2,}", text):
            norm = token.strip().lower()
            if len(norm) < 4 or norm in STOPWORDS:
                continue
            token_counter[norm] = token_counter.get(norm, 0) + 1
        for token in re.findall(r"[A-Z0-9][A-Z0-9\-\/]{3,}", text.upper()):
            if len(re.sub(r"[^0-9]", "", token)) < 4:
                continue
            numeric_tokens[token.lower()] = numeric_tokens.get(token.lower(), 0) + 1

    years: set[str] = set()
    for column in DATE_COLUMNS:
        if column not in df_bilag.columns:
            continue
        for value in df_bilag[column].dropna().tolist():
            year_match = re.search(r"(20\d{2})", str(value))
            if year_match:
                years.add(year_match.group(1))

    terms = build_search_terms(
        voucher_identifiers=[str(bilag or "").strip()],
        text_tokens=[token for token, _count in sorted(token_counter.items(), key=lambda item: (-item[1], item[0]))[:10]],
        reference_tokens=[token for token, _count in sorted(numeric_tokens.items(), key=lambda item: (-item[1], item[0]))[:10]],
        date_hints=sorted(years),
    )
    return suggest_documents(search_roots, terms)


def save_document_review(
    *,
    client: str | None,
    year: str | None,
    bilag: str | None,
    file_path: str,
    field_values: dict[str, str],
    validation_messages: list[str],
    raw_text_excerpt: str,
    notes: str,
    analysis: DocumentAnalysisResult | None = None,
    segments: list[Any] | None = None,
    repository: LocalJsonProfileRepository | None = None,
    field_hit_indices: dict[str, int] | None = None,
    field_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a document review and update the supplier profile with learned hints.

    ``segments`` should be the TextSegment list from the PDF extraction — when
    provided, the profile learns page-level location hints for each confirmed
    field value (coordinate-based learning).

    ``field_hit_indices`` persists the user's chosen hit position per field
    (which occurrence in the PDF they selected).

    ``field_evidence`` carries the user's confirmed FieldEvidence objects
    (with page + bbox) so the profile can learn the exact position the user
    selected, rather than always picking the first match in the segments.
    """
    repository = repository or LocalJsonProfileRepository()

    payload: dict[str, Any] = {
        "file_path": file_path,
        "fields": {key: str(value or "").strip() for key, value in field_values.items()},
        "validation_messages": list(validation_messages or []),
        "raw_text_excerpt": raw_text_excerpt.strip(),
        "notes": notes.strip(),
    }
    if field_hit_indices:
        payload["field_hit_indices"] = {k: int(v) for k, v in field_hit_indices.items() if v is not None}

    # Save field_evidence (page+bbox coordinates) from dialog or analysis
    if field_evidence:
        evidence_payload: dict[str, Any] = {}
        for k, v in field_evidence.items():
            if hasattr(v, "to_dict"):
                evidence_payload[k] = v.to_dict()
            elif isinstance(v, dict):
                evidence_payload[k] = v
        if evidence_payload:
            payload["field_evidence"] = evidence_payload

    if analysis is not None:
        payload["analysis_metadata"] = dict(analysis.metadata or {})
        payload["analysis_source"] = analysis.source
        payload["profile_status"] = analysis.profile_status
        # Merge analysis evidence (don't overwrite dialog-provided evidence)
        if not payload.get("field_evidence"):
            payload["field_evidence"] = {
                field_name: evidence.to_dict()
                for field_name, evidence in (analysis.field_evidence or {}).items()
            }
        payload["confidence"] = analysis.confidence

    # ── Coordinate-based profile learning ────────────────────────────────
    # Re-extract hints using the actual PDF segments so that page numbers are
    # recorded alongside labels.  The segments are passed in from the dialog
    # which runs the analysis just before saving.
    effective_segments = segments
    if effective_segments is None and file_path:
        effective_segments = _load_segments_for_learning(file_path)

    updated_profile = _upsert_profile_with_hints(
        repository,
        payload["fields"],
        payload["raw_text_excerpt"],
        effective_segments,
        field_evidence=field_evidence,
    )
    if updated_profile is not None:
        payload["supplier_profile_key"] = updated_profile.profile_key
        payload["supplier_profile_samples"] = updated_profile.sample_count
        payload["profile_status"] = "updated"

    return save_document_record(client, year, bilag, payload)


def load_saved_review(client: str | None, year: str | None, bilag: str | None) -> dict[str, Any] | None:
    return load_document_record(client, year, bilag)


# ---------------------------------------------------------------------------
# Voucher PDF auto-lookup
# ---------------------------------------------------------------------------

def find_or_extract_bilag_document(
    bilag: str,
    *,
    client: str | None,
    year: str | None,
    extra_voucher_paths: list[str | Path] | None = None,
) -> Path | None:
    """Try to find the bilag document by scanning Tripletex voucher PDFs.

    1. Checks the voucher index/cache for bilag *bilag*.
    2. If found, extracts the relevant pages to a per-bilag PDF.
    3. Returns the path to the extracted PDF, or None if not found.
    """
    try:
        from document_control_voucher_index import find_and_extract_bilag

        return find_and_extract_bilag(
            bilag,
            client=client,
            year=year,
            extra_paths=extra_voucher_paths,
            use_cache=True,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Document status helpers (for status column in selection tables)
# ---------------------------------------------------------------------------

DOK_STATUS_NOT_LINKED = ""
DOK_STATUS_LINKED = "Koblet"
DOK_STATUS_OK = "OK"
DOK_STATUS_AVVIK = "Avvik"


def compute_document_status(record: dict[str, Any] | None) -> str:
    """Return a single status string for a document control record.

    Returns:
        ""        – no record or no linked file
        "Koblet"  – file linked but not yet analysed (no extracted fields)
        "OK"      – analysed, no validation messages
        "Avvik"   – analysed, has validation messages
    """
    if not record:
        return DOK_STATUS_NOT_LINKED
    file_path = str(record.get("file_path", "") or "").strip()
    if not file_path:
        return DOK_STATUS_NOT_LINKED

    fields = dict(record.get("fields", {}) or {})
    has_fields = any(str(value or "").strip() for value in fields.values())
    if not has_fields:
        return DOK_STATUS_LINKED

    messages = list(record.get("validation_messages", []) or [])
    if messages:
        return DOK_STATUS_AVVIK
    return DOK_STATUS_OK


def load_document_statuses(
    client: str | None,
    year: str | None,
    bilag_keys: list[str],
) -> dict[str, str]:
    """Return a dict mapping normalised bilag key → status string.

    Only bilag in *bilag_keys* are checked.  Keys not present in the store
    get an empty status string (not linked).
    """
    if not bilag_keys:
        return {}

    from document_control_store import load_document_store, record_key

    store = load_document_store()
    records = store.get("records", {})

    result: dict[str, str] = {}
    for bilag in bilag_keys:
        key = record_key(client, year, bilag)
        record = records.get(key)
        result[bilag] = compute_document_status(record)
    return result


def export_supplier_profiles(export_path: str | Path) -> dict[str, Any]:
    return export_profiles_to_json(export_path)


def import_supplier_profiles(import_path: str | Path, *, merge: bool = True) -> dict[str, Any]:
    return import_profiles_from_json(import_path, merge=merge)


def _load_segments_for_learning(file_path: str) -> list[Any] | None:
    """Extract text segments from *file_path* for profile hint learning.

    Returns None if extraction fails or the file is not a PDF.
    """
    try:
        from document_engine.engine import extract_text_from_file
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() != ".pdf":
            return None
        result = extract_text_from_file(path)
        return result.segments or None
    except Exception:
        return None


def _upsert_profile_with_hints(
    repository: LocalJsonProfileRepository,
    fields: dict[str, str],
    raw_text: str,
    segments: list[Any] | None,
    *,
    field_evidence: dict[str, Any] | None = None,
) -> Any:
    """Build/update supplier profile including page-level location hints."""
    from document_engine.profiles import (
        build_supplier_profile,
        infer_field_hints,
        profile_key_from_fields,
    )

    profile_key = profile_key_from_fields(fields)
    if not profile_key:
        return None

    existing = repository.load_profiles().get(profile_key)

    # Build base profile (name, orgnr, aliases, static fields)
    profile = build_supplier_profile(fields, raw_text, existing_profile=existing)
    if profile is None:
        return None

    # Re-run hint inference with segments (coordinate-aware).
    # Pass field_evidence so hints use the user's confirmed page+bbox
    # instead of always picking the first text match in segments.
    new_hints = infer_field_hints(
        raw_text, fields, segments=segments, field_evidence=field_evidence,
    )
    if new_hints:
        from document_engine.profiles import _merge_hint_entries
        merged = dict(profile.field_hints or {})
        for field_name, hint_list in new_hints.items():
            current = list(merged.get(field_name, []) or [])
            merged[field_name] = _merge_hint_entries(current, hint_list)
        profile.field_hints = merged

    return repository.save_profile(profile)


def _append_root(roots: list[tuple[Path, str]], path: Path, label: str) -> None:
    try:
        path = path.expanduser()
    except Exception:
        return
    if not path.exists() or not path.is_dir():
        return
    norm = os.path.normcase(os.path.normpath(str(path)))
    if any(os.path.normcase(os.path.normpath(str(existing))) == norm for existing, _label in roots):
        return
    roots.append((path, label))


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_date_text(value: str) -> str:
    text = _normalize_whitespace(value)
    # Strip time component (e.g. "2025.01.31 00:00:00", "2025-01-31T00:00:00+01:00")
    text = re.sub(r"[T ][\d:Z+\-]+$", "", text).strip()
    text = text.replace("/", ".").replace("-", ".")
    parts = text.split(".")
    if len(parts) != 3:
        return text
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        day_int = int(day)
        month_int = int(month)
        year_int = int(year)
    except Exception:
        return text
    return f"{day_int:02d}.{month_int:02d}.{year_int:04d}"


def _parse_amount(value: Any) -> float | None:
    return parse_amount_flexible(value)
