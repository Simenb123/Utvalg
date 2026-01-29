# Overstyring av kontroller – implementeringsnotat

Denne pakken er laget for å kunne kjøre "kontroller" på transaksjonsdatasettet, vise treff i en tabell,
og la brukeren åpne drilldown / eksportere treff til Excel.

## Viktige designvalg (for å redusere risiko)

- **Backend og GUI er separert**
  - Backend (pandas) ligger i `overstyring/core.py` + `overstyring/checks_*.py`
  - UI (Tkinter) ligger i `overstyring/ui_panel.py` + `overstyring/ui_entrypoint.py`

- **Kompatibilitet / stabil importsti**
  - Repoet har en del flate moduler. For å unngå store endringer leveres også tynne "wrapper"-moduler:
    - `override_checks.py`
    - `override_check_registry.py`
    - `views_override_checks.py`

  Disse re-eksporterer funksjoner/klasser fra `overstyring/` og gjør det enkelt å integrere gradvis.

- **Best-effort kolonneoppslag**
  - `overstyring/core.resolve_core_columns()` bruker `cols` (fra `Session.get_dataset()` / `models.Columns`) hvis tilgjengelig.
  - Hvis `cols` mangler, forsøkes en konservativ alias-liste (Bilag/Konto/Beløp osv.).
  - Hvis bilag mangler, returnerer kontrollene tomt resultat i stedet for å kollapse.

## Hva som er implementert

### Backend

- `build_voucher_summary(df)` gir 1 rad per bilag med:
  - Antall linjer, netto, sum abs, min/max dato, unike konto/tekst/doknr osv.
- Kontroller (i `overstyring/checks_*.py`):
  - **Store bilag** (`large_vouchers`)
  - **Runde beløp** (`round_amount_vouchers`)
  - **Risiko-bilag** (`override_risk_vouchers`) – heuristikk-score
  - **Dupliserte linjer** (`duplicate_lines_vouchers`)

### Registry

- `overstyring/registry.py` definerer:
  - `ParamSpec` (UI-parameter)
  - `CheckSpec` (id, tittel, runner, parametre)
  - `get_override_check_specs()` (liste over kontroller)

Dette gjør det enkelt å legge til nye kontroller uten å endre UI.

### UI

- `open_override_checks_popup(parent, session, df_all=None, cols=None)` åpner vindu.
- Panelet viser:
  - Kontrollvalg + parametre
  - Sammendrag (bilag-liste)
  - Linjer (for valgte bilag)
  - Drilldown (åpner bilag i eksisterende drilldown-dialog)
  - Eksport til Excel (sammendrag + linjer)

## Hvor bør dette plasseres i repoet?

- **Anbefalt:** behold `overstyring/` som egen mappe/pakke.
  - Gir tydelig avgrensning, enklere testing og mindre risiko for "spagetti" i `page_analyse.py`.

- Wrapper-filene i rot (nevnt over) er bevisst små og kan fjernes senere hvis repoet refaktoreres mer.

## Integrasjonspunkt (når dere er klare)

Det tryggeste er å integrere via en *tynn action*:

Eksempel i en knapp-handler (Analyse-siden):
```python
from views_override_checks import open_override_checks_popup

open_override_checks_popup(parent=self.root, session=self.session)
```

Anbefaling: legg knappen i `page_analyse.py` (Analyse-fanen) eller i en meny (Main).
Ikke legg analyse-logikk i UI-lagene – kall bare entrypoint-funksjonen.

## Testing

Det finnes enhetstester som verifiserer at kontrollene returnerer forventet struktur og treff på et lite datasett
(se `tests/test_overstyring_checks.py`).

UI testes foreløpig ikke automatisk (Tkinter + headless), men er isolert slik at backend kan testes robust.
