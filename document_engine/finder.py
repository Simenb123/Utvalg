from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import os
import re

from .models import DocumentCandidate


SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".xml",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
}
MAX_SCAN_DEPTH = 4
MAX_SCAN_FILES_PER_ROOT = 2500
MAX_RESULTS = 8
SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "node_modules",
    "datasets",
}
PATH_KEYWORDS = ("bilag", "faktura", "invoice", "vedlegg", "attachment", "dokument", "doc")
TEMP_PATH_PATTERNS = ("\\appdata\\local\\temp\\", "\\temp\\", "\\tmp\\", ".zip")


@dataclass
class DocumentSearchTerms:
    voucher_identifiers: list[str] = field(default_factory=list)
    text_tokens: list[str] = field(default_factory=list)
    reference_tokens: list[str] = field(default_factory=list)
    date_hints: list[str] = field(default_factory=list)


def build_search_terms(
    *,
    voucher_identifiers: list[str] | None = None,
    text_tokens: list[str] | None = None,
    reference_tokens: list[str] | None = None,
    date_hints: list[str] | None = None,
) -> DocumentSearchTerms:
    return DocumentSearchTerms(
        voucher_identifiers=[str(value).strip().lower() for value in list(voucher_identifiers or []) if str(value).strip()],
        text_tokens=[str(value).strip().lower() for value in list(text_tokens or []) if str(value).strip()],
        reference_tokens=[str(value).strip().lower() for value in list(reference_tokens or []) if str(value).strip()],
        date_hints=[str(value).strip() for value in list(date_hints or []) if str(value).strip()],
    )


def suggest_documents(
    search_roots: list[tuple[Path, str]],
    terms: DocumentSearchTerms,
    *,
    max_results: int = MAX_RESULTS,
) -> list[DocumentCandidate]:
    suggestions: list[DocumentCandidate] = []
    seen_paths: set[str] = set()

    for root_path, root_label in search_roots:
        for candidate in _iter_document_files(root_path, max_depth=MAX_SCAN_DEPTH, max_files=MAX_SCAN_FILES_PER_ROOT):
            candidate_key = os.path.normcase(os.path.normpath(str(candidate)))
            if candidate_key in seen_paths:
                continue
            seen_paths.add(candidate_key)

            suggestion = score_candidate(candidate, root_label=root_label, terms=terms)
            if suggestion is not None:
                suggestions.append(suggestion)

    suggestions.sort(key=lambda item: (-item.score, Path(item.path).name.lower()))
    return suggestions[:max_results]


def score_candidate(path: Path, *, root_label: str, terms: DocumentSearchTerms) -> DocumentCandidate | None:
    name_lower = path.name.lower()
    stem_lower = path.stem.lower()
    path_lower = str(path).lower()
    compact_name = re.sub(r"[^a-z0-9]+", "", stem_lower)

    score = 0.0
    reasons: list[str] = []

    ext = path.suffix.lower()
    if ext == ".pdf":
        score += 18
        reasons.append("pdf")
    elif ext == ".xml":
        score += 16
        reasons.append("xml")
    elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        score += 10
        reasons.append("bilde")
    else:
        score += 4

    if any(keyword in path_lower for keyword in PATH_KEYWORDS):
        score += 10
        reasons.append("mappenavn")
    if any(pattern in path_lower for pattern in TEMP_PATH_PATTERNS):
        score -= 20
        reasons.append("temp-nedprioritert")
    if "overordnet" in root_label.lower():
        score -= 8
    elif root_label.lower().endswith("-kilde"):
        score += 6
    elif root_label.lower().endswith("-versjon"):
        score += 3

    voucher_hit = 0
    for identifier in terms.voucher_identifiers:
        digits = re.sub(r"\D+", "", identifier)
        if identifier and identifier in stem_lower:
            score += 60
            voucher_hit += 1
        elif digits and digits in re.sub(r"\D+", "", name_lower):
            score += 48
            voucher_hit += 1
    if voucher_hit:
        reasons.append(f"bilag:{voucher_hit}")

    text_hits = 0
    for token in terms.text_tokens:
        if token and token in stem_lower:
            score += 12
            text_hits += 1
    if text_hits:
        reasons.append(f"tekst:{text_hits}")

    reference_hits = 0
    for token in terms.reference_tokens:
        compact_token = re.sub(r"[^a-z0-9]+", "", token.lower())
        if compact_token and compact_token in compact_name:
            score += 18
            reference_hits += 1
    if reference_hits:
        reasons.append(f"ref:{reference_hits}")

    for date_hint in terms.date_hints:
        year_match = re.search(r"(20\d{2})", date_hint)
        if year_match and year_match.group(1) in path_lower:
            score += 4
            reasons.append("år")
            break

    if score < 20:
        return None
    return DocumentCandidate(path=str(path), score=score, reasons=reasons, root_label=root_label)


def _iter_document_files(root: Path, *, max_depth: int, max_files: int) -> Iterable[Path]:
    scanned = 0
    root_depth = len(root.parts)

    try:
        walker = os.walk(root)
    except Exception:
        return []

    for dirpath, dirnames, filenames in walker:
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".") and depth < max_depth
        ]

        for filename in filenames:
            if scanned >= max_files:
                return
            scanned += 1

            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                continue

            path = current / filename
            if path.exists() and path.is_file():
                yield path
