# Utvalg-fanen — status quo og ideer til forbedret visning og funksjonalitet

Dette dokumentet er en kartlegging av Utvalg-fanen («Selection Studio») slik
den er i dag, samt en samling av forslag til forbedret brukerflyt, mer
oversiktlig visning og mer interaktivt arbeid med utvalg.

Ingenting her er besluttet — det er et grunnlag for drøfting og prioritering
før vi setter i gang. Vi tar opp tråden senere.

---

## Status quo

### Arkitektur og kodemoduler

Utvalg-fanen er bygget rundt komponenten `SelectionStudio`, som ligger
spredt over 16 filer. Page-laget er bare et tynt skall:

| Lag | Fil | Rolle |
|---|---|---|
| Page (aktiv) | [page_utvalg_strata.py](../page_utvalg_strata.py) | `UtvalgStrataPage` — wrapper som mottar kontoer fra Analyse via `load_population(accounts)` og laster Studio |
| Page (legacy) | [page_utvalg.py](../page_utvalg.py) | `UtvalgPage` — eldre «Resultat»-fane, ikke lenger lagt til notebook |
| View-klasse | [views_selection_studio_ui.py](../views_selection_studio_ui.py) | `SelectionStudio` (Tk-klasse). Eier kun state-vars og delegerer hvert kall til `selection_studio.ui_widget_*` |
| UI-bygger | [selection_studio/ui_builder.py](../selection_studio/ui_builder.py) | Bygger Tk-widgets (Filtre / Utvalg / Beregning / knapper / tre-er) |
| UI-handlere | [selection_studio/ui_widget_filters.py](../selection_studio/ui_widget_filters.py) | Retning, beløpsfilter, custom strata-grenser |
| | [selection_studio/ui_widget_refresh.py](../selection_studio/ui_widget_refresh.py) | Debouncet refresh, anbefaling, materialitet, populasjons-summary |
| | [selection_studio/ui_widget_selection.py](../selection_studio/ui_widget_selection.py) | `_run_selection`: spesifikk + stratifisert trekning |
| | [selection_studio/ui_widget_actions.py](../selection_studio/ui_widget_actions.py) | Knappe-handlere: commit, export, drilldown, dokumentkontroll |
| Tk-fri matematikk | [selection_studio/ui_logic.py](../selection_studio/ui_logic.py) | Konfidens, stratifisering, parsing |
| | [selection_studio/helpers.py](../selection_studio/helpers.py) | Populasjonsmetrikker, formatering, anbefaling |
| | [selection_studio/bilag.py](../selection_studio/bilag.py) | Bilag-DataFrame, stratify_bilag_sums |
| | [selection_studio/specific.py](../selection_studio/specific.py) | Spesifikk utvelgelse |
| | [selection_studio/filters.py](../selection_studio/filters.py) | `filter_selectionstudio_dataframe` |
| | [selection_studio/adapters.py](../selection_studio/adapters.py) | Formaterings-adaptere |
| | [selection_studio/drill.py](../selection_studio/drill.py) | Bilag-drilldown-dialog |

`utvalgsgenerator.py` ble slettet som dead code (ingen konsumenter).
`utvalg_excel_report.py` er flyttet til `src/pages/utvalg/backend/excel_report.py`.

### Dataflyten inn til fanen

1. Analyse-fanen sender kontoer via `bus.emit("SELECTION_SET_ACCOUNTS", {"accounts": [...]})`
2. [bus.py](../bus.py) oppdaterer `session.SELECTION["accounts"]`
3. Henter `session.UTVALG_STRATA_PAGE` (registrert i [ui_main.py](../ui_main.py)) og kaller `load_population(accounts)`
4. Bytter til Utvalg-fanen via `nb.select(...)`

Studio mottar **kun en liste med kontonumre** — ikke regnskapslinjen som
ligger til grunn for utvalget. Hele «hvilken RL jobber jeg med»-konteksten
finnes ikke i Studio sin state.

### Dataflyten ut av fanen

