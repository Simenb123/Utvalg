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
    repository: LocalJsonProfileRepository | None = None,
) -> dict[str, Any]:
    repository = repository or LocalJsonProfileRepository()

    payload: dict[str, Any] = {
        "file_path": file_path,
        "fields": {key: str(value or "").strip() for key, value in field_values.items()},
        "validation_messages": list(validation_messages or []),
        "raw_text_excerpt": raw_text_excerpt.strip(),
        "notes": notes.strip(),
    }
    if analysis is not None:
        payload["analysis_metadata"] = dict(analysis.metadata or {})
        payload["analysis_source"] = analysis.source
        payload["profile_status"] = analysis.profile_status
        payload["field_evidence"] = {
            field_name: evidence.to_dict()
            for field_name, evidence in (analysis.field_evidence or {}).items()
        }
        payload["confidence"] = analysis.confidence

    updated_profile = repository.upsert_from_document(payload["fields"], payload["raw_text_excerpt"])
    if updated_profile is not None:
        payload["supplier_profile_key"] = updated_profile.profile_key
        payload["supplier_profile_samples"] = updated_profile.sample_count
        payload["profile_status"] = "updated"

    return save_document_record(client, year, bilag, payload)


def load_saved_review(client: str | None, year: str | None, bilag: str | None) -> dict[str, Any] | None:
    return load_document_record(client, year, bilag)


def export_supplier_profiles(export_path: str | Path) -> dict[str, Any]:
    return export_profiles_to_json(export_path)


def import_supplier_profiles(import_path: str | Path, *, merge: bool = True) -> dict[str, Any]:
    return import_profiles_from_json(import_path, merge=merge)


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
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[^\d,.\- ]+", "", text)
    text = text.replace(" ", "")
    if text.count(",") > 1 and "." not in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None
