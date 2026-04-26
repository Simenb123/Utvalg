# A07: Status, Mal Og Overtakelse

Dette er hoveddokumentet for A07-sporet. Les denne filen for aa forstaa hva
A07 i Utvalg er, hva som nylig er gjort, hvordan systemet er tenkt brukt, og
hva som bor bygges videre.

Sist oppdatert: 2026-04-26.

Kort operativ status etter siste A07-runder ligger i `CURRENT_STATUS.md`.
Bruk den som startpunkt for "hvor er vi naa?". Denne filen er det lengre
overtakelsesnotatet med historikk, prinsipper og bakgrunn.

For kodebase-/refaktorretning, filstorrelser, `src/pages/a07`-migrering og
lagdeling fremover, se ogsaa:

- `doc/architecture/a07_refaktor_og_src_plan.md`

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
- Lagt om A07-hovedflaten til fire faste arbeidsflater:
  `Saldobalansekontoer`, `A07-koder`, `Forslag` og `Koblinger`.
- Fjernet nederste notebook/faner, permanente forslag-/koblingsknapper,
  nederste statuslinjer og annen visuell stoy fra hovedarbeidsflaten.
- Flyttet A07-grupper ut av fast hovedflate og inn i popup/dialog, mens
  gruppehandlinger fortsatt gjores fra hoyreklikk paa A07-koder.
- Endret support-render slik at `Forslag` og `Koblinger` rendres samtidig for
  valgt A07-kode, i stedet for aa vaere avhengig av aktiv nederste fane.
- Flyttet offentlig page-shell til `src/pages/a07/page_a07.py`, med
  `page_a07.py` som tynn compat-shim i repo-roten.
- Splittet tidligere monolitter i mindre kanoniske moduler, blant annet
  `control/data`, `queue_data`, `matching`, `mapping_audit`, `classification`,
  `page_paths`, `ui/helpers`, `ui/canonical_layout`, `page_windows`,
  `page_a07_project_actions`, `page_a07_context_menu` og
  `page_a07_dialogs`.
- Splittet den gamle testmonolitten i `tests/a07/` og redusert
  `tests/test_page_a07.py` til legacy smoke-/compat-dekning.
- Innfoert modulbudsjetter og egen storrelsesrapport, slik at nye monolitter
  blir synlige raskt og kan stoppes foer de fester seg.
- Strammet A07-oppstart/refresh slik at fanen ikke skal drive med aggressiv
  automapping bare fordi siden aapnes eller refresher.
- Lagt inn `Skjul null` i saldobalansekontoer for aa redusere stoy fra kontoer
  uten aktivt belop i valgt basis.
- Lagt inn tydeligere drag-and-drop-feedback i A07-panelet, slik at bruker ser
  hva som dras, hva som er maal, og naar slipp er gyldig.
- Innfoert residual-solver v1 for `Tryllestav: finn 0-diff`. Den analyserer
  aapne differanser i oere/int, beskytter ferdige koder, og foreslaar bare
  auto-endring naar hele scenarioet er trygt og eksakt.

## Siste Runde: Fire Arbeidsflater

Den nyeste GUI-retningen er at A07-fanen skal fungere som fire samtidige
arbeidsflater, ikke som en toppflate med en tung nederste notebook.

Fast layout:

- Ovre venstre: `Saldobalansekontoer`
- Ovre hoyre: `A07-koder`
- Nedre venstre: `Forslag`
- Nedre hoyre: `Koblinger`

Dette gir en roligere arbeidsflyt:

- Velg A07-kode i hoyre liste.
- Se relevante forslag nederst til venstre.
- Se eksisterende koblinger nederst til hoyre.
- Bruk hoyreklikk/dobbeltklikk for handlinger, ikke permanente knapper som tar
  plass.

A07-grupper beholdes, men skal ikke ta fast skjermplass. De aapnes i popup naar
det trengs, for eksempel fra dobbelklikk paa en grupperad eller fra
hoyreklikkhandlinger paa A07-koder.

Viktig prinsipp: dette var en GUI-/arbeidsflateopprydding. Den skulle ikke
endre matchingmotor, mappingformat eller A07-regelbokskjema.

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
- `src/pages/a07/page_a07.py` er naa kanonisk page shell og
  monkeypatch-/forwarding-grense; `page_a07.py` i repo-roten er kun
  compat-entrypoint.
- A07 har naa egne storrelsesguardrails og ingen kodemoduler over `700`
  linjer. Det gjenstaar fortsatt noen mellomstore hotspots, men de store
  monolittene er brutt ned.
- `tests/a07/` er naa kanonisk testsuite for intern A07-runtime; `tests/test_page_a07.py`
  lever videre som liten offentlig smoke-/compat-vakt.
- Residual-solveren bor i `a07_feature/suggest/residual_solver.py`, med rene
  datamodeller i `a07_feature/suggest/residual_models.py`.
- Visningsadapteren `a07_feature/suggest/residual_display.py` gjoer
  residual-analyse om til kompakte forslag-/review-rader for eksisterende
  forslagstabell.
