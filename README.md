# Utvalg

Verktøy for å analysere hovedbok/saldobalanse i norsk revisjon (NGAAP).

Repoet inneholder en Tkinter‑app med faner for **Dataset**, **Analyse**, osv.

## Hurtigstart

Eksempel for Windows (PowerShell) i prosjektmappen (samme nivå som `app.py`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
pip install pandas openpyxl pytest

python app.py
```

> Tips: Tkinter følger normalt med Python på Windows.

## Datasetimport

Dataset‑fanen bygger et standardisert datasett (pandas DataFrame) med norske
feltnavn som **Konto**, **Bilag**, **Beløp**, osv.

Støttede kilder:

- **Excel**: `.xlsx`, `.xlsm`, `.xltx`, `.xltm`
- **CSV**: `.csv`
- **SAF‑T**: `.zip`, `.xml`, `.gz`, `.gzip` (konverteres til cachet `transactions.csv`)

Typisk arbeidsflyt:

1. Velg fil (**header/mapping lastes automatisk**)
2. (Excel) Velg riktig **Ark** (header/mapping oppdateres automatisk)
3. Juster **Header‑rad** (1‑indeksert) ved behov (Enter eller klikk ut av feltet)
   - eller trykk **Gjett header** for å autodetektere
4. Kontroller/juster mapping manuelt
5. Trykk **Bygg datasett**

### Hvorfor ny I/O‑vei for preview/header

Noen Excel‑filer kan ha "forurenset used‑range" (f.eks. formatert langt ned i arket),
som gjør enkelte bibliotekkall veldig trege. Preview og header‑lesing bruker derfor:

- `openpyxl` i `read_only=True` streaming‑modus
- alltid begrenset antall rader/kolonner

Dette ligger i `dataset_pane_io.py`.

### Robusthet ved Excel med feil ark/header

Hvis ingen av de mappede kolonnene finnes på valgt header‑rad, behandles dette som
en "hard fail" slik at `build_from_file()` kan falle tilbake til gjetting av ark/header.

## Arkitektur

Hovedkomponenter:

- `app.py` – entrypoint
- `ui_main.py` – hovedapp og faner
- `page_dataset.py` – Dataset‑fane
- `dataset_pane.py` – UI + mapping + async import
- `dataset_pane_io.py` – bounded IO (preview/header)
- `dataset_build_fast.py` – rask bygging av DataFrame fra fil

## Testing

Installer avhengigheter:

```bash
python -m pip install -U pip
pip install pandas openpyxl pytest
```

Kjør testene:

```bash
pytest -q
```

## Feilsøking

- **"Leser header…" står lenge**
  - Sjekk at du har valgt riktig ark
  - Bruk **Forhåndsvis** for å se rå data og velg riktig header‑rad
  - `.xls` (gammel Excel) støttes ikke – konverter til `.xlsx`
  - SAF‑T kan ta tid første gang (genererer cachet CSV)

- **Mapping virker feil**
  - Sjekk at header‑rad faktisk inneholder kolonnenavn
  - Mapping foreslås automatisk når header leses – juster manuelt ved behov

Se også **Logg**‑fanen for detaljer.

## TODO

- Avbryt/timeout for svært store importer
- Mer progress‑indikasjon (antall rader lest)
- Flere enhetstester rundt SAF‑T‑flyten
