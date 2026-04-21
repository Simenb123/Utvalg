"""Re-run profile hint inference for amount fields on existing records.

Background
----------
`_value_markers` previously did not normalize NBSP (\u00a0) to regular
space, so markers never matched the whitespace-collapsed segment lines.
Result: subtotal/vat/total hints were silently dropped for every save
where the amount value contained a grouped-thousands NBSP.

This migration script:
1. Loads document_control_store.json
2. Iterates records with clean amount values
3. Re-extracts PDF segments from each record's file_path
4. Runs infer_field_hints with saved field_evidence (page+bbox)
5. Merges new hints into the corresponding supplier profile
6. Saves the store (after backup)

Dry-run by default. Pass --apply to write changes.

Usage
-----
  python scripts/relearn_amount_hints.py              # dry run, summary only
  python scripts/relearn_amount_hints.py --apply      # write changes + backup
  python scripts/relearn_amount_hints.py --profile orgnr:935054737 --apply

Safety
------
- A timestamped backup of the store JSON is written before any change.
- Only amount fields are processed (subtotal/vat/total/currency).
- Garbage values (>15 digits, empty, non-numeric) are skipped.
- Existing hints are merged (count incremented if label+page matches),
  never deleted.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Repo root on sys.path so we can import document_engine & friends
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from document_engine.engine import extract_text_from_file
from document_engine.models import FieldEvidence, SupplierProfile
from document_engine.profiles import (
    _merge_hint_entries,
    infer_field_hints,
)

AMOUNT_FIELDS = ("subtotal_amount", "vat_amount", "total_amount", "currency")
DIGIT_ONLY_RE = re.compile(r"\D+")


def _is_clean_amount(value: str) -> bool:
    """Reject empty strings and garbage like long digit concatenations."""
    text = (value or "").strip()
    if not text:
        return False
    digits = DIGIT_ONLY_RE.sub("", text)
    if len(digits) == 0 or len(digits) > 12:  # >12 digits = garbage
        return False
    return True


def _is_clean_currency(value: str) -> bool:
    text = (value or "").strip()
    return 0 < len(text) <= 8


def _evidence_to_dict(ev: Any) -> dict[str, Any] | None:
    if ev is None:
        return None
    if isinstance(ev, dict):
        return ev
    if isinstance(ev, FieldEvidence):
        return {"page": ev.page, "bbox": ev.bbox}
    return None


def _pdf_path_for_record(record: dict) -> Path | None:
    file_path = (record.get("file_path") or "").strip()
    if not file_path:
        return None
    p = Path(file_path)
    if not p.exists() or p.suffix.lower() != ".pdf":
        return None
    return p


def process_store(
    store_path: Path,
    *,
    apply: bool,
    only_profile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    data = json.loads(store_path.read_text(encoding="utf-8"))
    profiles: dict[str, dict] = data.get("profiles", {}) or {}
    records: dict[str, dict] = data.get("records", {}) or {}

    stats = {
        "records_total": len(records),
        "records_considered": 0,
        "records_skipped_no_pdf": 0,
        "records_skipped_no_profile": 0,
        "records_skipped_no_clean_amounts": 0,
        "records_processed": 0,
        "hints_added": 0,
        "profiles_touched": set(),
        "per_profile_counts": {},
    }

    # Cache segments per file_path so we don't re-extract the same PDF
    segment_cache: dict[str, list] = {}

    for rec_key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        profile_key = rec.get("supplier_profile_key") or ""
        if only_profile and profile_key != only_profile:
            continue
        if not profile_key or profile_key not in profiles:
            stats["records_skipped_no_profile"] += 1
            continue

        fields = rec.get("fields") or {}
        # Build cleaned field subset: only LEARNABLE amount-like fields with
        # clean values. Drop garbage so we never pollute hints.
        cleaned: dict[str, str] = {}
        for fname in AMOUNT_FIELDS:
            val = (fields.get(fname) or "").strip()
            if fname == "currency":
                if _is_clean_currency(val):
                    cleaned[fname] = val
            else:
                if _is_clean_amount(val):
                    cleaned[fname] = val
        if not cleaned:
            stats["records_skipped_no_clean_amounts"] += 1
            continue

        stats["records_considered"] += 1

        pdf_path = _pdf_path_for_record(rec)
        if pdf_path is None:
            stats["records_skipped_no_pdf"] += 1
            continue

        # Re-extract segments (cached)
        cache_key = str(pdf_path)
        if cache_key not in segment_cache:
            try:
                result = extract_text_from_file(pdf_path)
                segment_cache[cache_key] = result.segments or []
            except Exception as exc:
                print(f"  [skip] {rec_key}: extract failed — {exc}")
                segment_cache[cache_key] = []
        segments = segment_cache[cache_key]
        if not segments:
            stats["records_skipped_no_pdf"] += 1
            continue

        # Saved evidence (page+bbox per field) if present
        raw_ev = rec.get("field_evidence") or {}
        field_evidence = {k: _evidence_to_dict(v) for k, v in raw_ev.items()}

        new_hints = infer_field_hints(
            raw_text="",
            fields=cleaned,
            segments=segments,
            field_evidence=field_evidence,
        )
        if verbose:
            print(f"  {rec_key}: cleaned={list(cleaned)} -> hints={list(new_hints) if new_hints else 'NONE'}")
            if not new_hints:
                # Diagnose: which markers are we looking for? Which evidence pages?
                for fname, val in cleaned.items():
                    ev = field_evidence.get(fname) or {}
                    print(f"    {fname}={val!r} ev_page={ev.get('page')} ev_bbox={ev.get('bbox')}")
        if not new_hints:
            continue

        # Merge into profile
        profile_raw = profiles[profile_key]
        merged = dict(profile_raw.get("field_hints") or {})
        added_this_record = 0
        for fname, hint_list in new_hints.items():
            current = list(merged.get(fname, []) or [])
            before_count = sum(int(h.get("count", 1) or 1) for h in current)
            merged[fname] = _merge_hint_entries(current, hint_list)
            after_count = sum(int(h.get("count", 1) or 1) for h in merged[fname])
            added_this_record += max(0, after_count - before_count)
        if added_this_record:
            profile_raw["field_hints"] = merged
            stats["hints_added"] += added_this_record
            stats["profiles_touched"].add(profile_key)
            stats["per_profile_counts"].setdefault(profile_key, 0)
            stats["per_profile_counts"][profile_key] += added_this_record
            stats["records_processed"] += 1

    # Report
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  records total:                 {stats['records_total']}")
    print(f"  records skipped (no profile):  {stats['records_skipped_no_profile']}")
    print(f"  records skipped (no clean $):  {stats['records_skipped_no_clean_amounts']}")
    print(f"  records considered:            {stats['records_considered']}")
    print(f"  records skipped (no PDF):      {stats['records_skipped_no_pdf']}")
    print(f"  records processed:             {stats['records_processed']}")
    print(f"  hints added:                   {stats['hints_added']}")
    print(f"  profiles touched:              {len(stats['profiles_touched'])}")
    if stats["per_profile_counts"]:
        print()
        print("Per-profile count increase:")
        for pk, n in sorted(stats["per_profile_counts"].items(), key=lambda x: -x[1]):
            print(f"  {pk}: +{n}")

    if not apply:
        print()
        print("DRY RUN — no changes written. Pass --apply to persist.")
        return stats

    # Backup + write
    backup_path = store_path.with_name(
        f"{store_path.stem}.backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    shutil.copy2(store_path, backup_path)
    print()
    print(f"Backup written: {backup_path}")

    store_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Store updated:  {store_path}")
    return stats


def _default_store_path() -> Path:
    """Default path — same as runtime repository."""
    try:
        from app_paths import data_file
        return data_file("document_control_store.json", subdir="document_control")
    except Exception:
        return Path(
            "//IB-SXD3E-008.i04.local/Common/Dokument/2/BHL klienter/"
            "Ny mappe klienter/document_control/document_control_store.json"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Path to document_control_store.json (defaults to app data location)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run).",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Limit to a specific supplier_profile_key (e.g. orgnr:935054737).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-record details (helpful for diagnosing misses).",
    )
    args = parser.parse_args()

    store_path = args.store or _default_store_path()
    if not store_path.exists():
        print(f"Store not found: {store_path}", file=sys.stderr)
        return 1
    print(f"Using store: {store_path}")
    if args.profile:
        print(f"Limiting to profile: {args.profile}")

    process_store(store_path, apply=args.apply, only_profile=args.profile, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
