# src/-struktur og felles vokabular

**Sist oppdatert:** 2026-04-23

Beskriver organiseringen av kodebasen rundt `src/`-mappen som ble innført i
April 2026, det felles kolonne-vokabularet i `src/shared/columns_vocabulary.py`,
og det typede pivot-cache-systemet på `AnalysePage`.

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
├── pages/
│   ├── __init__.py          # tom
│   ├── driftsmidler/
│   │   ├── __init__.py      # re-eksporterer DriftsmidlerPage
│   │   └── page_driftsmidler.py
│   └── statistikk/
│       ├── __init__.py      # re-eksporterer StatistikkPage
│       ├── page_statistikk.py
│       ├── page_statistikk_compute.py
│       └── page_statistikk_excel.py
└── shared/
    ├── __init__.py          # tom
    └── columns_vocabulary.py
```

### Hva går i `src/pages/`

Én fane = én undermappe. Klyngen flyttes samlet (alle `page_X*.py` +
`X_*.py`-filene som hører sammen). Konvensjon:

- `__init__.py` re-eksporterer fanens hovedklasse: `from .page_X import XPage`
- Intra-fane-imports er relative: `from .page_X_compute import _foo`
- Eksterne importer henter via fanens `__init__`: `from src.pages.X import XPage`

### Hva går i `src/shared/`

Cross-cutting kode som brukes av flere faner. Akkurat nå er
`columns_vocabulary.py` eneste innbygger.

På sikt kan dette inkludere:
- `formatting.py`, `preferences.py`, `session.py` (i dag i rot)
- Theme-moduler (`vaak_excel_theme.py`, `vaak_tokens.py`)
- Felles widget-helpers

Folder-strukturen under `src/shared/` skal kun splittes når det vokser
til 10+ filer — enkelhet først.

### Hva ligger fortsatt i rot

Alt som ennå ikke er flyttet. Migrering skjer fane-for-fane mens vi
jobber med dem. Det er **ikke** et mål å flytte alt på en gang —
re-export-shimmer eller bare oppdatert importsti gjør at flytting kan
skje uten å bryte resten.

### Migrering av en ny fane (playbook)

1. **Kartlegg klyngen.** Liste alle filer som hører til fanen
   (`grep page_X*.py + X_*.py`), tester (`tests/test_*X*.py`), og
   eksterne importere (`grep "import page_X\|from page_X"`).
2. **Lag mappestruktur:** `src/pages/X/__init__.py` med re-eksport
   av hovedklassen.
3. **Flytt filene:** `git mv` (preserves history; `git log --follow` fungerer).
4. **Gjør intra-fane-imports relative:**
   `from page_X_compute import …` → `from .page_X_compute import …`.
5. **Oppdater eksterne importere:**
   `from page_X import XPage` → `from src.pages.X import XPage`.
6. **Oppdater tester:** `import page_X` → `from src.pages.X import page_X`.
7. **Verifiser:**
   - `python -c "import ui_main"` — sikrer at hele import-grafen virker
   - `pytest tests/test_X*.py` — fanens egne tester
   - Bredere suite — fanger indirekte avhengigheter
8. **PyInstaller:** Ingen endring nødvendig så lenge entrypoint
   (`ui_main.py`) finner modulen — speccen lister bare `ui_main` som
   hidden import og finner resten via import-graf.

### Migrert hittil

- `src/pages/driftsmidler/` (1 fil) — pilot, validerte oppskriften
- `src/pages/statistikk/` (3 filer) — første flerfilet klynge

### Planlagt neste store klynge

- `src/pages/a07/`

For A07 er vedtatt retning aa flytte den offentlige page-entrypointen foerst,
ikke hele runtime-klyngen i ett steg.

Det betyr:

- `src/pages/a07/` blir kanonisk page-importflate
- `page_a07.py` beholdes som compat-shim i en overgangsperiode
- intern motorlogikk i `a07_feature/` splittes videre foer eventuell senere
  fysisk flytting

Se:

- [A07 Refaktor- Og `src/`-Plan](a07_refaktor_og_src_plan.md)

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
