# A07: Status, Mal Og Overtakelse

Dette er hoveddokumentet for A07-sporet. Les denne filen for aa forstaa hva
A07 i Utvalg er, hva som nylig er gjort, hvordan systemet er tenkt brukt, og
hva som bor bygges videre.

Sist oppdatert: 2026-04-21.

## Kortversjon

A07 skal hjelpe revisor med aa avstemme og koble A07/A-melding-data mot
saldobalanse, A07-koder og RF-1022. Malet er trygg revisjonsstotte, ikke flest
mulig automatiske koblinger.

Arbeidsretningen er:

- A07-koder er canonical matchingnivaa.
- RF-1022 er aggregert kontroll- og visningsnivaa.
- Automatikk skal feile lukket.
- Eksisterende daarlige koblinger skal flagges og gjores enkle aa rydde, ikke
  slettes automatisk.
- Nye A07-aliaser og ekskluderinger skal inn i A07-regelbok, ikke i legacy
  konseptaliaser.

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

## Dagens Status

Teknisk status:

- A07-regelbok er canonical sted for A07-matchingregler.
- `payroll_alias_library.json` finnes fortsatt som legacy/kompatibilitetslag.
  Runtime leser det fortsatt som fallback, men nye A07-laeringer skal ikke
  skrives dit.
- RF-1022-aliaser ligger fortsatt i RF-/klassifiseringskatalogen.
- Mappingformatet er uendret: lagret mapping representerer konto -> A07-kode.
- `mapping_audit_df` og `AliasStatus` er runtime-kontrollinformasjon, ikke nytt
  lagringsformat.

Produktstatus:

- Brukeren skal kunne starte i RF-1022-visningen for kontroll.
- `Forslag` viser kandidater.
- `Koblinger` viser eksisterende koblinger og auditstatus.
- `Kjor automatisk matching` skal bare bruke trygge kandidater.
- Feil eller mistenkelige koblinger ryddes manuelt via hoyreklikk/Delete.

Sist verifiserte kommandoer:

```powershell
py -3 -m compileall -q page_a07.py a07_feature saldobalanse_actions.py page_admin.py page_admin_alias.py page_admin_rulebook.py
py -3 -m pytest tests/test_page_a07.py tests/test_page_a07_payroll.py tests/test_a07_chain_regression.py tests/test_a07_namespace_smoke.py tests/test_a07_control_matching.py tests/test_a07_control_statement_source.py tests/test_a07_feature_suggest.py tests/test_payroll_classification.py tests/test_a07_feature_reconcile.py tests/test_page_control_data_rf1022.py tests/test_a07_control_presenter.py tests/test_page_saldobalanse.py tests/test_page_saldobalanse_detail_panel.py --no-cov -q
```

## Regelmodell

A07-regelbok:

- Fil: `config/classification/global_full_a07_rulebook.json`
- Brukes til A07 `keywords`, `exclude_keywords`, `allowed_ranges`,
  `boost_accounts`, `basis`, `expected_sign` og `special_add`.
- Nye A07-laeringer fra A07-fanen og saldobalanse skal skrives hit.

Konseptaliaser:

- Fil: `config/classification/payroll_alias_library.json`
- Brukes fortsatt som legacy/fallback naar effektiv A07-regelbok lastes.
- Skal ikke vaere hovedflate for nye A07-laeringer.
- Admin-fanen er merket som avansert/legacy for aa redusere forvirring.

RF-1022:

- RF-1022 er aggregert kontrollnivaa.
- RF-1022 bygges fra A07-koder via RF-1022-broen.
- Ukjente A07-koder skal ende som `uavklart_rf1022`, ikke falle tilbake til
  loenn.
- RF-1022-aliaser horer hjemme i RF-/klassifiseringskatalogen.

## Matchingregler Vi Beskytter

- Belop alene er ikke nok for trygg automatisk mapping.
- Historikk alene er ikke nok for nye trygge forslag.
- RF-1022-kandidater maa ha riktig gruppe, alias/katalogstotte og egen
  belopsstotte.
- `2940 Skyldig feriepenger` skal ha eksplisitt periodiserings-/balansestotte.
- `6701 Honorar revisjon` skal ikke ende i loenn/`annet` via belop alene.
- `5890 Annen refusjon` skal ikke vaere trygg refusjonskandidat uten
  NAV/sykepenger/foreldrepenger eller separat evidens.
- `5800 Refusjon av sykepenger` kan vaere trygg refusjonskandidat naar
  spesifikk stotte finnes.

## Dagens Arbeidsflyt

