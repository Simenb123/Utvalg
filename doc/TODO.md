# TODO — besluttede oppgaver

Dette er oppgaver vi har blitt enige om å implementere.
For ideer som ikke er besluttet ennå, se `*_IDEER.md`-filer i denne mappen.

Se [README.md](README.md) for beskrivelse av arbeidsmetoden.

---

## Aktive oppgaver

*(Ingen besluttede oppgaver per nå — flytt hit fra IDEER-filer etter drøfting)*

---

## Baklogg — tidligere noterte ønsker

Disse er eldre ideer som ikke er formelt besluttet, men som er verdt å ha med:

- **A/B-sammenligning mellom to kilder** — last inn datasett A og B, kjør
  krysshint (likt beløp / motsatt / two-sum / duplikat per part/konto/periode).

- **UI-polish** — zebra-striper i Treeview, «pinne» kolonner, smartere
  kolonnebredder, raskere søk i transaksjoner.

- **Skalerbarhet / ytelse** — virtuell/lazy Treeview for store datasett,
  caching av pivoter.

- **Automatisert test** — pytest-dekning for IO / format / ML / analyse.

- **Flere delanalyser** — terskelmønstre, brukermønstre, tid-på-døgnet,
  avvik mot saldobalanse.

- **Eksportmaler** — Excel-mal med pivoter/diagrammer/slicere og «rapportark».

- **GL-pivot per måned** — Kontonr | Kontonavn | Jan | Feb | … | Sum.

- **Motpost-fordeling** — for valgt konto: vis hvilke kontoer den er motpostert
  mot, i beløp og prosent, interaktivt.

---

## Fullført

*(Flytt hit etter at en oppgave er implementert og committet)*

- Reskontro: åpne poster matching på faktura-nr fra tekst *(2026-04-05)*
- Reskontro: UX-forbedringer — sortering, flervalg, Ctrl+C, høyreklikk-meny *(2026-04-05)*
- BRREG: fix for balansetall (eiendeler/egenkapitalGjeld) + cache v2 *(2026-04-05)*
