"""Tester for src.monitoring.baseline."""

from __future__ import annotations

import json
from pathlib import Path

from src.monitoring import baseline
from src.monitoring.events import TimingEvent


def _ev(op: str, duration_ms: float) -> TimingEvent:
    return TimingEvent(
        ts="2026-04-24T15:00:00.000Z",
        area=op.split(".", 1)[0] if "." in op else op,
        op=op,
        duration_ms=duration_ms,
        pid=1,
        meta={},
    )


class TestComputeStats:
    def test_empty_events(self) -> None:
        assert baseline.compute_stats([]) == {}

    def test_single_event_per_op(self) -> None:
        stats = baseline.compute_stats([_ev("sb.refresh", 100.0)])
        assert "sb.refresh" in stats
        s = stats["sb.refresh"]
        assert s.samples == 1
        assert s.median_ms == 100.0
        assert s.p95_ms == 100.0
        assert s.max_ms == 100.0

    def test_multiple_events_same_op(self) -> None:
        events = [
            _ev("sb.refresh", 100.0),
            _ev("sb.refresh", 200.0),
            _ev("sb.refresh", 150.0),
        ]
        stats = baseline.compute_stats(events)
        s = stats["sb.refresh"]
        assert s.samples == 3
        assert s.median_ms == 150.0
        assert s.max_ms == 200.0

    def test_groups_by_op(self) -> None:
        events = [
            _ev("sb.refresh", 100.0),
            _ev("analyse.pivot", 50.0),
            _ev("sb.refresh", 200.0),
        ]
        stats = baseline.compute_stats(events)
        assert stats["sb.refresh"].samples == 2
        assert stats["analyse.pivot"].samples == 1


class TestBaselineSaveLoad:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        events = [_ev("sb.refresh", 100.0), _ev("sb.base", 50.0)]
        b = baseline.build_baseline(events)
        path = tmp_path / "baseline.json"
        baseline.save_baseline(b, path)
        assert path.exists()

        loaded = baseline.load_baseline(path)
        assert loaded is not None
        assert loaded.source_events == 2
        assert "sb.refresh" in loaded.ops
        assert loaded.ops["sb.refresh"].median_ms == 100.0

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert baseline.load_baseline(tmp_path / "nope.json") is None

    def test_load_corrupt_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.json"
        path.write_text("ikke JSON", encoding="utf-8")
        assert baseline.load_baseline(path) is None

    def test_saved_json_is_valid(self, tmp_path: Path) -> None:
        events = [_ev("sb.refresh", 100.0)]
        b = baseline.build_baseline(events)
        path = tmp_path / "baseline.json"
        baseline.save_baseline(b, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "created_at" in data
        assert "source_events" in data
        assert "ops" in data
        assert "sb.refresh" in data["ops"]


class TestCompare:
    def test_compare_detects_regression(self) -> None:
        base_events = [_ev("sb.refresh", 100.0)] * 10
        curr_events = [_ev("sb.refresh", 200.0)] * 10
        b = baseline.build_baseline(base_events)
        comps = baseline.compare(b, curr_events)
        assert len(comps) == 1
        c = comps[0]
        assert c.op == "sb.refresh"
        assert c.baseline_median_ms == 100.0
        assert c.current_median_ms == 200.0
        assert c.delta_ms == 100.0
        assert c.delta_pct == 100.0  # Dobling = 100% regresjon

    def test_compare_detects_improvement(self) -> None:
        base_events = [_ev("sb.refresh", 200.0)] * 10
        curr_events = [_ev("sb.refresh", 100.0)] * 10
        b = baseline.build_baseline(base_events)
        comps = baseline.compare(b, curr_events)
        c = comps[0]
        assert c.delta_pct == -50.0  # Halvering = -50%

    def test_compare_new_op_not_in_baseline(self) -> None:
        b = baseline.build_baseline([_ev("sb.refresh", 100.0)])
        curr = [_ev("sb.refresh", 100.0), _ev("analyse.new", 80.0)]
        comps = baseline.compare(b, curr)
        new_ops = [c for c in comps if c.baseline_samples == 0]
        assert len(new_ops) == 1
        assert new_ops[0].op == "analyse.new"

    def test_compare_sorted_regressions_first(self) -> None:
        base = [
            _ev("a.x", 100.0),
            _ev("b.y", 100.0),
        ]
        curr = [
            _ev("a.x", 200.0),  # +100%
            _ev("b.y", 50.0),   # -50%
        ]
        b = baseline.build_baseline(base)
        comps = baseline.compare(b, curr)
        # Regresjonen skal komme først
        assert comps[0].op == "a.x"
        assert comps[-1].op == "b.y"

    def test_delta_pct_handles_zero_baseline(self) -> None:
        c = baseline.Comparison(
            op="x", baseline_median_ms=0.0,
            current_median_ms=100.0,
            baseline_samples=0, current_samples=1,
        )
        assert c.delta_pct == 0.0  # Ingen baseline → 0% (edge case)
