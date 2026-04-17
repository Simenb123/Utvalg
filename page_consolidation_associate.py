"""page_consolidation_associate.py — EK-metode / tilknyttede selskaper.

Fasade for tilknyttet-sak-flyt. Implementasjonen ligger i de mindre
`page_consolidation_associate_*`-modulene.
"""

from __future__ import annotations

from page_consolidation_associate_actions import (
    on_add_associate_adjustment,
    on_associate_case_selected,
    on_delete_associate_adjustment,
    on_delete_associate_case,
    on_edit_associate_adjustment,
    on_generate_associate_journal,
    on_new_associate_case,
    on_open_associate_journal,
    on_save_associate_case,
    open_associate_case_by_id,
)
from page_consolidation_associate_ar import (
    _apply_field_suggestions,
    create_or_update_associate_case_from_ar_relation,
    on_import_associate_line_support,
    on_import_associate_pdf_support,
    on_open_selected_associate_from_journal,
)
from page_consolidation_associate_state import (
    _associate_case_status_label,
    _build_case_from_form,
    _build_next_step_text,
    _find_duplicate_company,
    _fmt_no,
    _normalize_entity_name,
    _on_apply_goodwill_amortization,
    _on_compute_goodwill,
    _on_save_default_line_mapping,
    _parse_float,
    _parse_int,
    _regnr_display,
    _refresh_mapping_summary,
    _set_mapping_visibility,
    _update_goodwill_display,
    clear_associate_case_form,
    current_associate_case,
    load_default_line_mapping_into_ui,
    on_reset_associate_mapping,
    on_toggle_associate_mapping,
    populate_associate_case_form,
    refresh_associate_adjustment_tree,
    refresh_associate_case_actions,
    refresh_associate_case_tree,
    refresh_associate_case_views,
    refresh_investor_choices,
)
from page_consolidation_associate_ui import (
    _build_calc_tab,
    _build_journal_tab,
    _build_workpaper_tab,
    build_associate_cases_tab,
)
