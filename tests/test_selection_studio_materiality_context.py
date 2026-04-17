from __future__ import annotations

from types import SimpleNamespace

from selection_studio import ui_widget_refresh as mod


class _DummyVar:
    def __init__(self, value="") -> None:
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


def _digits(text: object) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())


def _make_studio() -> SimpleNamespace:
    return SimpleNamespace(
        var_materiality_choice=_DummyVar(""),
        var_tolerable_error=_DummyVar(""),
        var_materiality_info=_DummyVar(""),
        _materiality_payload=None,
        _materiality_threshold_key="",
    )


def test_set_materiality_context_prefills_tolerable_error_from_active_threshold() -> None:
    studio = _make_studio()

    mod.set_materiality_context(
        studio,
        {
            "source": "crmsystem",
            "performance_materiality": 175000,
            "overall_materiality": 250000,
            "clearly_trivial": 17500,
        },
        "performance_materiality",
    )

    assert studio.var_materiality_choice.get() == "Arbeidsvesentlighet (PM)"
    assert _digits(studio.var_tolerable_error.get()) == "175000"
    assert "CRMSystem" in studio.var_materiality_info.get()


def test_set_materiality_context_tolerates_legacy_manual_without_overwriting_local_override() -> None:
    studio = _make_studio()
    studio.var_tolerable_error.set("12 345")

    mod.set_materiality_context(
        studio,
        {
            "source": "local_calculation",
            "overall_materiality": 250000,
        },
        "manual",
    )

    assert studio.var_materiality_choice.get() == "Manuell"
    assert _digits(studio.var_tolerable_error.get()) == "12345"
    assert "Manuell verdi i feltet" in studio.var_materiality_info.get()
