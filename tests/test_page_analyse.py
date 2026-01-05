"""Tests for the minimal AnalysePage implementation.

These tests verify that the AnalysePage class is defined correctly,
exposes a ``refresh_from_session`` method with the expected signature, and
that the method can be called without errors. Additional tests cover the
callback mechanism used to communicate selected accounts to another
component.
"""

from __future__ import annotations

import inspect


def test_class_exists() -> None:
    """Ensure that the AnalysePage class exists in the page_analyse module."""
    import page_analyse

    assert hasattr(page_analyse, "AnalysePage"), "AnalysePage must be defined"
    AnalysePage = getattr(page_analyse, "AnalysePage")
    assert inspect.isclass(AnalysePage), "AnalysePage must be a class"


def test_refresh_from_session_signature() -> None:
    """Verify that refresh_from_session has the correct signature."""
    import page_analyse

    AnalysePage = page_analyse.AnalysePage
    assert hasattr(AnalysePage, "refresh_from_session"), "Missing refresh_from_session method"

    fn = getattr(AnalysePage, "refresh_from_session")
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    # The method should take at least self and session
    assert len(params) >= 2, "refresh_from_session should take self and session"
    # The name of the second parameter should be session or similar
    assert params[1].name in {"session", "sess"}, (
        "Second parameter of refresh_from_session should be named 'session' or 'sess'"
    )


def test_refresh_from_session_callable() -> None:
    """Check that refresh_from_session can be called with a dummy session."""
    import page_analyse

    class DummySession:
        def __init__(self) -> None:
            self.dataset = "dummy"

    AnalysePage = page_analyse.AnalysePage
    page = AnalysePage(None)
    session = DummySession()
    # Should not raise an exception
    page.refresh_from_session(session)
    # The dataset attribute should now be set to the dummy value
    assert page.dataset == "dummy"


def test_utvalg_callback() -> None:
    """Ensure that set_utvalg_callback registers a callback and is invoked correctly."""
    import page_analyse

    AnalysePage = page_analyse.AnalysePage

    called_with = {}

    def callback(accounts) -> None:
        called_with["accounts"] = accounts

    page = AnalysePage(None)
    page.set_utvalg_callback(callback)
    # Trigger the callback via the protected method
    page._send_to_selection([1, 2, 3])
    assert called_with.get("accounts") == [1, 2, 3], (
        "Callback did not receive the expected accounts"
    )
