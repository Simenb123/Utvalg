# Ytelsesarbeid i Utvalg — metodikk og status

Dette dokumentet beskriver **hvordan vi jobber med ytelse** i Utvalg, hva vi
har gjort så langt, og hvor vi står når vi tar opp tråden igjen.

For arkitekturen til selve overvåknings-subsystemet (`src/monitoring/`), se
[monitoring.md](monitoring.md).

**Sist oppdatert:** 2026-04-25

---

## 1. Verktøykassa

Vi har bygget et selvstendig overvåknings-system som lar oss finne ytelses-
problemer raskt:

| Komponent | Hva det gjør |
|---|---|
| [src/monitoring/perf.py](../../src/monitoring/perf.py) | API: `timer()`, `profile()`, `record_event()` — kalles fra koden |
| [src/monitoring/events.py](../../src/monitoring/events.py) | Lagrer hendelsene som JSON-linjer på disk (`events.jsonl`) |
| [src/monitoring/dashboard.py](../../src/monitoring/dashboard.py) | "Utvalg Monitor"-vindu — viser hendelsene live mens du jobber |

### Slik starter du monitoren

1. Start hovedappen som vanlig (Utvalg)
2. Åpne **Admin-fanen** → klikk **"Ytelsesmonitor…"** (passord: `123`)
3. Et eget vindu åpner seg som viser alle målte hendelser i sanntid

### Lese tabellen

| Kolonne | Innhold |
|---|---|
| Tid | Klokkeslett (lokal tid) |
| Område | Hovedkategori (sb, analyse, dataset, startup, …) |
| Operasjon | Hva som ble målt |
| Varighet | Hvor lenge det tok, **alltid i ms** med tusenskille |
| Meta | Ekstra kontekst (cache_hit, mode, antall rader, osv.) |

### Fargekoder på radene

| Farge | Tid | Tolkning |
|---|---|---|
| **Rød** | ≥ 1 000 ms (1 sek) | Alvorlig — påvirker brukeropplevelsen, må fikses |
| **Oransje** | 200-1000 ms | Merkbar lagg — verdt å se på |
| **Gul** | 50-200 ms | Litt seint, men akseptabelt |
| Ingen | < 50 ms | Føles umiddelbart, ikke et problem |

### Detalj-panel (høyre side)

Klikk på en rad for å se:
- Antall målinger (N)
- Median, P95, max
- Sparkline over de siste 20 kjøringene

Bra for å se om noe er **konsekvent tregt** eller bare **enkelte ganger tregt**.

---

## 2. Metodikk — slik finner vi flaskehalser

Dette er den fremgangsmåten vi har funnet som funker best:

### Steg 1: Identifiser hva brukeren faktisk venter på

Ikke gjett. Se i monitoren mens du gjør **akkurat den handlingen som
føles treg**. Eksempler:
- Klikk på en regnskapslinje
- Bytt mellom Regnskapslinje og Saldobalanse
- Åpne en klient
- Bygg et datasett

Kopier (eller skriv ned) hva du ser:
- Hvilke hendelser ble registrert?
- Hvor mange ms hver?
- Hvilken er rød/oransje?

### Steg 2: Finn det største enkelt-problemet

Når du har en liste med tider, finn den **største enkeltverdien** som
brukeren venter på. Typisk:
- En enkelt rød rad på 1+ sekund
- ELLER en sum av flere oransje rader

### Steg 3: Sett inn flere stoppeklokker (hvis nødvendig)

Hvis den trege operasjonen er én stor blokk uten underdeling, **legg
inn 3-7 stoppeklokker inni den** for å se hvor tiden faktisk går.

Eksempel (fra denne prosjekt-runden):

```python
# Før: én måling
with timer("analyse.refresh.refresh_pivot"):
    do_everything()

# Etter: del opp
def _step(label, fn):
    t0 = time.perf_counter()
    fn()
    record_event(f"analyse.refresh.{label}", (time.perf_counter() - t0) * 1000)

_step("refresh_mapping_issues", self._refresh_mapping_issues)
_step("refresh_pivot_dispatch", lambda: refresh_pivot(page=self))
_step("update_ao_count_label", self._update_ao_count_label)
_step("update_mapping_warning_banner", self._update_mapping_warning_banner)
```

