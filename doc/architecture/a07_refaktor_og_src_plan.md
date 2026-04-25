# A07 Refaktor- Og `src/`-Plan

**Sist oppdatert:** 2026-04-25

Dette dokumentet beskriver den vedtatte arbeidsretningen for videre
refaktorering av A07 i Utvalg. Dokumentet skal brukes som styringsgrunnlag
naar vi splitter store filer, rydder laggrenser og gradvis flytter A07 inn i
repoets `src/pages/`-struktur.

## Hvorfor Vi Gjor Dette

A07 har blitt en viktig arbeidsflate i Utvalg, men er fortsatt preget av eldre
lagdeling:

- for store moduler
- stor blanding av GUI, runtime-state og ren logikk
- en offentlig entrypoint i repo-roten
- testfiler som er blitt for brede til aa vaere lette aa vedlikeholde

Samtidig er retningen i repoet tydelig:

- faner skal gradvis samles under `src/pages/`
- ren, gjenbrukbar logikk skal skilles tydelig fra GUI
- featureklynger skal kunne utvikles stegvis uten store "big bang"-flytt

Maalet er ikke bare aa rydde A07-fanen. Maalet er aa bygge en A07-motor som paa
sikt kan gjenbrukes i andre flater og andre arbeidsflyter.

## Styrende Beslutninger

Dette er arbeidsreglene vi styrer etter videre:

- `1000` linjer er hard grense per A07-modul.
- `400` linjer er maal per kodemodul.
- Testmoduler skal ogsaa splittes ned; store testfiler skal ikke brukes som
  permanent oppsamlingsplass.
- Hver modul skal ha ett hovedansvar: `engine`, `orchestration`, `ui`,
  `storage`, `compat` eller `tests`.
- Ren logikk skal ikke vaere avhengig av `tkinter`, widgets, `session` eller
  page-spesifikk state hvis den skal vaere gjenbrukbar.
- `page_a07.py` beholdes som compat-shim saa lenge repoet fortsatt har gamle
  importer.
- Vi gjor ikke en stor totalflytt av hele `a07_feature/` i ett steg.

## Arkitekturmaale

Vi vil ha fire tydelige lag:

1. **Frontend/page shell**
   Ligger under `src/pages/a07/frontend/` og eier Tk, layout, dialoger,
   kontekstmenyer, kontrolloppstilling-vinduer, statuslinjer og visuell
   rendering.

2. **Backend/motor**
   Ligger under `src/pages/a07/backend/` naar logikken er moden nok til aa ha
   en hard headless-grense. Backend tar DataFrames, dicts og primitive verdier
   inn, og returnerer strukturerte resultater ut.

3. **Controller/orkestrering**
   Ligger under `src/pages/a07/controller/` naar vi trenger page-spesifikk
   koordinering som ikke bygger widgets og ikke er ren motorlogikk. Dette laget
   skal holdes smalt.

4. **Compat/legacy motorflate**
   `a07_feature/` lever videre som intern A07-featureflate og compat-lag mens
   vi flytter ansvar gradvis. Gamle imports skal fungere til vi eksplisitt tar
   en egen cleanup-runde.

Viktig konsekvens:

- `src/pages/a07/frontend/` skal ikke inneholde ren datalogikk.
- `src/pages/a07/backend/` skal ikke importere `tkinter`, dialogs, widgets,
  frontend, controller eller page-`self`.
- `src/pages/a07/controller/` skal ikke bli en ny dumpesone for motorlogikk.
- `a07_feature/` kan fortsatt eie intern motor i overgangsfasen, men ny ren
  logikk trekkes mot backend naar grensen er klar.

## Status Etter Siste Arkitekturrunde

Per 2026-04-25 er A07 ikke bare splittet i mindre filer; den har en faktisk
frontend/backend-grense som testes.

Ferdig canonical struktur:

- `src/pages/a07/frontend/page.py` er fysisk A07-page shell.
- `src/pages/a07/frontend/control_statement_ui.py`,
  `control_statement_panel_ui.py`, `control_statement_window_ui.py` og
  `rf1022.py` eier GUI-flater som tidligere laa i backend-lignende omraader.
- `src/pages/a07/backend/` er etablert som headless backend-namespace.
- `src/pages/a07/page_a07.py` og rotfilen `page_a07.py` er compat-shims.
- `a07_feature/control/statement_*.py` og `a07_feature/payroll/rf1022.py`
  peker videre til canonical frontend der det er GUI.

Backend-slices som er trukket ut:

- `control.py`: facade for ren kontroll-/statementdata.
- `payroll.py`: ren payroll-classification facade.
- `rf1022.py`: headless RF-1022 source/data-builder.
- `suggest.py`: residual-solver/suggest facade.
- `mapping_apply.py`: trygg mapping-apply for residual/tryllestav/history.
- `project_io.py`: prosjektstate, mapping-path decisions og filskriving uten GUI.
- `control_actions.py`: planlegging og utforying av konto-til-kode handlinger.
- `candidate_actions.py`: RF-1022/global-auto tellerverk og trygg plan-apply.

Guardrails som beskytter grensen:

- `tests/test_a07_backend_no_tk.py` feiler hvis canonical backend importerer
  Tk, frontend, controller eller A07-UI.
- `tests/test_a07_module_budgets.py` holder modulene innenfor avtalte
  linjebudsjetter.
- `tests/a07/*` er splittet etter runtime-ansvar og erstatter den gamle store
  `tests/test_page_a07.py`-flaten.

Gjenvaarende blandede omraader som bevisst ikke er siste-steg-ryddet ennaa:

- refresh/scheduler/watchdog, fordi den har hoy regresjonsrisiko
- enkelte page-mixins som fortsatt eier GUI-status, fokus og autosave
- context menus/dialoger der brukerflyt fortsatt modnes
- bredere cleanup av gamle compat-shims

## Planlagt Flytteretning For `src/`

`src/pages/`-migreringen for A07-page-entrypoint er gjennomfort:

- `src/pages/a07/` finnes.
- `src.pages.a07` er kanonisk offentlig importflate for fanen.
- `page_a07.py` i repo-roten er compat-fasade/re-eksport i en overgangsperiode.
- `ui_main.py` bruker ny importsti.

Det vi fortsatt **ikke** gjor i samme steg:

- vi flytter ikke hele `a07_feature/` fysisk til `src/pages/a07/`
- vi binder ikke ren motorlogikk tettere til page-laget
- vi river ikke opp alle gamle imports samtidig

Dette var og er en kontrollert entrypoint-migrering, ikke en total
omorganisering i ett kutt.

## Prioritert Arbeidsrekkefolge

### Fase 1: Splitt Ned De Storste Hotspotene

Foerste prioritet er aa faa ned de store filene som fortsatt gjor A07 tung aa
jobbe i.

Naavaerende hovedhotspots:

- `tests/test_page_a07.py`
- `a07_feature/page_a07_mapping_actions.py`
- `a07_feature/ui/support_render.py`
- `a07_feature/page_a07_context.py`

Rekkefolge:

1. Splitt `tests/test_page_a07.py` etter ansvar.
2. Splitt `page_a07_mapping_actions.py` i mindre action-/service-moduler.
3. Splitt `ui/support_render.py`.
4. Splitt `page_a07_context.py`.
5. Fortsett med andre moduler som fortsatt ligger over grenseverdiene.

### Fase 2: Flytt Offentlig A07-Entrypoint Til `src/pages/a07`

Status: gjennomfort for offentlig page-entrypoint.

Ferdig:

- `src/pages/a07/page_a07.py` er kanonisk page shell.
- `page_a07.py` i repo-roten er compat-shim.
- Tester dekker baade kanonisk og compat-import.

Videre arbeid i denne fasen handler bare om opprydding rundt page-spesifikke
compat-flater, ikke om aa flytte ren motorlogikk inn i `src/pages/a07`.

