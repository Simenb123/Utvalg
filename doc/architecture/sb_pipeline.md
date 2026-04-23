# SB-pipelinen — oversikt og referanse

**Status:** Levende dokument. Oppdatér når SB-kjernen endres.
**Sist oppdatert:** 2026-04-23
**Målgruppe:** Utviklere som skal endre i SB-byggingen, refresh-flyten eller mapping-lagene.

## Formål

Saldobalansen (SB) er kjerne-datasettet i Utvalg — alle andre faner leser fra den. Denne fila samler pipeline-kunnskapen på ett sted slik at du raskt finner «hvor starter jeg?» uten å grave gjennom 30+ moduler. Der et tema er dekket grundig i en annen doc/architecture-fil, lenker vi dit heller enn å duplisere.

## Modellen på 60 sekunder

```
┌───────────────────┐      ┌────────────────────────┐
│ Kildefil          │      │ Dataset-fanen          │
│  SAF-T (.zip)     │ ───▶ │ _build_dataset_clicked │
│  Excel / CSV      │      └────────────────────────┘
└───────────────────┘                │
                                     ▼
                        ┌────────────────────────┐
                        │ dataset_pane_build     │
                        │ .build_dataset()       │
                        └────────────────────────┘
                                     │
                   ┌─────────────────┼─────────────────┐
                   ▼                 ▼                 ▼
           ┌───────────────┐ ┌──────────────┐ ┌────────────────┐
           │ saft_reader   │ │dataset_build │ │dataset_cache_  │
           │ read_saft_led │ │_fast         │ │sqlite          │
           │ ger()         │ │.build_from_  │ │ (save/load)    │
           │ (SAF-T only)  │ │ file()       │ │                │
           └───────────────┘ └──────────────┘ └────────────────┘
                   │                 │                 │
                   └─────────────────┼─────────────────┘
                                     ▼
                   ┌──────────────────────────────────┐
                   │ session.set_dataset(df, cols)    │
                   │ bus.emit("DATASET_BUILT")        │
                   │ app._on_dataset_ready(df)        │
                   └──────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
      ┌──────────────┐      ┌──────────────────┐    ┌───────────────┐
      │ Analyse      │      │ Lazy dirty dict  │    │ Tab-activation│
      │ (EAGER)      │      │ (Saldobalanse,   │    │ (Konsolidering│
      │ after_idle   │      │ Regnskap, MVA,   │    │ A07, Saldo-   │
      │ refresh_from_│      │ Lønn, Skatt,     │    │ balanse, AR,  │
      │ session      │      │ Reskontro, Doc., │    │ Handlinger,   │
      │              │      │ Statistikk, …)   │    │ Materiality,  │
      │              │      │ → én-shot pop    │    │ Documents)    │
      │              │      │ ved tab-klikk    │    │ → hver gang   │
      └──────────────┘      └──────────────────┘    └───────────────┘
```

Mapping-lag (`konto → RL`, `konto → A07`, `konto → gruppe`) ligger som projeksjoner over dataene og leses av forbrukerne direkte.

## Datamodell

Kanoniske SB-kolonner defineres i [saldobalanse_payload.py](../../saldobalanse_payload.py) (`ALL_COLUMNS`):

| Kolonne | Type | Kilde | Formål |
|---|---|---|---|
| `Konto` | str | Kildefil | Kontonummer (primærnøkkel) |
| `Kontonavn` | str | Kildefil | Tekstbeskrivelse |
| `IB` | float | SAF-T/Excel | Inngående saldo |
| `Endring` | float | Beregnet | UB − IB hvis ikke i kilde |
| `UB` | float | SAF-T/Excel | Utgående saldo |
| `Antall` | int | HB | Bilagslinjer (kun i HB-modus) |
| `Gruppe` | str | Klassifisering | Fra konto_klassifisering |
| `A07-kode` | str | Mapping | Per klient/år |
| `RF-1022-post` | str | Mapping | Selskapsrapport-kode |
| `Regnskapslinje` | str | Mapping | Mappet regnskapslinje-navn |
| `Regnr` | str | Mapping | Regnskapslinje-nummer |
| `Mappingstatus` | str | Mapping | mapped / unmapped / sumline |
| `Kilde` | str | Build | `HB` / `SAF-T` / `TB` |
| `Tilleggspostering` | float | ÅO | UB_adjusted − UB_base |
| `UB før ÅO` | float | ÅO | Før periode-justering |
| `UB etter ÅO` | float | ÅO | Etter periode-justering |
| `Detaljklassifisering` | str | Klassifisering | Finkornet klassifisering |
| `Lønnsstatus` | str | A07 | Payroll-flagg |
| `Problem` | str | Validering | Evt. validerings-issue |
| `Kol` | str | Intern | GL-basis-kolonne |
| `Eid selskap` | bool | AR | Owned-company flagg |

