# Implementeringsplan: Globalt design- og fargesystem

**Mål:** Få et helhetlig visuelt språk i Utvalg/AarVaaken som er konsistent
på tvers av alle sider, lett å vedlikeholde, og som faktisk *gjelder* hele
appen — ikke bare token-filen.

**Relaterte dokumenter:**
- [design_system.md](design_system.md) — fargepalett og prinsipper
- [src/shared/ui/tokens.py](../../src/shared/ui/tokens.py) — token-definisjoner

---

## 1. Status i dag (oppdatert 2026-04-28)

### 1.1 Hva som er på plass

| Element | Plassering | Modenhet |
|---|---|---|
| Token-system | [src/shared/ui/tokens.py](../../src/shared/ui/tokens.py) | ✓ Komplett — 30+ tokens, utvidet med 8 nye 2026-04-28 (POS_TEXT_DARK, NEG_TEXT_DARK, INFO_TEXT/SOFT, BORDER_LIGHT, SAGE_WASH_SOFT) |
| Theme-applikator | [theme.py](../../theme.py) | ✓ Komplett — `apply_theme(root)` setter ttk-stiler basert på tokens |
| Excel-tema | [src/shared/ui/excel_theme.py](../../src/shared/ui/excel_theme.py) | ✓ Komplett — `openpyxl`-eksporter bruker samme tokens |
| Splash/loading | [src/shared/ui/loading.py](../../src/shared/ui/loading.py) | ✓ Bruker tokens med fallback-konstanter |
| **PageHeader** | [src/shared/ui/page_header.py](../../src/shared/ui/page_header.py) | ✓ Migrert til 10/15 hovedfaner. Bug-fiks: PIL-bilde-cache er nå Tk-rot-uavhengig |
| **ManagedTreeview** | [src/shared/ui/managed_treeview.py](../../src/shared/ui/managed_treeview.py) | ✓ Brukt på flere sider |
| **make_dialog()** | [src/shared/ui/dialog.py](../../src/shared/ui/dialog.py) | ✓ Brukt på de fleste nye dialoger |
| **enable_treeview_sorting** | [src/shared/ui/treeview_sort.py](../../src/shared/ui/treeview_sort.py) | ✓ Brukt selektivt |
| **Lint-test for hardkodede farger** | [tests/test_no_hardcoded_colors.py](../../tests/test_no_hardcoded_colors.py) | ✓ 3 tester: outside_allowlist, total_count, stale_entries. BASELINE = 513 (fra 652) |
| Designdokumentasjon | [design_system.md](design_system.md) | ✓ Oppdatert med lint-regel og nye tokens |

### 1.2 Hva som mangler / er rotete

| Problem | Omfang | Konsekvens |
|---|---|---|
| **Hardkodede `"#XXXXXX"`-farger i sidekoden** | 513 forekomster (ned fra 652), spredt på ~50 filer i allowlist | Tokens-endringer når fortsatt ikke disse, men gjelden krymper |
| Verstinger som gjenstår | fagchat (95, midlertidig deaktivert), spredte dialoger og audit_actions | Ryddes når noen uansett rører fila |
| `PageHeader` på 5 av 15 hovedfaner gjenstår | A07 (annen utvikler), Dataset, Saldobalanse, Driftsmidler, Konsolidering-sub-tabs | Inkonsistent header-layout på resterende faner |
| Token-endringer kjøres ikke gjennom regresjonstester | Bare manuell verifikasjon | Risiko for at en token-endring bryter en spesifikk visning |
| Ingen automatisk Excel/GUI-konsistens-sjekk | Manuell visuell verifikasjon | Eksporten kan drifte fra GUI over tid |

### 1.3 Hva er allerede bra

- Tokens-filen er **velstrukturert** og dekker det den trenger
- `theme.py` bruker `clam`-tema som er minst dårlig av Tkinter-temaene
- Designprinsippene fra det nye `design_system.md` er fornuftige og
  tilpasset audit-bruk (lesbarhet > estetikk)
- Komponentene `ManagedTreeview`, `make_dialog`, `treeview_sort` er
  godt etablerte mønstre
- Logo-farger er **eksakt kalibrert** mot AarVaaken.png nå

---

## 2. Optimalt målbilde

