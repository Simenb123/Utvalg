"""Read-only label scanner for the document-control store.

Purpose
-------
Before we build a field-specific whitelist or write a cleanup script that
mutates ``document_control_store.json``, we need a data-driven picture of
what is *actually* learned in the live store: which labels exist per
field, how strongly they are reinforced (count), how many distinct
supplier profiles carry them, and which labels look like noise.

This script is **strictly read-only**. It never writes, never mutates,
and never touches the live store in anything but ``open(..., "r")``
mode. The output is either a plain-text report for humans or a JSON
document for tooling.

Usage
-----
    python scripts/scan_profile_labels.py                    # text, live store
    python scripts/scan_profile_labels.py --store COPY.json  # scan a copy
    python scripts/scan_profile_labels.py --top 40           # more per field
    python scripts/scan_profile_labels.py --json > scan.json # machine-readable

The JSON output is a stable contract (documented in :func:`render_json`).
The text output is for eyeballing — format may change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from document_engine.profiles import LEARNABLE_FIELDS, GLOBAL_PROFILE_KEY


# ---------------------------------------------------------------------------
# Noise heuristics
# ---------------------------------------------------------------------------

# A label is "noisy" when one of these holds. The flags are orthogonal —
# a label can trip multiple flags. None of this is a classification; it is
# a triage aid for humans building the whitelist in step 2.
_BILAGSPRINT_TERMS = (
    "bilag nummer",
    "sum debet",
    "sum kredit",
    "konteringssammendrag",
    "regnskapslinje",
)
_ADDRESS_WORDS = (
    "kvarter", "gate", "gata", "vei", "veien", "plass",
    "allé", "alle", "terrasse", "brygge", "gård",
)
_FIELD_KEYWORDS = {
    # Hand-curated reference set — NOT used for filtering, only to flag
    # labels that clearly match the expected field vocabulary so the
    # human reader can quickly separate signal from noise during triage.
    "invoice_number": (
        "faktura", "invoice", "referanse", "reference", "kid", "nr", "nummer",
    ),
    "invoice_date": (
        "dato", "date", "utstedt", "issued", "fakturadato",
    ),
    "due_date": (
        "forfall", "due", "betalingsfrist", "payable",
    ),
    "subtotal_amount": (
        "netto", "grunnlag", "eksl", "ekskl", "subtotal", "net",
        "beløp eksl", "sum eks", "ordrebeløp",
    ),
    "vat_amount": (
        "mva", "merverdiavgift", "vat", "tax", "merverdi",
    ),
    "total_amount": (
        "total", "sum", "betale", "totalt", "grand", "å betale",
        "beløp", "sum faktura", "sluttsum",
    ),
    "currency": (
        "valuta", "currency", "nok", "sek", "dkk", "eur", "usd", "gbp",
    ),
}
_WORD_RE = re.compile(r"[a-zæøå]{3,}")


@dataclass
class LabelStat:
    label: str
    total_count: int = 0
    profile_count: int = 0
    pages: set[Any] = dc_field(default_factory=set)
    example_profiles: list[str] = dc_field(default_factory=list)
    noise_flags: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_count": self.total_count,
            "profile_count": self.profile_count,
            "pages": sorted(
                [p for p in self.pages if p is not None],
                key=lambda v: (isinstance(v, str), v),
            ) + ([None] if None in self.pages else []),
            "example_profiles": list(self.example_profiles),
            "noise_flags": list(self.noise_flags),
        }


def _classify_noise(label: str, field: str) -> list[str]:
    """Return a list of noise flags for *label* in the context of *field*.

    Flags are informational, not filtering — a caller may still decide
    to keep a label that trips a flag. Keeping this function pure so it
    is cheap to unit-test.
    """
    flags: list[str] = []
    low = (label or "").lower().strip()
    if not low:
        flags.append("empty")
        return flags

    # Structural flags
    words = _WORD_RE.findall(low)
    if not words:
        flags.append("no_real_word")
    if re.search(r"\d{4,}", low):
        flags.append("long_digit_run")
    if len(low) < 3:
        flags.append("too_short")
    if len(low) > 30:
        flags.append("too_long")

    # Content flags
    for term in _BILAGSPRINT_TERMS:
        if term in low:
            flags.append(f"bilagsprint:{term}")
            break
    for aw in _ADDRESS_WORDS:
        if re.search(rf"\b{aw}\b", low):
            flags.append(f"address_word:{aw}")
            break
    if "%" in low or re.search(r"\b\d{1,2}\s*00\s+av\b", low):
        flags.append("percent_rate_context")

    # Field-keyword match — the *absence* of this flag on a non-noisy label
    # is what tells the reader "this is probably a custom vendor term".
    field_kw = _FIELD_KEYWORDS.get(field, ())
    if field_kw and any(kw in low for kw in field_kw):
        flags.append("matches_field_vocab")

    return flags


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_store(store: dict[str, Any]) -> dict[str, Any]:
    """Aggregate labels per field across all non-global profiles.

    Returns a plain dict (JSON-friendly):

        {
            "profiles_total": int,
            "per_field": {
                field_name: [
                    {
                        "label": str,
                        "total_count": int,
                        "profile_count": int,
                        "pages": [int | None, ...],
                        "example_profiles": [profile_key, ...],
                        "noise_flags": [str, ...],
                    },
                    ...
                ],
            },
            "per_profile_label_counts": {profile_key: {field: int}},
        }
    """
    profiles = (store or {}).get("profiles", {}) or {}
    non_global = {
        k: v for k, v in profiles.items()
        if k != GLOBAL_PROFILE_KEY and isinstance(v, dict)
    }

    per_field: dict[str, dict[str, LabelStat]] = defaultdict(dict)
    per_profile_counts: dict[str, dict[str, int]] = defaultdict(dict)

    for profile_key, profile in non_global.items():
        field_hints = profile.get("field_hints", {}) or {}
        for field, hints in field_hints.items():
            hints = hints or []
            per_profile_counts[profile_key][field] = len(hints)
            for hint in hints:
                if not isinstance(hint, dict):
                    continue
                label = str(hint.get("label", "") or "").strip().lower()
                if not label:
                    continue
                count = int(hint.get("count", 1) or 1)
                page = hint.get("page")
                stat = per_field[field].get(label)
                if stat is None:
                    stat = LabelStat(label=label)
                    per_field[field][label] = stat
                stat.total_count += count
                stat.pages.add(page)
                if profile_key not in stat.example_profiles:
                    stat.example_profiles.append(profile_key)

    out_per_field: dict[str, list[dict[str, Any]]] = {}
    for field in LEARNABLE_FIELDS:
        stats = list(per_field.get(field, {}).values())
        for s in stats:
            s.profile_count = len(s.example_profiles)
            s.noise_flags = _classify_noise(s.label, field)
            s.example_profiles = s.example_profiles[:5]
        stats.sort(key=lambda s: (-s.total_count, s.label))
        out_per_field[field] = [s.to_dict() for s in stats]

    return {
        "profiles_total": len(non_global),
        "per_field": out_per_field,
        "per_profile_label_counts": dict(per_profile_counts),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_text(report: dict[str, Any], top: int) -> str:
    lines: list[str] = []
    lines.append(f"Profiles scanned: {report['profiles_total']}")
    lines.append("")
    for field in LEARNABLE_FIELDS:
        stats = report["per_field"].get(field, [])
        lines.append(f"=== {field} ({len(stats)} distinct labels) ===")
        if not stats:
            lines.append("  (none)")
            lines.append("")
            continue
        lines.append(
            f"  {'label':<32} {'count':>6} {'profs':>5}  noise flags"
        )
        for s in stats[:top]:
            flags = ",".join(s["noise_flags"]) or "-"
            lbl = s["label"]
            if len(lbl) > 31:
                lbl = lbl[:28] + "..."
            lines.append(
                f"  {lbl:<32} {s['total_count']:>6} {s['profile_count']:>5}  {flags}"
            )
        if len(stats) > top:
            lines.append(f"  ... {len(stats) - top} more labels not shown")
        lines.append("")

    # Noise summary per field: labels that are NOT in field vocabulary.
    lines.append("=== Noise-candidate summary (labels without field vocab match) ===")
    for field in LEARNABLE_FIELDS:
        stats = report["per_field"].get(field, [])
        noisy = [
            s for s in stats
            if "matches_field_vocab" not in s["noise_flags"]
        ]
        if not noisy:
            continue
        lines.append(
            f"  {field}: {len(noisy)} labels without field-vocab match "
            f"(top-3: {', '.join(s['label'] for s in noisy[:3]) or '-'})"
        )
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serialisable copy of *report*.

    Shape:
        {"profiles_total": int,
         "per_field": {<field>: [{label, total_count, profile_count,
                                  pages, example_profiles, noise_flags}, ...]},
         "per_profile_label_counts": {<profile_key>: {<field>: int}}}
    """
    # Already JSON-friendly from scan_store; just ensure no lingering sets.
    return json.loads(json.dumps(report, default=str))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _default_store_path() -> Path:
    try:
        from app_paths import data_file
        return data_file("document_control_store.json", subdir="document_control")
    except Exception:
        return Path("document_control_store.json")


def _load_store(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--store", type=Path, default=_default_store_path(),
                        help="Path to document_control_store.json (default: live store)")
    parser.add_argument("--top", type=int, default=25,
                        help="Max labels shown per field in text output (default: 25)")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON on stdout instead of text")
    args = parser.parse_args(argv)

    if not args.store.exists():
        print(f"Store not found: {args.store}", file=sys.stderr)
        return 2

    store = _load_store(args.store)
    report = scan_store(store)

    if args.json:
        print(json.dumps(render_json(report), indent=2, ensure_ascii=False))
    else:
        print(f"Scanning: {args.store}")
        print(render_text(report, top=args.top))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
