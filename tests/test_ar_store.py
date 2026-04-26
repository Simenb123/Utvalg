from __future__ import annotations

from types import SimpleNamespace


def _write_registry_csv(path) -> None:
    path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "914305195;AIR CARGO LOGISTICS AS;AIR MANAGEMENT AS;927612011;1000;1000",
                "916574657;BAGID AS;AIR MANAGEMENT AS;927612011;10;100",
                "916574657;BAGID AS;AIR MANAGEMENT AS;927612011;15;100",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT HOLDING AS;999999999;100;100",
            ]
        ),
        encoding="utf-8",
    )


def _configure_client_matching(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store
    import src.shared.client_store.meta_index as client_meta_index

    client_meta = {
        "Air Management AS": {"org_number": "927612011"},
        "Air Cargo Logistics AS": {"org_number": "914305195"},
        "Bagid AS": {"org_number": "916574657"},
    }

    monkeypatch.setattr(ar_store.app_paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(
        ar_store.client_store,
        "years_dir",
        lambda client, *, year: tmp_path / "clients" / client / "years" / year,
    )
    monkeypatch.setattr(
        ar_store.client_store,
        "read_client_meta",
        lambda client: dict(client_meta.get(client, {})),
    )
    monkeypatch.setattr(ar_store.client_store, "list_clients", lambda: list(client_meta))
    monkeypatch.setattr(
        client_meta_index,
        "get_index",
        lambda: {name: dict(meta) for name, meta in client_meta.items()},
    )
    monkeypatch.setattr(
        ar_store.client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: (
            SimpleNamespace(path="dummy.xlsx", filename="dummy.xlsx")
            if display_name == "Air Cargo Logistics AS" and year == "2024" and dtype == "sb"
            else None
        ),
    )


def test_import_registry_csv_and_get_client_ownership_overview(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store
    from src.pages.ar.backend.store import ManualOwnedChange

    _configure_client_matching(monkeypatch, tmp_path)
    csv_path = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_path)

    meta = ar_store.import_registry_csv(csv_path, year="2024")

    assert meta["year"] == "2024"
    assert meta["rows_read"] == 4
    assert meta["relations_count"] == 3

    ar_store.upsert_manual_owned_change(
        "Air Management AS",
        "2024",
        ManualOwnedChange(
            company_name="BAGID AS",
            company_orgnr="916574657",
            ownership_pct=25.0,
            relation_type="tilknyttet",
            note="Manuell oppdatering etter emisjon",
        ),
    )

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")
    owned = overview["owned_companies"]
    owners = overview["owners"]

    assert overview["client_orgnr"] == "927612011"
    assert len(owned) == 2
    assert len(owners) == 1
    assert overview["accepted_meta"]["source_kind"] == "register_baseline"

    air_cargo = next(row for row in owned if row["company_orgnr"] == "914305195")
    assert air_cargo["matched_client"] == "Air Cargo Logistics AS"
    assert air_cargo["has_active_sb"] is True
    assert air_cargo["relation_type"] == "datter"
    assert air_cargo["source"] == "accepted_register"

    bagid = next(row for row in owned if row["company_orgnr"] == "916574657")
    assert bagid["ownership_pct"] == 25.0
    assert bagid["relation_type"] == "tilknyttet"
    assert bagid["source"] == "manual_override"
    assert bagid["note"] == "Manuell oppdatering etter emisjon"
    assert bagid["matched_client"] == "Bagid AS"
    assert bagid["has_active_sb"] is False

    owner = owners[0]
    assert owner["shareholder_name"] == "AIR MANAGEMENT HOLDING AS"
    assert owner["shareholder_orgnr"] == "999999999"


def test_classify_relation_type_boundaries() -> None:
    import src.pages.ar.backend.store as ar_store

    assert ar_store.classify_relation_type(60.0) == "datter"
    assert ar_store.classify_relation_type(50.0) == "vurder"
    assert ar_store.classify_relation_type(20.0) == "tilknyttet"
    assert ar_store.classify_relation_type(19.99) == "investering"


def test_list_company_owners_with_fallback_uses_latest_company_year(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    monkeypatch.setattr(ar_store, "list_imported_years", lambda: ["2023", "2024", "2025"])

    def fake_list_company_owners(company_orgnr, year):
        if company_orgnr == "834108682" and year == "2024":
            return [
                {"shareholder_orgnr": "914601819", "shareholder_name": "JOZANI HOLDING AS"},
                {"shareholder_orgnr": "922294941", "shareholder_name": "RISTO AS"},
                {"shareholder_orgnr": "914601827", "shareholder_name": "THE PURCHASING GROUP AS"},
            ]
        return []

    monkeypatch.setattr(ar_store, "list_company_owners", fake_list_company_owners)

    used_year, rows = ar_store.list_company_owners_with_fallback("834108682", "2025")

    assert used_year == "2024"
    assert {r["shareholder_orgnr"] for r in rows} == {
        "914601819",
        "922294941",
        "914601827",
    }


def test_carry_forward_and_accept_register_changes(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    csv_2024 = tmp_path / "aksjeeiebok__2024.csv"
    _write_registry_csv(csv_2024)
    ar_store.import_registry_csv(csv_2024, year="2024")

    overview_2025 = ar_store.get_client_ownership_overview("Air Management AS", "2025")
    assert overview_2025["accepted_meta"]["source_kind"] == "carry_forward"
    assert overview_2025["accepted_meta"]["source_year"] == "2024"
    carried_air_cargo = next(row for row in overview_2025["owned_companies"] if row["company_orgnr"] == "914305195")
    assert carried_air_cargo["source"] == "carry_forward"
    assert overview_2025["owners_year_used"] == "2024"

    csv_2025 = tmp_path / "aksjeeiebok__2025.csv"
    csv_2025.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "914305195;AIR CARGO LOGISTICS AS;AIR MANAGEMENT AS;927612011;1000;1000",
                "916574657;BAGID AS;AIR MANAGEMENT AS;927612011;35;100",
                "918038035;LIVE SEAFOOD CENTER AS;AIR MANAGEMENT AS;927612011;550;1100",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT HOLDING AS;999999999;100;100",
            ]
        ),
        encoding="utf-8",
    )
    ar_store.import_registry_csv(csv_2025, year="2025")

    changed = ar_store.get_client_ownership_overview("Air Management AS", "2025")
    pending = changed["pending_changes"]
    assert len(pending) == 2
    assert {item["change_type"] for item in pending} == {"changed", "added"}
    assert next(row for row in changed["owned_companies"] if row["company_orgnr"] == "916574657")["ownership_pct"] == 25.0

    ar_store.accept_pending_ownership_changes("Air Management AS", "2025")

    accepted = ar_store.get_client_ownership_overview("Air Management AS", "2025")
    assert accepted["accepted_meta"]["source_kind"] == "accepted_update"
    assert accepted["pending_changes"] == []
    bagid = next(row for row in accepted["owned_companies"] if row["company_orgnr"] == "916574657")
    assert bagid["ownership_pct"] == 35.0
    live = next(row for row in accepted["owned_companies"] if row["company_orgnr"] == "918038035")
    assert live["relation_type"] == "vurder"


def test_self_owned_shares_are_shown_separately(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    csv_path = tmp_path / "aksjeeiebok__2024_self.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT AS;927612011;40;100",
                "914305195;AIR CARGO LOGISTICS AS;AIR MANAGEMENT AS;927612011;1000;1000",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT HOLDING AS;999999999;60;100",
            ]
        ),
        encoding="utf-8",
    )
    ar_store.import_registry_csv(csv_path, year="2024")

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")

    assert [row["company_orgnr"] for row in overview["owned_companies"]] == ["914305195"]
    assert [row["shareholder_orgnr"] for row in overview["owners"]] == ["999999999"]
    assert overview["self_ownership"]["ownership_pct"] == 40.0
    assert overview["self_ownership"]["shares"] == 40
    assert overview["self_ownership"]["total_shares"] == 100