- Tryllestav-flyten i page-laget er skilt ut i
  `a07_feature/page_a07_mapping_residual.py`.
- `Tryllestav: finn 0-diff` er i v1 en analyse- og sikker auto-apply-flyt, ikke
  en aggressiv "faa alt til aa gaa i null"-knapp.

Produktstatus:

- Brukeren skal kunne starte i A07-kodevisningen og se hvilke A07-koder som er
  ferdige, aapne eller mistenkelige.
- RF-1022 skal brukes som kontrolloppsummering og regnskapsmessig bro, ikke som
  primar aliasmatchingflate.
- `Forslag` viser kandidater.
- `Forslag` skal vise kontoer, A07-belop, GL-forslag, diff, status og hvorfor.
- `Koblinger` viser eksisterende koblinger, auditstatus og belop.
- `Forslag` og `Koblinger` skal alltid oppdateres sammen for valgt A07-kode.
- A07-grupper skal vises i egen popup, ikke som fast panel i hovedbildet.
- Global auto skal koere av seg selv for klare fasitsaker naar A07 oppdateres.
- Global auto og tryllestav skal ikke overskrive allerede ferdige 0-diff-koder.
- Feil eller mistenkelige koblinger ryddes manuelt via hoyreklikk/Delete.
- Hoyreklikk paa GL, A07-linje, forslag og koblinger skal gi samme mentale
  modell: tildel, fjern, laer alias, ekskluder alias eller gaa til admin.
- A07-koder med diff null skal markeres gronne; aapne/mistenkelige koder skal
  ikke se ferdige ut.

## Tryllestav Og Residual-Solver V1

Tryllestav v1 er bygget for revisjonsfaglig trygghet foer aggressiv
automatisering. Den skal hjelpe bruker aa se om en trygg helkonto-losning finnes,
men den skal ikke tvinge A07 til null ved aa flytte svake eller ferdige
koblinger.

Styrende regler:

- Alle belop analyseres deterministisk i oere/int, ikke som floats.
- A07-koder med `Diff = 0` er ferdige og skal ikke endres av tryllestav.
- Kontoer/koblinger som er `Trygg` skal som standard ikke flyttes.
- Kandidatpoolen er konservativ: umappede kontoer, `Uavklart`/`Feil`-koblinger
  og svake mappinger som horer til aapne koder.
- `annet` er residual/siste-utvei-kode og skal normalt vaere review-only.
- Auto-apply er bare lov naar hele aapne residual-scenarioet er `safe_exact`.
- Delvise eksakte treff kan vises i analyse, men skal ikke auto-appliseres hvis
  andre aapne koder fortsatt mangler trygg losning.
- Review-rader fra tryllestaven kan aapnes i avansert mapping med konto/kode
  forhaandsutfylt, men de skal ikke autosaves eller auto-appliseres.
- Naar ingen trygg helkonto-losning finnes, skal solver forklare kort at
  manuell vurdering eller splitt kreves.

5310-caset styrer denne retningen: konto `5310 Gruppelivsforsikring` kan forklare
samlet rest i eksempelet, men det er ikke nok til trygg automatisk mapping.
Solveren skal derfor markere konto/rest som mistenkelig eller review-only, ikke
late som hele A07 er trygt avstemt.

GUI-prinsipp for videre arbeid:

- Ikke legg masse tekst i hovedbildet.
- Bruk korte statuser, tags og kompakte kolonner som `Trygg`, `Maa vurderes`,
  `Mistenkelig rest` og `Laast 0-diff`.
- Lengre forklaring skal ligge bak detaljer/avansert visning, ikke dominere
  hovedflyten.

Sist verifiserte kommandoer:

```powershell
py -3 -m compileall -q page_a07.py a07_feature src\pages\a07 tests\a07
py -3 -m pytest tests\a07 tests\test_a07_module_budgets.py tests\test_a07_namespace_smoke.py tests\test_a07_chain_regression.py tests\test_page_a07.py tests\test_page_a07_payroll.py --no-cov -q
py -3 -m pytest tests\test_page_control_data_rf1022.py tests\test_page_saldobalanse.py tests\test_ui_main_dataset_analysis.py tests\test_tb_only_mode.py tests\test_payroll_classification.py tests\test_payroll_classification_suggest.py tests\test_payroll_classification_classify.py tests\test_payroll_classification_catalog.py tests\test_payroll_classification_audit.py --no-cov -q
py scripts\report_a07_module_sizes.py
```

Nyeste residual-/tryllestav-runde ble verifisert med:

