"""Tester for Utvalg-fanens materialitets-wiring mot SelectionStudio.

Speiler tests/test_page_utvalg_strata_materiality.py: verifiserer at
Utvalg-fanen (legacy-fanen uten embedded studio) nå sender aktiv
materialitet + valgt terskel til SelectionStudio når dialogen åpnes,
nøyaktig slik Strata-fanen allerede gjør.

Brukerens lokale toleranse-override i studioens entry-felt berøres ikke
av materialitets-konteksten — studioet velger default basert på
materialiteten, men feltet kan fortsatt endres manuelt.
"""

from __future__ import annotations

from types import SimpleNamespace

import page_utvalg as mod


def test_apply_materiality_to_studio_reads_active_state(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []

    studio = SimpleNamespace(set_materiality_context=lambda payload, key: calls.append((payload, key)))

    monkeypatch.setattr(mod.session, "client", "Demo AS", raising=False)
    monkeypatch.setattr(mod.session, "year", "2025", raising=False)

    payload = {
        "source": "crmsystem",
        "performance_materiality": 175000,
    }
    monkeypatch.setattr(
        mod,
        "_load_materiality_state",
        lambda client, year: {
            "active_materiality": payload,
            "selection_threshold_key": "performance_materiality",
        },
    )

    mod._apply_materiality_to_studio(studio)

    assert calls == [(payload, "performance_materiality")]


def test_apply_materiality_to_studio_tolerates_load_errors(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []
    studio = SimpleNamespace(set_materiality_context=lambda payload, key: calls.append((payload, key)))

    monkeypatch.setattr(mod.session, "client", "Demo AS", raising=False)
    monkeypatch.setattr(mod.session, "year", "2025", raising=False)

    def _raise(_client, _year):
        raise PermissionError("no access")

    monkeypatch.setattr(mod, "_load_materiality_state", _raise)

    mod._apply_materiality_to_studio(studio)

    assert calls == [(None, None)]


def test_apply_materiality_to_studio_without_client_or_year_sends_none(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []
    studio = SimpleNamespace(set_materiality_context=lambda payload, key: calls.append((payload, key)))

    # load_state skal IKKE kalles når klient/år mangler
    def _should_not_be_called(_c, _y):
        raise AssertionError("load_state må ikke kalles uten klient/år")

    monkeypatch.setattr(mod, "_load_materiality_state", _should_not_be_called)

    monkeypatch.setattr(mod.session, "client", None, raising=False)
    monkeypatch.setattr(mod.session, "year", "2025", raising=False)
    mod._apply_materiality_to_studio(studio)
    assert calls == [(None, None)]

    calls.clear()
    monkeypatch.setattr(mod.session, "client", "Demo AS", raising=False)
    monkeypatch.setattr(mod.session, "year", "", raising=False)
    mod._apply_materiality_to_studio(studio)
    assert calls == [(None, None)]


def test_apply_materiality_to_studio_noop_when_studio_lacks_setter() -> None:
    """Backwards-kompatibel: en SelectionStudio uten set_materiality_context
    skal ignoreres stille (ingen exception)."""
    studio = SimpleNamespace()  # ingen set_materiality_context
    # Skal ikke kaste
    mod._apply_materiality_to_studio(studio)


def test_open_studio_calls_materiality_wiring(monkeypatch) -> None:
    """_open_studio skal kalle _apply_materiality_to_studio med studio-instansen
    rett etter at SelectionStudio er konstruert."""
    import pandas as pd

    constructed: list[object] = []
    wired: list[object] = []

    class _FakeStudio:
        def __init__(self, master, df, on_commit, df_all):
            self.master = master
            self.df = df
            self.on_commit = on_commit
            self.df_all = df_all
            constructed.append(self)

    monkeypatch.setattr(mod, "SelectionStudio", _FakeStudio)
    monkeypatch.setattr(mod, "_apply_materiality_to_studio", lambda studio: wired.append(studio))

    page = mod.UtvalgPage.__new__(mod.UtvalgPage)
    page._df_show = pd.DataFrame({"Beløp": [100.0]})
    page._df_all = pd.DataFrame({"Beløp": [100.0, 200.0]})

    mod.UtvalgPage._open_studio(page)

    assert len(constructed) == 1
    assert wired == [constructed[0]]
