from __future__ import annotations

from types import SimpleNamespace

import page_utvalg_strata as mod


def test_apply_materiality_to_studio_reads_active_state(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []

    studio = SimpleNamespace(set_materiality_context=lambda payload, key: calls.append((payload, key)))
    page = mod.UtvalgStrataPage.__new__(mod.UtvalgStrataPage)
    page.studio = studio
    page.session = SimpleNamespace(client="Demo AS", year="2025")

    payload = {
        "source": "crmsystem",
        "performance_materiality": 175000,
    }
    monkeypatch.setattr(
        mod,
        "load_state",
        lambda client, year: {
            "active_materiality": payload,
            "selection_threshold_key": "performance_materiality",
        },
    )

    mod.UtvalgStrataPage._apply_materiality_to_studio(page)

    assert calls == [(payload, "performance_materiality")]


def test_apply_materiality_to_studio_tolerates_load_errors(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []

    studio = SimpleNamespace(set_materiality_context=lambda payload, key: calls.append((payload, key)))
    page = mod.UtvalgStrataPage.__new__(mod.UtvalgStrataPage)
    page.studio = studio
    page.session = SimpleNamespace(client="Demo AS", year="2025")

    def _raise(_client, _year):
        raise PermissionError("no access")

    monkeypatch.setattr(mod, "load_state", _raise)

    mod.UtvalgStrataPage._apply_materiality_to_studio(page)

    assert calls == [(None, None)]
