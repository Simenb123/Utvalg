# Saldobalanse: arbeidsflyt for lønnsklassifisering

## Kort fortalt
`Saldobalanse` er den daglige hovedflaten for manuell klassifisering av lønnskontoer. Her jobber vi med:

- `A07-kode`
- `RF-1022-post`
- eventuelle `Lønnsflagg`

`A07` og kontrolloppstilling brukes som støtte og verifikasjon, ikke som primær arbeidsflate.

## Anbefalt arbeidsflyt
1. Gå til `Saldobalanse`.
2. Sett `Preset` til `Lønnsklassifisering`.
3. Les `IB`, `Endring` og `UB` på raden du vurderer.
4. Se på:
   - lagret `A07-kode`
   - lagret `RF-1022-post`
   - forslag i `A07-forslag`
   - forslag i `RF-1022-forslag`
5. Høyreklikk på raden og velg riktig handling.

## Hovedhandlingene
### Godkjenn forslag
Brukes når dagens forslag ser riktige ut. Handlingen bruker bare nåværende forslag fra motoren.

### Bruk fjorårets klassifisering
Brukes når samme konto normalt betyr det samme som i fjor. Handlingen bruker bare historisk klassifisering når historikk finnes.

### Tildel A07-kode
Brukes når du vil sette eller overstyre A07 manuelt.

### Tildel RF-1022-post
Brukes når du vil sette eller overstyre RF-1022 manuelt.

### Legg til / fjern lønnsflagg
Brukes når kontoen trenger ekstra egenskaper som påvirker behandling i RF-1022 eller kontrolloppstilling.

### Lær av denne raden
Brukes når systemet bommer og du vil lære det av faktisk kontonavn eller kontonummer.

Tilgjengelige læringsvalg:
- `Kontonavn -> A07-alias`
- `Konto -> A07-boost`
- `Kontonavn -> RF-1022-alias`

## Hvordan lese radene
- `IB`: inngående balanse
- `Endring`: bevegelse i året
- `UB`: utgående balanse

For vanlige kostnadskontoer er `Endring` ofte det viktigste beløpet.
For skyldige, påløpte og periodiserte kontoer er `IB` og `UB` viktige for RF-1022-behandling.

## Når bruker vi A07 og kontrolloppstilling?
### A07
Brukes når du vil:
- kontrollere summer per A07-kode
- se koblede kontoer
- verifisere at A07-bildet henger sammen

### Kontrolloppstilling / RF-1022
Brukes når du vil:
- kontrollere hvilke kontoer som ligger bak en RF-1022-post
- forstå hvordan `IB`, `Endring` og `UB` behandles
- verifisere mot workbook-logikken

## Oppfrisk etter Admin-endringer
Hvis du endrer noe i `Admin`, for eksempel:
- `Konseptaliaser`
- `A07-regler`
- `RF-1022 og flagg`

så er normal arbeidsflyt:
1. `Lagre` i `Admin`
2. gå tilbake til `Saldobalanse`
3. trykk `Oppfrisk`

Dette er nok for å se effekt av regel- og aliasendringer i forslagene.

## Tommelfingerregler
- Bruk `Godkjenn forslag` når systemet allerede er tydelig.
- Bruk `Bruk fjorårets klassifisering` når kontoen er stabil år over år.
- Bruk manuell tildeling når forslag eller historikk er feil.
- Bruk `Lær av denne raden` når du ser et mønster som bør læres videre.
