# Handlinger 2.0 — Plan-, risiko- og utførelsesmodell

**Status:** Designutkast / drøftedokument. Ikke implementert. Ment for refleksjon før gjennomføring.
**Sist oppdatert:** 2026-04-23
**Forutgående:** [handlinger_workpapers.md](handlinger_workpapers.md) (slice 1 — bekreftede CRM-koblinger).
**Relaterte:** [scoping_engine](../../scoping_engine.py), [action_library](../../action_library.py), [action_workpaper_store](../../action_workpaper_store.py), [page_revisjonshandlinger](../../page_revisjonshandlinger.py), arkitekturnotater for [A07](../../a07_feature/), [analyse_pivot_engine.md](analyse_pivot_engine.md).

## Formål med dette dokumentet

Beskrive en helhetlig plan-/risiko-/utførelsesmodell som dekker hele revisjonsflyten i Utvalg, og som kobler eksisterende byggeklosser (Scoping, Vesentlighet, A07, AR, Analyse, Utvalg/sampling, MVA, Driftsmidler m.fl.) til ett sammenhengende arbeidsløp. Dokumentet er **ikke** en implementeringsplan — det er en gjennomtenkning av modellen vi skal bygge på. Konkrete slices og kode kommer etter at modellen er gjennomdrøftet.

## Bakgrunn

Slice 1 av Handlinger 2.0 (`workpapers.json`) håndterer bekreftelse/overstyring av RL-koblinger for CRM-handlinger. Det dekker *én* vinkel: «hvilken regnskapslinje hører denne CRM-handlingen til?». Det dekker ikke:

- Hvilken risiko CRM-handlingen er en respons på
- Hvilke påstander handlingen dekker
- Hvor handlingen faktisk utføres (hvilken Utvalg-fane)
- Hva status er, og hvilken evidens som er produsert
- Hvordan flere handlinger på samme regnskapslinje (splitting) håndteres
- Hvordan revisjonsprogrammet flyter fra vesentlighet → scoping → risiko → handling → utførelse → arbeidspapir

Disse manglene er ikke tekniske feil, de er bevisste begrensninger i slice 1. Dette dokumentet skisserer modellen som dekker hullene.

## Faglig forankring

Modellen er designet for å støtte revisjonsmetodikk i tråd med ISA-standardene:

- **ISA 315 / 330** — robust risikoidentifikasjon før utforming av fokuserte responser. Krever at handlinger er sporbart begrunnet i en risiko, ikke valgt løsrevet.
- **ISA 320** — vesentlighetsbestemmelse styrer hvilke regnskapslinjer som scopes inn (eksisterende `scoping_engine` følger dette).
- **ISA 520** — analytiske handlinger må være *egnet for påstanden* og bygd på pålitelig data. Begrunner krav om eksplisitt kobling påstand ↔ handling.
- **ISA 530** — utvalg må designes ut fra formål, populasjon og akseptabelt sampling risk. Påvirker `target_type=utvalg`-adapterens kontrakt.
- **ISA 230** — dokumentasjon som separat revisjonsspor. Excel er *projeksjon*, ikke sannhet — artefaktregisteret er sporet.
- **ISA 240** (revidert, ikraft 15.12.2026) — sterkere fraud-lens. Argument for spesialhandlinger for mislighetsrisiko inntekter og ledelsens overstyring.
- **ISA 550** — særskilt forståelse, forespørsler og risikohåndtering for nærstående parter. Argument for AR-knyttet spesialhandling.

## Begrepsmodell — lås språket først

I dag brukes ordet «handling» om minst tre ulike ting i kodebasen og samtalene. Vi låser begrepene:

| Begrep (norsk) | Engelsk modellnavn | Betydning |
|---|---|---|
| **Mal** | `ActionTemplate` | Gjenbrukbar definisjon i handlingsbiblioteket. Beskriver metode, hvor den utføres, hvilke påstander den dekker. Vedlikeholdes sentralt. |
| **Risiko** | `RiskNode` | Klient/år-spesifikk identifisert risiko. Knyttet til en RL eller tverrgående tema. Har påstander, iboende risiko, begrunnelse. |
| **Planlagt handling** | `PlannedResponse` | Revisors beslutning om at en konkret mal skal anvendes mot en konkret risiko, i en bestemt fase, evt. med segment/avgrensning. |
| **Utførelse** | `ExecutionRecord` | Faktisk arbeid: status, svar, observasjoner, konklusjon, signering. Skjer i en utførelsesmotor (Utvalg-fane eller inline). |
| **Evidens** | `ArtifactLink` | Peker til produsert fil, arbeidspapir eller intern feature-referanse. |

