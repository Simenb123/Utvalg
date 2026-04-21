# A07 Lonn Testing

Disse testene dekker det avgrensede A07-lonnsporet og skal holdes gronne under
migreringen.

## Minimumssett for fase 1 og senere strukturflytting

- `tests/test_a07_namespace_smoke.py`
- `tests/test_page_a07.py`
- `tests/test_page_a07_payroll.py`
- `tests/test_a07_chain_regression.py`
- `tests/test_payroll_classification.py`
- `tests/test_page_control_data_rf1022.py`

## Viktige delsett

### Offentlig A07-fasade

- `tests/test_page_a07.py`
- `tests/test_a07_chain_regression.py`

Disse beskytter at `page_a07.A07Page` og de etablerte A07-helperne fortsatt
virker mens intern struktur endres.

### Payroll / RF-1022

- `tests/test_page_a07_payroll.py`
- `tests/test_payroll_classification.py`
- `tests/test_page_control_data_rf1022.py`

Disse beskytter lonnsklassifisering, RF-1022-behandling og koplingen mellom
kontrollko og saldobalanse-oppfolging.

### Kontrollko / presentasjon

- `tests/test_page_a07.py`
- `tests/test_a07_control_matching.py`
- `tests/test_a07_control_presenter.py`

Disse er viktige nar vi senere begynner a flytte kontrolllogikk inn i
`a07_feature/control/`.

## Fase 1-aksept

Fase 1 er godkjent nar:

- de nye namespace-pakkene kan importeres
- ingen runtime-atferd er endret
- alle testene i minimumssettet er gronne
- dokumentasjonen peker tydelig ut hva som skal flyttes i neste fase