Kolonnene normaliseres i `_normalize_sb_frame` (samme fil) — gruppert på `Konto`, `IB`/`UB`/`Endring` aggregert per konto.

## Fase 1 — Build-pipelinen

**Entrypoint:** `_build_dataset_clicked` i [dataset_pane.py](../../dataset_pane.py) kalles når bruker klikker «Bygg dataset»-knappen. Den kaller `build_dataset(req)` i [dataset_pane_build.py](../../dataset_pane_build.py).

**Sekvens:**

```
build_dataset(req)
 ├─ _store_version_if_needed()
 │    kopierer kildefil til clients/<slug>/years/<YYYY>/<dtype>/
 ├─ dataset_cache_sqlite.load_cache(sha, signature)
 │    cache-hit: returner ferdig BuildResult
 ├─ cache-miss:
 │   if SAF-T:  saft_reader.read_saft_ledger(path)
 │   else:      dataset_build_fast.build_from_file(path, mapping, ...)
 ├─ dataset_cache_sqlite.save_cache(df, sha, signature)
 └─ returner BuildResult(df, cols, stored_path, stored_version_id, ...)
     └─ _apply_build_result()
         ├─ session.set_dataset(df, cols) / session.set_tb(df)
         ├─ bus.emit("DATASET_BUILT", df)
         └─ _schedule_auto_create_sb_from_saft()  (kun SAF-T)
```

**Nøkler:**

- **Cache-signatur**: `dataset_cache_sqlite.build_signature(mapping, sheet_name, header_row)` → sha256. Hele mapping-config inngår.
- **Cache-navn**: `<source_sha[:32]>__<signature[:32]>.sqlite`
- **READER_VERSION** i [saft_reader.py](../../saft_reader.py): inkrement ved endring i parser → alle gamle SAF-T-cacher invalideres automatisk

**TB-only (kun saldobalanse):** trigges av `set_sb_mode(True)` når bruker velger SB-versjon i stedet for HB. Krever kun `Konto`-kolonnen (ikke `Bilag`/`Beløp`/`Dato`). Samme build-flow, bare andre validerings-krav og mappe (`sb/` i stedet for `hb/`).

## Fase 2 — Storage

```
clients/
  <client_slug>/
    meta.json
    audit_log.jsonl
    years/
      <YYYY>/
        versions_index.json
        datasets/
          hb/                 HB-cacher (fullstendig hovedbok)
            <sha>__<sig>.sqlite
          sb/                 SB-cacher (TB-only / avledet SB)
            <sha>__<sig>.sqlite
```

- **Versjonering**: hver byggede kilde får en versjon. `versions_index.json` holder metadata.
- **Cache-invalidering**: automatisk via `READER_VERSION` + `build_signature`. Ingen manuell sletting nødvendig.

→ Se [dataset_pane_versioning.md](dataset_pane_versioning.md) for år-bytte-gotchas (bug i `_last_applied_client/_last_applied_year` løst 2026-04-17).

## Fase 3 — Refresh-distribusjon

Hybrid eager/lazy mønster i [ui_main.py](../../ui_main.py). Tre refresh-kategorier:

| Fane | Kategori | Refresh-hook | Trigger |
|---|---|---|---|
| **Analyse** | Eager | `refresh_from_session(defer_heavy=True)` | `_on_dataset_ready` + `_on_tb_ready` (umiddelbart `after_idle`) |
| **Saldobalanse** | Tab-activation | `_refresh_saldobalanse_from_session` | Hver tab-aktivering + lazy ved dataset-load |
| **Konsolidering** | Tab-activation | `_refresh_consolidation_from_session` | Hver tab-aktivering |
| **A07** | Tab-activation | `_refresh_a07_from_session` | Hver tab-aktivering |
| **AR** | Tab-activation | `_refresh_ar_from_session` | Hver tab-aktivering |
| **Admin** | Tab-activation | `_refresh_admin_from_session` | Hver tab-aktivering |
| **Handlinger** | Tab-activation | `_refresh_handlinger_from_session` | Hver tab-aktivering |
| **Scoping** | Tab-activation | `_refresh_scoping_from_session` | Hver tab-aktivering |
| **Vesentlighet** | Tab-activation | `_refresh_materiality_from_session` | Hver tab-aktivering (lagt til 2026-04-23) |
| **Documents** | Tab-activation | `_refresh_documents_on_tab_activate` | Hver tab-aktivering (tving disk-skann) |
| **Regnskap** | Lazy (en-shot) | `_refresh_regnskap` | Første tab-aktivering etter dataset-load |
| **MVA** | Lazy (en-shot) | `_refresh_mva` | Første tab-aktivering etter dataset-load |
| **Lønn** | Lazy (en-shot) | `_refresh_lonn` | Første tab-aktivering etter dataset-load |
| **Skatt** | Lazy (en-shot) | `_refresh_skatt` | Første tab-aktivering etter dataset-load |
| **Reskontro** | Lazy (en-shot) | `_refresh_reskontro` | Første tab-aktivering etter dataset-load |
| **Statistikk** | Popup (ikke-fane) | `_open_statistikk_popup` | Høyreklikk fra Analyse eller Handlinger |
| **Driftsmidler** | Lazy (en-shot) | `_refresh_driftsmidler` | Første tab-aktivering |
| **Oversikt** | Lazy (en-shot) | `_refresh_oversikt` | Første tab-aktivering |

**Lazy-mekanismen**: `_post_load_dirty_refreshers` er en dict `{widget: refresh_callable}` som bygges i `_on_dataset_ready`. Ved hver tab-aktivering pop'er `_on_notebook_tab_changed` callback'en ut og kjører `after_idle(fn)`. En-shot — etter første pop er fanen «rent».

**Tab-activation-mønster**: for faner som må synke klient/år hver gang (ikke bare første gang), finnes egne `_refresh_<fane>_from_session`-metoder som kalles direkte i `_on_notebook_tab_changed`.

**Kontrakten `refresh_from_session(session_obj, **_kw)`:**
- Leser `session.client`, `session.year`, `session.dataset`, `session.tb_df`
- Sjekker `_session_cache_key = (client, year)` — tidlig-return hvis uendret
- Invaliderer per-side cache ved endring

## Fase 4 — Mapping-lagene

Fire lag som transformerer konto-nivå-data til RL-nivå:

### 4.1 Konto → Regnskapslinje (RL)

- **Moduler**: [regnskap_mapping.py](../../regnskap_mapping.py), [regnskapslinje_mapping_service.py](../../regnskapslinje_mapping_service.py)
- **Katalog**: `config/regnskap/regnskapslinjer.json` + `kontoplan_mapping.json` (intervalbasert)
- **Oppløsning**: `resolve_accounts_to_rl()` — per konto: override → interval-treff → unmapped
- **Sannhet**: JSON-filene (generert fra Excel ved import)

### 4.2 Klient-overstyringer

- **Modul**: [regnskap_client_overrides.py](../../regnskap_client_overrides.py)
- **Lagring**: `<data_dir>/config/regnskap/client_overrides/<slug>.json`
- **Struktur**:
  ```json
  {
    "account_overrides": { "1300": 560 },          // Legacy, år-agnostisk
    "account_overrides_by_year": {
      "2024": { "1300": 585 },
      "2025": { "1300": 560 }
    }
  }
  ```
- **Prioritet**: `account_overrides_by_year[year]` først, fallback til `account_overrides`.
- **Fjorårs-fallback**: `load_prior_year_overrides()` — fjorårets eksplisitt, så i år som fallback (løser falske endringer ved reklassifisering, jf. fix 2026-04-17).

→ Se [regnskap_overrides.md](regnskap_overrides.md) for per-år-modellen.

### 4.3 Konto → A07-kode

- **Moduler**: [konto_klassifisering.py](../../konto_klassifisering.py), [a07_feature/mapping_source.py](../../a07_feature/mapping_source.py)
- **Lagring**: `<data_dir>/konto_klassifisering_profiles/<klient>/<år>/account_profiles.json`
- **API**: `load_a07_mapping(client, year=...)` / `save_a07_mapping(...)` — per klient + år
- **Fallback**: `load_nearest_prior_document()` leser nærmeste tidligere år

### 4.4 Konto → gruppe (klassifisering)

- **Modul**: [konto_klassifisering.py](../../konto_klassifisering.py) (facade) + `account_profile_legacy_api.py` (sannhet)
- **Scope**: `"analyse" | "mva" | "lonn" | "skatt" | "a07"` — hver scope har egne regler
- **Konsumenter**: MVA, Lønn, Skatt, A07-note, Saldobalanse-fanens klassifiserings-UI

