"""document_control_voucher_index

Client-level management of Tripletex voucher bundle PDFs.

Workflow
--------
1. User places one or more Tripletex voucher PDFs in the client's vouchers/ folder
   (or any other folder and then imports them via the dialog).
2. The index is built on first use and cached as JSON next to the store.
3. When document control opens for bilag X, we look up X in the index,
   extract the relevant pages to a per-bilag PDF and return the path.

Folder conventions
------------------
Voucher PDFs are searched in:
  <client_years_dir>/vouchers/        ← primary drop folder
  <client_years_dir>/                 ← fallback (PDFs in the year root)

Extracted single-bilag PDFs are saved to:
  <client_years_dir>/vouchers/extracted/<bilag_nr>.pdf

The index cache file is:
  <app_data>/document_control/voucher_index_<client_slug>_<year>.json
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app_paths
from document_engine.voucher_pdf import VoucherEntry, extract_entry, scan_voucher_pdf

try:
    import client_store as _cs
    _HAS_CLIENT_STORE = True
except Exception:
    _cs = None  # type: ignore[assignment]
    _HAS_CLIENT_STORE = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_voucher_search_dirs(client: str | None, year: str | None) -> list[Path]:
    """Return directories to search for Tripletex voucher bundle PDFs."""
    dirs: list[Path] = []

    if _HAS_CLIENT_STORE and client and year:
        try:
            year_root = _cs.years_dir(client, year=year)
            _add_dir(dirs, year_root / "vouchers")
            _add_dir(dirs, year_root)
        except Exception:
            pass

    return dirs


def scan_voucher_dirs(
    client: str | None,
    year: str | None,
    *,
    extra_paths: list[str | Path] | None = None,
) -> list[VoucherEntry]:
    """Scan all known voucher directories and return a flat list of VoucherEntries.

    Results from multiple PDFs are merged.  Entries from extra_paths are
    included alongside the standard directories.
    """
    search_dirs = get_voucher_search_dirs(client, year)
    pdf_paths: list[Path] = _collect_pdf_paths(search_dirs)

    for extra in extra_paths or []:
        p = Path(extra).expanduser()
        if p.is_file() and p.suffix.lower() == ".pdf":
            if p not in pdf_paths:
                pdf_paths.append(p)
        elif p.is_dir():
            _collect_from_dir(p, pdf_paths)

    entries: list[VoucherEntry] = []
    for pdf in pdf_paths:
        entries.extend(scan_voucher_pdf(pdf))
    return entries


def find_bilag_in_vouchers(
    bilag_nr: str,
    *,
    client: str | None,
    year: str | None,
    extra_paths: list[str | Path] | None = None,
    use_cache: bool = True,
) -> VoucherEntry | None:
    """Find the VoucherEntry for a given bilag number.

    Tries the cached index first (if use_cache=True), then falls back to a
    live scan.  Returns None if not found.
    """
    bilag_key = _norm(bilag_nr)
    if not bilag_key:
        return None

    if use_cache:
        cached = _load_index_cache(client, year)
        if cached is not None:
            raw = cached.get(bilag_key)
            if raw:
                return VoucherEntry.from_dict(raw)

    # Live scan (also refreshes cache)
    entries = scan_voucher_dirs(client, year, extra_paths=extra_paths)
    if use_cache and entries:
        _save_index_cache(client, year, entries)

    for entry in entries:
        if entry.bilag_key == bilag_key:
            return entry
    return None


def extract_bilag_pdf(
    entry: VoucherEntry,
    *,
    client: str | None,
    year: str | None,
    output_dir: str | Path | None = None,
    skip_if_exists: bool = True,
) -> Path:
    """Extract the bilag pages to a single PDF and return its path.

    The extracted file is saved to output_dir (or the standard vouchers/extracted/
    folder) and named <bilag_nr>.pdf.  If skip_if_exists=True (default) and the
    output file already exists, no re-extraction is performed.
    """
    if output_dir is None:
        output_dir = _extracted_dir(client, year)
    else:
        output_dir = Path(output_dir).expanduser()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{entry.bilag_nr}.pdf"

    if skip_if_exists and output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    return extract_entry(entry, output_path)


def find_and_extract_bilag(
    bilag_nr: str,
    *,
    client: str | None,
    year: str | None,
    extra_paths: list[str | Path] | None = None,
    output_dir: str | Path | None = None,
    use_cache: bool = True,
) -> Path | None:
    """One-shot: find bilag in voucher PDFs and extract to a single PDF.

    Returns the extracted PDF path, or None if not found.
    """
    entry = find_bilag_in_vouchers(
        bilag_nr,
        client=client,
        year=year,
        extra_paths=extra_paths,
        use_cache=use_cache,
    )
    if entry is None:
        return None
    return extract_bilag_pdf(entry, client=client, year=year, output_dir=output_dir)


def rebuild_index_cache(
    client: str | None,
    year: str | None,
    *,
    extra_paths: list[str | Path] | None = None,
) -> dict[str, VoucherEntry]:
    """Force a full rescan and rebuild the cache.  Returns the new index."""
    entries = scan_voucher_dirs(client, year, extra_paths=extra_paths)
    _save_index_cache(client, year, entries)
    return {e.bilag_key: e for e in entries}


def get_cached_index(client: str | None, year: str | None) -> dict[str, VoucherEntry] | None:
    """Return the cached index, or None if no cache exists yet."""
    raw = _load_index_cache(client, year)
    if raw is None:
        return None
    result: dict[str, VoucherEntry] = {}
    for key, payload in raw.items():
        try:
            result[key] = VoucherEntry.from_dict(payload)
        except Exception:
            pass
    return result


def import_voucher_pdf(
    pdf_path: str | Path,
    *,
    client: str | None,
    year: str | None,
    copy_to_vouchers: bool = True,
) -> list[VoucherEntry]:
    """Import a voucher PDF: scan it, copy to vouchers/ dir, update cache.

    Returns the list of VoucherEntries found in the PDF.
    """
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fant ikke filen: {pdf_path}")

    dest_path = pdf_path
    if copy_to_vouchers and _HAS_CLIENT_STORE and client and year:
        try:
            voucher_dir = _vouchers_dir(client, year)
            voucher_dir.mkdir(parents=True, exist_ok=True)
            dest_path = voucher_dir / pdf_path.name
            if not dest_path.exists():
                import shutil
                shutil.copy2(str(pdf_path), str(dest_path))
        except Exception:
            dest_path = pdf_path

    entries = scan_voucher_pdf(dest_path)

    # Merge into existing cache
    existing_raw = _load_index_cache(client, year) or {}
    for e in entries:
        existing_raw[e.bilag_key] = e.to_dict()
    _write_index_cache(client, year, existing_raw)

    return entries


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(client: str | None, year: str | None) -> Path:
    slug = _slug(client or "ukjent") + "_" + (year or "ukjent")
    return app_paths.data_file(
        f"voucher_index_{slug}.json",
        subdir="document_control",
    )


def _load_index_cache(client: str | None, year: str | None) -> dict[str, Any] | None:
    path = _cache_path(client, year)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data.get("entries", {}))
    except Exception:
        return None


def _save_index_cache(
    client: str | None,
    year: str | None,
    entries: list[VoucherEntry],
) -> None:
    payload: dict[str, Any] = {e.bilag_key: e.to_dict() for e in entries}
    _write_index_cache(client, year, payload)


def _write_index_cache(
    client: str | None,
    year: str | None,
    entries_raw: dict[str, Any],
) -> None:
    path = _cache_path(client, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "client": client,
        "year": year,
        "entries": entries_raw,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def _vouchers_dir(client: str | None, year: str | None) -> Path:
    if _HAS_CLIENT_STORE and client and year:
        try:
            return _cs.years_dir(client, year=year) / "vouchers"
        except Exception:
            pass
    return app_paths.data_file("", subdir="vouchers").parent


def _extracted_dir(client: str | None, year: str | None) -> Path:
    return _vouchers_dir(client, year) / "extracted"


def _add_dir(dirs: list[Path], path: Path) -> None:
    try:
        path = path.expanduser()
    except Exception:
        return
    norm = os.path.normcase(os.path.normpath(str(path)))
    if any(os.path.normcase(os.path.normpath(str(d))) == norm for d in dirs):
        return
    dirs.append(path)


def _collect_pdf_paths(dirs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for d in dirs:
        _collect_from_dir(d, paths)
    return paths


def _collect_from_dir(d: Path, paths: list[Path]) -> None:
    if not d.is_dir():
        return
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() == ".pdf" and f not in paths:
            paths.append(f)


def _norm(s: str) -> str:
    text = str(s or "").strip()
    text = re.sub(r"\.0+$", "", text)
    try:
        return str(int(text))
    except ValueError:
        return text


def _slug(s: str) -> str:
    return re.sub(r"[^\w]", "_", str(s or "").strip())[:40]
