# Utvalg – revisjonsverktøy

Dette prosjektet er et GUI-verktøy (Tkinter) for analyse/utvalg av regnskapsdata, med støtte for bl.a. filtrering,
kopiering til clipboard, Excel-eksport og motpostanalyse.

## Quickstart

1. Opprett og aktiver virtuelt miljø (Windows):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Installer avhengigheter:

```powershell
pip install -r requirements.txt
```

3. Start appen:

```powershell
python app.py
```

## Testing

Kjør alle tester:

```powershell
pytest
```

Kjør med coverage-rapport:

```powershell
pytest --cov
```

## Arkitektur (høynivå)

- **GUI / views**: `views_*.py`, `ui_*.py`
  - Tkinter/ttk widgets, event-binding, interaksjon og presentasjon
- **Analyse / domene-logikk**: `*_core.py`, `*_utils.py`, `*_model.py`, `analysis_*.py`, `motpost_*.py`
  - Beregninger, filtrering, transformasjoner av DataFrames, eksport
- **Kontrollflyt**: `controller_*.py`, `page_*.py`
  - Kobler UI sammen med modell/tilstand og aksjoner

Mål: holde UI-kode og backend-logikk mest mulig adskilt.

## Troubleshooting

- **Appen starter ikke i PyCharm**:
  - Sjekk *Working directory* i Run Configuration – den skal peke på prosjektroten.
  - Kjør gjerne fra terminal i prosjektroten: `python app.py`

- **Clipboard/Excel liming**:
  - `Ctrl+C` kopierer uten header (TSV), `Ctrl+Shift+C` kopierer med header.
  - I Excel: klikk i *én* celle før du limer inn hvis du får “Copy area and paste area aren't the same size”.

- **Bygge EXE (PyInstaller)**:
  - Kjør fra prosjektroten: `python build_exe.py`
  - Sørg for at `pyinstaller` er installert i venv.

## TODO (kortliste)

- Videre refaktorering: tydeligere pakkestruktur (`ui/`, `views/`, `domain/`, `services/`).
- Mer gjenbruk av felles Treeview/Listbox-funksjonalitet (kopi, summering, eksport).
- Flere integrasjonstester for viktige brukerflows (motpost/drilldown/utvalg).