### Sannhet per mapping

| Mapping | Sannhets-fil | Gyldighet |
|---|---|---|
| RL-intervall | `config/regnskap/regnskapslinjer.json` | Global |
| RL-override | `client_overrides/<slug>.json` | Per-klient, per-år |
| A07-kode | `account_profiles.json` | Per-klient, per-år |
| Gruppe | `account_profiles.json` (scope-filtrert) | Per-klient, per-år + scope |
| Drift-aksept | `client_overrides/<slug>.json::accepted_mapping_drift` | Per-klient, per-år-par |

→ Se [rl_mapping_drift.md](rl_mapping_drift.md) for drift-deteksjon (ikke-korrigerende, kun alerting).

## Cache-kontraktene

Fem cache-lag i SB-pipelinen. Når klassifisering endres må *alle* relevante cacher invalideres:

| Cache | Lokasjon | Nøkkel | Invalidering |
|---|---|---|---|
| `dataset_cache_sqlite` | Disk (`.sqlite`) | `(source_sha, signature)` | Automatisk ved ny build (ny signature) eller `READER_VERSION`-bump |
| `_SB_CACHE` | Modul-nivå i [page_analyse_rl_data.py](../../page_analyse_rl_data.py) | `(client, year, sb_path, mtime)` | Automatisk via mtime; eksplisitt `_invalidate_sb_cache()` |
| `_base_payload_cache` | Per-instans i [page_saldobalanse.py](../../page_saldobalanse.py) | `_base_payload_cache_key` | `_invalidate_payload_cache()` — kalles ved `refresh_from_session` og ved klassifiserings-endring |
| `_payroll_usage_features_cache` | Per-instans i [page_saldobalanse.py](../../page_saldobalanse.py) | `_payroll_usage_cache_key` | Samme `_invalidate_payload_cache()` |
| `_session_cache_key` | Per-instans (alle `refresh_from_session`-forbrukere) | `(client, year)` | Automatisk ved første ulik nøkkel |

**Kritisk invariant**: `_invalidate_payload_cache()` må kalles også når profil-dokumentet endres (ikke bare ved klient/år-bytte). Fix 2026-04 la til `_profile_document`, `_history_document`, `_profile_catalog`, `_payroll_context_key` i invalideringen — jf. commit `0b98da3`.

## Vocabulary

[src/shared/columns_vocabulary.py](../../src/shared/columns_vocabulary.py) sentraliserer alle SB-kolonne-labels:

- `heading(col_id, year=...)` → `"UB 2025"`, `"Δ UB 25/24"`, `"Δ UB-IB 25"`
- `active_year_from_session()` henter aktivt år
- `LABELS_STATIC` for kolonner uten år-suffiks

Brukes av alle forbrukere som viser SB-tall med år (Analyse, Saldobalanse, Statistikk, Regnskap).

→ Se [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) for fullt vokabular.

## Risikable moduler

Fem moduler hvor endringer lett kan ødelegge SB-pipelinen. Les denne seksjonen før du endrer noen av dem.

### [saldobalanse_payload.py](../../saldobalanse_payload.py) (~1306 LOC)

- **Rolle**: Kjernedata-bygger for Saldobalanse-fanen. Flettet sammen (base/adjusted/effective) SB-views, mapper A07/lønn, bygger payload for GUI.
- **Hva kan lett brytes**:
  - Kolonne-rename i `ALL_COLUMNS` uten å oppdatere alle forbrukere
  - Cache-invalideringshull (se over)
  - Endring i `_resolve_sb_columns` — bryter Excel-import med ikke-standard kolonnenavn
- **Før-/etter-tester**: `tests/test_page_saldobalanse*.py` + `tests/test_sb_to_regnskap_integration.py`

### [page_saldobalanse.py](../../page_saldobalanse.py)

- **Rolle**: GUI-integrasjon. Profil-lesing fra disk, cache-orchestrering mellom classification-UI og payload.
- **Hva kan lett brytes**: `_invalidate_payload_cache()` må kalles etter *hver* klassifiserings-endring. Rekkefølge-sensitivt: vars skal invalideres før disk-read.
- **Før-/etter-tester**: `tests/test_page_saldobalanse.py` + `tests/test_page_saldobalanse_detail_panel.py`

### [regnskap_client_overrides.py](../../regnskap_client_overrides.py)

