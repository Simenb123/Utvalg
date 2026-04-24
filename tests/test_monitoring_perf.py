"""Tester for src.monitoring.perf + events — timing-API og event-store."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from src.monitoring import events as events_mod
from src.monitoring import perf


# ---------------------------------------------------------------------------
# TimingEvent

class TestTimingEvent:
    def test_to_json_line_roundtrip(self) -> None:
        ev = events_mod.make_event("sb.refresh", 123.456, meta={"rows": 126})
        line = ev.to_json_line()
        obj = json.loads(line)
        assert obj["op"] == "sb.refresh"
        assert obj["area"] == "sb"
        assert obj["duration_ms"] == 123.456
        assert obj["meta"] == {"rows": 126}
        assert obj["pid"] == os.getpid()
        assert obj["ts"].endswith("Z")

    def test_area_derived_from_op(self) -> None:
        assert events_mod.make_event("sb.refresh", 1).area == "sb"
        assert events_mod.make_event("analyse.pivot.build", 1).area == "analyse"
        assert events_mod.make_event("lonely", 1).area == "lonely"
        assert events_mod.make_event("", 1).area == ""

    def test_duration_rounded_to_3_decimals(self) -> None:
        ev = events_mod.make_event("x.y", 1.23456789)
        assert ev.duration_ms == 1.235


# ---------------------------------------------------------------------------
# EventStore

class TestEventStore:
    def test_record_respects_min_duration(self, tmp_path: Path) -> None:
        store = events_mod.EventStore(tmp_path / "events.jsonl")
        store.record(events_mod.make_event("a.b", 0.5))  # Under threshold (1ms)
        store.record(events_mod.make_event("a.b", 2.0))  # Over threshold
        assert store.buffered_count() == 1

    def test_flush_writes_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        store = events_mod.EventStore(path)
        store.record(events_mod.make_event("a.b", 5.0))
        store.record(events_mod.make_event("c.d", 7.0, meta={"x": 1}))
        n = store.flush_now()
        assert n == 2
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert obj["op"] == "a.b"

    def test_flush_appends_across_calls(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        store = events_mod.EventStore(path)
        store.record(events_mod.make_event("a.b", 5.0))
        store.flush_now()
        store.record(events_mod.make_event("c.d", 7.0))
        store.flush_now()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_buffer_empty_after_flush(self, tmp_path: Path) -> None:
        store = events_mod.EventStore(tmp_path / "events.jsonl")
        store.record(events_mod.make_event("a.b", 5.0))
        store.flush_now()
        assert store.buffered_count() == 0

    def test_flush_on_empty_buffer_is_noop(self, tmp_path: Path) -> None:
        store = events_mod.EventStore(tmp_path / "events.jsonl")
        assert store.flush_now() == 0
        assert not (tmp_path / "events.jsonl").exists()

    def test_rotation_when_size_exceeds_threshold(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        store = events_mod.EventStore(path, rotate_bytes=200, max_rotated=3)
        # Skriv nok events til å overstige 200 bytes
        for i in range(20):
            store.record(events_mod.make_event(f"x.y{i}", 5.0))
        store.flush_now()
        # Andre flush skal se at filen er stor og rotere før skriv
        for i in range(20):
            store.record(events_mod.make_event(f"z.w{i}", 5.0))
        store.flush_now()
        # events.jsonl skal eksistere + events.1.jsonl
        assert path.exists()
        assert (tmp_path / "events.1.jsonl").exists()

    def test_start_stop_is_idempotent(self, tmp_path: Path) -> None:
        store = events_mod.EventStore(tmp_path / "events.jsonl", flush_interval_s=0.05)
        store.start()
        store.start()  # Skal ikke krasje eller lage ny tråd
        store.stop()
        store.stop()  # Samme

    def test_background_thread_flushes_periodically(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        store = events_mod.EventStore(path, flush_interval_s=0.05)
        store.start()
        try:
            store.record(events_mod.make_event("a.b", 5.0))
            # Vent på at bakgrunnstråd skal flushe
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if path.exists() and path.stat().st_size > 0:
                    break
                time.sleep(0.05)
            assert path.exists() and path.stat().st_size > 0
        finally:
            store.stop()


# ---------------------------------------------------------------------------
# read_events + tail_events

class TestReadEvents:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert events_mod.read_events(tmp_path / "nope.jsonl") == []

    def test_read_returns_parsed_events(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text(
            '{"ts":"2026-04-24T14:00:00Z","area":"sb","op":"sb.x","duration_ms":5,"pid":1,"meta":{}}\n'
            '{"ts":"2026-04-24T14:00:01Z","area":"a","op":"a.b","duration_ms":10,"pid":1,"meta":{"k":"v"}}\n',
            encoding="utf-8",
        )
        result = events_mod.read_events(path)
        assert len(result) == 2
        assert result[0].op == "sb.x"
        assert result[1].meta == {"k": "v"}

    def test_read_tolerates_corrupt_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text(
            '{"ts":"T","area":"a","op":"a.b","duration_ms":1,"pid":1,"meta":{}}\n'
            'ikke json\n'
            '{"ts":"T","area":"c","op":"c.d","duration_ms":2,"pid":1,"meta":{}}\n',
            encoding="utf-8",
        )
        result = events_mod.read_events(path)
        assert len(result) == 2
        assert [e.op for e in result] == ["a.b", "c.d"]

    def test_read_respects_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        lines = [
            json.dumps({"ts": "T", "area": "a", "op": f"a.{i}",
                        "duration_ms": 1, "pid": 1, "meta": {}})
            for i in range(10)
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = events_mod.read_events(path, limit=3)
        assert [e.op for e in result] == ["a.7", "a.8", "a.9"]


class TestTailEvents:
    def test_tail_from_start_returns_all(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text(
            '{"ts":"T","area":"a","op":"a.1","duration_ms":1,"pid":1,"meta":{}}\n'
            '{"ts":"T","area":"a","op":"a.2","duration_ms":1,"pid":1,"meta":{}}\n',
            encoding="utf-8",
        )
        events, offset = events_mod.tail_events(path, since_offset=0)
        assert len(events) == 2
        assert offset == path.stat().st_size

    def test_tail_from_offset_skips_old(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text(
            '{"ts":"T","area":"a","op":"a.1","duration_ms":1,"pid":1,"meta":{}}\n',
            encoding="utf-8",
        )
        first_size = path.stat().st_size

        # Legg til én ny
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"ts":"T","area":"a","op":"a.2","duration_ms":1,"pid":1,"meta":{}}\n')

        events, offset = events_mod.tail_events(path, since_offset=first_size)
        assert [e.op for e in events] == ["a.2"]
        assert offset == path.stat().st_size

    def test_tail_missing_file_returns_empty(self, tmp_path: Path) -> None:
        events, offset = events_mod.tail_events(tmp_path / "nope.jsonl", since_offset=0)
        assert events == []
        assert offset == 0


# ---------------------------------------------------------------------------
# perf.timer + perf.profile

class TestTimer:
    def setup_method(self) -> None:
        perf._reset_for_tests()

    def teardown_method(self) -> None:
        perf._reset_for_tests()

    def test_timer_noop_when_uninitialized(self) -> None:
        # Skal ikke krasje selv om init_monitoring ikke er kalt
        with perf.timer("x.y"):
            pass
        assert not perf.is_enabled()

    def test_timer_records_event(self, tmp_path: Path) -> None:
        store = perf.init_monitoring(events_path=tmp_path / "events.jsonl")
        assert store is not None
        try:
            with perf.timer("sb.refresh", meta={"rows": 10}):
                time.sleep(0.005)  # 5ms — over threshold
            # Flush så vi kan lese fra disk
            store.flush_now()
            result = events_mod.read_events(tmp_path / "events.jsonl")
            assert len(result) == 1
            assert result[0].op == "sb.refresh"
            assert result[0].meta == {"rows": 10}
            assert result[0].duration_ms >= 4.0  # noe mindre toleranse for Windows-timing
        finally:
            perf.shutdown_monitoring()

    def test_timer_skips_events_under_threshold(self, tmp_path: Path) -> None:
        store = perf.init_monitoring(events_path=tmp_path / "events.jsonl")
        try:
            with perf.timer("fast.op"):
                pass  # <1ms — skal filtreres bort
            store.flush_now()
            assert events_mod.read_events(tmp_path / "events.jsonl") == []
        finally:
            perf.shutdown_monitoring()

    def test_profile_decorator(self, tmp_path: Path) -> None:
        store = perf.init_monitoring(events_path=tmp_path / "events.jsonl")
        try:
            @perf.profile("test.decorated")
            def slow():
                time.sleep(0.005)
                return 42

            assert slow() == 42
            store.flush_now()
            result = events_mod.read_events(tmp_path / "events.jsonl")
            assert any(e.op == "test.decorated" for e in result)
        finally:
            perf.shutdown_monitoring()

    def test_profile_none_flag_disables(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("UTVALG_PROFILE_NONE", "1")
        store = perf.init_monitoring(events_path=tmp_path / "events.jsonl")
        assert store is None
        with perf.timer("x.y"):
            time.sleep(0.005)
        assert not perf.is_enabled()


class TestPerfEnv:
    def test_parse_profile_env_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("UTVALG_PROFILE", raising=False)
        assert perf._parse_profile_env() is None

    def test_parse_profile_env_all(self, monkeypatch) -> None:
        monkeypatch.setenv("UTVALG_PROFILE", "all")
        assert perf._parse_profile_env() == {"*"}
        monkeypatch.setenv("UTVALG_PROFILE", "1")
        assert perf._parse_profile_env() == {"*"}

    def test_parse_profile_env_areas(self, monkeypatch) -> None:
        monkeypatch.setenv("UTVALG_PROFILE", "sb,analyse")
        assert perf._parse_profile_env() == {"sb", "analyse"}
