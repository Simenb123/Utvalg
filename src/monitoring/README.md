# src/monitoring — ytelsesovervåking

Sentralt subsystem for å måle, logge og visualisere ytelsen i Utvalg
under utvikling.

## Oversikt

```
perf.py      → timer(), profile(), init_monitoring() — API for hovedappen
events.py    → EventStore (in-memory buffer + async JSONL-flush)
dashboard.py → Standalone Tk-sidekick (fase 2 — kommer)
baseline.py  → Baseline-verktøy (fase 3 — kommer)
bench.py     → Bench-suite-runner (fase 3 — kommer)
```

## Bruk i hovedappen

```python
from src.monitoring.perf import timer, profile

# Kontekstmanager — for blokker inne i en funksjon
with timer("sb.refresh", meta={"rows": 126, "cache": "miss"}):
    ...

# Dekorator — for hele funksjoner
@profile("analyse.build_pivot")
def _build_pivot(self, df):
    ...
```

`init_monitoring()` kalles én gang tidlig i `App.__init__` i `ui_main.py`.
Events blir persistent lagret i
`<data_dir>/monitoring/events.jsonl`.

## Envflag

| Flag | Effekt |
|---|---|
| (ingen) | Events lagres til disk, ingen stderr-print |
| `UTVALG_PROFILE=all` | Events prints til stderr i tillegg |
| `UTVALG_PROFILE=sb,analyse` | Kun valgte områder prints |
| `UTVALG_PROFILE_NONE=1` | Event-logging helt av |

Område-navnet utledes fra første del av `op` før første punktum:
`sb.refresh` → area `sb`. `analyse.pivot.build` → area `analyse`.

## Design-notater

- `timer()` har ingen ytelsestap når monitoring er av (<200ns per kall).
- `EventStore` bruker bakgrunnstråd for disk-skriving → hovedtråden
  blokkerer aldri på IO.
- Events <1ms (MIN_DURATION_MS) forkastes automatisk for å unngå støy.
- Filen roterer ved 10 MB. Opptil 5 historiske filer beholdes.
- Alle disk-operasjoner er try/except — monitoring skal ALDRI
  krasje hovedappen.

## Bakoverkompat

Eksisterende `UTVALG_PROFILE_REFRESH` og `UTVALG_PROFILE_SB` beholdes
under migreringen (Fase 4 i planen). Når alle moduler er migrert til
`timer()` kan de gamle flaggene fjernes.
