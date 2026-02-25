import analyse_columns


def test_normalize_tx_column_config_pins_and_requires_and_filters_unknowns():
    all_cols = ["Konto", "Kontonavn", "Dato", "Bilag", "Beløp", "MVA-kode"]

    order = ["Dato", "Beløp", "Konto", "Prosjekt", "Bilag"]
    visible = ["Dato", "Beløp"]

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=all_cols,
        pinned=("Konto", "Kontonavn"),
        required=("Konto", "Kontonavn", "Bilag"),
    )

    # Unknown column 'Prosjekt' should be filtered out
    assert "Prosjekt" not in order_clean

    # Pinned columns should be forced to the front
    assert order_clean[:2] == ["Konto", "Kontonavn"]

    # Required columns should be visible even if user didn't pick them
    assert "Bilag" in visible_order
    assert visible_order[:2] == ["Konto", "Kontonavn"]

    # Dato/Beløp chosen by user should remain visible
    assert "Dato" in visible_order
    assert "Beløp" in visible_order


def test_normalize_tx_column_config_handles_empty_order_and_de_dupes_visible():
    all_cols = ["Konto", "Kontonavn", "Bilag", "Beløp", "Dato"]

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=[],
        visible=["X", "Bilag", "Bilag"],
        all_cols=all_cols,
        pinned=("Konto", "Kontonavn"),
        required=("Konto", "Kontonavn", "Bilag"),
    )

    # Falls back to all_cols (with pinned forced first)
    assert order_clean[:2] == ["Konto", "Kontonavn"]

    # Unknown visible col removed, duplicates removed
    assert "X" not in visible_order

    # Required/pinned are always visible
    assert visible_order[:2] == ["Konto", "Kontonavn"]
    assert "Bilag" in visible_order
