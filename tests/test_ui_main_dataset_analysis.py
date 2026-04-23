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


def test_restore_last_tab_starts_on_oversikt() -> None:
    class _Notebook:
        def __init__(self) -> None:
            self.selected = None

        def select(self, tab=None):
            if tab is None:
                return self.selected
            self.selected = tab
            return tab

        def tabs(self):
            return ["dataset", "analyse"]

    app = ui_main.App.__new__(ui_main.App)
    app.nb = _Notebook()
    app.page_oversikt = "oversikt"

    app._restore_last_tab()

    assert app.nb.selected == "oversikt"


def test_restore_last_tab_falls_back_to_first_tab_without_oversikt() -> None:
    class _Notebook:
        def __init__(self) -> None:
            self.selected = None

        def select(self, tab=None):
            if tab is None:
                return self.selected
            self.selected = tab
            return tab

        def tabs(self):
            return ["dataset", "analyse"]

    app = ui_main.App.__new__(ui_main.App)
    app.nb = _Notebook()
    app.page_oversikt = None

    app._restore_last_tab()

    assert app.nb.selected == "dataset"


def test_dataset_ready_continues_when_analyse_refresh_fails() -> None:
    """Regression: feil i Analyse-refresh må ikke stoppe lazy-mappingen for andre sider.

    Etter overgang til lazy refresh (Quick win 1): kun Analyse refreshes
    eager. Andre sider havner i _post_load_dirty_refreshers og refreshes
    først ved tab-aktivering. Denne testen verifiserer at dirty-mappingen
    settes opp selv om Analyse-refresh kaster.
    """
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
        setattr(app.page_saldobalanse, "refresh_from_session", lambda _session: called.append("saldobalanse"))
        setattr(app.page_materiality, "refresh_from_session", lambda _session: called.append("materiality"))
        setattr(app.page_a07, "refresh_from_session", lambda _session: called.append("a07"))

        df = pd.DataFrame({
            "Konto": [1000],
            "Kontonavn": ["Testkonto"],
            "Beløp": [123.45],
            "Bilag": ["1"],
        })

        app._on_data_ready(df)

        assert app.page_analyse.dataset is df
        # Analyse refreshes (og kastet) — andre sider skal ennå ikke være
        # refreshet eager, men ligge i dirty-mappingen.
        assert called == [("analyse", True)]
        for page in (app.page_resultat, app.page_saldobalanse, app.page_materiality):
            assert page in app._post_load_dirty_refreshers
        # A07 var aldri eager og skal heller ikke være i mappingen
        # (den har egen lazy-refresh via _on_notebook_tab_changed)
        assert app.page_a07 not in app._post_load_dirty_refreshers
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass


def test_dataset_ready_only_eager_refreshes_analyse_others_marked_dirty() -> None:
    """Etter Quick win 1: kun Analyse refreshes umiddelbart. Andre sider
    havner i _post_load_dirty_refreshers og refreshes først når brukeren
    aktiverer dem. AR og Konsolidering har egne tab-handlers og er ikke
    i mappingen i det hele tatt."""
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
        setattr(app.page_analyse, "refresh_from_session", lambda _session, *, defer_heavy=False: called.append(("analyse", defer_heavy)))
        setattr(app.page_resultat, "on_dataset_loaded", lambda _df: called.append("resultat"))
        setattr(app.page_saldobalanse, "refresh_from_session", lambda _session: called.append("saldobalanse"))
        setattr(app.page_regnskap, "refresh_from_session", lambda _session: called.append("regnskap"))
        setattr(app.page_materiality, "refresh_from_session", lambda _session: called.append("materiality"))
        setattr(app.page_ar, "refresh_from_session", lambda _session: called.append("ar"))
        setattr(app.page_consolidation, "refresh_from_session", lambda _session: called.append("consolidation"))

        df = pd.DataFrame({
            "Konto": [1000],
            "Kontonavn": ["Testkonto"],
            "BelÃ¸p": [123.45],
            "Bilag": ["1"],
        })

        app._on_data_ready(df)

        # Kun Analyse skal være kalt eager — andre sider er lazy
        assert ("analyse", True) in called
        assert "resultat" not in called
        assert "saldobalanse" not in called
        assert "regnskap" not in called
        assert "materiality" not in called
        assert "ar" not in called
        assert "consolidation" not in called

        # Lazy mapping skal være satt for sider som tidligere ble eager-
        # refreshet. AR og Consolidation har egne tab-handlers og skal
        # ikke være i mappingen.
        dirty = app._post_load_dirty_refreshers
        assert app.page_resultat in dirty
        assert app.page_saldobalanse in dirty
        assert app.page_regnskap in dirty
        assert app.page_materiality in dirty
        assert app.page_ar not in dirty
        assert app.page_consolidation not in dirty
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass


def test_tab_change_triggers_lazy_refresh_for_dirty_page_only_once() -> None:
    """Når brukeren aktiverer en fane som er markert dirty etter dataset-
    last, skal lazy-refresh kjøres én gang og deretter fjernes fra
    mappingen (ingen dobbel refresh ved senere tab-byttes)."""
    session.client = None
    session.year = None
    app = ui_main.create_app()
    try:
        try:
            app.withdraw()  # type: ignore[attr-defined]
        except Exception:
            pass

        called: list[str] = []

        # Sett opp en dirty-mapping manuelt (simulerer post-dataset-load state)
        target = app.page_regnskap
        app._post_load_dirty_refreshers = {target: lambda: called.append("regnskap_dirty")}
        setattr(app, "after_idle", lambda fn: fn())
        app.nb.select(target)
        app._on_notebook_tab_changed()

        assert called == ["regnskap_dirty"]
        assert target not in app._post_load_dirty_refreshers

        # Andre tab-bytte til samme fane skal ikke kalle dirty-funksjonen igjen
        app._on_notebook_tab_changed()
        assert called == ["regnskap_dirty"]
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass


def test_tab_change_to_a07_syncs_dataset_context_and_refreshes_page() -> None:
    original_client = getattr(session, "client", None)
    original_year = getattr(session, "year", None)
    try:
        session.client = None
        session.year = None

        app = ui_main.App.__new__(ui_main.App)
        refresh_calls: list[object] = []
        store_section = type(
            "StoreSection",
            (),
            {
                "client_var": type("Var", (), {"get": lambda self: "Air Management AS"})(),
                "year_var": type("Var", (), {"get": lambda self: "2025"})(),
            },
        )()
        app.page_dataset = ui_main.SimpleNamespace(dp=ui_main.SimpleNamespace(_store_section=store_section))
        app.page_a07 = ui_main.SimpleNamespace(refresh_from_session=lambda sess: refresh_calls.append(sess))
        app.page_consolidation = object()
        app.page_saldobalanse = object()
        app.page_ar = object()
        app.page_revisjonshandlinger = object()
        app.page_scoping = object()
        app.nb = ui_main.SimpleNamespace(
            select=lambda *_args, **_kwargs: "a07",
            tab=lambda *_args, **_kwargs: "A07",
        )
        app.nametowidget = lambda _widget_id: app.page_a07
        app.after_idle = lambda fn: fn()

        app._on_notebook_tab_changed()

        assert session.client == "Air Management AS"
        assert session.year == "2025"
        assert refresh_calls == [session]
    finally:
        session.client = original_client
        session.year = original_year
