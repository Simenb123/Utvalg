from __future__ import annotations

import page_materiality as mod


class _DummyVar:
    def __init__(self, value="") -> None:
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


def _digits(text: object) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())


def test_resolve_active_threshold_display_formats_supported_threshold() -> None:
    label, amount = mod._resolve_active_threshold_display(
        {
            "performance_materiality": 175000,
            "overall_materiality": 250000,
            "clearly_trivial": 17500,
        },
        "performance_materiality",
    )

    assert label == "Arbeidsvesentlighet (PM)"
    assert _digits(amount) == "175000"


def test_resolve_active_threshold_display_tolerates_legacy_manual_state() -> None:
    label, amount = mod._resolve_active_threshold_display(
        {
            "overall_materiality": 250000,
        },
        "manual",
    )

    assert label == "Manuell"
    assert amount == "-"


def test_sync_threshold_choice_from_state_falls_back_to_supported_choice() -> None:
    page = mod.MaterialityPage.__new__(mod.MaterialityPage)
    page._state = {"selection_threshold_key": "manual"}
    page._threshold_choice_sync_guard = False
    page.var_threshold_choice = _DummyVar("")

    mod.MaterialityPage._sync_threshold_choice_from_state(page)

    assert page.var_threshold_choice.get() == "Arbeidsvesentlighet (PM)"


def test_on_threshold_choice_selected_persists_and_notifies(monkeypatch) -> None:
    page = mod.MaterialityPage.__new__(mod.MaterialityPage)
    page._client = "Demo AS"
    page._year = "2025"
    page._state = {
        "selection_threshold_key": "performance_materiality",
        "active_materiality": {
            "overall_materiality": 250000,
            "performance_materiality": 175000,
            "clearly_trivial": 17500,
        },
    }
    page._threshold_choice_sync_guard = False
    page.var_threshold_choice = _DummyVar("Total vesentlighet (OM)")
    page.var_status = _DummyVar("")

    merge_calls: list[tuple[str, str, dict[str, str]]] = []
    follow_up_calls: list[object] = []

    def _fake_merge(client: str, year: str, updates: dict[str, str]):
        merge_calls.append((client, year, dict(updates)))
        state = dict(page._state)
        state.update(dict(updates))
        return state

    monkeypatch.setattr(mod, "merge_state", _fake_merge)
    page._set_active_materiality = lambda payload: follow_up_calls.append(("set_active", payload))
    page._notify_utvalg_materiality_updated = lambda: follow_up_calls.append("notify")

    mod.MaterialityPage._on_threshold_choice_selected(page)

    assert merge_calls == [("Demo AS", "2025", {"selection_threshold_key": "overall_materiality"})]
    assert page._state["selection_threshold_key"] == "overall_materiality"
    assert any(call == "notify" for call in follow_up_calls)
    assert "Total vesentlighet" in str(page.var_status.get())


def test_refresh_calculation_updates_inverse_percentages_for_manual_om() -> None:
    page = mod.MaterialityPage.__new__(mod.MaterialityPage)
    page._benchmark_amounts = {"gross_profit": 6000000.0}
    page.var_benchmark = _DummyVar(mod.BENCHMARK_LABELS["gross_profit"])
    page.var_benchmark_amount = _DummyVar("-")
    page.var_reference_pct_range = _DummyVar("-")
    page.var_reference_amount_range = _DummyVar("-")
    page.var_selected_om = _DummyVar("175 000")
    page.var_pm_pct = _DummyVar("75,0")
    page.var_trivial_pct = _DummyVar("10,0")
    page.var_calc_om = _DummyVar("-")
    page.var_calc_pm = _DummyVar("-")
    page.var_calc_trivial = _DummyVar("-")
    page.var_calc_om_pct_of_benchmark = _DummyVar("-")
    page.var_calc_pm_pct_of_om = _DummyVar("-")
    page.var_calc_trivial_pct_of_pm = _DummyVar("-")
    page._benchmark_key = lambda: "gross_profit"
    page._update_action_states = lambda: None

    mod.MaterialityPage._refresh_calculation(page)

    assert _digits(page.var_calc_om.get()) == "175000"
    assert page.var_calc_om_pct_of_benchmark.get() == "2,92 %"
    assert page.var_calc_pm_pct_of_om.get() == "75,00 %"
    assert page.var_calc_trivial_pct_of_pm.get() == "10,00 %"
