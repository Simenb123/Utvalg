from __future__ import annotations

"""Compatibility re-export for legacy picker imports.

The canonical implementation lives in ``page_a07_dialogs``. Keep this thin
wrapper so older imports continue to work while we phase out the duplicate
module path.
"""

from .page_a07_dialogs import (  # noqa: F401
    _PickerOption,
    _count_nonempty_mapping,
    _editor_list_items,
    _filter_picker_options,
    _format_aliases_editor,
    _format_editor_list,
    _format_editor_ranges,
    _format_picker_amount,
    _format_special_add_editor,
    _numeric_decimals_for_column,
    _parse_aliases_editor,
    _parse_editor_ints,
    _parse_konto_tokens,
    _parse_special_add_editor,
    apply_manual_mapping_choice,
    apply_manual_mapping_choices,
    build_a07_picker_options,
    build_gl_picker_options,
    open_manual_mapping_dialog,
    remove_mapping_accounts,
)

__all__ = [
    "_PickerOption",
    "_count_nonempty_mapping",
    "_editor_list_items",
    "_filter_picker_options",
    "_format_aliases_editor",
    "_format_editor_list",
    "_format_editor_ranges",
    "_format_picker_amount",
    "_format_special_add_editor",
    "_numeric_decimals_for_column",
    "_parse_aliases_editor",
    "_parse_editor_ints",
    "_parse_konto_tokens",
    "_parse_special_add_editor",
    "apply_manual_mapping_choice",
    "apply_manual_mapping_choices",
    "build_a07_picker_options",
    "build_gl_picker_options",
    "open_manual_mapping_dialog",
    "remove_mapping_accounts",
]
