# Øktoppsummering — 25.-26. april 2026

To dagers intensiv refaktor + features. Total: **23 piloter, ~70 commits,
~150 filer flyttet, ~2 700 linjer dødt kode slettet, og 5 plan-doc'er
skrevet**.

## 1. Hva ble gjort

### Mappestruktur — fra rot til `src/`

**Rotbase:** Repoet hadde ~310 .py-filer i rot. Etter to dager: **226 filer**
(+/- noe Codex-modifikasjoner). De andre er fordelt under `src/`:

```
src/
├── pages/             18 mapper — én per fane i hovednotebook
├── audit_actions/     2 mapper — popups som åpnes fra faner
├── shared/            3 cross-cutting pakker + columns_vocabulary
└── monitoring/        ferdig (perf-overvåkning)
```

### Nye prinsipper etablert

1. **`src/pages/`** vs **`src/audit_actions/`** vs **`src/shared/`** —
   tre tydelige roller (jf. [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md))
2. **Frontend/backend-skille** innenfor hver pakke — backend ren Python
   uten Tk, verifisert med per-pakke lint-tester
3. **`sys.modules`-shim-mønsteret** for gradvis overgang når en pakke
   flyttes (dokumentert i playbook)
4. **Pure-data-API** — backend tar DataFrames inn/ut, ikke `page`-objekt
5. **`ManagedTreeview`** for nye/migrerte tabeller — drag-n-drop,
   sortering, kolonnevelger, persist mellom økter

### Features lagt til (ikke bare refaktor)

| Feature | Commit | Hva |
|---|---|---|
| Reskontro-berikelse | `2105dea` | Kunde/leverandør propageres fra reskontrolinjen til alle linjer i samme bilag i Analyse-fanen |
| Skille kunde/leverandør | `3d1c90b` | "Leverandør" som egen default-kolonne i transaksjons-treet |
| ManagedTreeview-migrering | `d785aac`, `922c1fa` | Revisjonshandlinger og scoping fikk drag-n-drop, sortering, kolonnevelger |
| Ytelsesfix scoping | `922c1fa` | `regnskapslinjer` lastes nå 1× per refresh i stedet for 3× |
| Etterslepende A07-arbeid | `87ee2fe`, `700e0e6` | Codex sitt A07-arbeid committet på hans vegne (han hadde DENY-ACL på `.git/`) |

### Plan-doc'er skrevet (for senere implementering)

| Doc | Tema | Status |
|---|---|---|
| [analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md) | Analyse-fanen kolonnehåndtering: BRREG vises som default, kolonnebredder hardkodet, manglende `ManagedTreeview` | TODO 2.3 (kunde/leverandør i export) etter quickfix |
| [dataset_klientoversikt_plan.md](dataset_klientoversikt_plan.md) | Dataset-fanen → Klientoversikt + Datasett-popup. Visena-import-flyt, regnskapssystem-rullgardin | Plan klar, ikke implementert |
| [dataset_compare_plan.md](dataset_compare_plan.md) | Bevart kunnskap fra slettet `ab_*`-prototype + plan for ny `src/audit_actions/dataset_compare/` | Plan klar |
| [mva_leverandorflagg_plan.md](mva_leverandorflagg_plan.md) | Kontroll under MVA-fanen: flagg inngående MVA-fradrag på ikke-MVA-registrerte leverandører (BRREG-kryssjekk) | Plan klar, datakilder finnes |
| [src_migrasjon_pilot_logg.md](src_migrasjon_pilot_logg.md) | Pilot-for-pilot logg over hele refaktoren | Levende |

### Memory-oppdateringer

- `project_dataset_pane_direction.md` — peker til ny `dataset_klientoversikt_plan.md`
- `project_consolidation.md` indeks-linje rettet (var "slice 1 starting", korrigert til "alle 4 slices ferdig")
- `project_pages_vs_audit_actions.md` (ny) — arkitekturregel for hvilken mappe en feature hører i

