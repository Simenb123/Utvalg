# AI-bilag-agent — visjon og veikart

**Sist oppdatert:** 2026-04-27

> ⚠️ **IKKE NESTE STEG.** Dette er endgame-visjonen og ligger godt
> frem i tid. Brukeren har eksplisitt signalisert at vi først må
> komme oss gjennom mer grunnleggende arbeid (root-cleanup, pilot
> 24+ av src-migrasjonen, gjenstående Analyse-/Saldobalanse-/
> Reskontro-polish, eksisterende plan-doc'er som
> [analyse_pivot_plan.md](analyse_pivot_plan.md)) før vi i det
> hele tatt begynner på Nivå 2 her. Denne planen er dokumentert
> SÅ visjonen ligger trygt for fremtiden, ikke som en kø-jobb.
> Selv Nivå 1 (PDF-visning, ferdig 2026-04-27) ble laget som en
> bivirkning av en bilag-popup-forbedring, ikke som første steg
> mot endgame.

Brukerens langsiktige ambisjon for Utvalg: bygge et revisjonsverktøy
hvor en AI-agent har **sylskarp kontekstforståelse** av både den
strukturerte regnskapsdataen, de underliggende bilag-dokumentene og
selve revisjonsmetodikken — slik at agenten kan svare på faglige
spørsmål, peke på avvik, foreslå handlinger og dokumentere arbeidet
på et nivå som ingen generell LLM (eller tradisjonelt regnskapsverktøy)
kan matche.

Dette dokumentet beskriver visjonen i lag, og holder tråden over tid
slik at vi vet hva vi bygger mot.

## 1. Hvorfor dette er en unik posisjon

Få (om noen) norske revisjonsverktøy kombinerer alle disse tre i ett
system:

1. **Strukturert regnskapsdata med revisorens semantikk**
   - Konto → regnskapslinje-mapping (RL)
   - Saldobalanse-pivot, kontoserier, perioder, retning
   - SAF-T med master-tabeller (TaxTable, kunder, leverandører)
   - A07-mapping (lønnsavstemming)
   - Reskontro-berikelse (kunde/leverandør per bilag)
   - Konsolidering og konsernoppsett

2. **Dokumenter knyttet direkte til transaksjonsraden**
   - Bilag-PDF fra Tripletex / PowerOffice GO (Nivå 1 — implementert)
   - Foreløpig: åpnes i ekstern viewer
   - På sikt: ekstrahert tekst + felter inn i appens database

3. **Revisjonsmetodikk som kjørbar kontekst**
   - Handlinger (revisjonshandlinger) med risiko og evidens
   - Scoping og vesentlighet
   - Workpaper-systemet
   - Dokumentkontroll med RF-1022 og lønnsavstemming
   - Klient-/team-info via Visena

**Konsekvens:** Når en LLM får tilgang til alle tre lag samtidig —
ikke bare PDF-en, ikke bare hovedboken, ikke bare en isolert handling —
kan den resonnere som en revisor: "Beløpet på 84 062 kr på konto 4500
matcher fakturaen, MVA-koden 25% gir 16 812 i inngående MVA, leverandøren
er ny denne perioden — verdt en stikkprøve under handling RH-12."

Det er den kombinasjonen som er moaten. Ikke modellen, ikke OCR-en,
ikke regnskapsdataen alene. **Alt sammen, med revisjonskonteksten på
toppen.**

## 2. Nivå-inndeling

Hvert nivå bygger på det forrige. Hvert nivå gir egen verdi (kan stå
alene), så vi kan stoppe på et hvilket som helst nivå hvis ressurs/
risiko/marked tilsier det.

### Nivå 1 — Bilag-PDF i appen ✓ (implementert 2026-04-27)

**Hva:** "📎 Se bilag"-knapp i bilag-popupen åpner PDF-en for
transaksjonen i systemets PDF-viewer. Bruker eksisterende
voucher-arkiv-infra (Tripletex-PDF / PowerOffice GO-ZIP).

**Verdi:** Revisor får direkte sammenheng mellom hovedboks-rad og
underbilag uten å forlate appen. Tar første friksjon vekk.

**Status:** Ferdig (commit `b282ca6`).

### Nivå 2 — OCR / dokument-forståelse (~1-2 uker)

