# A07 Lonn Module Map

Denne filen beskriver dagens faktiske modulgrenser etter refaktorrundene. Den
er ikke lenger et rent fase-1-notat; den skal brukes som oppslagsverk for hvor
kanonisk logikk bor, og hvilke wrappers som kun er compat.

## Regler

- `src/pages/a07/page_a07.py` er kanonisk page shell.
- `page_a07.py` i repo-roten er kun offentlig compat-shim.
- `a07_feature/` er fortsatt intern A07-motor/runtime.
- Flere gamle `page_a07_*`- og `control_*`-moduler lever videre som tynne
  compat-fasader.

## Offentlig Shell Og Compat

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `src/pages/a07/page_a07.py` | Kanonisk A07-shell og shared-ref-sync | Offentlig runtime-entrypoint i appen |
| `page_a07.py` | Root compat-shim | Re-eksporterer `A07Page` og helperflate |
| `a07_feature/page_a07_shared.py` | Compat/re-export-lag | Skal ikke brukes av aktive A07-moduler |

## Payroll / RF-1022

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `a07_feature/payroll/classification.py` | Kanonisk payroll-fasade | Wrapper over `classification_shared`, `classification_guardrails`, `classification_catalog`, `classification_a07_engine`, `classification_engine`, `classification_audit` |
| `payroll_classification.py` | Root compat-shim | Peker til payroll-pakken |
| `a07_feature/payroll/feedback.py` | Payroll feedback-hjelpere | Gammel rotsti beholdt som compat |
| `a07_feature/payroll/saldobalanse_bridge.py` | Handoff mellom A07 og saldobalanse | `saldobalanse_payroll_mode.py` beholdes som compat |
| `a07_feature/payroll/rf1022.py` | RF-1022-runtime | `a07_feature/page_a07_rf1022.py` beholdes som compat |
| `a07_feature/payroll/profile_state.py` | Payroll profilstate | Hentet ut av runtime-hjelpere |

## Suggest / Solver

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `a07_feature/suggest/__init__.py` | Kanonisk suggest-fasade | Re-eksporterer forslag, rulebook og residual-solver-symboler |
| `a07_feature/suggest/engine.py` | Kandidatbygging og scoremotor | Brukes for vanlige A07-forslag |
| `a07_feature/suggest/solver.py`, `solver_prepare.py`, `solver_code.py` | Eksisterende kode-/gruppe-solvere | Brukes for smarte A07-grupper og belopskandidater |
| `a07_feature/suggest/residual_solver.py` | Residual-solver v1 for `Tryllestav: finn 0-diff` | Ren motorlogikk uten GUI; jobber deterministisk i oere/int |
| `a07_feature/suggest/residual_models.py` | Datamodeller og belopshjelpere for residual-solver | Inneholder statuskonstanter, dataclasses og cents/display-konvertering |
| `a07_feature/suggest/residual_display.py` | Adapter fra residual-analyse til kompakte forslag-/review-rader | Holder GUI-tekst kort og lar eksisterende forslagstabell brukes |
| `a07_feature/suggest/explain.py`, `rule_lookup.py`, `special_add.py` | Forklaring, regeloppslag og spesialtillegg | Brukes av forslag/control-flyter |

## Kontrollmotor

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `a07_feature/control/data.py` | Kanonisk kontrollfasade | Re-eksporterer kontrollmotoren utad |
| `a07_feature/control/overview_data.py`, `history_data.py`, `control_queue_data.py`, `control_gl_data.py`, `control_filters.py`, `queue_shared.py`, `control_suggestion_selection.py` | Kontrollko, oversikt, historikk og GL-grunnlag | Tidligere `queue_data`-monolitt |
| `a07_feature/control/matching.py` | Compat-fasade for matching | Split i `matching_shared`, `matching_guardrails`, `matching_history`, `matching_display` |
| `a07_feature/control/mapping_audit.py` | Compat-fasade for mapping-audit | Split i `mapping_audit_rules`, `mapping_audit_status`, `mapping_review`, `mapping_audit_projection` |
| `a07_feature/control/statement_data.py` | Kontrolloppstilling-data | Kanonisk dataflate for statement/RF-1022 |
| `a07_feature/control/statement_ui.py` | Compat-fasade for statement-UI | Split i `statement_view_state`, `statement_window_ui`, `statement_panel_ui` |
| `a07_feature/page_control_data.py`, `a07_feature/control_matching.py`, `a07_feature/control_presenter.py`, `a07_feature/control_status.py`, `a07_feature/page_a07_control_statement.py` | Compat-stier | Beholdt for eldre importer |

