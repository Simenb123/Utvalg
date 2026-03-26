from __future__ import annotations


def test_save_and_load_account_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_account_overrides("Nbs Regnskap AS", {"1500": 610, "3000": 10})
    loaded = regnskap_client_overrides.load_account_overrides("Nbs Regnskap AS")

    assert loaded == {"1500": 610, "3000": 10}


def test_set_and_remove_account_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.set_account_override("Testklient", "9999", 42)
    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"9999": 42}

    regnskap_client_overrides.remove_account_override("Testklient", "9999")
    assert regnskap_client_overrides.load_account_overrides("Testklient") == {}


def test_save_and_load_expected_regnskapslinjer_presets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_expected_regnskapslinjer(
        "Nbs Regnskap AS",
        scope_regnr=[10],
        expected_regnr=[610, 790],
        selected_direction="Kredit",
    )
    loaded = regnskap_client_overrides.load_expected_regnskapslinjer(
        "Nbs Regnskap AS",
        scope_regnr=[10],
        selected_direction="Kredit",
    )

    assert loaded == [610, 790]


def test_account_overrides_and_expected_presets_preserve_each_other(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_account_overrides("Testklient", {"9999": 42})
    regnskap_client_overrides.save_expected_regnskapslinjer(
        "Testklient",
        scope_regnr=[10, 19],
        expected_regnr=[610, 790],
        selected_direction="Kredit",
    )

    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"9999": 42}
    assert regnskap_client_overrides.load_expected_regnskapslinjer(
        "Testklient",
        scope_regnr=[19, 10],
        selected_direction="Kredit",
    ) == [610, 790]


def test_save_and_load_expected_regnskapslinje_rule_presets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_expected_regnskapslinje_rule(
        "Nbs Regnskap AS",
        scope_regnr=[20],
        require_netting=True,
        tolerance=1.0,
        selected_regnr=[20],
        selected_direction="Debet",
    )
    loaded = regnskap_client_overrides.load_expected_regnskapslinje_rule(
        "Nbs Regnskap AS",
        scope_regnr=[20],
        selected_direction="Debet",
    )

    assert loaded == {"require_netting": True, "tolerance": 1.0, "selected_regnr": [20]}


def test_save_and_load_column_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    mapping = {"Bilag": "Voucher No", "Konto": "Account", "Beløp": "Amount"}
    regnskap_client_overrides.save_column_mapping("Testklient", mapping)
    loaded = regnskap_client_overrides.load_column_mapping("Testklient")

    assert loaded == mapping


def test_column_mapping_preserves_other_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_account_overrides("Testklient", {"1500": 610})
    regnskap_client_overrides.save_column_mapping("Testklient", {"Bilag": "Doc No"})

    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"1500": 610}
    assert regnskap_client_overrides.load_column_mapping("Testklient") == {"Bilag": "Doc No"}


def test_load_column_mapping_empty_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    assert regnskap_client_overrides.load_column_mapping(None) == {}
    assert regnskap_client_overrides.load_column_mapping("") == {}


# ---- MVA-funksjoner ----


def test_save_and_load_accounting_system(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_accounting_system("Testklient", "Tripletex")
    loaded = regnskap_client_overrides.load_accounting_system("Testklient")

    assert loaded == "Tripletex"


def test_load_accounting_system_empty_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    assert regnskap_client_overrides.load_accounting_system(None) == ""
    assert regnskap_client_overrides.load_accounting_system("") == ""


def test_save_and_load_mva_code_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    mapping = {"1": "1", "3": "3", "99": "8"}
    regnskap_client_overrides.save_mva_code_mapping("Testklient", mapping)
    loaded = regnskap_client_overrides.load_mva_code_mapping("Testklient")

    assert loaded == mapping


def test_load_mva_code_mapping_empty_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    assert regnskap_client_overrides.load_mva_code_mapping(None) == {}
    assert regnskap_client_overrides.load_mva_code_mapping("") == {}


def test_mva_fields_preserve_other_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_account_overrides("Testklient", {"1500": 610})
    regnskap_client_overrides.save_accounting_system("Testklient", "PowerOffice GO")
    regnskap_client_overrides.save_mva_code_mapping("Testklient", {"1": "1", "11": "11"})

    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"1500": 610}
    assert regnskap_client_overrides.load_accounting_system("Testklient") == "PowerOffice GO"
    assert regnskap_client_overrides.load_mva_code_mapping("Testklient") == {"1": "1", "11": "11"}


def test_year_specific_overrides(tmp_path, monkeypatch) -> None:
    """Year-specific overrides take priority; fallback to year-agnostic."""
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    # Save year-agnostic (legacy)
    regnskap_client_overrides.save_account_overrides("Testklient", {"1500": 610})
    assert regnskap_client_overrides.load_account_overrides("Testklient") == {"1500": 610}

    # Without year, we get the legacy value
    assert regnskap_client_overrides.load_account_overrides("Testklient", year=None) == {"1500": 610}
    # With a year that has no year-specific overrides, we still get legacy
    assert regnskap_client_overrides.load_account_overrides("Testklient", year="2024") == {"1500": 610}

    # Save year-specific overrides for 2024
    regnskap_client_overrides.save_account_overrides(
        "Testklient", {"1500": 620, "3000": 10}, year="2024")

    # Year-specific now takes priority
    assert regnskap_client_overrides.load_account_overrides("Testklient", year="2024") == {"1500": 620, "3000": 10}
    # A different year still falls back to legacy (which was updated to match 2024's save)
    loaded_2023 = regnskap_client_overrides.load_account_overrides("Testklient", year="2023")
    # 2023 has no year-specific, falls back to account_overrides (updated by last save)
    assert loaded_2023 == {"1500": 620, "3000": 10}

    # Save 2023-specific
    regnskap_client_overrides.save_account_overrides(
        "Testklient", {"1500": 610}, year="2023")
    assert regnskap_client_overrides.load_account_overrides("Testklient", year="2023") == {"1500": 610}
    # 2024 still has its own
    assert regnskap_client_overrides.load_account_overrides("Testklient", year="2024") == {"1500": 620, "3000": 10}


def test_prior_year_overrides(tmp_path, monkeypatch) -> None:
    """load_prior_year_overrides returns previous year's overrides."""
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    # Save overrides for 2023
    regnskap_client_overrides.save_account_overrides(
        "Testklient", {"1500": 610}, year="2023")

    # Load prior year overrides for 2024 → should get 2023's
    prior = regnskap_client_overrides.load_prior_year_overrides("Testklient", "2024")
    assert prior == {"1500": 610}

    # No overrides for 2022 → empty
    prior_empty = regnskap_client_overrides.load_prior_year_overrides("Testklient", "2023")
    # 2022 has no year-specific, falls back to legacy (which is 2023's save)
    assert prior_empty == {"1500": 610}


def test_mva_code_mapping_cleans_input(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_client_overrides

    regnskap_client_overrides.save_mva_code_mapping("Testklient", {
        " 1 ": " 1 ",
        "": "5",    # tom nøkkel → ignorert
        "3": "",    # tom verdi → ignorert
    })
    loaded = regnskap_client_overrides.load_mva_code_mapping("Testklient")

    assert loaded == {"1": "1"}
