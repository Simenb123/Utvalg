# Analyse-fanen — kolonnevisning og kolonnemeny

**Sist oppdatert:** 2026-04-26

Dokumenterer dagens kolonne-håndtering i Analyse-fanen og brukerønsker
om forbedringer. **Ingen kode endres som følge av dette dokumentet** —
det er en plan å gjennomføre senere på riktig tidspunkt. Analyse-fanen
er brukerens eget arbeidsområde, og endringer her bør synkroniseres med
brukerens pågående arbeid.

## 1. Status quo

Analyse-fanen har **to hoved-treeviews** (transaksjon-tre og pivot-tre)
som ikke bruker `ManagedTreeview` (jf. [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md)).
I stedet er det en egen kolonne-stack:

### 1.1 Filer som styrer kolonner

| Fil | Rolle |
|---|---|
| [page_analyse_columns.py](../../page_analyse_columns.py) | Standard kolonnesett per modus + dynamiske operasjoner |
| [page_analyse_columns_presets.py](../../page_analyse_columns_presets.py) | Presets, SB-dynamiske kolonner, cell-styling |
| [page_analyse_columns_widths.py](../../page_analyse_columns_widths.py) | Brukerens lagrede bredder + autofit-logikk |
| [page_analyse_columns_menu.py](../../page_analyse_columns_menu.py) | Høyreklikk-meny på kolonneoverskrift |
| [analyse_treewidths.py](../../analyse_treewidths.py) | Default-bredder basert på navne-hint |
| [src/shared/columns_vocabulary.py](../../src/shared/columns_vocabulary.py) | Heading-tekster + årstall-formattering |

### 1.2 Hva er "standardvisning"?

Standardvisningen avgjøres av en kombinasjon:

