from __future__ import annotations

import json

import pandas as pd

import classification_config
from a07_feature import (
    SuggestConfig,
    apply_suggestion_to_mapping,
    load_rulebook,
    suggest_mapping_candidates,
    suggest_mappings,
)
from a07_feature.page_paths import build_suggest_config


def test_global_rulebook_excludes_control_only_tax_codes():
    rulebook = load_rulebook(str(classification_config.resolve_rulebook_path()))

    assert "aga" not in rulebook
    assert "forskuddstrekk" not in rulebook


def test_suggest_excludes_aga_and_ignores_mapping_to_excluded_codes():
    a07 = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000},
            {"Kode": "aga", "Navn": "AGA", "Belop": 200},
            {"Kode": "forskuddstrekk", "Navn": "Forskuddstrekk", "Belop": 300},
        ]
    )
    gl = pd.DataFrame(
        [
            {"Konto": 5000, "Navn": "Loenn til ansatte", "UB": 0, "Debet": 1000, "Kredit": 0},
            {"Konto": 5400, "Navn": "Arbeidsgiveravgift", "UB": 0, "Debet": 200, "Kredit": 0},
            {"Konto": 2600, "Navn": "Forskuddstrekk", "UB": 0, "Debet": 0, "Kredit": 300},
        ]
    )

    cfg = SuggestConfig(
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        top_codes=10,
        exclude_mapped_accounts=True,
        override_existing_mapping=False,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
    )

    df = suggest_mapping_candidates(a07, gl, mapping_existing={"5000": "aga"}, config=cfg)

    assert "aga" not in set(df["Kode"].astype(str).tolist())
    assert "forskuddstrekk" not in set(df["Kode"].astype(str).tolist())
    row = df.loc[df["Kode"] == "fastloenn"].iloc[0]
    assert row["ForslagKontoer"] == "5000"
    assert row["GL_Sum"] == 1000
    assert bool(row["WithinTolerance"]) is True


