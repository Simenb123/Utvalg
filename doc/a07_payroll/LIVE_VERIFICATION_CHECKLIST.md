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
| A07-visning | A07-koder er hovedlisten og ferdige koder er gronne ved diff 0 |  |  |
| AGA-plikt | AGA-kolonne/visning viser `Ja`, `Nei` eller ukjent fra kilde/regler |  |  |
| Global auto | `Kjor automatisk matching` kobler bare trygge kandidater |  |  |
| Auto ved oppdatering | Klare 100-prosent-treff kobles uten at hver A07-kode maa klikkes |  |  |
| 2940 | `Skyldig feriepenger` bruker riktig `Kol` og blir relevant kandidat |  |  |
| Feriepenger special_add | Balanse-/periodiseringskontoer inngaar sammen med kostnad naar regelen tilsier det |  |  |
| Styrehonorar special_add | Avsatt styrehonorar/periodisering kan forklare diff naar alias og belop treffer |  |  |
| 6701 | `Honorar revisjon` auto-mappes ikke til lonn/`annet` |  |  |
| 5890 | `Annen refusjon` blir ikke trygg refusjon uten spesifikk evidens |  |  |
| 5800 | `Refusjon av sykepenger` kan bli trygg ved NAV/sykepenger-stotte |  |  |
| Generisk `annet` | Bodleie/kantine/driftskostnader blir ikke trygge uten tydelig evidens |  |  |
| A07-grupper | Vanlige lonnsgrupper summeres uten duplikater eller heng i GUI |  |  |
| Mistenkelig kobling | Eksisterende darlige koblinger flagges tydelig |  |  |
| Hoyreklikk GL | Tildel/fjern/avansert mapping virker |  |  |
| Hoyreklikk GL laering | `Laer av konto` skriver til A07-regelbok og refreshes raskt |  |  |
| Hoyreklikk Koblinger | Vis i GL/fjern/avansert mapping virker |  |  |
| Hoyreklikk nederste liste | Forslag/koblinger har meny etter refresh og tab-bytte |  |  |
| Delete | Fjerner valgt mapping nar konto ikke er last |  |  |
| Filter | `Alle`/`Kun mappede` og kontoseriefilter virker uten trege bakgrunnsjobber |  |  |
| Verktoy-meny | Menyvalg som beholdes har tydelig funksjon og ingen utdatert/dod flyt |  |  |

## Etter Test

- Noter hvilke kontoer som ble feil kandidat.
- Noter om feilen skyldes katalog/alias, belopsgrunnlag, gammel mapping eller UI-handling.
- Ikke slett eksisterende darlige koblinger automatisk; flagg dem og rydd manuelt.
