# Mapping-konflikt-deteksjon — handover

Dette dokumentet beskriver de **tre gjenstående arbeids­pakkene** etter
runden 28.04.2026, slik at noen andre kan plukke opp arbeidet.

For full historikk og design­bakgrunn: se
[MAPPING_KONFLIKT_DETEKSJON.md](MAPPING_KONFLIKT_DETEKSJON.md).

## Forutsetning før du starter

Før du bygger noen av pakkene under, **bruk det vi har levert i 1-2 uker**
på 2-3 reelle klienter. Vi har bare smoke-testet på Air Management AS,
og det er smart å se hva som dukker opp i praksis (falske positiver,
threshold-justeringer, akronym-kollisjoner) før vi bygger videre.

Når du har observasjoner, kommer det tydelig frem hvilken pakke som er
mest verdt å starte med.

---

## Pakke A — «Marker som vurdert»-flagg

**Innsats:** ~150-200 linjer + tester · 4-6 timer · 1 commit

### Hvorfor

I dag flagges samme konflikt på nytt hver oppstart selv om revisor har
vurdert den. Det skaper varselstøy. Vi trenger et persistert «sett til
side»-flagg per (klient, år, konto).

### Hva som skal bygges

1. Ny JSON-fil per klient/år: `mapping_review.json` med formen
   ```json
   {"client": "ACME AS", "year": 2025, "reviewed": {"1321": "560 -> 575 (vurdert 2026-04-28)"}}
   ```
   Lagres samme sted som `account_overrides.json` (samme klient-store-
   pattern).

2. Load/save-funksjoner i en ny modul `mapping_review_store.py` (ev.
   som modul under `src/shared/regnskap/`):
   - `load_reviewed(client, year) -> dict[konto, str]`
   - `mark_reviewed(client, year, konto, note)`
   - `clear_reviewed(client, year, konto=None)`

3. Modifiser `RLMappingIssue.has_suggestion_conflict` (eller en ny
   property `should_flag_conflict`) til å også sjekke om kontoen er
   markert som vurdert. Reviewed → returner False.

4. UI: legg til knapp **«Marker som vurdert»** i remap-dialog
   ([views_rl_account_drill.py](../views_rl_account_drill.py)) ved siden av
   «Lagre» og «Avbryt». Knappen lagrer flagg + lukker dialog +
   trigger refresh slik at gulfargingen forsvinner.

5. UI: legg til en lite-knapp i konflikt-cardet «Lukk varsel» som
   gjør det samme uten å åpne lagre-flyten.

### Filer som berøres

- `regnskapslinje_mapping_service.py` (utvide RLMappingIssue / pipeline)
- `views_rl_account_drill.py` (knapp i dialog)
- `analyse_sb_refresh.py` (sjekk reviewed-flagg når tags settes)
- Ny: `mapping_review_store.py` eller tilsvarende
- Ny tester: `tests/test_mapping_review_store.py` + utvidet
  `tests/test_regnskapslinje_mapping_service.py`

### Edge-cases du må tenke på

- Hva skjer hvis bruker **endrer** mapping etter å ha markert som
  vurdert? Bør flagget fjernes automatisk slik at neste konflikt vises?
  (Anbefaling: ja, clear ved override-endring.)
- Hva med **historikk-import** fra forrige år? Skal reviewed-flagg
  videreføres? (Anbefaling: nei, hver år er sin egen vurdering.)
- Plassering for «Vis tidligere markert som vurdert» — trengs det?
  (Anbefaling: dropp i første runde, legg til hvis bruker spør.)

---

## Pakke B — Bulk-review-popup

**Innsats:** ~250-350 linjer + tester · 6-10 timer · 1-2 commits
**Avhengighet:** Pakke A bør være ferdig først (popupen drar nytte av
«marker som vurdert» som batch-handling).

### Hvorfor

Klikke seg gjennom konfliktene én og én er tregt. Med 50+ konti per
klient og kanskje 5-10 mapping-konflikter trenger revisor en
oversiktsvisning som tar dem alle på én gang.

### Hva som skal bygges

Et nytt vindu (popup) som åpnes via en knapp i Analyse-fanens
verktøylinje, f.eks. **«Gjennomgå mapping-forslag (n)»** der `n` er
antall konflikter for klienten.

Layout (skisse):