- **Rolle**: Per-klient override-lag for RL-mapping. Løser reklassifiseringer uten å endre global regelbok.
- **Hva kan lett brytes**: Prioritets-reglene i `load_account_overrides()` og `load_prior_year_overrides()`. Fjorårs-fallback er kritisk for UB-fjor-sammenligning.
- **Før-/etter-tester**: `tests/test_regnskap_client_overrides.py`

### [saft_reader.py](../../saft_reader.py) (~583 LOC)

- **Rolle**: SAF-T XML-parser (stream-basert). Leser Transactions, Balances, Customers, Suppliers.
- **Hva kan lett brytes**:
  - Tegn-konvertering (` ` i SAF-T-eksporter)
  - Sign-konvensjon (Debit positiv, Credit negativ — avhenger av `AccountStructure`)
  - Hvis du legger til nye felter: **øk `READER_VERSION`** — ellers vil gamle cacher mangle nye data.
- **Før-/etter-tester**: `tests/test_saft_reader.py` + `tests/test_saft_tax_table.py`

### [dataset_build_fast.py](../../dataset_build_fast.py) (~730 LOC)

- **Rolle**: Rask Excel/CSV-import for ikke-SAF-T-datasett.
- **Hva kan lett brytes**:
  - `_coerce_header_row()` — off-by-one feller
  - Lowercase-alias-kompatibilitet (tester forventer spesifikt at `"saldo"` matcher `"Saldo"`)
- **Før-/etter-tester**: `tests/test_dataset_build_fast_*.py` (fem filer)

## Test-dekning

~30 testfiler dekker SB-pipelinen, med ~54 SB-spesifikke tester. Gruppert per fase:

| Fase | Tester |
|---|---|
| **Build** | `test_dataset_build_fast_*.py` (5 filer), `test_saft_reader.py`, `test_saft_tax_table.py`, `test_dataset_cache_sqlite.py` |
| **Refresh/distribusjon** | `test_page_saldobalanse.py`, `test_page_saldobalanse_detail_panel.py`, `test_page_analyse_sb*.py` (3 filer), `test_analyse_sb_refresh_prev_year.py`, `test_ui_main_dataset_analysis.py` |
| **Mapping** | `test_regnskap_client_overrides.py`, `test_rl_mapping_drift.py`, `test_konto_klassifisering.py`, `test_smart_mapping.py`, `test_ml_map_aliases.py` |
| **Integrasjon** | `test_sb_to_regnskap_integration.py` |

Ingen dokumenterte `xfail`/`skip` i disse. Kjent test-ordering-flakiness i `test_ui_main_dataset_analysis.py` (tester passerer i isolasjon men kan feile i full suite pga. andre testers state).

## Videre arbeid (parkert)

Fra [ytelse_status_og_plan.md](ytelse_status_og_plan.md):

- Dataset-versjon early-return (unngå duplikat-rebuild når samme versjon velges)
- Treeview batch-rendering (reduser re-render-kostnad ved store SB)
- Eksport ut av GUI-tråd (åpne mulighet for non-blocking Excel-eksport)

Fra [rl_mapping_drift.md](rl_mapping_drift.md):
- Drift-tjenesten detekterer men korrigerer ikke; revisor må handle manuelt. Et auto-forslag-UI er mulig neste steg.

## Referanser

| Doc | Tema |
|---|---|
| [dataset_pane_versioning.md](dataset_pane_versioning.md) | År-bytte-gotchas i versjons-dropdown |
| [regnskap_overrides.md](regnskap_overrides.md) | Per-år override-modellen |
| [rl_mapping_drift.md](rl_mapping_drift.md) | RL-drift mellom år, deteksjon |
| [ytelse_status_og_plan.md](ytelse_status_og_plan.md) | Performance-status og plan |
| [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) | Modul-struktur + kolonne-vokabular |
| [ansvar_tilordning.md](ansvar_tilordning.md) | Handling-ansvar (nylig separert fra konto-ansvar) |
| [handlinger_modell.md](handlinger_modell.md) | Fem-lags plan-/risiko-/utførelsesmodell (designutkast) |

## Vedlikehold

Når du endrer noe i SB-kjernen:
1. Oppdatér dette dokumentet hvis du endrer byggerekkefølge, cache-nøkler, mapping-prioriteter eller refresh-mønster.
2. Hvis du endrer `READER_VERSION`, si det i commit-meldingen.
3. Hvis du legger til en ny SB-forbruker (ny fane), legg den inn i refresh-distribusjons-tabellen over.
