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

## Gjenværende på toppnivå

To shim-filer er bevisst beholdt:

1. **`saldobalanse_payload.py`** — `a07_feature/payroll/saldobalanse_bridge.py`
   bruker den fortsatt. A07-utvikler oppdaterer importen ved neste runde.
2. **`bilag_drilldialog.py`** — Fra eldre refaktor, ikke vårt arbeid.

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

## Neste store kandidater (ikke gjort)

- **Analyse-fanen** — 28+ filer, ~12 000 linjer. Brukerens eget
  arbeidsområde, holdes utenfor refaktor inntil avtalt.
- **Mva, Reskontro, Dataset, Skatt, Scoping, Utvalg, Revisjonshandlinger**
  — én-fane-grupper med diverse hjelpefiler.
- **Diverse utility i rot** — formatting, preferences, session, theme-moduler
  (kandidater for `src/shared/`).
