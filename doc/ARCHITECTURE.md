# Arkitektur og repo-struktur (pågående refaktor)

Dette prosjektet er en desktop-app (Tkinter) som gjør analyse/utvalg/eksport på regnskapsdata (pandas).
Repoet har historisk vært ganske “flatt” (mange `.py`-filer i rot), og flere store moduler har blandet UI og logikk.

Målet med refaktoren er:

- tydeligere skille mellom **GUI (Tkinter)** og **forretningslogikk/data-transformasjoner**
- enklere gjenbruk (samme logikk brukes i UI, eksport og tester)
- mindre “spaghetti-imports” og færre sirkulære imports
- bedre “feature”-inndeling: hver funksjon/område samles i en pakke

## Dagens prinsipp

- **UI**: `page_*.py`, `views_*.py`, `ui_*.py`, `dataset_pane.py`, `widgets.py`
- **Logikk/“core”**: `analyse_*`, `analysis_*`, `selection_studio_*`, `motpost_*`, `formatting.py`, `excel_formatting.py`, osv.
- **Feature som pakke**: `overstyring/` (allerede ryddig: `core.py`, `ui_panel.py`, `registry.py`, …)

## Endring som er gjort nå

Vi har startet med å pakke inn to større “features” som allerede hadde relativt godt skille mellom UI og logikk:

### `selection_studio/` (ny pakke)

Den underliggende logikken ligger nå i:

- `selection_studio/helpers.py`
- `selection_studio/ui_logic.py`
- `selection_studio/ui_builder.py`
- `selection_studio/bilag.py`
- `selection_studio/drill.py`
- `selection_studio/adapters.py`
- `selection_studio/specific.py`
- `selection_studio/filters.py`

For bakoverkompatibilitet finnes fortsatt de gamle modulnavnene i rot (`selection_studio_helpers.py`, osv.),
men de er nå **tynne wrappers** som re-eksporterer innhold fra pakken.

### `motpost/` (ny pakke)

Motpost-relatert logikk og UI-hjelpere ligger nå i:

- `motpost/utils.py`
- `motpost/combinations.py`
- `motpost/combinations_popup.py`
- `motpost/konto_core.py`
- `motpost/excel.py`

Også her ligger legacy-modulene (`motpost_*.py`) fortsatt i rot som wrappers.

## Neste steg (anbefalt rekkefølge)

Dette er en praktisk og “lav risiko” plan som kan gjennomføres uten store brukersynlige endringer:

1. **Flytte mer feature-kode ut av rot**
   - f.eks. `analyse_*` og `analysis_*` inn i en egen `analysis/`-pakke
   - `ab_*` inn i `ab/` eller `analysis/ab/`

2. **Samle GUI**
   - Opprett `gui/` og flytt `page_*.py` og `views_*.py` inn i `gui/pages/` og `gui/views/`
   - behold root-wrappers i en periode for å unngå massive endringer i imports

3. **Splitt store moduler**
   - `page_analyse.py`: del ut “data prep/export”-metoder til en logikkmodul (`analysis/export_prep.py`)
   - `views_selection_studio_ui.py`: trekk ut “rene” funksjoner til `selection_studio/` slik at view-filen primært er UI

4. **Standardiser formatering**
   - samle tall-/dato-format i én modul (eks. `core/formatters.py`)
   - GUI skal formatere tall via samme helpers som eksport (så vi får konsistent oppførsel)

5. **Etter hvert: innfør tydeligere lag**
   - `domain/` (dataklasser, enums, “typer”)
   - `services/` (I/O, eksport, integrasjoner)
   - `features/` (hvert område samles)
   - `gui/` (Tkinter)

## Praktiske regler (enkle, men effektive)

- UI-komponenter skal helst kalle **rene** funksjoner som kan testes uten Tkinter.
- “Business rules” (f.eks. beløpsfiltrering, gruppering, pivot) skal ikke bo i `views_*.py`.
- Hver feature-pakke kan gjerne ha:
  - `core.py` / `logic.py` (ren logikk)
  - `ui_*.py` (Tkinter)
  - `export.py` (Excel/CSV)
  - `tests/` dekker logikk med DataFrames