```
┌─ Mapping-konflikter for ACME AS — 2025 ─────────────────────────────┐
│ Filter: [_______________]  Sorter: [Konfidens ▾]                     │
├──────────────────────────────────────────────────────────────────────┤
│ □  Konto   Navn                Nåværende   Forslag        Conf  Kilde│
├──────────────────────────────────────────────────────────────────────┤
│ □  1321    Aksjer i GPC        575 Tilkn. 560 Datter      94%  AR    │
│ □  1370    Lån til datter AS   591 Andre  570 Konsernlån  88%  alias │
│ □  1500    Kundefordringer     615 Andre  610 Kundefordr. 85%  alias │
│ ...                                                                   │
├──────────────────────────────────────────────────────────────────────┤
│ [Bytt valgte (3)]  [Marker valgte som vurdert]  [Lukk]               │
└──────────────────────────────────────────────────────────────────────┘
```

### Filer som berøres

- Ny: `views_mapping_conflict_review.py` (eget popup-vindu)
- `page_analyse_ui_toolbar.py` (legg til knapp som åpner popup)
- `regnskapslinje_mapping_service.py` (helper for å hente alle
  konflikter for klient/år)
- Ny tester: `tests/test_views_mapping_conflict_review.py`

### Hva som er gjenbruksbart

- Score- og forslag-pipelinen er allerede der (`build_page_rl_mapping_issues`
  returnerer alle issues — bare filtrer på `has_suggestion_conflict`).
- `RLAccountDrillDialog` (i `views_rl_account_drill.py`) viser hvordan
  man bygger en konto-tabell med Treeview — samme mønster.
- `set_account_override` og `mark_reviewed` (fra Pakke A) — bulk-versjon
  er bare en for-loop.

### Edge-cases

- Hva hvis bruker velger «Bytt valgte» og noen feiler? Vis hvilke som
  ble vellykket, hvilke som feilet, slik at de kan rettes manuelt.
- Hva hvis konflikt-listen endrer seg mens popupen er åpen? (En annen
  refresh trigger). Anbefaling: vis varsel «Listen er oppdatert,
  laster på nytt» og oppfrisk.

---

## Pakke C — A2 «Aksjespesifikasjon»-fane

**Innsats:** ~300-400 linjer + tester · 8-12 timer · 2-3 commits

### Hvorfor

I dag binder vi AR-eierandeler til SB-kontoer manuelt via SB-fanens
«Eid selskap»-kolonne. Bindingen vises i AR-fanens «Bokført på»-
kolonne (Pakke 3). Men en revisor trenger en **gap-analyse**:

- Eier klienten et selskap som **ikke** er bokført? → potensielt
  manglende investerings-konto
- Har klienten en investerings-konto (560/575/585) som **ikke** er
  bundet til en AR-eierandel? → potensielt utgått eller manglende
  AR-import

### Hva som skal bygges

Ny fane (eller subfane under AR) med tre seksjoner:

```
┌─ Aksjespesifikasjon — ACME AS, 2025 ───────────────────────────────┐
│                                                                     │
│ ✓ OK (5)                                                            │
│   Selskap                Org.nr     %     RL   Konto   UB           │
│   AIR CARGO LOGISTICS   914305195  100%  560  1310    500 000      │
│   ...                                                                │
│                                                                     │
│ ⚠ Mangler bokføring (2)                                             │
│   Selskap                Org.nr     %     Forventet RL              │
│   LIVE SEAFOOD CENTER   918038035  50%   575 Tilknyttet            │
│   ...                                                                │
│                                                                     │
│ ⚠ Bokført uten AR-match (1)                                         │
│   Konto    Kontonavn               Regnskapslinje    UB             │
│   1325     Aksjer Tigerdivisjonen   560 Datter       2 000 000      │
└─────────────────────────────────────────────────────────────────────┘
```

### Filer som berøres

- Ny: `src/pages/ar/frontend/aksjespesifikasjon_tab.py` (eller subfane
  i `page.py`)
- Ny: `src/pages/ar/backend/share_specification.py` med
  ```python
  def build_share_specification(
      client: str, year: int
  ) -> dict[str, list[dict]]
  # → {"ok": [...], "mangler_bokforing": [...], "bokfort_uten_ar": [...]}
  ```
- Tester: `tests/test_share_specification.py`

### Logikk per seksjon

1. **OK:** AR-rad har `AccountProfile.owned_company_orgnr`-treff i
   SB **og** SB-konto er på riktig RL (basert på eierskap).
2. **Mangler bokføring:** AR-rad har **ikke** binding til noen
   SB-konto. Foreslå forventet RL (560/575/585) basert på `%`.
3. **Bokført uten AR-match:** SB-konto er på 560/575/585 men
   `AccountProfile.owned_company_orgnr` er tom (eller peker på orgnr
   som ikke finnes i AR). To underkasus:
   - Helt uten binding → revisor må binde manuelt
   - Binding til orgnr som ikke er i AR → utgått eierandel som er solgt
     men kontoen ikke er nullet ut (revisjons­handling)

### Hva som er gjenbruksbart

