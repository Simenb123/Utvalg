# Mapping-konflikt-deteksjon — designnotat

## Status (per 2026-04-28)

Base-konfliktdeteksjon **levert og i bruk**. AR-utvidelse for
investerings-kontoer levert med live-justeringer fra første smoke-test.
UX-redesign av remap-dialogen og A1-kolonnen «Bokført på» i AR-fanen
levert i samme runde.

### Implementert

| Område | Commit |
|---|---|
| Splitt suggester for ytelse (`build_candidates` + `suggest_with_candidates`) | `45adbee` |
| Endring 1 — kjør suggester for alle kontoer | `1f5d99e` |
| Endring 2 — `has_suggestion_conflict`-property (threshold 0.7) | `1f5d99e` |
| Endring 3 — gul tag (`#FFF3CD`) på SB-tre-rader med konflikt | `be9d903` |
| Endring 4 — varsel + bytte-knapp i remap-dialog | `52040c1` |
| Encoding-fiks: «Hoy» → «Høy» i `_confidence_bucket` | `2f15eb2` |
| "Card"-stil for forslag (grønn match / gul konflikt) | `0f0c40a` |
| Full dialog-redesign — 640×460 resizable, robust bytt-knapp | `51c2a1b` |
| AR-utvidelse Step 1 — `OwnedCompany`, akronym-helper, score-bonus | `c3d90b9` |
| AR-utvidelse Step 2 — pipeline laster AR-data automatisk | `20d1549` |
| **Pakke 1** — undertrykk historikk når AR peker mot annen RL | `62e7f1d` |
| **Pakke 2** — dialog: listbokser med topp-5 forslag + søk + hotkeys | `8812341` |
| **Pakke 3** — A1 «Bokført på»-kolonne i AR-fanens «Eide selskaper»-tre | `3ae0e88` |
| Hotfix — bruk `get_client_ownership_overview` for videreført AR-data | `06f880d` |
| Perf — cache eide-selskaper (3-7 s overview-kall) + invalidate-hook | `093176b` |
| Bug-fix — 50 % nøyaktig er tilknyttet (575), ikke datter (560) | `5a9a32b` |

### Live-funn fra smoke-test (2026-04-28)

Tre regresjoner / bugs ble oppdaget under første kjøring på reell
klient og fikset samme dag:

1. **Historikk-overstyrte AR.** Konto «Aksjer i GPC» foreslo 575 (gammel
   feil-historikk) selv om AR sa 560 (datter, 83.51 %). Fix: undertrykk
   historikk-bonus når AR peker en annen vei. *Pakke 1 (`62e7f1d`).*
2. **AR-data lastet ikke.** `list_owned_companies` spør rå
   ownership_relations-tabellen, men «videreførte» eierandeler ligger
   i `accepted_owned_base`. Resultat: tomt owned_companies → AR-bonus
   fyrte aldri. Fix: bruk `get_client_ownership_overview` (samme kilde
   som AR-fanens tre). *Hotfix (`06f880d`).*
3. **App stallet.** `get_client_ownership_overview` er en 3-7 s
   operasjon, kalt 3+ ganger per refresh uten cache. Fix: cache per
   `(client, year)` med invalidate-hook. *Perf (`093176b`).*
4. **50 %-grensen feil.** `pct >= 50` regnet 50/50-eierskap som datter
   (560), men rskl. § 1-3 krever *over* 50 % for kontroll. Fix: bruk
   `pct > 50.0`. *Bug-fix (`5a9a32b`).*

### Ikke implementert (åpne punkter)

- **Endring 5** — `mapping_review.json` med «Marker som vurdert»-flagg.
  Konsekvens: konflikter flagges på nytt hver oppstart selv om revisor
  har vurdert dem. Avventes til vi har observert om støy faktisk er et
  problem.
- **Bulk-review-popup** «Gjennomgå mapping-forslag» — listevisning av
  alle konflikter for én klient.
- **A2 «Aksjespesifikasjon»-fane** — full gap-analyse: hvilke
  AR-eierandeler mangler bokføring (in AR, not in SB) og hvilke
  SB-investeringer mangler AR-binding (in SB, not in AR).
- **Bytt-til-forslag-knapp i konflikt-cardet.** Ble fjernet i Pakke 2
  redesign — listbox + dobbeltklikk dekker funksjonen, men
  hurtig-knappen kan være verdt å gjeninnføre hvis bruker savner den.

### Kjente uvisser som bør observeres videre

- **Threshold 0.7** — for lavt (støy) eller for høyt (savner konflikter)?
- **Konflikt-flagging på manuelle overrides** — ønsket eller bør
  undertrykkes? Etter Pakke 1-fixen er historikk-undertrykkelse
  asymmetrisk (AR slår historikk, men ikke omvendt) — ikke testet
  ennå om det gir falske positiver i praksis.