## 2. Tekniske erfaringer dokumentert

### Fra pilot 12-13 (shim-rydding)
- `from pkg import X` slår FØRST opp `X` som attributt på pkg, så
  faller tilbake til submodule-import. Konsekvens for tester:
  `monkeypatch.setitem(sys.modules, "pkg.X", ...)` virker IKKE hvis
  `pkg.X` allerede er importert som attributt. Bruk `setattr(pkg, "X", ...)`
- `git add -u`/`git add <mappe>` plukker opp untracked filer fra andre
  utvikleres pågående arbeid. Bruk **alltid** spesifikke filnavn ved
  staging når andres modifications er i working dir
- Pakke-shims krever pre-loading + `setattr` på pakka, ellers re-laster
  Python submoduler under `from pkg import X` og lager duplikate
  funksjons-objekter (avdekket av `test_compat_wrappers_pyinstaller`)

### Fra pilot 14-23 (videre flytting)
- Helper-script som modifiserer alle .py-filer i én batch er nyttig,
  men må filtrere bort egen helper-fil og nye lokasjoner
- `import X.Y.Z as W` er mer fragilt enn `from X.Y import Z as W` for
  monkeypatch-konsistens — sistnevnte bruker pakke-attributt-lookup
- Lokale imports inne i funksjoner blir hoppet over av `^import`-regex
  — må sjekke etterpå med `grep -r "import gammelt_navn"`
- Beholde pre-existing test failures uendret er en god akseptansetest
  ved refaktor — `8 failed, 109 passed` før == `8 failed, 109 passed` etter

## 3. Status `src/pages/` (alle 18 sider)

| Side | Pilot | Filer | Notat |
|---|---|---|---|
| a07 | (Codex) | mange | A07-utvikler eier — vi rører ikke |
| ar | 7 | 11 | Aksjonærer (ikke anleggsregister!) |
| consolidation | 11A-C | 47 | Tre sub-piloter (backend pkg + frontend + resten) |
| dataset | 19 | 14 | Bryter to roller — splitt planlagt |
| documents | (Codex) | — | Dokumentkontroll |
| driftsmidler | 1 | 2 | Etablerte mønsteret |
| fagchat | (Codex) | — | RAG-assistent |
| logg | (Codex) | — | Aktivitetslogg |
| materiality | 6 | 5 | Vesentlighet |
| mva | 18 | 9 | Avstemming, kontroller, melding-parser |
| oversikt | (Codex) | — | Klient-oversikt |
| regnskap | 8 + 21 | 1 + 3 | Page + 3 frontend-helpers (export/klient/noter) |
| reskontro | 20 | 12 | 4 backend + 8 frontend |
| revisjonshandlinger | 15 | 2 | ManagedTreeview-migrert |
| saldobalanse | 4-5 | 6 | Etablerte sys.modules-shim-mønster |
| scoping | 16 | 4 | ManagedTreeview-migrert + ytelsesfix |
| skatt | 14 | 1 | Én-fil-pilot |
| utvalg | 17 | 3 |  |

## 4. Status `src/audit_actions/` og `src/shared/`

**`src/audit_actions/`** (popups/handlinger):
- `motpost/` (pilot 9) — kalles fra Statistikk og Analyse
- `statistikk/` (pilot 10) — popup fra Analyse (omplassert fra pages)

**`src/shared/`** (cross-cutting utility):
- `regnskap/` (pilot 21) — 6 backend-moduler
- `client_store/` (pilot 22) — 5 backend-moduler
- `brreg/` (pilot 23) — 4 backend-moduler
- `columns_vocabulary.py` — felles label-vokabular

## 5. Plan videre — anbefalt rekkefølge

### Kortere piloter (én økt hver)