**Hva:** Trekk ut strukturerte felter fra hver bilag-PDF og lagre dem
ved siden av transaksjonsraden:
- Leverandør (navn, orgnr)
- Fakturanummer
- Fakturadato + forfallsdato
- Brutto-/netto-beløp + MVA
- KID
- Varelinjer (beskrivelse, antall, enhetspris, sum, MVA-kode)
- IBAN/kontonummer

**Tekniske valg:**
- **Lokal vs. sky:** Tesseract for ren OCR er gratis men svakt på
  fakturalayout. Dedikerte løsninger (AWS Textract, Google Document
  AI, Azure Form Recognizer) er presise men koster penger og krever
  data-eksport. **Vurder en ML-modell trent på norske fakturaer**
  hvis vi har data — kan kjøres lokalt og være konkurransefortrinn.
- **Felt-deteksjon:** Først regelbasert (regex på "Org.nr", "MVA",
  "Sum", "Fakturanr") for kjente layouter (Tripletex har f.eks.
  konsistent header). Så ML-modell for ukjente.
- **Lagring:** Ny tabell/JSON `bilag_extracted` koblet på (klient,
  år, bilag_nr). Versionert per OCR-kjøring.

**Verdi alene (uten LLM):**
- "Vis meg alle bilag fra leverandør X" — strukturert søk
- "Sammenlign fakturadato vs. bokføringsdato" — periodiserings-test
- Avvikssjekk: hovedbok-beløp vs. faktura-sum
- Eksporter til Excel som flat tabell

### Nivå 3 — LLM-grounding med revisjonskontekst (~2-3 uker)

**Hva:** Ein "Spør om bilag/transaksjon"-funksjon som sender en spørring
til en LLM, men hvor *konteksten* er nøye sammenstilt:

```
[KLIENT-KONTEKST]
- Klient: Spor Arkitekter AS, Org.nr 976588614
- År: 2025
- Bransje: Arkitekttjenester
- Vesentlighet: 250 000 kr (planlegging)

[REGNSKAPS-KONTEKST]
- Konto 4500 (Refunderbare tjenester)
- Regnskapslinje: 70 (Varekostnad)
- Hittil i år: 8 297 987 kr (12 bilag, snitt 691 499)
- Året før samme periode: 1 240 000 kr (3 bilag) — VIKTIG ENDRING

[BILAG-KONTEKST]
- Bilag 212-2025, dato 2025-05-30
- Sum: 84 062,50 kr (debet 4500)
- Motpost: 2400 Leverandørgjeld (-105 078,13), 2710 Inng. MVA (21 015,63)
- MVA-kode 1 (25%) — sjekk: 84 062 * 0,25 = 21 015,5 ✓

[BILAG-DOKUMENT (utdrag fra OCR)]
- Leverandør: BRAGE ARKITEKTER AS (Org.nr 210720)
- Fakturanr: 1012, dato 2025-05-30
- Beskrivelse: "Konsulenttjenester Q2 2025"
- Prosjekt: 165 Institutt Detaljprosjektering

[GJELDENDE REVISJONSHANDLING]
- RH-12: Test av varekostnader > vesentlighet
- Risiko: Periodisering, fullstendighet
- Tidligere konklusjoner på samme leverandør: ingen avvik

[BRUKERENS SPØRSMÅL]
"Er det noe spesielt jeg bør se på her?"
```

LLM får da resonneringsgrunnlag som er **uoverkommelig** for
generelle assistenter. Den kan svare:

> Tre observasjoner verdt å notere:
> 1. Konto 4500 har tredoblet seg vs. fjoråret samme periode — skyldes
>    nye prosjekter? Verifiser ramme-avtale.
> 2. Leverandøren BRAGE ARKITEKTER har samme adresse som klient —
>    nærstående-vurdering? Sjekk aksjonærregister.
> 3. MVA-grunnlaget stemmer perfekt (84 062 × 25% = 21 015 ≈ bokført
>    21 015,63). Avvik på 0,13 kr er avrundings-støy.
>
> Foreslår at handling RH-12 oppdateres med stikkprøve på
> ramme-avtalen, og at handling RH-08 (nærstående-test) vurderes
> aktivert for denne leverandøren.

