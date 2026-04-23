# Treeview-playbook — standard oppsett med `ManagedTreeview`

Denne guiden viser hvordan du setter opp (eller migrerer) en
`ttk.Treeview` i prosjektet slik at den får felles-funksjonaliteten
vi forventer på alle tabeller:

- **Klikk-sortering** på kolonneoverskrift (auto-detekterer
  tall/dato/tekst; norsk tallformat).
- **Høyreklikk-meny** på header for vis/skjul av kolonner.
- **Dra-n-slipp-rekkefølge** av kolonner.
- **Kolonnebredde-persistens** mellom økter.
- **Synlighets- og rekkefølge-persistens** per brukervisning.
- **Pinned-first-invariant** (låste kolonner alltid først).

Alt dette leveres av [ui_managed_treeview.py](../ui_managed_treeview.py)
via `ManagedTreeview`-klassen. Under panseret bruker den
[treeview_column_manager.py](../treeview_column_manager.py) (kolonne-
synlighet/rekkefølge + høyreklikk) og
[ui_treeview_sort.py](../ui_treeview_sort.py) (sorterings-motoren).

## Minimal oppskrift for en ny Treeview

```python
from ui_managed_treeview import ColumnSpec, ManagedTreeview

self._tree = ttk.Treeview(parent, columns=COLUMNS, show="headings")

self._managed = ManagedTreeview(
    self._tree,
    view_id="min_tabell",
    pref_prefix="ui",
    column_specs=[
        ColumnSpec(id="konto",     heading="Konto",     width=80,  pinned=True),
        ColumnSpec(id="kontonavn", heading="Kontonavn", width=220, stretch=True),
        ColumnSpec(id="beloep",    heading="Beløp",     width=110, anchor="e"),
    ],
    on_body_right_click=self._open_context_menu,  # valgfritt
)
```

Det er alt. Brukeren kan nå klikke overskrifter for å sortere,
høyreklikke for kolonnemeny, dra for å endre rekkefølge, og alle
valg persisterer til `preferences.json` under
`ui.min_tabell.visible_cols` / `column_order` / `column_widths`.

## Migrere en eksisterende Treeview til `ManagedTreeview`

### 1. Lag `ColumnSpec`-liste

Flytt hardkodede bredder/overskrifter/ankre/stretch til en liste av
`ColumnSpec`. Gjerne i en egen `build_column_specs()`-funksjon hvis
overskriftene er dynamiske (f.eks. årstall).

Se [saldobalanse_payload.py](../saldobalanse_payload.py) for et
konkret eksempel.

### 2. Erstatt manuell tree-oppsett-løkke

Før:

```python
for col in ALL_COLS:
    tree.heading(col, text=HEADINGS[col])
    tree.column(col, width=WIDTHS[col], anchor=...)
```

Etter:

```python
self._managed = ManagedTreeview(
    tree,
    view_id="...",
    column_specs=build_column_specs(),
    pref_prefix="ui",
)
```

### 3. Ta vare på eksisterende preferences via `legacy_pref_keys`

Hvis tabellen i dag lagrer valg under andre nøkler i
`preferences.json`, bruk `legacy_pref_keys` slik at brukerens valg
bevares første gang koden kjøres:

```python
ManagedTreeview(
    ...,
    legacy_pref_keys={
        "visible_cols":  "gammel.pref.visible",
        "column_order":  "gammel.pref.order",
        "column_widths": "gammel.pref.widths",  # kan utelates
    },
)
```

Gamle nøkler leses én gang, skrives til `ui.<view_id>.*`, og
beholdes deretter i `preferences.json` (for rollback — ikke slettet).

### 4. Fjern duplisert infrastruktur

Etter migreringen trenger du som regel ikke lenger:

- Egen header-sorterings-binding (erstattes av `enable_treeview_sorting`
  under panseret).
- Egen `<Button-3>`-binding på header (erstattes av
  `TreeviewColumnManager.on_right_click`).
