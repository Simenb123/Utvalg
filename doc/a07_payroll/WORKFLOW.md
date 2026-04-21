# A07 Lonn Workflow

Denne workflow-beskrivelsen dokumenterer hvordan A07-lonnsporet faktisk er satt
opp i dag, ikke hvordan vi ideelt sett onsker at det skal se ut etter UX-redning.

## Hovedflyt

```text
A07-kilde
  -> A07 parser / grouped A07 data
  -> forslag og matching
  -> eksisterende koblinger / historikk
  -> kontrollko
  -> kontroll / RF-1022 / lonnsflagg
  -> saldobalanse-handoff ved behov
```

## Praktisk arbeidsflyt i dag

1. Last A07-kilde.
2. Les inn eller bygg opp gjeldende mapping mellom GL-konto og A07-kode.
3. Kjor forslag/matching mot GL-grunnlaget.
4. Bygg kontrollkoen for A07-koder.
5. For valgt kode:
   - se forslag
   - se historikk
   - se koblede kontoer
   - se kontroll / RF-1022
6. Hvis kode eller konto krever videre lonnsklassifisering, send brukeren til
   saldobalanse-sporet.

## Viktig realitet i dagens UI

Dagens A07-side blander flere spor samtidig:

- eksisterende koblinger
- matchingforslag
- historikk
- RF-1022 / lonnskontroll

Dette er viktig kontekst for senere UX-redning. Fase 1 dokumenterer bare
strukturen rundt dette; den rydder ikke brukerflyten.

## Nar matching er kjort

Matching blir bygd i refreshflyten for A07 og dekorert for visning for kontroll-
og forslagspaneler. Det betyr at A07 ofte har kjort forslag selv om brukerflaten
ikke leder brukeren tydelig til forslagsporet.

## Nar saldobalanse tar over

Saldobalanse er fortsatt stedet der endelig lonnsklassifisering, RF-1022-post og
flagg kan maatte ryddes. A07 identifiserer behovet, men fullforer ikke alltid
hele klassifiseringen alene.
