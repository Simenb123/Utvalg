# Analyse-fanens RL-pivot-motor

**Moduler:**
- [page_analyse_rl.py](../../page_analyse_rl.py) — `build_rl_pivot`, aggregering.
- [regnskapslinje_mapping_service.py](../../regnskapslinje_mapping_service.py) — kanonisk konto→regnr-resolusjon.
- [previous_year_comparison.py](../../previous_year_comparison.py) — fjorårs-kolonner.
- [brreg_rl_comparison.py](../../brreg_rl_comparison.py) — BRREG-sammenligning.
- [regnskap_mapping.py](../../regnskap_mapping.py) — sumlinjer + normalisering.

**Sist oppdatert:** 2026-04-17

## Formål

Analyse-fanen viser en tabell med én rad per *regnskapslinje* (RL), ikke
én rad per konto. Pivot-motoren:

1. Aggregerer saldobalansen (IB/UB) per RL.
2. Teller antall HB-transaksjoner per RL.
3. Legger på fjorårs-kolonner (UB_fjor, Endring, Endring_pct).
4. Legger på AO-justering (base vs. adjusted).
5. Legger på BRREG-sammenligning.
6. Legger på sumposter (Σ-rader fra RL-hierarkiet).

Sluttresultatet er en DataFrame som mappes direkte til Treeview.

## Entry point — `refresh_rl_pivot`

```
refresh_rl_pivot(page, ...)
  ├─ build_rl_pivot(df_hb, intervals, regnskapslinjer, sb_df=..., account_overrides=...)
  ├─ [hvis fjorårs-SB tilgjengelig]
  │   add_previous_year_columns(pivot, sb_prev, ..., prior_year_overrides=load_prior_year_overrides(...))
  ├─ [AO-sammenligning]
  │   build_rl_pivot(base_sb_df) + build_rl_pivot(adjusted_sb_df)
  │   _add_adjustment_columns(pivot, base_pivot, adjusted_pivot)
  ├─ [hvis BRREG]
  │   brreg_rl_comparison.add_brreg_columns(...)
  └─ [rendering]
      tag-konfigurasjon, sumrader, Antall-kolonner, evt. skjul-sumposter
```

## Kanonisk konto→regnr-resolusjon

ALLE aggregeringer (SB, HB, fjor-SB, AO-base, AO-adjusted) bruker én
delt resolusjon via `regnskapslinje_mapping_service.resolve_accounts_to_rl`.
Dette er viktig — Analyse, Saldobalanse og Admin må gi samme mapping
for samme (konto, overrides, intervall)-kombinasjon.

Prioriteten er:

1. **Klient-override** (`account_overrides[konto] → regnr`).
2. **Intervall-match** (`intervals.fra ≤ konto ≤ intervals.til`).
3. **Ingen** (konto droppes fra pivoten, går i "umappet").

## Fjorårs-aggregering

Fjor-SB aggregeres med `prior_year_overrides`, som ikke nødvendigvis er
samme dict som current-year. Se [regnskap_overrides.md](regnskap_overrides.md)
for presis merge-semantikk. Hovedregelen:

> Fjorårets eksplisitte overrides vinner per konto. For kontoer uten
> eksplisitt fjor-override, arves årets override som fallback.

Dette hindrer falske "Endring"-linjer når revisor reklassifiserer et
balansepunkt mellom år uten at saldoen har endret seg reelt.

## Visningsregler

`build_rl_pivot` filtrerer visningen etter om SB er tilgjengelig:

- **Med SB:** vis RL der `|UB| > 1e-9` **ELLER** `|UB_fjor| > 1e-9`
  **ELLER** `Antall > 0`.
- **Uten SB:** vis kun RL der `Antall > 0`.

Grunn: uten SB kan vi ikke skille "null saldo" fra "ingen data". Da er
Antall den eneste indikatoren. Fjor-kolonnene legges på *før* filteret,
slik at RL som kun har fjorårsdata (typisk pga. mapping-drift) ikke
blir skjult. Se [rl_mapping_drift.md](rl_mapping_drift.md) for hvordan
selve drift-funn eksponeres i GUI.

HB-konto-modusen speiler denne regelen: `page_analyse_pivot.py`
merger UB_fjor per konto og skjuler kun rader der både inneværende UB
og UB_fjor er ≈0.

