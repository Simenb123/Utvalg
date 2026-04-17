# RF-1022: behandlingslogikk

## Formål
RF-1022-logikken skal ikke bare avgjøre hvilken post en konto hører til, men også hvordan beløpet behandles i spesifikasjonen. Workbook-logikken er fasit.

## Behandlingstyper
### COST
Vanlig kostnadskonto.

Regel:
- `Endring -> kostnadsført`

Typiske kontoer:
- `5000`
- `5002`
- `5020`

### ACCRUAL_PAY
Skyldig eller påløpt lønnsforpliktelse.

Regel:
- `+ IB` til tillegg tidligere år
- `- UB` til fradrag påløpt

Kortform i GUI:
- `RF-1022: +|IB| - |UB|`

Typiske kontoer:
- `2930 Skyldig lønn`
- `2940 Skyldig feriepenger`

### ACCRUAL_AGA
Skyldig eller påløpt arbeidsgiveravgift.

Regel:
- behandles som egen påløpt/skyldig familie
- skal ikke forveksles med vanlige lønnsytelser

Typiske kontoer:
- `2770 Skyldig arbeidsgiveravgift`
- `2785 Påløpt arbeidsgiveravgift på ferielønn`

### WITHHOLDING
Trekk- og oppgjørskontoer.

Regel:
- kontroll-/oppgjørskonto
- ikke vanlig lønnsytelse

Typisk konto:
- `2600 Forskuddstrekk`

### REFUND
Refusjonskontoer.

Regel:
- behandles som refusjonsspor, ikke som vanlig kostnadslønn

Typisk konto:
- `5800 Refusjon av sykepenger`

### PERIODISATION_PAY
Periodiseringskontoer for lønn og feriepenger.

Regel:
- behandles eksplisitt som periodiseringsfamilie
- kan få RF-1022-behandling uten å være vanlige A07-kandidater

Typiske kontoer:
- `2945`
- `5095`
- `5096`

## Regnereglene
### Kostnadskontoer
For kostnadskontoer brukes:

- `Endring -> kostnadsført`

Dette betyr at årets bevegelse er det beløpet som går inn i kostnadsført ytelse.

### Skyldig og påløpt
For skyldige og påløpte balanseposter brukes:

- `+ IB` til tillegg tidligere år
- `- UB` til fradrag påløpt

Dette er samme logikk som kort beskrives som:

- `+ IB - UB`

## Hvorfor 2940 Skyldig feriepenger behandles slik
`2940 Skyldig feriepenger` er ikke en vanlig kostnadskonto. Den representerer en lønnsforpliktelse som går over årsskiftet.

Derfor:
- inngående saldo (`IB`) representerer beløp fra tidligere år som nå skal tas med som tillegg
- utgående saldo (`UB`) representerer påløpte beløp som fortsatt ikke er innberettet og derfor skal trekkes fra i årets beregning

Det er derfor `2940` behandles som:

- `+ IB - UB`

og ikke som:

- `Endring -> kostnadsført`

## Kontoeksempler
### 2930 Skyldig lønn
- behandlingstype: `ACCRUAL_PAY`
- logikk: `+ IB - UB`

### 2940 Skyldig feriepenger
- behandlingstype: `ACCRUAL_PAY`
- logikk: `+ IB - UB`

### 2770 Skyldig arbeidsgiveravgift
- behandlingstype: `ACCRUAL_AGA`
- logikk: skyldig/påløpt AGA-spor

### 2785 Påløpt arbeidsgiveravgift på ferielønn
- behandlingstype: `ACCRUAL_AGA`
- logikk: skyldig/påløpt AGA-spor

### 2600 Forskuddstrekk
- behandlingstype: `WITHHOLDING`
- logikk: kontroll-/oppgjørsspor, ikke vanlig ytelseskonto

### 2945, 5095, 5096
- behandlingstype: `PERIODISATION_PAY`
- logikk: periodisering/påløpt-spor, vurderes eksplisitt

## Hvordan dette vises i GUI
I `Saldobalanse` vises behandlingen som kort tekst for valgt rad, for eksempel:

- `RF-1022: Endring -> kostnadsført`
- `RF-1022: +|IB| - |UB|`

I RF-1022-spesifikasjonen vises behandlingen videre i de relevante kolonnene:
- kostnadsført
- tillegg tidligere år
- fradrag påløpt
- samlede ytelser

## Viktig avgrensning
RF-1022-relevans og A07-forslag er ikke det samme.

En konto kan være:
- relevant for RF-1022
- men ikke en vanlig A07-kandidat

Dette gjelder særlig:
- skyldige kontoer
- påløpte kontoer
- periodiseringskontoer
- trekk-/oppgjørskontoer
