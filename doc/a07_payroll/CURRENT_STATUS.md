# A07: Gjeldende Status Og Videre Plan

Sist oppdatert: 2026-04-26.

Dette dokumentet er den korte operative statusen for A07. Den lange historikken,
bakgrunn og detaljer ligger fortsatt i `STATUS_AND_GOAL.md`, `MODULE_MAP.md` og
`RF1022_CONTRACT.md`.

## Kort Konklusjon

A07 er teknisk mye ryddigere enn tidligere, men er ikke produktmessig ferdig.
Vi har fjernet mye strukturell risiko og gammel GUI-stoy, men arbeidsflyten maa
fortsatt bli mer forstaaelig, trygg og effektiv for faktisk revisjonsbruk.

Viktig prinsipp fremover: Vi skal ikke lage oppgaver bare for aa lage oppgaver.
Videre arbeid skal starte med konkrete funn: kodepunkt, skjermbilde,
testscenario, eller en tydelig brukerflyt som faktisk er forvirrende eller
farlig.

## Dette Er Gjort

### Struktur Og Modulgrenser

- Offentlig A07-shell er flyttet til `src/pages/a07/page_a07.py`.
- Root-filen `page_a07.py` er beholdt som compat-shim.
- `a07_feature/` er beholdt som intern motor/runtime mens strukturen modnes.
- Store A07-filer er splittet i mindre moduler med modulbudsjetter.
- Testmonolitten er splittet til `tests/a07/`.
- `tests/test_a07_module_budgets.py` og `scripts/report_a07_module_sizes.py`
  beskytter mot nye monolitter.
- Frontend/backend-retningen er etablert:
  - Tk/dialog/layout flyttes til `src/pages/a07/frontend`.
  - Rene data-/motorfunksjoner flyttes mot `src/pages/a07/backend` eller
    rene `a07_feature`-motorpakker.
  - Full separasjon er startet, men ikke fullfort.

### A07 Hovedflate

- Den gamle `Lonn`-fanen er fjernet som egen fane.
- A07-fanen er gjort til hovedflate for A07/A-melding mot GL.
- Hovedflaten er forenklet rundt fire arbeidsflater:
  - `Saldobalansekontoer`
  - `A07-koder`
  - `Forslag`
  - `Koblinger`
- Det gamle nederste notebook-moensteret er faset ut.
- Historikk, umappet og grupper er flyttet vekk fra fast hovedflate.
- A07-grupper finnes fortsatt, men vises via egen gruppeknapp/popup og
  hoyreklikkflyt.
- Det er lagt inn `Skjul null` for aa redusere stoy fra nullkontoer.
- Drag-and-drop har faatt tydeligere visuell feedback.

### Automatching Og Guardrails

- Oppstart/refresh skal ikke automatisk odelegge eksisterende riktige mappinger.
- A07-koder med `Diff = 0` skal behandles som ferdige i hovedflyten.
- Automatching og tryllestav skal ikke endre laaste koder, trygge mappinger
  eller ferdige 0-diff-koder.
- Auto-matching krever streng evidens og skal feile lukket.
- `annet` behandles som siste-utvei/review-kode, ikke som vanlig trygg match.

### Residual-Solver / Tryllestav

- Residual-solver v1 er lagt til under `a07_feature/suggest/`.
- Solver jobber deterministisk i oere/int, ikke floats.
- Solver analyserer aapne differanser og returnerer review-/forslagsrader.
- Auto-apply er bare tillatt ved eksplisitt trygg eksakt losning.
- Mistenkelige rester, gruppeforslag og splittebehov skal vises som review,
  ikke som automatisk fasit.

### RF-1022 Og Kontrolloppstilling

- RF-1022 er behandlet som kontroll-/oppsummeringsnivaa, ikke som primar
  A07-matchingflate.
- Kontrolloppstillingen har faatt RF-1022-visning med:
  - opplysningspliktig spor
  - AGA-pliktig spor
  - diff per spor
  - tydeligere topprapport/summeringskort
  - `SUM`-rad nederst
- `Diff = 0` med svak faglig audit vises som `Avstemt` i hovedflaten, mens raa
  auditstatus beholdes for review/solver.
- RF-1022 popup/legacy-duplikat er ryddet ut av hovedmenyen.

### Gammel Rot Som Nylig Er Ryddet

- Skjulte compat-traer er fjernet fra runtime:
  - `tree_suggestions`
  - `tree_mapping`
  - `tree_control_statement`
  - `tab_reconcile`
  - `tree_reconcile`
- Gamle bindings/render-grener som bare sjekket disse traerne er fjernet.
- Kontrolloppstillingspanelet er ryddet slik at det ikke later som en skjult
  overview-tree fortsatt finnes.
- `_remove_selected_mapping` fra gammelt skjult mappingtre er fjernet.
- `tests/a07/shared.py` er ryddet for gamle `_obsolete_...` testhjelpere.

