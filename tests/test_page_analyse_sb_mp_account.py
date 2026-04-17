"""Tests for motpost account-level view in page_analyse_sb."""
from __future__ import annotations

import pandas as pd
import pytest


def test_refresh_mp_account_view_aggregates_correctly(monkeypatch) -> None:
    """Motposter (kontonivå) should aggregate counter-postings per account."""
    import page_analyse_sb

    # Build a dataset: konto 4000 has 2 bilag, each with motpost on 1920 and 2400
    df = pd.DataFrame({
        "Konto": ["4000", "1920", "2400", "4000", "1920"],
        "Kontonavn": ["Varekostnad", "Bank", "Leverandørgjeld", "Varekostnad", "Bank"],
        "Bilag": ["B1", "B1", "B1", "B2", "B2"],
        "Beløp": [100.0, -60.0, -40.0, 200.0, -200.0],
    })

    # Minimal page stub
    class StubPage:
        _df_filtered = df
        dataset = df
        _var_decimals = None
        _lbl_tx_summary = None

        def _get_selected_accounts(self):
            return ["4000"]

    monkeypatch.setattr("page_analyse_sb.pd", pd)

    page = StubPage()

    # Create frame stub
    class FakeFrame:
        pass

    frame = FakeFrame()

    class FakeTree:
        def __init__(self):
            self.rows = []
            self.tags_config = {}

        def delete(self, *a):
            self.rows.clear()

        def get_children(self):
            return [f"I{i}" for i in range(len(self.rows))]

        def insert(self, parent, pos, **kw):
            self.rows.append(kw)

        def tag_configure(self, *a, **k):
            pass

    tree = FakeTree()
    frame._mp_acct_tree = tree
    page._mp_acct_frame = frame

    page_analyse_sb.refresh_mp_account_view(page=page)

    # Should have: 1 selected account (4000) + 2 motkontoer (1920, 2400)
    assert len(tree.rows) == 3

    # First row is the selected account (4000)
    first = tree.rows[0]
    assert first["values"][0] == "4000"
    assert "selected_account" in first["tags"]

    # Find 1920 row — should have 2 bilag, sum = -260
    row_1920 = [r for r in tree.rows if r["values"][0] == "1920"]
    assert len(row_1920) == 1
    assert row_1920[0]["values"][2] == 2  # Antall bilag


def test_refresh_mp_account_view_empty_selection() -> None:
    """Should handle empty selection gracefully."""
    import page_analyse_sb

    class StubPage:
        _df_filtered = pd.DataFrame()
        dataset = pd.DataFrame()
        _var_decimals = None
        _lbl_tx_summary = None

        def _get_selected_accounts(self):
            return []

    class FakeFrame:
        pass

    class FakeTree:
        def __init__(self):
            self.rows = []

        def delete(self, *a):
            self.rows.clear()

        def get_children(self):
            return []

        def insert(self, parent, pos, **kw):
            self.rows.append(kw)

        def tag_configure(self, *a, **k):
            pass

    tree = FakeTree()
    frame = FakeFrame()
    frame._mp_acct_tree = tree

    page = StubPage()
    page._mp_acct_frame = frame

    # Should not raise
    page_analyse_sb.refresh_mp_account_view(page=page)
    assert len(tree.rows) == 0