Disse fem ordene er kjernen. All kode, GUI-tekst og dokumentasjon skal bruke dem konsistent. Når en ny utvikler eller revisor leser systemet skal de aldri lure på hva som menes med «handling».

## Domenemodell

### `ActionTemplate` (mal i biblioteket)

```text
id                   stabil nøkkel (uuid eller stabil slug som "motpostanalyse")
navn                 visningsnavn
beskrivelse          fri tekst, faglig formål
type                 substansiv | kontroll | analyse | innledende | annen
versjon              int (slice 2: alltid 1; versjonering legges til senere ved behov)

assertions           list[str] — F G N P K — påstander malen dekker
target_type          inline | analyse | utvalg | a07 | ar | mva |
                     driftsmidler | vesentlighet | scoping | skatt |
                     lønn | reskontro | special
target_ref           streng — peker til konkret funksjon innen target_type
                     (f.eks. "motpost", "bankavstemming", "fra_inntekter")

rl_kategori          driftsinntekter | driftskostnader | lønn | bank |
                     fordringer | gjeld | egenkapital | skatt | ... | tverrgående
risk_type_applicable list[str] — T | M | R — hvilke risiko-typer malen passer for

workpaper_template_id   referanse til arbeidspapir-generator (default eller spesial)
schema               dict | null — KUN for target_type=inline, beskriver felter
                     revisor skal fylle ut (navn, type, påkrevd)
```

Lagring: utvidelse av eksisterende `LocalAction` i [action_library.py](../../action_library.py). Ingen breaking change — nye felter er valgfrie. Eksisterende JSON-filer fortsetter å fungere.

### `RiskNode` (klient/år-risiko)

```text
id                   deterministisk fra (klient, år, regnr) for RL-bundne,
                     uuid for tverrgående/ad-hoc
klient, år
type                 T (Trigger) | M (Mislighet) | R (Risiko-relatert)
regnr                str | null — bundet til regnskapslinje, eller null for tverrgående
transaksjonsklasse   str | null — alternativ til regnr
navn                 visningsnavn (f.eks. "070 Andre driftskostnader",
                     "Mislighetsrisiko inntekter", "Nærstående parter")
assertions           list[str] — F G N P K — relevante påstander
inherent_risk        lav | middels | høy
område               regnskapsrapportering | tverrgående | ...
begrunnelse          fri tekst — hvorfor denne risikoen er identifisert
signed_by            str — hvem som godkjente risiko-vurderingen
signed_at            datetime
```

Lagring: ny fil `years/<YYYY>/handlinger/risk_nodes.json`.

### `PlannedResponse` (planlagt handling)

```text
id                   uuid
risk_node_id         FK → RiskNode
template_id          FK → ActionTemplate
template_snapshot    dict — fryst kopi av relevante template-felt på
                     planleggingstidspunktet (sikrer at endring i bibliotek
                     ikke ødelegger fjorårets dokumentasjon)

fase                 oppdragsvurdering | planlegging | utførelse | avslutning
target_type          str — fra template, kan overstyres
target_ref           str — fra template, kan overstyres
segment              dict | null — avgrensning ved splitting
                     (f.eks. {"konto_range": "6300-6399"} for
                     "leie av lokaler"-delen av RL 070)

ansvarlig            str
omfang               obligatorisk | valgfri
ordering             int — sekvens innen fase
```

Lagring: ny fil `years/<YYYY>/handlinger/planned_responses.json`.

### `ExecutionRecord` (utførelse)

```text
id                   uuid
planned_response_id  FK → PlannedResponse
status               tom | påbegynt | ferdig | signert
progress             str | null — f.eks. "5/8" for delvis-utført
inline_data          dict | null — fri form for target_type=inline
                     (svar, observasjoner, konklusjon basert på template.schema)
signert_av           str | null
signert_dato         datetime | null
last_synced_at       datetime — siste gang status ble hentet fra adapter
```

