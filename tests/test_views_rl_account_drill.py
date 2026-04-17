from __future__ import annotations

import views_rl_account_drill as drill


def test_resolve_initial_choice_prefers_suggestion_when_available() -> None:
    choice = drill._resolve_initial_choice(
        ["10 - Salg", "20 - Kundefordringer"],
        current_regnr=None,
        current_regnskapslinje="",
        suggested_regnr=20,
        suggested_regnskapslinje="Kundefordringer",
    )

    assert choice == "20 - Kundefordringer"


def test_suggestion_info_text_summarizes_why_and_sign_note() -> None:
    text = drill._suggestion_info_text(
        suggested_regnr=1460,
        suggested_regnskapslinje="Kundefordringer",
        suggestion_reason="navn/alias: kundefordring",
        suggestion_source="alias",
        confidence_bucket="Middels",
        sign_note="Fortegn passer med forventet normalbalanse.",
    )

    assert "Forslag: 1460 - Kundefordringer" in text
    assert "Kilde: alias" in text
    assert "Hvorfor: navn/alias: kundefordring" in text
    assert "Fortegn:" in text
