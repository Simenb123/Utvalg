# -*- coding: utf-8 -*-

from __future__ import annotations

from dataset_pane import MAIN_FILETYPES


def test_dataset_file_dialog_default_filter_is_all_files_first():
    """Første filter i Windows-dialogen blir default.

    Vi ønsker at brukeren alltid starter på "Alle filer", ikke bare Excel.
    """

    assert MAIN_FILETYPES, "MAIN_FILETYPES skal ikke være tom"
    label, pattern = MAIN_FILETYPES[0]
    assert label.lower().startswith("alle")
    assert "*.*" in pattern


def test_dataset_file_dialog_contains_excel_and_csv_and_saft():
    """Vi skal fortsatt tilby praktiske filtre for Excel/CSV/SAF-T."""

    joined = " ".join(pat for _lbl, pat in MAIN_FILETYPES)
    assert "*.xlsx" in joined
    assert "*.csv" in joined
    assert "*.zip" in joined or "*.xml" in joined
