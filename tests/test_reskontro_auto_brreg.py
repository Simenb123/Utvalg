"""Tests for auto-BRREG logic in page_reskontro."""
from __future__ import annotations

import pandas as pd
import pytest


def test_auto_brreg_all_skips_already_fetched(monkeypatch) -> None:
    """_auto_brreg_all should not trigger fetch if all orgnr are already in cache."""
    import src.pages.reskontro.frontend.page as page_reskontro

    started = []

    class StubPage:
        _master_df = pd.DataFrame({"nr": ["1"]})
        _orgnr_map = {"1": "123456789"}
        _brreg_data = {"123456789": {"enhet": {}, "regnskap": {}}}

        def _start_brreg_sjekk(self):
            started.append(True)

    page = StubPage()
    page_reskontro.ReskontroPage._auto_brreg_all(page)
    assert len(started) == 0


def test_auto_brreg_all_triggers_for_missing(monkeypatch) -> None:
    """_auto_brreg_all should trigger fetch if orgnr not yet fetched."""
    import src.pages.reskontro.frontend.page as page_reskontro

    started = []

    class StubPage:
        _master_df = pd.DataFrame({"nr": ["1"]})
        _orgnr_map = {"1": "987654321"}
        _brreg_data = {}  # empty — not fetched yet

        def _start_brreg_sjekk(self):
            started.append(True)

    page = StubPage()
    page_reskontro.ReskontroPage._auto_brreg_all(page)
    assert len(started) == 1


def test_auto_brreg_all_skips_empty_data(monkeypatch) -> None:
    """_auto_brreg_all should not trigger fetch if no data loaded."""
    import src.pages.reskontro.frontend.page as page_reskontro

    started = []

    class StubPage:
        _master_df = None
        _orgnr_map = {}
        _brreg_data = {}

        def _start_brreg_sjekk(self):
            started.append(True)

    page = StubPage()
    page_reskontro.ReskontroPage._auto_brreg_all(page)
    assert len(started) == 0