Det vi sikter mot — ikke nødvendigvis i én stor migrering.

### 2.1 Visuell konsistens

- **Alle hovedfaner** har `PageHeader` med refresh + eksport på samme sted
- **Alle popups** bruker `make_dialog()` (ingen rå `tk.Toplevel`)
- **Alle tabeller** bruker `ManagedTreeview` der det er mer enn 3 kolonner
  med persistens-behov
- **Alle Excel-eksporter** bruker `excel_theme` så fargene matcher GUI

### 2.2 Token-disiplin

- **Null hardkodede farger** for standard-tilfeller (bakgrunn, tekst, status)
- **Dokumenterte unntak** (chart-kategorier, ekstern brand-farge) merket
  med kommentar
- **Ny farge = ny token** — aldri introduser ad-hoc hex-streng

### 2.3 Vedlikeholdbarhet

- Endring av logo-farge → endre én verdi i `tokens.py` → hele appen følger
- Excel-eksport endrer seg automatisk
- Ingen "halvgammel-halvny"-tilstand der noen sider er oppdatert og andre ikke

### 2.4 Tkinter-realisme

- Vi sikter ikke på pixel-perfekt vaak.no-match
- Vi sikter på **visuell merkevare-gjenkjennelse** og funksjonell skjønnhet
- Vi godtar Tkinters begrensninger (rektangulære knapper, ingen myke
  skygger) og dokumenterer dem

---

## 3. Implementeringsplan i faser

Realistiske faser. Hver gir gevinst alene, ingen krever de neste.

### Fase 1: Fundament (ferdig ✓)

- ✓ `tokens.py` med komplett palett
- ✓ `theme.py` setter ttk-stiler fra tokens
- ✓ `design_system.md` dokumenterer reglene
- ✓ `PageHeader`-komponent eksisterer (pilot på Regnskap)
- ✓ Logo-farger kalibrert mot AarVaaken.png

### Fase 2: Disiplin — hindre ny gjeld (ferdig 2026-04-28 ✓)

**Mål:** Stoppe blødningen før vi rydder eksisterende kode.

**Leverte:**
- ✓ **pytest-test** [tests/test_no_hardcoded_colors.py](../../tests/test_no_hardcoded_colors.py)
  med tre kontroller:
  - `test_no_hardcoded_colors_outside_allowlist` — feiler ved nye filer
    med `"#XXXXXX"` utenfor allowlist
  - `test_total_hardcoded_color_count_does_not_increase` — BASELINE-tak
    som synker over tid (652 → 513)
  - `test_allowlist_entries_actually_exist` — fanger stale entries
- ✓ **Per-linje override** via `# design-exception: <grunn>`-kommentar
  på samme linje
- ✓ **Allowlist** med kjente rotete filer som ikke flagges før ryddet
- ✓ **Dokumentert** i [design_system.md §3.1](design_system.md)

**Pre-commit-hook ble vurdert men droppet:** Repoet har ingen
pre-commit-infrastruktur. Pytest-testene fyller samme funksjon (kjøres
som CI-erstatning).

### Fase 3: PageHeader-rollout (ferdig 2026-04-28, 10/15 ✓)

**Mål:** Konsistent header på alle hovedfaner.

**Migrert** (10 faner):
- ✓ Regnskap (pilot)
- ✓ Skatt
- ✓ Utvalg
- ✓ MVA
- ✓ Materiality (Vesentlighet)
- ✓ AR (Aksjonærregisteret) — sporbarhetsstripe beholdt
- ✓ Scoping
- ✓ Reskontro
- ✓ Analyse — filterlinje beholdt som egen rad under header
- ✓ Konsolidering — toolbar beholdt som egen rad under header

**Gjenstår** (5 faner):
- A07 — annen utvikler jobber med fanen
- Dataset
- Saldobalanse
- Driftsmidler
- Konsolidering-sub-tabs (resultat, mapping, eliminering osv. — egne mini-headers)

**Bug-fiks som kom underveis:**
[src/shared/ui/page_header.py](../../src/shared/ui/page_header.py) —
PhotoImage caches per Tk-rot, ikke globalt. Fikser
`image "pyimageN" doesn't exist`-feil når tester ødelegger og
gjenoppretter Tk-roten mellom kjøringer. PIL-bildet (kostbart å
prosessere) caches fortsatt globalt.

