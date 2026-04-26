# src/-migrasjon — pilot-logg

**Sist oppdatert:** 2026-04-26

Loggfører hver pilot i den fane-for-fane-migrasjonen som omorganiserer
repoet til `src/pages/`, `src/audit_actions/`, `src/shared/` og
`src/monitoring/`. For overordnet beskrivelse av strukturen, se
[src_struktur_og_vokabular.md](src_struktur_og_vokabular.md).

## Tabell over piloter

| Pilot | Dato | Commit | Side/handling | Filer | Linjer | Notat |
|---|---|---|---|---|---|---|
| 1 | 2026-04-25 | `5bbadfe` | driftsmidler | 2 | 550 | Etablerte frontend/backend-mønsteret |
| 2 | 2026-04-25 | `64ef9a0` | statistikk (struktur) | 3 | 1 700 | Andre fane med mønsteret |
| 3 | 2026-04-25 | `55843c9` | statistikk (pure-data) | 3 | 1 700 | Refaktorerte API til DataFrames inn/ut, fjernet `page`-arg |
| 4 | 2026-04-25 | `6266581` | saldobalanse (backend) | 1 | 1 452 | Etablerte sys.modules-shim-mønsteret for bakoverkompat |
| 5 | 2026-04-25 | `4f38ece` | saldobalanse (frontend) | 4 | 2 800 | Hele frontend-klyngen samlet |
| 6 | 2026-04-25 | `19dd3d7` | materiality (vesentlighet) | 5 | 2 000 | 4 backend + 1 frontend |
| 7 | 2026-04-25 | `c53644a` | ar (aksjonærer) | 11 | 7 100 | Største enkeltpilot, 4 backend + 7 frontend |
| 8 | 2026-04-26 | `0f36eab` | regnskap | 1 | 1 025 | Eneste én-fil-pilot, demonstrerte mønsteret for små faner |
| 9 | 2026-04-26 | `b43217f` | motpost | 27 | 7 586 | Etablerte `src/audit_actions/` (pakke-shim med pre-load + setattr) |
| 10 | 2026-04-26 | `14d598f` | statistikk (omplassering) | 6 | 1 700 | Korrigerte feilkategorisering — flyttet fra `pages/` til `audit_actions/` |
| 11A | 2026-04-26 | `8166108` | consolidation (backend pkg) | 15 | 6 000 | Eksisterende `consolidation/`-pakka flyttet til ny lokasjon |
| 11B | 2026-04-26 | `c090bf5` | consolidation (frontend) | 27 | 7 800 | `page_consolidation*.py` → `frontend/` |
| 11C | 2026-04-26 | `ce5d5a2` | consolidation (resten) | 5 | 1 200 | `consolidation_*.py` (3 backend, 2 frontend) + lint-test |
| 14 | 2026-04-26 | `be8428e` | skatt | 1 | 515 | Én-fil-pilot uten backend/frontend-skille (visningsside med selectmode="none") |
| 15 | 2026-04-26 | `4e426a1` | revisjonshandlinger | 2 | 2 224 | ManagedTreeview-migrering tidligere samme dag (`d785aac`) |
| 16 | 2026-04-26 | `3b34db0` | scoping | 4 | 1 787 | 1 frontend + 3 backend (engine, store, export) + ManagedTreeview-migrering |
| 17 | 2026-04-26 | `1ea4829` | utvalg | 3 | 1 042 | UtvalgPage + UtvalgStrataPage + utvalg_excel_report; AST-test-sti måtte oppdateres |
| 18 | 2026-04-26 | `b86c7ee` | mva | 9 | 4 054 | 6 backend + 3 frontend (avstemming, kontroller, melding-parser, dialoger) |
| 19 | 2026-04-26 | `8d75210` | dataset | 14 | 5 066 | 6 backend + 8 frontend; bryter to roller (datakilde + klient-info) — `dataset_klientoversikt_plan.md` beskriver senere splitt |
| 20 | 2026-04-26 | `9bb636b` | reskontro | 12 | 5 048 | 4 backend + 8 frontend; treeview-migrering utestående (5-6 trær, høy kompleksitet) |