## Page-Runtime Og Actions

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `a07_feature/page_a07_mapping_actions.py` | Compat-fasade for mappinghandlinger | Split i `page_a07_mapping_assign`, `page_a07_mapping_batch`, `page_a07_mapping_candidates`, `page_a07_mapping_control_actions`, `page_a07_mapping_learning_*`, `page_a07_mapping_candidate_apply`, `page_a07_mapping_shared` |
| `a07_feature/page_a07_mapping_residual.py` | Page-flyt for residual-tryllestav | Kaller ren solver, viser kort review-feedback og auto-appliserer bare `safe_exact` |
| `a07_feature/page_a07_context.py` | Tynn kontekstfasade | Context-/navigasjonsansvar er trukket ut til egne moduler |
| `a07_feature/page_a07_context_menu.py` | Compat-fasade for hoyreklikk | Split i `page_a07_context_menu_base`, `page_a07_context_menu_control`, `page_a07_context_menu_codes` |
| `a07_feature/page_a07_dialogs.py` | Compat-fasade for picker/dialog-hjelpere | Split i `page_a07_dialogs_shared`, `page_a07_dialogs_editors`, `page_a07_manual_mapping_dialog` |
| `a07_feature/page_a07_project_actions.py` | Compat-fasade for prosjekt-/verktoyhandlinger | Split i `page_a07_project_io`, `page_a07_group_actions`, `page_a07_project_tools` |
| `a07_feature/page_windows.py` | Compat-fasade for hjelpevinduer | Split i `page_windows_source`, `page_windows_mapping`, `page_windows_matcher_admin` |
| `a07_feature/page_paths.py` | Compat-fasade for path/runtime-context | Split i `path_context`, `path_rulebook`, `path_snapshots`, `path_trial_balance`, `path_history`, `path_shared` |
| `a07_feature/page_a07_refresh*.py` | Refresh-klynge | Fortsatt et av de tydeligste gjenvaarende hotspot-omraadene |

## UI-Lag

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `a07_feature/ui/page.py` | Kanonisk UI-entry | `a07_feature/page_a07_ui.py` beholdes som compat |
| `a07_feature/ui/canonical_layout.py` | Tynn layout-shell | Split i `control_layout`, `support_layout`, `groups_popup` |
| `a07_feature/ui/helpers.py` | Compat-fasade for UI-hjelpere | Split i `tree_builders`, `tree_sorting`, `tree_selection_helpers`, `manual_mapping_defaults`, `focus_helpers`, `drag_drop_helpers` |
| `a07_feature/ui/support_render.py` | Compat-fasade for support-render | Split i `support_filters`, `support_guidance`, `support_panel`, `support_suggestions`, `support_trees`, `support_render_shared` |
| `a07_feature/ui/selection.py` | Compat-fasade for selection | Split i `selection_context`, `selection_controls`, `selection_details`, `selection_events`, `selection_scope`, `selection_tree`, `selection_shared` |
| `a07_feature/ui/render.py`, `a07_feature/ui/tree_render.py` | Kanonisk rendering | Fortsatt aktive hovedmoduler i UI-laget |
| `a07_feature/page_a07_ui_canonical.py`, `page_a07_support_render.py`, `page_a07_selection.py`, `page_a07_render.py`, `page_a07_ui_helpers.py`, `page_a07_tree_render.py`, `page_a07_tree_ui.py` | Compat-stier | Beholdt for eldre importer og tester |

## Saldobalanse-Bridge

| Naa | Ansvar | Kommentar |
| --- | --- | --- |
| `page_saldobalanse.py` | Forbruker av payroll bridge | Flyttes ikke i denne runden |
| `saldobalanse_payroll_mode.py` | Compat for payroll bridge | Peker til `a07_feature/payroll/saldobalanse_bridge.py` |
| `a07_feature/page_a07_runtime_helpers.py` | Felles runtime-hjelpere | Noe profilstate er flyttet ut, men modulen lever videre |