### Fase 4: Migrere hardkodede farger (delvis ferdig 2026-04-28)

**Strategi:** **IKKE en stor rydde-PR.** Vi migrerer når vi uansett rører
en fil. Pytest-allowlist (Fase 2) krymper når en fil ryddes.

**Migrert hittil** (139 farger fjernet, 652 → 513):

| Fil | Til tokens | Markert | Dato |
|---|---|---|---|
| `src/pages/scoping/frontend/page.py` | 4 | 32 | 2026-04-28 |
| `src/pages/skatt/page.py` | 5 | 4 | 2026-04-28 |
| `src/audit_actions/statistikk/frontend/page.py` | 13 | 18 | 2026-04-28 |
| `src/pages/ar/frontend/page.py` | 3 | 31 lines | 2026-04-28 |
| `src/pages/ar/frontend/chart.py` | 0 | 19 lines | 2026-04-28 |

**Gjenstår** i allowlist (~50 filer):

1. **fagchat** (95 farger) — midlertidig deaktivert, lav prioritet
2. Diverse dialoger (analyse_*, audit_actions, dataset, mva-popups)
3. Kompakte UI-helpers (managed_treeview, loading, theme.py)

**Verifikasjon:** [tests/test_no_hardcoded_colors.py](../../tests/test_no_hardcoded_colors.py)
viser BASELINE-tallet og advarer hvis det ikke er oppdatert etter rydding.

### Fase 5: Komponentbibliotek-utvidelser (~4-6 t)

**Mål:** Plukke opp gjentatte mønstre og lage felles komponenter.

**Kandidater:**
- **`PillBadge`** — den lille piller-stilen brukt på Datasett-fanen,
  gjentatt i flere varianter
- **`StatusIndicator`** — "klart" / "advarsel" / "feil"-bokser som finnes
  spredt ad-hoc
- **`KpiCard`** — nøkkeltall-bokser i Regnskap, Skatt, Konsolidering ser
  ut til å være lignende men ulikt implementert

**Prosess:**
1. Identifiser 3+ steder med samme mønster
2. Bygg felles komponent i `src/shared/ui/`
3. Migrer kallesteder
4. Dokumenter i `design_system.md`

### Fase 6: Excel/GUI-konsistens (~2-3 t)

**Mål:** Eksporter ser likt ut som GUI-en.

**Leveranser:**
- Verifiser at alle excel-eksporter går via `excel_theme` (ikke ad-hoc
  PatternFill)
- Test som genererer en eksempel-Excel og en eksempel-GUI-render og
  sammenligner dominant fargepalett
- Dokumenter eksport-stilarter i `design_system.md`

### Fase 7: Polish (kontinuerlig)

- Splash/loading-konsistens
- Tooltip-styling (PageHeader har basic tooltip — kan utvides)
- Hover-states på interaktive elementer (innenfor Tkinter-rammen)
- Keyboard-navigasjon (F5 for refresh er etablert — kan utvides)

---

## 4. Avhengigheter mellom faser

```
Fase 1 ✓ ────►  Fase 2 ──────►  Fase 4
                  │                 │
                  ▼                 │
              Fase 3 ──────────────┤
                                    ▼
                                Fase 5 ──► Fase 6 ──► Fase 7
```

- Fase 2 (disiplin) **bør** komme før Fase 3-4 — ellers risikerer vi at
  migrering legger inn nye hardkodede farger
- Fase 3 (PageHeader) og Fase 4 (token-migrering) er **uavhengige** — kan
  gjøres parallelt
- Fase 5+ kommer naturlig etter at det grunnleggende er på plass

---

## 5. Tidsestimat-oppsummering

| Fase | Estimat | Faktisk | Status |
|---|---|---|---|
| 1 — Fundament | Ferdig | — | ✓ |
| 2 — Disiplin | 3-4 t | ~1,5 t | ✓ Ferdig 2026-04-28 |
| 3 — PageHeader-rollout | 6-8 t | ~7 t (10/15 faner) | 🟡 Delvis (A07 + 4 til gjenstår) |
| 4 — Migrere hardkodede | 10-20 t totalt (spredt) | ~3 t (139/652) | 🟡 Delvis — fortsetter on-touch |
| 5 — Komponentbibliotek | 4-6 t | — | ⏳ Ikke startet |
| 6 — Excel-konsistens | 2-3 t | — | ⏳ Ikke startet |
| 7 — Polish | Kontinuerlig | — | ⏳ Ikke startet |

