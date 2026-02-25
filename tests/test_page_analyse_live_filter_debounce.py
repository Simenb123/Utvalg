from __future__ import annotations


def test_schedule_apply_filters_debounces(monkeypatch) -> None:
    """Søk/Min/Maks skal bruke debounce (after/after_cancel) for å redusere støy."""
    import page_analyse

    page = page_analyse.AnalysePage(None)

    # Testene kan kjøre i headless CI der Tk init feiler.
    # Vi simulerer bare 'after'/'after_cancel' og tvinger _tk_ok=True.
    page._tk_ok = True  # type: ignore[attr-defined]

    calls: list[tuple[str, object]] = []

    def fake_after(ms: int, fn):
        calls.append(("after", ms))
        # returner en id tilsvarende Tk
        return f"after-{len([c for c in calls if c[0] == 'after'])}"

    def fake_after_cancel(after_id: str):
        calls.append(("cancel", after_id))

    # Unngå at planlagt callback kjører "ekte" filtrering i testen
    monkeypatch.setattr(page, "_apply_filters_and_refresh", lambda: None, raising=True)

    # Patch after/after_cancel
    monkeypatch.setattr(page, "after", fake_after, raising=False)
    monkeypatch.setattr(page, "after_cancel", fake_after_cancel, raising=False)

    # Første schedule
    page._filter_after_id = None  # type: ignore[attr-defined]
    page._schedule_apply_filters()
    first_id = page._filter_after_id
    assert isinstance(first_id, str)

    # Ny schedule skal avbryte forrige
    page._schedule_apply_filters()
    second_id = page._filter_after_id
    assert isinstance(second_id, str)
    assert second_id != first_id

    assert ("cancel", first_id) in calls


def test_apply_filters_now_cancels_debounce(monkeypatch) -> None:
    """_apply_filters_now skal avbryte planlagt debounce og kjøre filtrering umiddelbart."""
    import page_analyse

    page = page_analyse.AnalysePage(None)
    page._tk_ok = True  # type: ignore[attr-defined]

    calls: list[tuple[str, object]] = []
    applied = {"n": 0}

    def fake_after_cancel(after_id: str):
        calls.append(("cancel", after_id))

    def fake_apply() -> None:
        applied["n"] += 1

    monkeypatch.setattr(page, "after_cancel", fake_after_cancel, raising=False)
    monkeypatch.setattr(page, "_apply_filters_and_refresh", fake_apply, raising=True)

    page._filter_after_id = "after-1"  # type: ignore[attr-defined]

    page._apply_filters_now()

    assert ("cancel", "after-1") in calls
    assert page._filter_after_id is None
    assert applied["n"] == 1