def test_suggest_mappings_filters_irrelevant_accounts_and_keeps_columns_stable():
    a07 = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1_000_000},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 50_000},
        ]
    )
    gl = pd.DataFrame(
        [
            {"Konto": 1000, "Navn": "Bankinnskudd", "UB": 75_000_000, "Debet": 0, "Kredit": 0},
            {"Konto": 5000, "Navn": "Loenn til ansatte", "UB": 600_000, "Debet": 600_000, "Kredit": 0},
            {"Konto": 5010, "Navn": "Loenn timeloenn", "UB": 400_000, "Debet": 400_000, "Kredit": 0},
            {"Konto": 5090, "Navn": "Bonus", "UB": 50_000, "Debet": 50_000, "Kredit": 0},
            {"Konto": 7000, "Navn": "Kontorrekvisita", "UB": 10_000, "Debet": 10_000, "Kredit": 0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=2,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
    )

    assert list(df.columns) == [
        "Kode",
        "KodeNavn",
        "Basis",
        "A07_Belop",
        "ForslagKontoer",
        "GL_Sum",
        "Diff",
        "Score",
        "ComboSize",
        "WithinTolerance",
        "HitTokens",
        "HistoryAccounts",
        "Explain",
        "UsedRulebook",
        "UsedHistory",
        "UsedUsage",
        "UsedSpecialAdd",
        "UsedResidual",
        "AmountEvidence",
        "AmountDiffAbs",
        "AnchorSignals",
    ]
    assert not df["ForslagKontoer"].astype(str).str.contains("1000").any()

    fast = df[df["Kode"] == "fastloenn"].iloc[0]
    assert fast["ForslagKontoer"] in {"5000,5010", "5010,5000"}
    assert fast["GL_Sum"] == 1_000_000
    assert bool(fast["WithinTolerance"]) is True
    assert str(fast["Basis"]).strip() != ""
    assert "basis=" in str(fast["Explain"])
    assert str(fast["AmountEvidence"]) in {"exact", "within_tolerance"}
    assert float(fast["AmountDiffAbs"]) <= 1.0

    bonus = df[df["Kode"] == "bonus"].iloc[0]
    assert bonus["ForslagKontoer"] == "5090"
    assert bonus["GL_Sum"] == 50_000


def test_build_suggest_config_lets_rule_basis_override_ui_fallback(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        """
{
  "rules": {
    "fastloenn": {
      "label": "Fastlonn",
      "basis": "UB",
      "allowed_ranges": ["5000"],
      "keywords": ["lonn", "wages"]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    a07 = pd.DataFrame([{"Kode": "fastloenn", "Navn": "Fastlonn", "Belop": 1000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Wages", "Endring": 0.0, "UB": 1000.0},
            {"Konto": "6000", "Navn": "Wages out of scope", "Endring": 1000.0, "UB": 1000.0},
        ]
    )
    cfg = build_suggest_config(
        rulebook_path,
        {"tolerance_abs": 1.0, "tolerance_rel": 0.001, "max_combo": 1},
        basis_col="Endring",
    )

    df = suggest_mapping_candidates(a07, gl, mapping_existing={}, config=cfg)

    row = df.loc[df["Kode"] == "fastloenn"].iloc[0]
    assert cfg.basis_strategy == "per_code"
    assert row["Basis"] == "UB"
    assert row["ForslagKontoer"] == "5000"
    assert bool(row["UsedRulebook"]) is True
    assert bool(row["WithinTolerance"]) is True
    assert "wages" in str(row["HitTokens"]).casefold()


def test_suggest_residual_only_matches_remaining_amount():
    a07 = pd.DataFrame([{"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1_000_000}])
    gl = pd.DataFrame(
        [
            {"Konto": 5000, "Navn": "Loenn til ansatte", "UB": 600_000, "Debet": 600_000, "Kredit": 0},
            {"Konto": 5010, "Navn": "Loenn timeloenn", "UB": 400_000, "Debet": 400_000, "Kredit": 0},
            {"Konto": 5090, "Navn": "Bonus", "UB": 50_000, "Debet": 50_000, "Kredit": 0},
        ]
    )

    cfg = SuggestConfig(
        max_combo=2,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        top_codes=10,
        exclude_mapped_accounts=True,
        override_existing_mapping=False,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
    )

    df = suggest_mapping_candidates(a07, gl, mapping_existing={"5000": "fastloenn"}, config=cfg)

    row = df.loc[df["Kode"] == "fastloenn"].iloc[0]
    assert row["ForslagKontoer"] == "5010"
    assert row["GL_Sum"] == 1_000_000
    assert bool(row["WithinTolerance"]) is True
    assert bool(row["UsedResidual"]) is True


def test_apply_suggestion_to_mapping_respects_existing_mapping_by_default():
    a07 = pd.DataFrame([{"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1_000_000}])
    gl = pd.DataFrame(
        [
            {"Konto": 5000, "Navn": "Loenn til ansatte", "UB": 600_000, "Debet": 600_000, "Kredit": 0},
            {"Konto": 5010, "Navn": "Loenn timeloenn", "UB": 400_000, "Debet": 400_000, "Kredit": 0},
        ]
    )

    df = suggest_mapping_candidates(
        a07,
        gl,
        mapping={},
        config=SuggestConfig(top_suggestions_per_code=1, max_combo=2, tolerance_rel=0.001, tolerance_abs=1.0),
    )
    row = df.iloc[0]

    mapping = {}
    apply_suggestion_to_mapping(mapping, row)
    assert mapping["5000"] == "fastloenn"
    assert mapping["5010"] == "fastloenn"

    mapping2 = {"5000": "bonus"}
    apply_suggestion_to_mapping(mapping2, row, override_existing=False)
    assert mapping2["5000"] == "bonus"
    assert mapping2["5010"] == "fastloenn"


def test_suggestconfig_accepts_top_per_code_alias():
    cfg = SuggestConfig(top_suggestions_per_code=1, top_per_code=7)
    assert cfg.top_suggestions_per_code == 7


def test_load_rulebook_supports_pipe_ranges_and_special_add(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "fastloenn": {
                        "label": "Fast loenn",
                        "allowed_ranges": ["5000-5099 | 5190", "5290"],
                        "keywords": ["loenn", "maanedsloenn", "fastlonn"],
                        "special_add": [
                            {"account": "2940", "keywords": ["feriepenger"], "basis": "Endring", "weight": -1.0}
                        ],
                        "expected_sign": 1,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rulebook = load_rulebook(str(rulebook_path))
    rule = rulebook["fastloenn"]

    assert rule.allowed_ranges == ((5000, 5099), (5190, 5190), (5290, 5290))
    assert "maanedsloenn" in rule.keywords
    assert len(rule.special_add) == 1
    assert rule.special_add[0].account == "2940"
    assert rule.special_add[0].keywords == ("feriepenger",)
    assert rule.expected_sign == 1


def test_suggest_mappings_applies_rulebook_special_add_in_solver(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "feriepenger": {
                        "basis": "Endring",
                        "allowed_ranges": ["5000-5399 | 2900-2940"],
                        "keywords": ["feriepenger"],
                        "boost_accounts": ["2940"],
                        "expected_sign": 0,
                        "special_add": [{"account": "2940", "basis": "Endring", "weight": -1.0}],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 300.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Feriepenger kostnad", "Endring": 500.0},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "Endring": 200.0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="Endring",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    row = df.loc[df["Kode"] == "feriepenger"].iloc[0]
    assert row["ForslagKontoer"] == "5000,2940"
    assert row["GL_Sum"] == 300.0
    assert bool(row["WithinTolerance"]) is True
    assert "special_add" in str(row["Explain"])
    assert bool(row["UsedSpecialAdd"]) is True
    assert bool(row["UsedRulebook"]) is True
    assert "special_add" in str(row["AnchorSignals"])


def test_suggest_mappings_keeps_unmapped_special_add_as_mapping_candidate(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "feriepenger": {
                        "basis": "UB",
                        "allowed_ranges": ["5020", "2940"],
                        "keywords": ["feriepenger"],
                        "boost_accounts": ["2940"],
                        "special_add": [{"account": "2940", "basis": "Endring", "weight": 1.0}],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 900.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5020", "Navn": "Feriepenger", "UB": 1000.0, "Endring": 1000.0},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "UB": 4000.0, "Endring": -100.0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={"5020": "feriepenger"},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    row = df.loc[df["Kode"] == "feriepenger"].iloc[0]
    assert row["ForslagKontoer"] == "2940"
    assert row["GL_Sum"] == 900.0
    assert bool(row["WithinTolerance"]) is True


def test_suggest_mappings_special_add_can_match_balance_range_by_name(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "feriepenger": {
                        "basis": "UB",
                        "allowed_ranges": ["5020"],
                        "keywords": ["feriepenger"],
                        "special_add": [
                            {
                                "account": "2900-2999",
                                "keywords": ["feriepenger"],
                                "basis": "Endring",
                                "weight": 1.0,
                            }
                        ],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 900.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5020", "Navn": "Feriepenger", "UB": 1000.0, "Endring": 1000.0},
            {"Konto": "2941", "Navn": "Skyldig feriepenger", "UB": -1100.0, "Endring": -100.0},
            {"Konto": "2960", "Navn": "Annen palopt kostnad", "UB": -300.0, "Endring": -300.0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={"5020": "feriepenger"},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    row = df.loc[df["Kode"] == "feriepenger"].iloc[0]
    assert row["ForslagKontoer"] == "2941"
    assert row["GL_Sum"] == 900.0
    assert bool(row["WithinTolerance"]) is True
    assert bool(row["UsedSpecialAdd"]) is True


def test_suggest_mappings_expected_sign_prefers_negative_match(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "trekkILoennForFerie": {
                        "basis": "Endring",
                        "allowed_ranges": ["5200-5399"],
                        "keywords": ["trekk", "ferie"],
                        "expected_sign": -1,
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "trekkILoennForFerie", "Navn": "Trekk i loenn for ferie", "Belop": -59009.1}])
    gl = pd.DataFrame(
        [
            {"Konto": "5290", "Navn": "Trekk i loenn for ferie", "Endring": -59009.1},
            {"Konto": "5291", "Navn": "Trekk i loenn for ferie", "Endring": 59009.1},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="Endring",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    row = df.loc[df["Kode"] == "trekkILoennForFerie"].iloc[0]
    assert row["ForslagKontoer"] == "5290"
    assert row["GL_Sum"] == -59009.1
    assert bool(row["WithinTolerance"]) is True
    assert "sign=-1" in str(row["Explain"])
    assert bool(row["UsedRulebook"]) is True
    assert "sign" in str(row["AnchorSignals"])


def test_suggest_mappings_sign_evidence_only_when_combo_matches_sign(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "trekkILoennForFerie": {
                        "basis": "Endring",
                        "allowed_ranges": ["5200-5399"],
                        "keywords": ["trekk", "ferie"],
                        "expected_sign": -1,
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "trekkILoennForFerie", "Navn": "Trekk i loenn for ferie", "Belop": -59009.1}])
    gl = pd.DataFrame(
        [
            {"Konto": "5290", "Navn": "Trekk i loenn for ferie", "Endring": -59009.1},
            {"Konto": "5291", "Navn": "Trekk i loenn for ferie", "Endring": 59009.1},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=5,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="Endring",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    matching = df.loc[df["ForslagKontoer"] == "5290"].iloc[0]
    assert "sign" in str(matching["AnchorSignals"])
    assert bool(matching["UsedRulebook"]) is True

    wrong = df.loc[df["ForslagKontoer"] == "5291"]
    assert not wrong.empty, "forventet at feil-fortegn-kandidaten også emittes"
    wrong_row = wrong.iloc[0]
    assert "sign" not in str(wrong_row["AnchorSignals"]).split(",")


def test_suggest_mappings_keyword_match_sets_used_rulebook(tmp_path):
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "bonus": {
                        "label": "Bonus",
                        "keywords": ["bonus"],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    a07 = pd.DataFrame([{"Kode": "bonus", "Navn": "Bonus", "Belop": 5000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5090", "Navn": "Bonus utbetalt", "Endring": 5000.0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=1,
        candidates_per_code=5,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="Endring",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    row = df.loc[df["Kode"] == "bonus"].iloc[0]
    assert row["ForslagKontoer"] == "5090"
    assert "bonus" in str(row["HitTokens"])
    assert bool(row["UsedRulebook"]) is True
    assert "navnetreff" in str(row["AnchorSignals"])


def test_suggest_mappings_prioritizes_previous_year_mapping_when_candidates_are_equal():
    a07 = pd.DataFrame([{"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Loenn", "Endring": 1000.0},
            {"Konto": "5001", "Navn": "Loenn", "Endring": 1000.0},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        mapping_prior={"5001": "fastloenn"},
        max_combo=1,
        candidates_per_code=10,
        top_suggestions_per_code=3,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="Endring",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
    )

    row = df.loc[df["Kode"] == "fastloenn"].iloc[0]
    assert row["ForslagKontoer"] == "5001"
    assert row["GL_Sum"] == 1000.0
    assert bool(row["WithinTolerance"]) is True
    assert row["HistoryAccounts"] == "5001"
    assert "historikk=5001" in str(row["Explain"])
    assert bool(row["UsedHistory"]) is True
    assert "historikk" in str(row["AnchorSignals"])
