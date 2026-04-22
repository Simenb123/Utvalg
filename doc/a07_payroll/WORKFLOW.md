# A07 Lonn Workflow

Dette dokumentet beskriver dagens praktiske A07-flyt i Utvalg. A07-sporet er
ikke lenger bare en migreringsmal: det er en aktiv arbeidsflate for trygg
avstemming av A07/A-melding mot saldobalanse, A07-koder og RF-1022.

## Hovedflyt

```text
A07-kilde
  -> parser og grupperte A07-belop
  -> aktiv saldobalanse
  -> forslag med guardrails
  -> RF-1022-kontrollflate
  -> trygge koblinger eller manuell vurdering
```

## Praktisk Arbeidsflyt

1. Last A07-kilde.
2. Oppdater mot aktiv saldobalanse for valgt klient og ar.
3. Bruk RF-1022 som primaer kontrollflate.
4. Se lokale kandidater i `Forslag` for valgt RF-1022-post eller A07-kode.
5. Kjor `Kjor automatisk matching` for globale, trygge kandidater.
6. Kontroller `Koblinger` og eventuelle `Maa vurderes`-poster.
7. Rydd feil eller gamle koblinger med hoyreklikk, Delete eller avansert mapping.

## Dagens Hovedflate

A07-hovedflaten er bevisst roet ned. Nederste omrade viser bare:

- `Forslag`: RF-1022- eller A07-kandidater for valgt arbeidsnivaa.
- `Koblinger`: kontoene som er koblet til valgt post/kode.

Kontrolloppstilling, historikk og umappede detaljer er fortsatt tilgjengelige via
verktoy, compat-flater eller guidede handlinger, men de skal ikke dominere
hovedarbeidsflaten.

## Matchingprinsipp

Automatikk skal feile lukket:

- Belop alene er ikke nok.
- Historikk alene er ikke nok for nye trygge forslag.
- RF-1022-kandidater ma ha riktig gruppe, faglig/aliasstotte og egen
  belopsstotte.
- Eksisterende darlige koblinger slettes ikke automatisk, men flagges som
  mistenkelige og gjores enkle a rydde.
- A07-koder er matchingnivaet. RF-1022 brukes som aggregert kontrollvisning.
- Nye A07-laeringer skrives til A07-regelbok, ikke til legacy konseptaliaser.

Eksempler som skal beskyttes:

- `2940 Skyldig feriepenger` bruker periodiserings-/balansegrunnlag og skal ikke
  forsvinne fra feriepenger-kandidater.
- `6701 Honorar revisjon` skal ikke kobles til lonn/`annet` pa belop alene.
- `5890 Annen refusjon` skal ikke vaere trygg refusjon uten NAV/sykepenger/
  foreldrepenger eller annen separat evidens.

## Nar Saldobalanse Tar Over

Saldobalanse brukes nar selve konto-/profilklassifiseringen ma ryddes:

- A07-kode
- RF-1022-post
- lonnsflagg
- mistenkelig lagret profil

A07 skal vise kontrollbehovet tydelig, men saldobalanse er fortsatt riktig sted
for bredere konto- og profilrydding.

## Laering Fra Kontonavn

Nederste `Koblinger`-liste i A07 har hoyreklikkvalg for aa laere av en konto:

- `Legg navn til A07-alias`: legger kontonavnet til valgt/mappet A07-kodes
  `keywords`.
- `Ekskluder navn fra A07-kode`: legger kontonavnet til A07-kodens
  `exclude_keywords`.
- `Fjern mapping og ekskluder navn`: fjerner koblingen via checked remove-service
  og legger samtidig kontonavnet til `exclude_keywords`.

Dette er ment for aapenbare feil, for eksempel naar en konto er koblet til en
A07-kode fordi navnet eller belopet ga et for svakt treff.