def test_get_client_orgnr_falls_back_to_saved_regnskap_preferences(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    monkeypatch.setattr(ar_store.client_store, "read_client_meta", lambda client: {})
    monkeypatch.setattr(
        ar_store.preferences,
        "get",
        lambda key, default=None, client=None: (
            '{"orgnr": "927612011", "navn": "AIR MANAGEMENT AS"}'
            if key == "regnskap.noter.Air_Management_AS.__meta__.klientdata"
            else default
        ),
    )

    assert ar_store.get_client_orgnr("Air Management AS") == "927612011"


def test_find_client_by_orgnr_uses_local_index_without_client_scan(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    monkeypatch.setattr(
        ar_store.client_store,
        "list_clients",
        lambda: (_ for _ in ()).throw(AssertionError("should not scan clients when local index exists")),
    )

    assert ar_store.find_client_by_orgnr("914305195") == "Air Cargo Logistics AS"


def test_detect_circular_ownership_finds_cycle(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    csv_path = tmp_path / "circular.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "111111111;A AS;B AS;222222222;50;100",
                "222222222;B AS;C AS;333333333;60;100",
                "333333333;C AS;A AS;111111111;40;100",
            ]
        ),
        encoding="utf-8",
    )
    ar_store.import_registry_csv(csv_path, year="2024")

    cycles = ar_store.detect_circular_ownership("2024")
    assert len(cycles) >= 1
    # The cycle should contain all three orgnrs
    cycle_set = set(cycles[0])
    assert {"111111111", "222222222", "333333333"}.issubset(cycle_set)


def test_detect_circular_ownership_no_cycle(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    csv_path = tmp_path / "linear.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "111111111;A AS;B AS;222222222;50;100",
                "222222222;B AS;C AS;333333333;60;100",
            ]
        ),
        encoding="utf-8",
    )
    ar_store.import_registry_csv(csv_path, year="2024")

    cycles = ar_store.detect_circular_ownership("2024")
    assert len(cycles) == 0


