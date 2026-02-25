# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime

from preview_format import format_preview_value, infer_column_kinds


def test_format_preview_value_date_ddmmyyyy():
    assert format_preview_value(datetime(2026, 1, 5), kind="date") == "05.01.2026"


def test_format_preview_value_date_with_time():
    assert format_preview_value(datetime(2026, 1, 5, 13, 45), kind="date") == "05.01.2026 13:45"


def test_format_preview_value_amount_norwegian_separators():
    assert format_preview_value(87869.21, kind="amount") == "87 869,21"
    assert format_preview_value(-289043.44, kind="amount") == "-289 043,44"
    assert format_preview_value(500000, kind="amount") == "500 000,00"


def test_infer_column_kinds_basic_ledger_shape():
    rows = [
        [3000, 1008577, datetime(2025, 12, 31), -20625.0, "Husleie"],
        [2710, 1008577, datetime(2025, 12, 31), 4125.0, "Inngående mva"],
        [6300, 1008582, datetime(2026, 1, 5), 87869.21, "Forretningsfør"],
    ]

    kinds = infer_column_kinds(rows)
    assert kinds[0] == "id"      # Konto
    assert kinds[1] == "id"      # Bilag
    assert kinds[2] == "date"    # Dato
    assert kinds[3] == "amount"  # Beløp
    # Tekst blir ofte generic i denne enkle heuristikken, og det er ok.