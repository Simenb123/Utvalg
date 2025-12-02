# R10 – Kolonnevelger (synlighet + rekkefølge) – v1.43.0

Denne patchen gjør det mulig å velge **hvilke kolonner som vises** og **i hvilken rekkefølge** i transaksjonstabellene (Analyse + Utvalg).
Valgene lagres i `preferences` per fane og tas i bruk umiddelbart.

## Nye filer
- `views_column_chooser.py` – felles dialog for å velge/rydde kolonner.

## Oppdaterte filer
- `views_virtual_transactions.py` – nå med `apply_visible_order(...)` og støtte for `prefer_order`/`visible` i `set_dataframe(...)`.
- `page_analyse.py` – ny knapp **Kolonner…** + bruk av lagrede kolonnevalg.
- `page_utvalg.py` – ny knapp **Kolonner…** + bruk av lagrede kolonnevalg.

## Bruk
1. Gå til **Analyse** eller **Utvalg** og klikk **Kolonner…**.
2. Marker ønsket kolonne og bruk **Vis/Skjul**, **Opp**, **Ned** for å sette synlighet og rekkefølge.
3. Klikk **Lagre**. Valgene lagres i `preferences` og gjelder neste gang du starter programmet.
4. Pinned‑kolonner (menyen *Pinned kolonner*) vises alltid først i tabellen. Kolonnevelgeren styrer rekkefølgen innbyrdes og synligheten.

## Preferanse‑nøkler
- Analyse:
  - `analyse.columns.order` (List[str])
  - `analyse.columns.visible` (List[str])
  - `analyse.pinned` (List[str])
- Utvalg:
  - `utvalg.columns.order` (List[str])
  - `utvalg.columns.visible` (List[str])
  - `utvalg.pinned` (List[str])

## Kompatibilitet
- Hvis en lagret kolonne ikke finnes i nytt datasett, ignoreres den.
- Nye kolonner vises automatisk (du kan skjule dem i dialogen).
- Norsk formatering (beløp/dato) beholdes; ytelsen ivaretas siden formattering skjer kun på det synlige vinduet.