**Total brukt:** ~11,5 t / ~30 t estimat. Resten spres over neste uker
(on-touch-strategi for Fase 4) eller venter på behov (Fase 5–7).

---

## 6. Suksess-kriterier

Vi vet vi er ferdige når:

1. ✓ **Lint-regel:** Pytest-test avviser nye hardkodede farger (Fase 2 ferdig 2026-04-28)
2. 🟡 **Telling:** Pytest-test viser ≤ 50 hardkodede farger igjen — er på 513 (mål: under 100)
3. 🟡 **Konsistens:** 10 av 15 hovedfaner har `PageHeader`. Gjenstår: A07, Dataset, Saldobalanse, Driftsmidler + Konsolidering-sub-tabs
4. 🟡 **Brand-bytte-test:** Delvis oppfylt — endring av `BG_SAND` reflekteres i alle migrerte sider, men 513 hardkodede farger ignorerer fortsatt token-endringer
5. ✓ **Dokumentasjon:** Design_system.md oppdatert med lint-regel, nye tokens, og dette planen
6. ⏳ **Excel-konsistens:** Ikke verifisert ennå (Fase 6)

---

## 7. Hva vi bevisst IKKE skal gjøre

For å sikre at scope ikke siver:

| Ikke gjør dette | Hvorfor |
|---|---|
| Rive ut Tkinter for noe annet (Qt, web) | For stor jobb, ikke verdt det for et internt verktøy |
| Forsøk pixel-perfekt vaak.no-match | Tkinter er ikke web — vil alltid skuffe |
| Stor "rydd opp alle 630 hardkodede farger"-PR | Ufeasible — for mange filer i én commit, regresjons-risiko |
| Custom-tegne knapper med runde hjørner via Canvas | Vedlikeholdsmareritt, ingen tilgang til OS-styling |
| Animasjoner / overganger | Tkinter har dårlig støtte, lite gevinst |
| Light/dark-mode toggle | Eksperimentelt, ikke etterspurt |
| Fontavhengige features (variable fonter, ligaturer) | Tkinter-støtte er svak, OS-avhengig |

---

## 8. Veikart for neste konkrete steg

Hvor vi er nå (etter 2026-04-28):

**Umiddelbart:**
- ⏳ Smoke-teste appen i drift — sjekk at PageHeader-migreringene fungerer
  visuelt på alle 10 fanene som er migrert
- ⏳ Vente på at A07-utvikler er ferdig før vi tar A07-PageHeader

**Neste sesjon (når noen rører de gjenstående fanene):**
- Migrere PageHeader for Dataset, Saldobalanse, Driftsmidler
- Rydde resterende allowlist-filer i Fase 4 ettersom de berøres

**Lengre sikt:**
- Fase 5 (komponentbibliotek) — vent til vi ser konkrete duplikater
- Fase 6 (Excel-konsistens) — gjør når neste excel-eksport endres
- Reaktiver fagchat → migrer dens 95 hex til tokens samtidig

---

## 9. Når dette dokumentet skal oppdateres

- Etter hver fullført fase (oppdater status-tabellen)
- Når et nytt komponent legges til komponentbiblioteket
- Hvis tidsestimatene viser seg urealistiske (juster og forklar hvorfor)
- Hvis vi oppdager nye anti-mønstre som bør med i "ikke gjør"-listen

---

## 10. Eierskap og beslutninger

| Beslutning | Hvem |
|---|---|
| Endring av token-verdier (palett-tweak) | Utvikler + bruker-aksept |
| Ny token (utvider palett) | Utvikler — dokumenter i design_system.md |
| Fjerning av token | Krever migrasjons-PR — ingen løse ender |
| Komponent-API-endringer | Utvikler — oppdater dokumentasjon samtidig |
| Stor stilendring (fonts, base-tema) | Bruker-konsultasjon — påvirker hele appen |
