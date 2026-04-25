from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_apply_best_suggestion_requires_strict_guardrail() -> None:
    statuses: list[str] = []

    class DummyPage:
        tree_a07 = object()
        tree_control_suggestions = object()
        workspace = SimpleNamespace(
            mapping={},
            locks=set(),
            suggestions=pd.DataFrame(),
        )

        def _selected_control_code(self):
            return "annet"

        def _ensure_suggestion_display_fields(self):
            return pd.DataFrame(
                [
                    {
                        "Kode": "annet",
                        "ForslagKontoer": "6701",
                        "WithinTolerance": True,
                        "SuggestionGuardrail": "review",
                        "SuggestionGuardrailReason": "Belop uten stotte",
                    }
                ]
            )

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == [
        "Beste forslag er ikke trygt nok for automatisk bruk (Belop uten stotte). Kontroller eller map manuelt."
    ]

