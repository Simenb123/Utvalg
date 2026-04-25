from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.pages.a07.backend.mapping_apply import (
    apply_magic_wand_suggestions_to_mapping,
    apply_residual_changes_to_mapping,
    apply_safe_suggestions_to_mapping,
)


@dataclass(frozen=True)
class _ResidualChange:
    account: str
    to_code: str
    from_code: str = ""


def test_apply_residual_changes_to_mapping_skips_locked_and_conflicting_accounts() -> None:
    mapping = {"5990": "annet"}

    result = apply_residual_changes_to_mapping(
        mapping,
        [
            _ResidualChange("5000", "fastloenn"),
            _ResidualChange("5990", "fastloenn"),
            _ResidualChange("2940", "feriepenger"),
            _ResidualChange("5001", "timeloenn", from_code="old"),
        ],
        locked_codes={"feriepenger"},
    )

    assert result.applied_codes == 1
    assert result.applied_accounts == 1
    assert result.focus_code == "fastloenn"
    assert mapping == {"5000": "fastloenn", "5990": "annet"}


def test_apply_magic_wand_suggestions_to_mapping_keeps_non_exact_and_locked_codes_unchanged() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "bonus",
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "Score": 0.4,
                "SuggestionGuardrail": "accepted",
                "Diff": 0.0,
            },
            {
                "Kode": "telefon",
                "ForslagKontoer": "6990",
                "WithinTolerance": True,
                "Score": 0.4,
                "SuggestionGuardrail": "accepted",
                "Diff": 0.5,
            },
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "2940",
                "WithinTolerance": True,
                "Score": 0.4,
                "SuggestionGuardrail": "accepted",
                "Diff": 0.0,
            },
        ]
    )
    mapping: dict[str, str] = {}

    result = apply_magic_wand_suggestions_to_mapping(
        mapping,
        suggestions_df=suggestions,
        effective_mapping={},
        unresolved_codes=["bonus", "telefon", "feriepenger"],
        locked_codes={"feriepenger"},
    )

    assert (result.applied_codes, result.applied_accounts, result.skipped_codes) == (1, 1, 2)
    assert mapping == {"5000": "bonus"}


def test_apply_safe_suggestions_to_mapping_uses_effective_mapping_guardrails() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "bonus",
                "ForslagKontoer": "5000",
                "Score": 0.95,
                "WithinTolerance": True,
                "SuggestionGuardrail": "accepted",
            },
            {
                "Kode": "telefon",
                "ForslagKontoer": "6990",
                "Score": 0.40,
                "WithinTolerance": True,
                "SuggestionGuardrail": "accepted",
            },
        ]
    )
    mapping: dict[str, str] = {}

    result = apply_safe_suggestions_to_mapping(
        mapping,
        suggestions_df=suggestions,
        effective_mapping={},
        locked_codes=set(),
        min_score=0.85,
    )

    assert (result.applied_codes, result.applied_accounts) == (1, 1)
    assert mapping == {"5000": "bonus"}
