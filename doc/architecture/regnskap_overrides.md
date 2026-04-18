# Konto → regnskapslinje-overstyringer

**Modul:** [regnskap_client_overrides.py](../../regnskap_client_overrides.py)
**Lagringssted:** `<data_dir>/config/regnskap/client_overrides/<klient_slug>.json`
**Sist oppdatert:** 2026-04-17

## Formål

En revisor kan overstyre den automatiske koblingen mellom en konto og en
regnskapslinje for en spesifikk klient. Overstyringen lagres per klient og
kan variere per år (f.eks. når et selskap reklassifiserer investeringer
mellom regnskapsårene).

## Filformat

```json
{
  "client": "Klient AS",
  "account_overrides": { "1300": 560, "1301": 560 },
  "account_overrides_by_year": {
    "2024": { "1300": 585 },
    "2025": { "1300": 560, "1301": 560 }
  }
}
```

- `account_overrides` — legacy/år-agnostisk dict. Oppdateres alltid ved
  lagring til siste verdier (bakoverkompatibilitet).
- `account_overrides_by_year[<år>]` — dict per år, har prioritet ved
  lesing når `year` er kjent.

## Lese-regler

### `load_account_overrides(client, year=None)`

1. Hvis `year` er gitt og `account_overrides_by_year[year]` finnes →
   returner det (selv om tomt).
2. Ellers → fall tilbake til `account_overrides` (legacy).

### `load_prior_year_overrides(client, year)` — fjor-pivot

Brukes når "UB fjoråret"-kolonnen skal aggregeres i Analyse.

1. Fjorårets eksplisitte overrides (`account_overrides_by_year[year-1]`)
   har **alltid** prioritet per konto.
2. For kontoer som *mangler* eksplisitt fjor-verdi, arves årets
   overstyring som fallback.

Dette hindrer at en ny reklassifisering i gjeldende år gir en falsk
"Endring"-linje der saldoen i realiteten er uendret mellom årene.

## Skrive-regler

`save_account_overrides(client, overrides, year=...)`:

- Oppdaterer alltid den år-agnostiske kopien til siste lagring.
- Oppdaterer `account_overrides_by_year[year]` kun dersom `year` er gitt.
- Atomisk skriv via `.tmp` + `replace`.

## Kjente gotchas

### Per-år-modellen skaper falske endringer (løst 2026-04-17)

**Symptom:** Når revisor flyttet konto 1300/1301 fra RL 585 til 560 i år
2025, viste UB 2024-kolonnen 0 på RL 560 og hele saldoen som "Endring".

**Årsak:** `load_prior_year_overrides` returnerte strengt `year-1`-dict,
uten fallback til gjeldende års overstyringer. Når `account_overrides_by_year[2024]` eksisterte men ikke hadde 1300/1301, ble disse
rutet til auto-match (585) for fjoråret mens 2025 brukte ny override (560).

**Fix:** Fallback-regel i `load_prior_year_overrides`. Se [test](../../tests/test_regnskap_client_overrides.py) `test_prior_year_overrides_fallback_to_current_year`.

**Hvordan du kan gjenoppta "fjoråret var faktisk på 585" hvis det er
ønsket:** Lagre en eksplisitt fjor-override (f.eks. via SB-bytte med
2024 som aktivt år). Eksplisitte fjor-verdier vinner alltid over
fallback.

## Relaterte felt i samme fil

Samme JSON huser også:

- `column_mapping` — HB-kolonnekartlegging (konto, beløp, bilag etc.)
- `accounting_system` — "Tripletex" / "PowerOffice GO" etc.
- `mva_code_mapping` — klient → standard MVA-kode.
- `expected_regnskapslinjer_presets` — forventede RL-er per scope.
- `expected_regnskapslinje_rules` — netting/toleranse-regler per scope.
- `skatteetaten_data`, `mva_melding` — snapshot av MVA-meldinger per år.

Alle bor i samme fil. Funksjoner som `save_*` leser payload først og
skriver hele payloaden tilbake — de er additive, ikke destruktive.

## Testdekning

[tests/test_regnskap_client_overrides.py](../../tests/test_regnskap_client_overrides.py)

- Roundtrip for hver save/load-variant.
- Per-år vs. legacy-prioritet.
- Fallback fra år til fjor ved manglende eksplisitt verdi.
- Eksplisitt fjor-verdi vinner over fallback.
- Ikke-destruktiv: lagring av ett felt tar ikke ut andre.
