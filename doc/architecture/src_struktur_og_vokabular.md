# src/-struktur og felles vokabular

**Sist oppdatert:** 2026-04-26 (etter pilot 13 — 11 sider migrert + alle shims ryddet)

Beskriver organiseringen av kodebasen rundt `src/`-mappen som ble innført i
April 2026, det felles kolonne-vokabularet i `src/shared/columns_vocabulary.py`,
og det typede pivot-cache-systemet på `AnalysePage`.

Mappestrukturen utviklet seg gjennom piloter 1-13 (april 2026):
- Pilot 1-11: 11 sider/handlinger flyttet til `src/`
- Pilot 12-13: 67 toppnivå-shim-filer ryddet bort etter at importerere ble migrert

## Bakgrunn og motivasjon

Repoet hadde 373+ Python-filer i rota — flate, vanskelig å navigere, uten
naturlig gruppering. Tre konkrete problemer drev dette arbeidet:

1. **Faner var spredt på tvers av mange filer** uten gruppering. Analyse-fanen
   alene har 28+ filer (`page_analyse*.py` + `analyse_*.py`).
2. **Hardkodede kolonne-labels overalt.** Samme konsept ("UB i fjor"/"UB fjor"/
   "UB 2024") fikk forskjellig tekst i hver fane. Brukeren måtte mentalt
   oversette mellom variantene.
3. **`_pivot_df_last` overskrev seg selv** med ulike skjemaer (regnr-keyed
   for RL-modus, Konto-keyed for konto-modus). Konsumenter som forventet
   ett skjema fikk noen ganger det andre — stille no-ops eller blanket-ut
   data avhengig av hvilken modus brukeren sist hadde besøkt i Analyse-fanen.

Løsningen er introdusert gradvis fane-for-fane, ikke som en stor refaktor.

## src/-struktur

```
src/
├── __init__.py              # tom — gjør src importerbar som package
├── pages/                   # Faner i hovednotebook (ui_main.nb.add(...))
│   ├── __init__.py          # tom
│   ├── a07/                 # frontend/ + backend/ + controller/
│   ├── ar/                  # Aksjonærer (frontend/ + backend/)
│   ├── consolidation/       # Konsolidering (frontend/ + backend/)
│   ├── documents/
│   ├── driftsmidler/        # frontend/ + backend/
│   ├── fagchat/
│   ├── logg/
│   ├── materiality/         # Vesentlighet (frontend/ + backend/)
│   ├── oversikt/
│   ├── regnskap/            # frontend/
│   └── saldobalanse/        # frontend/ + backend/
├── audit_actions/           # Popups/handlinger åpnet FRA en fane
│   ├── __init__.py
│   ├── motpost/             # Kalles fra Statistikk og Analyse
│   └── statistikk/          # Åpnes som popup fra Analyse
├── shared/                  # Cross-cutting utility
│   ├── __init__.py
│   └── columns_vocabulary.py
└── monitoring/              # Ytelsesovervåkning (perf, events, dashboard)
    ├── perf.py
    ├── events.py
    ├── dashboard.py
    ├── baseline.py
    └── bench.py
```

### Hva går i `src/pages/` vs `src/audit_actions/`

