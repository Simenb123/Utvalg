# `document_engine` — Architecture

This package extracts invoice fields (amount, date, supplier, etc.)
from PDF/XML/TXT documents, and learns per-supplier hints that improve
extraction over time. It is designed to be reusable: no dependencies
on the wider Utvalg-1 application, and a stable public API surface.

## What it does

- Read text from a PDF / XML / image via multiple extractors, pick the
  best candidate by score.
- Match invoice fields (subtotal, VAT, total, invoice number, date,
  due date, supplier, currency, ...) against a library of regex
  patterns, then rank candidates with positional + label + profile
  signals.
- Detect Tripletex accounting cover pages ("bilagsprint") at page
  level and exclude them from extraction and learning.
- Cross-check `subtotal + vat ≈ total` and override inconsistent
  triples via joint candidate selection when possible.
- Build, merge and apply `SupplierProfile` hints so the next invoice
  from the same vendor gets a rank-boost on known labels/positions.
- Record *why* each field was picked via rich metadata on
  `FieldEvidence` — debuggable and directly consumable by ML
  pipelines.

## What it does **not** do

- UI, file-system dialog, or GUI-widget logic (lives in the host app).
- Store-file I/O beyond the `ProfileRepository` port (the host app
  plugs in concrete JSON/SQL implementations).
- Model training. Metadata is ML-ready (see below), but the package
  never imports ML frameworks or performs training.

## Module layout

| Module | Linjer | Ansvar |
|--------|-------|--------|
| `engine.py` | 864 | Orkestrering: `analyze_document`, `_extract_text_from_pdf`, profil-læring, XML-ekstraksjon |
| `profiles.py` | 788 | `SupplierProfile`-build/match/apply, hint-inferens, label-policy (`is_valid_label_for_field`) |
| `extractors.py` | 482 | PDF-extractors (pypdf, pdfplumber, fitz_words, fitz_blocks, OCR) + kandidat-scoring-helpers |
| `patterns.py` | 307 | Alle regex-patterns (amount, date, supplier, bilagsprint, invoice-number osv.) |
| `scoring.py` | 301 | Kandidat-ranking, `_score_field_match`, `_profile_hint_boost`, bbox-helpers |
| `amount_consistency.py` | 271 | `subtotal + vat ≈ total`-sjekk, joint selection, redo-OCR-triggere |
| `format_utils.py` | 268 | `parse_amount_flexible`, `normalize_amount_text`, `normalize_orgnr`, amount-variants |
| `voucher_pdf.py` | 248 | Splitting av Tripletex-samle-PDF i voucher-spesifikke filer |
| `models.py` | 241 | Alle dataklasser: `FieldEvidence`, `DocumentFacts`, `SupplierProfile`, `TextSegment`, osv. |
| `finder.py` | 189 | `DocumentCandidate`-oppslag, `build_search_terms`, `suggest_documents` |
| `supplier.py` | 159 | Supplier-ekstraksjon (Foretaksregisteret, label-pattern, high-caps fallback) |
| `__init__.py` | 138 | Offentlig API-overflate — 35 eksporterte symboler |
| `normalizers.py` | 112 | Felt-normalizers: dato → DD.MM.YYYY, orgnr → 9 digits, osv. |
| `bilagsprint.py` | 93 | Page-level bilagsprint-deteksjon (`_tag_bilagsprint_pages`, `_segment_is_bilagsprint`) |
| `ports.py` | 42 | `Protocol`-klasser: `ProfileRepository`, `DocumentLocator`, osv. |
| `contracts.py` | 37 | JSON-serialisering for batch-job-input/output |

Total: ~4 600 linjer.

## Avhengighetsgraf

```
patterns.py  models.py   ports.py  contracts.py
     │           │
     └──┬──┬─────┤
        │  │     │
        │  │     ▼
        │  │  format_utils.py  (stdlib + valgfritt pandas)
        │  │     │
        │  ▼     │
        │ bilagsprint.py
        │     │
        ▼     ▼
   extractors.py   ◄──┐
        │             │
        ▼             │
   scoring.py         │
        │             │
        ▼             │
   supplier.py  ──────┤
        │             │
        ▼             │
   normalizers.py ────┤
        │             │
        ▼             │
   profiles.py        │
        │             │
        │  ┌──────────┘
        ▼  ▼
   amount_consistency.py    finder.py   voucher_pdf.py
        │                        │           │
        └──────┬─────────────────┴───────────┘
               ▼
           engine.py  (orkestrator)
               │
               ▼
          __init__.py  (offentlig API)
```

