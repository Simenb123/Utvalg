# Ansvar og tilordning — problembeskrivelse

**Status:** Åpen problemstilling, ikke løst.
**Sist oppdatert:** 2026-04-19
**Relaterte moduler:**
[action_link_dialog.py](../../action_link_dialog.py),
[regnskap_client_overrides.py](../../regnskap_client_overrides.py),
[page_revisjonshandlinger.py](../../page_revisjonshandlinger.py),
[team_config.py](../../team_config.py)

## Kjernespørsmålet

Hvem på teamet er ansvarlig for _hva_? I dag finnes det kun én
tilordningsmekanisme (`assigned_to` på handlingskoblinger), men
konseptuelt er det minst tre forskjellige ansvar som blandes sammen.

## Tre ansvar som i dag kollapser til ett felt

1. **Ansvar for en revisjonshandling** — "SB gjør detaljkontroll lønn".
2. **Ansvar for en saldobalansekonto** — "TN eier konto 1579 Honorarreserver".
3. **Ansvar for en regnskapslinje** — "SB eier RL 615 Andre fordringer".

De overlapper ofte i praksis, men er ikke det samme. En konto kan ha
en ansvarlig selv uten at den er knyttet til en spesifikk handling.

## Dagens implementasjon

`assigned_to` lever kun som et felt på hver **konto→handling-** eller
**RL→handling-kobling**, satt via [action_link_dialog.py](../../action_link_dialog.py).

Konsekvenser:

- For å si "TN er ansvarlig for konto 1579" er revisor tvunget til å
  først opprette en kobling mellom kontoen og en handling. Ingen
  kobling = ingen måte å tildele ansvar på.
- [page_revisjonshandlinger.py](../../page_revisjonshandlinger.py) viser
  en **Tilordnet**-kolonne som er _aggregert_ fra koblingenes
  `assigned_to` (se `_load_local_assignments`, rundt linje 298). Det
  er ikke en direkte tilordning på handlingen.
- Handlinger uten tilknyttede kontoer/RL (planlegging, avslutning,
  generelle områder) har i dag **ingen** mulighet for tilordning.

## Hvorfor dette er rotete

Samme dialog brukes til å uttrykke tre semantisk forskjellige ting:

- «Denne kontoen hører til denne handlingen» (kobling).
- «Denne personen skal gjøre denne handlingen» (handling-ansvar).
- «Denne personen eier denne kontoen» (konto-ansvar).

Brukeren ser ikke forskjellen før den blir et problem — f.eks. når
man prøver å sette ansvarlig på en planleggingshandling (umulig) eller
lurer på hvorfor «Tilordnet» i handlingsfanen plutselig viser en annen
person enn den man trodde man satte.

## Potensielle retninger (ikke besluttet)

**A. Tre parallelle ansvarsspor.**
Egen lagring per nivå: `action_assignments.json`,
`account_assignments.json`, `rl_assignments.json`. Koblinger
mellom nivåene slutter å bære `assigned_to` — ansvar arves fra
handlingen eller kontoen alt etter kontekst.

**B. Kun handling-ansvar, resten blir visning.**
Konto- og RL-ansvar avledes fra hvilke handlinger de er koblet til.
Forutsetter at alle relevante kontoer faktisk knyttes til en handling.

**C. Beholde dagens løsning, bare legge på handling-ansvar.**
Minst inngripende. Risiko: "Tilordnet"-kolonnen får to kilder
(direkte og aggregert) som krever en prioritetsregel.

## Utløsende diskusjon

Oppdaget 2026-04-19 under planlegging av
multiselect + høyreklikk-tilordning på handlingsfanen. Konklusjonen
i den runden var å _ikke_ bygge noe nå, men dokumentere problemet
og ta en helhetlig beslutning senere.

## Åpne spørsmål å ta stilling til før implementering

- Skal konto-ansvar kunne settes uavhengig av handling-kobling?
- Hvis ja: hvor i UI-et setter man det? (Analyse-fanen? Egen dialog?
  Høyreklikk på konto?)
- Hva er forholdet mellom konto-ansvar og RL-ansvar når samme
  person eier flere kontoer i en RL?
- Skal Tilordnet-kolonnen i handlingsfanen vise direkte tilordning,
  aggregert tilordning, eller begge (to kolonner)?
- Hvordan rapporterer vi "hvem har ansvar for hva" på tvers av en
  klient uten å dobbelttelle?
