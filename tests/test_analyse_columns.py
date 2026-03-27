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

    assert "Prosjekt" not in order_clean
    assert order_clean[:2] == ["Konto", "Kontonavn"]
    assert "Bilag" in visible_order
    assert visible_order[:2] == ["Konto", "Kontonavn"]
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

    assert order_clean[:2] == ["Konto", "Kontonavn"]
    assert "X" not in visible_order
    assert visible_order[:2] == ["Konto", "Kontonavn"]
    assert "Bilag" in visible_order


def test_unique_preserve_canonicalizes_alias_columns_and_keeps_custom_columns():
    cols = [
        "Konto",
        "konto",
        "Belop",
        "beløp",
        "CustomerName",
        "Kundenavn",
        "mva-kode",
        "MVA-kode",
        "Egendefinert",
    ]

    out = analyse_columns.unique_preserve(cols, canonicalize=True)

    assert out == ["Konto", "Beløp", "Kundenavn", "MVA-kode", "Egendefinert"]


def test_normalize_tx_column_config_canonicalizes_old_saved_aliases():
    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=["konto", "customername", "mva-kode"],
        visible=["customername", "mva-kode"],
        all_cols=["Konto", "Kundenavn", "MVA-kode"],
        pinned=("Konto", "Kontonavn"),
        required=("Konto", "Bilag"),
    )

    assert "konto" not in order_clean
    assert "customername" not in order_clean
    assert "mva-kode" not in order_clean
    assert "Kundenavn" in order_clean
    assert "MVA-kode" in visible_order


def test_reorder_tx_column_moves_column_but_keeps_pinned_first():
    order = ["Konto", "Kontonavn", "Dato", "Bilag", "Beløp", "Tekst"]

    out = analyse_columns.reorder_tx_column(
        order,
        source="Tekst",
        target="Beløp",
        all_cols=order,
        pinned=("Konto", "Kontonavn"),
        required=("Konto", "Kontonavn", "Bilag"),
    )

    assert out[:2] == ["Konto", "Kontonavn"]
    assert out.index("Tekst") < out.index("Beløp")


def test_reorder_tx_column_does_not_move_pinned_column_out_of_front():
    order = ["Konto", "Kontonavn", "Dato", "Bilag", "Beløp"]

    out = analyse_columns.reorder_tx_column(
        order,
        source="Konto",
        target="Beløp",
        all_cols=order,
        pinned=("Konto", "Kontonavn"),
        required=("Konto", "Kontonavn", "Bilag"),
    )

    assert out[:2] == ["Konto", "Kontonavn"]
