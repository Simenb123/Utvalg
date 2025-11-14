# Utvalg – SelectionStudio-filtre
Generert: 2025-11-14T13:41:57.933645Z

Denne pakken inneholder nye, rene hjelpefunksjoner og tester for filtreringslogikken
i stratifiseringsvinduet (SelectionStudio).

## Nye filer

- `selectionstudio_filters.py` – ren funksjon `filter_selectionstudio_dataframe(...)` som
  implementerer retning- og beløpsfiltre slik SelectionStudio gjør det i GUI.
- `tests/test_selectionstudio_filters.py` – pytest-tester som verifiserer at
  filtreringen fungerer for:
  - Debet/Kredit/Alle,
  - min-/maksbeløp,
  - bruk av absoluttbeløp,
  - norske tallformater med mellomrom og komma.

## Testing

Fra rotmappen til prosjektet ditt:

```bash
pytest tests/test_selectionstudio_filters.py
```

Når denne testen er grønn, kan du trygt koble `filter_selectionstudio_dataframe`
inn i `views_selection_studio.py` sin `_apply_filters`-metode (erstatt dagens
manuelle filtreringskode med et kall til hjelpefunksjonen).