- AR-data: `get_client_ownership_overview` (cachet)
- AccountProfile-bindinger: nettopp bygget i [account_bindings.py](../src/pages/ar/backend/account_bindings.py)
  (Pakke 3) — utvid med reverse-direction (orgnr → konto-liste finnes
  allerede; trenger også konto → orgnr-map)
- SB-data: `_load_account_profile_document_only` i
  saldobalanse-payload
- Ownership-pct → RL: `regnskapslinje_suggest.ownership_pct_to_regnr`

### Edge-cases

- Hva med selskapet klienten *eier* andelen av seg selv (egne aksjer)?
  Skal det med? (Sannsynligvis ikke — sjekk `AR-store._split_self_relations`)
- Hva hvis SB-kontoen er pålydende 0? Skal den med under «bokført uten
  AR-match»? (Anbefaling: ja, men sorter sist — kan være fjorårets
  saldo som er tilbakeført.)

---

## Andre småting i kø

### D — Bytt-til-forslag-knapp i konflikt-cardet

Vi fjernet knappen i Pakke 2 (`8812341`) fordi listbox + dobbeltklikk
gjør samme jobben. Men hvis bruker savner hurtig-knappen, gjenintroduser
den i konflikt-cardet ved siden av varsel-teksten. ~20 linjer.

### E — Threshold-justering basert på live-bruk

Currently `has_suggestion_conflict` krever `confidence >= 0.7`. Hvis
det viser seg at 0.7 er for lavt (støy) eller for høyt (savner ekte
konflikter), juster i `regnskapslinje_mapping_service.RLMappingIssue`.
Trivielt — én linje.

### F — Akronym-kollisjon-fix

Korte akronymer (2 bokstaver) kan matche tilfeldig — f.eks. «GP» kan
finnes i mange kontonavn. Hvis vi ser falske positiver, øk min-lengde
til 3 i `_owned_company_match` ([regnskapslinje_suggest.py](../regnskapslinje_suggest.py)
linje 433):

```python
if company.acronym and len(company.acronym) >= 3:
```

---

## Totalt estimat

| Pakke | Linjer | Timer | Commits |
|---|---:|---:|---:|
| A — Marker som vurdert | 150-200 | 4-6 | 1 |
| B — Bulk-review-popup | 250-350 | 6-10 | 1-2 |
| C — A2 Aksjespesifikasjon | 300-400 | 8-12 | 2-3 |
| D-F — småjusteringer | 30-50 | 1-2 | 1 |
| **Totalt** | **~750-1000** | **~20-30** | **5-7** |

## Tips til utvikleren som tar over

1. **Les eksisterende kode først.** Mønstrene for klient-store, JSON-
   persistens, og Tk-popup er etablerte:
   - Klient-store: [src/shared/client_store/](../src/shared/client_store/)
   - JSON-persistens med versjonering: [src/shared/regnskap/client_overrides.py](../src/shared/regnskap/client_overrides.py)
   - Popup-vindu: [views_rl_account_drill.py:RLAccountDrillDialog](../views_rl_account_drill.py)

2. **Husk cache-invalidering.** Ved endringer i AR-data eller
   AccountProfile, kall:
   - `regnskapslinje_mapping_service.invalidate_owned_companies_cache(client)`
   - `saldobalanse_payload._invalidate_owned_company_cache(client)`

3. **Test først, bygg etter.** Pipelinen i `regnskapslinje_suggest.py`
   er testbar uten Tk. Bygg gap-analyse og marker-som-vurdert som rene
   funksjoner i backend først, så koble UI på.

4. **Følg eksisterende commit-stil.** Sjekk `git log --oneline -20` —
   prefiks `feat()`, `fix()`, `perf()`, `docs()` med scope, kort
   beskrivelse, deretter detaljer i body. Co-author-tag hvis brukt
   med assistent.

5. **Varsko brukeren mellom hver pakke.** Ikke kjør alle 3 pakkene
   uten å verifisere mellom — runden 28.04 viste at live-bruk
   surfacer bugs som unit-tester ikke fanger.

## Referanser

- [MAPPING_KONFLIKT_DETEKSJON.md](MAPPING_KONFLIKT_DETEKSJON.md) — full design og status
- [regnskapslinje_suggest.py](../regnskapslinje_suggest.py) — score-engine, akronym-helper
- [regnskapslinje_mapping_service.py](../regnskapslinje_mapping_service.py) — pipeline
- [views_rl_account_drill.py](../views_rl_account_drill.py) — remap-dialog
- [src/pages/ar/backend/account_bindings.py](../src/pages/ar/backend/account_bindings.py) — orgnr → konto-binding
- [src/pages/ar/frontend/page.py](../src/pages/ar/frontend/page.py) — AR-fanens UI