## Kolonne-kontrakt

Returnert DataFrame skal alltid ha disse kjernekolonnene:

| Kolonne | Type | Kilde |
|---------|------|-------|
| `regnr` | int | RL-katalog |
| `regnskapslinje` | str | RL-katalog |
| `IB` | float | sb_df.ib sum per regnr |
| `Endring` | float | UB - IB |
| `UB` | float | sb_df.ub sum per regnr |
| `Antall` | int | HB-rader som mapper til regnr |

Betingede tilleggs-kolonner:

- `UB_fjor`, `Endring_fjor`, `Endring_pct` — hvis sb_prev gitt.
- `UB_base`, `UB_adjusted`, `AO_diff` — hvis AO-sammenligning kjørt.
- `BRREG_UB`, `BRREG_diff` — hvis BRREG-data tilgjengelig.

GUI-laget (`_refresh_rl_view` i `page_analyse_sb.py`) må tåle at alle
tilleggs-kolonner mangler.

## Gotchas

### Sumposter beregnes SIST

`regnskap_mapping.compute_sumlinjer` beregnes til slutt, etter at alle
kolonne-transformasjoner er ferdige. Hvis en ny kolonne introduseres
må den inngå i sumlinje-beregningen hvis verdien skal aggregeres opp.
Ellers blir sumraden `NaN` for den kolonnen.

### AO-kolonner kan krasje uavhengig av pivot

`_add_adjustment_columns(pivot_df)` (uten base/adjusted) legger til
tomme AO-kolonner — brukes som fallback hvis AO-pipelinen feiler. Viktig
for å unngå KeyError i nedstrøms rendering.

### Prev-year-fallback endrer fjor-UB ved reklassifisering (2026-04-17)

Løst: se [regnskap_overrides.md](regnskap_overrides.md) gotcha-seksjon.
Tidligere returnerte `load_prior_year_overrides` strengt prev-år-dict,
som ga 0 i fjor-kolonnen når en konto var reklassifisert i år.

### Identiske tall i UB og UB_fjor = samme konto-saldo, ikke bug

Overrides endrer *mapping*, ikke saldoer. Hvis UB 2025 = UB 2024 på en
RL betyr det at de underliggende kontoene har samme saldo. Sjekk
konto-listen før du antar pivot-bug.

### Visning-dropdown må dispatche FØR normalize_view_mode (løst 2026-04-17)

**Symptom:** Velge "Nøkkeltall" i Visning-rullgardinen viste SB-tree i
høyre panel, ikke nøkkeltall-teksten.

**Årsak:** `page_analyse_columns.normalize_view_mode` kollapser alle
ukjente verdier (inkludert "Nøkkeltall", "Motposter", "Motposter
(kontonivå)") til "Saldobalansekontoer". Dispatcheren sjekket
normalisert modus først, så legacy-grenen ble aldri nådd.

**Fix:** [page_analyse.py:_refresh_transactions_view](../../page_analyse.py) kaller
nå `_dispatch_legacy_tx_view(raw_mode=raw_mode)` FØR normalisering.
Regresjon dekket av [test_page_analyse_view_dispatch.py](../../tests/test_page_analyse_view_dispatch.py).

## Perf-notater

- `_resolve_regnr_for_accounts` bygger en `RLMappingContext` per kall.
  For store SAF-T (> 500k rader) er dette hot-path — hold kontekst-
  oppsett billig, ikke les JSON flere ganger.
- `pandas.merge` på konto-streng må normalisere (strip) begge sider,
  ellers får vi stille NaN-match.
- `compute_sumlinjer` gjør rekursiv aggregering — O(N·D) hvor D er
  dybden av RL-hierarkiet. Fint i praksis.

## Testdekning

[tests/test_page_analyse_rl.py](../../tests/test_page_analyse_rl.py) —
pivot-kontrakt, visningsregler.

[tests/test_previous_year_comparison.py](../../tests/test_previous_year_comparison.py) —
fjor-kolonner, mapping-priortitet.

[tests/test_regnskapslinje_mapping_service.py](../../tests/test_regnskapslinje_mapping_service.py) —
kanonisk konto→regnr.

[tests/test_regnskap_client_overrides.py](../../tests/test_regnskap_client_overrides.py) —
`load_prior_year_overrides` med fallback (regresjon for 2026-04-17).
