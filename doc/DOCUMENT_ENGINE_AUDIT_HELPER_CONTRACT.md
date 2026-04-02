# Document Engine -> Audit Helper Contract

Dette dokumentet låser første kontrakt mellom den lokale `document_engine`-motoren i `Utvalg-1` og en fremtidig worker-/jobbintegrasjon i `audit-helper`.

## Mål

Motoren skal kunne kjøres headless i en senere worker og returnere strukturert dokumentanalyse uten avhengighet til Tkinter eller lokal `client_store`.

## Job input

Statusmodell følger `analysis_jobs` / `import_jobs`-mønster:

- `queued`
- `running`
- `done`
- `failed`

Inputobjekt:

- `engagement_id`
- `gl_import_id`
- `sample_run_id`
- `sample_item_id`
- `task_id`
- `anchor_task_id`
- `voucher_no`
- `document_no`
- `line_ids[]`
- `source_meta_json`
- `params_json`

## Job output

Motoren skal returnere:

- `document_facts`
- `field_evidence[]`
- `validation_messages[]`
- `matched_profile`
- `result_file_path`
- `result_json`

## `document_facts`

Første kjernesett:

- `supplier_name`
- `supplier_orgnr`
- `invoice_number`
- `invoice_date`
- `due_date`
- `subtotal_amount`
- `vat_amount`
- `total_amount`
- `currency`

## `field_evidence`

Hvert felt bør kunne serialiseres med:

- `field_name`
- `normalized_value`
- `raw_value`
- `source`
- `confidence`
- `page`
- `bbox`
- `inferred_from_profile`
- `validated_against_voucher`
- `validation_note`
- `metadata`

## Audit Helper mapping

Fremtidig worker bør:

1. Claim jobben fra `analysis_jobs`.
2. Hente dokumentkilde fra storage / attachment / sample item lineage.
3. Kalle `document_engine`.
4. Lagre `result_json`.
5. Eventuelt generere arbeidspapir og registrere dette som `generated_workpaper`.

## Lineage-krav før full integrasjon

`audit-helper` bør senere sikre:

- at `voucher_no` og `voucher_key` skilles tydelig
- at `line_ids[]` bevares gjennom sampling-flyten
- at `document_no` og `source_meta_json` eksponeres til worker
- at resultat kan kobles til både `sample_items` og `task_attachments`
