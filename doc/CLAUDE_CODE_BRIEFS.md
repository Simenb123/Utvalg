# Claude Code Briefs

Claude Code brukes i hybrid rolle i dette programmet: UX/spec-eier og implementoer i eksisterende komplekse moduler.

## Arbeidsrekkefolge for boelge 1
1. Cross-feature interaction grammar
2. Mapping/fjoraar-strategi
3. A07 polish
4. Analyse/MVA completion
5. Analyse polish
6. GUI-regresjonsmatrise

## Tverrgaaende krav

- `TB-only` skal vaere en foersteklasses arbeidsmodus i relevante features.
- GUI-et skal tydelig vise hva som er tilgjengelig naar brukeren bare har saldobalanse, og hva som krever full hovedbok eller SAF-T.
- Manglende transaksjonsgrunnlag skal ikke oppleves som feil hvis arbeidsflyten faktisk kan fullfoeres med TB-only.

## 1. Cross-feature Interaction Grammar

Lag en felles interaction spec for:
- drag/drop
- detaljpanel
- inline varsler
- info-ikoner
- fargekoder
- vis/skjul detaljer
- tastaturregler
- popup-minimering

Denne skal gjelde Analyse, A07, konsolidering og reskontro.

## 2. Mapping/Fjoraar Strategy Brief

Implementer og dokumenter denne laaste strategien:
- aarets manuelle mapping er alltid fasit
- fjoraar brukes som forslag/prior
- fortegnsskifte eller materiell mismatch gir reviewstatus
- `lock_prior_year_mapping` er av som standard

Dette vil kreve samspill mellom GUI, overrides/storage og regnskapsvisningene.

## 3. A07 Polish Brief

Maal:
- Ikke redesign A07 fra bunnen.
- Gjoer eksisterende A07-arbeidsflate pilotklar.
- Gjoer normalarbeid mulig i én hovedflyt med mindre popupbruk.
- Behold eksisterende kjerne, men poler arbeidsflate, mapping, historikk, forslag og drag/drop.

Lever:
- skjermstruktur for hovedflyt
- primaarhandlinger
- tomtilstander
- tastatur/mus-regler
- navngivning av knapper/felt
- popup-regler for hva som er admin/noedverktoey
- akseptkriterier for pilot

## 4. Analyse/MVA Completion Brief

Maal:
- Fullfoer dagens Analyse/MVA-flyt end-to-end.
- Ikke bygg ny modul.
- Gjoer dagens MVA-pivot, oppsett, kontoutskriftimport og avstemming til en ferdig arbeidsflyt.
- Definer hvordan Analyse og MVA skal oppfoere seg i TB-only-modus.

Lever:
- tydelig brukerflyt
- hvilke innganger som skal vaere synlige i Analyse
- hvordan status og feil skal vises uten stoey
- UX for import, oppsett, avstemming og eksport
- hvilke deler som er tilgjengelige i TB-only-modus og hvilke som krever transaksjoner
- akseptkriterier for GUI-smoketest

## 5. Analyse Polish Brief

Maal:
- Fullfoer nulllinje-skjuling, SAF-T-opprydding, drill fra SB-konto til transaksjoner og bedre synlighet for kommentarer, tilleggsposteringer og motpost.
- Behold Analyse som referanse for interaction grammar.

## 6. Consolidation Workspace Brief

Maal:
- Lag Analyse-lignende arbeidsflate for hardt avgrenset konsolidering MVP.

MVP-scope:
- velg klient/aar
- importer TB per selskap
- map til konsernlinjer
- review-koe
- manuell elimineringsjournal
- kjoer konsolidering
- eksporter arbeidsbok
- full hovedbok eller SAF-T skal ikke vaere krav for aa fullfoere MVP-flyten

Lever:
- informasjonshierarki
- skjermsoner
- inline review-koe
- journalflyt
- hvordan status og mangler skal forstaas i GUI
- hva som eksplisitt IKKE er med i MVP

## 7. Reskontro Workspace Brief

Maal:
- Lag én samlet kunde-/leverandoermodul som motpartsoversikt fra hovedbokstransaksjoner.

V1-scope:
- venstre motpartsoversikt
- hoyre transaksjoner for valgt motpart
- modus for Kunder / Leverandorer
- konto-/periodefilter, tekstfilter, `kun saldo != 0`, `kun uten id`
- lokale risikosignaler
- drill til bilag

Merk:
- Reskontro v1 bygger paa transaksjonsgrunnlag og er derfor ikke en TB-only-feature.
- Briefen skal beskrive hvordan GUI-et forklarer dette tydelig uten at brukeren opplever modulen som “brutt”.

Lever:
- listevisning
- drilldown
- filtermodell
- risiko- og statusmarkeringer
- hvilke felt som ma vaere synlige i v1
- hva som er ut av scope i v1
