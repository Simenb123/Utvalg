# A07 Target Architecture In Utvalg

## Decision

Use Utvalg as the host application and move A07 in as a feature package.

Do not continue long-term with two parallel desktop apps.
Do not copy the current A07 GUI wholesale into Utvalg.
Do move the reusable A07 core logic into Utvalg behind a small, explicit feature boundary.

Recommended package name in Utvalg for the first migration:

- `a07_feature/`

This fits the current repo style better than a full `features/` namespace and avoids name clashes with the standalone `a07` package during migration.

## Why This Direction

- Utvalg already acts as the anchor app for audit workflows, client context, dataset handling, exports, settings, and future feature growth.
- A07 already has useful pure logic for parsing, reconciliation, grouping, suggestion generation, and mapping application.
- The current A07 GUI carries too much app-specific state, compatibility glue, and duplicated workflow logic to be a good transplant target.
- Utvalg already has a trial balance path, but A07 contains stronger heuristics for a few edge cases. We should borrow those heuristics where they help, not fork the entire file-loading story.

## Main Principles

- Keep A07 business logic pure and testable.
- Keep A07 UI thin and Utvalg-native.
- Reuse Utvalg app shell, theme, logging, data-dir patterns, and client/year context.
- Do not bind A07 directly to the general Dataset page in phase 1.
- Use adapters between Utvalg data structures and A07 data structures.
- Keep numeric behavior stable during migration. Do not rewrite all A07 money logic at the same time.

## A07 Lonn Phase 1 Direction

For A07-lonn follow-up work, phase 1 establishes a dedicated documentation set and
target namespace structure without moving runtime files yet.

Phase 1 references:

- `doc/a07_payroll/README.md`
- `doc/a07_payroll/WORKFLOW.md`
- `doc/a07_payroll/MODULE_MAP.md`
- `doc/a07_payroll/TESTING.md`

The approved migration direction for this track is:

- `a07_feature/payroll/`
- `a07_feature/control/`
- `a07_feature/ui/`

Important constraint:

- phase 1 is structure and documentation preparation only
- no existing A07 or saldobalanse runtime files are moved in this phase

## Recommended Package Layout

```text
a07_feature/
  __init__.py
  models.py
  parser.py
  monthly_summary.py
  reconcile.py
  groups.py
  storage.py
  export.py
  adapters.py
  workspace.py
  suggest/
    __init__.py
    api.py
    models.py
    helpers.py
    engine.py
    apply.py
    rulebook.py
  ui/
    __init__.py
    page_a07.py
    board.py
    mapping_panel.py
    suggest_panel.py
    controls.py
```

### Role Of Each File

- `parser.py`: parse A07 JSON into a normalized table.
- `monthly_summary.py`: optional AGA and withholding summaries from A07.
- `reconcile.py`: compare A07 totals and GL totals based on account mapping.
- `groups.py`: optional grouping of multiple A07 codes into one logical bucket.
- `storage.py`: save and load mapping, groups, locks, rulebook pointers, and simple feature state.
- `export.py`: A07-specific export for workbook/report output inside Utvalg conventions.
- `adapters.py`: translate Utvalg trial balance data into the A07-friendly shape.
- `workspace.py`: small dataclasses for in-memory A07 state in the page.
- `suggest/`: isolated suggestion engine and rulebook logic.
- `ui/page_a07.py`: the Utvalg tab/page entrypoint.
- `ui/board.py`: Utvalg-native interactive mapping board.

## Integration Points In Utvalg

### UI

Add a dedicated A07 tab to `ui_main.py`.

The A07 tab should be its own workflow:

- load A07 JSON
- select current trial balance source
- load or create account-to-code mapping
- view control picture
- accept suggestions
- export A07 workpaper

Do not force A07 through the general Dataset page first. A07 has a different input model and should keep that distinction.

### Storage

Follow the same pattern as `regnskap_config.py` and store feature files in Utvalg data paths instead of repo-root files.

Recommended storage shape:

```text
<data_dir>/config/a07/
  default_rulebook.json

<data_dir>/clients/<client>/<year>/a07/
  mapping.json
  groups.json
  locks.json
  a07_project.json
  exports/
```

If client/year context is not available, fall back to a generic feature folder under `config/a07/`.

### Trial Balance Reuse

Utvalg should remain the owner of generic trial balance import.

Use:

- `trial_balance_reader.py` as the canonical Utvalg reader
- `a07_feature.adapters.from_trial_balance(...)` to convert into A07-ready columns

Important nuance:

- Do not push all A07 sign conventions into `trial_balance_reader.py`
- Do port the generic robustness wins from A07 `core/gl_import.py` into `trial_balance_reader.py` where they are generally useful

