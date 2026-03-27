# Konsolidering MVP — Komplett spesifikasjon

## 1. Domene- og datamodell

### Hierarki

```
ConsolidationProject          (1 per klient/aar)
  ├── companies: [CompanyTB]  (N importerte selskaper)
  │     └── tb: DataFrame     (normalisert TB, lagret som parquet)
  ├── mapping_config          (felles intervaller + per-selskap overstyringer)
  ├── eliminations: [EliminationJournal]   (M elimineringsjournaler)
  │     └── lines: [EliminationLine]
  └── runs: [RunResult]       (historikk over kjoeringer)
```

### Dataklasser

```python
@dataclass
class ConsolidationProject:
    project_id: str               # uuid4
    client: str                   # display_name fra session
    year: str
    created_at: float             # time.time()
    updated_at: float
    companies: list[CompanyTB]
    mapping_config: MappingConfig
    eliminations: list[EliminationJournal]
    runs: list[RunResult]

@dataclass
class CompanyTB:
    company_id: str               # uuid4
    name: str                     # brukervalgt navn, f.eks. "Morselskap AS"
    source_file: str              # opprinnelig filnavn
    source_type: str              # "excel" | "csv" | "saft"
    imported_at: float
    row_count: int
    has_ib: bool                  # om IB-kolonnen finnes og er ikke-null

@dataclass
class MappingConfig:
    # Alle selskaper mapper mot samme globale intervaller + regnskapslinjer
    # fra regnskap_config. Per-selskap overstyringer loeser avvik.
    company_overrides: dict[str, dict[str, int]]
    # company_id -> {konto: regnr, ...}

@dataclass
class EliminationJournal:
    journal_id: str               # uuid4
    name: str                     # f.eks. "Internhandel", "Konsernfordringer"
    created_at: float
    lines: list[EliminationLine]

    @property
    def is_balanced(self) -> bool:
        return abs(sum(l.amount for l in self.lines)) < 0.005

    @property
    def net(self) -> float:
        return sum(l.amount for l in self.lines)

@dataclass
class EliminationLine:
    regnr: int                    # konsernlinje (regnskapslinje-nummer)
    company_id: str               # hvilket selskap linjen treffes paa
    amount: float                 # positiv = debet, negativ = kredit
    description: str

@dataclass
class RunResult:
    run_id: str                   # uuid4
    run_at: float
    company_ids: list[str]
    elimination_ids: list[str]
    warnings: list[str]
    result_hash: str              # SHA256 av resultat-DataFrame
```

### Invarianter

- `companies` kan vaere 0..N. Gate 2 krever minst 2.
- `eliminations` kan vaere 0..M. Alle er valgfrie.
- `mapping_config.company_overrides` refererer kun til `company_id`-er som finnes i `companies`.
- `EliminationLine.company_id` maa referere til et eksisterende selskap.
- `RunResult` er immutable etter opprettelse — en ny kjoeringen gir en ny RunResult.


## 2. Elimineringsjournal — semantikk

### Prinsipp: Justeringslag, ikke mutasjon

Elimineringer foelger **samme prinsipp som tilleggsposteringer** i Analyse:

```
grunnlag (raa TB per selskap)
  + justeringslag (elimineringsjournaler)
  = effektiv konsolidert visning
```

- Raa TB per selskap endres **aldri** av elimineringer.
- Elimineringer lagres separat og legges paa ved kjoeretidspunkt.
- Resultatet viser: `sum foer eliminering | eliminering | konsolidert`.
- Brukeren kan naar som helst se raa TB uten elimineringer.

### Journalstruktur

Hver journal er en navngitt batch med debet/kredit-linjer:

| Felt | Type | Beskrivelse |
|------|------|-------------|
| regnr | int | Konsernlinjenummer (fra regnskapslinjer) |
| company_id | str | Hvilket selskap linjen gjelder |
| amount | float | Positiv = debet, negativ = kredit |
| description | str | Fritekst, f.eks. "Internhandel varesalg" |

### Balansevalidering

- Hver journal valideres individuelt: `sum(lines.amount) == 0`.
- Ubalanse er en **advarsel**, ikke en blokkering.
- GUI viser tydelig balanseindikator per journal.
- Run-resultatet inkluderer warnings for ubalanserte journaler.

