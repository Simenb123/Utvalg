from __future__ import annotations

import importlib


def test_dialog_helpers_and_compat_wrappers_point_to_split_modules() -> None:
    dialogs = importlib.import_module("a07_feature.page_a07_dialogs")
    dialogs_shared = importlib.import_module("a07_feature.page_a07_dialogs_shared")
    dialogs_editors = importlib.import_module("a07_feature.page_a07_dialogs_editors")
    manual_dialog = importlib.import_module("a07_feature.page_a07_manual_mapping_dialog")
    picker = importlib.import_module("a07_feature.page_a07_picker")

    assert dialogs._PickerOption is dialogs_shared._PickerOption
    assert dialogs.build_gl_picker_options is dialogs_shared.build_gl_picker_options
    assert dialogs._format_picker_amount is dialogs_shared._format_picker_amount
    assert dialogs._format_aliases_editor is dialogs_editors._format_aliases_editor
    assert dialogs.apply_manual_mapping_choices is dialogs_editors.apply_manual_mapping_choices
    assert dialogs.open_manual_mapping_dialog is manual_dialog.open_manual_mapping_dialog
    assert picker.open_manual_mapping_dialog is dialogs.open_manual_mapping_dialog
