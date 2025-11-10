
# R12 – Utvalg UX & Strata‑veiviser

Dette patchsettet leverer:
- Ny **Utvalg**‑side med sumstripe, paging (side/per side) og robust kontoserie‑filter.
- **Delutvalg/Stratifisering** som en veiviser i tre steg (Filtre → Strata → Trekk).
- **Bilagsdrill** (dbl‑klikk i transaksjoner åpner alle linjer for bilaget).
- Enkel **persistens per klient** (modul `preferences.py`) – klar for utvidelse.
- Oppdatert `VirtualTransactionsPanel` med paging API.

## Hurtigstart
1. Kopiér alle `.py` fra denne pakken inn i prosjektmappen (erstatt eksisterende).
2. Start som før: `python app.py`.
3. I **Analyse**: marker kontoer og klikk **Til utvalg**.
4. I **Utvalg**: bruk filtre og åpne **Til underpop/Stratifisering**.

## Arkitektur
- `page_utvalg.py`: UI for utvalg.
- `views_selection_studio.py`: veiviser for delutvalg/stratifisering.
- `views_bilag_drill.py`: modal for bilagsdrill.
- `views_virtual_transactions.py`: tabell m/paging.
- `io_utils.py`: kontoserie og beløpsverktøy.
- `preferences.py`: JSON-baserte preferanser (per klient).
- `excel_export.py`: eksport av strata og trekk (to ark).

## Feilsøking
- Hvis Utvalg er tomt: sjekk at `session.dataset` er satt etter innlasting i **Datasett**.
- Hvis kolonner mangler: `VirtualTransactionsPanel` viser kolonner etter `visible` listen; `page_utvalg` fyller denne fra standardfelt som finnes i filen.

## TODO (neste runde)
- Persistér kolonnevalg/pinned/vis‑N per klient via `preferences.py` (nå bare klargjort).
- Sumstripe for *valgte kontoer* separat.
- Paging-kontroller integreres i Analyse (nå tilgjengelig via VirtualTransactionsPanel).
- Ekspander “Forhåndsvis” i veiviser (sidevalg).
- Flere eksportmaler.
