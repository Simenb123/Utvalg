from __future__ import annotations


def test_dataset_pane_exposes_main_filetypes() -> None:
    """MAIN_FILETYPES skal være tilgjengelig og inneholde relevante filtre."""

    from dataset_pane import MAIN_FILETYPES

    assert isinstance(MAIN_FILETYPES, list)
    assert len(MAIN_FILETYPES) >= 1

    # Første filter blir default i Windows-dialogen
    first_label, first_pattern = MAIN_FILETYPES[0]
    assert isinstance(first_label, str)
    assert isinstance(first_pattern, str)
    assert first_label.lower().startswith("alle")
    assert "*.*" in first_pattern

    joined = " ".join(pat for _lbl, pat in MAIN_FILETYPES)
    assert "*.xlsx" in joined
    assert "*.csv" in joined
    assert "*.zip" in joined or "*.xml" in joined