**Regler:**
- `models.py`, `patterns.py`, `ports.py`, `contracts.py` har ingen
  andre interne avhengigheter — trygt import-grunnlag.
- `engine.py` er *toppen* av grafen og importerer alle andre moduler.
  Ingen modul nedover importerer `engine.py` på topp-nivå.
- Noen moduler har **lazy** engine-import inne i en funksjon (f.eks.
  `amount_consistency._apply_joint_amount_selection` bruker
  `_collect_ranked_candidates` fra scoring, som i sin tur brukes av
  engine). Dette er bevisst — lazy import bryter import-sykler uten
  å kreve refaktor.

## Offentlig vs internt API

### Offentlig (stabilt)

Alt som eksporteres fra `document_engine/__init__.py` — 35 symboler,
gruppert etter kategori i filen. Endringer her bør følge vanlig
bakoverkompat-praksis (deprecation-varsler før fjerning).

### Internt (kan endres)

Alt med `_`-prefiks i undermoduler. Eksempler: `_collect_ranked_candidates`,
`_profile_hint_boost`, `_normalize_amount_text`. Tester og interne
call-sites kan bruke dem, men eksterne konsumenter bør ikke.

Re-eksport-mønsteret: `engine.py` re-eksporterer flere private navn
fra andre moduler for at tester og interne kall kan importere dem via
`engine`-modulen uten å vite den konkrete submodul-plasseringen. Dette
er bakoverkompat-lim og kan skrelles bort hvis/når eksisterende call-
sites oppdateres.

## Metadata-skjema

`FieldEvidence.metadata` er en dict med eksplisitt definerte nøkler.
Disse er dokumentert her fordi de utgjør det primære integrasjonspunktet
for ML-pipelines.

### `FieldEvidence.metadata`

| Nøkkel | Type | Betydning | Satt av |
|--------|------|-----------|---------|
| `winner_source` | `str` | Hvilken extractor vant (`pdf_text_fitz_words`, `pdf_text_pdfplumber`, `pdf_ocrmypdf_redo`, ...) | `scoring._collect_ranked_candidates` |
| `pattern_index` | `int` | Indeks i pattern-listen som matchet (0 = primær, høyere = mer generisk) | scoring |
| `segment_index` | `int` | Segment-posisjon (0-basert) — lavest = høyest-prioritert side | scoring |
| `hint_boost` | `float` | Bonusen profil-hint ga denne kandidaten (+0 / +150 / +200 / +400 / +500 / +700) | scoring |
| `rank` | `float` | Endelig rank-score som bestemte seieren | scoring |
| `bbox_width` | `float` | Bredde på match-bbox i punkter (bred = tabellrad, smal = enkelt-tall) | scoring |
| `selected_by` | `str` | Satt til `"joint_amount_ranking"` når `amount_consistency._apply_joint_amount_selection` overstyrte | amount_consistency |
| `self_consistent` | `bool` | Satt på amount-felt når `subtotal + vat ≈ total`-sjekken er kjørt | amount_consistency |

### `DocumentAnalysisResult.metadata`

| Nøkkel | Type | Betydning |
|--------|------|-----------|
| `file_name` | `str` | Kortnavn |
| `file_size` | `int` | Bytes |
| `ocr_used` | `bool` | True hvis noen kandidat var OCR-produsert |
| `page_count` | `int` | Antall sider i PDF |
| `candidate_count` | `int` | Antall extraction-kandidater som ble vurdert |
| `candidate_sources` | `list[dict]` | Per-extractor: `{source, score, ocr_used, char_count, segment_count}` |
| `selected_score` | `float` | Score for vinnerkandidaten |
| `text_char_count` | `int` | Lengde på valgt tekst |
| `line_count` | `int` | Antall kandidatlinjer i valgt tekst |
| `amount_self_consistent` | `bool\|None` | `subtotal + vat ≈ total`-verdikt (None = manglende felt) |
| `ocr_redo_triggered_by` | `str` | `"amount_mismatch"` når redo-OCR-fallback ble brukt |
| `ocr_redo_attempted` | `bool` | True hvis redo ble prøvd men ikke valgt |
| `ocr_redo_chosen` | `bool` | True når redo-resultatet ble valgt over native |

## Utvidelsesmønstre

### Legge til et nytt ekstraksjonsfelt

1. Definér pattern i `patterns.py` som `_MYFIELD_PATTERNS`.
2. Legg `myfield` til `LEARNABLE_FIELDS` i `profiles.py` hvis det skal
   læres per leverandør.
