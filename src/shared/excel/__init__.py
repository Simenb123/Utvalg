"""Domene-nøytrale Excel-utilities.

Pilot 36. Hjelpefunksjoner for import/eksport av Excel-filer som brukes
av flere fans. Tk-fri.

Moduler:
- ``importer.py``        — robust import av Excel-filer (sheet/header-deteksjon)
- ``import_heuristics.py`` — heuristikk for å gjette header-rad og kolonner
- ``sheet_guess.py``     — heuristikk for å velge default sheet
- ``export.py``          — bygging av export-DataFrame med visningskolonner
- ``formatting.py``      — Excel-formatering (kolonnebredder, fargekoder, freeze panes)
"""
