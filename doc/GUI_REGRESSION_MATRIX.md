# GUI Regression Matrix og Gates

Dette dokumentet beskriver minste testnivaa per boelge for store GUI-features i `Utvalg-1`.

## Felles prinsipper
- Hver boelge maa ha:
  - enhetstester for ny logikk
  - headless GUI-naere tester for state, controllers og view-builders
  - minst én manuell smoketest paa reelle klientdata
- Popupvinduer er kun tillatt for filvalg, admin og avanserte noedverktoey.
- Performance skal vurderes paa store SAF-T-/dataset-caser foer hver gate.

## Gate 1: Analyse, A07 og MVA

### A07
- last A07
- bruk aktiv saldobalanse
- kjoer Tryllestav
- drag/drop eller bruk forslag
- lagre mapping
- eksporter
- lukk og aapne igjen og faa tilbake state

### MVA
- aktiver MVA-visning i Analyse
- verifiser MVA-pivot
- importer kontoutskrift
- kjoer avstemming mot Skatteetaten
- verifiser status og eksport
- lukk og aapne igjen og behold klientspesifikke innstillinger

### Analyse
- last datasett
- bytt mellom RL, SB og transaksjoner
- drill fra saldobalansekonto til transaksjoner
- verifiser skjul nulllinjer / sumlinjer
- verifiser kommentarer, motpost og tilleggsposteringer
- verifiser TB-only-modus: saldobalansevisninger virker, transaksjonskrevende funksjoner er tydelig nedtonet eller skjult

## Gate 2: Konsolidering MVP
- opprett klient/aar-prosjekt
- importer TB for minst to selskaper
- map vesentlige kontoer
- foer minst én elimineringsbatch
- kjoer konsolidering uten feil
- eksporter arbeidsbok
- lukk og aapne igjen og faa tilbake state
- verifiser at hele flyten fungerer uten hovedbok eller SAF-T, sa lenge TB finnes

## Gate 3: Reskontro v1
- aapne reskontro i modus Kunder
- filtrer og velg motpart
- drill til transaksjoner og videre til bilag
- bytt til Leverandorer
- verifiser lokale risikosignaler
- verifiser konto-/periodefiltre

## Gate 4: Rapporter og arbeidspapirer
- bygg Excel-utdata uten feil
- bygg PDF-utdata uten feil
- verifiser at output stemmer med GUI-tall
- verifiser at output kan kobles til revisjonskontekst
