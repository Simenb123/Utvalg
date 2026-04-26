# Datasett-sammenligning (A vs B) — bevart kunnskap + plan

**Sist oppdatert:** 2026-04-26

Dokumenterer en gammel prototype-feature for sammenligning av to
datasett som ble bygget men aldri tatt i bruk. Koden ble slettet
2026-04-26 (commit etter `9bb636b`) for å rydde roten, men
domenekunnskap og algoritmer er bevart i git-historikken og oppsummert
her for når featuren faktisk skal bygges.

## 1. Hva ble slettet

11 filer (~2300 linjer) som var dødt kode — ingen wiret dem inn i
hovedappen:

**UI-prototyper:**
- `page_ab.py` (616 linjer) — `ABPage(ttk.Frame)` for AB-sammenligning
- `page_ab_compare.py` (276 linjer) — alternativ `ABPage` med to dataset-paneler
- `page_studio.py` (132 linjer) — `StudioPage` (annen feature, ikke datasett-sammenligning)

**Algoritmer (dødt etter sletting av UI):**
- `ab_analysis.py` (164 linjer) — `same_amount`, `opposite_sign`, `two_sum`
- `ab_analyzers.py` (49 linjer) — fasade
- `ab_matchers.py` (235 linjer) — vektorisert matching, greedy 1-til-1
- `ab_key_deviation.py` (165 linjer) — fakturanr-normalisering

**Kjedet til ab_*-koden:**
- `analysis_pkg.py` — pakke som binder ab_* mot dataset
- `analysis_pack.py` — eldre versjon (LEGACY-merket allerede)
- `page_analyse_model.py` — `AnalyseState`-modell
- `page_analyser.py` — eldre versjon (LEGACY-merket allerede)

**Tilhørende tester:**
- `tests/test_analysis_pkg.py`
- `tests/test_page_analyse_model.py`

**Beholdt:**
- `ab_prefs.py` (106 linjer) — preset-lagring, brukes fortsatt av
  `views_settings.py`. Ikke død kode.

**Git-referanse:** Hele klyngen finnes i commit `9bb636b` og tidligere
(originalt fra `b9881f8` 2025-11-10). Hent fram med:
```
git checkout 9bb636b -- page_ab.py ab_matchers.py ab_key_deviation.py
```

## 2. Verdifull domenekunnskap fra koden

### 2.1 Matching-algoritmer (`ab_matchers.py`)

Solid implementasjon — vektorisert pandas, ikke trivielle å gjenoppdage:

- **`match_same_amount`** — A ↔ B med likt beløp innenfor toleranse,
  valgfritt med dato-toleranse (± dager) og krav om samme part
- **`match_opposite_sign`** — kreditnota-detektering (A=−B beløp)
- **`match_two_sum`** — A = B+C-mønster (én transaksjon i A matcher
  to i B). Dyrt: O(n²) per bucket, derfor `max_rows_two_sum_bucket=2000`-kappe
- **`_greedy_unique_pairs`** — 1-til-1-paring sortert på score
  (`|beløpsavvik|*100 + |dager|`)

### 2.2 Fakturanr-normalisering (`ab_key_deviation.py`)

Ikke-triviell forretningslogikk:

- **`normalize_invoice_series`** — strip whitespace, kun alphanumeric,
  upper-case, valgfritt strip leading zeros (handler "0001234" = "1234")
- **`match_invoice_equal`** — A ↔ B på normalisert fakturanr,
  valgfritt med dato-toleranse og krav om samme part
- **Avviksrapporter** — for matchede par: beløpsavvik + dato-avvik

### 2.3 Konfigurasjon (`ab_analysis.ABConfig`)

Domain-konstanter som er kalibrert for revisor-bruk:

```python
days_tolerance: int = 3              # Standard 3-dagers vindu
amount_tolerance: float = 0.0        # Eksakt match som default
require_same_party: bool = False     # Kan slå på for kunde/leverandør
invoice_drop_non_alnum: bool = True
invoice_strip_leading_zeros: bool = True
unique_match: bool = True
max_pairs_per_bucket: int = 50_000   # Skalerings-kappe
max_rows_two_sum_bucket: int = 2_000 # Two-sum er O(n²)
```