```powershell
py -m pytest tests/a07 --no-cov -q
py -m pytest tests/test_a07_namespace_smoke.py tests/test_a07_module_budgets.py --no-cov -q
py -m py_compile a07_feature/suggest/residual_models.py a07_feature/suggest/residual_solver.py a07_feature/page_a07_mapping_residual.py a07_feature/page_a07_mapping_batch.py tests/a07/test_residual_solver.py tests/a07/test_residual_magic.py
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
- Automatching maa likevel vaere konservativ: ferdige 0-diff-koder, trygge
  koblinger og review-only residualer skal ikke overstyres automatisk.

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
- `Explain` og `HvorforKort` er visningsfelt. Beslutningslogikk skal bruke
  strukturerte evidence-felt som `UsedRulebook`, `UsedUsage`,
  `UsedSpecialAdd`, `AmountEvidence`, `HitTokens`, `AnchorSignals` og
  `SuggestionGuardrail`.

## Dagens Arbeidsflyt

1. Last A07.
2. Oppdater mot aktiv saldobalanse.
3. Motoren koerer trygge automatiske A07-koblinger naar evidensen er klar.
4. Bruk A07-kodevisningen som hovedarbeidsflate.
5. Bruk RF-1022/kontrolloppstilling som oppsummering og avvikskontroll.
6. Se usikre kandidater i `Forslag`.
7. Kontroller eksisterende koblinger i `Koblinger`.
8. Bruk A07-gruppe-popup ved behov for aa se eller rydde grupper.
9. Rydd feil/mistenkelige koblinger med hoyreklikk eller Delete.
10. Bruk `Laer av kontonavn` naar en feil er aapenbar:
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

- `src/pages/a07/page_a07.py`: kanonisk page shell, offentlig A07-entrypoint og
  shared-ref-sync for shell/runtime.
- `page_a07.py`: tynn root-compat-shim for eldre importer.
- `a07_feature/control/data.py`: kanonisk kontrollfasade over
  `overview_data`, `history_data`, `control_queue_data`, `control_gl_data`,
  `statement_data`, `rf1022_candidates`, `rf1022_support`, `mapping_audit` og
  `global_auto`.
- `a07_feature/control/matching.py` og `a07_feature/control/matching_*`:
  guardrails, historikkvurdering og presentasjonsstatus for forslag.
- `a07_feature/control/mapping_audit.py` og `a07_feature/control/mapping_*`:
  runtime-audit, review og projeksjon av eksisterende koblinger.
- `a07_feature/control/statement_ui.py` og `statement_*`: kontrolloppstilling,
  vindu/panel-state og statement-visning.
- `a07_feature/payroll/classification.py` og `classification_*`:
  lonnsklassifisering, payroll-relevans og katalog-/guardrail-logikk.
- `a07_feature/payroll/rf1022.py`: RF-1022-runtime og payroll-kontrollflyt.
- `a07_feature/suggest/residual_solver.py`: ren residual-solver for
  `Tryllestav: finn 0-diff`, uten GUI-avhengighet.
- `a07_feature/suggest/residual_models.py`: statuskonstanter, dataclasses og
  belopskonvertering i oere/int for residual-solveren.
- `a07_feature/suggest/residual_display.py`: adapter som lager korte
  forslag-/review-rader av residual-analysen.
- `a07_feature/page_a07_mapping_actions.py` og `page_a07_mapping_*`:
  mappinghandlinger, batchflyt, laering og kontrollhandlinger fra hovedflaten.
- `a07_feature/page_a07_mapping_residual.py`: page-flyt rundt residual-solveren,
  inkludert kort review-feedback og trygg auto-apply-grense.
- `a07_feature/page_a07_context_menu.py` og `page_a07_context_menu_*`:
  hoyreklikkmenyer for GL, forslag, koblinger, A07-koder og grupper.
- `a07_feature/page_a07_dialogs.py` og `page_a07_dialogs_*`:
  picker-/editorhjelpere og manual mapping-dialog.
- `a07_feature/page_a07_refresh.py`, `page_a07_refresh_apply.py`,
  `page_a07_refresh_state.py` og `page_a07_refresh_services.py`:
  refresh-orkestrering, payload-apply, cache/state og payload-bygging.
- `a07_feature/ui/`: kanonisk UI-lag for layout, selection, support-render,
  tree-render og helpers.
- `tests/a07/`: kanonisk intern A07-testsuite etter testsplitten.
- `tests/test_page_a07.py`, `tests/test_a07_namespace_smoke.py` og
  `tests/test_a07_module_budgets.py`: offentlig smoke-/compat- og
  strukturvakter.

## Neste Plan

Naereste nyttige steg:

1. Gaa tilbake til funksjonalitetsutvikling paa toppen av den nye strukturen.
2. Gjore tryllestav-resultatet mer operativt i GUI uten tekstvegg: korte
   statuser, tags og eventuelt en kompakt detaljer-/avansertvisning.
3. Bruk videre refaktor bare maalrettet der konkret featurearbeid treffer et
   gjenvaarende hotspot.
4. Prioriter refresh-klyngen ved neste strukturelle behov:
   - `page_a07_refresh_apply.py`
   - `page_a07_refresh_state.py`
   - `page_a07_refresh.py`
   - eventuelt `page_a07_refresh_services.py`
5. Fortsett aa holde `src/pages/a07/page_a07.py` som rent page shell og unngaa
   at ny motorlogikk lekker inn der.
6. Hold modulbudsjetter, smoke-tester og `report_a07_module_sizes.py` oppdatert
   samtidig som nye features legges til.
7. Live-verifiser fortsatt nye A07-endringer mot flere klienter, spesielt naar
   refresh, historikk eller solverlogikk endres.

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
