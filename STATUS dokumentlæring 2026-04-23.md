# Status — dokumentlæring 2026-04-23

## Kort status

Motoren for dokumentlæring har gjennomgått et større løft i denne økten. Hint-læringen blokkeres ikke lenger av tabell-layout (posisjon-only hints), bilagsprint-sider filtreres nå korrekt på word-nivå, flere norske fakturabegreper gjenkjennes automatisk, auto-save-støy er dempet, og hvert felt lagrer nå debug-metadata som gjør feilsøking målrettet i stedet for gjettebasert.

**391 tester grønne. Ingen kjente regresjoner.**

Vi er i «observer og juster»-fase. Anbefalingen er å bruke systemet som vanlig i noen dager og komme tilbake ved konkrete problemer med bilag-ID + skjermbilde.

---

## Hva vi har gjort i denne økten

Endringene er gruppert tematisk. Hver har dedikert(e) test(er).

### 1. Cleanup av lagret støy

Før: storet inneholdt hint-labels som `sum debet` (count=42 på 12 profiler), `bilag nummer 292-20`, `153 poulssons kvarter 1`, SWIFT/BIC-headere, rene tallfragmenter. Disse ga motoren aktivt feil signal.

Fiks:
- [document_engine/profiles.py](document_engine/profiles.py): semantisk `is_valid_label_for_field`-policy med universal svarteliste (`sum debet`, `sum kredit`, `bilag nummer`, `konteringssammendrag`, `regnskapslinje`, `sist endret`) og per-felt vokabular.
- [scripts/scan_profile_labels.py](scripts/scan_profile_labels.py) — read-only rapport over lagrede labels per felt.
- [scripts/clean_profile_labels.py](scripts/clean_profile_labels.py) — dry-run-first cleanup. Rapporterer bl.a. hvilke profiler som mister *alle* hints for et felt (kritisk signal).
- Kjørt mot live-store: 190 label-entries fjernet, 35 KB redusert, `sample_count` bevart på alle.

### 2. Gjenvinning av tapte counts via relearn

Før: `relearn_document_profiles.py` nullstilte eksisterende hints når den regenererte en profil. BRAGE `fakturanr` gikk fra count=52 → 25 fordi kun de nye save-ene ble tellet.

Fiks:
- Plan A (Fullføre trygg massekjøring): `_merge_hint_entries` med to-pass aggregering per profil-gruppe; sample_count bevares; eksisterende hints re-merges inn slik at relearn er *additiv*, ikke destruktiv.
- Maskinlesbar `--json`-output; backup-vern ved apply.
- Tester: `test_relearn_preserves_pre_existing_hint_counts` + 29 andre.

### 3. Belsøps­ekstraksjon-forbedringer (Plan B)

Før: `Beløp eksl. MVA 940.00` / `Å betale NOK 1,175.00` i punktum-desimal-format ble ikke fanget. `25.00%` kunne bli `vat_amount`. Joint subtotal+vat+total-logikk manglet.

Fiks i [document_engine/engine.py](document_engine/engine.py):
- Utvidet `_AMOUNT_PATTERNS`, `_SUBTOTAL_PATTERNS`, `_VAT_PATTERNS` med norske og engelske varianter: `totalt å betale`, `sluttsum`, `brutto(beløp|sum)?`, `grand total`, `total due`, `sum inkl mva`, `mva-grunnlag`, `avgiftsgrunnlag`, `ordrebeløp`, `ordresum`, `herav mva`, `sales tax`, osv.
- `_match_is_percentage`-filter rejecter `25.00%` som vat/subtotal-kandidat.
- `_collect_ranked_candidates` + `_select_self_consistent_amounts` + `_apply_joint_amount_selection`: enumererer top-K per amount-felt og overstyrer med en konsistent (`s + v ≈ t`) trio hvis den første per-felt-pickingen er inkonsistent.
- 17 nye amount-tester inkl. Arkitektbedriftene-case, Norsk/internasjonalt format, zero-VAT, percent rejection, brutto, herav mva, grand total.

### 4. Hint-kvalitet og -boost (fra CODEX-rapport)

**Quick-wins 1-3:**
- Amount-felt lagrer ikke `page=None`-hints fra flat-text fallback — `build_supplier_profile(...)` uten segments produserer ingen amount-hints. Hindrer «sticky» fel læring fra råtekst.
- Label-only-boost satt til 0 for amount-felt i `_profile_hint_boost`. Non-amount beholder +200. Amount må ha page-match før noen hint kan lyfte rank.
- `_choose_file()` i review-dialog nullstiller `_field_evidence`, `_field_hits`, `_field_hit_index`, `_pinned_fields` før `_reload_segments_for` og trigger `_auto_analyse` mot nytt dokument. Før: save rett etter filbytte kunne persistere gammel geometri på ny fil.

