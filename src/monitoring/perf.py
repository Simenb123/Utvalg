"""Perf-API — ``timer()``, ``profile()`` og ``init_monitoring()``.

Hovedappen bruker dette API-et i stedet for å sette opp egne
``perf_counter()``-blokker. Events går automatisk til den globale
``EventStore`` som flusher til disk i bakgrunnstråd — ingen ytelsestap
i hovedtråden.

Bruk:

    from src.monitoring.perf import timer, profile, init_monitoring

    init_monitoring()  # Kalles én gang tidlig i App.__init__

    with timer("sb.refresh", meta={"rows": 126}):
        ...

    @profile("analyse.build_pivot")
    def _build_pivot(self, df):
        ...

Envflag:

- ``UTVALG_PROFILE=all`` — verbose stderr-print for alle events
- ``UTVALG_PROFILE=sb,analyse`` — kun valgte områder prints
- ``UTVALG_PROFILE_NONE=1`` — skru av event-logging helt
"""

from __future__ import annotations

import functools
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from src.monitoring.events import EventStore, make_event


# ---------------------------------------------------------------------------
# Global store (ett EventStore per prosess)

_STORE: Optional[EventStore] = None
_PROFILE_AREAS: Optional[set[str]] = None  # None = ingen stderr-print


def _parse_profile_env() -> Optional[set[str]]:
    """Tolker ``UTVALG_PROFILE`` og returnerer sett med områder eller None.

    - Tom/uset → None (ingen stderr-print)
    - "all" eller "*" → set med "*"
    - "sb,analyse" → {"sb", "analyse"}

    Bakoverkompat: ``UTVALG_PROFILE_SB=1`` → legger til "sb".
    ``UTVALG_PROFILE_REFRESH=1`` → legger til "analyse".
    """
    areas: set[str] = set()

    raw = os.environ.get("UTVALG_PROFILE", "").strip().lower()
    if raw:
        if raw in {"all", "*", "1", "true", "yes", "on"}:
            return {"*"}
        areas.update(p.strip() for p in raw.split(",") if p.strip())

    # Bakoverkompat med gamle flagg
    if os.environ.get("UTVALG_PROFILE_SB", "").strip().lower() in {"1", "true", "yes", "on"}:
        areas.add("sb")
    if os.environ.get("UTVALG_PROFILE_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}:
        areas.add("analyse")

    return areas or None


def init_monitoring(
    *,
    events_path: Optional[Path] = None,
    enabled: bool = True,
) -> Optional[EventStore]:
    """Initialiser global EventStore. Kall én gang ved app-start.

    Hvis ``UTVALG_PROFILE_NONE=1`` eller ``enabled=False`` → no-op.
    Hvis ``events_path`` ikke gitt, bruker vi ``app_paths.data_dir() /
    monitoring / events.jsonl``.
    """
    global _STORE, _PROFILE_AREAS

    if os.environ.get("UTVALG_PROFILE_NONE", "").strip().lower() in {"1", "true", "yes", "on"}:
        _STORE = None
        _PROFILE_AREAS = None
        return None
    if not enabled:
        return None

    if events_path is None:
        try:
            import app_paths
            events_path = app_paths.data_dir() / "monitoring" / "events.jsonl"
        except Exception:
            # Fallback: ved siden av denne modulen
            events_path = Path(__file__).resolve().parent / "events.jsonl"

    _PROFILE_AREAS = _parse_profile_env()

    if _STORE is not None:
        # Reinit: stopp gammel, start ny (sjelden tilfelle — f.eks. tester)
        try:
            _STORE.stop(flush=True)
        except Exception:
            pass

    store = EventStore(Path(events_path))
    store.start()
    _STORE = store
    return store


def shutdown_monitoring() -> None:
    """Stopp bakgrunnstråden og flush gjenværende events.

    Kalles ved app-exit. Idempotent.
    """
    global _STORE
    if _STORE is None:
        return
    try:
        _STORE.stop(flush=True)
    except Exception:
        pass
    _STORE = None


def is_enabled() -> bool:
    """Returnerer True hvis monitoring er aktivt."""
    return _STORE is not None


def _should_print(area: str) -> bool:
    if _PROFILE_AREAS is None:
        return False
    if "*" in _PROFILE_AREAS:
        return True
    return area in _PROFILE_AREAS


def _print_event(op: str, duration_ms: float, meta: Optional[dict]) -> None:
    try:
        meta_str = ""
        if meta:
            parts = [f"{k}={v}" for k, v in meta.items()]
            meta_str = " " + " ".join(parts)
        sys.stderr.write(f"[perf] {op} = {duration_ms:.3f}ms{meta_str}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Direkte event-recording (for imperative timing-kode)

def record_event(
    op: str,
    duration_ms: float,
    *,
    meta: Optional[dict] = None,
) -> None:
    """Direkte record uten timer-context.

    Brukes når kode allerede måler tiden selv (f.eks. via
    ``_tick``-mønster i saldobalanse_payload). For nye implementasjoner,
    foretrekk ``timer()`` context-manager eller ``profile()``-dekorator.
    """
    area = op.split(".", 1)[0] if "." in op else op
    if _STORE is not None:
        try:
            _STORE.record(make_event(op, duration_ms, meta=meta))
        except Exception:
            pass
    if _should_print(area):
        _print_event(op, duration_ms, meta)


# ---------------------------------------------------------------------------
# Timer context-manager

@contextmanager
def timer(op: str, *, meta: Optional[dict] = None) -> Iterator[None]:
    """Kontekstmanager som måler tiden og sender event til EventStore.

    Trygt å bruke selv om ``init_monitoring()`` ikke er kalt — da blir
    det bare en no-op (minimal overhead).
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        area = op.split(".", 1)[0] if "." in op else op
        if _STORE is not None:
            try:
                _STORE.record(make_event(op, duration_ms, meta=meta))
            except Exception:
                pass
        if _should_print(area):
            _print_event(op, duration_ms, meta)


# ---------------------------------------------------------------------------
# Profile decorator

def profile(op: str, *, meta: Optional[dict] = None) -> Callable[[Callable], Callable]:
    """Dekorator som wrapper en funksjon med ``timer()``.

    Praktisk for hele funksjoner der du vil time enkeltkall. Bruk
    ``timer()`` i stedet hvis du trenger å time en blokk inne i en
    funksjon.
    """

    def _decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            with timer(op, meta=meta):
                return fn(*args, **kwargs)

        return _wrapper

    return _decorator


# ---------------------------------------------------------------------------
# Test-hjelper

def _reset_for_tests() -> None:
    """Tøm global state. KUN for tester."""
    global _STORE, _PROFILE_AREAS
    if _STORE is not None:
        try:
            _STORE.stop(flush=False)
        except Exception:
            pass
    _STORE = None
    _PROFILE_AREAS = None
