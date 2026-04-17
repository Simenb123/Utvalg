# Klassifiseringsfelter i lønnsflyten

## Hovedfeltene i Saldobalanse
### A07-kode
Den lagrede A07-klassifiseringen for kontoen.

### A07-forslag
Det systemet akkurat nå foreslår som A07-kode.

### A07 OK
Viser grønn hake når lagret `A07-kode` og dagens `A07-forslag` er like.

### RF-1022-post
Den lagrede RF-1022-posten for kontoen.

### RF-1022-forslag
Det systemet akkurat nå foreslår som RF-1022-post.

### RF-1022 OK
Viser grønn hake når lagret `RF-1022-post` og dagens `RF-1022-forslag` er like.

### Status
Den primære arbeidsstatusen i gridet. Denne brukes for å avgjøre hva vi bør gjøre videre med raden.

## Lagret verdi, forslag og historikk
### Lagret verdi
Det som allerede er lagret på kontoen i dagens klassifisering.

### Forslag
Det dagens motor foreslår basert på aliaser, regler, intervaller, kontooppførsel og annen nåværende logikk.

### Historikk
Det samme kontoen ble klassifisert som tidligere, typisk fra fjoråret eller lagret historisk profil.

Forslag og historikk er ikke det samme:
- `Godkjenn forslag` bruker dagens motor
- `Bruk fjorårets klassifisering` bruker tidligere kjent klassifisering

## Lønnsflagg
`Lønnsflagg` er ekstra egenskaper, ikke hovedklassifiseringen.

Typiske eksempler:
- `AGA-pliktig`
- `Feriepengegrunnlag`
- `Opplysningspliktig`
- `Naturalytelse`
- `Refusjon`

Flaggene brukes for å styre hvordan beløpet behandles i RF-1022 og kontrolloppstilling. De svarer ikke alene på hva kontoen “er”, men på hvordan kontoen skal behandles.

## Høyreklikkhandlinger
### Godkjenn forslag
Bruker dagens forslag når det finnes en reell forskjell mellom lagret og foreslått verdi.

### Bruk fjorårets klassifisering
Bruker historisk klassifisering når historikk finnes.

### Tildel A07-kode / Tildel RF-1022-post
Brukes for manuell overstyring. Manuell tildeling er fasit når forslag eller historikk er feil.

### Lær av denne raden
Skriver inn læring i oppsettet uten at du må gå via Admin først.

Det brukes til:
- kontonavn som nytt A07-alias
- kontonummer som A07-boost
- kontonavn som RF-1022-alias

Etter lagring kan effekten normalt sees etter `Oppfrisk`.

## Admin-fanene
### Konseptaliaser
Styrer hvilke ord og navn som matcher hvilke konsepter.

### A07-regler
Styrer scoring, basis og intervaller for A07.

### RF-1022 og flagg
Styrer kontrolloppstilling, RF-1022-katalog og tilhørende flagg.

## Praktisk lesemåte
Hvis du er i tvil om en rad:
1. se lagret verdi
2. se forslag
3. se `A07 OK` og `RF-1022 OK`
4. les detaljfeltet øverst
5. velg `Godkjenn forslag`, `Bruk fjorårets klassifisering` eller manuell tildeling