Lagring: ny fil `years/<YYYY>/handlinger/execution_records.json`.

For `target_type != inline` lever de faktiske dataene (utvalgslister, A07-svar, motpost-analyse-resultat) i target-fanens egen lagring. `ExecutionRecord` er en koordinerings-shadow som speiler status og holder evidens-pekere.

### `ArtifactLink` (evidens)

```text
id                   uuid
execution_record_id  FK → ExecutionRecord
type                 file | workpaper | external | feature_ref
path                 str — relativ sti for filer
ref                  str — id for arbeidspapir eller feature-intern referanse
url                  str | null — for eksterne lenker
generert_av          str — navnet på prosessen som lagde artefaktet
generert_dato        datetime
```

Lagring: ny fil `years/<YYYY>/handlinger/action_documents.json`. Forutsatt allerede i [handlinger_workpapers.md](handlinger_workpapers.md) som planlagt neste filtype.

## Forhold til eksisterende kode

| Eksisterende | Hva som gjenbrukes/utvides |
|---|---|
| [action_library.py](../../action_library.py) `LocalAction` | Utvides additivt med `assertions`, `target_type`, `target_ref`, `rl_kategori`, `risk_type_applicable`, `workpaper_template_id`. Eksisterende felter (`id`, `navn`, `type`, `omraade`, `default_regnr`, `standard_arbeidspapir`, `workpaper_ids`, `beskrivelse`) beholdes uendret. |
| [action_workpaper_store.py](../../action_workpaper_store.py) `workpapers.json` | Beholdes som «slice 1»-laget. CRM-handlinger som bekreftes mot RL fortsetter å lagres her. Den nye modellen leser disse for å vise CRM-koblede handlinger samlet med planlagte-handlinger. |
| [scoping_engine.py](../../scoping_engine.py) `ScopingLine.audit_action` | Erstattes gradvis av referanser til `PlannedResponse`-IDer. Bakoverkompatibel migrering: feltet beholdes som fritekst i v1, men nye registreringer er strukturerte. |
| [scoping_engine.py](../../scoping_engine.py) `ScopingLine.action_count` | Kan utvides til å telle både CRM-match og `PlannedResponse`-koblinger. |
| [page_revisjonshandlinger.py](../../page_revisjonshandlinger.py) | Beholdes som kommandosenter. Fasegrupperes gradvis (Oppdragsvurdering / Planlegging / Utførelse / Avslutning). Detaljpanelet utvides til å vise risiko, plan og utførelse samtidig. |
| [page_scoping.py](../../page_scoping.py) | Utvides til full risikovurderings-flate. Fanen renames (forslag: «Risikovurdering»). Eksisterende klassifisering/scoping-kolonner beholdes, nye risiko-attributter kommer som ekstra kolonner. |
| Eksisterende arbeidspapir-generatorer (workpaper_*.py) | Inngår som `workpaper_template_id` i ActionTemplate. Standardgenerator dekker «vanlige» RL; spesialgeneratorer for FRA, estimater, nærstående, mislighet. |
| Utførelsesfaner (A07, AR, Analyse, Utvalg, MVA, Driftsmidler, Vesentlighet, …) | Får hver sin **statusadapter** (kontrakt under). Ingen fane-intern logikk endres — kun en tynn «utlevering»-flate eksponeres. |

## Lagringsmønster

Filbasert per klient/år, i tråd med eksisterende lagringskultur (workpapers, A07-state, artefaktregister). **Ingen ny sentral database i v1.** Begrunnelse:

- Repoet har konsistent klient/år-lagring — å bryte mønsteret for ett delsystem skaper inkonsistens
- A07-arkitekturen anbefaler eksplisitt samme mønster
- En logisk repository-abstraksjon mellom domene og fil gjør at SQLite kan introduseres senere uten domene-endringer hvis tversgående analyse blir nødvendig

Filer under `years/<YYYY>/handlinger/`:

```text
workpapers.json          eksisterende — bekreftede CRM↔RL-koblinger (slice 1)
risk_nodes.json          NY — RiskNode-instanser
planned_responses.json   NY — PlannedResponse-instanser
execution_records.json   NY — ExecutionRecord-instanser
action_documents.json    NY — ArtifactLink-instanser
assignments.json         OPSJON — eier/ansvarlig per handling/risiko
templates_cache.json     OPSJON — snapshot av brukte maler for revisjons-spor
```

