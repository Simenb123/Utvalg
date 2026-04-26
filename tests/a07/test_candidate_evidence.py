from __future__ import annotations

import re

from .shared import *  # noqa: F401,F403

from a07_feature.control.evidence import normalize_candidate_evidence
from a07_feature.control.matching_guardrails import decorate_suggestions_for_display
from a07_feature.control.rf1022_candidates import build_rf1022_candidate_df


def test_candidate_evidence_normalizes_structured_fields_and_legacy_explain() -> None:
    structured = pd.Series(
        {
            "Explain": "Menneskelig forklaring uten maskintokens.",
            "UsedRulebook": True,
            "UsedUsage": True,
            "UsedSpecialAdd": True,
            "HitTokens": "lonn",
            "AnchorSignals": "navnetreff,kontobruk",
            "WithinTolerance": True,
            "AmountEvidence": "exact",
        }
    )
    legacy = pd.Series({"Explain": "basis=UB | navn=lonn | regel=kontonr | bruk=tekst | special_add"})

    structured_evidence = normalize_candidate_evidence(structured)
    legacy_evidence = normalize_candidate_evidence(legacy)

    assert structured_evidence.used_rulebook is True
    assert structured_evidence.used_usage is True
    assert structured_evidence.used_special_add is True
    assert structured_evidence.has_name_anchor is True
    assert structured_evidence.has_amount_support is True
    assert legacy_evidence.used_rulebook is True
    assert legacy_evidence.used_usage is True
    assert legacy_evidence.used_special_add is True
    assert legacy_evidence.has_name_anchor is True


def test_decisions_use_structured_evidence_when_explain_is_human_text() -> None:
    gl_df = pd.DataFrame(
        [{"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "BelopAktiv": 1000.0}]
    )
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "KodeNavn": "Fastlonn",
                "ForslagKontoer": "5000",
                "A07_Belop": 1000.0,
                "GL_Sum": 1000.0,
                "Diff": 0.0,
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "UsedRulebook": True,
                "HitTokens": "lonn",
                "AnchorSignals": "navnetreff,konto-intervall",
                "Explain": "Regelbok og kontonavn peker mot fastlonn.",
            }
        ]
    )

    decorated = decorate_suggestions_for_display(suggestions, gl_df)
    rf1022_candidates = build_rf1022_candidate_df(
        gl_df,
        decorated,
        "100_loenn_ol",
        basis_col="Endring",
    )

    assert decorated.loc[0, "SuggestionGuardrail"] == "accepted"
    assert decorated.loc[0, "HvorforKort"] == "Treff paa regelbok"
    assert rf1022_candidates["Konto"].tolist() == ["5000"]
    assert rf1022_candidates.loc[0, "Forslagsstatus"] == "Trygt forslag"


def test_legacy_explain_fallback_is_limited_to_evidence_module() -> None:
    root = Path("a07_feature/control")
    token_pattern = re.compile(
        r"(Explain.*(regel=|bruk=|special_add|navn=))|"
        r"((regel=|bruk=|special_add|navn=).*Explain)|"
        r"(explain_token=)|"
        r"(explain_lower)|"
        r"(row\.get\([\"']Explain[\"'])|"
        r"(_suggestion_text\(row, [\"']Explain[\"'])"
    )
    offenders: list[str] = []
    for path in root.glob("*.py"):
        if path.name == "evidence.py":
            continue
        text = path.read_text(encoding="utf-8")
        if token_pattern.search(text):
            offenders.append(str(path))

    assert offenders == []