Good examples of generic improvements worth borrowing:

- header-row detection based on row content
- best-sheet selection based on actual sheet content, not only sheet name
- robust handling of `AccountID` and `AccountDescription`
- robust fallback from `Debet` and `Kredit` to movement

Keep A07-specific sign normalization in the adapter layer.

## Module Triage From The A07 Repo

### Move Almost As-Is

These are the best migration candidates because they are mostly pure logic and already tested.

- `src/a07/a07_parser.py` -> `a07_feature/parser.py`
- `src/a07/core/reconcile.py` -> `a07_feature/reconcile.py`
- `src/a07/a07_grouping.py` -> `a07_feature/groups.py`
- `src/a07/core/suggest_models.py` -> `a07_feature/suggest/models.py`
- `src/a07/core/suggest_helpers.py` -> `a07_feature/suggest/helpers.py`
- `src/a07/core/suggest_engine.py` -> `a07_feature/suggest/engine.py`
- `src/a07/core/suggest_apply.py` -> `a07_feature/suggest/apply.py`
- `src/a07/core/suggest_rulebook.py` -> `a07_feature/suggest/rulebook.py`
- `src/a07/core/suggest.py` -> `a07_feature/suggest/api.py`

### Move, But Adapt To Utvalg

- `src/a07/core/api.py`
  - Split into smaller feature-facing functions.
  - Do not carry over the whole compatibility surface.

- `src/a07/core/gl_import.py`
  - Do not import this wholesale as the new source of truth.
  - Mine generic heuristics and fold them into Utvalg `trial_balance_reader.py`.
  - Keep any A07-only sign rules inside `a07_feature/adapters.py`.

- `src/a07/a07_export.py`
  - Rework into `a07_feature/export.py`.
  - Prefer Utvalg export conventions and existing workbook helpers where practical.

- `src/a07/services/mapping_store.py`
  - Useful as inspiration for persistent learning or mapping hints.
  - Rename and simplify before adoption, for example `a07_feature/storage.py` or `a07_feature/learning_store.py`.

### UI Inspiration Only

These contain useful ideas, but should not be transplanted directly.

- `src/a07/a07_board_dnd.py`
  - Good ideas:
    - diff-first ordering of code cards
    - status coloring
    - explicit unmap drop target
    - manual drag fallback without hard dependency on `tkinterdnd2`
  - Bad fit:
    - tightly coupled to old A07 models and app flow

- `src/a07/gui_v1_helpers.py`
  - Mine selected pure helpers only.
  - Example: best-suggestion selection logic may be worth lifting into a small pure helper.

- `src/a07/gui_v1_*`
  - Use for workflow inspiration only.
  - Rebuild the page in Utvalg terms instead of porting the current GUI modules.

### Legacy Inspiration, Not Phase-1 Code

- `src/a07/a07_matcher.py`
  - Interesting as an alternative object-based solver.
  - Useful later if we want bundle-aware or multi-target matching experiments.
  - Not the phase-1 solver to port.

- `src/a07/a07_rulebook_store.py`
  - Useful conceptually for editable rulebooks.
  - Current implementation has hardcoded paths and old model dependencies.
  - Rebuild, do not port.

- `src/a07/a07_app.py`
- `src/a07/a07_app_full.py`
- `src/a07/a07_dnd_board.py`
- `src/a07/a07_core.py`
- `src/a07/models.py`
  - Leave behind unless a very specific behavior is missing from the newer core.

## Recommended Utvalg-Native Data Flow

```text
A07 JSON
  -> a07_feature.parser.parse_a07_json()
  -> A07 codes DataFrame

Trial balance in Utvalg
  -> trial_balance_reader.read_trial_balance()
  -> a07_feature.adapters.from_trial_balance()
  -> A07 GL DataFrame

Mapping JSON
  -> a07_feature.storage.load_mapping()

A07 + GL + mapping
  -> a07_feature.reconcile.reconcile_a07_vs_gl()
  -> a07_feature.suggest.api.suggest_mapping_candidates()
  -> a07_feature.ui.page_a07
```

## Suggested First Milestone

Build a useful A07 tab without drag and drop first.

### Scope

- load A07 JSON
- use current Utvalg trial balance file or trial balance DataFrame
- compute A07 control table
- show unmapped accounts
- generate suggestions
- accept selected suggestion into mapping
- save and load mapping

### Explicitly Out Of Scope For Milestone 1

- full drag and drop board
- editable rulebook UI
- groups editor UI
- advanced project-file workflow
- parity with the full standalone A07 GUI

