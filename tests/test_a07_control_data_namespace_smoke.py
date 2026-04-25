from __future__ import annotations

import importlib


def test_control_data_rf1022_support_split_modules_and_facades_are_importable() -> None:
    data = importlib.import_module("a07_feature.control.data")
    support = importlib.import_module("a07_feature.control.rf1022_support")
    compat = importlib.import_module("a07_feature.page_control_data")

    assert compat is data
    assert data.Rf1022TreatmentDetails is support.Rf1022TreatmentDetails
    assert data._safe_float is support._safe_float
    assert data.a07_code_rf1022_group is support.a07_code_rf1022_group
    assert data.rf1022_group_label is support.rf1022_group_label
    assert data.rf1022_post_for_group is support.rf1022_post_for_group
    assert data.rf1022_treatment_details is support.rf1022_treatment_details
    assert data.format_rf1022_treatment_text is support.format_rf1022_treatment_text
