# A07 Lonn Module Map

Denne filen er beslutningsgrunnlaget for senere flytting. Fase 1 flytter ingen
runtime-filer, men laster plasseringen for neste faser.

## Regler

- `page_a07.py` forblir offentlig fasade
- `page_saldobalanse.py` forblir forbruker av lonnssporlogikken
- nye malmapper innfores, men uten runtime-importer i fase 1

## Fasade / compat

| Naa | Framtidig ansvar | Malmappe | Kommentar |
| --- | --- | --- | --- |
| `page_a07.py` | Offentlig fasade og monkeypatch-grense | beholdes | Offentlig entrypoint beholdes, men peker na direkte til kanoniske flyttede moduler |
| `a07_feature/page_a07_shared.py` | Compat/re-export-lag for eldre helperflate | beholdes som compat | Skal ikke brukes av aktive A07-moduler; henter na kontrollfunksjoner fra kanoniske control-moduler |

## Lonn / RF-1022

| Naa | Framtidig ansvar | Malmappe | Kommentar |
| --- | --- | --- | --- |
| `payroll_classification.py` | Lonnsklassifisering, relevans, RF-1022-forslag, flagg | `a07_feature/payroll/classification.py` | Flyttet i fase 2. Rotsti beholdt som compat-shim |
| `payroll_feedback.py` | Tilbakemelding og hjelpefunksjoner for lonnsspor | `a07_feature/payroll/feedback.py` | Flyttet i fase 2. Rotsti beholdt som compat-shim |
| `saldobalanse_payroll_mode.py` | Bridge mellom saldobalanse og lonnsspor | `a07_feature/payroll/saldobalanse_bridge.py` | Flyttet i fase 2. Rotsti beholdt som compat-shim |
| `a07_feature/page_a07_rf1022.py` | RF-1022-visning og RF-1022-vindu | `a07_feature/payroll/rf1022.py` | Flyttet i fase 2. Gammel A07-sti beholdt som compat-shim |
| payroll-relevante deler av `a07_feature/page_a07_runtime_helpers.py` | Runtime-hjelpere for lonnsprofil-/kontrollstate | `a07_feature/payroll/profile_state.py` | Flyttet i fase 2. Resten av A07-runtime blir liggende i gammel modul forelopig |

## Kontrollko / presentasjon

| Naa | Framtidig ansvar | Malmappe | Kommentar |
| --- | --- | --- | --- |
| `a07_feature/page_control_data.py` | Kontrollko, kontrolldata, RF-1022-dataformatering | `a07_feature/control/data.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/control_matching.py` | Presentasjon av forslag, historikk og smart fallback | `a07_feature/control/matching.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/control_presenter.py` | Tekstbygging for kontrollpanel | `a07_feature/control/presenter.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/control_status.py` | Statusetiketter, next action, bucket summary | `a07_feature/control/status.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/control_statement_model.py` | Modeller og view-definisjoner for kontrolloppstilling | `a07_feature/control/statement_model.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/control_statement_source.py` | Datakilde for kontrolloppstilling | `a07_feature/control/statement_source.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_control_statement.py` | UI-bindinger og handlinger for kontrolloppstilling | `a07_feature/control/statement_ui.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |

## A07 UI

| Naa | Framtidig ansvar | Malmappe | Kommentar |
| --- | --- | --- | --- |
| `a07_feature/page_a07_ui.py` | UI-entry og UI-byggerkobling | `a07_feature/ui/page.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_ui_canonical.py` | Kanonisk A07-layout | `a07_feature/ui/canonical_layout.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_support_render.py` | Rendering av stottefaner og sammendrag | `a07_feature/ui/support_render.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_selection.py` | UI-seleksjon og fanerouting | `a07_feature/ui/selection.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_render.py` | Tree- og panel-rendering | `a07_feature/ui/render.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_ui_helpers.py` | UI-hjelpere og defaultvalg | `a07_feature/ui/helpers.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_tree_render.py` | Tree-spesifikk rendering | `a07_feature/ui/tree_render.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |
| `a07_feature/page_a07_tree_ui.py` | Legacy tree-compat / tree-UI | `a07_feature/ui/tree_ui.py` | Flyttet i fase 2. Gammel sti beholdt som compat-shim |

## Saldobalanse-bridge

| Naa | Framtidig ansvar | Malmappe | Kommentar |
| --- | --- | --- | --- |
| `page_saldobalanse.py` | Forbruker av payroll bridge | beholdes | Flyttes ikke i fase 1 |
| `saldobalanse_payroll_mode.py` | Payroll bridge og mode-switching | `a07_feature/payroll/` | Selve bridge-laget flyttes senere, men kallestedet beholdes |
| `a07_feature/page_a07_runtime_helpers.py` | Laster profile/state som begge spor bruker | delt | Ma sannsynligvis splittes mellom payroll og generell A07-runtime |

## Bevisste unntak i fase 1

Disse flyttes ikke na:

- `page_a07.py`
- `page_saldobalanse.py`
- eksisterende testimporter
- eksisterende `a07_feature/__init__.py`
