# Revidert programplan for Utvalg

Dette dokumentet er master-roadmapen for videre arbeid i `Utvalg-1`.

## Styrende valg

- Stabiliser foerst.
- A07 skal stabiliseres, forenkles og poleres, ikke redesignes fra bunnen.
- MVA skal fullfoeres og hardes i eksisterende Analyse-flyt.
- Claude Code brukes i hybrid rolle: UX/spec-eier og implementoer i eksisterende komplekse moduler.
- Explorers brukes on-demand, ikke som faste staaende roller.
- Fase 0 gaar parallelt med boelge 1 og skal ikke bli en papirblokkering.
- Reskontro v1 bygges som en samlet motpartsmodul paa eksisterende hovedboksdata.
- Konsolidering MVP avgrenses hardt til TB-import, felles mapping, manuell elimineringsjournal, reproducerbar run og Excel-eksport.
- `TB-only` er en foersteklasses arbeidsmodus: det skal vaere mulig aa jobbe videre med kun saldobalanse der full hovedbok eller SAF-T ikke finnes.

## Operative regler
- Claude review-godkjenner alle PR-er eller kodeendringer fra `worker_a07_support` og `worker_mva_finish` foer merge.
- Endringer i eksisterende A07-, Analyse- og MVA-moduler prioriteres til Claude eller en hovedimplementoer med helhetlig kontekst, ikke til isolerte workers uten review.
- Workers brukes mest paa nye pakker, rene hjelpepakker, eksport, storage og godt avgrensede write-sets.

## Boelge 0 og 1: grunnmur + stabilisering

### Rekkefolge inne i boelge 1
1. Cross-feature interaction grammar
2. Mapping/fjoraar-strategi
3. A07 polish
4. MVA completion
5. Analyse polish
6. GUI-regresjonsmatrise og manuelle smoketester

### Grunnmur som laases tidlig
- Ett felles arbeidsflatemoenster for store features: venstre liste, hoyre liste, detaljpanel, drag/drop, inline status, minst mulig popup.
- Lagringskontrakter under klient/aar via `client_store`.
- Ett felles datainntaksprinsipp:
  - full dataset = hovedbok/transaksjoner + saldobalanse
  - TB-only = kun saldobalanse
  - features skal eksplisitt vise hva som virker og hva som ikke virker i TB-only-modus
- Eksplisitt strategi for mapping mellom aar:
  - aarets manuelle mapping er alltid fasit
  - fjoraar er forslag/prior, ikke automatisk sannhet
  - fortegnsskifte eller materiell mismatch gir reviewstatus
  - `lock_prior_year_mapping` er av som standard
- GUI-regresjonsmatrise for Analyse, A07 og MVA.
- Enkle performanceregler: unngaa full refresh av store visninger uten grunn, og lazy-load detaljer der det er naturlig.

### A07
- Stabiliser dagens arbeidsflate som pilotflate.
- Gjør normalarbeid mulig i én hovedflyt med mindre popupbruk.
- Fullfør robust drag/drop, direkte mapping, Tryllestav, eksport og gjenåpning.
- Flytt avansert mapping og admin til sekundære verktøy.
- Kjør ekte GUI-smoketest på reelle klientdata fra last A07 til eksport.

### MVA
- Fullfør eksisterende MVA-flyt i Analyse.
- Hard fokus på:
  - MVA-pivot
  - MVA-oppsett
  - import av kontoutskrift
  - avstemming mot Skatteetaten
  - tydelig status og eksport
- Prioriter ende-til-ende verifikasjon framfor ny funksjonsutvidelse.

### Analyse/regnskap
- Fullfør:
  - skjul nulllinjer som tydelig brukerinnstilling
  - SAF-T-opprydding av nullkontoer i saldobalansevisning
  - drill fra saldobalansekonto til transaksjoner
  - bedre synlighet for kommentarer
  - bedre synlighet for tilleggsposteringer
  - mer konsekvent bruk av motpost-visning
- Sørg for at Analyse kan brukes meningsfullt i TB-only-modus, med tydelig nedtoning eller skjuling av funksjoner som krever transaksjoner.
- Analyse er referansen for felles interaction grammar.