3. Legg til vokabular i `_FIELD_VOCAB[myfield]` i `profiles.py` for
   label-whitelist.
4. Kall `_first_match_evidence(...)` fra feltløkken i
   `engine.extract_invoice_fields_from_text`.
5. Legg til test i `tests/test_amount_cross_check.py` (eller ny
   tilsvarende fil).

### Legge til en ny PDF-extractor

1. Skriv funksjonen i `extractors.py` med signatur
   `(path: Path) -> tuple[str, list[TextSegment]]`. Sett en unik
   `source`-string på hvert segment (f.eks. `"pdf_text_mynew"`).
2. Legg til kall i `_extract_text_from_pdf` via `_append_candidate(...)`.
3. `_score_text_candidate` trenger ingen endring — den jobber på tekst,
   ikke på extractor-typen.
4. Test: mock extractoren i `tests/test_document_control_service.py` og
   verifiser at den vinner når tekst-kvaliteten er best.

### Legge til ny leverandør-spesifikk hint-kilde

1. Utvid `SupplierProfile`-dataklassen i `models.py` med felt som kan
   lagres (f.eks. `static_fields`, `field_hints`, `aliases`).
2. Utvid `infer_field_hints` i `profiles.py` til å samle signalene du
   vil lære.
3. Boost skjer via `scoring._profile_hint_boost` — ingen endring nødvendig
   om du holder samme hint-format `{label, page, bbox, count}`.

## Læringsmodell

`SupplierProfile.field_hints` er en `dict[str, list[dict]]` — per felt,
en liste av observerte `(label, page, bbox, count)`-registreringer.

**Byggestegene:**
1. Ved lagring: `_upsert_profile_with_hints` kaller `infer_field_hints`
   med segments + evidence fra brukerens bekreftelse.
2. `_find_hint_in_segments` leter etter feltverdien i hver (ikke-
   bilagsprint) segment og trekker ut `_extract_label_from_line` +
   `page` + `bbox`.
3. `_merge_hint_entries` aggregerer nye hints med eksisterende. Duplikater
   med samme `(label, page)` slås sammen og `count` akkumuleres.
4. `is_valid_label_for_field` validerer label-policy — både struktur og
   per-felt vokabular må passe.
5. Resultatet lagres tilbake via `ProfileRepository.save_profile`.

**Bruksstegene:**
1. Ved ny ekstraksjon: `match_supplier_profile` matcher leverandør på
   `supplier_orgnr` → `name` → alias-fuzzy.
2. `extract_invoice_fields_from_text_with_hints` kaller
   `_collect_ranked_candidates` med profilens hints som tilleggs-input.
3. `_profile_hint_boost` gir +150 / +200 / +400 / +500 / +700 avhengig
   av hvor mange signaler (page, label, bbox_near) som stemmer.
4. Amount-felt har spesialregler: posisjon-only-hints (label=""),
   ingen label-only-boost, joint consistency-check.

## ML-integrasjon

Metadata­skjemaet ovenfor er designet for å være feature-komplett for
en ML-pipeline:

- **Per-felt features**: `FieldEvidence.metadata` → alle nøkler er
  numeriske eller enum-lignende strenger.
- **Per-dokument features**: `DocumentAnalysisResult.metadata` →
  extractor-fordeling, OCR-status, selvkonsistens.
- **Per-leverandør features**: `SupplierProfile.field_hints` → liste av
  (label, frekvens, posisjon)-tripler.

Eksport til ML-format er **bevisst ikke inkludert** i pakken. Det
kan legges til som egen modul (`ml_export.py`) når den konkrete
ML-pipelinen er kjent. Metadata er allerede stabilt, så en slik modul
kan utvikles uten å endre core-extraction.

## Versjonering

Intern dataklasser har ingen versjonsnummer. Unntak: `SupplierProfile`
har `schema_version` (nåværende `1`). Endringer i hint-formatet skal
bumpe dette nummeret og `_coerce_profile` i `profiles.py` skal
migrere gammelt format.

## Teststruktur

Tester lever i `tests/` (utenfor pakken). De viktigste:

- `tests/test_amount_cross_check.py` — amount-ekstraksjon, self-consistency, joint selection
- `tests/test_document_control_learning.py` — profile-læring, label-policy, bilagsprint-filter
- `tests/test_document_control_service.py` — end-to-end via service-lag
- `tests/test_document_engine_contracts.py` — serialisering
- `tests/test_document_format_utils.py` — amount-parsing-varianter

Rundt 391 tester totalt, alle grønne pr. nåværende commit.
