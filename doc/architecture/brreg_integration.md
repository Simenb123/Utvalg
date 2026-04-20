# BRREG-integrasjon i Analyse-fanen

**Moduler:**
- [brreg_client.py](../../brreg_client.py) — API-klient + disk-cache (24 t TTL).
- [brreg_rl_comparison.py](../../brreg_rl_comparison.py) — RL↔BRREG-mapping via aliaser + GUI-overstyring.
- [brreg_mapping_config.py](../../brreg_mapping_config.py) — persistens for eksplisitt BRREG→regnr-mapping.
- [page_admin_brreg_mapping.py](../../page_admin_brreg_mapping.py) — admin-editor for mapping.
- [brreg_fjor_fallback.py](../../brreg_fjor_fallback.py) — BRREG som fjor-kolonne når egen SB-fjor mangler.
- [page_analyse_ui_helpers.py](../../page_analyse_ui_helpers.py) — fetch-trigger og `page._nk_brreg_data`.
- [page_analyse_rl_render.py](../../page_analyse_rl_render.py) — heading-injeksjon og fallback-valg i `refresh_rl_pivot`.
- [page_analyse_nokkeltall_render.py](../../page_analyse_nokkeltall_render.py) — nøkkeltall-panelet.

**Sist oppdatert:** 2026-04-20

## Formål