Da ser vi nøyaktig hvilken del som er treg.

### Steg 4: Test hypotesen

Be brukeren gjøre samme handling igjen. Se i monitoren:
- Hvilken av de nye stoppeklokkene er størst?
- Stemmer det med hvor du **trodde** problemet var?

Det er normalt at hypotesen bommer. Da legger vi inn enda flere
stoppeklokker, eller graver dypere i den ene som var størst.

### Steg 5: Fiks problemet (med rett mønster — se neste seksjon)

### Steg 6: Mål igjen for å bekrefte

Aldri stol på at fikset hjalp. Mål før og etter.

---

## 3. Fiks-mønstre som funker

Her er mønstrene vi har brukt med suksess. Velg etter hva som passer
problemet:

### A) Mellomlager med id()-basert nøkkel

**Når:** Samme tunge beregning kjøres flere ganger på samme data
mellom brukerinteraksjoner.

**Mønster:**
```python
def _get_thing_cached(page, source_df):
    cache_key = id(source_df)
    cached_key = getattr(page, "_thing_cache_key", None)
    cached = getattr(page, "_thing_cache", None)
    if cached is not None and cached_key == cache_key:
        return cached
    
    result = expensive_compute(source_df)  # tar 200 ms
    page._thing_cache_key = cache_key
    page._thing_cache = result
    return result
```

**Fungerer fordi:** når brukeren laster nytt datasett, får DataFrame
ny `id()` → cache invalideres automatisk.

**VIKTIG:** Bruk **stabile** kilde-objekter som nøkkel, ikke avledede
ting som blir rebygget per kall (f.eks. `_df_filtered` som filter-
systemet bygger på nytt hver gang).

**Brukt i:**
- `analyse_sb_refresh._get_prev_maps_cached` (fjorårs-data)
- `analyse_sb_refresh._resolve_all_accounts_to_rl_cached`
- `analyse_sb_refresh._get_regnr_maps_cached`
- `page_analyse_rl_render._RL_ENRICHED_CACHE`

### B) Mellomlager med save-basert invalidering

**Når:** Disk-data som leses ofte men endres sjelden, gjennom
funksjoner du kontrollerer.

**Mønster:**
```python
_CACHE: dict[str, dict] = {}

def invalidate_cache(client=None):
    if client is None:
        _CACHE.clear()
    else:
        _CACHE.pop(client, None)

def load(client):
    if client in _CACHE:
        return _CACHE[client]
    result = read_disk(client)  # tar 200 ms
    _CACHE[client] = result
    return result

def save(client, data):
    write_disk(client, data)
    invalidate_cache(client)  # ← husk å rydde opp
```

**VIKTIG:** Returverdien deles mellom kall — kallere må **ikke** mutere.
Eller: returner en kopi (men da mister du noe av gevinsten).

**Brukt i:**
- `regnskap_client_overrides.load_comments` / `_account_review`
- `konto_klassifisering.load`

### C) Mellomlager med mtime-basert invalidering

**Når:** Disk-data som kan endres av andre prosesser, eller hvor du
ikke har kontroll over alle skrive-stier.

**Mønster:**
```python
@lru_cache(maxsize=8)
def _read_cached(path: str, mtime_ns: int) -> dict:
    return json.loads(Path(path).read_text())

def read(path):
    mtime = Path(path).stat().st_mtime_ns
    return _read_cached(path, mtime)
```

**Fungerer fordi:** Hver gang fila endres, får den ny mtime → cachen
bygges på nytt automatisk.

**ADVARSEL:** `path.stat()` kan være tregt på OneDrive/nettverk/disker
med antivirus (vi har sett 30-80 ms per kall). Hvis `read()` kalles
mange ganger per klikk, kan stat-kallene bli verre enn cachen var
tenkt å spare. Bruk **save-basert** istedet hvis mulig.

### D) Bakgrunns-preload

**Når:** Tung operasjon som gjøres i en spesifikk fane, men kan
forberedes mens brukeren ser på en annen fane.

**Mønster:**
```python
def _preload_thing_async(self):
    def _worker():
        try:
            from heavy_module import compute_thing
            compute_thing(client, year)  # fyller modul-cache
        except Exception:
            pass
    
    threading.Thread(
        target=_worker, name="thing-preload", daemon=True
    ).start()
```

