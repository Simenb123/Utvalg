from __future__ import annotations


def test_direction_change_handler_triggers_apply(monkeypatch) -> None:
    """Retning combobox skal trigge filter-oppdatering uten ekstra klikk."""
    import page_analyse

    page = page_analyse.AnalysePage(None)

    # CI kan kjøre uten Tk. Vi simulerer at GUI er ok slik at handleren kjører.
    page._tk_ok = True  # type: ignore[attr-defined]

    called = {"n": 0}

    def _fake_apply() -> None:
        called["n"] += 1

    # Overstyr metoden på instansen – vi vil ikke kjøre full GUI-logikk i test.
    monkeypatch.setattr(page, "_apply_filters_and_refresh", _fake_apply, raising=True)

    page._on_direction_changed()

    assert called["n"] == 1


def test_max_rows_change_handler_refreshes_transactions(monkeypatch) -> None:
    """Endring i 'Vis' skal oppdatere transaksjonslisten."""
    import page_analyse

    page = page_analyse.AnalysePage(None)

    called = {"n": 0}

    def _fake_refresh() -> None:
        called["n"] += 1

    monkeypatch.setattr(page, "_refresh_transactions_view", _fake_refresh, raising=True)

    page._on_max_rows_changed()

    assert called["n"] == 1
