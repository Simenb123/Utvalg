# Ytelses‑patch v1.41.0 – Virtualisert transaksjonsvisning

**Hva**: `views_virtual_transactions.py` er fullstendig omskrevet:
- Virtuell visning (**kun ~1500 rader** rendres om gangen)
- Scrollbar representerer hele datasettet – flytter vinduet
- Klikk‑sortering på kolonneoverskrifter
- `pinned`‑kolonner støttes
- Zebra‑striper
- `max_rows` (default 100k) kan settes i `preferences` via `table.max_rows`

**Hvordan ta i bruk**
1. Bytt ut `views_virtual_transactions.py` i prosjektet med filen i denne ZIP‑en.
2. (Valgfritt) I `preferences.json` eller via `preferences.set(...)` kan du sette:
   - `"table.max_rows": 100000` (standard)
   - `"table.window_size": 1500` (ikke eksponert i denne patchen, men kan raskt utvides)

**Hvorfor dette hjelper**
- På datasett med 500k+ rader rendres kun ~1500 elementer i `Treeview` om gangen.
- Skrolling og kolonne‑klikk bytter ganske enkelt hvilket *vinduuutsnitt* som vises.
- Dette fjerner de store frysene som kom av å forsøke å fylle hele tabellen.