**Label-validering:**
- `normalize_hint_label` strammet: label må ha minst ett ord ≥3 bokstaver (blokkerer `27`, `55`, `1 00`, `as 2`).
- `_extract_label_from_line` beskjærer prefix til siste 3 ord (hindrer `mva 25 00 av 940 00`-unike labels).

**Posisjon-only hints (Endring A):**
- Når `user_search`-evidence har page + bbox, men `_find_hint_in_segments` ikke klarer å trekke ut en gyldig label (typisk tabell-rader), lagres en hint med `label=""`, `page=N`, `bbox=...`. Dette var hovedårsaken til at Norkart/BRAGE aldri lærte total/due_date — label-ekstraksjon feiler, men posisjon er kjent.
- `_merge_hint_entries` akseptere posisjon-only-hint (tom label + side + bbox).
- `_profile_hint_boost` gir +400 ved page + bbox_near match uansett om hint har label. Men page-only-boost (+150) er *begrenset til hints med label* — så posisjon-only hints ikke gir falsk boost til hele siden.

### 5. Forklarbarhet (Endring B)

[document_engine/engine.py](document_engine/engine.py) `_collect_ranked_candidates` skriver metadata per evidence:
- `winner_source` — hvilken extractor (f.eks. `pdf_text_fitz_words`)
- `pattern_index` — hvilken pattern som matchet
- `segment_index` — posisjon i segmentrekka
- `hint_boost` — bonus gitt (0 / 150 / 200 / 400 / 500 / 700)
- `rank` — endelig rank-score
- `bbox_width`
- `selected_by` — `joint_amount_ranking` når joint-logikk overstyrte
- `self_consistent` — satt av `_validate_amount_self_consistency`

**Ingen GUI-endring.** Metadata lagres kun for debugging. Neste gang noe feiler kan vi lese metadata direkte fra storet og se umiddelbart hvorfor motoren valgte det den valgte.

Forklarbarhet avdekket allerede én reell bug: `self_consistent`-metadata var *stale* etter brukerens korrigering. Fiks: [document_control_review_dialog.py](document_control_review_dialog.py) `_save_current` synker GUI-verdier inn i evidence og re-kjører `_validate_amount_self_consistency` før lagring.

### 6. Page-level bilagsprint-filter

Før: `_is_bilagsprint_segment(text)` krevde at ett segment hadde BÅDE "bilag nummer X" OG "konteringssammendrag" i samme tekst. Word-level extractorer produserer én linje per segment — så filteret slo ALDRI inn på word-level. Alle linjer fra bilagsprint-siden ble behandlet som fakturalinjer.

Fiks:
- `TextSegment.is_bilagsprint_page: bool` — nytt flag.
- `_tag_bilagsprint_pages(segments)` — grupperer per side, sjekker kombinert sidetekst, markerer alle segmenter på bilagsprint-sider.
- `_segment_is_bilagsprint(segment)` — primær helper; sjekker flag, faller tilbake til tekst-check.
- Kjøres automatisk i `_extract_text_from_pdf` før retur. Alle 4 call-sites som hadde segment-tilgang byttet over.

Endringen er hovedårsaken til at Norkart bilag 516 tidligere hadde `-5 140,14` fra kontering-debet som total-kandidat.

### 7. Auto-analyse snapshot-problem

Før: når brukeren lagret bilag A (som oppdaterte profil), og deretter navigerte til bilag B, ble stale extraction-evidence fra forrige analyse av B preservert fordi den hadde bbox. Nye profilendringer slo derfor ikke inn.

