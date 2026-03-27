"""Tests for ui_main dataset-to-analysis integration.

This test verifies that when a dataset is built via the DatasetPane,
the registered callback in ``ui_main.App`` updates the AnalysePage
and switches to the Analyse tab.  The test constructs an ``App``
instance, invokes the private ``_on_ready`` callback on the dataset
pane with a dummy DataFrame, and checks that the AnalysePage's
``dataset`` attribute has been updated.  The Tk root is destroyed at
the end of the test to avoid lingering GUI windows.
"""

from __future__ import annotations

import pandas as pd

import session
import ui_main


def test_dataset_ready_updates_analysis() -> None:
    """Dataset build should refresh AnalysePage and set its dataset."""
    # Construct the application without starting the main event loop.
    app = ui_main.create_app()
    # Hide the main window to avoid it popping up during tests (if Tk is available).
    try:
        app.withdraw()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        # Access the dataset pane and its callback
        dp = getattr(app.page_dataset, "dp", None)
        assert dp is not None, "DatasetPage should expose a dp attribute"
        callback = getattr(dp, "_on_ready", None)
        assert callable(callback), "DatasetPane._on_ready should be callable"
        # Create a simple dummy dataset
        df = pd.DataFrame({
            "Konto": [1000],
            "Kontonavn": ["Testkonto"],
            "Beløp": [123.45],
            "Bilag": ["1"],
        })
        # Invoke the callback as DatasetPane would after building the dataset
        callback(df)  # type: ignore[misc]
        # Verify that AnalysePage.dataset now references the DataFrame
        assert app.page_analyse.dataset is df
    finally:
        # Ensure the application is destroyed to clean up any Tk resources
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass


def test_dataset_ready_continues_when_analyse_refresh_fails() -> None:
    """Regression: feil i Analyse-refresh må ikke stoppe Resultat, og A07 skal ikke eager-refreshes."""
    session.client = None
    session.year = None
    app = ui_main.create_app()
    try:
        try:
            app.withdraw()  # type: ignore[attr-defined]
        except Exception:
            pass

        called: list[object] = []

        setattr(app, "after_idle", lambda fn: fn())
        setattr(app, "after", lambda _ms, fn: fn())
        setattr(
            app.page_analyse,
            "refresh_from_session",
            lambda _session, *, defer_heavy=False: (
                called.append(("analyse", defer_heavy)),
                (_ for _ in ()).throw(RuntimeError("boom")),
            )[-1],
        )
        setattr(app.page_resultat, "on_dataset_loaded", lambda _df: called.append("resultat"))
        setattr(app.page_a07, "refresh_from_session", lambda _session: called.append("a07"))

        df = pd.DataFrame({
            "Konto": [1000],
            "Kontonavn": ["Testkonto"],
            "Beløp": [123.45],
            "Bilag": ["1"],
        })

        app._on_data_ready(df)

        assert app.page_analyse.dataset is df
        assert called == [("analyse", True), "resultat"]
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass
