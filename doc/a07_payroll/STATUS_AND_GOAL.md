# A07: Status, Mal Og Overtakelse

Dette er hoveddokumentet for A07-sporet. Les denne filen for aa forstaa hva
A07 i Utvalg er, hva som nylig er gjort, hvordan systemet er tenkt brukt, og
hva som bor bygges videre.

Sist oppdatert: 2026-04-23.

## Kortversjon

A07 skal hjelpe revisor med aa avstemme og koble A07/A-melding-data mot
saldobalanse, A07-koder og RF-1022. Malet er trygg revisjonsstotte: motoren
skal koble automatisk naar den har klar fasit, og ellers vise sporbare forslag.

Arbeidsretningen er:

- A07-koder er canonical matchingnivaa.
- RF-1022 er aggregert kontroll- og visningsnivaa.
- Automatikk skal feile lukket, men trygge 100-prosent-treff skal ikke vente
  paa manuell godkjenning.
- Eksisterende daarlige koblinger skal flagges og gjores enkle aa rydde, ikke
  slettes automatisk.
- Nye A07-aliaser og ekskluderinger skal inn i A07-regelbok, ikke i legacy
  konseptaliaser.
- AGA-plikt skal vises fra A07-kilden der den finnes, med A07-regelbok som
  fallback naar kildefilen ikke har feltet.

## Hva Vi Har Jobbet Med

Vi har flyttet A07 fra en stor og urolig flate mot en mer kontrollert
revisjonsarbeidsflyt:

- Flyttet A07 inn i Utvalg som `a07_feature`.
- Etablert modulstruktur for `payroll`, `control` og `ui`.
- Beholdt `page_a07.A07Page` og compat-shims for gamle imports.
- Forenklet A07-hovedflaten slik at nederste omraade fokuserer paa `Forslag`
  og `Koblinger`.
- Flyttet kontrolloppstilling, historikk og umappet arbeid ut av hovedflaten der
  de ikke skal dominere brukerflyten.
- Stabiliserte RF-1022-radvalg slik at radvalg ikke skal flytte support-tab,
  GL-markering eller forslagmarkering uten eksplisitt brukerhandling.
- Innfoerte RF-1022-bro som avleder RF-post fra A07-koder og feiler til
  `uavklart_rf1022` naar koden ikke er kjent.
- Lagt inn RF-1022-, A07- og `Kol`-visning i GL-/saldobalanselisten.
- Samlet basisforstaaelse: resultatkontoer bruker normalt `UB`, balanse- og
  periodiseringsposter bruker normalt `Endring`, og special_add kan overstyre.
- Strammet automatisk matching slik at global auto bare bruker strenge, trygge
  kandidater.
- Bygget runtime-audit for eksisterende koblinger med status som `Feil`,
  `Mistenkelig`, `Uavklart` og `Trygg`.
- Fikset kataloglasting, stale RF-kandidat-cache og trygg fjerning av mappinger.
- Lagt til hoyreklikklaering i `Koblinger`: legg kontonavn til A07-alias,
  ekskluder kontonavn fra A07-kode, eller fjern mapping og ekskluder navnet.
- Oppdatert saldobalanse-laering slik at A07-alias og A07-boost skrives til
  A07-regelbok.
- Fjernet A07 sin avhengighet til legacy konseptaliaser og samlet A07-aliaslogikk
  i `global_full_a07_rulebook.json`.
- Ryddet Admin > A07-regler til fanene `Grunnregel`, `Aliaser`, `Kontoer` og
  `Avansert`, med eksplisitt `Lagre`, `Forkast endringer` og dirty-status.
- Flyttet RF-1022-kobling inn paa A07-reglene som `rf1022_group`, slik at egen
  RF-1022-aliasmatching ikke lenger er hovedarbeidsflate for A07.
- Ryddet katalogadmin til `Flagg og grupper`; kontrollflagg er fjernet fra
  synlig adminflyt, mens payroll-flagg og legacy analysegrupper er beholdt som
  egne katalogtyper.
- Ryddet Admin > Kontoklassifisering slik at detaljklasser ligner mer paa
  A07-regelbildet og brukes til regnskapsmessig kontoklassifisering, ikke som
  A07-kildesannhet.
- Endret A07-fanen i retning A07-kode som primar arbeidsflate. RF-1022 er
  fortsatt kontrolloppsummering, men A07-koden er koblingsnivaaet.
- Lagt inn smart gruppe-/solverarbeid for typiske lonnsgrupper som
  `trekkILoennForFerie`, `fastloenn`, `timeloenn`, `overtidsgodtgjoerelse` og
  `fastTillegg`.
- Lagt inn kontoseriefilter og enklere mappingfilter i A07-fanen, og begynt aa
  fjerne rullgardiner som dupliserer informasjonen i nederste koblingsliste.
- Lagt inn AGA-pliktig som valgfritt felt i A07-regelbok, parser og A07-visning.

## Dagens Status

Teknisk status:

- A07-regelbok er canonical sted for A07-matchingregler.
- `global_full_a07_rulebook.json` er eneste aktive A07-kildesannhet for
  matcher-runtime.
- RF-1022-gruppe ligger paa A07-regelen, ikke som separat A07-aliaskilde.
- RF-1022-/katalogaliaser kan fortsatt finnes i klassifiseringskatalogen, men
  de skal ikke overstyre A07-regelbok for A07-matching.
- Mappingformatet er uendret: lagret mapping representerer konto -> A07-kode.
- `mapping_audit_df` og `AliasStatus` er runtime-kontrollinformasjon, ikke nytt
  lagringsformat.
- `special_add` brukes til periodiserings-/balanseposter, for eksempel
  skyldig feriepenger og avsatt styrehonorar. Dette skal vaere regelstyrt og
  ikke hardkodet til ett konkret kontonummer.
- A07-parseren kan hente `AgaPliktig` fra kilde-JSON naar feltet finnes. Hvis
  kilden mangler feltet, kan A07-regelbok fylle visningen.
- A07 workspace/path er strammet inn slik at klient/aar faar namespaced
  fallback og ikke faller tilbake til delt global A07-state.

Produktstatus:

- Brukeren skal kunne starte i A07-kodevisningen og se hvilke A07-koder som er
  ferdige, aapne eller mistenkelige.
- RF-1022 skal brukes som kontrolloppsummering og regnskapsmessig bro, ikke som
  primar aliasmatchingflate.
- `Forslag` viser kandidater.
- `Forslag` skal vise kontoer, A07-belop, GL-forslag, diff, status og hvorfor.
- `Koblinger` viser eksisterende koblinger, auditstatus og belop.
- Global auto skal koere av seg selv for klare fasitsaker naar A07 oppdateres.
- Feil eller mistenkelige koblinger ryddes manuelt via hoyreklikk/Delete.
- Hoyreklikk paa GL, A07-linje, forslag og koblinger skal gi samme mentale
  modell: tildel, fjern, laer alias, ekskluder alias eller gaa til admin.
- A07-koder med diff null skal markeres gronne; aapne/mistenkelige koder skal
  ikke se ferdige ut.

Sist verifiserte kommandoer:

```powershell
py -3 -m json.tool config\classification\global_full_a07_rulebook.json
py -3 -m compileall -q page_admin_rulebook.py page_admin_helpers.py a07_feature tests
py -3 -m pytest tests\test_a07_feature_parser.py tests\test_page_admin.py tests\test_page_a07.py --no-cov -q
py -3 -m pytest tests\test_a07_feature_suggest.py tests\test_a07_control_matching.py tests\test_a07_suggest_usage.py tests\test_page_saldobalanse.py --no-cov -q
```

## Nye Beslutninger

Dette er beslutningene som styrer videre arbeid:

- Vi beholder A07-grupper. De er nyttige for lonnsarter som ofte avstemmes som
  pakker, men gruppene skal ikke skjule svak evidens paa enkeltkontoer.
- `aga` og `forskuddstrekk` skal ikke ligge som A07-koder for
  arbeidsgiveravgiftsgrunnlaget. De er kontrollverdier og regnskapsmessige
  kontoklasser.
- RF-1022-aliasmatching skal ikke bygges videre som egen A07-fasade. A07-regel
  -> RF-1022-gruppe er tydeligere og gir en kilde til sannhet.
