# A07 Live-Verifisering

Bruk denne sjekklisten nar A07 testes mot faktisk klientdata. Malet er a fange
konkrete konto-/kodefeil for de blir gjort til regelendringer.

## Oppsett

- Klient:
- Ar:
- A07-kilde:
- Aktiv saldobalanse:
- Tester:
- Dato:

## Sjekkpunkter

| Sjekk | Forventning | Resultat | Konto/kode/notat |
| --- | --- | --- | --- |
| Last A07 | A07-kilde lastes uten traceback |  |  |
| Oppdater | Aktiv saldobalanse brukes |  |  |
| RF-1022-visning | Postene 100/111/112 viser GL, A07 og diff |  |  |
| Global auto | `Kjor automatisk matching` kobler bare trygge kandidater |  |  |
| 2940 | `Skyldig feriepenger` bruker riktig `Kol` og blir relevant kandidat |  |  |
| 6701 | `Honorar revisjon` auto-mappes ikke til lonn/`annet` |  |  |
| 5890 | `Annen refusjon` blir ikke trygg refusjon uten spesifikk evidens |  |  |
| 5800 | `Refusjon av sykepenger` kan bli trygg ved NAV/sykepenger-stotte |  |  |
| Mistenkelig kobling | Eksisterende darlige koblinger flagges tydelig |  |  |
| Hoyreklikk GL | Tildel/fjern/avansert mapping virker |  |  |
| Hoyreklikk Koblinger | Vis i GL/fjern/avansert mapping virker |  |  |
| Delete | Fjerner valgt mapping nar konto ikke er last |  |  |

## Etter Test

- Noter hvilke kontoer som ble feil kandidat.
- Noter om feilen skyldes katalog/alias, belopsgrunnlag, gammel mapping eller UI-handling.
- Ikke slett eksisterende darlige koblinger automatisk; flagg dem og rydd manuelt.
