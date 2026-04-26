# Analyse-fanen — pivot på transaksjonsdata + Excel-eksport

**Sist oppdatert:** 2026-04-26

Plan for å gjøre Analyse-fanens transaksjonsdata til et raskt ad-hoc
pivot-verktøy med Excel-eksport, slik at revisor kan svare på
"hvor mye er det egentlig der?"-spørsmål uten å forlate Utvalg.

## 1. Visjon

Brukeren skal raskt kunne:
- **Pivotere transaksjonsdata** på relevante dimensjoner (Regnskapslinje,
  Konto, Kunde, Leverandør, Måned, MVA-kode, …) uten å eksportere først
- **Eksportere til Excel** som en faktisk pivot — ikke bare flat tabell —
  slik at videre analyse kan gjøres i Excel av kvalitetshensyn
  (sporbarhet, kollegaformidling, dokumentasjon)
- **Lagre vanlige oppsett** som "templates" så ofte-brukte pivot-vinkler
  kan kjøres med ett klikk

Dette er ikke ment å erstatte Excel; det er ment å gi revisor svar på
80% av "hva er det egentlig her?"-spørsmål direkte i Utvalg, med ett-
klikks Excel-eksport for de resterende 20%.

## 2. Tre-nivå tilnærming

### Nivå 1 — Regnr/Regnskapslinje som valgfri kolonner (~1 time)

**Mål:** Gjør Regnr og Regnskapslinje tilgjengelig i transaksjons-treet
slik at brukeren kan inkludere dem i visningen og sortere/filtrere på
dem.

**Endringer:**
1. Berik `build_transactions_view_df` (i [analyse_viewdata.py](../../analyse_viewdata.py))
   med Regnr og Regnskapslinje hvis disse er i `tx_cols`. Bruk
   eksisterende `regnskapslinje_mapping_service` for konto → RL-oppslag
   (samme kilde som RL-pivot på venstre side).
2. Legg til `Regnr` og `Regnskapslinje` i `AnalysePage.TX_COLS_DEFAULT`.
3. Oppdater `build_tx_column_specs` (i
   [page_analyse_columns_presets.py](../../page_analyse_columns_presets.py))
   slik at disse to kolonnene får `visible_by_default=False` — de er
   tilgjengelige via høyreklikk-velgeren men ikke synlige automatisk.
4. Sett kolonnebredder i [analyse_treewidths.py](../../analyse_treewidths.py)
   (Regnr ~70px, Regnskapslinje ~240px).

**Risiko:** Lav. Berikingen er opt-in (kun hvis kolonnen er i `tx_cols`),
og defaults er uendret for eksisterende brukere.

**Status:** Planlagt — implementeres samtidig med dette dokumentet.

### Nivå 2 — "Pivot her"-popup fra høyreklikk (~½–1 dag)

**Mål:** En egen Toplevel-dialog som lar brukeren rask-pivotere
transaksjonsdataene de ser på.

**Skisse:**
- Høyreklikk på rad eller header i transaksjons-treet → meny-element
  "Pivot her…"
- Åpner en Toplevel-dialog med tre dropdowns:
  - **Rader:** Regnskapslinje / Konto / Kunde / Leverandør / Måned / Kvartal / Bilag-prefiks
  - **Kolonner (valgfri):** Måned / Kvartal / MVA-kode / Konto-serie
  - **Verdi:** Beløp (sum) / Antall transaksjoner / Min / Maks / Snitt
- Resultat vises i en `ManagedTreeview` i samme dialog
- Total-rad nederst
- Knapp "Eksporter til Excel" (se Nivå 3)
- Knapp "Lagre som template…" (se under)

**Templates:**
Forhåndsdefinerte pivot-oppsett som dekker vanlige revisor-spørsmål:
- "Topp 10 leverandører × regnskapslinje"
- "Beløp per måned × konto-serie"
- "Bilag per kunde × måned"
- "MVA-kode × konto"
- "Kontoserie 4 kostnader per måned"

Templates kan deles på tvers av klienter (lagres i `preferences` eller
egen `pivot_templates.json`).

**Bruker grensesnittet:** Pivot-dialogen viser også **drilldown-knapp**
— klikker brukeren på en pivot-celle, dukker det opp en liste med de
underliggende transaksjonene som inngår.

