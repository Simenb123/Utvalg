
# R11b – UI/ytelse/rekkefølge (v1.44.2)

**Hva er nytt**
- **Kontoserier**: robust første siffer (riktig 6/7).
- **Pivot pr konto**: standard sortering **Konto ↑**.
- **Vis (rader)**: Analyse viser 100/200/500/1000/**Alle** i GUI; beregninger på full filtrert mengde.
- **Kolonner**: rekkefølge/visning + pinned anvendes korrekt.

**Filer**
- `page_analyse.py`
- `views_virtual_transactions.py`
- `views_column_chooser.py`

**Hurtigstart**
```
pip install pandas numpy openpyxl chardet
python app.py
```

**Kjent**
- Hvis pivot fremdeles ikke lar seg markere på ditt OS‑tema, si ifra – jeg legger på en liten style‑patch.
