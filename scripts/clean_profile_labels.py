"""Cleanup stored hint-labels that violate the current label policy.

Dry-run is the default. ``--apply`` writes a backup first, then
rewrites the store. The policy is owned by
:func:`document_engine.profiles.is_valid_label_for_field`, which
combines a universal blacklist (cover-page artefacts like ``sum debet``,
``bilag nummer``) with a per-field vocabulary.

The dry-run report is built to make the human decision easy:

    * top-N labels removed across the store (the usual suspects),
    * **profiles that end up losing all hints for a given field**
      after cleanup (the most important signal — extraction will get
      worse on those profiles until new saves accumulate),
    * before/after label counts per profile,
    * ``sample_count`` is NEVER touched (it is reinforcement history,
      not a label artefact).

Usage
-----
    python scripts/clean_profile_labels.py                  # dry-run, live
    python scripts/clean_profile_labels.py --store COPY     # dry-run copy
    python scripts/clean_profile_labels.py --json           # machine-readable
    python scripts/clean_profile_labels.py --apply          # writes + backup
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from document_engine.profiles import (
    GLOBAL_PROFILE_KEY,
    LEARNABLE_FIELDS,
    is_valid_label_for_field,
)


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------

@dataclass
class CleanupDiff:
    """Per-profile diff of a cleanup pass."""
    profile_key: str
    supplier_name: str
    sample_count: int
    fields_cleared: list[str] = dc_field(default_factory=list)
    per_field_before: dict[str, int] = dc_field(default_factory=dict)
    per_field_after: dict[str, int] = dc_field(default_factory=dict)
    removed_labels: list[tuple[str, str, int]] = dc_field(default_factory=list)
    # ^ list of (field, label, count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_key": self.profile_key,
            "supplier_name": self.supplier_name,
            "sample_count": self.sample_count,
            "fields_cleared": list(self.fields_cleared),
            "per_field_before": dict(self.per_field_before),
            "per_field_after": dict(self.per_field_after),
            "removed_labels": [
                {"field": f, "label": l, "count": c}
                for f, l, c in self.removed_labels
            ],
        }


@dataclass
class CleanupReport:
    store_path: Path
    applied: bool
    profiles_scanned: int = 0
    labels_total_before: int = 0
    labels_total_after: int = 0
    per_profile: list[CleanupDiff] = dc_field(default_factory=list)
    top_removed: list[tuple[str, str, int]] = dc_field(default_factory=list)
    # ^ list of (field, label, total_removed_count) — aggregated across store
    profiles_losing_all_hints_by_field: dict[str, list[str]] = dc_field(
        default_factory=dict,
    )
    backup_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_path": str(self.store_path),
            "applied": self.applied,
            "profiles_scanned": self.profiles_scanned,
            "labels_total_before": self.labels_total_before,
            "labels_total_after": self.labels_total_after,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "top_removed": [
                {"field": f, "label": l, "total_removed": c}
                for f, l, c in self.top_removed
            ],
            "profiles_losing_all_hints_by_field": {
                f: list(ks)
                for f, ks in self.profiles_losing_all_hints_by_field.items()
            },
            "per_profile": [d.to_dict() for d in self.per_profile],
        }


# ---------------------------------------------------------------------------
# Cleanup logic (pure — no I/O)
# ---------------------------------------------------------------------------

def clean_profile_field_hints(
    profile: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[tuple[str, str, int]]]:
    """Return (new_field_hints, removed) where *removed* lists
    ``(field, label, count)`` entries dropped by the policy.

    Duplicate entries (same ``(label, page)`` tuple) are consolidated by
    summing their counts — incidentally folding any legacy doubles.
    """
    old_hints = profile.get("field_hints", {}) or {}
    new_hints: dict[str, list[dict[str, Any]]] = {}
    removed: list[tuple[str, str, int]] = []

    for field, entries in old_hints.items():
        entries = entries or []
        merged_by_key: dict[tuple[str, Any], dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label", "") or "")
            count = int(entry.get("count", 1) or 1)
            if not is_valid_label_for_field(label, field):
                if label:
                    removed.append((field, label.strip().lower(), count))
                continue
            key = (label.strip().lower(), entry.get("page"))
            kept = merged_by_key.get(key)
            if kept is None:
                kept = dict(entry)
                kept["label"] = label.strip().lower()
                kept["count"] = count
                merged_by_key[key] = kept
            else:
                kept["count"] = int(kept.get("count", 0) or 0) + count

        kept_list = sorted(
            merged_by_key.values(),
            key=lambda h: (-int(h.get("count", 0) or 0), str(h.get("label", ""))),
        )
        if kept_list:
            new_hints[field] = kept_list
    return new_hints, removed


def build_report(
    store: dict[str, Any],
    store_path: Path,
    *,
    applied: bool,
) -> tuple[CleanupReport, dict[str, Any]]:
    """Return (*report*, *new_store*).

    *new_store* is a deep-ish copy with cleaned profile hints applied;
    it is the caller's job to decide whether to write it.
    ``sample_count`` is never changed.
    """
    profiles = (store or {}).get("profiles", {}) or {}
    report = CleanupReport(store_path=store_path, applied=applied)

    new_profiles: dict[str, dict[str, Any]] = {}
    global_total = Counter()  # (field, label) -> count removed

    for profile_key, profile in profiles.items():
        if not isinstance(profile, dict):
            new_profiles[profile_key] = profile  # leave alone
            continue
        if profile_key == GLOBAL_PROFILE_KEY:
            # ``__global__`` is rebuilt from individual profiles on save,
            # so we preserve it here unchanged; it will be regenerated
            # downstream if/when the store is rewritten through the repo.
            new_profiles[profile_key] = profile
            continue

        old_hints = profile.get("field_hints", {}) or {}
        new_hints, removed = clean_profile_field_hints(profile)

        per_field_before = {f: len(old_hints.get(f) or []) for f in LEARNABLE_FIELDS}
        per_field_after = {f: len(new_hints.get(f) or []) for f in LEARNABLE_FIELDS}

        # Fields that had hints before but none after
        fields_cleared = [
            f for f in LEARNABLE_FIELDS
            if per_field_before.get(f, 0) > 0 and per_field_after.get(f, 0) == 0
        ]
        for f in fields_cleared:
            report.profiles_losing_all_hints_by_field.setdefault(f, []).append(
                profile_key,
            )

        for field, label, count in removed:
            global_total[(field, label)] += count

        diff = CleanupDiff(
            profile_key=profile_key,
            supplier_name=str(profile.get("supplier_name", "") or ""),
            sample_count=int(profile.get("sample_count", 0) or 0),
            fields_cleared=fields_cleared,
            per_field_before={f: per_field_before[f] for f in LEARNABLE_FIELDS},
            per_field_after={f: per_field_after[f] for f in LEARNABLE_FIELDS},
            removed_labels=removed,
        )
        report.per_profile.append(diff)
        report.labels_total_before += sum(per_field_before.values())
        report.labels_total_after += sum(per_field_after.values())

        new_profile = dict(profile)
        new_profile["field_hints"] = new_hints
        # sample_count is intentionally preserved.
        new_profiles[profile_key] = new_profile

    report.profiles_scanned = sum(
        1 for k in profiles if k != GLOBAL_PROFILE_KEY
    )
    report.top_removed = [
        (field, label, count)
        for (field, label), count in global_total.most_common(30)
    ]

    new_store = dict(store)
    new_store["profiles"] = new_profiles
    return report, new_store


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_text(report: CleanupReport) -> str:
    lines: list[str] = []
    mode = "APPLY" if report.applied else "DRY-RUN"
    lines.append(f"[{mode}] store: {report.store_path}")
    lines.append(
        f"  profiles scanned: {report.profiles_scanned}"
    )
    lines.append(
        f"  total label-entries: {report.labels_total_before} -> {report.labels_total_after}"
        f"  (removed: {report.labels_total_before - report.labels_total_after})"
    )
    if report.backup_path:
        lines.append(f"  backup: {report.backup_path}")
    lines.append("")

    # Top removed labels
    lines.append("=== Top 30 removed labels (sum of count across all profiles) ===")
    for field, label, count in report.top_removed:
        lbl = label if len(label) <= 40 else label[:37] + "..."
        lines.append(f"  [{field:<17}] {lbl:<42} {count:>6}")
    if not report.top_removed:
        lines.append("  (none — the store is already clean)")
    lines.append("")

    # Profiles losing all hints for a field — the critical signal
    lines.append("=== Profiles that LOSE ALL hints for a field after cleanup ===")
    losers = report.profiles_losing_all_hints_by_field
    if not losers:
        lines.append("  (none — no profile will be left without hints on any field)")
    else:
        for field in LEARNABLE_FIELDS:
            keys = losers.get(field) or []
            if not keys:
                continue
            lines.append(f"  {field}: {len(keys)} profile(s)")
            for k in keys[:10]:
                # Find supplier_name for display
                name = next(
                    (d.supplier_name for d in report.per_profile if d.profile_key == k),
                    "",
                )
                lines.append(f"    - {k}  ({name})")
            if len(keys) > 10:
                lines.append(f"    ... {len(keys) - 10} more not shown")
    lines.append("")

    # Per-profile summary
    lines.append("=== Per-profile summary (top 15 by total removed) ===")
    per_profile_sorted = sorted(
        report.per_profile,
        key=lambda d: -sum(c for _, _, c in d.removed_labels),
    )
    for d in per_profile_sorted[:15]:
        total_removed = sum(c for _, _, c in d.removed_labels)
        if total_removed == 0:
            continue
        before = sum(d.per_field_before.values())
        after = sum(d.per_field_after.values())
        cleared = f" CLEARED:{','.join(d.fields_cleared)}" if d.fields_cleared else ""
        lines.append(
            f"  {d.profile_key}  ({d.supplier_name})"
            f"  samples={d.sample_count}"
            f"  entries {before}->{after}  removed_count={total_removed}{cleared}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _default_store_path() -> Path:
    try:
        from app_paths import data_file
        return data_file("document_control_store.json", subdir="document_control")
    except Exception:
        return Path("document_control_store.json")


def _write_store_with_backup(store_path: Path, new_store: dict[str, Any]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = store_path.with_name(f"{store_path.stem}.backup_{timestamp}{store_path.suffix}")
    shutil.copy2(store_path, backup)
    store_path.write_text(
        json.dumps(new_store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0] if __doc__ else "",
    )
    parser.add_argument("--store", type=Path, default=_default_store_path(),
                        help="Path to document_control_store.json (default: live store)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write the cleaned store (default is dry-run)")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON on stdout")
    args = parser.parse_args(argv)

    if not args.store.exists():
        print(f"Store not found: {args.store}", file=sys.stderr)
        return 2

    store = json.loads(args.store.read_text(encoding="utf-8"))
    report, new_store = build_report(store, args.store, applied=args.apply)

    if args.apply:
        if report.labels_total_before == report.labels_total_after:
            # Nothing to do — do not touch the file so no accidental
            # timestamp churn or gratuitous backup.
            pass
        else:
            report.backup_path = _write_store_with_backup(args.store, new_store)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
