# Ytelsesovervåknings-subsystem (`src/monitoring/`)

**Moduler:**
- [src/monitoring/perf.py](../../src/monitoring/perf.py) — `timer()`, `profile()`, `record_event()`, `init_monitoring()`
- [src/monitoring/events.py](../../src/monitoring/events.py) — `TimingEvent`, `EventStore`, `read_events`, `tail_events`
- [src/monitoring/dashboard.py](../../src/monitoring/dashboard.py) — standalone Tk-sidekick
- [src/monitoring/baseline.py](../../src/monitoring/baseline.py) — baseline-snapshot + regresjons-sammenligning
- [src/monitoring/bench.py](../../src/monitoring/bench.py) — wrapper for `scripts/bench_*.py`

**Sist oppdatert:** 2026-04-24
**Forutgående:** [ytelse_status_og_plan.md](ytelse_status_og_plan.md) (tiltak 1-5, status frem til 2026-04-23)

## Formål

Utvalg har lenge hatt ad-hoc profilerings-kode spredt i flere moduler (`UTVALG_PROFILE_REFRESH`, `UTVALG_PROFILE_SB`, ad-hoc `perf_counter()`). Det fungerte, men krevde at utviklere lette opp ulike flagg, konsoll-output gikk tapt, og baseline-sammenligning over tid var umulig.

Dette subsystemet løser tre problemer:
1. **Én felles API** — `timer()`/`profile()`/`record_event()` i stedet for ad-hoc `perf_counter()`
2. **Persistent event-logg** — events overlever app-restart og kan sammenlignes med baseline
3. **Live sidekick-dashboard** — se ytelsesdata mens du utvikler, uten å lese stderr

## Flyt

```
Hovedapp (Utvalg)                         Sidekick (dashboard)
─────────────────                         ───────────────────
with timer("sb.refresh"):                 events.jsonl
    ...                                   ├─ tail fil (2 Hz polling)
                                          └─ vis live-tabell + sparkline
    │
    ▼
EventStore (in-memory buffer)
    │
    ▼ (async flush hver 2s, bakgrunnstråd)
events.jsonl (<data_dir>/monitoring/events.jsonl)
    │
    ▼ (roterer ved 10 MB → events.1.jsonl, events.2.jsonl, ...)
```

Hovedappen blokkerer aldri på disk-skriving. `perf_counter()` + threshold-check er ~500ns per event, som er under måleterskelen.

## API

### Hovedbruk

```python
from src.monitoring.perf import timer, profile, record_event

# Kontekstmanager
with timer("sb.refresh", meta={"rows": 126, "cache": "miss"}):
    ...

# Dekorator
@profile("analyse.build_pivot")
def _build_pivot(self, df):
    ...

# Imperativ recording (når du allerede måler tiden selv)
_t0 = time.perf_counter()
... # tung kode
record_event("sb.base.ownership_map", (time.perf_counter() - _t0) * 1000.0)
```

### Initialisering

```python
# I ui_main.App.__init__ — kalles én gang
from src.monitoring.perf import init_monitoring
init_monitoring()
```

Uten `init_monitoring()` blir `timer()` en no-op (minimal overhead). Hovedappen initialiserer alltid automatisk.

### Events-format

```json
{"ts": "2026-04-24T14:03:22.153Z", "area": "sb", "op": "sb.refresh",
 "duration_ms": 1200, "pid": 12345, "meta": {"rows": 126, "cache": "miss"}}
```

- `area`: første del av `op` før første punktum. Brukes av dashboard til filtrering.
- `duration_ms`: millisekunder, avrundet til 3 desimaler. Events <1ms forkastes.
- `meta`: fri-form dict med kontekst (rader, filnavn, cache-treff).
- `pid`: skiller samtidige kjøringer (f.eks. hvis bruker har to Utvalg-vinduer åpne).

## Envflag

| Flag | Effekt |
|---|---|
| (ingen) | Events lagres til disk, ingen stderr-print |
| `UTVALG_PROFILE=all` | Events prints til stderr i tillegg (alle områder) |
| `UTVALG_PROFILE=sb,analyse` | Kun valgte områder prints |
| `UTVALG_PROFILE_SB=1` | Bakoverkompat — samme som `UTVALG_PROFILE=sb` |
| `UTVALG_PROFILE_REFRESH=1` | Bakoverkompat — samme som `UTVALG_PROFILE=analyse` |
| `UTVALG_PROFILE_NONE=1` | Skru av event-logging helt |

Merk: disk-skriving er **alltid på**. Flagg styrer kun stderr-print for live debugging.

## Sidekick-dashboarden

```bash
python -m src.monitoring.dashboard
```

Åpner Tk-vindu som tailer `events.jsonl` og viser:
- **Live-tabell** med tid, område, op, varighet, meta
- **Filter**: område (dropdown), tidsvindu (1/5/30 min), min varighet
- **Detalj-panel**: median/P95/max for valgt op + sparkline over siste 20 samples
- **Pause/fortsett** og **Tøm visning**

Dashboarden kjøres som egen prosess ved siden av hovedappen. Ingen shared state — tåler at hovedappen krasjer midt i.

## Baseline + regresjonsdeteksjon