## src/shared/ — cross-cutting utility-pakker

Når roten av faner var flyttet, ble shared-utilities samlet til
`src/shared/<domene>/`. Mønster: ren backend (verifisert med lint-test),
brukt av flere faner.

| Pilot | Dato | Commit | Pakke | Filer | Notat |
|---|---|---|---|---|---|
| 21 | 2026-04-26 | `459f935` | `src/shared/regnskap/` | 6 backend + 3 frontend | `regnskap_*.py` splittet: 6 til shared, 3 frontend-helpers (export, klient, noter) til `src/pages/regnskap/frontend/` |
| 22 | 2026-04-26 | `d8d6594` | `src/shared/client_store/` | 5 backend | `client_store/{store, meta_index, enrich, importer, versions}.py`. Tk-koblede dialoger (`client_picker_dialog`, `client_store_enrich_ui`) beholdt på toppnivå |
| 23 | 2026-04-26 | `e573951` | `src/shared/brreg/` | 4 backend | BRREG-API-klient med cache + RL-sammenligning + fallback-logikk |

## Andre forbedringer 2026-04-26

| Commit | Beskrivelse |
|---|---|
| `eea102d` | Slett dødt kode (~2 700 linjer): page_ab*, page_studio, ab_*, analysis_pkg/pack — bevart kunnskap i `dataset_compare_plan.md` |
| `2105dea` | Reskontro-berikelse: kunde/leverandør propageres til alle linjer i samme bilag (Analyse-fanen) |
| `3d1c90b` | Skille kunde og leverandør i transaksjons-treet (quickfix) |
| `d785aac` | `page_revisjonshandlinger` migrert til `ManagedTreeview` |
| `922c1fa` | `page_scoping` migrert til `ManagedTreeview` + ytelses-rydding (regnskapslinjer lastes nå 1× per refresh i stedet for 3×) |

## Opprydding (pilot 12-13)

Etter at fanene var flyttet, var det 69 toppnivå-shim-filer igjen som
holdt eksterne importerere virksomme. Pilot 12-13 ryddet 67 av dem ved
å oppdatere alle eksterne importerere til ny lokasjon og slette shimene.

| Pilot | Dato | Commit | Slettet | Notat |
|---|---|---|---|---|
| 12A | 2026-04-26 | `6e99984` | 33 konsolidering-shims | Bulk-rewrite-script |
| 12B | 2026-04-26 | `0fbb8c7` | 11 AR-shims | Avdekket `from-import-pakkeattributt`-fallgruve |
| 12C | 2026-04-26 | `95cb7dc` | 4 saldobalanse-shims | `payload.py` bevart for A07-kompatibilitet |
| 12D | 2026-04-26 | `4bd44e3` | 5 materiality-shims | |
| 12E | 2026-04-26 | `c2537a2` | 1 regnskap-shim | |
| 13A | 2026-04-26 | `78d0107` | 8 selection_studio-shims | Eldre refaktor (annen utvikler) |
| 13B | 2026-04-26 | `730eb61` | 5 motpost-modul-shims | flowchart_*-fila var reell kode, beholdt |
| 13C | 2026-04-26 | `5f17ce9` | 2 pakke-shims | `consolidation.py` + `motpost.py` — krevde også retting av interne pakke-imports |

**Totalt etter rydding:** 67 shim-filer slettet, hundrevis av importerere
oppdatert til ny lokasjon, alle pre-existing test-failures uendret.

## Status etter pilot 23 (2026-04-26)

**Roten:** 226 .py-filer (var 254 før dagens ettermiddag).

