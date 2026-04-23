# Ytelse — status og plan

**Sist oppdatert:** 2026-04-23

Dokumenterer arbeidet med å gjøre Utvalg-appen mer responsiv ved store
datasett, basert på kombinert kode-analyse, profilering og syntetisk
benchmarking.

## Bakgrunn

Brukeren rapporterte at Analyse-fanen tok lang tid å laste etter at et
datasett var importert. En ekstern kode-analyse pekte på tre hovedhypoteser:

1. **For mange refresh-kall etter datasett-last.** `_on_data_ready` oppdaterte
   13 sider umiddelbart, mesteparten i bakgrunnen.
2. **Tab-bytte trigger full rebuild.** Treeview-fyll rad-for-rad er treg
   for store sett.
3. **Eksport går via Treeview.** Tar med all GUI-state, ikke direkte
   DataFrame.

Vi besluttet å verifisere med faktiske målinger framfor å anta — to nye
verktøy ble bygget for å gjøre dette enkelt fremover.

## Verktøy for å måle ytelse

### Profile-flagg på Analyse-refresh

Sett miljøvariabel før appen startes:

```powershell
$env:UTVALG_PROFILE_REFRESH=1; python app.py
```

Da skriver `_run_heavy_refresh_staged` én linje pr refresh til loggen
(via `log.warning`):

```
[REFRESH PROFILE] | total=4823ms | 0_reload_rl_config=12ms |
1_build_filtered_df=189ms | 2_refresh_pivot=4380ms |
3_refresh_transactions_view=210ms | 4_refresh_detail_panel=8ms |
5_adapt_columns+update_data_level=24ms
```

Implementert i [page_analyse_refresh.py](../../page_analyse_refresh.py)
(commit `5bac77d`). Default av — null overhead i prod.

### CLI-benchmark for Analyse-pipeline

```bash
python scripts/bench_analyse_refresh.py [--rows N] [--accounts N] [--repeats N]
```

Genererer syntetisk dataset (default 100k rader / 300 kontoer) og kjører
de tunge operasjonene isolert. Rapporterer min/median/mean/max over N
repetisjoner. Brukes til å diagnostisere hvor tiden går — uten å måtte
laste ekte klientdata via GUI.

Implementert i [scripts/bench_analyse_refresh.py](../../scripts/bench_analyse_refresh.py)
(commit `32f119d`).

## Hva er gjort

### Tiltak 1: Lazy refresh etter datasett-last (commit `b5fd55b`)

**Før:** `ui_main._on_data_ready` planla refresh for **13 faner** spredd
over 310ms (Resultat, Saldobalanse, Regnskap, Materiality, MVA, Lønn,
Skatt, Reskontro, Documents, Statistikk, Driftsmidler, Oversikt + Analyse).
Alle kjørte i samme GUI-tråd, hver gjorde tung pandas-logikk.

**Etter:** Kun Analyse refreshes umiddelbart (det er fanen brukeren bytter
til). Andre faner havner i `App._post_load_dirty_refreshers` og refreshes
**første gang brukeren aktiverer fanen**. Hvis brukeren aldri besøker
f.eks. Skatt, kjøres den aldri.

Implementert i [ui_main.py:_on_data_ready](../../ui_main.py) +
[ui_main.py:_on_notebook_tab_changed](../../ui_main.py).

**Effekt:** "Tid til Analyse er klar" blir mye kortere fordi 12 andre
faner ikke lenger gjør jobb i bakgrunnen. Første besøk til Saldobalanse/
Reskontro tar samme tid som før, men nå er det forutsigbart.

### Tiltak 2: Cache av RL-config (commit `2824666`)

**Funn fra bench (200k rader, 500 kontoer):**
- `add_previous_year_columns` brukte **337ms**
- `_aggregate_sb_to_regnr` brukte **411ms**
- Roten: `regnskap_config.load_kontoplan_mapping()` og
  `load_regnskapslinjer()` leste fra disk **hver gang** (250-300ms pr kall)

Disse ble kalt ofte fordi `_resolve_regnr_for_accounts` falt tilbake til
disk-load når `regnskapslinjer=None` ble sendt inn (typisk fra
`add_previous_year_columns` til `_aggregate_sb_to_regnr`).

**Fix A:** Modul-nivå cache i [regnskap_config.py](../../regnskap_config.py)
med mtime-invalidering. Filene leses kun fra disk første gang ELLER når
mtime endres (brukeren har lagret ny config). `.copy()` returneres så
kallere ikke kan korrumpere cache ved muts.

**Fix B:** [previous_year_comparison.py](../../previous_year_comparison.py)
`add_previous_year_columns` sender nå med `regnskapslinjer`-DataFrame
til `_aggregate_sb_to_regnr`, så det interne kallet aldri trenger
disk-load.

**Effekt (median av 5 kjøringer, 200k/500):**
| Operasjon | Før | Etter |
|---|---|---|
| `add_previous_year_columns` | 337ms | **36ms** (−89%) |
| `build_rl_pivot (med fjor)` | 543ms | **359ms** (−34%) |

Cachen vil også hjelpe andre konsumenter (workpaper-eksporter, ml_map_utils,
diverse rapporter).

