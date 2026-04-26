# A07 Evidence Roadmap

Sist oppdatert: 2026-04-26.

Dette notatet destillerer Deep Research-rapporten og de siste A07-valgene til en
praktisk retning for videre utvikling.

## Låste Prinsipper

- A07-kode er primær arbeidsflate og canonical matchingnivå.
- RF-1022 og kontrolloppstilling er avstemming, summering og kvalitetssikring,
  ikke primær alias-/matchingmotor.
- `Explain` og `HvorforKort` er mennesketekst. Beslutningslogikk skal bruke
  strukturerte evidence-felt.
- Auto-logikk skal aldri endre 0-diff-koder, låste koder eller trygge
  mappinger.
- `annet` er residual/siste-utvei og skal normalt være review-only.

## Evidence-Kontrakt

A07-kandidater skal bygges med maskinlesbare felt:

- `UsedRulebook`
- `UsedHistory`
- `UsedUsage`
- `UsedSpecialAdd`
- `UsedResidual`
- `AmountEvidence`
- `AmountDiffAbs`
- `HitTokens`
- `AnchorSignals`
- `SuggestionGuardrail`
- `SuggestionGuardrailReason`

Gamle cache-/testdata kan fortsatt ha tokens som `regel=` eller `bruk=` i
`Explain`. Det er kun lov å tolke dette i den sentrale evidence-normaliseringen.
Ny beslutningslogikk skal ikke lese fritekst for å avgjøre om en kandidat er
trygg.

## Neste Motorsteg

1. Bruk evidence-kontrakten overalt i RF-1022-kandidater, guardrails, tags,
   global auto og residualsolver.
2. Behold GUI kompakt: korte statuser i tabellen, detaljer kun der bruker ber om
   dem.
3. Bygg solver v2 som komponentanalyse over små sett av åpne A07-koder og
   kontoer, ikke som global brute force.
4. La solver v2 foreslå scenarioer først: `Trygg løsning`, `Må vurderes`,
   `Krever gruppe`, `Krever splitt` og `Mistenkelig rest`.
5. Utvid auto-apply kun når hele scenarioet er trygt, eksakt og ikke berører
   ferdige/låste/trygge koblinger.

## Hvorfor Dette Er Viktig

Deep Research-rapporten bekrefter at dagens A07 har en god regelbasert kjerne,
men at videre smartlogikk blir vanskelig hvis fritekst brukes som skjult API.
Strukturert evidence gjør at vi kan forbedre matching, gruppeforslag og solver
uten å gjøre GUI-et mer rotete eller introdusere usporbare avgjørelser.