1. Last A07.
2. Oppdater mot aktiv saldobalanse.
3. Bruk RF-1022-visningen som hovedkontroll.
4. Se kandidater i `Forslag`.
5. Kjor automatisk matching bare for trygge kandidater.
6. Kontroller `Koblinger`.
7. Rydd feil/mistenkelige koblinger med hoyreklikk eller Delete.
8. Bruk `Laer av kontonavn` naar en feil er aapenbar:
   - legg navn til A07-alias for en riktig kobling
   - ekskluder navn fra A07-kode for en feil kobling
   - fjern mapping og ekskluder navn i samme handling

## Strategisk Retningsvalg: A07-Grupper

Vi ser at noen A07-koder maa vurderes samlet for at avstemmingen skal gi
mening. Det betyr ikke at vi skal bygge full A07-gruppemotor foer resten av
flyten er stabil.

Gjeldende beslutning:

- A07-koder forblir canonical matchingnivaa.
- RF-1022 forblir aggregert kontroll- og visningsnivaa.
- A07-grupper/pakker kan brukes som kontrollforklaring og summeringsnivaa.
- Full gruppematching skal vente til GUI, audit, laering, fjerning og trygg
  global auto fungerer rolig mot faktiske klientdata.

Guardrails for A07-grupper:

- En gruppe skal ikke alene gjore en konto trygg.
- En gruppe skal ikke skjule at enkeltkontoer mangler faglig evidens.
- Kombinasjonsforslag skal vises som kombinasjon/pakke, ikke som om hver konto
  enkeltvis er trygg.
- Belop paa gruppenivaa er ikke nok uten konto-/alias-/regelstotte paa
  kontoene som inngaar.
- Ukjente eller blandede grupper skal feile til `uavklart_rf1022` eller
  `Maa vurderes`, ikke til loenn eller annen standardgruppe.
- Mappingformatet skal fortsatt representere konto -> A07-kode. Eventuelle
  grupper skal vaere runtime-kontrollinformasjon inntil en egen migrering er
  eksplisitt vedtatt.

Praktisk prioritet naa er derfor ikke aa utvide gruppelogikken kraftig. Neste
steg er aa gjore eksisterende flate forutsigbar: ingen stale forslag, ingen
overraskende fokusflytting, ingen menyvalg som bare delvis virker, og ingen
automatisk mapping uten sporbar faglig og belopsmessig stotte.

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
- `a07_feature/rule_learning.py`: intern regel-laering for A07 keywords,
  ekskluderinger og boost-kontoer.
- `a07_feature/page_a07_mapping_actions.py`: mappinghandlinger, fjerning og
  A07-laering fra `Koblinger`.
- `a07_feature/page_a07_context_menu.py`: hoyreklikkmenyer i A07.
- `saldobalanse_actions.py`: saldobalansehandlinger, inkludert A07-laering fra
  kontonavn.
- `page_admin.py`, `page_admin_rulebook.py`, `page_admin_alias.py`:
  adminflatene for A07-regler og legacy konseptaliaser.

## Neste Plan

Naereste nyttige steg:

1. Live-verifiser A07 mot faktisk klientdata.
2. Test spesielt `2940`, `5800`, `5890` og `6701`.
3. Kontroller at `Alias`-kolonnen gir nyttig forklaring i GL og `Koblinger`.
4. Test hoyreklikkflyten `Fjern mapping og ekskluder navn` i GUI.
5. Bygg en tydeligere `Kontroller eksisterende koblinger`-visning/filter.
6. Flagge out-of-scope og mistenkelige mappinger enda mer synlig.
7. Vurdere migrering av gamle konseptaliaser inn i A07-regelbok.
8. Skjule eller flytte `Konseptaliaser` enda tydeligere bak avansert/legacy
   dersom admin-UI fortsatt oppleves forvirrende.
9. Vurdere A07-grupper/pakker foerst naar punktene over er stabile nok til at
   gruppelogikken ikke gjor GUI og matching vanskeligere aa forstaa.

## Kjente Avgrensninger

- Ingen automatikk skal slette eksisterende koblinger.
- Ingen endring skal gjore mappingformatet inkompatibelt.
- GUI er fortsatt viktig aa live-teste fordi mye av verdien handler om rolig
  arbeidsflyt, fokus og hoyreklikkhandlinger.
- Konseptaliaser kan ikke slettes direkte ennå; de er fortsatt runtime-input.

## Relaterte Dokumenter

- `README.md`: indeks for A07-lonnsporet.
- `WORKFLOW.md`: praktisk arbeidsflyt.
- `LIVE_VERIFICATION_CHECKLIST.md`: sjekkliste for live-test mot klientdata.
- `MODULE_MAP.md`: modulstruktur og compat-lag.
- `TESTING.md`: testsett som beskytter A07-sporet.
- `../A07_TARGET_ARCHITECTURE.md`: arkitektur- og migreringsretning.
