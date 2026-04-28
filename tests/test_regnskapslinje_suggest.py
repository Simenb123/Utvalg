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


def test_ownership_pct_to_regnr_threshold_boundaries() -> None:
    """Følg rskl. § 1-3: kun *over* 50 % er datter, 20-50 % er tilknyttet."""
    # Datter (>50%): kontroll
    assert suggest.ownership_pct_to_regnr(50.01) == 560
    assert suggest.ownership_pct_to_regnr(83.51) == 560
    assert suggest.ownership_pct_to_regnr(100.0) == 560

    # Tilknyttet (20-50%): betydelig innflytelse — 50% nøyaktig er tilknyttet, ikke datter
    assert suggest.ownership_pct_to_regnr(50.0) == 575  # Boundary case: 50% er tilknyttet
    assert suggest.ownership_pct_to_regnr(49.99) == 575
    assert suggest.ownership_pct_to_regnr(20.0) == 575
    assert suggest.ownership_pct_to_regnr(30.0) == 575

    # Aksjer/andeler (<20%)
    assert suggest.ownership_pct_to_regnr(19.99) == 585
    assert suggest.ownership_pct_to_regnr(4.63) == 585
    assert suggest.ownership_pct_to_regnr(0.0) == 585


def test_ar_target_overrides_historikk_when_they_differ() -> None:
    """AR-eierskap skal slå historikk når de peker på forskjellige RL.

    Case: konto 1321 «Aksjer i GPC». Historikk fra fjoråret peker på 575
    (feil-mappet i fjor), men AR sier klienten eier «Gardermoen Perishable
    Center AS» med 84 % → datter → 560. Suggesteren skal foreslå 560,
    ikke videreføre historikk-feilen.
    """
    rl_df = pd.DataFrame(
        {
            "nr": [560, 575],
            "regnskapslinje": [
                "Investering i datterselskap",
                "Investeringer i tilknyttet selskap",
            ],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )
    owned = [
        suggest.OwnedCompany(
            name="Gardermoen Perishable Center AS",
            acronym="GPC",
            ownership_pct=84.0,
            suggested_regnr=560,
        )
    ]
    rulebook = {
        "rules": {
            "560": {"aliases": ["aksjer", "datter"]},
            "575": {"aliases": ["aksjer", "tilknyttet"]},
        }
    }

    suggestion = suggest.suggest_regnskapslinje(
        konto="1321",
        kontonavn="Aksjer i GPC",
        regnskapslinjer=rl_df,
        rulebook_document=rulebook,
        historical_regnr=575,
        owned_companies=owned,
    )

    assert suggestion is not None
    assert suggestion.regnr == 560
    assert "akronym" in suggestion.reason
    assert "historikk" not in suggestion.reason


def test_suggest_top_n_returns_ranked_list() -> None:
    """Topp-N-funksjonen skal returnere flere kandidater rangert på score."""
    rl_df = pd.DataFrame(
        {
            "nr": [560, 575, 585],
            "regnskapslinje": [
                "Investering i datterselskap",
                "Investeringer i tilknyttet selskap",
                "Investeringer i aksjer og andeler",
            ],
            "sumpost": ["nei", "nei", "nei"],
            "Formel": ["", "", ""],
        }
    )
    rulebook = {
        "rules": {
            "560": {"aliases": ["aksjer", "datter"], "account_ranges": ["1300-1369"]},
            "575": {"aliases": ["aksjer", "tilknyttet"], "account_ranges": ["1300-1369"]},
            "585": {"aliases": ["aksjer", "andeler"], "account_ranges": ["1300-1369"]},
        }
    }

    top = suggest.suggest_top_n_regnskapslinje(
        n=5,
        konto="1320",
        kontonavn="Aksjer i datter AS",
        regnskapslinjer=rl_df,
        rulebook_document=rulebook,
    )

    assert len(top) >= 2
    # Sortert høyest først
    assert all(top[i].confidence >= top[i + 1].confidence for i in range(len(top) - 1))
    # Datter vinner over de andre på "datter"-alias-treff
    assert top[0].regnr == 560


def test_suggest_top_n_respects_limit() -> None:
    """N-parameteren skal begrense lengden på resultatet."""
    rl_df = pd.DataFrame(
        {
            "nr": [10, 20, 30, 40],
            "regnskapslinje": ["A", "B", "C", "D"],
            "sumpost": ["nei", "nei", "nei", "nei"],
            "Formel": ["", "", "", ""],
        }
    )
    rulebook = {
        "rules": {
            str(n): {"aliases": ["test", "konto"], "account_ranges": ["1000-1099"]}
            for n in (10, 20, 30, 40)
        }
    }

    top = suggest.suggest_top_n_regnskapslinje(
        n=2,
        konto="1050",
        kontonavn="Test konto",
        regnskapslinjer=rl_df,
        rulebook_document=rulebook,
    )

    assert len(top) <= 2


def test_historikk_still_wins_when_ar_agrees_or_silent() -> None:
    """Historikk skal *ikke* undertrykkes hvis AR peker på samme RL eller
    ikke gir noe utsagn. Sikrer at vi ikke regrederer det generelle
    historikk-tilfellet."""
    rl_df = pd.DataFrame(
        {
            "nr": [560, 575],
            "regnskapslinje": [
                "Investering i datterselskap",
                "Investeringer i tilknyttet selskap",
            ],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )
    rulebook = {"rules": {"560": {"aliases": ["aksjer"]}, "575": {"aliases": ["aksjer"]}}}

    # AR-data finnes men matcher ikke navnet → ingen ar_target → historikk gjelder
    owned_no_match = [
        suggest.OwnedCompany(
            name="Helt Annet Selskap AS",
            acronym="HAS",
            ownership_pct=84.0,
            suggested_regnr=560,
        )
    ]
    suggestion = suggest.suggest_regnskapslinje(
        konto="1321",
        kontonavn="Aksjer i ukjent firma",
        regnskapslinjer=rl_df,
        rulebook_document=rulebook,
        historical_regnr=575,
        owned_companies=owned_no_match,
    )
    assert suggestion is not None
    assert suggestion.regnr == 575  # historikk vinner