- Kontrollflagg er fjernet fra praktisk GUI-flyt. Payroll-flagg og legacy
  analysegrupper kan beholdes inntil vi har verifisert om de fortsatt gir verdi.
- A07-laering skal skrive til A07-regelbok og deretter invalidere forslag/cache
  umiddelbart, slik at ny aliasregel blir synlig etter oppdatering og ikke foerst
  etter tilfeldig senere refresh.
- Automatching skal kunne koere ved A07-oppdatering for klare fasitsaker, ikke
  bare etter at bruker trykker seg gjennom hver A07-kode.

## Regelmodell

A07-regelbok:

- Fil: `config/classification/global_full_a07_rulebook.json`
- Brukes til A07 `keywords`, `exclude_keywords`, `allowed_ranges`,
  `boost_accounts`, `basis`, `expected_sign`, `rf1022_group`, `aga_pliktig` og
  `special_add`.
- Nye A07-laeringer fra A07-fanen og saldobalanse skal skrives hit.
- Admin viser `special_add` som periodiserings-/balansekontoer, ikke som raatekst.
- `aga_pliktig` er valgfritt. Ukjent er lovlig og skal ikke gjette.

Tidligere konseptaliaser:

- Er faset ut av A07-runtime og fjernet som egen JSON-kilde.
- Skal ikke brukes som A07-kildesannhet.
- Admin-fanen er skjult slik at A07-regler er eneste synlige A07-regelflate.

RF-1022:

- RF-1022 er aggregert kontrollnivaa.
- RF-1022 bygges fra A07-koder via RF-1022-broen.
- A07-regelens `rf1022_group` er den foretrukne mappingen fra A07-kode til
  RF-1022.
- Ukjente A07-koder skal ende som `uavklart_rf1022`, ikke falle tilbake til
  loenn.
- RF-1022-aliaser horer hjemme i RF-/klassifiseringskatalogen.

Kontoklassifisering:

- Kontoklassifisering er regnskapsmessig detaljklassifisering av kontoer.
- Den kan brukes til kontroll og forklaring, men skal ikke bli en parallell
  A07-aliaskilde.
- Eksempel: skyldig feriepenger, skyldig AGA og forskuddstrekk er relevante
  kontoklasser selv om de ikke skal vaere A07-koder i grunnlagsmatchingen.

## Matchingregler Vi Beskytter

- Belop alene er ikke nok for trygg automatisk mapping.
- Historikk alene er ikke nok for nye trygge forslag.
- RF-1022-kandidater maa ha riktig gruppe, alias/katalogstotte og egen
  belopsstotte.
- Balanse-/periodiseringsposter skal kunne matches via regelstyrt
  `special_add`, og helst via kontoomraade + alias, ikke hardkodet enkeltkonto.
- Feriepenger skal kunne inkludere kostnadsforte feriepenger og relevant
  balanse-/periodiseringsendring naar belop og regel peker samme vei.
- Avsatt styrehonorar skal kunne behandles paa samme maate som feriepenger:
  alias + relevant 2xxx/periodiseringsomraade + belopsmatch.
- `6701 Honorar revisjon` skal ikke ende i loenn/`annet` via belop alene.
- `5890 Annen refusjon` skal ikke vaere trygg refusjonskandidat uten
  NAV/sykepenger/foreldrepenger eller separat evidens.
- `5800 Refusjon av sykepenger` kan vaere trygg refusjonskandidat naar
  spesifikk stotte finnes.
- Generiske A07-koder som `annet` maa vaere ekstra konservative. Kontoer som
  bodleie, kantine, IT, leie eller andre driftskostnader skal ikke bli trygge
  bare fordi belopet kan forklare differansen.
- A07-koder med AGA-plikt skal synliggjore dette i kontrollflaten, slik at
  bruker kan skille arbeidsgiveravgiftspliktige og ikke-pliktige poster.

## Dagens Arbeidsflyt