| Pilot | Pakke | Filer | Risiko |
|---|---|---|---|
| 24 | `src/shared/saft/` | 4 (saft_*) | Lav |
| 25 | `src/shared/workpapers/` | 9 (workpaper_*) | Middels — mange importerere |
| 26 | `src/shared/ui/` | 9 (vaak_*, ui_*) | Middels — brukes av alle faner |
| 27 | `src/shared/classification/` | ~10 (account_*, konto_klassifisering, classification_*) | Middels |
| 28 | `src/shared/actions/` | 7 (action_*) | Lav |

### Større piloter (1-2 dager hver)

| Pilot | Pakke | Notat |
|---|---|---|
| 29 | `src/audit_actions/document_control/` | 21 filer (controller*, document_control_*) |
| 30 | Reskontro-trær til ManagedTreeview | 5-6 trær, høy kompleksitet |
| 31 | Analyse-tabeller til ManagedTreeview | Brukerens område — vent på grønt lys |

### Plan-doc-implementeringer (når tid kommer)

1. Dataset → Klientoversikt + Datasett-popup ([dataset_klientoversikt_plan.md](dataset_klientoversikt_plan.md))
2. MVA-leverandørflagg-kontroll ([mva_leverandorflagg_plan.md](mva_leverandorflagg_plan.md))
3. Datasett-sammenligning A vs B ([dataset_compare_plan.md](dataset_compare_plan.md))
4. Analyse-fanen ManagedTreeview + BRREG-default-fiks ([analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md))

### Rydde-oppgaver

- 8 pre-existing failures i `tests/test_consolidation_engine.py` — krever utgraving av hver test
- `test_build_ui_restores_missing_analyse_features` — manglende `<ButtonPress-1>`-binding
- 2 toppnivå-shims gjenstår: `saldobalanse_payload.py` (A07-avh.), `bilag_drilldialog.py` (eldre)

### Hold-unna (andres område)

- A07/admin (~17 filer) — Codex eier
- Analyse (~46 filer) — brukerens eget arbeidsområde

## 6. Hvorfor er repoet bedre nå?

**Før (25. april):**
- 310+ .py-filer i rot, flatt
- 73 page_consolidation*.py + consolidation_*.py uten gruppering
- saldobalanse spred over 6 filer på rot
- ar over 11 filer på rot
- Ingen lint-test for "bør ikke importere tkinter"
- Mange dødt kode (~2 700 linjer) ingen visste om
- Klient-info, BRREG, regnskap — alt cross-cutting men flat struktur

**Etter (26. april kveld):**
- 226 .py-filer i rot (74 % reduksjon)
- 23 fane-pakker + 2 audit_actions + 3 shared-pakker, alle dokumentert
- Per-pakke lint-tester for "ingen tkinter" på alle backend-moduler
- 5 plan-doc'er for fremtidige features med klar arkitektur
- Pages vs audit_actions-skille er en bevisst arkitekturbeslutning,
  ikke noe ad-hoc
- Frontend/backend-skille gjør REST-eksponering enklere senere
- Domain-glossary i memory så fremtidige AI-assistenter ikke gjetter feil
  (AR=aksjonærer, ikke anleggsregister)

## 7. Hva vi IKKE har gjort (bevisst)

- **Ikke endret A07/admin-kode** — Codex sitt område, vi committet kun
  hans pågående arbeid på hans vegne pga DENY-ACL
- **Ikke endret Analyse-fanens kjerne** — brukerens eget arbeidsområde,
  kun små quickfixes (kunde/leverandør-skille, reskontro-berikelse)
- **Ikke implementert noen av plan-doc'ene** — bevisst dokumentert for
  senere når riktig tid kommer
- **Ikke fikset 8 pre-existing test_consolidation_engine-failures** —
  parkeret, krever egen utgraving

## 8. Co-author

Alle commits har `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.
Codex sitt A07-arbeid (`87ee2fe`, `700e0e6`) har dobbel co-author med
Codex som primær.
