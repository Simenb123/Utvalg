# RF-1022 kontrolloppstilling: faglig kontrakt

Dette er arbeidskontrakten for A07/RF-1022-visningen i appen. Den skal sikre at
kontrolloppstillingen behandles som en standardisert avstemming, ikke som en
ekstra mappingflate.

## Formaal

Kontrolloppstillingen skal vise om bokforte lonns- og pensjonskostnader stemmer
mot A07/A-ordning paa et standardisert RF-1022-lignende format.

A07-hovedfanen er arbeidsflate for mapping, grupper og solver. RF-1022
kontrolloppstilling er rapport-/avstemmingsflate.

## Hovedformel

For opplysningspliktige ytelser er kontrollen:

```text
Kostnadsfort ytelse
+ Tillegg tidligere aar
- Fradrag palopt
= Samlede opplysningspliktige ytelser
```

Disse summeres mot A07-belop for samme RF-1022-post/kontrollgruppe.

## AGA-sporet

AGA-pliktige ytelser er ikke det samme som alle opplysningspliktige ytelser.
Det er et eget spor/delgrunnlag:

```text
GL AGA-grunnlag mot A07 AGA-pliktig belop = AGA diff
```

I motoren betyr dette:

- `opplysningspliktig` styrer om raden inngaar i `SamledeYtelser`.
- `aga_pliktig` styrer om samme rad ogsaa inngaar i `AgaGrunnlag`.
- `feriepengergrunnlag` er et eget flagg i detaljspesifikasjonen.
- `aga_pliktig` og `feriepengergrunnlag` behandles som underliggende RF-1022-spor
  av opplysningspliktige ytelser, selv om eldre profilmateriale mangler eksplisitt
  `opplysningspliktig`.

## Visningsnivaa

Oversikten skal vise summer per RF-1022-post/kontrollgruppe:

- GL opplysningspliktig
- A07 opplysningspliktig
- Diff opplysningspliktig
- GL AGA
- A07 AGA
- Diff AGA

Detaljvisningen skal ligge tett paa workbook-eksempelet i `doc/files/RF-1022.xlsx`:

- Post
- Kontonr
- Kontobetegnelse
- Kostnadsfort ytelse
- Tillegg tidligere aar
- Fradrag palopt
- Samlede ytelser
- AGA-pliktig
- AGA-grunnlag
- Feriepengergrunnlag

## Viktige avgrensninger

RF-1022-relevans og A07-mapping er ikke det samme. En konto kan vaere relevant
for kontrolloppstillingen uten aa vaere en vanlig A07-kandidat.

Eksempler:

- skyldig/palopt lonn
- skyldig/palopt arbeidsgiveravgift
- refusjon
- pensjon
- trekk-/oppgjorskontoer
- periodisering

Dette skal derfor holdes i motor-/rapportlaget, ikke gjemmes i GUI-logikk.