**Tekniske valg:**
- Bruk `pandas.pivot_table` for selve aggregeringen — etablert API,
  rask, håndterer NaN-verdier konsistent
- Inputdata er det FILTRERTE datasettet (det brukeren ser i transaksjons-
  treet), ikke hele hovedboken — brukeren kan dermed "zoome inn" først
- Pivot-resultatet er en pandas DataFrame som vises i en
  `ManagedTreeview` for konsistens med resten av appen

**Risiko:** Middels. Krever ny dialog-fil. UX-design (hvilke dimensjoner,
hvordan navngi dem) bør avklares med bruker først.

### Nivå 3 — Excel-eksport med ekte pivot (~1 dag)

**Mål:** Eksporter pivot-resultatet til Excel slik at brukeren kan
fortsette analyse i Excel med full pivot-funksjonalitet.

**To smaker:**

#### 3a. Lett (anbefalt start)
- Skriv to ark til Excel-filen:
  - **Pivot:** ferdig-aggregert tabell (det brukeren så i Utvalg)
  - **Rådata:** de underliggende filtrerte transaksjonene
- Fordeler: enkelt, robust, virker overalt
- Ulemper: brukeren må lage Excel-pivot selv hvis hen vil endre
  dimensjoner

#### 3b. Avansert (senere)
- Bruk `openpyxl`'s `PivotTable`/`PivotCache`-API til å lage en
  faktisk Excel-pivot med rådata-arket som kilde
- Fordeler: brukeren kan endre dimensjoner direkte i Excel
- Ulemper: openpyxl-pivot-API er ikke veldokumentert, krever testing
  i ulike Excel-versjoner

**Anbefalt sekvens:** 3a først (lavt risiko, dekker 80% av behov),
deretter 3b når 3a er stabil.

**Risiko:** Lav for 3a, middels for 3b.

## 3. Avhengigheter og forutsetninger

- **RL-mapping må være konfigurert** for klienten for at Regnr/
  Regnskapslinje skal fylles ut. Hvis ikke: kolonnene viser tomt.
  (Dette er allerede tilfellet for resten av RL-funksjonaliteten.)
- **Pivot-popupen forutsetter** at transaksjonsdataene har
  konsistente felter for kunde/leverandør/dato. Dette er etablert
  via berikings-laget (`enrich_reskontro_counterparty_for_view`).

## 4. Hvorfor denne rekkefølgen?

- **Nivå 1 først** gir umiddelbar verdi (kolonner i visningen) og
  legger grunnlaget for at Regnr/Regnskapslinje er tilgjengelig som
  pivot-dimensjoner i Nivå 2.
- **Nivå 2 og 3 bør avklares med bruker** — UX-valg om dialog vs.
  integrert i eksisterende RL-pivot, hvilke templates som er nyttigst,
  Excel-format-valg.
- **Bevisst scope-begrensning:** Pivot-funksjonen skal være rask å
  bruke for vanlige spørsmål, ikke konkurrere med Excel selv. Hvis
  brukeren trenger noe komplisert, eksporterer de til Excel og fortsetter
  der.

## 5. Smartere alternativ — templates kan komme før full Pivot-popup

**Vurder:** Bygg 4-5 ferdige pivot-templates som ett-klikks Excel-
eksporter (Nivå 3a), uten å bygge Nivå 2-dialogen først. Hver template
er en knapp eller meny-element under "Rapporter ▾" i toolbaren:
- "Topp leverandører per regnskapslinje (Excel)"
- "Beløp per måned per konto-serie (Excel)"
- "Bilagsanalyse per kunde (Excel)"

Dette dekker antagelig 80% av reelt behov med lavere kompleksitet enn
en full pivot-dialog. Pivot-dialogen kan komme senere når vi vet
hvilke dimensjoner brukerne faktisk savner.

## 6. Relaterte dokumenter

- [analyse_kolonnevisning_plan.md](analyse_kolonnevisning_plan.md) —
  kolonne-håndtering i Analyse-fanen
- [src_struktur_og_vokabular.md](src_struktur_og_vokabular.md) —
  hvor pivot-popup-koden bør ligge (sannsynligvis
  `src/audit_actions/pivot/` siden det er en popup åpnet fra Analyse)
- [TREEVIEW_PLAYBOOK.md](../TREEVIEW_PLAYBOOK.md) — `ManagedTreeview`-
  mønsteret for pivot-resultat-visning