Når brukeren trykker «Legg i utvalg» kalles `commit_selection`, som videre
kaller `UtvalgStrataPage._on_commit_selection`. Den ekspanderer bilag-sample
til transaksjonsrader og sender til `App._on_utvalg_commit_sample`.

### Dagens layout

```
┌─ Topplinje ───────────────────────────────────────────────────────┐
│ Grunnlag: 950 rader | 337 bilag | 40 kontoer                      │  ← Antall rå tx
│ Etter filter: 950 rader | 337 bilag | 40 kontoer                  │  ← Etter beløp/retning
│ Sum (netto): 3 168 082,59  |  Abs: 5 650 597,53                   │
└──────────────────────────────────────────────────────────────────┘
┌─ Filtre ────────────┬─ Notebook ─────────────────────────────────┐
│ Retning: ☐debet ☐kr │ [Utvalg]  [Grupper]                        │
│ Beløp fra/til       │                                            │
├─ Utvalg ────────────┤  [Last opp bilag…]  [Vis kontorer]         │
│ Risiko, Sikkerhet   │  [Drilldown]  [Dokumentkontroll]           │
│ Tolererbar feil     │  [Massekjøring…]                           │
│ Aktiv terskel       │                                            │
│ Metode/k/n          │  Bilag | Dato | Tekst | SumBeløp | …       │
├─ Beregning ─────────┤  (tom inntil "Kjør utvalg")                │
│ Tolererbar / KF /   │                                            │
│ Forslag             │                                            │
│ Populasjon/spes/    │                                            │
│ rest                │                                            │
├─ Knapper ───────────┤                                            │
│ [Kjør utvalg]       │                                            │
│ [Legg i utvalg]     │                                            │
│ [Eksporter Excel]   │                                            │
└─────────────────────┴────────────────────────────────────────────┘
```

### Den matematiske beregningen

#### Trinn 1 — Spesifikk utvelgelse (alltid med)

