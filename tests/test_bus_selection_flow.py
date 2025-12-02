"""Tests for the bus → selection/utvalg flow.

These tests are deliberately simple and ASCII-only to avoid encoding issues.
If something fails, we can adapt the expectations to the actual bus/session
implementation in your project.
"""

import sys
import types
import importlib


def make_fake_session():
    """Create a minimal fake `session` module for testing bus.emit."""
    fake_session = types.ModuleType("session")

    class DummyUtvalgStrataPage:
        def __init__(self):
            self.loaded_accounts = None

        def load_population(self, accounts):
            # called by bus when new accounts are selected
            self.loaded_accounts = list(accounts)

    class DummyNotebook:
        def __init__(self):
            self.selected = None

        def select(self, page):
            # in the real app this would switch tab; here we just remember
            self.selected = page

    fake_session.UTVALG_STRATA_PAGE = DummyUtvalgStrataPage()
    fake_session.NOTEBOOK = DummyNotebook()
    fake_session.SELECTION = {}
    # If your real code uses a specific tab id constant, we can add it later.
    fake_session.UTVALG_TAB_ID = "utvalg-tab"

    return fake_session


def reload_bus_with_fake_session():
    """Helper: install fake session module and reload bus."""
    fake_session = make_fake_session()
    sys.modules["session"] = fake_session

    # Import or reload bus so it picks up our fake session module
    import bus  # noqa: F401
    importlib.reload(bus)

    return fake_session, bus


def test_emit_selection_set_accounts_updates_session_and_page():
    """bus.emit should update session.SELECTION and call load_population()."""
    fake_session, bus = reload_bus_with_fake_session()

    accounts = ["1000", "2000"]

    bus.emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})

    # 1) session.SELECTION should be updated
    sel = fake_session.SELECTION
    assert sel.get("accounts") == accounts

    # 2) UTVALG_STRATA_PAGE.load_population should have been called
    page = fake_session.UTVALG_STRATA_PAGE
    assert page.loaded_accounts == accounts


def test_emit_selection_set_accounts_ignores_empty_list():
    """Empty accounts list should not break anything."""
    fake_session, bus = reload_bus_with_fake_session()

    bus.emit("SELECTION_SET_ACCOUNTS", {"accounts": []})

    page = fake_session.UTVALG_STRATA_PAGE
    # best-effort expectation: no population loaded for empty selection
    assert page.loaded_accounts is None
