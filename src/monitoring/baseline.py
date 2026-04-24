"""Baseline-verktøy for ytelse-overvåking.

Lagrer snapshot av gjeldende events som baseline-statistikk per op,
og sammenligner senere kjøringer mot baseline for å fange regresjoner.

Bruk:

    python -m src.monitoring.baseline save    # Lagre gjeldende events som baseline
    python -m src.monitoring.baseline compare # Sammenlign gjeldende mot baseline
    python -m src.monitoring.baseline show    # Print baseline til konsoll

Baseline lagres som JSON i ``<data_dir>/monitoring/baseline.json``.
Format:

    {
      "created_at": "2026-04-24T15:00:00Z",
      "source_events": 1234,
      "ops": {
        "sb.refresh": {"samples": 42, "median_ms": 1150, "p95_ms": 1450, "max_ms": 2100},
        "sb.base.ownership_map": {"samples": 1, "median_ms": 3000, "p95_ms": 3000, "max_ms": 3000},
        ...
      }
    }
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.monitoring.events import TimingEvent, read_events


# ---------------------------------------------------------------------------
# Data-modell

@dataclass
class OpStats:
    """Statistikk for én op, aggregert over mange samples."""

    samples: int = 0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class Baseline:
    """Baseline-snapshot. Serialiseres til JSON."""

    created_at: str
    source_events: int
    ops: dict[str, OpStats] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "source_events": self.source_events,
            "ops": {op: asdict(s) for op, s in self.ops.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Baseline":
        ops = {
            op: OpStats(**stats)
            for op, stats in (data.get("ops") or {}).items()
        }
        return cls(
            created_at=str(data.get("created_at", "")),
            source_events=int(data.get("source_events", 0)),
            ops=ops,
        )


# ---------------------------------------------------------------------------
# Core API

def default_events_path() -> Path:
    try:
        import app_paths
        return app_paths.data_dir() / "monitoring" / "events.jsonl"
    except Exception:
        return Path(__file__).resolve().parent / "events.jsonl"


def default_baseline_path() -> Path:
    try:
        import app_paths
        return app_paths.data_dir() / "monitoring" / "baseline.json"
    except Exception:
        return Path(__file__).resolve().parent / "baseline.json"


def compute_stats(events: list[TimingEvent]) -> dict[str, OpStats]:
    """Grupper events per op og regn median/P95/max per op."""
    by_op: dict[str, list[float]] = {}
    for ev in events:
        by_op.setdefault(ev.op, []).append(ev.duration_ms)

    result: dict[str, OpStats] = {}
    for op, samples in by_op.items():
        if not samples:
            continue
        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        p95_idx = max(0, int(0.95 * n) - 1) if n > 1 else 0
        result[op] = OpStats(
            samples=n,
            median_ms=round(float(statistics.median(sorted_samples)), 3),
            p95_ms=round(float(sorted_samples[p95_idx]), 3),
            max_ms=round(float(sorted_samples[-1]), 3),
        )
    return result


def build_baseline(events: list[TimingEvent]) -> Baseline:
    """Bygg baseline-snapshot fra en liste events."""
    now = datetime.now(timezone.utc)
    iso = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    return Baseline(
        created_at=iso,
        source_events=len(events),
        ops=compute_stats(events),
    )


def save_baseline(baseline: Baseline, path: Optional[Path] = None) -> Path:
    """Lagre baseline som JSON."""
    out_path = Path(path) if path else default_baseline_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(baseline.to_dict(), fh, ensure_ascii=False, indent=2)
    return out_path


def load_baseline(path: Optional[Path] = None) -> Optional[Baseline]:
    """Les baseline fra disk. None hvis filen ikke finnes eller er korrupt."""
    in_path = Path(path) if path else default_baseline_path()
    if not in_path.exists():
        return None
    try:
        with in_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    try:
        return Baseline.from_dict(data)
    except Exception:
        return None


@dataclass
class Comparison:
    """Én sammenligning: op, baseline vs. gjeldende."""

    op: str
    baseline_median_ms: float
    current_median_ms: float
    baseline_samples: int
    current_samples: int

    @property
    def delta_ms(self) -> float:
        return self.current_median_ms - self.baseline_median_ms

    @property
    def delta_pct(self) -> float:
        if self.baseline_median_ms <= 0:
            return 0.0
        return (self.delta_ms / self.baseline_median_ms) * 100.0


def compare(
    baseline: Baseline,
    current_events: list[TimingEvent],
) -> list[Comparison]:
    """Sammenlign baseline mot gjeldende events. Returnerer sortert liste."""
    current_stats = compute_stats(current_events)
    all_ops = set(baseline.ops.keys()) | set(current_stats.keys())
    comparisons: list[Comparison] = []
    for op in all_ops:
        base = baseline.ops.get(op)
        curr = current_stats.get(op)
        comparisons.append(
            Comparison(
                op=op,
                baseline_median_ms=base.median_ms if base else 0.0,
                current_median_ms=curr.median_ms if curr else 0.0,
                baseline_samples=base.samples if base else 0,
                current_samples=curr.samples if curr else 0,
            )
        )
    # Sorter: regresjoner først (største positive delta), så forbedringer
    comparisons.sort(key=lambda c: c.delta_pct, reverse=True)
    return comparisons


# ---------------------------------------------------------------------------
# CLI

def _cli_save(events_path: Path, baseline_path: Path) -> int:
    events = read_events(events_path)
    if not events:
        print(f"Ingen events å lagre. Tom eller manglende fil: {events_path}", file=sys.stderr)
        return 1
    baseline = build_baseline(events)
    path = save_baseline(baseline, baseline_path)
    print(f"Lagret baseline: {path}")
    print(f"  Events: {baseline.source_events}  Ops: {len(baseline.ops)}  Opprettet: {baseline.created_at}")
    return 0


def _cli_show(baseline_path: Path) -> int:
    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(f"Fant ikke baseline: {baseline_path}", file=sys.stderr)
        return 1
    print(f"Baseline {baseline_path}")
    print(f"Opprettet: {baseline.created_at}  Events: {baseline.source_events}")
    print()
    print(f"{'Op':<40} {'Samples':>8} {'Median':>12} {'P95':>12} {'Max':>12}")
    print("-" * 90)
    for op in sorted(baseline.ops.keys()):
        s = baseline.ops[op]
        print(f"{op:<40} {s.samples:>8} {s.median_ms:>10.2f}ms {s.p95_ms:>10.2f}ms {s.max_ms:>10.2f}ms")
    return 0


def _cli_compare(events_path: Path, baseline_path: Path, *, warn_pct: float = 15.0) -> int:
    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(f"Fant ikke baseline: {baseline_path}. Kjør 'save' først.", file=sys.stderr)
        return 1
    events = read_events(events_path)
    if not events:
        print(f"Ingen events å sammenligne. Kjør appen først og generer timings.", file=sys.stderr)
        return 1

    comparisons = compare(baseline, events)
    regressions = [c for c in comparisons if c.delta_pct > warn_pct and c.baseline_samples > 0 and c.current_samples > 0]
    improvements = [c for c in comparisons if c.delta_pct < -warn_pct and c.baseline_samples > 0 and c.current_samples > 0]
    new_ops = [c for c in comparisons if c.baseline_samples == 0]
    removed_ops = [c for c in comparisons if c.current_samples == 0]

    print(f"Sammenligning mot baseline {baseline.created_at}")
    print(f"Gjeldende events: {len(events)}  Baseline events: {baseline.source_events}")
    print()
    print(f"{'Op':<40} {'Baseline':>12} {'Gjeldende':>12} {'Δ':>12} {'Δ %':>10}")
    print("-" * 90)
    for c in comparisons:
        if c.baseline_samples == 0 or c.current_samples == 0:
            continue
        marker = ""
        if c.delta_pct > warn_pct:
            marker = "  ⚠ regresjon"
        elif c.delta_pct < -warn_pct:
            marker = "  ✓ bedre"
        print(f"{c.op:<40} {c.baseline_median_ms:>10.2f}ms {c.current_median_ms:>10.2f}ms "
              f"{c.delta_ms:>+10.2f}ms {c.delta_pct:>+8.1f}%{marker}")

    if new_ops:
        print()
        print("Nye ops (ikke i baseline):")
        for c in new_ops:
            print(f"  + {c.op}  median={c.current_median_ms:.2f}ms")
    if removed_ops:
        print()
        print("Ops i baseline som ikke har samples nå:")
        for c in removed_ops:
            print(f"  - {c.op}  (baseline={c.baseline_median_ms:.2f}ms)")

    print()
    if regressions:
        print(f"⚠ {len(regressions)} regresjoner over {warn_pct:.0f}% tregere")
        return 2  # exit-kode for CI-integrasjon senere
    if improvements:
        print(f"✓ {len(improvements)} forbedringer over {warn_pct:.0f}% raskere")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__, file=sys.stderr)
        return 0

    cmd = argv[0]
    events_path = default_events_path()
    baseline_path = default_baseline_path()

    if cmd == "save":
        return _cli_save(events_path, baseline_path)
    if cmd == "show":
        return _cli_show(baseline_path)
    if cmd == "compare":
        return _cli_compare(events_path, baseline_path)

    print(f"Ukjent kommando: {cmd}. Bruk save / show / compare.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