**Tekniske valg:**
- **Modellvalg:** Claude Sonnet/Opus eller GPT-4-class for tunge
  resonnementer. Kan supplere med lokal Llama/Mistral for billige
  rutinemessige sjekker.
- **Privacy:** Klient-data MÅ behandles confidentielt. Vurder:
  - Anthropic / OpenAI med no-training-clause + EU-hosting
  - Lokal modell (Ollama, LM Studio) for sensitive klienter
  - Hybridoppsett: lokal screening + sky-LLM for komplekse spørsmål
- **Prompt-engineering:** Konteksten over er det kritiske. Bygg en
  `build_audit_context(client, year, bilag_nr, action_id?)` som
  samler all relevant info i et standardisert format.
- **Sitater og sporbarhet:** LLM-svar må alltid kunne spores tilbake
  til kilde (hvilken konto, hvilken handling, hvilken faktura-linje).
  Dette er revisjonsdokumentasjon — ikke bare et chat-svar.

### Nivå 4 — Agent-modus (~1-2 måneder)

**Hva:** LLM får ikke bare *kontekst*, men *verktøy* — den kan handle
i Utvalg på vegne av revisor:

- "Kjør motpost-analyse på konto 4500 for hele året" → kaller
  `motpost_analysis(konto=4500)` og returnerer resultatet
- "Marker alle bilag fra leverandør X som granska" → setter status
  på utvalg
- "Foreslå nye handlinger basert på årets MVA-bilde" → leser scoping,
  RL-pivot, sammenlignet med fjorår, foreslår RH-handlinger
- "Eksporter konklusjon til arbeidspapir" → bygger workpaper-doc

Tekniske valg:
- **Tool-calling-API** — Claude og GPT støtter dette nativt
- **Verktøyhierarki:** Lavnivå (les data) → middels (kjør analyse) →
  høyt (skriv konklusjon, lag handling). Sistnevnte krever
  brukergodkjenning per kall.
- **Audit-trail:** Alle agent-aksjoner må logges med tidsstempel,
  klient, bruker, kontekst-snapshot. Revisor må kunne svare for
  ALT agenten har gjort i revisjonsdokumentasjonen.
- **Sandboxing:** Agenten må aldri kunne sende e-post, slette filer,
  endre klient-stamdata uten eksplisitt godkjenning.

## 3. Avhengigheter på tvers av nivåer

| Avhengighet | Nivå 1 | Nivå 2 | Nivå 3 | Nivå 4 |
|---|---|---|---|---|
| Voucher-arkiv-infra | ✓ kreves | ✓ kreves | ✓ kreves | ✓ kreves |
| OCR/extraction | – | ✓ kreves | sterkt anbefalt | ✓ kreves |
| Klient-/år-mapping | ✓ | ✓ | ✓ | ✓ |
| RL-/SAF-T-/A07-pipelines | – | nyttig | ✓ kreves | ✓ kreves |
| Handlinger med risiko-felt | – | – | ✓ kreves | ✓ kreves |
| Versjonert kunnskapsgrunnlag (NRS, ISA) | – | – | sterkt anbefalt | ✓ kreves |
| Tool-calling-rammeverk | – | – | – | ✓ kreves |
| Audit-trail / sporbarhet | – | – | nyttig | ✓ kreves |

## 4. Strategiske beslutninger som må tas

Disse trenger ikke være avklart før vi begynner, men bør ikke utsettes
til langt ut i implementeringen:

### 4.1 Privacy / data-håndtering

- Skal klient-data noensinne gå utenfor Norge/EØS?
- Tilstrekkelig at LLM-leverandør har no-training-clause + EU-hosting?
- Eller må sensitive klienter (banker, offentlig sektor, helse) kjøres
  100% lokalt med åpne modeller?
- **Mulig sluttkonfigurasjon:** "AI-modus" per klient i Admin —
  bruker velger nivå (av/lokal/EU-sky) ved klient-oppsett.

### 4.2 Modellvalg

- Hvilken LLM? Claude Sonnet 4.5 / Opus 4.7 / GPT-4-class / lokal
  Llama 3.1 70B?
