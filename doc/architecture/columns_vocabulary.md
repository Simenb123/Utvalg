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

## Format-konvensjon

- **Rene verdier (UB, IB, HB, UB_fjor) vises med 4-sifret år** for å være
  entydige i Excel-eksporter og dokumenter (eks. "UB 2025").
- **Endringskolonner vises med 2-sifret år** for å spare plass — operandene
  i navnet (UB-IB, UB) gjør at det fremdeles er entydig hva som er trukket
  fra hva (eks. "Δ UB 25/24").
- Excel-eksport bruker samme labels som GUI.

## Kanoniske ID-er

| Intern ID | Brukerlabel (med år=2025) | Brukerlabel (uten år) | Semantikk |
|---|---|---|---|
| `Konto` | "Konto" | "Konto" | Kontonummer |
| `Kontonavn` | "Kontonavn" | "Kontonavn" | Kontotekst |
| `OK` | "OK" | "OK" | OK-flagg (ferdigrevidert) |
| `OK_av` | "OK av" | "OK av" | Hvem som markerte OK |
| `OK_dato` | "OK dato" | "OK dato" | Når markert OK |
| `Vedlegg` | "Vedlegg" | "Vedlegg" | Vedlagte filer |
| `Gruppe` | "Gruppe" | "Gruppe" | Konto-grupperings-tag |
| `IB` | "IB 2025" | "IB" | Inngående saldo (SB) |
| `UB` (eller `Sum`) | "UB 2025" | "UB" | Utgående saldo (SB) |
| `UB_fjor` | "UB 2024" | "UB i fjor" | UB forrige regnskapsår (SB) |
| `HB` | "HB 2025" | "HB" | HB-aggregat (sum transaksjoner i HB) |
| `Endring` | "Δ UB-IB 25" | "Δ UB-IB" | Periode-bevegelse, UB − IB |
| `Endring_fjor` | "Δ UB 25/24" | "Endring" | År-over-år, UB − UB_fjor |
| `Endring_pct` | "Δ % 25/24" | "Endring %" | Prosentvis YoY-endring |
| `Antall` | "Antall" | "Antall" | Antall transaksjoner |
| `Antall_bilag` | "Antall bilag" | "Antall bilag" | Antall unike bilag |
| `AO_belop` | "Tilleggspostering" | "Tilleggspostering" | Sum tilleggsposteringer (ÅO) |
| `UB_for_ao` | "UB før ÅO" | "UB før ÅO" | UB uten tilleggsposteringer |
| `UB_etter_ao` | "UB etter ÅO" | "UB etter ÅO" | UB inkludert tilleggsposteringer |
| `BRREG` | "BRREG 2024" | "BRREG" | BRREG-tall, brreg_year injiseres |
| `Avvik_brreg` | "Avvik mot BRREG" | "Avvik mot BRREG" | Differanse mot BRREG |
| `Avvik_brreg_pct` | "Avvik % mot BRREG" | "Avvik % mot BRREG" | Prosentvis avvik mot BRREG |

## Viktig semantisk skille: `Endring` vs `Endring_fjor`

To kolonner med "Endring" i navnet er ofte forvirrende. Skillet er bevisst,
og labels gjør operandene eksplisitte:

- **`Endring`** = periode-bevegelse innenfor samme år: `UB − IB`.
  Vises som *"Δ UB-IB 25"* — operandene er entydig hva som er trukket fra hva.
- **`Endring_fjor`** = år-over-år sammenligning: `UB − UB_fjor`.
  Vises som *"Δ UB 25/24"* — UB i 2025 minus UB i 2024.

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