BRREG-integrasjonen gir revisor sammenligningstall fra offentlig
[Regnskapsregisteret](https://data.brreg.no/regnskapsregisteret/regnskap/)
i to former:

1. **BRREG-kolonne** i RL-pivot og nøkkeltall-panel — direkte
   sammenligning UB (klient) mot BRREG for samme regnskapsår.
2. **BRREG som fjor-fallback** — når egne fjorårs-SB-tall mangler,
   brukes BRREG-linjer fra år N-1 til å fylle UB_fjor /
   Endring_fjor / Endring_pct i RL-pivoten.

BRREG-tall er på RL-nivå (ikke konto-nivå). SB-konto-pivot har derfor
ikke BRREG-integrasjon.

## Datakilde — autoritativ kilde

**For revisjonsformål er det kritisk å vite *hvor* hver BRREG-verdi kommer fra.**

| Aspekt | Verdi |
|---|---|
| Kilde-URL | `https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}` |
| OpenAPI-spec | [v3/api-docs](https://data.brreg.no/regnskapsregisteret/regnskap/v3/api-docs) |
| Protokoll | HTTP GET, JSON-respons |
| Autentisering | Ingen — åpen tjeneste fra Brønnøysundregistrene |
| Dekning | Innleverte årsregnskap for norske rapporteringspliktige enheter |
| Cache-lag | Lokal disk-cache (`~/.utvalg/brreg_cache.json`), TTL 24 t, schema-versjonert (`regnskap_v{n}`) |
| User-Agent | `Utvalg-revisjonsverktoy/1.0` |

**Kilde for sammenligningsgrunnlag.** All data i BRREG-kolonnen i Analyse-
fanen, nøkkeltall-panelet og BRREG-fjor-fallback kommer fra nøyaktig denne
endpointen. Ingen annen ekstern kilde brukes (ikke proff.no, ikke Enin, ikke
SAF-T, ikke Altinn).

**Hva gratis-API-et *ikke* gir.** BRREGs offentlige REST-API returnerer
regnskapstall på sum-nivå for alle selskap, men **detaljposter er optional**
og rapporteres av selskapet selv. Selv selskap med oppstillingsplan `"store"`
leverer i praksis ofte kun sum-nivå til dette API-et. Fullstendige
detaljposter (tomter separat, kundefordringer separat, leverandørgjeld
separat, utbytte-avsetning, etc.) ligger i **XBRL-innleveringen til Altinn**
— et separat dokumentregister som krever kommersiell avtale med BRREG for
maskinell tilgang. Kilder som proff.no og proff forvalt henter fra dette
XBRL-arkivet, ikke fra gratis-API-et.

**Konsekvens for revisor.** BRREG-kolonnen i Utvalg gir garantert
sammenligning på sum-nivå (driftsinntekter, sum_eiendeler, etc.). For
detalj-linjer vil kolonnen være blank for de fleste klienter — det er
ikke en feil i Utvalg, men en begrensning i hva det åpne API-et leverer.
Hjelpefunksjonen `brreg_rl_comparison.availability(key)` returnerer `"sum"`
eller `"detail"` og brukes i admin-editoren til å vise forventet
leveringsdyktighet per nøkkel.

## Datastruktur — `_nk_brreg_data`

Etter `brreg_client.fetch_regnskap(orgnr)` sitter dette på `page`:

```python
{
    "orgnr": "123456789",
    "regnskapsaar": "2024",          # nyeste (bakoverkompatibelt)
    "linjer": { ... },                # nyeste års RL-linjer (bakoverkompatibelt)
    "driftsinntekter": 1_100_000.0,   # øvrige felter for nyeste år (bakoverkompat)
    ...
    # Flerårs-utvidelse:
    "years": {
        2024: {"regnskapsaar": "2024", "linjer": {...}, ...},
        2023: {"regnskapsaar": "2023", "linjer": {...}, ...},
        2022: {"regnskapsaar": "2022", "linjer": {...}, ...},
    },
    "available_years": [2024, 2023, 2022],  # sortert synkende, int-nøkler
}
```

**Bakoverkompatibilitet:** `regnskapsaar`, `linjer` og alle flate
toppfelter (driftsinntekter, sum_eiendeler, ...) reflekterer **nyeste**
år. Eksisterende kode som leser disse feltene fortsetter å virke uten
endringer. Ny kode kan indeksere spesifikt år via `years[år]`.

**Cache-schema:** `regnskap_v6:{orgnr}`. Ved schema-endringer bumpes
`_REGNSKAP_SCHEMA_VERSION` i `brreg_client`, noe som transparent
invaliderer all gammel cache (v5-data og eldre leses aldri).

**Maks antall år:** `_MAX_YEARS = 5`. BRREG leverer typisk 3–7
innleverte år; 5 er en god balanse mellom dekning og cache-størrelse.

## Flyt — datalag til visningslag

```
BRREG API (data[])
  ├─ brreg_client.fetch_regnskap(orgnr)
  │     ├─ for hver regnskapspost i data[:_MAX_YEARS]:
  │     │     _extract_entry_fields(rec) → {fra_dato, linjer, ...}
  │     └─ bygg result = nyeste års fields + years + available_years
  ├─ disk-cache: regnskap_v6:{orgnr}
  │     (_normalize_years_keys på load — JSON gjør int → str, normaliser tilbake)
  └─ returnerer dict til caller
         ↓
  page._nk_brreg_data = data
         ↓
  RL-pivot (refresh_rl_pivot):
    ├─ brreg_rl_comparison.add_brreg_columns(pivot, rl_df, data)
    │     → BRREG / Avvik_brreg / Avvik_brreg_pct
    └─ brreg_fjor_fallback.build_brreg_fjor_pivot_columns(pivot, rl_df, data, fjor_år)
          → UB_fjor / Endring_fjor / Endring_pct (når egen SB-fjor mangler)
         ↓
  Heading-injeksjon:
    _rl_headings_with_year(år, brreg_year=..., fjor_source=...)
      ├─ index 5: "UB {år}"
      ├─ index 10: "UB {år-1}" eller "UB {år-1} (BRREG)" hvis fjor_source == "brreg"
      └─ index 13: "BRREG {brreg_year}"
```

## Fjor-fallback-kontrakt

Satt av `refresh_rl_pivot`. Leses av `_rl_headings_with_year` og
`update_pivot_headings` (sistnevnte toggler kolonnebredde).

```python
page._rl_fjor_source ∈ {"sb", "brreg", None}
```

| Tilfelle | `_rl_fjor_source` | UB_fjor-kilde | Heading-suffix |
|---|---|---|---|
| Egen SB-fjor lastet | `"sb"` | fjorårs saldobalanse | – |
| Kun BRREG-år N-1 | `"brreg"` | BRREG RL-aggregat | `(BRREG)` |
| Ingen av delene | `None` | – (kolonner skjult) | – |

**Regel:** BRREG-fallback kjøres **kun** når egen SB-fjor ikke
er lastet. Ingen dobbelt-henting, ingen overlapp. Når egen SB er
lastet senere (lazy), trigges refresh og fjor_source byttes til `"sb"`.

## Nøkkeltall-panelet (page_analyse_nokkeltall_render)

Tidligere bug: `elif has_brreg` gjorde fjor og BRREG gjensidig
utelukkende — revisor mistet BRREG-sammenligningen så snart
fjorårs-SB ble importert.

Nåværende oppførsel:
- Kun fjor: `I år | Fjor | Endring`
- Kun BRREG: `I år | BRREG {år} | Endring %`
- Begge: `I år | Fjor | Endring | BRREG {år}` (parallell visning)
- Bunntekst: `regnskapsåret 2024` (entall) eller
  `regnskapsårene 2024, 2023, 2022` (flertall — fra `available_years`).

## BRREG-feltkatalog (kanoniske nøkler)

`_BRREG_KEYS` i [brreg_rl_comparison.py](../../brreg_rl_comparison.py)
definerer alle 35 kanoniske nøkler, med `sign`, `aliases` og evt. `formula`.
`_extract_entry_fields` i [brreg_client.py](../../brreg_client.py) mapper
disse fra BRREG-API-ets JSON-struktur (offisielt OpenAPI-skjema:
[v3/api-docs](https://data.brreg.no/regnskapsregisteret/regnskap/v3/api-docs)).

**Fortegnskonvensjon.** RL bruker revisorkonvensjonen (debet = +, kredit = −).
Eiendeler og kostnader er `sign = +1`; inntekter, EK, gjeld og resultat-poster
er `sign = −1`. BRREG-API leverer absoluttbeløp; `_resolve_brreg_value`
multipliserer inn RL-fortegnet ved oppslag.

**Schema-optionality.** BRREG-API definerer feltene, men innrapporterende
selskap *kan* utelate detalj-poster (særlig små foretak med forenklet
oppstillingsplan). Der felt mangler lagres `None`, og BRREG-kolonnen forblir
tom i Analyse-fanen.

### Resultatregnskap

| BRREG-nøkkel | API-kilde | Sign | Kommentar |
|---|---|---|---|
| `driftsinntekter` | `resultatregnskapResultat.driftsresultat.driftsinntekter.sumDriftsinntekter` | −1 | Aggregat |
| `salgsinntekt` | `…driftsinntekter.salgsinntekt` | −1 | Detalj (optional) |
| `annen_driftsinntekt` | `…driftsinntekter.annenDriftsinntekt` | −1 | Detalj (optional) |
| `driftskostnader` | `…driftskostnad.sumDriftskostnad` | +1 | Aggregat |
| `varekostnad` | `…driftskostnad.varekostnad` | +1 | Detalj (optional) |
| `loennskostnad` | `…driftskostnad.loennskostnad` | +1 | Detalj (optional) |
| `avskrivning` | `…driftskostnad.avskrivningVarigeDriftsmidlerImmatrielleEiendeler` | +1 | Detalj (optional) |
| `nedskrivning` | `…driftskostnad.nedskrivningVarigeDriftsmidlerImmatrielleEiendeler` | +1 | Detalj (optional) |
| `annen_driftskostnad` | `…driftskostnad.annenDriftskostnad` | +1 | Detalj (optional) |
| `driftsresultat` | `…driftsresultat.driftsresultat` | −1 | Aggregat |
| `finansinntekter` | `…finansresultat.finansinntekt.sumFinansinntekter` | −1 | Aggregat |
| `finanskostnader` | `…finansresultat.finanskostnad.sumFinanskostnad` | +1 | Aggregat |
| `rentekostnad_samme_konsern` | `…finanskostnad.rentekostnadSammeKonsern` | +1 | **Ny v6** — detalj (optional) |
| `annen_rentekostnad` | `…finanskostnad.annenRentekostnad` | +1 | **Ny v6** — detalj (optional) |
| `netto_finans` | `…finansresultat.nettoFinans` | −1 | Aggregat |
| `resultat_for_skatt` | `ordinaertResultatFoerSkattekostnad` | −1 | Aggregat |
| `skattekostnad` | `ordinaertResultatSkattekostnad` | +1 | **Ny v6** — detalj (optional) |
| `aarsresultat` | `aarsresultat` | −1 | Aggregat |
| `ekstraordinaere_poster` | `ekstraordinaerePoster` | −1 | **Ny v6** — detalj (optional) |
| `totalresultat` | `totalresultat` | −1 | **Ny v6** — detalj (optional) |

### Balanse

| BRREG-nøkkel | API-kilde | Sign | Kommentar |
|---|---|---|---|
| `sum_anleggsmidler` | `eiendeler.anleggsmidler.sumAnleggsmidler` | +1 | Aggregat |
| `goodwill` | `eiendeler.goodwill` | +1 | **Ny v6** — detalj (optional) |
| `sum_omloepsmidler` | `eiendeler.omloepsmidler.sumOmloepsmidler` | +1 | Aggregat |
| `sum_varer` | `eiendeler.sumVarer` | +1 | **Ny v6** — detalj (optional) |
| `sum_fordringer` | `eiendeler.sumFordringer` | +1 | **Ny v6** — detalj (optional) |
| `sum_investeringer` | `eiendeler.sumInvesteringer` | +1 | **Ny v6** — detalj (optional) |
| `sum_bankinnskudd_og_kontanter` | `eiendeler.sumBankinnskuddOgKontanter` | +1 | **Ny v6** — detalj (optional) |
| `sum_eiendeler` | `eiendeler.sumEiendeler` | +1 | Aggregat |
| `sum_innskutt_egenkapital` | `egenkapitalGjeld.egenkapital.innskuttEgenkapital.sumInnskuttEgenkaptial` | −1 | (obs: stavefeil `Egenkaptial` i API) |
| `sum_opptjent_egenkapital` | `egenkapitalGjeld.egenkapital.opptjentEgenkapital.sumOpptjentEgenkapital` | −1 | Har formula-fallback |
| `sum_egenkapital` | `egenkapitalGjeld.egenkapital.sumEgenkapital` | −1 | Har formula-fallback |
| `langsiktig_gjeld` | `egenkapitalGjeld.gjeldOversikt.langsiktigGjeld.sumLangsiktigGjeld` | −1 | Aggregat |
| `kortsiktig_gjeld` | `egenkapitalGjeld.gjeldOversikt.kortsiktigGjeld.sumKortsiktigGjeld` | −1 | Aggregat |
| `sum_gjeld` | `egenkapitalGjeld.gjeldOversikt.sumGjeld` | −1 | Har formula-fallback |
| `sum_egenkapital_og_gjeld` | `egenkapitalGjeld.sumEgenkapitalGjeld` | −1 | Har formula-fallback |

### Begrensninger i BRREG-API

Se også "Datakilde — autoritativ kilde" øverst i dette dokumentet.

**Ikke eksponert overhodet** (må hentes fra XBRL-innlevering i Altinn,
kommersiell avtale — utenfor scope):
- Varige driftsmidler-detaljer (tomter, bygninger, maskiner, inventar)
- Finansielle anleggsmidler-detaljer (datterselskap-aksjer, lån i konsern)
- Aksjekapital / overkursfond separat
- Avsetninger (pensjon, utsatt skatt)
- Leverandørgjeld, skyldige offentlige avgifter, utbytte separat

**Eksponert i API-skjema, men ofte `None`** (schema-optional, avhengig av
hva selskapet har valgt å rapportere — markert `"detail"` av
`availability(key)`):
- Resultat-detaljer: `salgsinntekt`, `annen_driftsinntekt`, `varekostnad`,
  `loennskostnad`, `avskrivning`, `nedskrivning`, `annen_driftskostnad`
- Finans-detaljer: `rentekostnad_samme_konsern`, `annen_rentekostnad`
- Skatt / totalresultat: `skattekostnad`, `ekstraordinaere_poster`,
  `totalresultat`
- Balanse-detaljer: `goodwill`, `sum_varer`, `sum_fordringer`,
  `sum_investeringer`, `sum_bankinnskudd_og_kontanter`

**Alltid populert** (`"sum"`-nivå): alle sum-aggregater — `driftsinntekter`,
`driftskostnader`, `driftsresultat`, `finansinntekter`, `finanskostnader`,
`netto_finans`, `resultat_for_skatt`, `aarsresultat`,
`sum_anleggsmidler/omloepsmidler/eiendeler`, hele EK-subtreet,
`langsiktig_gjeld`, `kortsiktig_gjeld`, `sum_gjeld`,
`sum_egenkapital_og_gjeld`.

Admin-editoren viser "Kilde"-kolonnen med Sum/Detalj per nøkkel. Mapper man
en `"detail"`-nøkkel, lagres mappingen uansett, men Analyse-radens
BRREG-kolonne forblir blank så lenge selskapets innrapportering ikke
inneholder feltet.

### Formula-fallback

Noen sum-nøkler kan beregnes fra andre når API-et ikke leverer direkte:

```python
"sum_opptjent_egenkapital": formula = ["sum_egenkapital", "-sum_innskutt_egenkapital"]
"sum_egenkapital":          formula = ["sum_innskutt_egenkapital", "sum_opptjent_egenkapital"]
"sum_gjeld":                formula = ["langsiktig_gjeld", "kortsiktig_gjeld"]
"sum_egenkapital_og_gjeld": formula = ["sum_egenkapital", "sum_gjeld"]
```

`_brreg_value` prøver først direkte feltuttrekk; hvis `None`, evaluerer
formelen rekursivt. Returnerer `None` hvis ikke alle formel-ledd har verdi.

## Overstyring via GUI-mapping

BRREG-API-et bruker sitt eget linjenavn-sett (f.eks. `salgsinntekt`,
`sum_eiendeler`). Vår RL-metodikk er sannheten — vi endrer ikke regnr
eller linjenavn når BRREG ikke treffer via alias. I stedet kan revisor
koble BRREG-nøkler direkte til egne regnr via Admin-fanen → "BRREG-mapping".

**Modulskisse:**

```
_BRREG_KEYS                  brreg_mapping_config
(aliases + sign + formula)   (eksplisitt JSON-mapping)
         │                            │
         └──────── add_brreg_columns ─┘
                   (mapping vinner, alias = fallback)
```

**Datamodell.** Lagres i `config/classification/brreg_rl_mapping.json`
(globalt, ikke per klient):

```json
{
  "version": 1,
  "mappings": {
    "salgsinntekt": 10,
    "sum_eiendeler": 665
  }
}
```

**API.** [brreg_mapping_config.py](../../brreg_mapping_config.py):
- `resolve_brreg_mapping_path()` — sti under `app_paths.config_dir()`.
- `load_brreg_rl_mapping() -> dict[str, int]` — robust mot manglende fil / invalid JSON.
- `save_brreg_rl_mapping(mapping)` — type-coerce før lagring.
- `list_brreg_keys() -> list[(brreg_key, human_label)]` — henter fra `_BRREG_KEYS`.

**Integrering i `add_brreg_columns`.** Parameteret `rl_mapping` styrer
kilden:

- `rl_mapping=None` (default) → last fra JSON.
- `rl_mapping={}` → eksplisitt tom, ingen overstyring.
- `rl_mapping={"key": regnr, ...}` → direkte overstyring.

**Prioritet.** For hver BRREG-nøkkel som er mapped:
1. Verdi skrives direkte på `regnr = mapping[key]` (sign tas fra `_BRREG_KEYS[key]["sign"]`).
2. Nøkkelen legges i `mapped_brreg_keys` og ekskluderes fra alias-fallback
   — forhindrer at samme BRREG-verdi både havner på mapped regnr og på
   et alias-match regnr.
3. Regnr som allerede er fylt via mapping legges i `overridden_regnrs` og
   overskrives ikke av alias-match.

Alias-matching i `_BRREG_KEYS["aliases"]` kjører som fallback for BRREG-
nøkler som **ikke** er i mapping-filen. `compute_sumlinjer` kjører
uendret og propagerer oppover i hierarkiet.

**GUI-flyt.** `page_admin_brreg_mapping._BrregMappingEditor`:
- Treeview lister alle BRREG-nøkler fra `_BRREG_KEYS`.
- Combobox-detail viser `regnr — navn` fra `regnskapslinje_mapping_service`.
- "Forhåndsvis"-knapp åpner modal med mapped vs. umappet oversikt.
- "Lagre" skriver til JSON; Analyse-fanen plukker opp endringen ved neste refresh.

## Gotchas

- **RL-nivå, ikke konto-nivå.** BRREG har ikke kontoplan. Derfor
  fungerer BRREG-integrasjonen kun for `Regnskapslinje`-modus i
  Analyse-fanen. I SB-konto-modus skjules alle BRREG-kolonner
  (eksplisitt width=0 i `update_pivot_headings`).
- **Cache-invalidering er transparent.** `_REGNSKAP_SCHEMA_VERSION`
  er en del av cache-nøkkelen; bump den for strukturelle endringer.
- **Int-nøkler i `years`.** JSON-cache serialiserer int-nøkler som
  strings. `_normalize_years_keys` konverterer tilbake på load slik
  at `years[2024]` (int) alltid fungerer.
- **BRREG-fjor-fallback er ikke en avstemming.** Den gir visuell
  sammenligning mot offentlige tall, men skal ikke brukes til
  IB/UB-avstemmingskontroll (BRREG kan avvike fra egen
  hovedbok pga. klassifiseringsforskjeller).
- **Ingen UI-årvelger ennå.** Default aktivt BRREG-år =
  `available_years[0]` (nyeste). Historiske år brukes kun som
  fjor-fallback-kilde. Fremtidig UX-iterasjon kan eksponere
  årvelger dersom behov oppstår.

## Test-dekning

- [tests/test_brreg_multiyear.py](../../tests/test_brreg_multiyear.py) — flerårs-fetch, cache-schema v4, int-nøkkel-roundtrip.
- [tests/test_brreg_rl_comparison.py](../../tests/test_brreg_rl_comparison.py) — alias-mapping, RL-fortegns-normalisering.
- [tests/test_brreg_rl_comparison_override.py](../../tests/test_brreg_rl_comparison_override.py) — eksplisitt GUI-mapping overstyrer alias.
- [tests/test_brreg_mapping_config.py](../../tests/test_brreg_mapping_config.py) — persistens, type-coerce, robust load.
- [tests/test_brreg_fjor_fallback.py](../../tests/test_brreg_fjor_fallback.py) — fjor-fallback via BRREG, `fjor_source`-flyt.
- [tests/test_rl_default_columns_and_headings.py](../../tests/test_rl_default_columns_and_headings.py) — heading-injeksjon med `brreg_year`.
- [tests/test_nk_render_brreg.py](../../tests/test_nk_render_brreg.py) — nøkkeltall-panelet viser både fjor og BRREG parallelt.
