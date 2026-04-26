# A07 Lonn Testing

Disse testene beskytter A07-lonnsporet, RF-1022-kontrollen og den fail-closed
matchinglogikken.

## Baseline For A07-Endringer

Kjor dette for og etter endringer i A07:

```powershell
py -3 -m compileall -q page_a07.py a07_feature src\pages\a07 tests\a07
py -3 -m pytest tests\a07 tests\test_a07_module_budgets.py tests\test_a07_namespace_smoke.py tests\test_a07_chain_regression.py tests\test_page_a07.py tests\test_page_a07_payroll.py --no-cov -q
```

Nar saldobalansevisning, kolonner eller lonnsklassifisering beres, kjor ogsa:

```powershell
py -3 -m pytest tests\test_page_saldobalanse.py tests\test_page_control_data_rf1022.py tests\test_ui_main_dataset_analysis.py tests\test_tb_only_mode.py tests\test_payroll_classification.py tests\test_payroll_classification_suggest.py tests\test_payroll_classification_classify.py tests\test_payroll_classification_catalog.py tests\test_payroll_classification_audit.py --no-cov -q
py scripts\report_a07_module_sizes.py
```

Merk:

- `tests\a07\` er naa kanonisk intern A07-testsuite.
- `tests\test_page_a07.py` er redusert til legacy smoke-/compat-vakt.
- `tests\test_a07_module_budgets.py` og `report_a07_module_sizes.py` beskytter
  modulstorrelsene og skal kjorers jevnlig etter strukturelle endringer.

## Viktige Delsett

## Debuglogg Ved Bakgrunnsfeil

A07 skriver intern diagnostikk til `%TEMP%\utvalg_a07_debug.log` når
`_A07_DIAGNOSTICS_ENABLED` er aktiv. GUI-et skal fortsatt vise korte
feilmeldinger, men bakgrunnsjobbene for kontekst, kjerne-refresh og
støttevisninger logger nå full traceback i debugloggen. Bruk denne loggen når
fanen blinker/refresh stopper, eller når GUI-et bare viser en kort
`A07-oppdatering feilet`-melding.

Loggen skal brukes til feilsøking, ikke som brukerflate. Nye background-feil bør
derfor legge detaljer i debuglogg og holde `status_var`/`details_var` korte.

### Offentlig Fasade Og Compat

- `tests/test_page_a07.py`
- `tests/test_a07_chain_regression.py`
- `tests/test_a07_namespace_smoke.py`
- `tests/a07/test_facade_and_compat.py`
- `tests/test_a07_*_namespace_smoke.py`

Disse beskytter at `page_a07.A07Page` og gamle importstier fortsatt virker mens
intern struktur flyttes.

### Refresh, UI Og Arbeidsflate

- `tests/a07/test_refresh_and_apply.py`
- `tests/a07/test_support_refresh.py`
- `tests/a07/test_context_and_selection.py`
- `tests/a07/test_support_render.py`
- `tests/a07/test_tree_and_labels.py`

Disse beskytter refresh-payloads, selection-state, supportrender og arbeidsflyt
paa hovedflaten.

### Mapping, Laering Og Hoyreklikk

- `tests/a07/test_mapping_actions.py`
- `tests/a07/test_manual_mapping_and_learning.py`
- `tests/a07/test_mapping_action_guardrails.py`

Disse beskytter mappingflyt, laering, hoyreklikkmenyer og remove-/assign-
handlinger paa tvers av GL, forslag, koblinger og A07-koder.

### Matching Og Guardrails

- `tests/test_a07_control_matching.py`
- `tests/test_a07_feature_suggest.py`
- `tests/test_a07_feature_reconcile.py`
- `tests/a07/test_overview_and_history_engine.py`
- `tests/a07/test_control_queue_data.py`
- `tests/a07/test_control_gl_data.py`
- `tests/a07/test_control_filters.py`
- `tests/a07/test_rf1022_runtime.py`
- `tests/a07/test_rf1022_statement_engine.py`

Disse skal dekke at automatikk bare bruker strenge forslag, og at kjente
problemkontoer som `2940`, `5890` og `6701` ikke feiltolkes.

### RF-1022 Og Kontrollgrunnlag

- `tests/test_a07_control_statement_source.py`
- `tests/test_page_control_data_rf1022.py`
- `tests/test_a07_control_presenter.py`

Disse beskytter kataloglasting, kontrolloppstilling, RF-1022-grupper og visning
av riktig belopskolonne.

### Payroll / Saldobalanse

- `tests/test_page_a07_payroll.py`
- `tests/test_payroll_classification.py`
- `tests/test_payroll_classification_suggest.py`
- `tests/test_payroll_classification_classify.py`
- `tests/test_payroll_classification_catalog.py`
- `tests/test_payroll_classification_audit.py`
- `tests/test_page_saldobalanse.py`

Disse beskytter handoff mellom A07, saldobalanse og profilklassifisering.

## Regresjoner Som Skal Forbli Dekket

- `load_current_catalog()` returnerer aktiv katalog ved suksess.
- Out-of-scope kontrollgrupper lekker ikke inn i RF-/kontrollflaten.
- `Kjor automatisk matching` bygger ferske RF-1022-kandidater ved klikk.
- Batchmatching bruker bare strict-auto / accepted guardrails.
- Kombinasjonsforslag gir ikke hver enkelt konto trygg status uten egen evidens.
- Remove-handlinger respekterer las og bruker felles remove-service.
- Hovedflaten viser bare `Forslag` og `Koblinger`, med gamle flater som compat
  der tester eller eldre call sites trenger dem.
