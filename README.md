# Utvalgsgenerator – Runde C (leveranse)

Denne leveransen er en **selvstendig** og ryddig modulær versjon av appen.
Alt er standard Python (.py). Start med `app.py`.

## Kjøring
```bash
python app.py
```

Avhengigheter: `pandas`, `numpy`, `openpyxl`, `chardet` (for CSV).

## Struktur (kort)
- `app.py` – entrypoint.
- `ui_main.py` – hovedvindu, faner: Datasett, Analyse, Utvalg.
- `dataset_pane.py` – åpne fil, finne header, velge kolonner, bygge datasett.
- `page_analyse.py` – kontopivot til venstre + transaksjoner til høyre.
- `views_selection_studio.py` – segmentering/kvantiler og trekk/eksport.
- `controller_core.py` – filtrerings/kalkulasjonslogikk.
- `io_utils.py` – lesing av Excel/CSV, header-deteksjon, kolonne‑gjetting.
- `formatting.py` – norsk formatering (beløp/dato) + parser.
- `models.py` – dataklasser for kolonner m.m.
- `session.py` – delt datasett mellom faner.
- `preferences.py` – enkle preferanser (json).
- `ui_utils.py` & `theme.py` – UI‑nytte og tema.
- `export_utils.py` – Excel‑eksport (åpner filen direkte).

## Viktige valg
- **Norsk visning**: tusenskiller med mellomrom og komma som desimal.
- **Ingen popup‑storm**: Alt skjer i hovedvindu/faner. (Kun fil‑dialoger når nødvendig.)
- **Debug**: Detaljerte `try/except` med `messagebox` og konsoll‑logging.
