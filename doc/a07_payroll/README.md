# A07 Lonn: Struktur Og Dokumentasjon

Denne mappen samler dokumentasjon for A07-lonnsporet i Utvalg.

Hvis du er ny i repoet, start med `STATUS_AND_GOAL.md`. Det dokumentet fungerer
som overtakelsesnotat: hvorfor A07-sporet finnes, hva som nettopp er gjort,
dagens tekniske status, og hvilken plan som bor folges videre.

## Hva dette sporet dekker

A07-lonnsporet dekker fire tett koblede omrader:

- A07-fanen og arbeidsflyten rundt matching, koblinger og kontroll
- lonnsklassifisering og payroll-relevans
- RF-1022 og kontrolloppstilling
- handoff til saldobalanse nar videre klassifisering ma skje der

## Dagens entrypoints

Disse er fortsatt gjeldende runtime-entrypoints:

- `page_a07.py`
- `payroll_classification.py`
- `saldobalanse_payroll_mode.py`
- eksisterende `a07_feature/page_a07_*`-filer
- eksisterende `a07_feature/control_*`- og `a07_feature/page_control_data.py`

Fra og med fase 2 er disse tre payroll-modulene flyttet til `a07_feature/payroll/`,
men de gamle rotstiene beholdes som compat-shims:

- `a07_feature/payroll/classification.py`
- `a07_feature/payroll/feedback.py`
- `a07_feature/payroll/saldobalanse_bridge.py`

Fra og med fase 2, runde 2 er disse A07-lonnsmodulene ogsa flyttet inn i payroll-pakken:

- `a07_feature/payroll/rf1022.py`
- `a07_feature/payroll/profile_state.py`

Gamle A07-stier beholdes fortsatt for kompatibilitet:

- `a07_feature/page_a07_rf1022.py`
- `a07_feature/page_a07_runtime_helpers.py`

Fra og med fase 2, runde 3 er disse kontrollmodulene flyttet inn i `a07_feature/control/`:

- `a07_feature/control/data.py`
- `a07_feature/control/matching.py`
- `a07_feature/control/status.py`
- `a07_feature/control/presenter.py`
- `a07_feature/control/statement_model.py`
- `a07_feature/control/statement_source.py`

De gamle modulstiene under `a07_feature/` beholdes som compat-shims.

Fra og med fase 2, runde 4 er kontrolloppstillings-UI-et ogsa flyttet inn i
kontrollpakken:

- `a07_feature/control/statement_ui.py`

Den gamle A07-stien beholdes fortsatt som compat-shim:

- `a07_feature/page_a07_control_statement.py`

Fra og med fase 2, runde 5 er den kanoniske A07-UI-slicen flyttet inn i
`a07_feature/ui/`:

- `a07_feature/ui/page.py`
- `a07_feature/ui/canonical_layout.py`
- `a07_feature/ui/helpers.py`
- `a07_feature/ui/tree_render.py`
- `a07_feature/ui/support_render.py`
- `a07_feature/ui/render.py`

De gamle `page_a07_*`-stiene for disse modulene beholdes som compat-shims.

Fra og med fase 2, runde 6 er ogsa seleksjonslaget og legacy tree-UI flyttet
inn i `a07_feature/ui/`:

- `a07_feature/ui/selection.py`
- `a07_feature/ui/tree_ui.py`

De gamle `page_a07_selection.py`- og `page_a07_tree_ui.py`-stiene beholdes som
compat-shims.

Fra og med fase 2, runde 7 peker `page_a07.py`-fasaden direkte mot de
kanoniske flyttede `payroll`-, `control`- og `ui`-modulene, og
`a07_feature/page_a07_shared.py` er strammet inn som tydelig compat/re-export
lag med kanoniske kontrollimporter.

## Nye malmapper i fase 1

Fase 1 oppretter disse malmappene for senere migrering:

- `a07_feature/payroll/`
- `a07_feature/control/`
- `a07_feature/ui/`

`a07_feature/payroll/` er ikke lenger bare en malmappe. Den inneholder na den
kanoniske plasseringen for den flyttede payroll-kjernen.

## Hva du finner i denne dokumentasjonen

- `STATUS_AND_GOAL.md`: samlet status, formal, arbeidsprinsipper og neste mal
- `WORKFLOW.md`: hvordan A07-lonn faktisk flyter i dag
- `LIVE_VERIFICATION_CHECKLIST.md`: sjekkliste for test mot faktisk klientdata
- `MODULE_MAP.md`: dagens filer og framtidig plassering
- `TESTING.md`: hvilke tester som beskytter dette sporet

## Status etter fase 2, runde 7

Struktur og dokumentasjon er pa plass, payroll-kjernen er flyttet inn i
`a07_feature/payroll/`, og A07-loennsspesifikk RF-1022/profilstate er flyttet
dit uten at gamle importstier er brutt. Kontroll-laget har na ogsa en
kanonisk plassering under `a07_feature/control/`, inkludert UI-bindingene for
kontrolloppstilling. Den sentrale UI-slicen lever na ogsa under
`a07_feature/ui/`, inkludert seleksjonslaget og legacy tree-UI. Fasaden peker
na direkte til de flyttede kanoniske modulene, mens `page_a07_shared.py`
bevisst er beholdt som compat-lag.

## Aktiv Produktretning

A07-sporet er na mer enn en migreringsstruktur. Vi jobber aktivt med a gjore
matching, RF-1022 og koblingsflyten tryggere i praktisk revisjonsarbeid. Les
`STATUS_AND_GOAL.md` for gjeldende mal, prinsipper og neste prioriteringer.

## Viktig Retning Etter A07-13

- A07-koder er canonical matchingnivaa.
- RF-1022 er aggregert kontroll- og visningsnivaa.
- Nye A07-aliaser, ekskluderinger og boost-kontoer skal skrives til
  `global_full_a07_rulebook.json`.
- `payroll_alias_library.json` beholdes som legacy/kompatibilitetslag, men skal
  ikke vaere hovedflate for nye A07-laeringer.