### Typiske elimineringsjournaler

1. **Internhandel** — eliminere inntekt/kostnad mellom selskaper
2. **Konsernfordringer/-gjeld** — eliminere mellomvaerende
3. **Utbytte** — eliminere konserninternt utbytte
4. **Urealisert gevinst** — eliminere interngevinst paa eiendeler


## 3. Workspace-spec — GUI

### Layout

```
+--------------------------------------------------------------+
| Verktoeylinje rad 1:                                         |
|   [Importer selskap]  [Kjoer konsolidering]  [Eksporter]     |
| Verktoeylinje rad 2 (status):                                |
|   "3 selskaper | 2 elimineringer | Siste run: OK 14:32"     |
+------------------------------+-------------------------------+
|                              |                               |
| VENSTRE PANEL (tabs):        | HOEYRE PANEL (tabs):          |
|                              |                               |
|  [Selskaper]  [Eliminering]  |  [Detalj]  [Resultat]        |
|                              |                               |
| *** Tab Selskaper ***        | *** Tab Detalj ***            |
| Treeview:                    | Viser valgt selskaps TB:      |
|  Navn | Kilde | Rader | %Map |  Konto | Kontonavn | IB | UB  |
|  Mor AS | saft | 342 | 98%  |  ...                          |
|  Datter AS | xlsx | 89 | 95% |  Umappede kontoer markert     |
|                              |  med "review"-tag             |
| Hoeyreklikk:                 |                               |
|  - Fjern selskap             | *** Tab Resultat ***          |
|  - Importer paa nytt         | Konsernoppstilling:           |
|  - Vis mapping-review        |  Nr | Linje | Mor | Dat | Elim | Kons |
|                              |  100 | Salg | 500 | 200 | -50 | 650 |
| *** Tab Eliminering ***      |  ...sumlinjer med tags...     |
| Treeview (journaler):        |                               |
|  Journal | Linjer | Balanse  |                               |
|  Internhandel | 4 | OK      |                               |
|  Konsgj. | 2 | Ubalanse!    |                               |
|                              |                               |
| Valgt journal -> linjer:     |                               |
|  Regnr | Selskap | Beloep   |                               |
|  3000 | Mor | -500 000       |                               |
|  4000 | Datter | 500 000    |                               |
|  [Legg til] [Slett]         |                               |
|                              |                               |
+------------------------------+-------------------------------+
| Statuslinje: Konsolidering | Klient X / 2025 | TB-only      |
+--------------------------------------------------------------+
```

### Interaksjonsmoenster (fra INTERACTION_GRAMMAR.md)

| Handling | Oppfoersel |
|----------|-----------|
| Klikk selskap i venstreliste | Laster TB i hoeyrepanelet (Detalj-tab) |
| Dobbeltklikk selskap | Aapner mapping-review i Detalj |
| Enter paa selskap | Samme som dobbeltklikk |
| Klikk journal i Eliminering-tab | Viser journallinjer under |
| F2 paa journal | Inline-redigering av journalnavn |
| Delete paa journallinje | Fjerner linje (med bekreftelse) |
| Ctrl+C paa Resultat-tree | Kopierer synlige rader som TSV |
| Escape | Lukker eventuelle dialoger |

### Tags og farger

| Tag | Bruk | Farge |
|-----|------|-------|
| `sumline` | Sumlinjer i resultat | #EDF1F5 bakgrunn |
| `sumline_major` | Hovedtotaler | #E0E4EA bakgrunn |
| `neg` | Negative beloep | Roed tekst |
| `review` | Umappede kontoer | #FCEBD9 bakgrunn |
| `done` | Fullstendig mappet selskap | #E2F1EB bakgrunn |
| `warning` | Ubalansert journal | #FCEBD9 bakgrunn |

### TB-only som fullverdig modus

Konsolidering er **designet for TB-only**. Hele flyten — import, mapping,
eliminering, run, eksport — fungerer med kun saldobalanse. Det finnes ingen
avhengighet til hovedbok/transaksjoner. Statuslinjen viser "TB-only" for
informasjon, men dette er normalmodusen, ikke en degradert tilstand.