**Krever:** at den tunge operasjonen er **trådsikker** og at resultatet
mellomlagres et sted senere kall kan finne det.

**Brukt i:**
- `ui_main._preload_ownership_map_async` — sparte 3 sekunder ved første
  åpning av Saldobalanse-fanen

### E) Defere arbeid til etter at viktigste UI er vist

**Når:** Tung operasjon som *trenger* hovedtråden (Tk-widgets), men
som ikke er kritisk for førsteinntrykk.

**Mønster:**
```python
def _refresh_pivot(self):
    # Vis pivot FØRST
    self._build_pivot()
    self._show_pivot()
    
    # Sekundært arbeid (banner, knapper) etterpå
    def _deferred():
        self._build_mapping_warnings()
        self._update_banner()
    
    self.after(50, _deferred)  # IKKE after_idle (se under)
```

**ADVARSEL:** `after_idle` kan trigges av `update_idletasks()` som
finnes i veldig mange Tk-funksjoner. Bruker du `after_idle`, kan
arbeidet plutselig kjøre synkront inni `set_status` eller lignende.
Bruk `after(50, ...)` for å garantere ekte forsinkelse.

**Brukt i:**
- `page_analyse._refresh_pivot` — pivot vises først, mapping-issues
  kommer 50 ms senere

### F) Lat-bygging / lazy loading

**Når:** Komponent som er dyr å bygge, men sjelden brukt.

**Mønster:**
```python
# I stedet for å bygge alle faner ved oppstart:
self.page_dataset = DatasetPage(self.nb)  # eager: bygges nå

# La faner som sjelden brukes vente:
self._fagchat_factory = lambda: FagchatPage(self.nb)  # lazy
self._fagchat_instance = None

def _get_fagchat_page(self):
    if self._fagchat_instance is None:
        self._fagchat_instance = self._fagchat_factory()
    return self._fagchat_instance
```

**Brukt i:** ennå **ikke** brukt i Utvalg, men vurdert som neste skritt
for å kutte cold-start fra 4 sek til ~1 sek.

---

## 4. Antimønstre — ting vi har lært å unngå

### `copy.deepcopy` for "sikkerhets skyld"

Vi prøvde å la `_read_payload_cached` returnere `copy.deepcopy()` av
resultatet for å unngå at kallere muterer cachen. Det tok **100+ ms
per kall** — like tregt som disk-lesinga vi prøvde å unngå.

**Lærdom:** Dokumenter at returverdien er readonly i stedet, og hold
deg til det i kode-review.

### `update_idletasks()` rett etter `after_idle()`

Tk's `after_idle()` planlegger en jobb. Tk's `update_idletasks()`
kjører pending idle-jobber. Hvis du planlegger noe via `after_idle`
og deretter kaller `set_status()` (som kaller `update_idletasks()`),
kjøres jobben din synkront i set_status.

**Lærdom:** Bruk `after(50, ...)` for ekte forsinkelse hvis du vil
være sikker på at jobben venter.

### Cache-nøkkel basert på derived/computed objekter

Vi prøvde først å bruke `id(adjusted_sb_df)` (et avledet objekt) som
del av cache-nøkkelen. Det fungerte ikke — `adjusted_sb_df` ble
rebygget hver gang via `_resolve_analysis_sb_views`, så cachen bommet
alltid.

**Lærdom:** Bruk **kilde-objekter** (`page.dataset`, `page._rl_sb_df`,
`page._rl_intervals`) + state-flagg (`include_ao`) i stedet.

### Antakelser uten måling