1. Last A07.
2. Oppdater mot aktiv saldobalanse.
3. Motoren koerer trygge automatiske A07-koblinger naar evidensen er klar.
4. Bruk A07-kodevisningen som hovedarbeidsflate.
5. Bruk RF-1022/kontrolloppstilling som oppsummering og avvikskontroll.
6. Se usikre kandidater i `Forslag`.
7. Kontroller eksisterende koblinger i `Koblinger`.
8. Rydd feil/mistenkelige koblinger med hoyreklikk eller Delete.
9. Bruk `Laer av kontonavn` naar en feil er aapenbar:
   - legg navn til A07-alias for en riktig kobling
   - ekskluder navn fra A07-kode for en feil kobling
   - fjern mapping og ekskluder navn i samme handling

## Strategisk Retningsvalg: A07-Grupper

Vi beholder A07-grupper fordi de er faglig relevante. Flere A07-koder gir ofte
mening som pakker, spesielt i lonn:

- `trekkILoennForFerie`
- `fastloenn`
- `timeloenn`
- `overtidsgodtgjoerelse`
- `fastTillegg`

Gjeldende beslutning:

- A07-koder forblir canonical mappingnivaa.
- A07-grupper er runtime-/kontrollinformasjon, ikke nytt lagringsformat.
- Solver kan foreslaa eller auto-koble en gruppe naar kombinasjonen gir klar
  belopsfasit og alle kontoene har faglig evidens.
- RF-1022 forblir aggregert kontroll- og visningsnivaa.

Guardrails for A07-grupper:

- En gruppe skal ikke alene gjore en konto trygg.
- En gruppe skal ikke skjule at enkeltkontoer mangler faglig evidens.
- Kombinasjonsforslag skal vises som kombinasjon/pakke, ikke som om hver konto
  enkeltvis er trygg.
- Belop paa gruppenivaa er ikke nok uten konto-/alias-/regelstotte paa kontoene
  som inngaar.
- Ukjente eller blandede grupper skal feile til `uavklart_rf1022` eller
  `Maa vurderes`, ikke til loenn eller annen standardgruppe.
- Gruppevisningen maa deduplisere og refreshes rolig; den skal ikke henge GUI.

Praktisk plan er aa bygge en konservativ solver i flere steg: forst eksakte
summer for vanlige lonnsgrupper, deretter bedre forslagstekster, deretter
eventuell auto-kobling naar status er trygg.

## Hvorfor Dette Kan Bli Stort

Dette prosjektet handler ikke om at AI magisk skal forstaa revisjon. Det vi
bygger er sterkere enn det: en faglig regelmotor kombinert med klientdata,
laering og revisjonsspesifikke kontrollflater.

En generell LLM uten dette domenelaget vil ofte gjette. A07-sporet skal i
stedet kunne resonnere med sporbar evidens:

- konto
- kontonavn
- alias og ekskluderinger
- kontointervall
- belop og valgt kolonne
- A07-kode
- RF-1022-post
- avvik og auditstatus

Det er der presisjonen kommer fra. Naar A07 sitter, er monsteret overforbart
til MVA, skatt, lonnskostnader, naerstaende, driftsmidler, avsetninger og andre
revisjonsomraader. Ambisjonen er ikke aa lage en chatbot som svarer pent, men
et revisjonsverktoy som kan forklare hvorfor en kobling er trygg, mistenkelig
eller feil.

English version:

This may become something genuinely different. Not because AI magically
understands audit, but because we are building something better: a domain rule
engine combined with client data, learning loops, and audit-specific control
surfaces.

A general-purpose LLM without that domain layer will guess. This system should
eventually reason with traceable evidence: account number, account name,
aliases, exclusions, account ranges, amount basis, A07 code, RF-1022 group,
variance and audit status.

That is where the precision comes from. Once this works for A07, the same
pattern can be transferred to VAT, tax, payroll costs, related parties, fixed
assets, accruals and other audit areas. The goal is not a chatbot that sounds
convincing. The goal is an audit engine that can explain why a mapping is safe,
suspicious or wrong.

## Viktige Filer

- `page_a07.py`: offentlig A07-fasade og compat-entrypoint.
- `a07_feature/control/data.py`: kontroll-, audit-, RF-1022- og auto-planlogikk.
- `a07_feature/control/rf1022_bridge.py`: A07 -> RF-1022-bro.
- `a07_feature/parser.py`: parser A07-kilde, inkludert belop og AGA-plikt der
  kilden har feltet.