Fiks: [document_control_review_dialog.py:1260-1274](document_control_review_dialog.py#L1260): `_auto_analyse` bevarer kun evidence fra *trusted* kilder (`user_search`, `saved`, `profile`). Stale extraction-evidence blir overskrevet av ny analyse.

### 8. Dirty-check på auto-save

Før: `_auto_save_before_nav` trigget ved hver navigering, selv om brukeren ikke hadde endret noe. BRAGE gikk fra 79 → 96 saves (+17) selv om bare 3 bilag ble korrigert (~5.7x multiplikator).

Fiks:
- `self._edited_bilag: set[int]` — track hvilke bilag som er aktivt berørt i økten. Fylles i `_on_pdf_var_change` (user), `_focus_pdf_field` (pil-navigering), notes `<KeyPress>`.
- Ny `_is_dirty()`-metode:
  - Hvis bilag er saved: diff pdf_vars / notes / bbox mot saved snapshot.
  - Hvis aldri saved: kun dirty hvis `idx in _edited_bilag` (extraction-fylte verdier alene teller ikke).
- `_auto_save_before_nav` skipper save når `_is_dirty() is False`.
- 6 nye tester via minimal dialog-stub.

### 9. GUI-forenkling

Review-dialog har nå `[◀] Lagret [▶]` (eller `ikke lagret`) i stedet for `s.2 1/17`-sidebadgen og den separate «Lagret s.2: ...»-teksten.
- ◀/▶ blar gjennom PDF-hits begge veier. Grået ut når det bare er ett hit.
- Midtfelt-tekst viser lagringsstatus mot GUI-verdi (grønn = match, oransje = usaved endring, grå = ikke lagret). Klikk → hopp til nåværende kandidat.

### 10. Scan-verktøy (read-only)

[scripts/scan_profile_labels.py](scripts/scan_profile_labels.py) — produserer rapport over alle lagrede labels per felt med noise-klassifisering (bilagsprint-term, adresse-ord, matches vokabular, lange tall osv.). 21 unit-tester.

---

## Minnes­­lager oppdatert

- [feedback: dokumentlæring cleanup-workflow](.claude/projects/.../memory/feedback_document_learning_cleanup.md) — scan → dry-run → apply, og aldri relearn rett etter cleanup.
- [project: Utvalg-1 document engine](.claude/projects/.../memory/project_utvalg1_document_engine.md) — hvor dokumentmotoren bor + F-sti til live-store.

---

## Plan videre

Ingen nye features planlagt på kort sikt. Vi er i observasjons­fase.

### Prioriterte gjenstående forbedringer (når tiden er inne)

| # | Tittel | Scope | Når |
|---|--------|-------|-----|
| 1 | Topp-N bbox per `(label, page)` i hint-datamodell | Middels — endrer datamodell, merge, serialisering | Utsatt; marginell gevinst etter page-level-filter |
| 2 | Brage-benchmark med committerte PDF-er + expected JSON | Stort — egen uke, CI-integrasjon | Når vi vil *målbart* vite at endringer forbedrer (ikke bare «føles bedre») |
| 3 | Tabell-layout-håndtering: bruk kolonneoverskrift som label | Stort prosjekt — egen plan, ny codepath | Når posisjon-only-hint viser seg utilstrekkelig i praksis |
| 4 | `debug`-knapp i review-dialog som viser forklarbarhets-metadata for valgt felt | Lite — men skal ikke legges til før vi har konkret bruksmønster | Når brukeren ser behov |

### Neste bruksrunde — hva som bør observeres

1. **Norkart / BRAGE nye fakturaer**: klikker du nå færre ganger manuelt? Posisjon-only hints (count 7-12 på Norkart) skal slå inn med +400 boost ved `bbox_near` på neste faktura fra samme leverandør.

2. **Sample_count-vekst**: bør matche antall *unike* brukersaves, ikke ganges 5-10x av navigering. HAM-mønstret bør være dødt.

3. **Nye auto-fanget felt**: bilag 516 subtotal ble auto-fanget med rank=1150, hint_boost=700 i forrige runde. Forvent at flere felt begynner å ta seg selv. Hvis det ikke skjer — metadata viser hvorfor.

4. **Bilagsprint-forurensning**: `bilag nummer X-YY`, `sum debet` osv. bør ikke dukke opp som nye labels. Cleanup-scriptet kan kjøres i dry-run innimellom for å verifisere.

5. **Edge-cases å rapportere**:
   - Extraktor velger feil side på tabell-fakturaer der beløp står i kolonner uten label-prefix på samme linje (gjelder fortsatt; posisjon-hints hjelper kun etter ≥1 user_search).
   - `dato` lært som invoice_number-label (fortsatt 81 count i storet — kan være extraction-bug i engine, ikke cleanup-sak).
   - Currency-feltet er svakt dekket — hvis ikke vokabularet matcher («valuta», «currency», 3-letter koder), læres ikke hintet.

### Når du kommer tilbake med et problem

Send bilag-ID + skjermbilde + gjerne hvilken leverandør det er. Forklarbarhets-metadata (lagret i storet fra neste save og fremover) lar oss se i sekunder hvilken kilde motoren valgte, hvilken rank, hvor mye boost. Målrettet fiks i stedet for arkitektgjetting.

---

## Teknisk oppsummering

- 8 commits verdi av endringer i løpet av økten (ikke laget ennå — brukeren må commite selv).
- Rørt filer: `document_engine/engine.py`, `document_engine/profiles.py`, `document_control_review_dialog.py`, `document_control_app_service.py`, `scripts/relearn_document_profiles.py`.
- Nye filer: `scripts/scan_profile_labels.py`, `scripts/clean_profile_labels.py`, `tests/test_amount_cross_check.py`, `tests/test_scan_profile_labels.py`, `tests/test_clean_profile_labels.py`.
- 391 tester grønne i den relevante suiten (opp fra ~180 ved sesjonens start).
- Store på F:-drive er ryddet (2026-04-22) og har posisjon-only hints for Norkart (4 felt, count 7-12).
- En cleanup-rapport ligger som `cleanup_report_20260422.json` ved siden av storet.
