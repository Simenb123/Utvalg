# A07 Lonn Testing

Disse testene beskytter A07-lonnsporet, RF-1022-kontrollen og den fail-closed
matchinglogikken.

## Baseline For A07-Endringer

Kjor dette for og etter endringer i A07:

```powershell
py -3 -m compileall -q page_a07.py a07_feature
py -3 -m pytest tests/test_page_a07.py tests/test_page_a07_payroll.py tests/test_a07_chain_regression.py tests/test_a07_namespace_smoke.py tests/test_a07_control_matching.py tests/test_a07_control_statement_source.py tests/test_a07_feature_suggest.py tests/test_payroll_classification.py tests/test_a07_feature_reconcile.py --no-cov -q
```

Nar saldobalansevisning, kolonner eller lonnsklassifisering beres, kjor ogsa:

```powershell
py -3 -m pytest tests/test_page_saldobalanse.py tests/test_page_saldobalanse_detail_panel.py --no-cov -q
```

## Viktige Delsett

### Offentlig Fasade Og Compat

- `tests/test_page_a07.py`
- `tests/test_a07_chain_regression.py`
- `tests/test_a07_namespace_smoke.py`

Disse beskytter at `page_a07.A07Page` og gamle importstier fortsatt virker mens
intern struktur flyttes.

### Matching Og Guardrails

- `tests/test_a07_control_matching.py`
- `tests/test_a07_feature_suggest.py`
- `tests/test_a07_feature_reconcile.py`

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
