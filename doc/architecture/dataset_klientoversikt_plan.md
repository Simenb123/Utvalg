# Dataset-fanen → Klientoversikt — status quo og ønsket retning

**Sist oppdatert:** 2026-04-26

Dokumenterer dagens organisering av klient-info, regnskapssystem-flagg
og Visena-import. Beskriver ønsket fremtidig retning der Dataset-fanen
blir en klientoversikt-side, og selve datasett-håndteringen (regnskaps-
data) flyttes til en egen popup. **Ingen kode endres som følge av dette
dokumentet** — det er en plan å gjennomføre senere på riktig tidspunkt.

## 1. Status quo

### 1.1 Hva Dataset-fanen er i dag

Dataset-fanen er en hybrid mellom datakilde-velger og klient-info-visning.
Den embedder [DatasetPane](../../dataset_pane.py) som inneholder:

1. **Datakilde-blokken (øverst)** — klient-bytter, år-combobox, versjons-
   knapp, status-pills (HB/SB/KR/LR). Beskrevet i
   [dataset_pane_versioning.md](dataset_pane_versioning.md).
2. **Klient-info-blokken (midten)** — tre LabelFrames side-ved-side via
   [dataset_pane_store_ui.py:99-200](../../dataset_pane_store_ui.py):
   - **Selskap** (orgnr, knr, orgform, næring, MVA-reg, adresse,
     stiftelsesdato, ansatte, hjemmeside, kapital, antall aksjer, status)
   - **Roller** (fra BRREG)
   - **Team** (fra Visena)
3. **Sheet/header/mapping-velger (under)** — for valg av Excel-sheet,
   header-rad og kolonne-mapping.
4. **Eksport-knapp (nederst)** — eksporter HB til Excel.

Klient-info-feltene fylles i to steg:

- **Synkront** fra `client_meta_index.json` (lokal indeks med orgnr, knr,
  responsible, manager, team_members) — under 10ms per klient
- **Asynkront** fra BRREG via `_update_brreg_fields` — orgform, næring,
  adresse, stiftelsesdato, ansatte, kapital, antall aksjer, status, roller

### 1.2 Hvor klient-data lagres

Klient-data ligger spredt på fire filplasseringer per klient:

| Lokasjon | Innhold | Format |
|---|---|---|
| `<clients_root>/<client>/meta.json` | org_number, client_number, responsible, manager, team_members + brukervalg | JSON |
| `<data_dir>/client_meta_index.json` | rask oppslagstabell over alle klienter (den samme dataen, denormalisert) | JSON |
| `<data_dir>/regnskap_client_overrides/<client>.json` | accounting_system, mva_code_mapping, account_overrides, prior_year_overrides | JSON |
| BRREG-cache (per orgnr) | navn, adresse, roller, kapital, status osv. | JSON |

API-er for å lese/skrive:
- [client_store.read_client_meta()](../../client_store.py) / `update_client_meta()` — meta.json
- [client_meta_index.get_index()](../../client_meta_index.py) / `update_entry()` — indeksen
- [regnskap_client_overrides.load_accounting_system()](../../regnskap_client_overrides.py) /
  `save_accounting_system()` — regnskapssystem (Tripletex, PowerOffice GO, Xledger osv.)
- [brreg_client.fetch_company](../../brreg_client.py) — async BRREG-oppslag

### 1.3 Hvordan Visena-import fungerer i dag

Visena er regnskapsbyrået-systemet du henter klientlister og team-tilhørighet
fra. **Det finnes to separate import-veier**:

#### A. Klient-liste-import (lager klient-mapper)

[client_store_import.py](../../client_store_import.py):
- Leser **XLSX, CSV eller TXT** med klientnavn (én per linje eller én rad
  i kolonnen "Klient"/"Firma"/"Kunde")
- For Visena XLSX detekteres kolonnene **"Firma" + "Knr"** automatisk og
  display-navnet bygges som `"<Knr> <Firma>"`