def _make_rf1086_parse_result(
    *,
    orgnr: str,
    year: str,
    shareholders: list[tuple[str, str, str, int, int, list[tuple[str, str, int, str, float]]]],
):
    """Build a ParseResult for RF-1086 tests.

    Each shareholder tuple: (id, name, kind, shares_start, shares_end, transactions)
    transaction tuple: (direction, type, shares, date, amount)
    """
    from src.pages.ar.backend.pdf_parser import (
        CompanyHeader, ParseResult, ShareholderRecord, Transaction,
    )

    total_start = sum(s[3] for s in shareholders)
    total_end = sum(s[4] for s in shareholders)
    header = CompanyHeader(
        company_orgnr=orgnr,
        company_name=f"Testselskap {orgnr}",
        antall_aksjer_start=total_start,
        antall_aksjer_end=total_end,
        year=year,
    )
    sh_records = []
    for sid, name, kind, s_start, s_end, txs in shareholders:
        sh_records.append(ShareholderRecord(
            shareholder_id=sid, shareholder_name=name, shareholder_kind=kind,
            shares_start=s_start, shares_end=s_end, page_number=1,
            transactions=[
                Transaction(direction=d, trans_type=tt, shares=sh, date=dt, amount=amt)
                for d, tt, sh, dt, amt in txs
            ],
        ))
    return ParseResult(header=header, shareholders=sh_records)


def test_rf1086_import_writes_history_and_compare(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    client = "Air Cargo Logistics AS"
    orgnr = "914305195"
    src_pdf = tmp_path / "rf1086_2024.pdf"
    src_pdf.write_bytes(b"%PDF-1.4\n% dummy payload\n")

    # Base year 2024: single shareholder with 1000 shares, no transactions
    pr_2024 = _make_rf1086_parse_result(
        orgnr=orgnr, year="2024",
        shareholders=[("111111111", "Eier AS", "company", 1000, 1000, [])],
    )
    meta_2024 = ar_store.import_registry_pdf(
        pr_2024, year="2024", source_file="rf1086_2024.pdf",
        client=client, source_path=src_pdf,
    )
    assert meta_2024["import_id"]

    # Current year 2025: 900 shares + new shareholder 100 (via tx)
    pr_2025 = _make_rf1086_parse_result(
        orgnr=orgnr, year="2025",
        shareholders=[
            ("111111111", "Eier AS", "company", 1000, 900, [
                ("avgang", "Salg", 100, "01.06.2025", 500000.0),
            ]),
            ("222222222", "Ny Eier AS", "company", 0, 100, [
                ("tilgang", "Kjøp", 100, "01.06.2025", 500000.0),
            ]),
        ],
    )
    meta_2025 = ar_store.import_registry_pdf(
        pr_2025, year="2025", source_file="rf1086_2025.pdf",
        client=client, source_path=src_pdf,
    )
    assert meta_2025["import_id"]

    # Verify managed-copy target exists
    assert meta_2025["stored_file_path"]
    from pathlib import Path as _P
    assert _P(meta_2025["stored_file_path"]).exists()

    # List_company_imports should return both
    imports = ar_store.list_company_imports(client=client, company_orgnr=orgnr)
    assert len(imports) == 2
    years = {row["register_year"] for row in imports}
    assert years == {"2024", "2025"}

    # Overview for 2025 should carry compare + history
    overview = ar_store.get_client_ownership_overview(client, "2025")
    assert overview.get("owners_current_year_used") == "2025"
    assert overview.get("owners_base_year_used") == "2024"
    compare = overview.get("owners_compare") or []
    assert compare, "owners_compare should be populated"
    by_orgnr = {r["shareholder_orgnr"]: r for r in compare}
    assert "111111111" in by_orgnr
    assert by_orgnr["111111111"]["change_type"] == "changed"
    assert by_orgnr["111111111"]["shares_delta"] == -100
    assert by_orgnr["111111111"]["shares_sold"] == 100
    assert "222222222" in by_orgnr
    assert by_orgnr["222222222"]["change_type"] == "new"
    assert by_orgnr["222222222"]["shares_bought"] == 100

    history = overview.get("import_history") or []
    assert len(history) >= 2

    # Trace detail for existing shareholder
    trace = ar_store.get_shareholder_trace_detail(client, "2025", "org:111111111")
    assert trace.get("transactions"), "trace transactions should be present"
    assert trace["transactions"][0]["shares"] == 100


def test_rf1086_import_reimport_is_idempotent(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure_client_matching(monkeypatch, tmp_path)

    client = "Air Cargo Logistics AS"
    orgnr = "914305195"
    src_pdf = tmp_path / "rf1086_2024.pdf"
    src_pdf.write_bytes(b"%PDF-1.4\n")

    pr = _make_rf1086_parse_result(
        orgnr=orgnr, year="2024",
        shareholders=[("111111111", "Eier AS", "company", 500, 500, [])],
    )
    ar_store.import_registry_pdf(
        pr, year="2024", source_file="a.pdf",
        client=client, source_path=src_pdf,
    )
    # Second import for same year — must not raise PK violation
    ar_store.import_registry_pdf(
        pr, year="2024", source_file="b.pdf",
        client=client, source_path=src_pdf,
    )
    imports = ar_store.list_company_imports(client=client, company_orgnr=orgnr)
    assert len(imports) == 2  # two distinct import_ids, same register_year