### Fase 3: Rydd Page-Spesifikk Kode Inn I `src/pages/a07`

Etter entrypoint-flytten kan page-spesifikk kode gradvis samles der:

- page shell
- page-spesifikk UI-komposisjon
- page-spesifikk orkestrering
- compat-lag som bare finnes for A07-fanen

Dette skal skje gradvis og bare naar modulgrensene er tydelige.

### Fase 4: Modn Motoren For Gjenbruk

Naar A07 er godt splittet og page-laget er tydelig:

- identifiser ren logikk som ikke er A07-GUI-spesifikk
- hold den fri for `tkinter`, `session`, dialogs og widget-state
- vurder flytting til egnet delt/domeneorientert plass under `src/`

Dette er et senere steg. Vi velger ikke endelig plassering for alt dette na,
men vi bygger modulene slik at den flytten blir mulig.

Ny residual-solver er et eksempel paa denne retningen:

- `a07_feature/suggest/residual_solver.py` er ren motorlogikk.
- Den jobber med DataFrames/dicts og dataclasses, ikke widgets.
- Belop behandles i oere/int for deterministisk matching.
- Page-laget i `a07_feature/page_a07_mapping_residual.py` kaller motoren og tar
  GUI-/statusansvaret.
- `src/pages/a07` skal fortsatt bare vaere shell/orkestrering, ikke solver-eier.

## Modulregler Vi Skal Jobbe Etter

### Kodemoduler

- `<= 400` linjer: oensket standard
- `401-1000` linjer: akseptabelt midlertidig, men skal vurderes for splitt
- `> 1000` linjer: aktivt refaktormaal

### Testmoduler

- tester skal speile modulgrensene i runtime
- store tester splittes etter ansvar, ikke tilfeldig etter historikk
- GUI-, compat-, engine- og regressjonstester skal ikke samles i samme store fil

### Ansvarsdeling

Eksempler paa oensket ansvar per modul:

- `engine`: ren datalogikk og transformasjoner
- `orchestration`: setter sammen kall og payloads
- `ui`: widgets, layout, bindinger og rendering
- `storage`: lasting/lagring av persistente data
- `compat`: re-eksport og bakoverkompatibilitet

Eksempler paa uoensket blanding:

- widgets + DataFrame-regler i samme modul
- `session`-oppslag midt i ren matchinglogikk
- stor page-metode som baade leser state, bygger data og muterer GUI

## Praktiske Regler For Flytt Og Refaktor

- Ingen "big bang"-refaktor.
- En refaktorbølge skal vaere liten nok til aa holdes groen.
- Compat beholdes eksplisitt naar vi flytter offentlige symboler.
- Nye kanoniske moduler skal komme foer gamle shim-lag fjernes.
- Tester og dokumentasjon oppdateres i samme runde som strukturen endres.
- Bruk `git mv` ved reelle filflytter naar vi vil bevare historikk.

## Definition Of Done For Hver Runde

En A07-refaktorrunde er ikke ferdig foer:

- modulgrensen er tydeligere enn foer
- runtime-atferd er uendret eller bevisst justert
- compat-flater fortsatt virker der de skal
- relevante tester er oppdatert og groenne
- dokumentasjonen er oppdatert hvis vi endret struktur eller arbeidsretning

## Hva Vi Ikke Skal Glemme

- A07 er baade en fane og en motor. Hvis vi bare optimaliserer for fanen, blir
  gjenbruk senere dyrt.
- `src/pages/a07` er riktig retning for page shell, men feil sted for all ren
  motorlogikk.
- Maalet er ikke bare mindre filer. Maalet er tydeligere lag, enklere testing
  og bedre framtidig gjenbruk.
- Funksjonelle steg som residual-solver skal dokumenteres som motorprinsipper,
  ikke bare som GUI-knapper. Trygghet, laasing og review-only-regler er del av
  arkitekturen.