- Hvor mye er vi villige til å betale per spørring? (Tunge resonnement
  kan koste 10-50 øre per kall — overkommelig hvis det erstatter
  timer av manuelt arbeid)
- Norsk vs. engelsk: nyere modeller er gode på norsk, men spesialiserte
  norske modeller (NorBERT, NorLLM) kan være verdt en pilot.

### 4.3 Forretningsmodell og posisjonering

- Lisensmodell — per bruker / per klient / per AI-spørring?
- Hvilke konkurrenter posisjonerer seg mot dette? (Visma Audit, BDO
  digital, Maestro, m.fl. — sjekk hva de annonserer for 2026/2027)
- Pilot-kunder — hvilke revisjonsselskaper er villige til å være
  første brukere?

### 4.4 Compliance og ansvar

- Hvem har ansvar når AI-en foreslår en konklusjon som er feil?
  → Revisor, alltid. AI-en er et verktøy. Men loggen må vise det.
- ISA 220 / kvalitetskontroll: AI-bruk må dokumenteres.
- DNR / Finanstilsynet: følg med på guidance om AI i revisjonsarbeid.

## 5. Foreslått sekvens hvis vi går videre

1. **Nivå 2-pilot på én klient** (~2 uker)
   - Velg en klient med 100-300 bilag
   - Test 2-3 OCR-løsninger (Tesseract, AWS Textract, lokal modell)
   - Mål: ekstraher leverandør, beløp, dato, MVA på 95%+ av bilagene
   - Lager: `bilag_extracted_v1`-tabell

2. **Nivå 3 minimal-MVP** (~2 uker)
   - "Spør om denne transaksjonen"-knapp i bilag-popup
   - Bygger kontekst-pakke som beskrevet over
   - Kall til Claude API med no-training-clause
   - Vis svar i samme popup, lagre som notat på bilaget

3. **Demo til 1-2 betrodde kolleger / revisjons-venner**
   - Verdivurdering: er dette noe markedet vil ha?
   - Hvilke spørsmål stiller de spontant?
   - Justere kontekst-bygger basert på faktiske bruksmønstre

4. **Avgjør Nivå 4 basert på respons**
   - Hvis Nivå 3 er kraftig nok: stopp og polish
   - Hvis brukerne sier "nå må AI-en gjøre det": bygg agent-modus

## 6. Hva vi IKKE bygger

For å unngå scope-explosjon:

- **Generell chatbot** — Utvalgs AI svarer kun på revisjonsfaglige
  spørsmål med strukturert kontekst
- **Automatisk konklusjon uten brukergodkjenning** — agenten foreslår,
  revisor signerer
- **Konkurrere med Excel** — pivot/eksport til Excel forblir det
  primære for ad-hoc analyse (jf. [analyse_pivot_plan.md](analyse_pivot_plan.md))
- **Erstatte fagpersonen** — verktøyet skal *forsterke* revisor, ikke
  ta over
- **Skybasert tjenestested** — appen forblir desktop med lokal
  databehandling. AI-kallene skjer over API, men datalagring forblir
  hos klienten

## 7. Hva som er sant i dag (2026-04-27)

- ✓ Bilag-PDF kan vises (Nivå 1 implementert i dag)
- ✓ Voucher-indeksering for Tripletex-PDF og PowerOffice GO-ZIP
- ✓ SAF-T-parser med master-TaxTable og berikelse av MVA-felter
- ✓ RL-mapping per konto med override-støtte
- ✓ Handlinger-fanen med risiko/evidens-felt
- ✓ Scoping og vesentlighet
- ✓ Konsolidering og konsern
- ✓ A07-lønnsavstemming
- ✓ Reskontro-berikelse av kunde/leverandør per bilag
- – OCR: ikke bygd
- – LLM-integrasjon: ikke bygd
- – Tool-calling-rammeverk: ikke bygd

## 8. Relaterte plan-dokumenter

- [analyse_pivot_plan.md](analyse_pivot_plan.md) — pivot/Excel-eksport
  (komplementær: dekker ad-hoc-analyse av strukturerte data)
- [analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md) —
  kolonneoppsett i Analyse-fanen
- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  hvor AI-/agent-koden bør ligge når den kommer (sannsynligvis
  `src/ai_assistant/` eller `src/audit_actions/ai_agent/`)
