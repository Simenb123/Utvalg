from __future__ import annotations

import pandas as pd

import regnskapslinje_suggest as suggest


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [10, 20],
            "regnskapslinje": ["Maskiner og inventar", "Skyldig skatt"],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )


def test_normalize_rulebook_document_cleans_overlay_fields() -> None:
    normalized = suggest.normalize_rulebook_document(
        {
            "rules": {
                " 10 ": {
                    "label": " Maskiner og inventar ",
                    "aliases": ["maskiner", " inventar ", "maskiner"],
                    "exclude_aliases": "gjeld\ngjeld",
                    "usage_keywords": "avskrivning\nvedlikehold",
                    "account_ranges": ["1200-1299", " "],
                    "normal_balance_hint": "debet_typisk",
                },
                "x": {"aliases": ["ugyldig"]},
            }
        }
    )

    assert normalized["rules"]["10"]["aliases"] == ["maskiner", "inventar"]
    assert normalized["rules"]["10"]["exclude_aliases"] == ["gjeld"]
    assert normalized["rules"]["10"]["usage_keywords"] == ["avskrivning", "vedlikehold"]
    assert normalized["rules"]["10"]["account_ranges"] == ["1200-1299"]
    assert normalized["rules"]["10"]["normal_balance_hint"] == "debet_typisk"
    assert "x" not in normalized["rules"]


def test_suggest_regnskapslinje_uses_aliases_and_soft_sign_note() -> None:
    suggestion = suggest.suggest_regnskapslinje(
        konto="1200",
        kontonavn="Maskiner og inventar",
        ub=-500.0,
        regnskapslinjer=_regnskapslinjer_df(),
        rulebook_document={
            "rules": {
                "10": {
                    "aliases": ["maskiner", "inventar"],
                    "account_ranges": ["1200-1299"],
                    "normal_balance_hint": "debet_typisk",
                }
            }
        },
    )

    assert suggestion is not None
    assert suggestion.regnr == 10
    assert suggestion.confidence_bucket == "Middels"
    assert "navn/alias" in suggestion.reason
    assert "Fortegn" in suggestion.sign_note


def test_suggest_regnskapslinje_history_can_surface_without_alias_hit() -> None:
    suggestion = suggest.suggest_regnskapslinje(
        konto="2990",
        kontonavn="Uklassifisert konto",
        ub=-250.0,
        regnskapslinjer=_regnskapslinjer_df(),
        rulebook_document={"rules": {}},
        historical_regnr=20,
    )

    assert suggestion is not None
    assert suggestion.regnr == 20
    assert suggestion.source == "historikk"
    assert "historikk" in suggestion.reason
