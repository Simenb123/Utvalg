"""Ambient "current action" brukt av innebygde eksporter til forside-fane.

Handling-siden pusher en `ActionContext` rett før den kaller en innebygd
generator (f.eks. `AnalysePage._export_ib_ub_kontroll`). Eksporteren leser
via `action_context.current()` og kan legge ved en "Beskrivelse"-fane uten
å måtte endre signaturen sin.

Kontekst er kun satt innenfor `push()`-blokken — eksporter som kjøres
uten handling-kobling får `None` og hopper over forside-fanen.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Optional


@dataclass
class ActionContext:
    action_key: str
    handling_navn: str
    handling_type: str = ""
    omraade: str = ""
    regnr: str = ""
    beskrivelse: str = ""
    kommentar: str = ""
    kjort_av: str = ""
    kjort_at: str = ""
    client: str = ""
    year: str = ""
    workpaper_navn: str = ""
    ekstra: dict[str, str] = field(default_factory=dict)


_CURRENT: Optional[ActionContext] = None


def current() -> Optional[ActionContext]:
    return _CURRENT


def set_current(ctx: Optional[ActionContext]) -> None:
    global _CURRENT
    _CURRENT = ctx


def clear() -> None:
    global _CURRENT
    _CURRENT = None


@contextmanager
def push(ctx: ActionContext) -> Iterator[ActionContext]:
    global _CURRENT
    prev = _CURRENT
    if not ctx.kjort_at:
        ctx.kjort_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _CURRENT = ctx
    try:
        yield ctx
    finally:
        _CURRENT = prev
