from __future__ import annotations

import pandas as pd

from a07_feature.control_presenter import (
    build_control_panel_state,
    build_gl_selection_amount_summary,
    build_gl_selection_status_message,
    build_selected_code_status_message,
)


def test_build_selected_code_status_message_uses_linked_accounts_summary() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lønn", "Endring": 100.0},
            {"Konto": "5002", "Navn": "Etterlønn", "Endring": 25.0},
        ]
    )

    out = build_selected_code_status_message(
        code="fastloenn",
        accounts_df=accounts_df,
        basis_col="Endring",
    )

    assert out.startswith("Valgt fastloenn | 2 kontoer koblet | Endring 125,00")
    assert "5000 Lønn" in out


def test_build_gl_selection_status_message_handles_multi_select_without_conflicting_codes() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn"},
            {"Konto": "5001", "Kode": "fastloenn"},
        ]
    )

    out = build_gl_selection_status_message(
        control_gl_df=control_gl_df,
        account="5000",
        selected_accounts=["5000", "5001"],
    )

    assert out == "2 kontoer er valgt og er koblet til fastloenn."


def test_build_gl_selection_amount_summary_uses_ib_endring_ub() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "IB": 10.0, "Endring": 100.0, "UB": 110.0},
            {"Konto": "5001", "IB": "-5,00", "Endring": "1 234,50", "UB": "1.300,50"},
        ]
    )

    out = build_gl_selection_amount_summary(
        control_gl_df=control_gl_df,
        selected_accounts=["5000", "5001"],
    )

    assert out == "2 kontoer valgt | IB: 5,00 | Endring: 1 334,50 | UB: 1 410,50"


def test_build_gl_selection_status_message_surfaces_mapping_audit_reason() -> None:
    control_gl_df = pd.DataFrame(
        [
            {
                "Konto": "6701",
                "Kode": "annet",
                "MappingAuditStatus": "Feil",
                "MappingAuditReason": "Kontoen ser ut som drifts-/honorarkostnad utenfor A07-lonn.",
            },
        ]
    )

    out = build_gl_selection_status_message(
        control_gl_df=control_gl_df,
        account="6701",
        selected_accounts=["6701"],
    )

    assert out == "Konto 6701 har feil A07-kobling: Kontoen ser ut som drifts-/honorarkostnad utenfor A07-lonn."


def test_build_control_panel_state_marks_saldobalanse_follow_up_cleanly() -> None:
    linked_accounts_df = pd.DataFrame([{"Konto": "5945", "Navn": "Pensjonsforsikring", "Endring": 690556.0}])

    state = build_control_panel_state(
        code="tilskuddOgPremieTilPensjon",
        navn="Tilskudd og premie til pensjon",
        status="Uløst",
        work_label="Manuell",
        why_text="Direkte treff på pensjon.",
        next_action="Tildel RF-1022-post i Saldobalanse.",
        a07_amount_text="690 556,00",
        gl_amount_text="684 825,00",
        diff_amount_text="5 731,00",
        linked_accounts_df=linked_accounts_df,
        basis_col="Endring",
        has_history=False,
        best_suggestion=None,
        is_locked=False,
    )

    assert state.use_saldobalanse_action is True
    assert state.meta_text == "Klassifisering i Saldobalanse."
    assert state.next_text == "Neste: Tildel RF-1022-post i Saldobalanse."
    assert state.match_text == "A07 690 556,00 | GL 684 825,00 | Diff 5 731,00"


def test_build_control_panel_state_routes_existing_avvik_to_best_suggestion() -> None:
    state = build_control_panel_state(
        code="feriepenger",
        navn="Feriepenger",
        guided_status="Kontroller kobling",
        guided_next="Kontroller kobling",
        linked_accounts_df=pd.DataFrame([{"Konto": "5020", "Navn": "Feriepenger", "UB": 866816.10}]),
        basis_col="UB",
        best_suggestion=pd.Series(
            {
                "ForslagKontoer": "2932,2940",
                "WithinTolerance": True,
                "UsedSpecialAdd": True,
            }
        ),
        matching_ready=True,
        suggestion_count=1,
    )

    assert state.action_label == "Se forslag"
    assert state.action_target == "suggestions"
    assert state.reason_text == "Det finnes et konkret forslag som kan vurderes."