## Status

**Verifisert i syntetisk bench:**
- `add_previous_year_columns` raskere fra 337ms → 36ms.
- `build_rl_pivot (med fjor)` raskere fra 543ms → 359ms.

**Ikke verifisert ennå:**
- Faktisk forbedring i appen med ekte klientdata. Bruker bør kjøre
  `UTVALG_PROFILE_REFRESH=1` med en stor klient og rapportere tallene.
- Effekt på "kald" oppstart av appen.

**Ikke gjort:**
- Andre tiltak fra rapporten (se nedenfor).

## Plan videre

Rangert etter forventet effekt vs implementasjonskost. Anbefales å gå
i rekkefølge.

### A. `dataset_version` + early return (Quick win 2 fra rapport)

Hver fane huske sist behandlede dataset-versjon. Hvis brukeren bytter
fane og tilbake uten at datagrunnlaget faktisk er endret, returner
tidlig fra `refresh_from_session()` i stedet for å bygge alt på nytt.

Mønsteret finnes allerede partielt:
- `AnalysePage._session_cache_key` ([page_analyse_refresh.py](../../page_analyse_refresh.py))
- `SaldobalansePage._base_payload_cache_key`

Generaliser til et felles enkelt system: `session.dataset_version` (int
som økes ved `_on_data_ready`) + `page._last_seen_dataset_version` per
fane.

**Forventet effekt:** Stor for tab-navigering (gå frem/tilbake). Ingen
effekt på første-last (vi bygger uansett).

**Kostnad:** Lav-moderat. Trenger oppdatering i ~10 fane-klasser.

### B. Treeview batch-rendering for store tabeller

`SaldobalansePage._render_df()` og `reskontro_selection.apply_filter()`
bygger hver rad og setter inn én etter én. For 5 000–10 000 rader fryser
GUI-en målbart.

**Tiltak:** Batch innsetting i porsjoner med `after(...)` mellom hver
batch (f.eks. 200 rader / 10ms). Eller progressive load: vis først 500
rader, last resten i bakgrunnen.

**Forventet effekt:** Stor for opplevd respons (GUI fryser ikke), middels
for total CPU-tid.

**Kostnad:** Moderat. Krever refaktor av to-tre tunge `_render`-metoder.

### C. Eksport ut av UI-tråd

`export_active_view_excel` og `nokkeltall_report.save_report_pdf`
(Playwright) kjører synkront i hovedtråd. Eksport av store visninger
fryser appen.

**Tiltak:**
- Kjør eksportjobben i bakgrunnstråd via `LoadingOverlay.run_async`
  (vi har den allerede).
- Eksporter direkte fra DataFrame der mulig — ikke fra Treeview-celler.
- For Excel: kutt out auto-bredde-skanning over alle rader; bruk header
  + utvalg av rader.

**Forventet effekt:** Stor for opplevd flyt under eksport. Total tid
omtrent som før, men UI fryser ikke.

**Kostnad:** Moderat. Per-eksportør jobb.

### D. Fjern unødvendige `df.copy()` i Resultat/Utvalg-flyten

`UtvalgPage.on_dataset_loaded()` gjør `df.copy()`, `apply_filters()`
kopierer igjen, og `filter_utvalg_dataframe()` starter også med
`df_all.copy()`. Tre fullkopier av samme datasett.

**Forventet effekt:** Lav for opplevd lagg, men reduserer minnepress.

**Kostnad:** Lav, men krever forsiktig testing — `.copy()` er der
sannsynligvis for å unngå muts av delt state.

### E. Optimalisere `_aggregate_sb_to_regnr` videre

Etter cache-fixen er funksjonen fortsatt ~300ms i bench (når kalt
*uten* regnskapslinjer-arg). I produksjonsbruken (med arg) er den
mye raskere, men kall som ikke er fikset enda kan ha samme problem.

**Tiltak:** Audit alle kall til `_resolve_regnr_for_accounts` og
`_aggregate_sb_to_regnr` for å sikre at `regnskapslinjer` alltid
sendes med når den er tilgjengelig.

**Forventet effekt:** Moderat — gjelder kun for kall som ennå ikke er
fikset.

**Kostnad:** Lav.

## Anti-mønstre å unngå

Funnet under bench-arbeidet:

- **`df.apply(lambda r: ..., axis=1)`** — pandas row-wise apply er flere
  størrelsesordener tregere enn vektorisert numpy. Vi fjernet ett tilfelle
  i `previous_year_comparison.py` (men hovedflaskehalsen var disk-IO,
  ikke apply).
- **Disk-IO i hot path uten cache** — selv "billig" JSON-lesing koster
  250-300ms når den gjøres flere ganger pr refresh. Cache med mtime-sjekk
  er enkelt og trygt.
- **`set(df["col"].tolist())` inni list-comprehension** — settet bygges
  pr iterasjon. Bygg utenfor.

## Relaterte dokumenter

- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) — pågående
  src/-omorganisering og felles kolonne-vokabular
- [analyse_pivot_engine.md](analyse_pivot_engine.md) — hvordan RL-pivoten
  bygges fra HB/SB-data
