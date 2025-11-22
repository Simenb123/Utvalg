# R7 – Underpopulasjoner, stratifisering og "trekk n bilag" (v1.40.0)

## Innhold
- **views_selection_studio.py** – nytt vindu for å definere underpopulasjoner og stratifisering:
  - Filtre per underpop (søk, retning, beløpsintervall)
  - Stratifisering på Beløp (absolutt eller signert), metode: `quantile` eller `equal-width`
  - Trekk `n` bilag per stratum, reproduserbart (`seed`)
  - Forhåndsvisning av strata og prøvetrekk
  - Eksport til Excel (ark pr. underpop: `*_Trans`, `*_Pivot`, `*_Strata`, `*_Trekk`)
- **page_utvalg.py** – ny knapp **"Underpop/Stratifisering…"** som åpner studioet for dagens utvalg.

## Bruk
1. Gå til **Utvalg** (etter at du har sendt kontoer fra Analyse).
2. Klikk **Underpop/Stratifisering…**.
3. Definer én eller flere underpopulasjoner og trykk **Forhåndsvis**.
4. Trykk **Eksporter Excel** for å få alle arkene ut i én fil i temp.

## Krav
- Kolonnen **Beløp** må finnes i utvalgets transaksjoner.

## Notater
- Ytelse: all filtrering og stratifisering er vektorisert i pandas – ingen per-rad for‑løkker.
- Robusthet: manglende kolonner gir tydelige meldinger; studioet åpner ikke uten `Beløp`.