### 2.4 Preset-lagring (`ab_prefs.py`)

Beholdt — virker fortsatt. Lagrer brukerens matching-konfigurasjon
som navngitte presets i `<data_dir>/ab_presets.json`. API:
`save_preset(name, config_dict)` / `load_preset(name)` / `list_presets()`.

## 3. Hvorfor koden ble slettet (ikke bare arkivert)

- **UI-prototypen var aldri ferdig** — to filer definerer samme
  klassenavn (`ABPage`), eldre Tk-mønster uten `ManagedTreeview`,
  ingen kolonneveiler/sortering
- **Duplisert algoritme** — `ab_analysis` og `ab_matchers` implementerer
  samme matching, men med ulike API-er. `ab_analysis` har dårligere
  skalering (O(n²)-løkke i stedet for vektorisert pandas)
- **Hele kjeden (analysis_pack, analysis_pkg, page_analyser) var
  LEGACY-merket** — eldre versjoner som aldri ble erstattet

Bedre å bygge nytt med moderne mønster når featuren skal tas i bruk
enn å bære med dødt kode i roten.

## 4. Plan for når featuren skal bygges

### 4.1 Lokasjon

`src/audit_actions/dataset_compare/` — popup som åpnes fra Analyse-fanen
eller dataset-fanen. Ikke en egen faneside (jf. pages-vs-audit_actions-
skille i [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md)).

### 4.2 Struktur

```
src/audit_actions/dataset_compare/
├── __init__.py
├── backend/
│   ├── __init__.py
│   ├── matchers.py          # Refaktorert ab_matchers — vektorisert matching
│   ├── invoice_norm.py      # Refaktorert ab_key_deviation
│   ├── config.py            # ABConfig-dataclass
│   └── prefs.py             # Flytt ab_prefs hit
└── frontend/
    ├── __init__.py
    └── dialog.py            # Ny Toplevel med ManagedTreeview
```

### 4.3 UI-konsept

**Todelt vindu:**
```
+------------------+------------------+
| Datasett A       | Datasett B       |
| (kilde-velger)   | (kilde-velger)   |
+------------------+------------------+
| Konfigurasjon (felles)              |
|  Match-type: [✓] Likt beløp         |
|              [✓] Motsatt fortegn    |
|              [ ] Two-sum            |
|              [ ] Likt fakturanr     |
|  Toleranse: 3 dager, 0.00 kr        |
|  Preset: [Standard ▾] [Lagre…]      |
+-------------------------------------+
| Resultat (ManagedTreeview)          |
| - Sortering, kolonneveiler          |
| - Per match-type fane               |
+-------------------------------------+
```

### 4.4 Rekkefølge

1. **Backend først** — flytt ab_prefs til ny lokasjon, hent ab_matchers
   fra git-historikk og refaktor for tester + skalerbarhet
2. **Test-suite** — enhetstester for hver matcher med konkrete eksempler
3. **Frontend** — ny dialog med ManagedTreeview
4. **Integrasjon** — knapp i dataset-fanen / analyse-fanen som åpner dialogen

### 4.5 Forbedringer mot original

- Bruk `ManagedTreeview` (sortering, kolonneveiler, persist)
- Bedre two-sum-skalering (vurder hashing eller indeks-basert algoritme
  i stedet for O(n²))
- Lint-test for backend (ingen tkinter-imports)
- Pure-data API (ta DataFrames inn, ikke `page`-objekt)
- Eksport til Excel via samme stil som andre eksport-knapper
- Pages-vs-audit_actions-konvensjon (Toplevel-popup, ikke fane)

## 5. Relaterte dokumenter

- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) — pages
  vs audit_actions-skillet
- [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) — ManagedTreeview-mønster
- [analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md) —
  kolonneretning som dataset_compare bør følge