**`src/`-strukturen:**
```
src/
├── pages/             18 mapper (a07, ar, consolidation, dataset, documents,
│                      driftsmidler, fagchat, logg, materiality, mva, oversikt,
│                      regnskap, reskontro, revisjonshandlinger, saldobalanse,
│                      scoping, skatt, utvalg)
├── audit_actions/     2 mapper (motpost, statistikk)
├── shared/            3 mapper (regnskap, client_store, brreg) + columns_vocabulary.py
└── monitoring/        ferdig (perf, events, dashboard, baseline, bench)
```

**Bevisst beholdt på toppnivå (shim-filer):**

1. **`saldobalanse_payload.py`** — `a07_feature/payroll/saldobalanse_bridge.py`
   bruker den fortsatt. A07-utvikler oppdaterer importen ved neste runde.
2. **`bilag_drilldialog.py`** — Fra eldre refaktor, ikke vårt arbeid.

**Tk-koblede dialoger fortsatt på toppnivå (kandidater for senere
`src/shared/dialogs/`):**

- `client_picker_dialog.py` — klient-velger
- `client_store_enrich_ui.py` — Visena-berikelse-dialog

## Neste mulige piloter

| Pilot | Pakke | Filer | Risiko |
|---|---|---|---|
| 24 | `src/shared/saft/` | 4 (saft_importer, saft_reader, saft_tax_table, saft_trial_balance) | Lav |
| 25 | `src/shared/workpapers/` | 9 (workpaper_*) | Middels — mange importerere |
| 26 | `src/shared/ui/` | 9 (vaak_*, ui_*) | Middels — brukes av alle faner |
| 27 | `src/shared/classification/` | ~10 (account_*, konto_klassifisering, classification_*) | Middels |
| 28 | `src/shared/actions/` | 7 (action_*) | Lav |
| 29 | `src/audit_actions/document_control/` | ~21 (controller*, document_control_*) | Høy — 21 filer, kompleks |

**Hold-unna (andres område):**
- A07/admin (~17 filer)
- Analyse (~46 filer — `page_analyse*.py` + `analyse_*.py`)

**Senere "annet"** (~70 filer): brreg fallbacks, build_exe, column_*,
convert_*, diverse helpers — vurderes case-by-case.

## Erfaringer og prinsipper etablert

### Frontend/backend-skille

Innenfor en side: `backend/` har ingen tkinter-imports (verifisert av
lint-test), `frontend/` har Tk-widgets. Backend skal kunne kjøres hodeløst
og senere eksponeres som REST-endepunkt — derfor pure-data-API
(DataFrames inn/ut, ikke `page`-objekt-arg).

### sys.modules-shim-mønsteret

For å unngå å oppdatere mange eksterne importerere på en gang ved flytting:
toppnivå-fila blir til en `sys.modules`-alias som peker til ny lokasjon.
For pakker må submoduler pre-loades OG settes som attributter på pakka,
ellers vil `from pkg import X` re-eksekvere modulen og lage
duplikate funksjons-objekter (avdekket av compat-wrapper-test for
PyInstaller).

### `from pkg import X`-fallgruve under monkeypatch

`from pkg import X` slår FØRST opp `X` som attributt på `pkg`. Bare hvis
det mangler, faller Python tilbake til submodule-import. Konsekvens for
tester: `monkeypatch.setitem(sys.modules, "pkg.X", FakeX)` virker IKKE
hvis `pkg.X` allerede er importert som attributt. Bruk i stedet:

```python
import pkg
monkeypatch.setattr(pkg, "X", FakeX)
```

### Pages vs audit_actions

`StatistikkPage` ble først kategorisert som `pages/` fordi den arver
`ttk.Frame`. Etter pilot 9 ble det klart at det riktige kriteriet er
om siden er en `nb.add(...)` i `ui_main.py` — ikke widget-klassebasen.
Statistikk åpnes som popup, dermed `audit_actions/`. Pilot 10 korrigerte
plasseringen.

### Presis git staging

`git add -A` eller `git add src/pages` plukker opp untracked filer fra
andre utvikleres pågående arbeid (typisk A07 i denne perioden). Bruk
**alltid** spesifikke filnavn ved staging når andre utviklere har skitne
working dir-modifikasjoner.