```bash
# Lagre gjeldende events som baseline
python -m src.monitoring.baseline save

# Sammenlign gjeldende mot baseline
python -m src.monitoring.baseline compare

# Print baseline-statistikk
python -m src.monitoring.baseline show
```

Baseline lagres som JSON i `<data_dir>/monitoring/baseline.json` med per-op statistikk (samples, median, P95, max). `compare` rapporterer:
- Ops som er ≥15% tregere → **regresjon** (exit-kode 2)
- Ops som er ≥15% raskere → **forbedring**
- Ops i baseline som mangler samples → potensielt død kode
- Ops som ikke er i baseline → nytt målepunkt

Eksit-kodene gjør at `compare` kan brukes som pre-push hook eller CI-gate senere.

## Bench-suite

```bash
# Kjør alle scripts/bench_*.py
python -m src.monitoring.bench

# Kjør kun noen
python -m src.monitoring.bench --only sb --only analyse

# Bare list
python -m src.monitoring.bench --list
```

Wrapper som finner `scripts/bench_*.py` og kjører dem som subprocess. Total-tiden per script logges som `bench.<navn>`-event. Brukes typisk slik:

```bash
python -m src.monitoring.bench
python -m src.monitoring.baseline save
# gjør endringer i koden
python -m src.monitoring.bench
python -m src.monitoring.baseline compare
```

## Arkitektur-valg

### Hvorfor egen prosess for dashboard?

- **Ingen hovedapp-påvirkning** — Tk-event-loop'er er ikke trådsikre, og kjøring i samme prosess ville kreve å dele loop'en.
- **Dashboarden tåler at Utvalg krasjer** — events er allerede på disk.
- **Fremtidig Admin-popup** skal vise samme data men som Toplevel inne i hovedappen. Koden deles via GUI-moduler; event-kilden er uendret.

### Hvorfor JSONL?

- **Append-only** — ingen låsing av hele filen
- **Menneskelig lesbart** — `tail -f events.jsonl` virker
- **Korrupt-tolerant** — én dårlig linje ødelegger ikke resten
- **Standardverktøy** fungerer (`grep`, `jq`, Python `json`)

Alternativet (SQLite) gir spørrings-fleksibilitet men krever transaksjoner, noe som komplisererer bakgrunnstråden.

### Hvorfor threshold på 1ms?

Events under 1ms gir støy uten informasjon. En typisk Analyse-refresh har 50-200 timer-kall; uten threshold ville vi logget mange tusen events per klient-last, som blåser opp filen uten nytte.

## Migrering fra ad-hoc timing

Moduler som tidligere hadde egne `UTVALG_PROFILE_*`-blokker er migrert til `record_event()`:

| Modul | Gammelt mønster | Nytt event-navn |
|---|---|---|
| `saldobalanse_payload.py` | `_tick()` + stderr | `sb.base.<fase>` |
| `page_saldobalanse.py` | stderr + `log.debug` | `sb.refresh`, `sb.refresh.{base,postprocess,render}` |
| `page_analyse.py:_refresh_pivot` | `_stages`-dict + `log.warning` | `analyse.refresh.<fase>` |
| `page_analyse_pivot.py` | stderr | `analyse.pivot.dispatch` |
| `page_analyse_rl_render.py` | `_mark()` + log | `analyse.rl_pivot.<fase>` |
| `analyse_mapping_ui.py` | `_t()` + log | `analyse.mapping_issues.<fase>` |
| `motpost/combinations_popup.py` | `log.debug` | `motpost.combinations.{display_cache, drilldown_cache}` |

A07-filer (`a07_feature/page_a07_mapping_candidates.py`) er **ikke** migrert — pågående refaktor av annen utvikler, berøres ikke.

## Admin-popup-integrasjon (senere)

Når Admin-refaktoren er ferdig, legges en "Åpne ytelsesmonitor"-knapp i Admin-fanen. Den kaller en ny `src.monitoring.dashboard.open_as_popup(master)`-funksjon som oppretter samme GUI inne i en Toplevel i stedet for egen Tk-instans. Ingen kodeendring i `perf.py` eller `events.py` trengs.

## Test-dekning

- [tests/test_monitoring_perf.py](../../tests/test_monitoring_perf.py) — 26 tester: EventStore, timer, profile, env-flagg
- [tests/test_monitoring_baseline.py](../../tests/test_monitoring_baseline.py) — 13 tester: compute_stats, save/load, compare

Dashboard-koden har ikke auto-tester (Tk-GUI er vanskelig å teste headless) — smoke-testes manuelt ved å åpne vinduet.

## Fremtidig arbeid (parkert)

- **Dashboard Admin-popup-modus** — når Admin-refaktoren er stabil
- **Pre-push hook** som kjører `baseline compare` og hindrer push hvis >15% regresjon
- **Graf-sammenligning i dashboard** — vis baseline som stiplet linje i sparkline
- **Flamegraph-generator** — agreger `*.<fase>`-events til kall-hierarki for dypere profiling
- **Fjerning av bakoverkompat-flagg** `UTVALG_PROFILE_SB`/`_REFRESH` når alle utviklere har vent seg til `UTVALG_PROFILE=sb` / `=analyse`