- **Falske positiver fra akronym-treff** — korte akronymer som GPC kan
  matche tilfeldig. Ingen rapportert ennå, men aktuell ved skalering.
- **Cache-invalideringspunkter** — vi invaliderer ved klientbytte og
  AR-import, men er det andre flyter som endrer eide selskaper og bør
  tømme cache?

## Plan videre

Anbefalt rekkefølge når brukeren vil fortsette:

1. **Lengre live-bruk på flere klienter.** Vi har bare smoke-testet på
   én klient (Air Management AS). Test på 2-3 klienter til for å se
   om threshold/akronymer holder generelt.
2. **«Marker som vurdert»** (Endring 5) hvis støy fra gjentakende
   konflikt-flagging blir et reelt problem.
3. **A2 «Aksjespesifikasjon»-fane** når base-deteksjonen er stabil —
   gir revisor en revisjons-handling som krysstester AR mot SB med gap-
   analyse i begge retninger.
4. **Bulk-review-popup** som videre utvikling av A2 — knapper for
   «Bytt valgte» / «Marker valgte som vurdert» på tvers av klient.

For konkret innsats-estimat, oppskrift, filer som skal endres og tips
til utvikleren som tar over: se [MAPPING_KONFLIKT_HANDOVER.md](MAPPING_KONFLIKT_HANDOVER.md).

## Bakgrunn

Saldobalanse-til-regnskapslinje-mapping i appen har tre lag:

1. **Intervall-mapping** (`regnskapslinjer.json`) — global, regelbasert via konto-områder
2. **Klient-overrides** (`account_overrides.json` per klient/år) — manuelle valg, vinner alltid
3. **Smart-suggester** (`regnskapslinje_suggest.py`) — alias-basert score-engine

Suggesteren brukes i dag **kun for problem-kontoer** (status `unmapped` eller
`sumline`), se `enrich_rl_mapping_issues_with_suggestions`. Det betyr at hvis
intervallet ga et svar — også hvis det er feil — kjører ingen kontroll mot
hva kontonavnet faktisk sier.

## Problemet — to konkrete eksempler

### 1. Overlappende intervaller

RL 560 «Investering i datterselskap» og RL 570 «Langsiktig lån til foretak i
samme konsern» har begge intervallet 1300-1369. Konto 1320 «Lån til datter AS»
treffes av begge i intervall-loggen. Hvilken som velges er deterministisk
(første match), men ikke nødvendigvis riktig.

### 2. Konto utenfor sitt naturlige intervall

Konto 1370 «Lån til datter AS» faller i intervallet til 591 «Andre langsiktige
fordringer». Mappes silent til 591, selv om kontonavnet sterkt signaliserer 570
(alias-treff: `lån`, `konsern`).

I begge tilfeller har suggester-engine-en informasjonen for å løfte konflikten
— men den blir aldri kjørt fordi statusen er `interval`, ikke `unmapped`.

## Foreslått løsning

### Endring 1 — kjør suggester også for `interval`-kontoer

Fjern `if not issue.is_problem: continue` fra
`enrich_rl_mapping_issues_with_suggestions`. Suggester kjører for **alle**
kontoer, og resultatet hektes på `RLMappingIssue` som
`suggested_regnr` osv.

### Endring 2 — beregn `has_suggestion_conflict`

Nytt felt på `RLMappingIssue`:

```python
@property
def has_suggestion_conflict(self) -> bool:
    if self.suggested_regnr is None:
        return False
    if self.suggestion_confidence is None or self.suggestion_confidence < 0.7:
        return False
    return self.suggested_regnr != self.regnr
```

Threshold på 0.7 unngår falske positiver fra svake forslag.

### Endring 3 — flagg i Saldobalanse + Analyse SB-tre

Tag rader med `has_suggestion_conflict = True` med en gul/oransje bakgrunn
eller en flagg-ikon i en ny "Forslag"-kolonne. Tooltip viser begge alternativene
med confidence og grunn.

### Endring 4 — vis konflikt i remap-dialogen

Når bruker åpner «Endre regnskapslinje for X»: hvis `has_suggestion_conflict`,
vis et lite varsel-panel med teksten

```
⚠ Forslag: 570 Langsiktig lån til foretak i samme konsern
   (95 % — alias: lån, konsern)
   Nåværende: 591 Andre langsiktige fordringer (intervall)

   [Bytt til 570]   [Behold 591]   [Marker som vurdert]
```

«Marker som vurdert» skriver et flagg til en sidekanal-fil
(`mapping_review.json` per klient/år) slik at konflikten ikke flagges igjen.

