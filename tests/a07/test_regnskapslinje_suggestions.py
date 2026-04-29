from __future__ import annotations

import json

import pandas as pd

from a07_feature import load_rulebook, suggest_mappings


def test_load_rulebook_merges_global_preferred_regnskapslinjer(tmp_path) -> None:
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "global_preferred_regnskapslinjer": ["40 Lønnskostnad"],
                "rules": {
                    "fastloenn": {
                        "label": "Fast lønn",
                        "preferred_regnskapslinjer": ["500 Lønn"],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rulebook = load_rulebook(str(rulebook_path))

    assert rulebook["fastloenn"].preferred_regnskapslinjer == (40, 500)


def test_suggestions_hard_block_global_regnskapslinje_even_on_exact_amount(tmp_path) -> None:
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "global_blocked_regnskapslinjer": ["655 Bankinnskudd"],
                "rules": {
                    "feriepenger": {
                        "basis": "UB",
                        "preferred_ranges": ["2940"],
                        "keywords": ["feriepenger"],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    a07 = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 1000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "1920", "Navn": "Bankinnskudd", "UB": 1000.0, "Endring": 1000.0, "Regnr": "655"},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "UB": 1000.0, "Endring": 1000.0, "Regnr": "296"},
        ]
    )

    df = suggest_mappings(
        a07,
        gl,
        mapping={},
        max_combo=2,
        candidates_per_code=10,
        top_suggestions_per_code=5,
        filter_mode="a07",
        basis_strategy="per_code",
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    assert not df["ForslagKontoer"].astype(str).str.contains("1920").any()
    assert df.iloc[0]["ForslagKontoer"] == "2940"


def test_suggestions_prefer_regnskapslinje_rule_over_plain_amount_match(tmp_path) -> None:
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {"rules": {"fastTillegg": {"basis": "UB", "preferred_regnskapslinjer": ["500 Lonn"]}}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    a07 = pd.DataFrame([{"Kode": "fastTillegg", "Navn": "Fast tillegg", "Belop": 1000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "6800", "Navn": "Kontorrekvisita", "UB": 1000.0, "Endring": 1000.0, "Regnr": "777"},
            {"Konto": "5005", "Navn": "Fast tillegg", "UB": 1000.0, "Endring": 1000.0, "Regnr": "500"},
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
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    assert df.iloc[0]["ForslagKontoer"] == "5005"
    assert bool(df.iloc[0]["UsedRulebook"]) is True
    assert "regnskapslinje" in str(df.iloc[0]["AnchorSignals"])


def test_suggestions_prefer_global_regnskapslinje_rule_over_plain_amount_match(tmp_path) -> None:
    rulebook_path = tmp_path / "a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "global_preferred_regnskapslinjer": ["500 Lonn"],
                "rules": {"fastTillegg": {"basis": "UB"}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    a07 = pd.DataFrame([{"Kode": "fastTillegg", "Navn": "Fast tillegg", "Belop": 1000.0}])
    gl = pd.DataFrame(
        [
            {"Konto": "6800", "Navn": "Kontorrekvisita", "UB": 1000.0, "Endring": 1000.0, "Regnr": "777"},
            {"Konto": "5005", "Navn": "Fast tillegg", "UB": 1000.0, "Endring": 1000.0, "Regnr": "500"},
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
        basis="UB",
        tolerance_rel=0.001,
        tolerance_abs=1.0,
        rulebook_path=str(rulebook_path),
    )

    assert df.iloc[0]["ForslagKontoer"] == "5005"
    assert "regnskapslinje" in str(df.iloc[0]["AnchorSignals"])