Globalt (under `app_paths.data_dir()`):

```text
action_library.json      eksisterende — handlingsbibliotek (utvidet)
```

### Repository-lag

For hver entitetstype et lite Python-modul med:

```python
load_<type>(klient, år) -> list[<Type>]
save_<type>(klient, år, items) -> None
get_by_id(klient, år, id) -> <Type> | None
upsert(klient, år, item) -> None
delete(klient, år, id) -> bool
```

Plassering: ny featurepakke `engagement_actions/` (eller `handlinger_feature/`) med:

```text
engagement_actions/
  __init__.py
  models.py              dataclasses for de fem entitetene
  store.py               repository-funksjoner per entitet
  router.py              dispatch til target_type-adaptere
  status_adapters/
    __init__.py
    analyse.py
    utvalg.py
    a07.py
    ar.py
    mva.py
    driftsmidler.py
    inline.py
    ...
  export.py              Excel-projeksjon
  ui/                    GUI-komponenter (tabeller, dialoger)
```

Dette matcher repoets retning mot featurepakker (jf. `a07_feature/`, `src/pages/`-refaktor).

## Adapterkontrakt for utførelsesmotorer

Hver utførelsesfane som er router-target eksponerer en liten kontrakt. Kontrakten er pure functions som tar en context og returnerer enten en handling (`open`) eller data (`get_*`):

```python
def open(context: ExecutionContext) -> None:
    """Hopp til fanen, scrollet/filtrert til riktig kontekst."""

def get_status(context: ExecutionContext) -> ExecutionStatus:
    """{state, progress, signed_by, signed_at, last_updated}"""

def get_evidence_refs(context: ExecutionContext) -> list[ArtifactRef]:
    """Liste over filer/arbeidspapirer denne handlingen har produsert."""

def get_export_section(context: ExecutionContext) -> ExportSection:
    """Innhold for Excel-projeksjon (tabell + tekst, klar til render)."""
```

`ExecutionContext` inneholder typisk: klient, år, regnr (nullable), segment (nullable), planned_response_id. Adapteren bruker disse til å slå opp riktig data i fanens egen lagring.

Adaptere kobles inn én etter én. Foreslått rekkefølge:

1. **Analyse** — eksisterende motpost/trend/bruttofortjeneste-handlinger har strukturert state; lett å eksponere status
2. **Utvalg** (Selection Studio) — sampling-state er ferdig modellert
3. **A07** — egen featurepakke med klar lagrings-pattern; status «alle inntektsmottakere behandlet» er enkel
4. **AR** — klientinfo-arbeidspapir gir naturlig «ferdig-flagg» når eksportert
5. Resterende (MVA, Driftsmidler, Vesentlighet, Skatt, Reskontro) — etter behov

## Faser i revisjonsprosessen

Modellen organiseres etter de fire revisjons-stegene. `PlannedResponse.fase` styrer hvilken seksjon en handling tilhører.

| Fase | Typisk innhold | Eksempel-maler |
|---|---|---|
| **1. Oppdragsvurdering** | Få faste handlinger før oppdraget aksepteres | Oppdragsvurdering, uavhengighetsvurdering |
| **2. Planlegging** | Forberedelse til utførelse: forståelse, vesentlighet, scoping, risikoidentifikasjon, planlegging | Innledende analyse (target=analyse), Vesentlighet (target=vesentlighet), Klientinfo (target=ar), Forespørsler til ledelsen (target=inline), Risikomatrise-utfylling |
| **3. Utførelse** | Substanshandlinger, detaljkontroller, kontrolltester | Motpostanalyse (target=analyse), Detaljkontroll bilag (target=utvalg), Lønnsarbeid (target=a07), MVA-avstemming (target=mva), Avskrivningsmodell (target=driftsmidler), spesialhandlinger (FRA, estimater, nærstående) |
| **4. Avslutning** | Avsluttende analyse, ikke-korrigerte feil, konklusjon | Avsluttende analyse (target=analyse), Ikke-korrigerte feil (target=inline), Konklusjon (target=inline) |

## Excel-arbeidspapir som projeksjon