- Hardkodede numerisk-vs-tekst-lister for sortering
  (auto-detekteres per kolonne).

Body-bindings (rad-seleksjon, dobbelklikk, kontekst-meny på rad)
beholdes orthogonalt. Bruk `on_body_right_click=self._open_body_menu`
hvis du tidligere hadde `<Button-3>`-logikk som skilte header fra
body.

### 5. Verifiser

1. Unit-tester: `py -m pytest tests/test_ui_managed_treeview.py`
2. Regresjon for siden du migrerte.
3. Manuell røyk-test: start appen, prøv sortering, høyreklikk,
   kolonne-dra, preset-bytte (hvis relevant), restart for å
   verifisere persistens.

## Eksisterende call-sites

Ferdig migrert (bruker `ManagedTreeview` direkte):

- [page_saldobalanse.py](../page_saldobalanse.py) — bruker
  `build_column_specs(year)` fra [saldobalanse_payload.py](../saldobalanse_payload.py).
- [page_konsolidering.py](../page_konsolidering.py) — konsoliderings-
  tabellene (tidligere mønster, driver forventningene).

Bruker bare deler av stacken:

- [analyse_sb_remap.py](../analyse_sb_remap.py) — delegerer sortering
  til `ui_treeview_sort.enable_treeview_sorting`. Kolonne-synlighet
  og preferences ligger fortsatt i
  [page_analyse_columns_presets.py](../page_analyse_columns_presets.py)
  fordi logikken for dynamisk UB_fjor-skjul og legacy IB/Endring-
  migrering er tett koblet til `configure_sb_tree_columns`. Full
  `ManagedTreeview`-migrering krever å flytte den dynamikken inn i
  en `ColumnSpec`-bygger og er ikke gjort ennå.

## Gjenstående migrerings-kandidater

Disse har egne sort/kolonne-menyer som kan konsolideres senere:

| Fil | Tabeller | Kompleksitet | Kommentar |
|-----|----------|--------------|-----------|
| `page_analyse.py` | TX-tree + Pivot | Middels | Har egen `page_analyse_columns` med dynamiske kolonner — må flyttes til en `build_column_specs`-bygger. |
| `reskontro_ui_build.py` | 5-6 tre-er | Høy | Flere paralelle visninger; behandles en om gangen. |
| `page_revisjonshandlinger.py` | 1 tabell | Lav | Bør være en direkte migrering. |
| `page_scoping.py` | 1-2 tabeller | Lav | Ingen spesiell dynamikk. |
| `page_admin_brreg_mapping.py` | 1 tabell | Lav |  |
| `rl_mapping_drift_dialog.py` | 1 tabell | Lav |  |

## Preferences-nøkkelstandard

Nye migreringer skal bruke:

```
{pref_prefix}.{view_id}.visible_cols    # list[str]
{pref_prefix}.{view_id}.column_order    # list[str]
{pref_prefix}.{view_id}.column_widths   # dict[str, int]
```

Default-prefix er `"ui"`. Hvis siden allerede har et annet prefix
(f.eks. `"consolidation"`) og bytte ville tapt brukervalg, beholder
vi det; `legacy_pref_keys` brukes fortsatt for å migrere fra gamle
flate nøkkelnavn.

## Kjent teknisk gjeld

- Det finnes tre parallelle sort-motorer i repoet:
  [ui_treeview_sort.py](../ui_treeview_sort.py) (kanonisk),
  `ui_utils.enable_treeview_sort` og `treeutils.attach_sorting`.
  Etter Saldobalanse- og Analyse-SB-migreringen er de to siste
  kandidater til sletting, men noen call-sites gjenstår. Rydding
  er egen oppgave — vent til migreringene over er ferdige.
- `TreeviewColumnManager.visible_cols` og `.column_order` er
  read-only property-kopier. Skriv via `set_visible_columns()` og
  `reorder_columns()` for å bevare pinned-invariantet.
