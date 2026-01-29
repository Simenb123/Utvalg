from __future__ import annotations

import pandas as pd

import page_analyse
import views_override_checks
from overstyring.ui_entrypoint import open_override_checks_popup


def test_analyse_open_override_checks_calls_entrypoint(monkeypatch) -> None:
    """AnalysePage should delegate to views_override_checks entrypoint."""

    page = page_analyse.AnalysePage(None)

    df_all = pd.DataFrame(
        {
            "Bilag": [1, 2],
            "Beløp": [100.0, -100.0],
            "Konto": [3000, 3000],
        }
    )
    df_scope = df_all.iloc[:1].copy()

    # Simulate a loaded dataset + current filtered scope
    page.dataset = df_all
    page._df_filtered = df_scope

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(views_override_checks, "open_override_checks_popup", fake)

    page._open_override_checks()

    assert calls, "Expected open_override_checks_popup to be called"
    _, kwargs = calls[0]

    assert "df_all" in kwargs
    assert "df_scope" in kwargs
    assert isinstance(kwargs["df_all"], pd.DataFrame)
    assert isinstance(kwargs["df_scope"], pd.DataFrame)

    assert kwargs["df_all"].equals(df_all)
    assert kwargs["df_scope"].equals(df_scope)


def test_open_override_checks_popup_accepts_legacy_kwargs() -> None:
    """Ensure UI entrypoint stays compatible with older call-sites."""

    empty = pd.DataFrame()
    # Should not raise (returns None because dataset is empty)
    assert open_override_checks_popup(master=None, df_scope=empty) is None
