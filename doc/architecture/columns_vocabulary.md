# Kolonne-vokabular

Kanonisk vokabular for kolonner som vises i tabeller på tvers av Utvalg-fanene.
Implementert i [src/shared/columns_vocabulary.py](../../src/shared/columns_vocabulary.py).

## Hvorfor

Tidligere hadde hver fane sine egne hardkodede labels. Resultat: samme
konsept fikk forskjellig tekst i ulike faner ("UB i fjor" i Statistikk-KPI vs
"UB fjor" i Statistikk-tabellen vs "UB 2024" i Analyse). Brukeren må mentalt
oversette mellom variantene.

Med ett felles vokabular forsvinner inkonsistensen automatisk: alle faner
kaller `heading(col_id, year=…)` og får samme tekst.

## Bruk

```python
from src.shared.columns_vocabulary import heading, active_year_from_session

year = active_year_from_session()
label = heading("UB", year=year)        # → "UB 2025"
label = heading("UB_fjor", year=year)   # → "UB 2024"
label = heading("Endring_fjor")          # → "Endring"
```

`active_year_from_session()` er en bekvemmelighets-funksjon som leser
`session.year` og returnerer int eller None. Faner som allerede har en
lokal year-getter kan sende inn det.

## Kanoniske ID-er

| Intern ID | Brukerlabel | Semantikk |
|---|---|---|
| `Konto` | "Konto" | Kontonummer |
| `Kontonavn` | "Kontonavn" | Kontotekst |
| `OK` | "OK" | OK-flagg (ferdigrevidert) |
| `OK_av` | "OK av" | Hvem som markerte OK |
| `OK_dato` | "OK dato" | Når markert OK |
| `Vedlegg` | "Vedlegg" | Vedlagte filer |
| `Gruppe` | "Gruppe" | Konto-grupperings-tag |
| `IB` | "IB" | Inngående saldo |
| `UB` (eller `Sum`) | "UB \<år\>" | Utgående saldo, år injiseres dynamisk |
| `UB_fjor` | "UB \<år-1\>" eller "UB i fjor" | UB forrige regnskapsår |
| `Endring` | "Bevegelse i år" | Periode-bevegelse, UB − IB |
| `Endring_fjor` | "Endring" | År-over-år, UB − UB_fjor |
| `Endring_pct` | "Endring %" | Prosentvis YoY-endring |
| `Antall` | "Antall" | Antall transaksjoner |
| `Antall_bilag` | "Antall bilag" | Antall unike bilag |
| `AO_belop` | "Tilleggspostering" | Sum tilleggsposteringer (ÅO) |
| `UB_for_ao` | "UB før ÅO" | UB uten tilleggsposteringer |
| `UB_etter_ao` | "UB etter ÅO" | UB inkludert tilleggsposteringer |
| `BRREG` | "BRREG \<år\>" eller "BRREG" | BRREG-tall, år injiseres |
| `Avvik_brreg` | "Avvik mot BRREG" | Differanse mot BRREG |
| `Avvik_brreg_pct` | "Avvik % mot BRREG" | Prosentvis avvik mot BRREG |

## Viktig semantisk skille: `Endring` vs `Endring_fjor`

To kolonner med "Endring" i navnet er ofte forvirrende. Skillet er bevisst:

- **`Endring`** = periode-bevegelse innenfor samme år: `UB − IB`.
  Vises som *"Bevegelse i år"* for å gjøre forskjellen visuell.
- **`Endring_fjor`** = år-over-år sammenligning: `UB − UB_fjor`.
  Vises som *"Endring"* fordi det er den brukeren typisk forstår som "endring".

Bruk riktig ID — å forveksle dem gir tall som ser like ut men betyr
forskjellige ting (særlig for IB-saldoer, der `UB − IB` og `UB − UB_fjor`
ofte er nært, men ikke identisk).

## Migrering av eksisterende kode

Faner med hardkodede labels migreres ved å:

1. Importere `heading` (og `active_year_from_session` om nødvendig).
2. Erstatte string-literals med kall til `heading(col_id, year=…)`.
3. Hvis tree-overskrifter er låst til kolonne-ID-en (som i Statistikk
   `_make_tree`): overskriv heading-text etter `tree`-konstruksjon med
   `tree.heading(col_id, text=heading(label_id, year=…))`.

Migrert hittil:
- Analyse-fanen (gammel `analysis_heading()` er nå tynn wrapper)
- Statistikk-fanen (KPI-banner, kontoer-tabell, Excel-eksport)

## Hva er *ikke* dekket av vokabularet

- Tabell-bredder, kolonneorden, drag-n-drop og sorterings-mekanikk.
  Det er en separat sak (felles widget-stack), foreløpig kun implementert
  i Analyse-fanen.
- Tall-formatering (decimaler, tusen-skille, fortegnsvisning).
  Dekkes av `formatting.py`.
- Faner som beholder egne, fane-spesifikke kolonner som ikke har en
  delt mening. Disse skal *ikke* tvinges inn i vokabularet.
