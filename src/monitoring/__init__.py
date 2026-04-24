"""Ytelsesovervåking for Utvalg.

Sentralt API for å måle og overvåke ytelse i Utvalg. Eventene
lagres persistent på disk (events.jsonl) og kan vises live i
sidekick-dashboarden (``python -m src.monitoring.dashboard``).

Quick-start:

    from src.monitoring.perf import timer, profile

    with timer("sb.refresh", meta={"rows": 126}):
        # ... tung kode
        ...

    @profile("analyse.build_pivot")
    def _build_pivot(self, df):
        ...

Se `src/monitoring/README.md` for mer detaljert bruk.
"""

from src.monitoring.perf import (
    init_monitoring,
    is_enabled,
    profile,
    timer,
)

__all__ = [
    "init_monitoring",
    "is_enabled",
    "profile",
    "timer",
]