## 4. Storage-kontrakt

### Katalogstruktur

```
{clients_root}/{klient}/years/{YYYY}/consolidation/
    project.json                 # Serialisert prosjekt (alt unntatt DataFrames)
    companies/
        {company_id}.parquet     # Normalisert TB per selskap
    exports/
        {run_id}_workbook.xlsx   # Genererte eksporter
```

### project.json — format

```json
{
  "schema_version": 1,
  "project_id": "uuid",
  "client": "Eksempel AS",
  "year": "2025",
  "created_at": 1711540000.0,
  "updated_at": 1711545000.0,
  "companies": [
    {
      "company_id": "uuid",
      "name": "Morselskap AS",
      "source_file": "mor_tb_2025.xlsx",
      "source_type": "excel",
      "imported_at": 1711540100.0,
      "row_count": 342,
      "has_ib": true
    }
  ],
  "mapping_config": {
    "company_overrides": {
      "<company_id>": {"1920": 1900, "3010": 3000}
    }
  },
  "eliminations": [
    {
      "journal_id": "uuid",
      "name": "Internhandel",
      "created_at": 1711541000.0,
      "lines": [
        {"regnr": 3000, "company_id": "uuid", "amount": -500000.0, "description": "Varesalg"},
        {"regnr": 4000, "company_id": "uuid", "amount": 500000.0, "description": "Varekjop"}
      ]
    }
  ],
  "runs": [
    {
      "run_id": "uuid",
      "run_at": 1711542000.0,
      "company_ids": ["uuid1", "uuid2"],
      "elimination_ids": ["uuid3"],
      "warnings": [],
      "result_hash": "sha256hex"
    }
  ]
}
```

### Skrivekontrakt

- **Atomic write**: tmp-fil + `os.replace()` (samme moenster som `client_store`).
- **Parquet for TB**: rask lese/skrive, ingen Excel-skriveproblemer.
- **project.json oppdateres ved enhver tilstandsendring**: import, mapping, eliminering, run.
- **updated_at** settes ved hver save.

### Session-kobling

```python
# session.py (allerede forberedt)
consolidation_project = None   # type: ConsolidationProject | None
```

- `ConsolidationPage.refresh_from_session(sess)` leser `client`/`year`, laster project.json.
- Prosjektet opprettes foerst ved foerste import (ikke automatisk).
- Sideskift til Konsolidering-fanen er trygt ogsaa uten prosjekt (viser tom tilstand).


## 5. Konsolideringsmotor — deterministisk run

### Steg

1. For hvert selskap: last TB-parquet, apply interval mapping, apply overrides.
2. Aggreger hver selskaps TB til regnskapslinjenivaa (`aggregate_by_regnskapslinje`).
3. Lag samle-DataFrame med kolonner: `regnr, regnskapslinje, <selskap1>, <selskap2>, ..., sum_foer_elim`.
4. Konverter alle elimineringsjournaler til DataFrame. Aggreger per regnr.
5. Legg til eliminerings-kolonnen(e).
6. Beregn `konsolidert = sum_foer_elim + total_eliminering`.
7. Beregn sumlinjer via `compute_sumlinjer`.
8. Generer SHA256-hash av resultat-DataFrame.
9. Lagre RunResult.

### Determinisme

- Selskaper sorteres etter `company_id` (stabil rekkefoelge).
- Elimineringer sorteres etter `journal_id`.
- Samme input gir alltid samme `result_hash`.

### Gjenbruk

- `regnskap_mapping.apply_interval_mapping()` — mapper konto -> regnr
- `regnskap_mapping.apply_account_overrides()` — per-selskap overstyringer
- `regnskap_mapping.aggregate_by_regnskapslinje()` — aggregering
- `regnskap_mapping.compute_sumlinjer()` — sumlinjeformler
- `regnskap_config.load_regnskapslinjer()` — henter regnskapslinjer
- `regnskap_config.load_kontoplan_mapping()` — henter intervallmapping


## 6. Excel-eksport — arkstruktur

### Ark 1: "Konsernoppstilling"

