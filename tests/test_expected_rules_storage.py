from __future__ import annotations


def test_roundtrip_mixed_account_modes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    from motpost.expected_rules import (
        ExpectedRule,
        ExpectedRuleSet,
        load_rule_set,
        save_rule_set,
    )

    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="alle",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(
                target_regnr=790,
                account_mode="selected",
                allowed_accounts=("2740", "2770"),
                requires_netting=True,
                netting_tolerance=2.5,
            ),
        ),
    )
    save_rule_set("Nbs Regnskap AS", rule_set)

    loaded = load_rule_set(
        "Nbs Regnskap AS", source_regnr=10, selected_direction="alle"
    )
    assert loaded.source_regnr == 10
    assert loaded.selected_direction == "alle"
    assert len(loaded.rules) == 2
    assert loaded.rules[0] == ExpectedRule(target_regnr=610, account_mode="all")
    assert loaded.rules[1] == ExpectedRule(
        target_regnr=790,
        account_mode="selected",
        allowed_accounts=("2740", "2770"),
        requires_netting=True,
        netting_tolerance=2.5,
    )


def test_empty_rule_set_returned_for_missing_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    from motpost.expected_rules import load_rule_set

    loaded = load_rule_set("Ikke-lagret", source_regnr=10)
    assert loaded.source_regnr == 10
    assert loaded.selected_direction == "alle"
    assert loaded.rules == ()
    assert loaded.is_empty()


def test_direction_normalized_on_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    from motpost.expected_rules import (
        ExpectedRule,
        ExpectedRuleSet,
        load_rule_set,
        save_rule_set,
    )

    rule_set = ExpectedRuleSet(
        source_regnr=20,
        selected_direction="Debet",  # rå form, skal normaliseres
        rules=(ExpectedRule(target_regnr=40),),
    )
    save_rule_set("Testklient", rule_set)

    # Lastes med case-insensitive retning
    loaded = load_rule_set("Testklient", source_regnr=20, selected_direction="debet")
    assert loaded.selected_direction == "debet"
    assert len(loaded.rules) == 1


def test_remove_rule_set_drops_preset(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    from motpost.expected_rules import (
        ExpectedRule,
        ExpectedRuleSet,
        load_rule_set,
        remove_rule_set,
        save_rule_set,
    )

    save_rule_set(
        "Testklient",
        ExpectedRuleSet(
            source_regnr=10,
            selected_direction="alle",
            rules=(ExpectedRule(target_regnr=610),),
        ),
    )
    remove_rule_set("Testklient", source_regnr=10, selected_direction="alle")
    loaded = load_rule_set("Testklient", source_regnr=10, selected_direction="alle")
    assert loaded.is_empty()


def test_invalid_rule_entries_are_skipped(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides
    from motpost.expected_rules import load_rule_set

    regnskap_client_overrides.save_expected_motpost_rules(
        "Testklient",
        source_regnr=10,
        selected_direction="alle",
        payload={
            "version": 2,
            "rules": [
                {"target_regnr": 610, "account_mode": "all", "allowed_accounts": []},
                {"target_regnr": "not-a-number"},
                "string-in-list",
                {"target_regnr": 790, "account_mode": "unknown"},
            ],
        },
    )
    loaded = load_rule_set("Testklient", source_regnr=10, selected_direction="alle")
    assert len(loaded.rules) == 2
    assert loaded.rules[0].target_regnr == 610
    # Ugyldig account_mode faller tilbake til "all"
    assert loaded.rules[1].target_regnr == 790
    assert loaded.rules[1].account_mode == "all"


def test_roundtrip_excluded_accounts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    from motpost.expected_rules import (
        ExpectedRule,
        ExpectedRuleSet,
        load_rule_set,
        save_rule_set,
    )

    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="alle",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="all",
                excluded_accounts=("1520", "1530"),
            ),
        ),
    )
    save_rule_set("Testklient", rule_set)
    loaded = load_rule_set("Testklient", source_regnr=10, selected_direction="alle")
    assert len(loaded.rules) == 1
    assert loaded.rules[0].account_mode == "all"
    assert loaded.rules[0].excluded_accounts == ("1520", "1530")


def test_account_overrides_and_motpost_rules_preserve_each_other(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides
    from motpost.expected_rules import (
        ExpectedRule,
        ExpectedRuleSet,
        load_rule_set,
        save_rule_set,
    )

    regnskap_client_overrides.save_account_overrides("Testklient", {"9999": 42})
    save_rule_set(
        "Testklient",
        ExpectedRuleSet(
            source_regnr=10,
            selected_direction="kredit",
            rules=(ExpectedRule(target_regnr=610),),
        ),
    )

    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"9999": 42}
    loaded = load_rule_set(
        "Testklient", source_regnr=10, selected_direction="kredit"
    )
    assert len(loaded.rules) == 1
    assert loaded.rules[0].target_regnr == 610
