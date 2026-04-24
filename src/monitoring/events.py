"""EventStore — in-memory buffer + async flush til JSONL på disk.

Hovedappen kaller ``store.record(event)``, som er en rask lock-append til
en in-memory liste. En bakgrunnstråd flusher bufferet til disk hvert
``flush_interval_s``. Hovedtråden blokkerer aldri på disk-IO.

Events skrives som én JSON-linje per event (JSONL). Filen roteres når
den passerer ``rotate_bytes``; gamle filer beholdes som
``events.1.jsonl``, ``events.2.jsonl`` osv.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class TimingEvent:
    """Én timing-måling. Serialiseres som JSONL.

    Felter:
    - ``ts``: ISO-8601 i UTC (Z-suffix)
    - ``area``: første del av ``op`` før første punktum (sb, analyse, ...).
      Brukes til filtrering i dashboarden.
    - ``op``: fullt operasjonsnavn (f.eks. ``"sb.refresh"``)
    - ``duration_ms``: millisekunder, avrundet til 3 desimaler
    - ``pid``: prosess-id — skiller samtidige kjøringer i filen
    - ``meta``: valgfri ekstra kontekst (rader, filnavn, cache-hit/miss)
    """

    ts: str
    area: str
    op: str
    duration_ms: float
    pid: int
    meta: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


def _derive_area(op: str) -> str:
    op_clean = str(op or "").strip()
    if not op_clean:
        return ""
    idx = op_clean.find(".")
    if idx < 0:
        return op_clean
    return op_clean[:idx]


def make_event(
    op: str,
    duration_ms: float,
    *,
    meta: Optional[dict] = None,
    ts: Optional[datetime] = None,
) -> TimingEvent:
    """Fabrikk som fyller inn alle felter på standardisert måte."""
    when = ts or datetime.now(timezone.utc)
    iso = when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"
    return TimingEvent(
        ts=iso,
        area=_derive_area(op),
        op=str(op or ""),
        duration_ms=round(float(duration_ms), 3),
        pid=os.getpid(),
        meta=dict(meta or {}),
    )


class EventStore:
    """Thread-safe event-buffer med async flush til JSONL-fil.

    Bufferet holder events i minnet. En daemon-tråd flusher periodisk til
    ``events_path``. Ved app-exit flushes bufferet én siste gang.

    Rotasjon: når fil-størrelse overstiger ``rotate_bytes``, flyttes den
    til ``events.1.jsonl``, eksisterende ``events.N.jsonl`` blir til
    ``events.(N+1).jsonl``, opp til ``max_rotated`` filer.
    """

    # Minimum varighet for å bli lagret. Trivielle events (<1ms) ignoreres
    # — de ville bare gi støy og marginalt disk-bruk.
    MIN_DURATION_MS: float = 1.0

    def __init__(
        self,
        events_path: Path,
        *,
        flush_interval_s: float = 2.0,
        rotate_bytes: int = 10 * 1024 * 1024,  # 10 MB
        max_rotated: int = 5,
    ) -> None:
        self.events_path = Path(events_path)
        self.flush_interval_s = float(flush_interval_s)
        self.rotate_bytes = int(rotate_bytes)
        self.max_rotated = int(max_rotated)

        self._buffer: list[TimingEvent] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API

    def record(self, event: TimingEvent) -> None:
        """Legg event i bufferet. Rask (lock + append)."""
        if event.duration_ms < self.MIN_DURATION_MS:
            return
        with self._lock:
            self._buffer.append(event)

    def start(self) -> None:
        """Start flush-tråden. Idempotent."""
        if self._started:
            return
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._stop.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="monitoring-flush",
            daemon=True,
        )
        self._flush_thread.start()
        self._started = True

    def stop(self, *, flush: bool = True) -> None:
        """Stopp flush-tråden. Hvis ``flush=True`` flushes bufferet først."""
        self._stop.set()
        thread = self._flush_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.flush_interval_s + 1.0)
        if flush:
            self._flush_once()
        self._started = False

    def flush_now(self) -> int:
        """Tving umiddelbar flush. Returnerer antall events skrevet."""
        return self._flush_once()

    def buffered_count(self) -> int:
        with self._lock:
            return len(self._buffer)

    # ------------------------------------------------------------------
    # Internals

    def _flush_loop(self) -> None:
        while not self._stop.wait(self.flush_interval_s):
            try:
                self._flush_once()
            except Exception:
                # Skal aldri stoppe bakgrunnstråden
                pass

    def _flush_once(self) -> int:
        with self._lock:
            if not self._buffer:
                return 0
            to_write = self._buffer
            self._buffer = []

        try:
            # Rotér om nødvendig før skriv
            self._maybe_rotate()
            with self.events_path.open("a", encoding="utf-8") as fh:
                for ev in to_write:
                    fh.write(ev.to_json_line())
                    fh.write("\n")
        except Exception:
            # Disk full / read-only / permission — events går tapt men
            # hovedapp må aldri krasje på grunn av monitoring
            return 0
        return len(to_write)

    def _maybe_rotate(self) -> None:
        path = self.events_path
        try:
            if not path.exists():
                return
            if path.stat().st_size < self.rotate_bytes:
                return
        except Exception:
            return
        # Rotér: events.N.jsonl → events.(N+1).jsonl, nyeste først
        try:
            for n in range(self.max_rotated - 1, 0, -1):
                src = path.with_suffix(f".{n}.jsonl")
                dst = path.with_suffix(f".{n + 1}.jsonl")
                if src.exists():
                    try:
                        if dst.exists():
                            dst.unlink()
                    except Exception:
                        pass
                    try:
                        src.rename(dst)
                    except Exception:
                        pass
            # events.jsonl → events.1.jsonl
            first_rotated = path.with_suffix(".1.jsonl")
            try:
                if first_rotated.exists():
                    first_rotated.unlink()
            except Exception:
                pass
            try:
                path.rename(first_rotated)
            except Exception:
                pass
        except Exception:
            pass


def read_events(path: Path, *, limit: Optional[int] = None) -> list[TimingEvent]:
    """Les events fra JSONL-fil. Tålt for korrupte linjer.

    Returnerer en liste av TimingEvent. Hvis ``limit`` gitt, tar de siste N.
    """
    if not Path(path).exists():
        return []
    events: list[TimingEvent] = []
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    obj = json.loads(line_s)
                except Exception:
                    continue
                try:
                    events.append(
                        TimingEvent(
                            ts=str(obj.get("ts", "")),
                            area=str(obj.get("area", "")),
                            op=str(obj.get("op", "")),
                            duration_ms=float(obj.get("duration_ms", 0.0)),
                            pid=int(obj.get("pid", 0)),
                            meta=dict(obj.get("meta") or {}),
                        )
                    )
                except Exception:
                    continue
    except Exception:
        return events
    if limit is not None and limit > 0 and len(events) > limit:
        events = events[-limit:]
    return events


def tail_events(path: Path, since_offset: int = 0) -> tuple[list[TimingEvent], int]:
    """Les events fra en gitt byte-offset og ut til EOF.

    Returnerer ``(events, new_offset)``. Dashboarden kan polle med
    siste offset for å få kun nye events siden sist.

    Hvis filen er mindre enn ``since_offset`` (f.eks. rotert),
    starter vi fra begynnelsen.
    """
    p = Path(path)
    if not p.exists():
        return [], 0
    try:
        size = p.stat().st_size
    except Exception:
        return [], since_offset
    start = since_offset if 0 <= since_offset <= size else 0
    events: list[TimingEvent] = []
    try:
        with p.open("r", encoding="utf-8") as fh:
            fh.seek(start)
            for line in fh:
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    obj = json.loads(line_s)
                except Exception:
                    continue
                try:
                    events.append(
                        TimingEvent(
                            ts=str(obj.get("ts", "")),
                            area=str(obj.get("area", "")),
                            op=str(obj.get("op", "")),
                            duration_ms=float(obj.get("duration_ms", 0.0)),
                            pid=int(obj.get("pid", 0)),
                            meta=dict(obj.get("meta") or {}),
                        )
                    )
                except Exception:
                    continue
    except Exception:
        pass
    try:
        new_offset = p.stat().st_size
    except Exception:
        new_offset = size
    return events, new_offset