- `a07_feature/suggest/rulebook.py`: laster A07-regelbok til matcher-runtime.
- `a07_feature/suggest/engine.py`: kandidatmotor for A07-regler, special_add
  og gruppeforslag.
- `a07_feature/groups.py`: A07-grupper, runtime-grupper og persisted groups.
- `a07_feature/rule_learning.py`: intern regel-laering for A07 keywords,
  ekskluderinger og boost-kontoer.
- `a07_feature/page_a07_mapping_actions.py`: mappinghandlinger, fjerning og
  A07-laering fra `Koblinger`.
- `a07_feature/page_a07_context_menu.py`: hoyreklikkmenyer i A07.
- `a07_feature/ui/canonical_layout.py`: hovedlayout for A07-flaten.
- `a07_feature/ui/render.py`, `a07_feature/ui/support_render.py` og
  `a07_feature/ui/tree_render.py`: rendering av GL, A07-liste, forslag og
  koblinger.
- `saldobalanse_actions.py`: saldobalansehandlinger, inkludert A07-laering fra
  kontonavn.
- `page_admin.py`, `page_admin_rulebook.py`, `page_admin_catalog.py` og
  `page_admin_detail_class.py`: adminflatene for A07-regler, flater/grupper og
  kontoklassifisering.

## Neste Plan

Naereste nyttige steg:

1. Live-verifiser A07-fanen mot flere klienter etter siste GUI- og solverarbeid.
2. Fiks eventuelle stale cache-/refresh-problemer etter `Laer av konto`, slik at
   admin og A07-fane ser samme regel umiddelbart.
3. Gjennomgaa ytelse i A07-fanen. Tunge beregninger skal bare koere ved
   refresh/oppdatering, ikke ved hvert radvalg eller enkel hoyreklikkhandling.
4. Ferdigstill filteropprydding:
   - fjern `Kun aktive`
   - erstatt `Kun umappede` med `Alle` / `Kun mappede`
   - fjern `Vis kontoer` hvis nederste koblingsliste dekker behovet
   - behold kontoseriefilter
5. Ferdigstill A07-hoyre side:
   - fjern unodvendig `Vis`-rullgardin hvis fargestatus er nok
   - fjern `Skjul detaljer` hvis den ikke gir tydelig verdi
   - vis AGA-plikt tydelig i A07-listen
6. Stabiliser hoyreklikk:
   - GL-listen skal ha `Laer av konto`
   - nederste forslag/koblingsliste skal alltid ha meny
   - alle menyvalg skal invalidere relevante cacher
7. Stram forslag for generiske koder som `annet`, slik at out-of-scope
   driftskostnader ikke blir kandidat uten tydelig regelstotte.
8. Viderebygg solver for A07-grupper med eksakte summer og faglig evidens.
9. Live-test special_add for feriepenger, styrehonorar og andre
   periodiserings-/balanseposter.
10. Rydd Verktoy-menyen etter at vi har bekreftet hvilke handlinger som fortsatt
    har praktisk verdi.

## Kjente Avgrensninger

- Ingen automatikk skal slette eksisterende koblinger.
- Ingen endring skal gjore mappingformatet inkompatibelt.
- GUI er fortsatt viktig aa live-teste fordi mye av verdien handler om rolig
  arbeidsflyt, fokus og hoyreklikkhandlinger.
- Gamle konseptalias-/legacy-regelbokfiler er fjernet som A07-kilder.
- A07-grupper skal ikke bli nytt persistent mappingformat uten egen beslutning.
- AGA-pliktig-felt i A07-regelbok er fallback/regelmetadata; kilde-JSON skal
  fortsatt vinne der den faktisk inneholder AGA-plikt.

## Relaterte Dokumenter

- `README.md`: indeks for A07-lonnsporet.
- `WORKFLOW.md`: praktisk arbeidsflyt.
- `LIVE_VERIFICATION_CHECKLIST.md`: sjekkliste for live-test mot klientdata.
- `MODULE_MAP.md`: modulstruktur og compat-lag.
- `TESTING.md`: testsett som beskytter A07-sporet.
- `../A07_TARGET_ARCHITECTURE.md`: arkitektur- og migreringsretning.
