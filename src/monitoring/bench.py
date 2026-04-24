"""Bench-suite-runner for Utvalg.

Kjører eksisterende bench-scripts under ``scripts/bench_*.py`` og
eventuelle framtidige bench-moduler. Eventene skrives til monitoring-
subsystemet så baseline.py kan sammenligne.

Bruk:

    python -m src.monitoring.bench              # Kjør alle bench'er
    python -m src.monitoring.bench --only sb    # Kjør kun sb-bench'er

Dette er en tynn wrapper som kjører subprocesses og samler opp.
Egentlige bench-logikken holdes i scripts/bench_*.py for å unngå
duplisering.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from src.monitoring.perf import init_monitoring, record_event, shutdown_monitoring


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def discover_bench_scripts() -> list[Path]:
    """Finn alle scripts/bench_*.py."""
    scripts_dir = _PROJECT_ROOT / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(scripts_dir.glob("bench_*.py"))


def run_bench_script(script_path: Path) -> tuple[int, float, str]:
    """Kjør et bench-script som subprocess. Returnerer (exit_code, duration_s, output_head).

    Bench-scripts antas å være idempotente og skrive sin egen output til stdout.
    Vi måler total-tid for hele scriptet og sender én oppsummert event.
    """
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=_PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        return 124, time.perf_counter() - t0, "timeout"
    except Exception as exc:
        return 1, time.perf_counter() - t0, f"feil: {exc}"
    duration = time.perf_counter() - t0
    output_head = result.stdout[:500] if result.stdout else ""
    return result.returncode, duration, output_head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kjør bench-suite for Utvalg")
    parser.add_argument(
        "--only",
        action="append",
        help="Kjør kun bench'er som matcher substring (kan brukes flere ganger)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List bench-scripts uten å kjøre dem",
    )
    args = parser.parse_args(argv)

    scripts = discover_bench_scripts()
    if args.only:
        scripts = [s for s in scripts if any(o in s.name for o in args.only)]

    if not scripts:
        print("Ingen bench-scripts funnet. Se scripts/bench_*.py", file=sys.stderr)
        return 1

    if args.list:
        for s in scripts:
            print(s.relative_to(_PROJECT_ROOT))
        return 0

    init_monitoring()
    total_start = time.perf_counter()
    failures: list[tuple[str, int]] = []
    try:
        for script_path in scripts:
            rel = script_path.relative_to(_PROJECT_ROOT)
            print(f"→ {rel}")
            exit_code, duration, output_head = run_bench_script(script_path)
            op_name = f"bench.{script_path.stem}"
            record_event(op_name, duration * 1000.0, meta={"exit": exit_code})
            status = "OK" if exit_code == 0 else f"FEIL (exit={exit_code})"
            print(f"  {status} · {duration:.2f}s")
            if exit_code != 0:
                failures.append((script_path.name, exit_code))
                if output_head:
                    print("  Første 500 tegn av output:")
                    for line in output_head.splitlines():
                        print(f"    {line}")

        total_duration = time.perf_counter() - total_start
        print()
        print(f"Ferdig. Total: {total_duration:.2f}s. Bench'er: {len(scripts)}. Feil: {len(failures)}.")
    finally:
        shutdown_monitoring()

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
