"""Strict re-learning runner for document_control supplier profiles.

This is the mass-run sibling of ``scripts/relearn_amount_hints.py``:
instead of only re-inferring amount hints, it rebuilds **every
learnable field** for every record that passes a strict safety gate. It
is the tool you use when you want to refresh supplier profiles after
fixing a bug in the extractor (NBSP normalisation, marker inference,
bbox geometry) without risking that bad records pollute what we learn.

Criteria -- a record is only replayed when ALL of the following hold:

1. It has a ``supplier_profile_key`` that is already in the store
   (i.e. we know which supplier to update).
2. The linked ``file_path`` exists and is a PDF.
3. It has a non-empty ``raw_text_excerpt`` (a save without a preceding
   analysis has no text -- skip it, never infer blindly).
4. ``validation_messages`` is empty (records that already had avvik are
   not trusted enough to teach the profile).
5. Every learnable field has evidence with a real ``page`` and a
   ``bbox`` narrower than ``--max-bbox-width`` (default 140 pt) -- a huge
   bbox is the telltale sign of a block-level match that could cover
   the wrong amount on a tabular invoice.
6. ``subtotal + vat ~= total`` -- if saved amounts do not self-cross-check
   we do NOT want them reinforcing profile hints, even if the user
   confirmed them.
7. For records whose selected extraction was ``pdf_ocrmypdf_redo``
   (``metadata.ocr_redo_chosen == True``), the script re-extracts with
   ``force_ocr_redo=True`` so the new segments match the original OCR
   layer -- otherwise bbox/label inference would regress.
8. Orgnr-keyed profiles must have a 9-digit orgnr; name-keyed profiles
   must have a non-empty ``supplier_name``. Short / blank values get
   skipped.

Aggregation
-----------
Multiple accepted records for the same supplier are rolled up into a
**single** profile rebuild. Hints inferred from each record are merged
with :func:`document_engine.profiles._merge_hint_entries`, so a label
confirmed by N records ends up with ``count: N`` -- not ``count: 1``
from whichever record happens to be processed last.

``description`` and ``period`` are intentionally NOT learnable.

``--dry-run`` (default) reports the verdict for every record without
writing anything. ``--apply`` writes one backup of the store ONLY when
at least one profile actually ends up being rewritten, rebuilds
profiles for accepted records, regenerates ``__global__`` via
``build_global_profile()``, and persists.

Usage
-----
    py scripts/relearn_document_profiles.py                # dry run
    py scripts/relearn_document_profiles.py --json         # JSON to stdout
    py scripts/relearn_document_profiles.py --profile orgnr:935054737
    py scripts/relearn_document_profiles.py --apply

Safety
------
- A timestamped backup of the store JSON is written before any change,
  but only when the apply run will actually rewrite at least one profile.
- The canonical order of operations is: load -> evaluate dry-run verdict
  for every record -> re-extract segments -> aggregate hints per profile
  -> (if --apply and at least one profile gained hints) backup -> rewrite.
- ``--json`` emits valid JSON to stdout ONLY; all human-readable status
  text is routed to stderr so the stdout stream can be fed straight to
  ``json.loads``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from document_engine.engine import extract_text_from_file
from document_engine.format_utils import (
    normalize_orgnr,
    parse_amount_flexible,
)
from document_engine.models import SupplierProfile
from document_engine.profiles import (
    GLOBAL_PROFILE_KEY,
    LEARNABLE_FIELDS,
    _merge_hint_entries,
    build_global_profile,
    build_supplier_profile,
    infer_field_hints,
)


# Fields we re-learn in the strict runner. ``currency`` is included but
# ``description``/``period`` are intentionally NOT: they are free-text
# and their hints do not reliably round-trip.
_LEARNABLE = tuple(f for f in LEARNABLE_FIELDS if f != "description")
_AMOUNT_FIELDS = ("subtotal_amount", "vat_amount", "total_amount")


@dataclass
class RecordVerdict:
    record_key: str
    profile_key: str
    decision: str  # "accept" | "skip"
    reasons: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_key": self.record_key,
            "profile_key": self.profile_key,
            "decision": self.decision,
            "reasons": list(self.reasons),
        }


def _ev_get(ev: Any, key: str) -> Any:
    if ev is None:
        return None
    if isinstance(ev, dict):
        return ev.get(key)
    return getattr(ev, key, None)


def _bbox_width(bbox: Any) -> float | None:
    if not bbox:
        return None
    try:
        x0, _, x1, _ = bbox
        return float(x1) - float(x0)
    except Exception:
        return None


def _amounts_self_consistent(
    field_values: dict[str, str],
    *,
    tolerance: float = 1.0,
) -> tuple[bool | None, str]:
    sub = parse_amount_flexible(field_values.get("subtotal_amount"))
    vat = parse_amount_flexible(field_values.get("vat_amount"))
    tot = parse_amount_flexible(field_values.get("total_amount"))
    if sub is None or vat is None or tot is None:
        return None, "missing_one_of_subtotal_vat_total"
    deviation = abs((sub + vat) - tot)
    if deviation <= tolerance:
        return True, ""
    return False, f"subtotal+vat!=total (|dev|={deviation:.2f})"


def _profile_ident_ok(profile_key: str, supplier: dict[str, Any]) -> tuple[bool, str]:
    """Reject profiles we cannot safely key (blank orgnr / blank name)."""
    if profile_key.startswith("orgnr:"):
        digits = normalize_orgnr(profile_key.split(":", 1)[1])
        if len(digits) != 9:
            return False, f"profile_key has non-9-digit orgnr: {digits!r}"
        return True, ""
    if profile_key.startswith("name:"):
        name = profile_key.split(":", 1)[1].strip()
        if not name:
            return False, "profile_key is name:<empty>"
        return True, ""
    return False, f"unrecognised profile_key prefix: {profile_key!r}"


def _evaluate_record(
    rec_key: str,
    rec: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    *,
    max_bbox_width: float,
) -> RecordVerdict:
    profile_key = (rec.get("supplier_profile_key") or "").strip()
    verdict = RecordVerdict(record_key=rec_key, profile_key=profile_key, decision="skip")

    if not profile_key:
        verdict.reasons.append("missing supplier_profile_key")
        return verdict
    if profile_key not in profiles:
        verdict.reasons.append(f"profile {profile_key!r} not in store")
        return verdict
    ident_ok, ident_reason = _profile_ident_ok(profile_key, rec)
    if not ident_ok:
        verdict.reasons.append(ident_reason)
        return verdict

    file_path = (rec.get("file_path") or "").strip()
    if not file_path:
        verdict.reasons.append("no file_path")
        return verdict
    pdf_path = Path(file_path)
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        verdict.reasons.append(f"file_path missing or non-PDF: {pdf_path}")
        return verdict

    raw_text_excerpt = (rec.get("raw_text_excerpt") or "").strip()
    if not raw_text_excerpt:
        verdict.reasons.append("raw_text_excerpt is empty")
        return verdict

    validation_messages = rec.get("validation_messages") or []
    if validation_messages:
        verdict.reasons.append(
            f"record has {len(validation_messages)} validation message(s)"
        )
        return verdict

    fields = rec.get("fields") or {}
    amounts_ok, amount_reason = _amounts_self_consistent(fields)
    if amounts_ok is None:
        verdict.reasons.append(amount_reason)
        return verdict
    if amounts_ok is False:
        verdict.reasons.append(amount_reason)
        return verdict

    evidence_map = rec.get("field_evidence") or {}
    for fname in _LEARNABLE:
        if fname == "currency":
            continue
        value = (fields.get(fname) or "").strip()
        if not value:
            verdict.reasons.append(f"{fname}: empty")
            return verdict
        ev = evidence_map.get(fname)
        page = _ev_get(ev, "page")
        bbox = _ev_get(ev, "bbox")
        if page is None or bbox is None:
            verdict.reasons.append(f"{fname}: evidence missing page/bbox")
            return verdict
        width = _bbox_width(bbox)
        if width is None or width > max_bbox_width:
            verdict.reasons.append(
                f"{fname}: bbox too wide ({width!r} > {max_bbox_width})"
            )
            return verdict

    verdict.decision = "accept"
    return verdict


def _needs_force_ocr_redo(rec: dict[str, Any]) -> bool:
    md = rec.get("metadata") or {}
    if md.get("ocr_redo_chosen") is True:
        return True
    source = (rec.get("source") or md.get("source") or "").strip().lower()
    return source == "pdf_ocrmypdf_redo"


def _extract_fields_subset(rec: dict[str, Any]) -> dict[str, str]:
    """Return only the learnable field values from *rec* (ignore info-only)."""
    fields = rec.get("fields") or {}
    out: dict[str, str] = {}
    for fname in _LEARNABLE:
        v = (fields.get(fname) or "").strip()
        if v:
            out[fname] = v
    # Static identity fields are needed so build_supplier_profile can
    # resolve the right profile_key and preserve supplier_name/orgnr.
    for ident in ("supplier_name", "supplier_orgnr", "currency"):
        v = (fields.get(ident) or "").strip()
        if v:
            out[ident] = v
    return out


def _empty_stats(*, apply: bool) -> dict[str, Any]:
    return {
        "records_considered": 0,
        "records_accepted_initial": 0,
        "records_accepted_final": 0,
        "records_skipped": 0,
        "records_skipped_after_extract": 0,
        "skip_reason_counts": {},
        "profiles_touched": set(),
        "profiles_with_no_hints": set(),
        "ocr_redo_used": 0,
        "hints_written": 0,
        "hints_written_by_profile": {},
        "apply": apply,
    }


def process_store(
    store_path: Path,
    *,
    apply: bool,
    only_profile: str | None = None,
    max_bbox_width: float = 140.0,
    verbose: bool = False,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _log: Callable[[str], None] = log if log is not None else print

    data = json.loads(store_path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, Any]] = data.get("records", {}) or {}
    profiles: dict[str, dict[str, Any]] = data.get("profiles", {}) or {}

    verdicts: list[RecordVerdict] = []
    for rec_key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        if only_profile and rec.get("supplier_profile_key") != only_profile:
            continue
        verdicts.append(
            _evaluate_record(rec_key, rec, profiles, max_bbox_width=max_bbox_width)
        )

    accepted_initial = [v for v in verdicts if v.decision == "accept"]
    skipped_initial = [v for v in verdicts if v.decision == "skip"]

    stats = _empty_stats(apply=apply)
    stats["records_considered"] = len(verdicts)
    stats["records_accepted_initial"] = len(accepted_initial)

    for v in skipped_initial:
        key = v.reasons[0] if v.reasons else "unknown"
        # Collapse reasons that include record-specific paths/numbers
        bucket = key.split(":", 1)[0]
        stats["skip_reason_counts"][bucket] = stats["skip_reason_counts"].get(bucket, 0) + 1

    if verbose:
        for v in verdicts:
            line = f"  [{v.decision}] {v.record_key} -> {v.profile_key}"
            if v.reasons:
                line += "  :: " + "; ".join(v.reasons)
            _log(line)

    result: dict[str, Any] = {
        "store_path": str(store_path),
    }

    if not accepted_initial:
        stats["records_skipped"] = len(skipped_initial)
        result["stats"] = stats
        result["verdicts"] = [v.to_dict() for v in verdicts]
        _print_summary(stats, log=_log)
        return result

    # --------------------------------------------------------------
    # Pass 1: re-extract segments per (path, redo-mode). One record
    # that fails extract is marked skip-after-extract; cache hits
    # are free so N records for the same PDF do not re-run OCR.
    # --------------------------------------------------------------
    segment_cache: dict[tuple[str, bool], tuple[list[Any], str]] = {}
    ocr_redo_paths: set[tuple[str, bool]] = set()

    for verdict in accepted_initial:
        rec = records[verdict.record_key]
        pdf_path = Path(rec["file_path"])
        force_redo = _needs_force_ocr_redo(rec)
        cache_key = (str(pdf_path), force_redo)
        if cache_key not in segment_cache:
            try:
                extracted = extract_text_from_file(pdf_path, force_ocr_redo=force_redo)
                segment_cache[cache_key] = (
                    list(extracted.segments or []),
                    extracted.text or "",
                )
            except Exception as exc:  # noqa: BLE001 — bubbling the message is the point
                segment_cache[cache_key] = ([], "")
                verdict.decision = "skip"
                verdict.reasons.append(f"re-extract failed: {exc!r}")
                stats["records_skipped_after_extract"] += 1
                continue
        segments, raw_text = segment_cache[cache_key]
        if not segments and not raw_text:
            verdict.decision = "skip"
            verdict.reasons.append("re-extract produced no text/segments")
            stats["records_skipped_after_extract"] += 1
            continue
        if force_redo and cache_key not in ocr_redo_paths:
            ocr_redo_paths.add(cache_key)
            stats["ocr_redo_used"] += 1

    # --------------------------------------------------------------
    # Pass 2: aggregate hints from all still-accepted records per
    # profile_key. A profile is only touched if the aggregated
    # hint map is non-empty; otherwise the existing profile is
    # left alone and the records are marked skip.
    # --------------------------------------------------------------
    by_profile: dict[str, list[RecordVerdict]] = defaultdict(list)
    for v in accepted_initial:
        if v.decision == "accept":
            by_profile[v.profile_key].append(v)

    new_profile_objects: dict[str, SupplierProfile] = {}

    for profile_key, group in by_profile.items():
        existing_raw = profiles.get(profile_key)
        accumulator: SupplierProfile | None = None
        merged_hints: dict[str, list[dict[str, Any]]] = {}
        aggregated_count = 0

        for v in group:
            rec = records[v.record_key]
            fields_subset = _extract_fields_subset(rec)
            if not fields_subset:
                v.decision = "skip"
                v.reasons.append("no learnable fields after subset")
                stats["records_skipped_after_extract"] += 1
                continue

            pdf_path = Path(rec["file_path"])
            force_redo = _needs_force_ocr_redo(rec)
            segments, raw_text = segment_cache[(str(pdf_path), force_redo)]

            # Identity update: bump sample_count, merge static_fields
            # and aliases onto the running accumulator. We immediately
            # discard build_supplier_profile's flat-text hint fallback
            # because pass-2 accumulation uses segment-based inference
            # only (flat text has no page/bbox info).
            base = accumulator
            if base is None and existing_raw is not None:
                base = SupplierProfile.from_dict(existing_raw)
                if base is not None:
                    base.field_hints = {}
            tmp_profile = build_supplier_profile(
                fields=fields_subset,
                raw_text=raw_text,
                existing_profile=base,
            )
            if tmp_profile is None:
                v.decision = "skip"
                v.reasons.append("build_supplier_profile returned None")
                stats["records_skipped_after_extract"] += 1
                continue

            inferred = infer_field_hints(
                raw_text=raw_text,
                fields=fields_subset,
                segments=segments,
                field_evidence=rec.get("field_evidence") or {},
            )
            for fname, new_hints in inferred.items():
                merged_hints[fname] = _merge_hint_entries(
                    merged_hints.get(fname, []), new_hints
                )

            tmp_profile.field_hints = {}
            accumulator = tmp_profile
            aggregated_count += 1

        if accumulator is None or aggregated_count == 0:
            # Every record for this profile skipped during extract/subset.
            continue

        if not merged_hints:
            # Re-extract succeeded but no hints could be inferred from
            # the refreshed segments — refuse to overwrite the existing
            # profile with an empty hint map.
            stats["profiles_with_no_hints"].add(profile_key)
            for v in group:
                if v.decision == "accept":
                    v.decision = "skip"
                    v.reasons.append("inferred no hints from re-extracted segments")
                    stats["records_skipped_after_extract"] += 1
            continue

        # Merge pre-existing hints BACK in so relearn is additive — the
        # counts are cumulative ("how many times has this label been
        # confirmed across history"), and scrapping them for records not
        # re-processed in this run would make the store progressively
        # forget what it already knew.
        if existing_raw is not None:
            existing_profile = SupplierProfile.from_dict(existing_raw)
            if existing_profile is not None and existing_profile.field_hints:
                for fname, old_hints in existing_profile.field_hints.items():
                    merged_hints[fname] = _merge_hint_entries(
                        merged_hints.get(fname, []), list(old_hints or []),
                    )

        accumulator.field_hints = merged_hints
        new_profile_objects[profile_key] = accumulator
        stats["profiles_touched"].add(profile_key)
        hint_entry_count = sum(len(entries) for entries in merged_hints.values())
        stats["hints_written_by_profile"][profile_key] = hint_entry_count
        stats["hints_written"] += hint_entry_count

    stats["records_accepted_final"] = sum(
        1 for v in accepted_initial if v.decision == "accept"
    )
    stats["records_skipped"] = sum(1 for v in verdicts if v.decision == "skip")

    result["stats"] = stats
    result["verdicts"] = [v.to_dict() for v in verdicts]

    if not apply:
        _print_summary(stats, log=_log)
        return result

    if not new_profile_objects:
        # Apply requested but nothing to write: skip backup, skip rewrite.
        _print_summary(stats, log=_log)
        _log("")
        _log("No profile gained hints — store left untouched, no backup written.")
        return result

    # Apply: backup -> overwrite profiles -> regenerate __global__ -> write.
    backup_path = store_path.with_name(
        f"{store_path.stem}.backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    shutil.copy2(store_path, backup_path)
    result["backup_path"] = str(backup_path)
    _log("")
    _log(f"Backup written: {backup_path}")

    for key, profile in new_profile_objects.items():
        profiles[key] = profile.to_dict()

    global_profile = build_global_profile(profiles)
    if global_profile is not None:
        profiles[GLOBAL_PROFILE_KEY] = global_profile.to_dict()
    else:
        profiles.pop(GLOBAL_PROFILE_KEY, None)

    data["profiles"] = profiles
    store_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log(f"Store updated:  {store_path}")
    _print_summary(stats, log=_log)
    return result


def _print_summary(
    stats: dict[str, Any],
    *,
    log: Callable[[str], None] = print,
) -> None:
    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"  records considered:          {stats['records_considered']}")
    log(f"  records accepted (initial):  {stats['records_accepted_initial']}")
    log(f"  records accepted (final):    {stats['records_accepted_final']}")
    log(f"  records skipped:             {stats['records_skipped']}")
    log(f"    of which after extract:    {stats['records_skipped_after_extract']}")
    log(f"  OCR-redo replays:            {stats['ocr_redo_used']}")
    log(f"  profiles touched:            {len(stats['profiles_touched'])}")
    log(f"  profiles with no hints:      {len(stats['profiles_with_no_hints'])}")
    log(f"  hints written:               {stats['hints_written']}")
    if stats["hints_written_by_profile"]:
        log("")
        log("Hints written per profile:")
        for key, n in sorted(
            stats["hints_written_by_profile"].items(), key=lambda x: (-x[1], x[0])
        ):
            log(f"  {n:>4}  {key}")
    if stats["skip_reason_counts"]:
        log("")
        log("Skip reasons:")
        for reason, n in sorted(stats["skip_reason_counts"].items(), key=lambda x: -x[1]):
            log(f"  {n:>4}  {reason}")
    if not stats["apply"]:
        log("")
        log("DRY RUN - no changes written. Pass --apply to persist.")


def _default_store_path() -> Path:
    try:
        from app_paths import data_file
        return data_file("document_control_store.json", subdir="document_control")
    except Exception:
        return Path(
            "//IB-SXD3E-008.i04.local/Common/Dokument/2/BHL klienter/"
            "Ny mappe klienter/document_control/document_control_store.json"
        )


def _result_for_json(result: dict[str, Any]) -> dict[str, Any]:
    """Convert set-valued stats to sorted lists so the result is JSON-safe."""
    stats = dict(result.get("stats") or {})
    stats["profiles_touched"] = sorted(stats.get("profiles_touched") or [])
    stats["profiles_with_no_hints"] = sorted(stats.get("profiles_with_no_hints") or [])
    out: dict[str, Any] = {
        "stats": stats,
        "verdicts": list(result.get("verdicts") or []),
        "profiles_touched": list(stats["profiles_touched"]),
        "store_path": result.get("store_path", ""),
    }
    if "backup_path" in result:
        out["backup_path"] = result["backup_path"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strict re-learning of supplier profiles (see module docstring for criteria).",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store path")
    parser.add_argument("--apply", action="store_true", help="Persist changes (default dry-run)")
    parser.add_argument("--profile", type=str, default=None, help="Limit to supplier_profile_key")
    parser.add_argument("--max-bbox-width", type=float, default=140.0,
                        help="Reject evidence with bbox width over this many pt (default 140)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON report to stdout (human text goes to stderr)")
    parser.add_argument("--verbose", action="store_true", help="Print per-record verdicts")
    args = parser.parse_args(argv)

    store_path = args.store or _default_store_path()

    # With --json, stdout is reserved for the JSON document only: all
    # human-readable status text is routed to stderr so the stdout stream
    # can be piped directly into ``json.loads``.
    if args.json:
        def _log(msg: str = "") -> None:
            print(msg, file=sys.stderr)
    else:
        def _log(msg: str = "") -> None:
            print(msg)

    if not store_path.exists():
        print(f"Store not found: {store_path}", file=sys.stderr)
        return 1

    _log(f"Using store: {store_path}")
    if args.profile:
        _log(f"Limiting to profile: {args.profile}")

    result = process_store(
        store_path,
        apply=args.apply,
        only_profile=args.profile,
        max_bbox_width=args.max_bbox_width,
        verbose=args.verbose,
        log=_log,
    )

    if args.json:
        json_doc = _result_for_json(result)
        print(json.dumps(json_doc, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
