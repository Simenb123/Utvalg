from __future__ import annotations

from types import SimpleNamespace

import pandas as pd


class _DummyVar:
    def __init__(self, value: str):
        self._value = value

    def get(self) -> str:
        return self._value


def test_open_nr_series_control_builds_rl_scope_and_opens_popup(monkeypatch) -> None:
    import page_analyse_actions_impl
    import page_analyse_rl

    df_all = pd.DataFrame(
        {
            "Konto": ["3000", "1500", "3000"],
            "Bilag": ["100443", "100443", "100444"],
            "Referanse": ["443", "443", "444"],
            "Tekst": ["Faktura nummer 443", "Faktura nummer 443", "Faktura nummer 444"],
        }
    )
    df_filtered = df_all.loc[df_all["Konto"] == "3000"].copy()

    page = SimpleNamespace(
        dataset=df_all,
        _df_filtered=df_filtered,
        _var_aggregering=_DummyVar("Regnskapslinje"),
    )
    page._get_selected_accounts = lambda: ["3000"]

    monkeypatch.setattr(page_analyse_rl, "get_selected_rl_rows", lambda *, page: [(10, "Salgsinntekt")])

    captured = {}

    def fake_popup(**kwargs) -> None:
        captured.update(kwargs)

    page_analyse_actions_impl.open_nr_series_control(
        page=page,
        messagebox=None,
        show_nr_series_control=fake_popup,
    )

    assert captured["master"] is page
    assert captured["selected_accounts"] == ["3000"]
    assert captured["scope_mode"] == "regnskapslinje"
    assert captured["scope_items"] == ["10 Salgsinntekt"]
    assert captured["konto_regnskapslinje_map"] == {}
    assert captured["analysis_jump_callback"] == getattr(page, "_jump_to_nr_series_context", None)
    assert captured["df_scope"]["Konto"].tolist() == ["3000", "3000"]
    assert captured["df_all"].equals(df_all)


def test_analysepage_open_nr_series_control_forwards_dependencies(monkeypatch) -> None:
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    captured = {}
    popup_sentinel = object()

    monkeypatch.setattr(page_analyse, "_show_nr_series_control", popup_sentinel, raising=False)

    def fake_open(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(page_analyse.page_analyse_actions_impl, "open_nr_series_control", fake_open)

    page_analyse.AnalysePage._open_nr_series_control(page)

    assert captured["page"] is page
    assert captured["messagebox"] is page_analyse.messagebox
    assert captured["show_nr_series_control"] is popup_sentinel
