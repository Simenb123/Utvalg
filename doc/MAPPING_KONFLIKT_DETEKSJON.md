# Mapping-konflikt-deteksjon — designnotat

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

## Referanser

- [regnskapslinje_suggest.py](../regnskapslinje_suggest.py) — score-engine
- [regnskapslinje_mapping_service.py](../regnskapslinje_mapping_service.py) — issue-bygging og override-prioritering
- [analyse_sb_remap.py](../analyse_sb_remap.py) — høyreklikk-meny og remap-dialog-bridging
- [views_rl_account_drill.py](../views_rl_account_drill.py) — selve remap-dialogen
