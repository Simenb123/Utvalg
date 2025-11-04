
# Handover – Utvalg (M5c)

Dette er siste stabile leveranse (**M5c**) av appen for revisjonsanalyse av hovedbok (Tkinter, én‑vindu). Inneholder samtlige `.py`‑filer og denne README.md.

## Kort om flyten
- **Datasett**: Åpne fil → header‑deteksjon → kolonnemapping (konto, kontonavn, bilag, beløp, dato, tekst, part; valgfritt: forfall/periodestart/periodeslutt) → **Bygg datasett** (lagres i session og Analyse‑fanen oppdateres).
- **Analyse**: Søk/filter (retning, beløp, periode), pivot pr. konto, transaksjoner for markerte kontoer, **dbl‑klikk drilldown** på bilag, **motpost‑fordeling**, **Til utvalg**.
- **Utvalg**: Populasjon og underpopulasjoner (konto‑uttrykk, beløp/retning/periode), stratifisering i bøtter, *trekk n bilag*, eksport (temp‑xlsx).
- **Analyser (Excel)**: Runde beløp‑andeler, Outliers, A/B‑krysshint (likt beløp / motsatt fortegn / two‑sum), Duplikater (flere varianter), Periodekontroller (inkl. forfall/egen rad‑periode).

## Kjøring
```bash
pip install pandas numpy openpyxl chardet
python ui_main.py
```

## Viktige prinsipper
- **Norsk format** i visning: `dd.mm.yyyy` og tusenskiller m/ komma‑desimal.
- **Mini‑ML** (`ml_map.py`) gjenkjenner filtyper basert på header‑signatur + co‑occurrence‑hint for hele kolonnesett.
- **Best‑effort eksport**: analyser som mangler forutsetninger blir utelatt fremfor å feile.

## TODO (neste utvikler)
1. **A/B mellom to kilder** – eget “Datasett B” + menypunkt for A↔B‑krysshint. Ytelse: bucketing og grenset n for par.
2. **UI‑polish** – zebra‑striper, pinne kolonner, raskere søk i transaksjoner, bedre kolonnebreddestyring.
3. **Skalerbarhet** – lazy‑load/virtuell Treeview for store filer, caching av pivoter.
4. **Tester** – pytest for IO/format/ML/analyse. Testdata: små CSV/Excel‑snutter med ulike headere.
5. **Flere analyser** – terskel‑mønstre, bruker/part‑sekvenser, avvik mot saldobalanse, toleranser pr. konto/part.
6. **Eksportmaler** – Excel‑mal med pivoter, slicere og formler per ark.

## Filer
Se koden i denne mappen. Nøkler:
- `dataset_pane.py` (innlasting/kolonnemapping/ML)
- `page_analyse.py` (pivot, drilldown, motpost, til utvalg)
- `page_utvalg.py` (populasjon/underpop/stratifisering/trekk/eksport)
- `analysis_pkg.py`, `ab_analysis.py`, `dup_period_checks.py` (analyser)
- `io_utils.py`, `formatting.py`, `ml_map.py` (I/O, format, ML)
- `excel_export.py` (temp‑xlsx, åpnes direkte)
- `theme.py`, `logger.py`, `ui_utils.py`, `session.py`, `controller_core.py`

God videre utvikling!
