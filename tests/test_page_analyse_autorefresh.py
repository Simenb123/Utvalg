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


def test_refresh_from_session_defer_heavy_schedules_without_full_refresh(monkeypatch) -> None:
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._tk_ok = True  # type: ignore[attr-defined]
    page.dataset = None

    called: list[str] = []

    monkeypatch.setattr(page, "_refresh_mva_code_choices", lambda: called.append("mva"), raising=False)
    monkeypatch.setattr(page, "_update_data_level", lambda: called.append("level"), raising=False)
    monkeypatch.setattr(page, "_schedule_heavy_refresh", lambda: called.append("schedule"), raising=False)
    monkeypatch.setattr(page, "_reload_rl_config", lambda: called.append("reload"), raising=False)
    monkeypatch.setattr(page, "_apply_filters_and_refresh", lambda: called.append("apply"), raising=False)

    class DummySession:
        dataset = "dummy"

    page_analyse.AnalysePage.refresh_from_session(page, DummySession(), defer_heavy=True)

    assert page.dataset == "dummy"
    assert called == ["mva", "level", "schedule"]


def test_schedule_heavy_refresh_coalesces(monkeypatch) -> None:
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._tk_ok = True  # type: ignore[attr-defined]
    page._heavy_refresh_after_id = None
    page._heavy_refresh_generation = 0

    calls: list[tuple[str, object]] = []

    def fake_after_idle(fn):
        calls.append(("after_idle", fn))
        return f"idle-{len([c for c in calls if c[0] == 'after_idle'])}"

    def fake_after_cancel(after_id):
        calls.append(("cancel", after_id))

    monkeypatch.setattr(page, "after_idle", fake_after_idle, raising=False)
    monkeypatch.setattr(page, "after_cancel", fake_after_cancel, raising=False)

    page_analyse.AnalysePage._schedule_heavy_refresh(page)
    first_id = page._heavy_refresh_after_id

    page_analyse.AnalysePage._schedule_heavy_refresh(page)
    second_id = page._heavy_refresh_after_id

    assert first_id == "idle-1"
    assert second_id == "idle-2"
    assert ("cancel", "idle-1") in calls


def test_include_ao_change_uses_adjustment_refresh(monkeypatch) -> None:
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    called = {"n": 0}
    monkeypatch.setattr(
        page,
        "_refresh_analysis_views_after_adjustment_change",
        lambda: called.__setitem__("n", called["n"] + 1),
        raising=False,
    )

    page_analyse.AnalysePage._on_include_ao_changed(page)

    assert called["n"] == 1


def test_adjustment_refresh_includes_nokkeltall_view(monkeypatch) -> None:
    """ÅO-toggle må også refreshe nøkkeltall-visningen, ikke bare pivot/detaljer/transaksjoner."""
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    calls: list[str] = []

    monkeypatch.setattr(page, "_refresh_pivot", lambda: calls.append("pivot"), raising=False)
    monkeypatch.setattr(page, "_refresh_detail_panel", lambda: calls.append("detail"), raising=False)
    monkeypatch.setattr(page, "_refresh_transactions_view", lambda: calls.append("tx"), raising=False)
    monkeypatch.setattr(page, "_refresh_nokkeltall_view", lambda: calls.append("nk"), raising=False)

    page_analyse.AnalysePage._refresh_analysis_views_after_adjustment_change(page)

    assert "nk" in calls
    assert calls == ["pivot", "detail", "tx", "nk"]