**Avgjørende kriterium:** Er det en `nb.add(...)` for siden i [ui_main.py:340-367](../../ui_main.py#L340-L367)?

- **`src/pages/<navn>/`** — Faneside i hovednotebook. Brukeren navigerer
  EXPLISITT dit. Egen UI-state, eget tab-ikon. Ved React-migrering blir
  dette en route (f.eks. `/saldobalanse`).
- **`src/audit_actions/<navn>/`** — Popup/dialog/handling som åpnes FRA
  en annen fane (typisk høyreklikk-meny eller knapp). Lever i `tk.Toplevel`
  eller midlertidig vindu. Ved React-migrering blir dette en komponent.

Eksempel: `StatistikkPage` har klassebase `ttk.Frame`, MEN den åpnes via
`_open_statistikk_popup()` i Analyse — derfor `audit_actions/`, ikke `pages/`.
`SaldobalansePage` legges til hovednotebooken via `self.nb.add(self.page_saldobalanse, ...)`
— derfor `pages/`.

### Frontend/backend-mønsteret

Innenfor en side-pakke deler vi i to undermapper:

```
src/pages/X/
├── __init__.py          # re-eksporterer XPage fra frontend.page
├── frontend/
│   ├── __init__.py      # re-eksporterer XPage fra .page
│   ├── page.py          # Tk-widgets (XPage(ttk.Frame))
│   ├── actions.py       # Knappklikk-handlinger
│   └── ...              # Dialoger, kolonne-helpers, osv.
└── backend/
    ├── __init__.py
    ├── compute.py       # Beregningslogikk (rene DataFrames inn/ut)
    ├── store.py         # Lagring/lasting
    └── excel.py         # Excel-eksport
```

Konvensjoner:
- **Backend importerer ALDRI tkinter** — verifiseres av
  `tests/test_<X>_backend_no_tk.py` (lint-test per side)
- **Frontend importerer fra backend** via relative import: `from ..backend.compute import ...`
- **Backend tar pure data**, ikke `page`-objekter (gjør hodeløs kjøring +
  REST-eksponering mulig senere)
- **Eksterne kallere** importerer via fanens `__init__`:
  `from src.pages.X import XPage`

### Hva går i `src/shared/`

Cross-cutting kode som brukes av flere faner. I dag inneholder den
bare `columns_vocabulary.py`. Folder-strukturen under `src/shared/`
skal kun splittes når det vokser til 10+ filer — enkelhet først.

### Hva går i `src/monitoring/`

Ytelsesovervåknings-subsystem (etablert med plan-fila før piloter):
- `perf.py` — `timer()`, `profile()`, `init_monitoring()`
- `events.py` — `EventStore` med async disk-flush
- `dashboard.py` — Tk-sidekick (`python -m src.monitoring.dashboard`)
- `baseline.py` + `bench.py` — baseline-sammenligning

Se [doc/architecture/monitoring.md](monitoring.md).

### Hva ligger fortsatt i rot

Alt som ennå ikke er flyttet — store og små. Migrering skjer fane-for-fane
mens vi jobber med dem. Etter pilot 13 har roten KUN reell kode + 2
shim-filer (`bilag_drilldialog.py` og `saldobalanse_payload.py`).

Største gjenstående klynger:
- **Analyse-fanen** — 28+ filer (`page_analyse*.py` + `analyse_*.py`),
  brukerens eget område, holdes utenfor refaktor inntil videre
- **Reskontro, MVA, Skatt, Utvalg, Scoping, Dataset, Admin, Revisjonshandlinger**
  — én-fane-grupper med diverse hjelpefiler
- **Diverse utility i rot** — formatting.py, preferences.py, session.py osv.
  (kandidater for `src/shared/` på sikt)

### Migrering av en ny fane (playbook)

1. **Kartlegg klyngen.** Liste alle filer som hører til fanen
   (`grep page_X*.py + X_*.py`), tester (`tests/test_*X*.py`), og
   eksterne importere (`grep "import page_X\|from page_X"`).
2. **Identifiser tk-frie vs Tk-koblede filer:**
   `grep -l "import tkinter\|from tkinter" *X*.py` — gir kandidater
   for backend/ vs frontend/.
3. **Lag mappestruktur:** `src/pages/X/{frontend,backend}/__init__.py`
   med re-eksport.
4. **Flytt filene:** `git mv` (preserves history; `git log --follow` fungerer).
5. **Gjør intra-pakke-imports relative:**
   - Frontend-til-frontend: `from . import Y`
   - Frontend-til-backend: `from ..backend.compute import ...`
   - Backend-til-backend: `from .Y import ...`
6. **Oppdater eksterne importere** (alle steder som bruker gamle navn):
   `from page_X import XPage` → `from src.pages.X import XPage`
7. **(Valgfritt) Lag sys.modules-shim** for gradvis overgang — se
   [Skim-mønsteret](#sys-modules-shim-mønsteret-overgangsfase) under.
8. **Lag lint-test:** `tests/test_X_backend_no_tk.py` som forbyr
   tkinter-imports i backend/.
9. **Verifiser:**
   - `python -c "import ui_main"` — sikrer at hele import-grafen virker
   - `pytest tests/test_X*.py` — fanens egne tester
   - Bredere suite — fanger indirekte avhengigheter
10. **PyInstaller:** Ingen endring nødvendig så lenge entrypoint
    (`ui_main.py`) finner modulen.

### sys.modules-shim-mønsteret (overgangsfase)

Når en fane med mange eksterne importerere flyttes, kan vi unngå å
oppdatere alle på en gang ved å lage en shim-fil på toppnivå:

```python
# saldobalanse_payload.py (toppnivå-shim)
"""Bakoverkompat-shim — har flyttet til src.pages.saldobalanse.backend.payload."""
from __future__ import annotations
import sys as _sys
from src.pages.saldobalanse.backend import payload as _payload
_sys.modules[__name__] = _payload
```

`sys.modules`-aliaseringen gjør at `import saldobalanse_payload` returnerer
nøyaktig samme modul-objekt som `src.pages.saldobalanse.backend.payload` —
viktig for monkeypatch-konsistens i tester.

**For pakker** (motpost/, consolidation/) trengs litt mer for at
`from pkg import X` skal returnere SAMME modul-objekt — pre-load
submoduler OG sett dem som attributter på pakka:

```python
# motpost.py (toppnivå pakke-shim)
import importlib as _importlib
import pkgutil as _pkgutil
import sys as _sys
from src.audit_actions import motpost as _motpost
_sys.modules[__name__] = _motpost
for _info in _pkgutil.iter_modules(_motpost.__path__):
    _mod = _importlib.import_module(f"src.audit_actions.motpost.{_info.name}")
    _sys.modules[f"motpost.{_info.name}"] = _mod
    setattr(_motpost, _info.name, _mod)
```

Shimmen fjernes når alle eksterne importerere er oppdatert (typisk i
en separat opprydnings-pilot — se piloter 12-13).

### Migrert hittil (etter pilot 13)

**`src/pages/`** (11 sider):
| Side | Pilot | Linjer | Notat |
|---|---|---|---|
| driftsmidler | 1 | 550 | Etablerte mønsteret |
| saldobalanse | 4-5 | 4 250 | 6 filer, sys.modules-shim første gang |
| materiality | 6 | 2 000 | 5 filer |
| ar (aksjonærer) | 7 | 7 100 | 11 filer, største enkeltpilot |
| regnskap | 8 | 1 025 | 1 fil — ren én-fil-pilot |
| consolidation | 11 | 10 000 | 47 filer, delt i 3 sub-piloter |
| a07, oversikt, fagchat, logg, documents | (annen utvikler) | — | Codex-arbeid |

**`src/audit_actions/`** (2 handlinger):
| Handling | Pilot | Notat |
|---|---|---|
| motpost | 9 | Etablerte audit_actions-kategorien |
| statistikk | 10 | Korrigert fra `pages/` (åpnes som popup, ikke fane) |

**Opprydding (pilot 12-13):** 67 toppnivå-shim-filer fjernet.

Se:
- [A07 Refaktor- Og `src/`-Plan](a07_refaktor_og_src_plan.md)
- [Monitoring-arkitektur](monitoring.md)

## Felles kolonne-vokabular

**Modul:** [src/shared/columns_vocabulary.py](../../src/shared/columns_vocabulary.py)
**Detaljert ID-tabell:** [columns_vocabulary.md](columns_vocabulary.md)

Én funksjon (`heading()`) og én dict (`LABELS_STATIC`) er kilde til
sannhet for hva en intern kolonne-ID betyr og hvordan den vises.

### Format-konvensjon

| Type kolonne | Format | Eksempel |
|---|---|---|
| Rene verdier (UB, IB, HB, UB_fjor) | 4-sifret år | `UB 2025`, `IB 2025`, `HB 2025` |
| Endringskolonner | Δ-prefiks + 2-sifret år | `Δ UB 25/24`, `Δ UB-IB 25`, `Δ % UB 25/24` |

**Hvorfor Δ?** Etablert mattekonvensjon for differanse, sparer plass
sammenlignet med "Endr"-prefiks (3 tegn pr kolonne), og signaliserer
visuelt at kolonnen er en *beregnet differanse* — ikke en råverdi.

**Hvorfor 2-sifret år på endringer?** Endringskolonner har naturlig
operand-eksplisittering ("Δ UB 25/24" — UB i 25 minus UB i 24). Det
korte året er ikke tvetydig fordi konteksten allerede sier hva det er
sammenlignet med. Rene UB/IB-kolonner får 4-sifret år for å være
entydige i Excel-eksporter.

### Bruk

```python
from src.shared.columns_vocabulary import active_year_from_session, heading

yr = active_year_from_session()           # leser session.year
label = heading("UB", year=yr)            # → "UB 2025"
label = heading("UB_fjor", year=yr)       # → "UB 2024"
label = heading("Endring_fjor", year=yr)  # → "Δ UB 25/24"
label = heading("Endring", year=yr)       # → "Δ UB-IB 25"
label = heading("Endring_pct", year=yr)   # → "Δ % UB 25/24"
label = heading("Konto")                  # → "Konto" (ukjente returneres uendret)
```

### Migrering av en fane til vokabularet

Mønster (gjentatt i Statistikk, Lønn, MVA, Saldobalanse):

1. Importer:
   ```python
   from src.shared.columns_vocabulary import active_year_from_session, heading
   ```
2. Erstatt `tree.heading("col", text="UB")` med
   `tree.heading("col", text=heading("UB", year=yr))`. For tre med
   loop: `for col in COLUMNS: tree.heading(col, text=heading(col, year=yr))`
   — heading() har innebygd fallback for ukjente IDs så fane-spesifikke
   kolonner returneres uendret.
3. Lag `_apply_vocabulary_labels()`-metode på fane-klassen som re-kjører
   heading-setting med `active_year_from_session()`.
4. Kall `_apply_vocabulary_labels()` fra både:
   - `__init__` (etter `_build_ui()`) — initial state, kanskje uten år
   - `refresh_from_session()` — etter klient/år-bytte
5. For KPI-banner-labels (statiske `Label`-widgets): konverter til
   `StringVar` slik at de kan oppdateres.

### Migrert hittil

| Fane | Hva er migrert |
|---|---|
| Analyse | Pivot-tre + SB-tre via `analysis_heading()` (tynn wrapper over `heading()`) |
| Statistikk | KPI-banner + Kontoer-tabell + Excel-eksport |
| Lønn | RS-, BS-, og konto-tre (3 trær) |
| MVA | Summary- og konto-tre (2 trær) |
| Saldobalanse | Hovedtre (alle ALL_COLUMNS via `heading()` med fallback) |

### Bakoverkompatibilitet

`page_analyse_columns.py` re-eksporterer `analysis_heading()` som tynn
wrapper over `heading()`, så eksisterende callere virker uendret.
Den gamle `_ANALYSIS_HEADINGS_STATIC`-dict-en er nå alias for
`LABELS_STATIC`. Dette ble gjort for å unngå å oppdatere alle callere
i én commit.

## Pivot-cache-skjemaer på AnalysePage

**Bakgrunn:** Tidligere skrev RL-, SB-konto- og HB-konto-pivotene alle til
`page._pivot_df_last`. Konsumenter som antok regnr-keyed skjema fikk
noen ganger Konto-keyed pivot tilbake — stille no-op eller blanket-ut
data, avhengig av hvilken Analyse-modus brukeren sist hadde besøkt.

### Tre typede attributter

`AnalysePage` lagrer nå pivot-snapshots på tre uavhengige attributter,
satt av hver sin refresh-funksjon:

| Attributt | Settes av | Skjema (nøkkelkolonne) |
|---|---|---|
| `_pivot_df_rl` | [page_analyse_rl_render.py:495](../../page_analyse_rl_render.py#L495) | `regnr` (int) |
| `_pivot_df_sb_konto` | [page_analyse_pivot.py:373](../../page_analyse_pivot.py#L373) | `Konto` (str) |
| `_pivot_df_hb_konto` | [page_analyse_pivot.py:656](../../page_analyse_pivot.py#L656) | `Konto` (str) |

`_pivot_df_last` beholdes for skjema-agnostiske konsumenter (pivot-eksport,
`_has_prev_year`-sjekk) og settes av alle tre — den representerer "siste
synlige pivot uansett skjema".

### Konsumenter

| Konsument | Bruker | Hvorfor |
|---|---|---|
| [analyse_drilldown.py:222](../../analyse_drilldown.py#L222) | `_pivot_df_rl` | Nøkkeltall-merging trenger regnr |
| [workpaper_export_rl.py:30](../../workpaper_export_rl.py#L30) | `_pivot_df_rl` | UB_fjor-merge trenger regnr |
| [page_driftsmidler.py:466](../../page_driftsmidler.py#L466) | `_pivot_df_rl` | Henter regnr=555 UB |
| [page_statistikk.py](../../src/pages/statistikk/page_statistikk.py) `_update_kpi` | `_pivot_df_rl` | KPI-radlookup pr regnr |
| [page_statistikk_excel.py](../../src/pages/statistikk/page_statistikk_excel.py) | `_pivot_df_rl` | Samme KPI-lookup ved eksport |
| [regnskap_export.py:28](../../regnskap_export.py#L28) | `_pivot_df_rl` | UB_fjor for Excel-årsregnskap |
| [page_regnskap.py:855](../../page_regnskap.py#L855) | `_pivot_df_rl` (fallback) | UB_fjor leveres nå direkte fra prepare_*_export_data |
| [page_analyse_columns.py:189](../../page_analyse_columns.py#L189) | `_pivot_df_last` | Kun eksistens-sjekk for UB_fjor — skjema-uavhengig OK |
| [page_analyse_export.py:129](../../page_analyse_export.py#L129) | `_pivot_df_last` | Eksporter "den synlige pivoten" — skjema-uavhengig OK |

### Regel for ny kode

Hvis du leser fra et pivot-cache for å hente data fra en *spesifikk*
nøkkel (regnr eller Konto): **bruk det typede attributtet** for det
skjemaet du forventer.

Hvis du bare trenger "den siste pivoten som ble vist" uten antakelser
om skjema (eksport, eksistens-sjekk): `_pivot_df_last` er OK.

## Relaterte dokumenter

- [columns_vocabulary.md](columns_vocabulary.md) — full ID-tabell og
  semantisk skille mellom Endring (periode) og Endring_fjor (år-over-år)
- [analyse_pivot_engine.md](analyse_pivot_engine.md) — hvordan pivotene
  bygges fra HB/SB-data
