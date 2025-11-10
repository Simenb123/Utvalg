
# R11b – Perf Hotfix (v1.44.4)

**Fikser**
- La til `AnalysePage._reset_filters()` (knappen "Nullstill" ga crash).
- "Pinned kolonner" som menytekst.
- Samme ytelsesgrep som 1.44.3 (debounce, observed=True, guarded autoload).
- Skjuler interne kolonner (`_search`, `_abs_beløp`) i kolonnedialog/visning.
- Re-render av transaksjoner uten å re-konfigurere kolonner når det ikke trengs.

**Kjøring**
```
pip install pandas numpy openpyxl chardet
python app.py
```