I [ui_logic.py:299-346](../selection_studio/ui_logic.py#L299-L346):

```
For hvert bilag:
    hvis |SumBeløp| ≥ tolererbar feil → spesifikt utvalg (alltid med)
    ellers                            → restpopulasjon
```

Hvis `tolererbar feil = 0`: spesifikk-listen blir tom, alt blir rest.

#### Trinn 2 — Konfidensfaktor (Eilifsen et al. tabell 17.1)

| Risiko ↓ / Sikkerhet → | 80 % (lav) | 90 % (middels) | 95 % (høy) |
|---|---|---|---|
| **Lav** | 1.0 | 1.2 | 2.0 |
| **Middels** | 1.2 | 1.6 | 2.3 |
| **Høy** | 2.0 | 2.3 | 3.0 |

#### Trinn 3 — Anbefalt antall i tilfeldig trekk

I [ui_logic.py:576-622](../selection_studio/ui_logic.py#L576-L622):

```
n_random = ⌈ (|netto-sum av rest| / tolererbar feil) × konfidensfaktor ⌉
```

Klampet til [1, antall_bilag_i_rest]. Returnerer 0 hvis grunnlag mangler.

To viktige antakelser:
- Det brukes **netto** (signert) sum, ikke abs-sum. Hvis netto er 0
  (debet/kredit netter ut), foreslås 0 i tilfeldig trekk — selv om det
  åpenbart er aktivitet å revidere.
- Restpopulasjonen er bilag-nivå.

#### Trinn 4 — Trekningen

I [ui_widget_selection.py:33-120](../selection_studio/ui_widget_selection.py#L33-L120):

1. Spesifikke bilag legges alltid inn først
2. `n_random` bilag trekkes **stratifisert** fra restpopulasjonen via
   `quantile`/`equal_width`/`custom` (k antall grupper du velger)
3. Allokering per stratum er **proporsjonal med antall bilag**, ikke beløp:
   `n_per_stratum = round(n_random × stratum_størrelse / total_rest_størrelse)`
4. Innenfor hvert stratum: **uniform tilfeldig** trekning med seed = 42
   (deterministisk — samme datasett gir samme utvalg)

#### Trinn 5 — Total

```
desired_total = max(brukervalg eller anbefalt, antall_spesifikke)
n_random_faktisk = desired_total − antall_spesifikke
```

### Sperrer som finnes i dag — det er nesten ingen

#### Antall i utvalg (`var_sample_n`)

| Sperre | Hva som skjer |
|---|---|
| Spinbox-grenser | from_=0, to=99 999 (i [ui_builder.py:113](../selection_studio/ui_builder.py#L113)) |
| 0 = auto | Bruker anbefalingen automatisk |
| Aldri lavere enn spesifikke | `max(desired, n_specific)` |
| Større enn populasjonen | Bare warning-dialog, programmet trekker så mange som finnes |
| Negative tall | Ingen guard — spinbox-min er 0 |

Ingen øvre profesjonell grense som «maks 60 bilag».

#### Tolererbar feil (`var_tolerable_error`)

| Sperre | Hva som skjer |
|---|---|
| Default ved tom verdi | 5 % av netto populasjonsverdi (eller 5 % av abs-sum hvis netto ≈ 0) |
| Materialitetspåfyll | Hentes automatisk fra Vesentlighet-fanen via `set_materiality_context` |
| Negative verdier | Tas `abs()` av — ingen feilmelding |
| 0 / tom | Spesifikt utvalg blir tomt + tilfeldig trekning returnerer 0 |
| Urealistisk høy verdi | Ingen sperre — anbefalt antall blir trolig 1 |
| Urealistisk lav verdi | Ingen sperre — spesifikt utvalg blir hele populasjonen |

#### Andre felt uten validering

- **Min/max beløp**: tekstfelt, ingen min/max-sjekk og ingen sjekk på at min ≤ max
- **Risiko / Sikkerhet**: combobox `state="readonly"` (begrenset til de tre verdiene)
- **k (antall strata)**: Spinbox 1–12

---

## Hva fungerer / hva mangler

| Område | I dag | Mangler / problem |
|---|---|---|
| **Hva er valgt?** | Bare antall rader / bilag / kontoer i toppen — ingen referanse til regnskapslinje | Ingen visuell kontekst om at «du jobber på RL 30 Salgsinntekt». Brukeren må huske hva som ble valgt i Analyse |
| **Velge kilde fra Studio** | Nei — populasjonen kommer kun fra Analyse-fanen via bus + `session.SELECTION["accounts"]` | Kan ikke velge RL/konti direkte i Studio. Må alltid hoppe innom Analyse først |
| **Filtrer ut enkeltkontoer** | Ingen UI — alle kontoer som ble sendt fra Analyse er med | Hvis du sendte 40 kontoer, må du tilbake til Analyse for å unmark én |
| **Konto-oversikt** | Knapp «Vis kontorer» åpner et eget vindu med Konto/Navn/Rader/Bilag/Sum | Eget vindu — er ute av flyten. Ingen mulighet til å unmark direkte |
| **Beskrivende statistikk** | Bare net/abs-sum øverst. Ingen IB/UB, ingen fjorår, ingen konsentrasjon, ingen månedsfordeling | Statistikk-fanen ([src/audit_actions/statistikk/frontend/page.py](../src/audit_actions/statistikk/frontend/page.py)) har dette ferdig |
| **Materialitet** | Vises som «Aktiv terskel: Arbeidsvesentlighet (PM)» + lokal beregning + lov til å overstyre | OK i dag |
| **Filtre** | Retning (debet/kredit) og beløp fra/til | Ingen dato/periode. Ingen MVA-kode. Ingen kunde/leverandør. Ingen fritekst-søk |
| **Resultatvisning** | Tom inntil «Kjør utvalg» trykkes | Kunne vist populasjonen «live» og latt brukeren se trekket bygges. Ingen markering av spesifikke vs tilfeldige rader |
| **Grupper-fanen** | Liste over strata med antall + sum | OK, men ikke koblet visuelt til hvilke bilag som havner i hvilken gruppe |
| **Netto-grunnlag** | Anbefalingen bruker netto sum av restpopulasjonen | Mellomregningskontoer som netter ut gir n_random = 0 selv om det er aktivitet — samme problem som RL 610 i Analyse-fanen |

---

## Komponenter som kan gjenbrukes

Disse er Tk-frie og testet — kan plukkes inn direkte hvis vi velger å bygge ut:

| Hva | Hvor | Hva det gir |
|---|---|---|
| `compute_kontoer` | [src/audit_actions/statistikk/backend/compute.py:300](../src/audit_actions/statistikk/backend/compute.py#L300) | Konto-tabell med Konto, Kontonavn, IB, Bevegelse, UB, Antall — også konti uten bevegelse |
| `_compute_extra_stats` | [compute.py:432](../src/audit_actions/statistikk/backend/compute.py#L432) | Topp 10-konsentrasjon, unike kunder, anomale måneder, runde beløp |
| `_compute_maned_pivot` | [compute.py:480](../src/audit_actions/statistikk/backend/compute.py#L480) | Pivot per måned med sum |
| `_compute_bilag` | [compute.py:504](../src/audit_actions/statistikk/backend/compute.py#L504) | Bilag-aggregat med Sum / Antall poster / Kontoer |
| `get_konto_ranges` + `get_konto_set_for_regnr` | [compute.py:79](../src/audit_actions/statistikk/backend/compute.py#L79) | Override-bevisst RL → konto-set |
| `compute_population_metrics` | [selection_studio/helpers.py:304](../selection_studio/helpers.py#L304) | rows / bilag / konto / sum_net / sum_abs |
| `RLMappingContext` + `resolve_accounts_to_rl` | [regnskapslinje_mapping_service.py](../regnskapslinje_mapping_service.py) | Konto → RL-mapping inkl. overrides |

---

## Forslag — én ny layout

Sentral idé: **én sentral kontekst (regnskapslinjen)** og **tre-kolonnes layout**.

```
┌─ KONTEKST-BANNER ─────────────────────────────────────────────────┐
│ Regnskapslinje: [10 Salgsinntekt ▼]   Klient: Spor AS — 2025      │
│                                                       [Bytt RL…]  │
│ UB: 3 168 083  |  UB 2024: 2 950 000  |  Endring: +218 k (+7,4%) │  ← KPI-banner
│ 337 bilag  |  40 kontoer  |  950 transaksjoner                    │
└──────────────────────────────────────────────────────────────────┘
┌─ Venstre 30% ───────────┬─ Midtre 35% ───────────┬─ Høyre 35% ──┐
│ KONTI                   │ FILTRE & UTVALG        │ POPULASJON   │
│ ☑ 3000 Salg             │ Retning, beløp, dato,  │ Live tabell  │
│ ☑ 3010 Salg avg.fri     │ MVA-kode, tekst…       │ med:         │
│ ☐ 3050 Periodisering    │                        │ - alle bilag │
│ ☐ 3060 …                │ Risiko/sikkerhet/      │ - tag for    │
│ (klikk for å exclude)   │ tolererbar feil        │   spesifikk  │
│                         │                        │ - tag for    │
│ Sum valgt: 3 050 000    │ [Anbefalt utvalg: 29]  │   trukket    │
│                         │ Brukervalg: [29]       │              │
│ TOPP 10 BILAG           │ Metode/k                │ Søylediagr.: │
│ Konsentrasjon: 64%      │ [Kjør utvalg]          │ måned/sum    │
│ Anomale måneder: 2      │ [Legg i utvalg]        │              │
│ Runde beløp: 18%        │ [Eksporter…]           │              │
└──────────────────────────┴─────────────────────────┴───────────────┘
```

### Hva det løser

| Ønske | Løsning |
|---|---|
| **Tydelig hvilken RL** | Banner øverst med RL-navn + KPI. RL-velger som dropdown så man kan bytte rett her uten å gå til Analyse |
| **Velge RL fra Studio** | Dropdown «Bytt RL…» laster `_rl_regnskapslinjer` + bygger konto-set via `get_konto_set_for_regnr` |
| **Deskriptiv statistikk** | KPI-banner gjenbruker `_compute_extra_stats`. Statistikk-tabben legges som en av tabbene i høyre panel (eller som en egen «Statistikk»-tab) |
| **Filtrer bort enkeltkontoer** | Konto-listen til venstre med checkbokser. Når du fjerner en hake oppdateres populasjon + KPI live (debouncet). Kontoene kan aldri «forsvinne», bare ekskluderes |
| **Bedre flyt** | Live populasjon i høyre panel — ser hva man jobber med før trekket. Fjerner «Kjør utvalg-så-er-det-tomt»-overraskelsen |
| **Mer interaktivt** | Konto-checklist + filtre er live. Tagging i populasjonstabellen (spesifikk vs trekkbar vs trukket) gjør utvalget visuelt forståelig |

---

## Mulig implementasjon i 5 inkrementelle steg

Hvis vi går videre: dette kan gjøres inkrementelt så vi ikke knekker dagens
fungerende flyt. Hvert steg kan committes separat og testes i isolasjon.

1. **RL-kontekst inn i Studio** — la `UtvalgStrataPage` motta `regnr` i tillegg til `accounts`. Lagre `current_regnr`/`current_rl_name` i Studio. Vis bannerlinje øverst.
2. **KPI-banner** — Bruk `_compute_extra_stats` + UB/IB fra `compute_kontoer`. Renderer som tilsvarende widget i Statistikk-fanen.
3. **Konto-checklist til venstre** — Erstatt nåværende «Filtre»-frame med en konto-liste (built fra `compute_kontoer`). Hver konto har checkbox + viser Sum/Antall. Toggling driver `apply_filters`.
4. **«Bytt RL»-dropdown** — Last RL-liste fra `regnskap_config`, lar brukeren bytte uten å gå tilbake til Analyse.
5. **Live populasjons-tabell + tagging** — Vis hele populasjonen i høyre panel (virtualisert), med tags `spesifikk`, `trukket`, `ekskludert`.

---

## Åpne spørsmål til drøfting

Disse må vi ta stilling til før vi implementerer:

1. **Skal Studio kunne brukes uavhengig av Analyse-fanen?** Hvis ja: vi
   trenger en RL-velger i Studio, og bus-flyten må kunne snus (Studio
   sender RL → Analyse, ikke bare omvendt).
2. **Hva er kanonisk sannhet for «valgt RL»?** I dag er det implisitt via
   `session.SELECTION["accounts"]`. Skal vi innføre `session.SELECTION["regnr"]`?
3. **Hvor mye av Statistikk-fanens UI skal flyttes inn vs. lenkes til?**
   Risiko: dobbeltarbeid + potensielt to forskjellige tall hvis logikken
   drifter. Anbefaling: bygg et felles `compute_*`-API og la begge faner
   kalle det.
4. **Skal de manglende sperrene legges på samtidig?** F.eks. advarsel hvis
   tolererbar feil er > 100 % av netto, eller hvis n_specific > 200.
   Antakelig ja — men kanskje som egne, små commits før layout-endringen.
5. **Bør netto-vs-abs-grunnlaget for n_random kunne velges av brukeren?**
   I dag er det hardkodet til netto. For mellomregningskontoer ville abs
   gitt mer revisormeningsfullt resultat.
6. **Live populasjonstabell — performanse?** Hvis populasjonen er 50k+
   bilag må vi bruke virtualisering ([VirtualTransactionsPanel](../views_virtual_transactions.py)
   eller lignende).

---

## Tidligere notater og relaterte dokumenter

- [doc/ANALYSE_UX_IDEER.md](ANALYSE_UX_IDEER.md) — UX-ideer for Analyse-fanen
- [doc/POPUP_STANDARD.md](POPUP_STANDARD.md) — standard for popup-dialoger
- [doc/TREEVIEW_PLAYBOOK.md](TREEVIEW_PLAYBOOK.md) — playbook for `ManagedTreeview`
- [doc/INTERACTION_GRAMMAR.md](INTERACTION_GRAMMAR.md) — felles
  interaksjonsmønstre
