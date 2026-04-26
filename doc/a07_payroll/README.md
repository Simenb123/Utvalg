# A07 Lonn: Struktur Og Dokumentasjon

Denne mappen samler dokumentasjon for A07-lonnsporet i Utvalg.

Hvis du er ny i repoet, start med `CURRENT_STATUS.md`. Det er den korte,
operative statusen: hva som er gjort, hva som fortsatt ikke er godt nok, og
hva vi jobber etter videre. Bruk `STATUS_AND_GOAL.md` som lengre
overtakelsesnotat og historikk.

## Hva dette sporet dekker

A07-lonnsporet dekker fire tett koblede omrader:

- A07-fanen og arbeidsflyten rundt matching, koblinger og kontroll
- lonnsklassifisering og payroll-relevans
- RF-1022 og kontrolloppstilling
- handoff til saldobalanse nar videre klassifisering ma skje der

## Dagens entrypoints

Disse er fortsatt gjeldende runtime-entrypoints:

- `src/pages/a07/page_a07.py`
- `page_a07.py`
- `payroll_classification.py`
- `saldobalanse_payroll_mode.py`
- `a07_feature/payroll/`
- `a07_feature/control/`
- `a07_feature/ui/`

Navaerende tommelfingerregel:

- `src/pages/a07/page_a07.py` er kanonisk page shell.
- `page_a07.py` i repo-roten er offentlig compat-shim.
- `a07_feature/` er intern motor/runtime.
- eldre `page_a07_*`, `control_*` og `page_control_data.py` lever videre der de
  trengs som compat-stier.

De viktigste kanoniske modulomraadene naa er:

- `a07_feature/payroll/` for payroll- og RF-1022-kjernen
- `a07_feature/control/` for kontrollmotor, audit og statement-logikk
- `a07_feature/ui/` for kanonisk UI-lag
- tynne wrappers som `page_a07_dialogs.py`, `page_a07_context_menu.py`,
  `page_a07_project_actions.py`, `page_windows.py` og `page_paths.py` for
  bakoverkompatibilitet

## Hva du finner i denne dokumentasjonen

- `CURRENT_STATUS.md`: kort gjeldende status, siste opprydding og videre plan
- `STATUS_AND_GOAL.md`: samlet historikk, formal, arbeidsprinsipper og neste mal
- `WORKFLOW.md`: hvordan A07-lonn faktisk flyter i dag
- `LIVE_VERIFICATION_CHECKLIST.md`: sjekkliste for test mot faktisk klientdata
- `MODULE_MAP.md`: dagens kanoniske filer, wrappers og compat-lag
- `TESTING.md`: hvilke tester som beskytter dette sporet
- `EVIDENCE_ROADMAP.md`: beslutningene rundt structured evidence, `Explain`
  som visningsfelt og solver v2-retning

## Status naa

Struktur, testing og dokumentasjon er na i mye bedre samsvar:

- `src/pages/a07/page_a07.py` er etablert som offentlig shell
- store A07-monolitter er splittet ned i mindre kanoniske moduler
- testmonolitten er splittet til `tests/a07/`
- modulbudsjetter og storrelsesrapport beskytter videre struktur
- gamle importstier lever videre som compat der det fortsatt trengs

## Aktiv Produktretning

A07-sporet er na mer enn en migreringsstruktur. Vi jobber aktivt med a gjore
matching, RF-1022 og koblingsflyten tryggere i praktisk revisjonsarbeid. Les
`STATUS_AND_GOAL.md` for gjeldende mal, prinsipper og neste prioriteringer.

## Viktig Retning Etter A07-13

- A07-koder er canonical matchingnivaa.
- RF-1022 er aggregert kontroll- og visningsnivaa.
- `Explain` er visningsfelt. Matching, RF-1022, solver og auto-plan skal bruke
  strukturerte evidence-felt.
- Nye A07-aliaser, ekskluderinger og boost-kontoer skal skrives til
  `global_full_a07_rulebook.json`.
- `global_full_a07_rulebook.json` er eneste aktive A07-kildesannhet.
  Legacy konseptaliasfiler brukes ikke lenger av A07-runtime.