- Oppretter klient-mapper på disk via `client_store.add_client()`

#### B. Berikelse — koble Visena-rader til eksisterende klienter

[client_store_enrich.py](../../client_store_enrich.py) +
[client_store_enrich_ui.py](../../client_store_enrich_ui.py):
- Leser **Visena-prosessliste-XLSX** med kolonner: Firma, OrgNr, KlientNr,
  Prosjekt, Ansvarlig, Har som manager, Har som prosjektmedlem
- 3-trinns matching mot eksisterende klient-display-navn:
  1. Eksakt Knr-match
  2. Eksakt navnematch (normalisert)
  3. Fuzzy navnematch (SequenceMatcher >= 0.85)
- Oppdaterer **meta.json** og **client_meta_index.json** med felt:
  `org_number`, `visena_responsible`, `visena_manager`, `visena_team_members`

**Inngang i UI** (her er friksjonspunktet):
- Berikelse startes via **"Klient"-fanen i Regnskap-siden** (ikke Dataset!)
  — [src/pages/regnskap/frontend/page.py:760](../../src/pages/regnskap/frontend/page.py#L760)
  kaller `regnskap_klient.start_enrichment()` som åpner
  `client_store_enrich_ui.start_enrichment_flow()`
- Klient-listing-importen (A) har et separat innmatningspunkt
  (en knapp under Klienter-listen, men ikke samme sted som B)

### 1.4 Regnskapssystem — flyt og synlighet

[mva_codes.py:65-76](../../mva_codes.py#L65) — gyldige verdier:
`Tripletex, PowerOffice GO, Xledger, Visma Business, Visma eAccounting,
Fiken, Uni Economy, 24SevenOffice, SAF-T Standard, Annet`.

**Tre måter feltet kan settes:**
1. **Auto-detect ved SAF-T-import** —
   [dataset_pane_build._auto_detect_saft_system()](../../dataset_pane_build.py#L47)
   kaller `saft_reader.detect_accounting_system(header)` og lagrer hvis
   feltet ikke er satt fra før
2. **Manuell endring** — kun via [mva_config_dialog.py](../../mva_config_dialog.py)
   (en sub-dialog under MVA-oppsett, gjemt langt unna hovedflyten)
3. **Programmatisk** — via `regnskap_client_overrides.save_accounting_system()`

**Konsumenter** (hvor det leses):
- `page_analyse_mva.py:43` — for å filtrere MVA-kode-mapping
- `mva_config_dialog.py` — for å vise og endre

**Synlighet i UI:** Ingen i hovedflyten. Brukeren må åpne MVA-oppsett-
dialogen for å se hvilket regnskapssystem som er valgt for klienten.

## 2. Konkrete problemer

1. **Regnskapssystem er usynlig.** Settes implisitt fra SAF-T og kan kun
   endres via en sub-dialog i MVA-oppsett. Brukeren må huske at feltet
   finnes og at det påvirker MVA-mapping og evt. SAF-T-tolkning.

2. **Klient-info ligger spredt på flere faner.** Dataset viser BRREG +
   meta synkront. Regnskap-siden har en egen "Klient"-fane med roller +
   start-enrichment-knapp. Det skaper to "sannheter" om hvor man finner
   klient-data.

3. **Visena-import-startpunkt er ikke der man forventer det.** En revisor
   som skal koble Visena-data til Utvalg, ville naturlig søkt under
   Dataset (siden det er der klient-info vises) eller en egen
   "Klienter"-side — ikke under Regnskap.

4. **Manuell legg-til av orgnr mangler.** Hvis en klient ikke har orgnr
   i client_meta_index, må brukeren enten gjøre Visena-berikelse, eller
   redigere meta.json for hånd. Det er ingen "Legg til orgnr"-knapp i UI.

5. **Dataset-fanen blander to roller.** Den er både:
   - Klient-info-vindu (det er her brukeren ser hvem klienten er)
   - Datakilde-velger (HB/SAF-T/SB-fil + sheet/header/mapping)
   
   Disse to bør være separate. Brukeren oppgir at datasett-håndteringen
   er sjeldnere enn klientoversikt-bruk og bør være en popup.

## 3. Ønsket retning

### 3.1 Dataset-fanen → Klientoversikt

Dataset-fanen omdøpes til **"Klient"** (eller "Klientoversikt"), og det
blir hjemmen for alt som handler om hvem klienten er. Innhold:

- **Klient-velger** øverst (som i dag)
- **År-velger** (samme)
- **Selskap-LabelFrame** med utvidede felt:
  - Org.nr (med "Legg til"-knapp hvis tom)
  - Knr
  - Regnskapssystem (rullgardin med ACCOUNTING_SYSTEMS-listen, lagrer
    direkte når brukeren bytter)
  - Resten som i dag (orgform, næring, adresse osv. fra BRREG)
- **Roller** (BRREG, som i dag)
- **Team** (Visena, som i dag, med "Oppdater fra Visena"-knapp lokalt)
- **Knapper** (en aksjonslinje):
  - "Legg til/endre klientinfo" — popup med redigerbart skjema for
    org.nr, knr, regnskapssystem, evt. andre felter (uten å åpne MVA-
    dialog eller Regnskap-fanen)
  - "Importer klienter (Visena XLSX)" — flyttet hit fra dagens
    nåværende plass
  - "Berik mot Visena…" — flyttet hit fra Regnskap-fanen
  - "Datasett…" — åpner ny popup beskrevet under

### 3.2 Datasett-popup

All datasett-håndtering (HB/SAF-T-fil-velger, sheet/header, kolonne-
mapping, versjoner, eksport-til-Excel) flyttes til en egen popup som
åpnes med "Datasett…"-knappen fra klientoversikten. Innhold:

- Versjons-velger (HB/SB/KR/LR-pills som i dag)
- Filsti + sheet/header/mapping (som i dag)
- Status og bygge-knapp
- Eksport-til-Excel
- Forbedret GUI: tydeligere skille mellom "aktiv versjon", "tilgjengelige
  versjoner" og "importer ny"

Brukeren oppgir at datasett-håndtering er en **handling man gjør innimellom**
(ved import av nytt regnskapsår, bytte til SAF-T osv.), ikke noe man bor i.
Derfor passer popup-formatet bedre.

Strukturmessig blir popup'en en kandidat for `src/audit_actions/datasett/`
når den lages — i tråd med pages-vs-audit_actions-skille
(jf. [src/pages vs audit_actions](../../) memory og
[src_struktur_og_vokabular.md](src_struktur_og_vokabular.md)).

### 3.3 Regnskapssystem som førsteklasses felt

Regnskapssystem flyttes til Selskap-frame som rullgardin (Combobox)
direkte — ikke gjemt i sub-dialog. Lagring skjer ved valg-endring via
`regnskap_client_overrides.save_accounting_system()`. Endringen
trigger `bus.emit("client_meta_changed")` slik at MVA-fanen og andre
konsumenter får beskjed.

På sikt kan vi vurdere om verdien også bør speiles i
`session.accounting_system` for raskere oppslag (i dag krever det disk-
oppslag i `regnskap_client_overrides`).

### 3.4 Kilde-indikator for auto-detekterte felt

For felter som kan ha tre kilder (auto-detektert, manuelt valgt, BRREG-
hentet) bør UI vise diskret hvor verdien kommer fra. Eksempel for
regnskapssystem: liten merknad bak combobox-en — `(auto fra SAF-T)` /
`(manuelt)`. Implementasjon krever utvidelse av payload i
`regnskap_client_overrides` til å lagre `accounting_system_source` i
tillegg til verdien selv.

### 3.5 Manuell legg-til av orgnr

I dag må man enten gjøre full Visena-berikelse eller redigere meta.json
for hånd. Vi vil ha en eksplisitt UI-flyt:

- "Org.nr: –" som viser tom verdi (i dag)
- Pil/blyant-ikon eller hover-knapp som åpner inline-redigering eller
  liten popup med:
  - Org.nr-felt (9 siffer, validering)
  - "Slå opp i BRREG"-knapp som forhåndsutfyller navn/adresse/osv.
  - "Lagre"-knapp
- Lagring oppdaterer meta.json + client_meta_index.

Samme mønster bør gjelde for **Knr** (klientnummer) — det er ofte tomt
hvis klienten er importert manuelt og ikke matcher en Visena-rad.

## 4. Konsekvenser for andre faner

- **Regnskap-fanen "Klient"-undertab:** Når Visena-berikelse og roller-
  håndtering flyttes til Klientoversikt, blir denne undertaben tom. Den
  kan enten fjernes helt eller forenkles til kun signatar-håndtering
  (som er regnskap-spesifikt, ikke generell klient-data).
- **MVA-config-dialog:** Beholder mva_code_mapping, men "Regnskapssystem"-
  rullgardinen i toppen kan fjernes (verdien settes nå fra Klientoversikt).
  Dialog viser kun verdien som read-only ("Klient bruker: Tripletex").
- **Oversikt-fanen** (`src/pages/oversikt/`) bruker `client_store_enrich.is_my_client()`
  — fortsatt relevant, ingen endring nødvendig.
- **A07-fanen, AR-fanen, Saldobalanse-fanen, Konsolidering-fanen** —
  alle leser klient-info via samme API-er (`client_meta_index`,
  `client_store.read_client_meta`). Ingen endring nødvendig så lenge
  API-ene er stabile.

## 5. Rekkefølge for implementering (når tid kommer)

Forslag i tre størrelser:

**Fase 1 (lite, ~1 dag):** Regnskapssystem som rullgardin i Selskap-frame.
- Legg til `regnskapssystem`-rad som Combobox i `dataset_pane_store_ui`
- Bind til `regnskap_client_overrides.{load,save}_accounting_system`
- Skriv ny tekst inn ved auto-detect

**Fase 2 (middels, ~2-3 dager):** "Legg til klientinfo"-knapp og popup
for orgnr/knr-redigering.
- Ny dialog med org.nr, knr, regnskapssystem-felt
- BRREG-oppslag-knapp
- Lagring til både meta.json og client_meta_index

**Fase 3 (større, ~1 uke):** Splitt Dataset → Klientoversikt + Datasett-popup.
- Ny `src/audit_actions/datasett/` med versjons-velger, sheet/header/mapping
- Klientoversikt blir slank: kun klient-info + handlinger
- Visena-import-knappene flyttes hit
- Regnskap-fanens "Klient"-undertab forenkles eller fjernes

**Fase 4 (utforskning):** "Flere åpne API"-utvidelse fra
[Dataset-fanen retning](../../) memory:
- Kunngjøringer fra Brønnøysund
- Kunngjorte regnskap (PDF-nedlasting + parser)
- Revisor-historikk (tidligere revisor for klient)
- Konsernstruktur fra BRREG

## 6. Relaterte dokumenter

- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  pages vs audit_actions-skille (datasett blir audit_action)
- [dataset_pane_versioning.md](dataset_pane_versioning.md) — versjons-
  håndtering (uendret av denne planen, men vil flyttes til popup)
- [columns_vocabulary.md](columns_vocabulary.md) — felles label-vokabular
- [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) — tabell-mønster

## 7. Memory-notat for AI-assistenter

I [project_dataset_pane_direction.md](../..) er det allerede notert:

> Dataset-fanen retning — Minimér datakilde-seksjon, utvid klient-info,
> utforsk flere åpne API.

Dette dokumentet er den utvidede versjonen av samme retning, med konkrete
brukerønsker fra 2026-04-26.
