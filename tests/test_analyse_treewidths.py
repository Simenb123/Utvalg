from __future__ import annotations

import analyse_treewidths


def test_default_column_width_uses_domain_specific_defaults() -> None:
    assert analyse_treewidths.default_column_width("Tekst") == 320
    assert analyse_treewidths.default_column_width("Kontonavn") == 260
    assert analyse_treewidths.default_column_width("Beløp") == 105
    assert analyse_treewidths.default_column_width("Bilag") == 72
    # Smale kolonner skal være kompakte
    assert analyse_treewidths.default_column_width("Nr") == 42
    assert analyse_treewidths.default_column_width("Antall") == 58


def test_suggest_column_width_keeps_numeric_columns_compact() -> None:
    width = analyse_treewidths.suggest_column_width("Beløp", ["1 234,50", "-98 765,43"])
    assert 65 <= width <= 150


def test_suggest_column_width_caps_long_text_columns() -> None:
    width = analyse_treewidths.suggest_column_width("Tekst", ["x" * 300])
    assert width == 500


def test_column_anchor_uses_right_alignment_for_numeric_fields() -> None:
    assert analyse_treewidths.column_anchor("Beløp") == "e"
    assert analyse_treewidths.column_anchor("UB") == "e"
    assert analyse_treewidths.column_anchor("Tekst") == "w"