Excel-output bygges som projeksjon av modellen, ikke som arbeidsformat. To filtyper:

**A. Konsolidert revisjons-arbeidspapir** (per klient/år):
- Forside: klient, år, totalstatus per fase
- Per fase: liste over PlannedResponses med status, signering, koblet RiskNode
- Per RL/risiko: detaljblokk med RiskNode-attributter (påstander, iboende, begrunnelse) og koblede handlinger
- Skjult `_meta`-ark: `planned_response_id` / `execution_record_id` for hver linje, så Excel kan kobles tilbake til database

**B. Individuelle arbeidspapirer per handling**:
- Genereres av `workpaper_template_id` på malen
- Standardgenerator dekker «vanlige» RL-handlinger
- Spesialgeneratorer for FRA, estimater, nærstående, mislighet (ISA 240/550-drevet)
- Lagres i artefaktregisteret med `ArtifactLink` tilbake til `ExecutionRecord`

## Spesialhandlinger som krever egne maler

Disse handlingene har skjema og output-struktur som ikke passer i standard RL-mal. De får egne `target_type=special` og dedikerte `target_ref`-verdier + `excel_template`-IDer:

| Handling | `target_ref` | Hjemmel |
|---|---|---|
| Mislighetsrisiko inntekter | `special:fra_inntekter` | ISA 240 |
| Ledelsens overstyring av kontroller | `special:management_override` | ISA 240 |
| Nærstående parter | `special:related_parties` | ISA 550 |
| Estimater | `special:estimates` | ISA 540 |

Disse har egne skjemaer (sensitivitetsanalyse, journal-entry-kriterier osv.) og leverer egne Excel-arbeidspapirer.

## Forhold til CRM/Descartes

Dagens [page_revisjonshandlinger.py](../../page_revisjonshandlinger.py) er en read-only visning av CRM-handlinger med RL-auto-match. I den nye modellen:

- **CRM-handlinger** vises fortsatt som kilde, men sees som *onboarding-hjelp*, ikke autoritativ sannhet
- **Eksplisitte planlagte koblinger** (`PlannedResponse`) er det som dokumenterer revisors faktiske beslutninger
- **Sync til Descartes** er énveis først (eksport av status), toveis vurderes senere når intern modell er stabil

Dette er ikke en nedprioritering av Descartes — det er en arkitektonisk beslutning om at intern modell må kunne stå på egne ben før ekstern sync gjøres autoritativ.

## Slice-rekkefølge

Foreslått inkrementell implementering. Hvert slice er leverbart isolert.

| Slice | Innhold | Forutsetter | Estimert størrelse |
|---|---|---|---|
| **A — Begrepslås** | Dette dokumentet committed; konsensus om de fem entitetene og navngivning | — | Drøfting + commit |
| **B — Modeller + lagring** | Dataclasses for de fem entitetene; repository-modul for hver; tester for round-trip; ingen GUI | A | Halv–hel dag |
| **C — Bibliotek-utvidelse** | Utvid `LocalAction` med nye felter; admin-GUI for redigering; populér med kjernebibliotek (innledende, klientinfo, vesentlighet, FRA, nærstående) | A | Halv dag |
| **D — Risikovurdering-fanen** | Utvid Scoping-fanen til å være Risikovurdering. Erstatt fritekst-`audit_action` med strukturerte `PlannedResponse`-koblinger. Vis dekningsmatrise per RL. | B + C | 1–2 dager |
| **E — Statusadapter for analyse** | Implementér `status_adapters/analyse.py`. Bruk i Risikovurdering- og Handlinger-fanen | B | 2–4 timer |
| **F — Statusadapter for utvalg, A07, AR** | En om gangen | B | 2–4 timer per fane |
| **G — Handlinger-fanen som kommandosenter** | Fasegruppering, sann status fra adaptere, navigasjon til utførelsesfaner | D + E + F | Halv dag |
| **H — Standardgenerator for arbeidspapir** | Excel-projeksjon med standard RL-mal | B | Halv dag |
| **I — Spesialgeneratorer** | FRA, estimater, nærstående, mislighet — én om gangen | H | 1–2 dager per generator |
| **J — Sync til Descartes (énveis)** | Eksporter status/dekning som CSV/JSON for opplasting | G | 2–4 timer |

Slice A–C er det som låser fundamentet. D er det første grepet som gir synlig verdi i UI. E–G bygger statusbroene. H–I leverer arbeidspapirene. J er valgfritt og senere.

## Hva dette dokumentet IKKE dekker

Eksplisitt utenfor scope nå:

- **Auto-anvendelse av standardrespons** (ResponseBundle): Mappingen «for denne risikoprofil-en, foreslå disse malene» tas opp etter at biblioteket er bygd ordentlig. Krever ikke modellendringer.
- **Versjonering av maler**: Slice 2 antar `versjon=1`. Versjonering legges til når behovet oppstår (revisjonsmetodikken endres og fjorårets dokumentasjon må fryses).
- **API-sync med Descartes**: Énveis eksport først; toveis vurderes senere.
- **Selvbetjent admin-GUI for `ResponseBundle`-redigering**: JSON-fil i repo først; admin-GUI hvis behov.
- **Tversgående analyse på tvers av klienter**: Krever sentral database. Ikke nødvendig før behov er dokumentert.
- **Auto-tagging av maler ut fra navn**: Manuell tagging i admin er pålitelig nok.

## Åpne spørsmål som krever beslutning før gjennomføring

**1. Tversgående analyse på tvers av klienter/år — på sikt nødvendig?**
- *Hvis ja*: Repository-laget må designes for å kunne flyttes til SQLite uten domeneendring. Krever litt mer arkitekturarbeid i slice B.
- *Hvis nei*: Klient/år-fil er enkleste løsning. Repository-laget kan være lett.

Anbefaling: bygg repository-laget med klar abstraksjon uansett. Det koster lite ekstra og holder døren åpen.

**2. Hvor mye skal speile Descartes 1:1?**
- *Speil 1:1*: Lett sync, men du arver Descartes' modell-begrensninger og må tilpasse hver gang Sticos endrer noe.
- *Egen modell + énveis sync*: Du eier modellen, men må skrive konvertering for sync.

Anbefaling: egen modell + énveis sync først. Toveis vurderes etter 6 måneder i drift.

**3. Skal Risikovurdering være ny fane eller utvidelse av Scoping?**
- *Ny fane*: Klar separasjon, men én fane til i et allerede stort fane-sett.
- *Utvid Scoping (rename til Risikovurdering)*: Mindre fane-rot, men endrer eksisterende brukers mentale modell.

Anbefaling: utvid Scoping. Datamodellen og koden er allerede der; UX-overgangen kan være progressiv.

**4. Hvor mye av kjernebiblioteket skal være forhåndsutfylt vs. brukerdefinert?**
- *Forhåndsutfylt*: Flere standard-maler i repo (10–30) basert på vanlig BHL-praksis. Mindre oppstart-friksjon.
- *Brukerdefinert*: Tomt bibliotek; bruker bygger selv. Maksimal fleksibilitet, men tregere oppstart.

Anbefaling: forhåndsutfylt med 10–15 sentrale maler (FRA, estimater, nærstående, vesentlighet, klientinfo, motpost, detaljkontroll, A07, MVA-avstemming, bankavstemming, …). Resten bygges over tid.

**5. Hvor «obligatorisk» skal `PlannedResponse.fase` være?**
- *Obligatorisk*: Hver planlagte handling må ha eksplisitt fase. Kvalitetssikrer at intet havner i feil del av flyten.
- *Default fra mal*: Mal bestemmer fase; revisor kan overstyre.

Anbefaling: default fra mal med mulighet for overstyring. Reduserer friksjon, beholder fleksibilitet.

## Beslutningsmoment

Dokumentet er klart for refleksjon. Kjernebeslutningen er om vi adopterer **fem-lags modellen** (Mal + Risiko + Planlagt handling + Utførelse + Evidens) som arkitektonisk fundament. Hvis ja, blir slice A (begrepslås + commit av denne fila) første konkrete steg. Resten av rekkefølgen følger av slice-tabellen over.

Hvis modellen revurderes, er det viktigste å avklare *hvorfor*: er det noe i revisjonsmetodikken denne ikke fanger? Er det noe i kodebasen den bryter med? Begge er gyldige grunner til å justere — og bedre å oppdage før implementering enn under.
