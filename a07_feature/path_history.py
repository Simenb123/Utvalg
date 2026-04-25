from __future__ import annotations

from pathlib import Path

from . import load_mapping, mapping_source
from .path_shared import _clean_context_value, client_store


def find_previous_year_mapping_path(
    client: str | None,
    year: str | int | None,
) -> tuple[Path | None, str | None]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return None, None

    try:
        current_year = int(str(year_s))
    except Exception:
        return None, None

    try:
        years_root = client_store.years_dir(client_s, year=str(year_s)).parent
    except Exception:
        return None, None

    candidates: list[tuple[int, Path]] = []
    try:
        for child in years_root.iterdir():
            if not child.is_dir():
                continue
            try:
                child_year = int(child.name)
            except Exception:
                continue
            if child_year >= current_year:
                continue
            mapping_path = child / "a07" / "a07_mapping.json"
            if mapping_path.exists():
                candidates.append((child_year, mapping_path))
    except Exception:
        return None, None

    if not candidates:
        return None, None

    prior_year, prior_path = max(candidates, key=lambda item: item[0])
    return prior_path, str(prior_year)


def find_previous_year_context(
    client: str | None,
    year: str | int | None,
) -> str | None:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return None

    try:
        current_year = int(str(year_s))
    except Exception:
        return None

    try:
        years_root = client_store.years_dir(client_s, year=str(year_s)).parent
    except Exception:
        return None

    prior_years: list[int] = []
    try:
        for child in years_root.iterdir():
            if not child.is_dir():
                continue
            try:
                child_year = int(child.name)
            except Exception:
                continue
            if child_year < current_year:
                prior_years.append(child_year)
    except Exception:
        return None

    if not prior_years:
        return None
    return str(max(prior_years))


def load_previous_year_mapping_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[dict[str, str], Path | None, str | None]:
    """Resolve nearest prior-year mapping from union of legacy JSON and profile
    documents. Within the chosen year, profile document wins over legacy JSON.
    """

    legacy_path, legacy_year = find_previous_year_mapping_path(client, year)
    try:
        legacy_year_i = int(legacy_year) if legacy_year else None
    except Exception:
        legacy_year_i = None

    current_year_i: int | None = None
    year_s = _clean_context_value(year)
    if year_s:
        try:
            current_year_i = int(year_s)
        except Exception:
            current_year_i = None

    doc = None
    doc_year_i: int | None = None
    if current_year_i is not None:
        try:
            doc, doc_year_i = mapping_source.load_nearest_prior_document(
                client or "", current_year_i
            )
        except Exception:
            doc, doc_year_i = None, None

    candidate_years = [y for y in (legacy_year_i, doc_year_i) if y is not None]
    if not candidate_years:
        context_year = find_previous_year_context(client, year)
        return {}, None, context_year

    chosen_year = max(candidate_years)
    chosen_year_s = str(chosen_year)

    if doc is not None and doc_year_i == chosen_year:
        mapping = mapping_source.mapping_from_document(doc)
        if mapping:
            return mapping, None, chosen_year_s
        return {}, None, chosen_year_s

    if legacy_path is not None and legacy_year_i == chosen_year:
        try:
            mapping = load_mapping(legacy_path, client=client, year=chosen_year_s)
        except Exception:
            mapping = {}
        if mapping:
            return mapping, legacy_path, chosen_year_s
        return {}, legacy_path, chosen_year_s

    return {}, None, chosen_year_s
