# Utvalg


**Innhold**
- `preferences.py` – kompatibel modul med get/set + load/save (lagrer i .session/preferences.json om mulig)
- `views_virtual_transactions.py` – robust, rask transaksjonstabell (NaN-sikker, limit-visning, dblklikk-callback)
- `ui_loading.py` – global loading overlay (modal Toplevel + indeterminate progressbar)
- `page_analyse.py` – Analyse med overlay, paging, pivot (observed=True), sikre fallbacks
- `page_utvalg.py` – Utvalg med overlay, sikre fallbacks, paging
- `ml_map_utils.py` – last/lagre/suggest/update mapping i .ml_map.json (bakoverkompatibel)
- `dataset_build_fast.py` – hurtig innlesing med usecols + robust parsing
- `dataset_pane.py` – valgfri drop-in som kobler inn overlay + fastload + ML

**Hurtigstart**
1. Kopiér alle filene ved siden av dine eksisterende `.py`-filer (samme nivå som `app.py`).
2. Start `python app.py`.
3. (Valgfritt) Bytt din nåværende `dataset_pane.py` med denne for å få loading+fastload+ML.

**Trygghet**
- Alle filer er bakoverkompatible. Hvis enkelte moduler (f.eks. `views_column_chooser`) mangler, bruker vi stubs for å unngå krasj.



## Testing

Prosjektet bruker `pytest` for automatiserte tester.

### Installere avhengigheter

Opprett og aktiver et virtuelt miljø (valgfritt, men anbefalt), og installer avhengigheter:

```bash
pip install -r requirements.txt
pip install pytest