## Status Naa

### Teknisk

- A07-testpakken er gronn etter siste opprydding:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/a07 --no-cov -q
.\.venv\Scripts\python.exe -m pytest tests/test_a07_backend_no_tk.py tests/test_a07_namespace_smoke.py tests/test_a07_ui_canonical_namespace_smoke.py tests/test_page_a07_payroll.py --no-cov -q
.\.venv\Scripts\python.exe -m pytest tests/test_a07_module_budgets.py --no-cov -q
```

- `tests/test_page_saldobalanse.py` har per siste sjekk en separat feil i
  `test_load_owned_company_name_map_filters_invalid_rows`. Den ser ut til aa
  ligge i AR/eierskap/saldobalanse-testoppsettet, ikke i A07-oppryddingen.

### Produktmessig

A07 er fortsatt ikke godt nok som sluttbrukerflyt. De viktigste problemtypene er:

- Brukeren maa tydeligere forstaa hva som er ferdig, trygt, avstemt, svakt,
  mistenkelig eller manuelt.
- Solver/tryllestav, grupper og forslag maa oppleves som en samlet arbeidsflyt,
  ikke som separate tekniske funksjoner.
- Hoyreklikkmenyer og verktoymeny maa holdes korte og praktiske.
- Kontrolloppstilling/RF-1022 maa vise revisjonsnyttige summer uten aa bli en
  duplikat-GUI.
- Gamle compat-lag finnes fortsatt flere steder og maa fjernes gradvis naar det
  er bevist at de ikke brukes.
- Frontend/backend-skillet er bedre, men ikke profesjonelt fullfort.

## Ting Vi Ikke Skal Rore Uten God Grunn

- `Laer regel` skal beholdes. Den er kjernefunksjon.
- A07-grupper skal beholdes.
- Manuell mapping skal beholdes.
- Tryllestav/solver skal beholdes, men maa bli tydeligere.
- Lagret mappingformat `konto -> A07-kode` skal ikke endres uten egen beslutning.
- Automatching skal aldri overskrive ferdige 0-diff-koder.
- RF-1022 datamotor skal beholdes selv om duplikat-GUI fjernes.

## Videre Plan

### 1. Fortsett Med Bevisbar Rot

Rydd bare ting som er aapenbart doedt, duplisert eller compat-stoy.

Eksempler paa trygge kandidater:

- ubrukte wrappers
- gamle menuvalg som ikke lenger har synlig funksjon
- testhjelpere med `_obsolete_`
- defensive `getattr(..., None)`-grener for widgets som ikke lenger bygges
- compat-importer der smoke-tester viser at de ikke trengs

Akseptkriterium: Ingen brukerflyt skal endres uten at vi kan forklare hvorfor.

### 2. Lag En Konkret A07 Produkt-Audit

Neste nyttige ikke-kodearbeid er en audit-liste med konkrete funn:

- faktisk feil
- sannsynlig brukerforvirring
- legacy/stoy
- faglig uklarhet
- teknisk gjeld

Hvert funn maa ha en kilde: kodepunkt, skjermbilde, test, eller observert
brukerflyt. Dette hindrer at vi finner paa arbeid.

### 3. Rydd Arbeidsflyten

Prioritet etter audit:

- forenkle hoyreklikkmenyer
- rydde verktoymeny
- tydeliggjore statusbegreper
- gi grupper en klarere visning
- gjore tryllestav-resultater enklere aa handle paa
- unngaa tekstvegger i hoved-GUI

### 4. Gjor Solver Og Grupper Mer Praktiske

Solver v1 finnes, men flyten maa bli mer nyttig:

- vise kort scenario-status
- foreslaa gruppe naar flere A07-koder bor ses samlet
- vise lange kontolister kompakt
- skille tydelig mellom `trygg losning`, `maa vurderes`, `krever gruppe`,
  `krever splitt` og `mistenkelig rest`

### 5. Fortsett Frontend/Backend-Skillet Naar Featurearbeid Treffer Det

Ikke gjor bred refaktor bare for aa refaktorere. Men naar vi uansett jobber i
et omraade:

- flytt ren data-/planlogikk ut av page-mixins
- la frontend eie Tk/dialog/status/rendering
- la backend ta DataFrames/dicts/primitive input og returnere strukturerte
  resultater
- behold compat til en egen oppryddingsrunde

## Neste Mest Hensiktsmessige Runde

Hvis vi fortsetter med A07 naa, anbefalt neste runde er:

1. Lage en A07 audit-liste over konkret rot/forvirring med filreferanser.
2. Fjerne neste lille, bevisbart doede legacy-slice.
3. Deretter velge en brukerflyt aa forbedre: sannsynligvis grupper/tryllestav
   eller hoyreklikk-/verktoymeny.

Dette holder oss unna "oppgaver for oppgavenes skyld" og retter arbeidet mot
det som faktisk gjor A07 bedre.