## Suggested Migration Phases

### Phase 0: Stabilize Source Logic

- Freeze the standalone A07 GUI except bug fixes.
- Treat A07 repo as source reference during migration.
- Keep A07 tests as the behavioral baseline.

### Phase 1: Port Pure Core

- Create `a07_feature/`
- Port parser, reconcile, grouping, suggest package
- Port the matching tests that describe expected behavior

Minimum tests to port first:

- parser tests
- reconcile tests
- suggest tests
- select-best-suggestion helper tests if we keep that helper

### Phase 2: Build Utvalg Adapters

- Add `a07_feature/adapters.py`
- Implement:
  - `from_trial_balance(tb_df) -> a07_gl_df`
  - `normalize_mapping_keys(...)`
  - optional helpers for client/year specific paths

- Improve `trial_balance_reader.py` only where the heuristics are generic and broadly useful

### Phase 3: Read-Only A07 Page

- Add `A07Page` to `ui_main.py`
- Load A07 JSON and current trial balance
- Show:
  - A07 table
  - GL table
  - control table
  - unmapped accounts

This gives immediate value before interactive mapping is finished.

### Phase 4: Interactive Mapping

- add suggestion acceptance
- add mapping save and load
- add optional click-to-assign
- then add drag and drop if the page still needs it

Recommendation:

- Start with click-to-assign and explicit buttons.
- Use manual drag behavior inspired by `a07_board_dnd.py` if needed later.
- Avoid introducing `tkinterdnd2` as a hard dependency in the first slice.

### Phase 5: Export And Persistence

- add A07-specific workbook export
- add groups and locks persistence
- add feature-local project/workspace persistence only if the page truly needs it

### Phase 6: Advanced Features

- rulebook editor
- learning store
- auto-grouping UX
- AGA drill-downs
- richer client-specific heuristics

## Concrete File Mapping Proposal

```text
A07 repo source                                 -> Utvalg target
src/a07/a07_parser.py                          -> a07_feature/parser.py
src/a07/core/reconcile.py                      -> a07_feature/reconcile.py
src/a07/a07_grouping.py                        -> a07_feature/groups.py
src/a07/core/suggest.py                        -> a07_feature/suggest/api.py
src/a07/core/suggest_models.py                 -> a07_feature/suggest/models.py
src/a07/core/suggest_helpers.py                -> a07_feature/suggest/helpers.py
src/a07/core/suggest_engine.py                 -> a07_feature/suggest/engine.py
src/a07/core/suggest_apply.py                  -> a07_feature/suggest/apply.py
src/a07/core/suggest_rulebook.py               -> a07_feature/suggest/rulebook.py
src/a07/services/mapping_store.py              -> a07_feature/storage.py (adapt)
src/a07/a07_export.py                          -> a07_feature/export.py (adapt)
src/a07/a07_board_dnd.py                       -> a07_feature/ui/board.py (rewrite from ideas)
src/a07/gui_v1_helpers.py select helper logic  -> a07_feature/ui/controls.py or suggest/select.py
```

## Legacy Evaluation Summary

### Worth Reusing Directly

- parser
- reconcile
- grouping
- suggest package

### Worth Mining For Ideas

- board DnD UI
- legacy matcher
- legacy rulebook store

### Not Worth Carrying Forward

- standalone A07 app shells
- old project-file workflow as currently implemented
- duplicate DnD widgets
- old object-model parser path

## Risks To Avoid

- Do not create two separate state models inside Utvalg for the same client/year.
- Do not let A07 become a second app hidden inside the first app.
- Do not rewrite parser, loader, suggestion engine, and UI in one step.
- Do not bake A07-specific sign conventions into Utvalg's generic trial balance semantics.
- Do not rely on root-level JSON files in the repo as long-term storage.

## First Implementation Slice I Would Actually Build

1. Create `a07_feature/` with parser, reconcile, suggest, adapters, storage, and workspace modules.
2. Port parser, reconcile, and suggest tests from the A07 repo.
3. Add a simple `A07Page` tab in Utvalg with:
   - A07 JSON path
   - "Use current trial balance" action
   - mapping path
   - refresh button
   - control table
   - suggestions table
   - apply selected suggestion
4. Save mapping under Utvalg data-dir conventions.
5. Add export only after the page is stable.

## Source Of Truth During Migration

Until feature parity is good enough:

- Utvalg becomes the new host UI
- standalone A07 repo remains the behavioral reference and migration sandbox

Once the Utvalg A07 tab is good enough for normal work:

- stop adding major GUI work in the standalone A07 repo
- keep it only for small fixes, experiments, or extraction work until retirement