| Nr | Regnskapslinje | Mor AS | Datter AS | Sum foer elim. | Eliminering | Konsolidert |
|----|----------------|--------|-----------|----------------|-------------|-------------|
| 3000 | Salgsinntekt | 1 000 000 | 500 000 | 1 500 000 | -200 000 | 1 300 000 |
| ... | ... | ... | ... | ... | ... | ... |

- Tittelfelt med klient, aar, genereringstidspunkt.
- Sumlinjer i bold med fyllfarge (#F3F6F9).
- Beloepsformat: `#,##0.00;[Red]-#,##0.00`.
- Frozen panes under header.

### Ark 2: "Elimineringer"

En seksjon per journal:
- Journalnavn som header
- Linjer: Regnr | Selskap | Beloep | Beskrivelse
- Bunnrad: Balansesjekk (sum)

### Ark 3..N: "TB - {Selskapsnavn}"

Per selskap: Konto | Kontonavn | IB | UB | Netto | Regnr | Regnskapslinje

### Ark N+1: "Kontrollark"

- Run-metadata: run_id, tidspunkt, hash
- Inkluderte selskaper og elimineringer
- Balansesjekk: sum alle selskapers UB + elimineringer = konsolidert total


## 7. Implementeringsbrief — foerste slice

### Slice 1: Datamodell + lagring + TB-import (backend-only, ingen GUI)

Opprettes i denne rekkefoelgen:

| # | Fil | Innhold |
|---|-----|---------|
| 1 | `consolidation/__init__.py` | Re-eksport av public API |
| 2 | `consolidation/models.py` | Alle dataklasser over |
| 3 | `consolidation/storage.py` | `save_project`, `load_project`, `save_company_tb`, `load_company_tb`, `project_dir` |
| 4 | `consolidation/tb_import.py` | `import_company_tb(path, name)` — wrapper rundt `trial_balance_reader` + `saft_trial_balance`, normaliser kolonner |
| 5 | `tests/test_consolidation_models.py` | Round-trip: opprett prosjekt, serialiser, deserialiser |
| 6 | `tests/test_consolidation_storage.py` | Save/load project + parquet TB, verify paths |
| 7 | `tests/test_consolidation_tb_import.py` | Import Excel + CSV fixture, sjekk normaliserte kolonner |

### Slice 2: Mapping + eliminering + engine (backend-only)

| # | Fil | Innhold |
|---|-----|---------|
| 8 | `consolidation/mapping.py` | `map_company_tb()` — wrapper med overstyringer |
| 9 | `consolidation/elimination.py` | Validering, DataFrame-konvertering |
| 10 | `consolidation/engine.py` | `run_consolidation()` — deterministisk motor |
| 11 | `consolidation/export.py` | Excel-arbeidsbok med alle ark |
| 12 | `tests/test_consolidation_engine.py` | 2 selskaper + 1 eliminering -> korrekt resultat + hash |
| 13 | `tests/test_consolidation_export.py` | Eksporter, les tilbake, sjekk celleverdier |

### Slice 3: GUI-skjelett + integrasjon

| # | Fil | Innhold |
|---|-----|---------|
| 14 | `page_consolidation.py` | Erstatt stub med ekte workspace |
| 15 | `ui_main.py` | Wire inn fanen (minimalt — bare nb.add + refresh) |

### Slice 4: GUI komplett + polish

| # | Fil | Innhold |
|---|-----|---------|
| 16 | `page_consolidation.py` | Import-dialog, mapping-review, elimineringseditor, run+resultat, eksport |
| 17 | Gate 2-verifisering | Ende-til-ende test med 2 selskaper |

### Avhengigheter mellom slicer

```
Slice 1 (modell/lagring/import) ── uavhengig
Slice 2 (mapping/elim/engine)   ── krever Slice 1
Slice 3 (GUI-skjelett)          ── krever Slice 1
Slice 4 (GUI komplett)          ── krever Slice 2 + 3
```

### Filer som IKKE endres i boelge 2

- `page_analyse.py`, `page_analyse_ui.py`, `page_analyse_columns.py`
- `page_a07.py`
- Alle andre eksisterende GUI-sider

Eneste endring i eksisterende filer er `ui_main.py` (Slice 3) for aa wire inn fanen.