### Gate 1
- A07 kan brukes ende-til-ende av pilotbruker.
- MVA kan brukes ende-til-ende av pilotbruker.
- Analyse baerer hovedarbeidsflyt uten popup-avhengighet.
- Fjoraars-/alternativ-mapping er implementert og testet.

## Boelge 2: konsolidering MVP

### Scope som er med
- Ett klient/aar-forankret konsolideringsprosjekt.
- Import av TB per selskap fra Excel/CSV og SAF-T.
- Normalisering til felles TB-format.
- Full hovedbok eller SAF-T er ikke et krav for konsolidering MVP; TB-only maa vaere nok til aa komme gjennom arbeidsflyten.
- Felles mapping til konsernlinjer med gjenbruk av eksisterende regnskapsmapping.
- Manuell elimineringsjournal med batch-balansekrav.
- Deterministisk konsolideringsrun.
- Analyse-lignende arbeidsflate.
- Excel-eksport av arbeidsbok.

### Scope som ikke er med
- Minoritetsinteresser.
- PPA/goodwill/oppkjoepsanalyse.
- Egenkapitalmetoden.
- Multi-level konsern.
- Avansert valuta/CTA.
- Smart auto-eliminering.
- PDF/noter/aarsregnskapsgenerator.
- BRREG/kredittscore/CRM/dokumentreader.

### Teknisk retning
- Gjenbruk TB-lesere, regnskapsmapping, eksportmotor og `client_store`.
- Innfør egen `consolidation/`-pakke og egen side i appskallet.
- Lagring laases til klient/aar under `consolidation/` med prosjekt, selskaper, mapping, elimineringer, runs og eksportreferanser.

### Gate 2
- Minst to selskaper kan importeres, mappes, elimineres, kjoeres og eksporteres i ett klient/aar-prosjekt, og state kan aapnes igjen uten tap.

## Boelge 3: reskontro v1 + separat API-discovery

### Reskontro v1
- Én samlet `Reskontro`-modul med modus `Kunder` og `Leverandorer`.
- Bygges paa eksisterende aktivt datasett, ikke ny importpipeline.
- V1 er en motpartsoversikt fra hovedbokstransaksjoner, ikke full aapen-post-reskontro.
- Arbeidsflate:
  - venstre: motpartsoversikt
  - hoyre: transaksjoner for valgt motpart
  - topp: modus, konto-/periodefilter, tekstfilter, `kun saldo != 0`, `kun uten id`
- V1-risikosignaler:
  - mangler id
  - mangler navn
  - saldo uten nylig aktivitet
  - mange transaksjoner
  - saldo med feil fortegn i valgt modus
- Drilldown til bilag gjenbruker eksisterende drillmoenstre.

### Ut av scope i v1
- Full aging 0-30 / 31-60 / 61-90.
- Orgnr som launchkrav.
- BRREG-/MVA-/konkursintegrasjon som del av v1.
- Kredittscore, eierskap og regnskapstall.

### API-discovery som eget spor
- Etter reskontro v1 kjoeres et separat discovery-/adapterspor for:
  - Brreg enhetsdata
  - MVA-registerstatus
  - konkurs/avvikling
  - senere betalte kilder
- Foer dette ma vi laase hvordan `orgnr` skal lagres eller berikes lokalt.

### Gate 3
- Reskontro kan brukes paa én klient med kunde-/leverandoermodus, drill til transaksjoner og tydelige lokale risikosignaler.

## Boelge 4: rapportering, arbeidspapirer og styringslag
- Samle Excel-utdata, PDF-rapporter, noekkeltall og regnskapsoppstillinger i ett felles rapport-/workpaper-lag.
- Knytt output fra Analyse, A07, MVA, reskontro og konsolidering til samme revisjonskontekst.
- Bygg grunnlaget for risikooversikt og kobling mellom analyser, handlinger og arbeidspapirer.

## Boelge 5: senere R&D
- dokumentmatching
- dokumentreader
- skatteberegning og midlertidige forskjeller
- presentasjon/PPT
- CRM/datavarehus-spor