Hver gang vi har antatt noe ("det er nok regelbok-matching som er
tregt"), har vi tatt feil. Mål alltid først.

---

## 5. Kart over kjente flaskehalser

Status per 2026-04-25. Tider er typiske medianer fra varm cache.

### App-oppstart

| Hendelse | Tid | Status | Notat |
|---|---|---|---|
| `startup.app.tk_init` | ~150 ms | OK | Tkinter-init |
| `startup.app.splash` | ~250 ms | OK | Splash-vindu |
| `startup.app.theme` | ~5 ms | OK | |
| `startup.app.notebook+footer` | ~10 ms | OK | |
| `startup.app.all_pages` | **~2 200 ms** | ⚠️ Kan forbedres | Lazy-load er neste store skritt |
| Per fane: dataset | ~990 ms | ⚠️ | Største enkeltfane |
| Per fane: admin | ~590 ms | ⚠️ | |
| Per fane: regnskap | ~270 ms | OK | |

**Tiltak gjort:** Fagchat-fanen deaktivert (sparte 534 ms).

**Neste mulige tiltak:** Lazy-loading av admin/dataset/consolidation
(potensielt -2 sek).

### Datasett-bygging (per klient)

| Hendelse | Tid | Status |
|---|---|---|
| `dataset.build.setup_before_cache_load` | ~330 ms | ⚠️ |
| `dataset.build.load_cache` | ~230 ms | OK (disk-lesing) |
| `dataset.apply.update_ml_and_save_mapping` | <5 ms | OK |
| `dataset.apply.store_section_refresh` | ~340 ms | ⚠️ Disk-lesing av versjons-liste |
| `dataset.apply.saft_auto_create_check` | ~340 ms | ⚠️ Disk-sjekk |
| `dataset.apply.set_status` | ~17 ms | OK |
| `dataset.apply.on_ready_callback` | ~95 ms | OK |
| **Totalt `dataset.build_total`** | **~1 500-1 900 ms** | ⚠️ |

**Tiltak gjort:** Forsøkt deferring via `after_idle` — fungerte ikke,
arbeidet ble bare flyttet til `set_status`. **Reell fiks står igjen:**
cache disk-lesinger i `client_store.list_clients/list_versions`.

### Saldobalanse (per åpning av fanen)

| Hendelse | Tid | Status |
|---|---|---|
| Total `sb.refresh` første gang | ~1 100 ms | OK (var 5 100 ms) |
| Total `sb.refresh` cache-hit | ~150 ms | OK |
| `sb.payroll.build_items.classify` | ~250-470 ms | ⚠️ A07-låst |

**Tiltak gjort:**
- Bakgrunns-preload av `ownership_map` (sparte 3 sek)
- Cache av rf1022-bridge (`_a07_group_pairs`)
- Cache av `_resolve_target_kontoer`
- Vektorisering av `_decorate_with_ownership`-loop

**Neste:** A07-refaktor (annen utvikler) blokkerer ytterligere fiks i
`build_items.classify`.

### Saldobalanse — klikk på regnskapslinje

| Hendelse | Tid | Status |
|---|---|---|
| Total per klikk (var) | ~700 ms | |
| Total per klikk (nå) | **~5-10 ms** | ✓ Ferdig |

**Tiltak gjort:**
- Cache `load_comments`, `load_account_review`, `konto_klassifisering.load`
- Fikset treg `app_paths.data_dir()` (kalt 3× per klikk, 60-180 ms hver)
- Cache `_resolve_target_kontoer`
- Cache `_get_prev_maps_cached`, `_get_regnr_maps_cached`

### Analyse-fanen — første bygging etter klient-åpning

| Hendelse | Tid | Status |
|---|---|---|
| `mapping_issues.build_page_mapping_issues` | ~660 ms | ⚠️ Største gjenstående |
| `mapping_issues._compute_mapping_drifts` | ~280-420 ms | OK på cache-treff |
| `refresh_mapping_issues` totalt | ~880-1 280 ms | ⚠️ |
| `pivot.dispatch (Regnskapslinje)` | ~450-700 ms | OK med cache |

**Tiltak gjort:**
- Cache `_compute_mapping_drifts`
- Cache `build_page_mapping_issues` resultat (treff på 2.+ refresh)
- Defererung av `mapping_issues` så pivot vises først (50 ms etter)
- Cache av hele beriket pivot_df

### Analyse-fanen — bytte mellom Regnskapslinje og Saldobalanse

| | Tid | Status |
|---|---|---|
| Cache-treff | ~150 ms | OK |
| Cache-miss (første bytte) | ~600-950 ms | ⚠️ |

**Tiltak gjort:**
- Stoppet `_apply_filters_and_refresh()` på mode-bytte (rebygde alt)
- Cache av `build_rl_pivot` (kalles 3× per bytte)
- Cache av hele beriket pivot_df

**Gjenstår:** "Ekte" fix krever refaktor (to ferdige trær i minnet,
bytt visning i stedet for å bygge på nytt).

---

## 6. Resultater oppsummert

Sammenligning før/etter alt arbeid i denne perioden:

| Operasjon | Før | Etter |
|---|---|---|
| App cold start | ~6 000 ms | ~3 600 ms |
| Saldobalanse første åpning | ~5 100 ms | ~1 100 ms |
| Saldobalanse cache-hit | ~200 ms | ~150 ms |
| **Klikk på regnskapslinje** | **~700 ms** | **~5-10 ms** |
| Mode-bytte (cache-hit) | ~700 ms | ~150 ms |
| `mapping_issues` (deferred) | blokkerte 1 sek | nå usynlig |

---

## 7. Hvor vi står — neste skritt

I prioritert rekkefølge basert på påvirkning på brukeropplevelse:

### Høyt prioritert
1. **Cache `client_store.list_clients/list_versions`** — sparer ~340 ms
   i hver dataset-bygging
2. **Cache `_invalidate_sb_for_current_year`** — sparer ~340 ms
3. **Lazy-load admin/dataset/consolidation-faner** — sparer ~2 sek på
   cold start

### Middels prioritert
4. **Make `build_page_mapping_issues` faster** — sparer ~660 ms
   ved første åpning av klient (selv om nå deferred)
5. **Cache av build_rl_pivot på modulnivå** — flere garantier mot
   cache-miss på mode-bytte

### Lavt prioritert / krever større refaktor
6. **To ferdige pivot-trær** for instant mode-bytte
7. **A07 `classify`-optimering** — blokkert av annen utvikler

---

## 8. Hvordan ta opp tråden

Når du vil jobbe videre med ytelse:

1. **Start hovedappen + monitoren** (Admin → Ytelsesmonitor, passord 123)
2. **Gjør den handlingen som føles treg** — observer monitor live
3. **Finn røde/oransje rader** — det er kandidatene
4. **Velg én å angripe** (start med den største)
5. **Bruk fiks-mønstrene i seksjon 3** — typisk: cache med stabil nøkkel
6. **Mål før/etter** for å bekrefte

Generelle tips:
- **Test alltid på reell klient** — testdata er ofte for små til å vise
  problemer
- **Cold + warm runs** — første gang er ofte 2× tregere; mål begge
- **Ikke glem `meta`-feltet** — `cache_hit=True/False`, `mode=...`,
  osv. hjelper deg å forstå konteksten

---

## 9. Filer å sjekke ut

For å forstå hvordan systemet og fiksene henger sammen:

**Selve overvåknings-systemet:**
- [src/monitoring/perf.py](../../src/monitoring/perf.py)
- [src/monitoring/dashboard.py](../../src/monitoring/dashboard.py)
- [doc/architecture/monitoring.md](monitoring.md)

**Eksempler på fiks-mønstrene fra seksjon 3:**
- Mønster A (id-basert cache): [analyse_sb_refresh.py](../../analyse_sb_refresh.py)
  — søk etter `_get_prev_maps_cached`, `_resolve_all_accounts_to_rl_cached`
- Mønster B (save-basert): [konto_klassifisering.py](../../konto_klassifisering.py)
  — `_MAPPING_CACHE` + `invalidate_cache`
- Mønster C (mtime-basert): [a07_feature/control/rf1022_bridge.py](../../a07_feature/control/rf1022_bridge.py)
  — `_a07_group_pairs_cached`
- Mønster D (preload): [ui_main.py](../../ui_main.py)
  — `_preload_ownership_map_async`
- Mønster E (defer): [page_analyse.py](../../page_analyse.py)
  — `_refresh_pivot` (mapping_issues-deferring)

**Hvor vi har lagt målepunkter:**
- App-init: [ui_main.py](../../ui_main.py) — `startup.app.*`, `startup.page.*`
- Dataset: [dataset_pane.py](../../dataset_pane.py),
  [dataset_pane_build.py](../../dataset_pane_build.py)
- Analyse: [analyse_mapping_ui.py](../../analyse_mapping_ui.py),
  [analyse_sb_refresh.py](../../analyse_sb_refresh.py),
  [page_analyse.py](../../page_analyse.py),
  [page_analyse_rl_render.py](../../page_analyse_rl_render.py)
- Saldobalanse: [saldobalanse_payload.py](../../saldobalanse_payload.py),
  [classification_workspace.py](../../classification_workspace.py)
