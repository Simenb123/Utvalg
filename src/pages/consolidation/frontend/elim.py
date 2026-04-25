"""page_consolidation_elim.py - Facade for elimination handlers."""

from __future__ import annotations

from .elim_draft import (
    _fmt_no,
    _parse_konto_from_combo,
    _parse_regnr_from_combo,
    begin_new_elim_draft,
    clear_preview,
    compute_preview,
    ensure_elim_draft_voucher_no,
    get_sum_foer_elim,
    load_journal_into_draft,
    on_create_simple_elim,
    on_delete_simple_elim,
    on_draft_add_line,
    on_draft_clear,
    on_draft_edit_line,
    on_draft_remove_line,
    on_elim_combo_filter,
    on_elim_level_changed,
    on_elim_line_selected,
    populate_elim_combos,
    refresh_draft_tree,
    update_elim_draft_header,
)
from .elim_journal import (
    on_add_elim_line,
    on_copy_journal_to_draft,
    on_delete_elim_line,
    on_delete_journal,
    on_journal_select,
    on_load_journal_to_draft,
    on_new_journal,
    on_use_result_rl,
    on_simple_elim_selected,
    refresh_elim_lines,
    refresh_journal_tree,
    refresh_simple_elim_tree,
    show_elim_detail,
)
from .elim_suggestions import (
    on_create_journal_from_suggestion,
    on_generate_suggestions,
    on_ignore_suggestion,
    on_suggestion_select,
    refresh_suggestion_tree,
    show_suggestion_detail,
)