1. **Modus** — `Konto` eller `Regnskapslinje` (RL). Bytte via toggle.
2. **Hardkodet defaults** i [page_analyse_columns.py:131](../../page_analyse_columns.py#L131):
   ```python
   ("Konto", "Kontonavn", "Endring", "Sum", "UB_fjor", "Antall", "Endring_pct")
   ```
3. **Dynamiske tilleggskolonner** som kommer/går automatisk:
   - **SB-dynamiske kolonner** (`UB_fjor`, `Endring_fjor`, `Endring_pct`) —
     skjules hvis fjorår-data mangler, vises ellers
   - **BRREG-kolonner** (`BRREG`, `Avvik_brreg`, `Avvik_brreg_pct`) —
     legges til AUTOMATISK i `_pivot_visible_cols` når BRREG-data hentes
     (via `update_pivot_columns_for_brreg()` i page_analyse_columns.py:372)
   - **AO-kolonner** (`UB_for_ao`, `UB_etter_ao`) — vises ved tilleggsposteringer
4. **Brukerpreferanser** — overstyrer hardkodet default per visning, lagret i:
   - `analyse.tx_cols.visible` (transaksjons-tre)
   - `analyse.pivot.visible` (pivot-tre)
   - `analyse.tx_cols.widths` (bredder)
   - `analyse.pivot.widths`

### 1.3 Hvor kolonnebredder kommer fra

I prioritert rekkefølge:

1. **Brukerens lagrede bredde** (`page._tx_col_widths` / `page._pivot_col_widths`,
   persisterer til preferences)
2. **Autofit fra innhold** — `analyse_treewidths.suggest_column_width(name, values)`
   som ser på de første 200 cellene og estimerer bredde fra max-tegnlengde
   (~8px per tegn)
3. **Default per navne-hint** — `analyse_treewidths.default_column_width(name)`
   som matcher kolonne-ID mot kategorier:
   - `_AMOUNT_HINTS = ("belop", "beløp", "sum", "ib", "ub", "endring", "bevegelse")` → 105px
   - `_NARROW_NUMERIC_HINTS = ("antall", "andel", "prosent")` → 58px
   - `_NAME_HINTS = ("navn", "regnskapslinje", "kontonavn")` → 260px
   - `_TEXT_HINTS = ("tekst", ...)` → 320px
   - default → 120px

### 1.4 Heading-tekstene

Fra [columns_vocabulary.py](../../src/shared/columns_vocabulary.py):
```
Endring        → "Δ UB-IB <yy>"      (periode-bevegelse)
Endring_fjor   → "Δ UB <yy>/<yy-1>"  (år-over-år)
Endring_pct    → "Δ % UB <yy>/<yy-1>" (år-over-år, prosentvis)
UB_fjor        → "UB <år-1>"
Sum / UB       → "UB <år>"
```

Endringskolonner får 2-sifret år (`25/24`) for å være kompakte —
verdi-kolonner får 4-sifret år (`UB 2025`).

## 2. Konkrete problemer brukeren peker på (2026-04-26)

### 2.1 BRREG vises som standardvisning

**Problem:** BRREG-kolonnen dukker opp uten at brukeren har valgt det.

**Årsak:** `update_pivot_columns_for_brreg()` legger den automatisk til
i `_pivot_visible_cols` så snart BRREG-data finnes (typisk hentes BRREG
første gang for nye klienter). Endringen persisteres til preferences,
så fra da av VIRKER den som "brukerens valg" selv om brukeren aldri
trykket på den.

**Brukerønske:** BRREG bør være opt-in, ikke opt-out. Eventuelt: vis
som diskret notifikasjon "BRREG-data finnes — vis kolonne?" som
brukeren kan klikke ja/nei på.

### 2.2 Kolonnebredder er hardkodet og treffer ikke

**Problem:** Kolonnen `Endring_pct` (heading "Δ % UB 25/24") er for smal
slik at headeren skjules. Får 105px (matcher `endring` i AMOUNT_HINTS),
men headeren med kompakt format trenger ~140-150px.

**Årsak:** `analyse_treewidths.default_column_width()` matcher ID mot
hint-lister og returnerer fast tall. Det tar ikke hensyn til faktisk
heading-lengde, og pct-kolonner har lengre heading enn beløpskolonner.

**Mulige fikser:**
- **Quickfix A:** Legg til egen hint for `_pct`/`pct` i
  `default_column_width()` med ~140px:
  ```python
  _DELTA_PCT_HINTS = ("_pct", "endring_pct")
  if any(hint in text for hint in _DELTA_PCT_HINTS):
      return 140
  ```
- **Quickfix B:** I `suggest_column_width()`, ta hensyn til full heading-
  lengde fra `analysis_heading()` i tillegg til celle-innhold.
- **Større fix:** Migrere Analyse-fanens treeview til `ManagedTreeview`
  med `ColumnSpec`-bredder som Saldobalanse-fanen.

**Risiko ved quickfix:** Endring i defaults påvirker kun nye brukere
(eksisterende har lagrede bredder). Likevel kan det forvirre etablerte
brukere ved kombinasjoner av "noen kolonner mine, noen nye defaults".

### 2.3 Kunde og leverandør i transaksjons-treet (delvis fikset 2026-04-26)

**Brukerønske:** Skille kunde og leverandør i visningen. Tidligere ble
de slått sammen i én "Kunder"-kolonne via `first_nonempty_series` med
fallback gjennom både kunde- og leverandør-felter.

**Quickfix gjort 2026-04-26:**
- Lagt til `Leverandør` som egen default-kolonne i `DEFAULT_TX_COLS`
- Ny `DEFAULT_SUPPLIER_COLS` med fallback `Leverandør` →
  `Leverandørnavn` → `Supplier` → `SupplierName` →
  `_AnalyseLeverandørnavn` (utledet fra reskontro-bilag)
- Fjernet leverandør-felter fra `DEFAULT_CUSTOMER_COLS` så `Kunder` nå
  viser KUN kunde-info
- `_AnalyseKunder` (utledet fra reskontro-helper) reflekterer kun
  kunde-info, ikke kombinert med leverandør
- `analyse_columns._DISPLAY_ALIAS_GROUPS` har ny `Leverandør` med
  aliaser (Leverandor, Supplier osv.)

**TODO (gjenstår, fremtidig pilot):**
- `page_analyse_export.py:32,51,56` aggregerer fortsatt til "Kunder" i
  Excel-eksport — bør oppdateres for å skille kunde/leverandør i
  eksport-arket også
- `analysis_filters.py:241` har "Kunder" som filter-kategori — vurder
  om "Leverandør" skal bli egen filter
- `overstyring/ui_panel.py:499` har "Kunder" — uavklart hva som ønskes
- For brukere med lagrede kolonneinnstillinger: ny `Leverandør`-kolonne
  vises ikke automatisk (preferanse-systemet bevarer eldre utvalg).
  Brukeren må legge den til manuelt via kolonnemenyen, eller vi kan
  bygge en migrerings-helper som auto-legger inn ny kolonne første
  gang etter oppdatering
- Vurder om "Kunder"-kolonnenavnet bør endres til "Kunde" (entall) for
  konsistens med "Leverandør"

### 2.4 Kolonnenavn — ønsker tydeligere "UB"-prefiks

**Brukerønske:** "Får lyst til å [ha] UB foran begge, da jeg tenker det
bør være standard at dette er fra saldobalansen."

**Status:** Headings har allerede `UB` i Δ-kolonnene (`Δ UB 25/24`,
`Δ % UB 25/24`). Brukeren ser kanskje på en eldre versjon eller mener
en annen kolonne. Mulige tolkninger:

- **Tolkning A:** Brukeren vil ha "Δ UB" → "UB Δ" (sett UB først).
  Krever endring i `heading()`-funksjonen og kan bryte annen kode som
  matcher tekst-strenger.
- **Tolkning B:** Brukeren vil ha 4-sifret år også på Δ-kolonner
  (`Δ UB 2025/2024` i stedet for `Δ UB 25/24`). Krever endring i
  `heading()`.
- **Tolkning C:** Brukeren ser kolonner som ikke har UB-prefiks (f.eks.
  `Endring` heter "Δ UB-IB") og vil at de skal være tydeligere.

**Avklaring trengs** — ta opp med bruker neste gang dette diskuteres.

### 2.5 Kolonne-popupen er ikke intuitiv

**Problem:** Brukeren er usikker på om popupen "fungerer som tiltenkt".

**Status:** Implementert i [page_analyse_columns_menu.py](../../page_analyse_columns_menu.py).
Ikke samme mønster som `ManagedTreeview`'s høyreklikk-kolonneveiler
(som brukes på Saldobalanse, Konsolidering, Handlinger osv.).

**Sannsynlige problemer:**
1. **Inkonsistens** med resten av appen — andre faner har `ManagedTreeview`-
   menyen som er sjekkbox-basert med drag-n-drop. Analyse har en annen,
   eldre meny.
2. **Endringer kan oppleves uforklarlige** når kolonner kommer/går
   automatisk (BRREG, SB-dynamiske) — brukeren tror de selv slo dem
   av/på.
3. **Persistens-logikken** har minst 4 lag (visible_cols, column_order,
   column_widths, modus-spesifikke presets) som ikke alltid synkroniserer
   pent.

**Mulig løsning på sikt:** Migrer Analyse-fanen til `ManagedTreeview`.
Det er listet som "Middels kompleksitet" i
[TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) fordi de dynamiske
kolonnene må bygges via en `build_column_specs()`-funksjon som tar
modus/data-tilstand som input. Krever også å samordne med eksisterende
preset-logikken i `page_analyse_columns_presets.py`.

## 3. Anbefalt rekkefølge for senere implementering

**Steg 1 (lite, ~30 min):** Fix kolonnebredde for `_pct`-kolonner
(quickfix A i 2.2). Lavt risiko siden kun nye brukere påvirkes.

**Steg 2 (lite, ~1 time):** BRREG opt-in. Endre
`update_pivot_columns_for_brreg()` til å vise en knapp/notifikasjon
i stedet for å auto-legge-til. Krever liten UI-justering.

**Steg 3 (avklaring, så ~1 time):** Avklar 2.3 med bruker, så endre
`heading()` deretter. Synkroniser med tester som matcher heading-tekst.

**Steg 4 (større, ~1-2 dager):** Migrer Analyse-fanens treeviews til
`ManagedTreeview`. Krever:
- `build_column_specs(mode, has_prev_year, has_brreg, has_ao)`-funksjon
- Migrering av eksisterende preferences (legacy_pref_keys)
- Verifisere at sortering, drag-n-drop og kolonneveiler fungerer for
  alle modi (Konto, RL, med/uten BRREG, med/uten AO)
- Beholde dynamiske heading-tekster (årstall) ved klient/år-bytte

**Steg 5 (etter steg 4):** Slett `page_analyse_columns_menu.py` og de
3 parallelle sort-motorene som nevnes i TREEVIEW_PLAYBOOK.

## 4. Hvorfor ikke quickfix nå (2026-04-26)

Analyse-fanen er brukerens eget arbeidsområde
(jf. [Work split](../../) memory). Endringer i kolonnehåndtering kan:

- Påvirke brukerens lagrede preferences ved oppgradering
- Bryte tester som matcher heading-tekster
- Forvirre brukeren midlertidig før hen forstår nye defaults

Bedre å gjøre alle endringer som én koordinert pilot når brukeren har
sagt at det er greit og test-suite kan oppdateres samtidig. Dokumentere
alt nå sikrer at vi husker konteksten.

## 5. Relaterte dokumenter

- [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) — `ManagedTreeview`-mønsteret
- [columns_vocabulary.md](columns_vocabulary.md) — kolonne-ID-tabell og
  heading-konvensjoner
- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  felles vokabular-design
