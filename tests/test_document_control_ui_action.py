from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import selection_studio.ui_widget_actions as actions


class _FakeTree:
    def selection(self):
        return ("item-1",)

    def item(self, _item_id, option):
        assert option == "values"
        return ("1001.0", "15.02.2025", "Eksempel", "1250,00")


def test_open_document_control_uses_selected_bilag_and_full_bilag_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeDialog:
        def __init__(self, _master, **kwargs):
            captured.update(kwargs)

        def wait_window(self):
            captured["waited"] = True

    monkeypatch.setattr(actions, "DocumentControlDialog", _FakeDialog)
    monkeypatch.setattr(actions.session, "client", "Demo AS", raising=False)
    monkeypatch.setattr(actions.session, "year", "2025", raising=False)

    studio = SimpleNamespace(
        tree=_FakeTree(),
        _df_all=pd.DataFrame(
            {
                "Bilag": [1001, 1001, 1002],
                "Tekst": ["linje 1", "linje 2", "annen"],
                "Beløp": [1000.0, 250.0, 99.0],
            }
        ),
    )

    actions.open_document_control(studio)

    assert captured["bilag"] == "1001"
    assert isinstance(captured["df_bilag"], pd.DataFrame)
    assert list(captured["df_bilag"]["Bilag"]) == [1001, 1001]
    assert captured["client"] == "Demo AS"
    assert captured["year"] == "2025"
    assert captured["waited"] is True