## Trygghet — eksisterende mappinger blir ikke endret

Konflikt-deteksjonen er ren read-only. Den leser eksisterende mapping og
sammenligner med suggesteren. Ingen automatisk write-back. Brukeren må
eksplisitt klikke for å endre.

## Innsats-estimat

| Endring | Linjer | Kompleksitet |
|---|---:|---|
| 1 — suggester for alle | ~3 | Trivielt |
| 2 — `has_suggestion_conflict` | ~10 | Lavt |
| 3 — UI-flagg | ~30 | Medium |
| 4 — konflikt-panel i dialog | ~50 | Medium |
| 5 — `mapping_review.json` lagring | ~30 | Medium |
| **Totalt** | **~120** | **2-3 timers økt** |

## Fremtidig utvidelse — bulk-review-popup

Når en klient er ferdig importert og mappet, kunne det vært nyttig med en
egen popup-dialog «**Gjennomgå mapping-forslag**» som lister ALLE konflikter
for klienten i én tabell:

```
┌─ Mapping-konflikter for Acme AS — 2025 ─────────────────────────────┐
│ Konto    Navn                  Nåværende      Forslag         Conf │
├─────────────────────────────────────────────────────────────────────┤
│ 1320     Aksjer i datter AS    570 Lån        560 Aksjer        92 %│
│ 1370     Lån til datter AS     591 Andre…     570 Konsernlån    95 %│
│ 1500     Kundefordringer       615 Andre…     610 Kundefordr.   88 %│
│ ...                                                                  │
└─────────────────────────────────────────────────────────────────────┘
[Bytt valgte (3)]  [Marker valgte som vurdert]  [Lukk]
```

Lar revisor gå gjennom hele listen i én sleng etter import, ikke kontot for
konto. Spesielt nyttig for nye klienter.

Lagres som ide for senere — implementeres etter at base-konfliktdeteksjonen
(endring 1-5 over) er på plass og brukt en stund.

## Utvidelse — AR-basert akronym-bonus (commit c3d90b9 + 20d1549)

For kontoer som representerer eierandeler i andre selskaper (typisk
1320-1389), er kontonavnet ofte en **forkortelse** av selskapet. Eksempel:

```
Konto 1321 «Aksjer i GPC»
```

Uten ekstra signal mapper suggesteren typisk feil — det finnes ingen alias
for «GPC». Men hvis klienten eier et selskap kalt
«Gardermoen Perishable Center AS» i AR (aksjonærregisteret), kan vi:

1. Bygge akronymet `GPC` av selskapsnavnet (skipper selskapsformer som AS,
   ASA og småord som «og», «for», …).
2. Sjekke om kontonavnet inneholder fullt navn eller akronym (case-
   insensitive).
3. Gi sterk score-bonus mot riktig RL basert på eierskaps­andel:
   - **≥ 50 %** → RL **560** (Investering i datterselskap)
   - **20-50 %** → RL **575** (Investering i tilknyttet selskap)
   - **< 20 %** → RL **585** (Investeringer i aksjer og andeler)

### Implementasjon

- `regnskapslinje_suggest.OwnedCompany` — dataklasse (navn, akronym, %, regnr)
- `regnskapslinje_suggest.company_acronym(name)` — bygger forkortelse
- `regnskapslinje_suggest.ownership_pct_to_regnr(pct)` — % → regnr
- `_load_owned_companies_for_client(client, year)` i
  `regnskapslinje_mapping_service.py` — laster AR-data automatisk i
  pipeline-callerne (`build_page_admin_rl_rows`,
  `build_page_rl_mapping_issues`).
- Bonus i suggesterens score: fullt navn-treff = **+0.45**, akronym-treff
  = **+0.30**.

### Effekt på konflikt-deteksjonen

AR-bonusen gir suggesteren høy confidence (typisk > 0.85) på
investerings-kontoer der intervallet ellers ville plassert dem
generelt (f.eks. 591). Med `has_suggestion_conflict`-flagget løftes da
konflikten umiddelbart i SB-treet og remap-dialogen.

## Referanser

- [regnskapslinje_suggest.py](../regnskapslinje_suggest.py) — score-engine, `OwnedCompany`, akronym-helper
- [regnskapslinje_mapping_service.py](../regnskapslinje_mapping_service.py) — issue-bygging, override-prioritering, `_load_owned_companies_for_client`
- [src/pages/ar/backend/store.py](../src/pages/ar/backend/store.py) — AR-store med `list_owned_companies` og `get_client_orgnr`
- [analyse_sb_remap.py](../analyse_sb_remap.py) — høyreklikk-meny og remap-dialog-bridging
- [views_rl_account_drill.py](../views_rl_account_drill.py) — selve remap-dialogen
