from __future__ import annotations

from types import SimpleNamespace


def _write_registry_csv(path) -> None:
    path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT HOLDING AS;999999999;70;100",
                "927612011;AIR MANAGEMENT AS;OLA NORDMANN;01021980123;30;100",
            ]
        ),
        encoding="utf-8",
    )


def _write_registry_csv_updated(path) -> None:
    path.write_text(
        "\n".join(
            [
                "Orgnr;Selskap;Navn aksjonær;Fødselsår/orgnr;Antall aksjer;Antall aksjer selskap",
                "927612011;AIR MANAGEMENT AS;AIR MANAGEMENT HOLDING AS;999999999;60;100",
                "927612011;AIR MANAGEMENT AS;OLA NORDMANN;01021980123;40;100",
            ]
        ),
        encoding="utf-8",
    )


def _configure(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store
    import client_meta_index

    client_meta = {
        "Air Management AS": {"org_number": "927612011"},
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
        lambda display_name, *, year, dtype: None,
    )


def test_manual_owner_change_roundtrip(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    change = ar_store.ManualOwnerChange(
        shareholder_name="NY EIER AS",
        shareholder_orgnr="111111111",
        shareholder_kind="company",
        shares=50,
        total_shares=100,
        ownership_pct=50.0,
        note="Test",
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2024", change)

    loaded = ar_store.load_manual_owner_changes("Air Management AS", "2024")
    assert len(loaded) == 1
    assert loaded[0].shareholder_orgnr == "111111111"
    assert loaded[0].op == ar_store.MANUAL_OWNER_OP_UPSERT

    ar_store.delete_manual_owner_change(
        "Air Management AS", "2024", loaded[0].change_id
    )
    assert ar_store.load_manual_owner_changes("Air Management AS", "2024") == []


def test_merge_owners_upsert_wins(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    register_rows = [
        {
            "shareholder_name": "OLA NORDMANN",
            "shareholder_orgnr": "",
            "shares": 30,
            "total_shares": 100,
            "ownership_pct": 30.0,
            "shareholder_kind": "person",
        },
    ]
    change = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shareholder_kind="person",
        shares=45,
        total_shares=100,
        ownership_pct=45.0,
    )
    merged = ar_store._merge_owners(register_rows, [change])
    assert len(merged) == 1
    assert merged[0]["shares"] == 45
    assert merged[0]["source"] == "manual_override"
    assert merged[0]["manual_change_id"] == change.change_id


def test_merge_owners_remove_filters_register(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    register_rows = [
        {
            "shareholder_name": "OLA NORDMANN",
            "shareholder_orgnr": "",
            "shares": 30,
            "total_shares": 100,
            "ownership_pct": 30.0,
        },
        {
            "shareholder_name": "AIR HOLDING AS",
            "shareholder_orgnr": "999999999",
            "shares": 70,
            "total_shares": 100,
            "ownership_pct": 70.0,
        },
    ]
    change = ar_store.ManualOwnerChange(
        op=ar_store.MANUAL_OWNER_OP_REMOVE,
        shareholder_name="OLA NORDMANN",
    )
    merged = ar_store._merge_owners(register_rows, [change])
    assert [r["shareholder_name"] for r in merged] == ["AIR HOLDING AS"]


def test_merge_owners_new_manual_without_register(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    change = ar_store.ManualOwnerChange(
        shareholder_name="Nytt Selskap AS",
        shareholder_orgnr="222222222",
        shareholder_kind="company",
        shares=10,
        total_shares=100,
        ownership_pct=10.0,
    )
    merged = ar_store._merge_owners([], [change])
    assert len(merged) == 1
    assert merged[0]["source"] == "manual"
    assert merged[0]["manual_change_id"] == change.change_id


def test_build_pending_owner_changes_overwrite_and_restore() -> None:
    import src.pages.ar.backend.store as ar_store

    upsert = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shares=45,
        total_shares=100,
        ownership_pct=45.0,
    )
    removed = ar_store.ManualOwnerChange(
        op=ar_store.MANUAL_OWNER_OP_REMOVE,
        shareholder_name="KARI NORDMANN",
    )
    candidate_rows = [
        {
            "shareholder_name": "OLA NORDMANN",
            "shareholder_orgnr": "",
            "shares": 40,
            "total_shares": 100,
            "ownership_pct": 40.0,
        },
        {
            "shareholder_name": "KARI NORDMANN",
            "shareholder_orgnr": "",
            "shares": 10,
            "total_shares": 100,
            "ownership_pct": 10.0,
        },
    ]
    pending = ar_store.build_pending_owner_changes([upsert, removed], candidate_rows)
    types = {r["change_type"] for r in pending}
    assert types == {"owner_overwrite", "owner_restored"}
    assert all(r["kind"] == "owner" for r in pending)
    assert all(r["manual_change_id"] for r in pending)


def test_build_pending_owner_changes_skips_when_match() -> None:
    import src.pages.ar.backend.store as ar_store

    change = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shares=40,
        total_shares=100,
        ownership_pct=40.0,
    )
    candidate_rows = [
        {
            "shareholder_name": "OLA NORDMANN",
            "shareholder_orgnr": "",
            "shares": 40,
            "total_shares": 100,
            "ownership_pct": 40.0,
        },
    ]
    assert ar_store.build_pending_owner_changes([change], candidate_rows) == []


def test_accept_pending_owner_changes_deletes_manual(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    c1 = ar_store.ManualOwnerChange(shareholder_name="A")
    c2 = ar_store.ManualOwnerChange(shareholder_name="B")
    ar_store.save_manual_owner_changes("Air Management AS", "2024", [c1, c2])
    removed = ar_store.accept_pending_owner_changes(
        "Air Management AS", "2024", [c1.change_id]
    )
    assert [c.change_id for c in removed] == [c1.change_id]
    remaining = ar_store.load_manual_owner_changes("Air Management AS", "2024")
    assert [c.change_id for c in remaining] == [c2.change_id]


def test_accept_all_owner_changes(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    c1 = ar_store.ManualOwnerChange(shareholder_name="A")
    c2 = ar_store.ManualOwnerChange(shareholder_name="B")
    ar_store.save_manual_owner_changes("Air Management AS", "2024", [c1, c2])
    ar_store.accept_pending_owner_changes("Air Management AS", "2024", None)
    assert ar_store.load_manual_owner_changes("Air Management AS", "2024") == []


def test_overview_reports_manual_owner_override(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    csv_path = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_path)
    ar_store.import_registry_csv(csv_path, year="2024")

    change = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shareholder_kind="person",
        shares=45,
        total_shares=100,
        ownership_pct=45.0,
        note="Etter emisjon",
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2024", change)
    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")

    owners = overview["owners"]
    ola = next(o for o in owners if o["shareholder_name"].upper() == "OLA NORDMANN")
    assert ola["shares"] == 45
    assert ola["source"] == "manual_override"
    assert ola["manual_change_id"] == change.change_id

    compare = overview["owners_compare"]
    ola_cmp = next(r for r in compare if r["shareholder_name"].upper() == "OLA NORDMANN")
    assert ola_cmp["manual_change_id"] == change.change_id

    # Manual override (45) differs from register (30) → surfaces as pending
    pending = overview["pending_owner_changes"]
    assert len(pending) == 1
    assert pending[0]["change_type"] == "owner_overwrite"
    assert pending[0]["manual_change_id"] == change.change_id


def test_overview_surfaces_pending_on_register_conflict(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    csv_2024 = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_2024)
    ar_store.import_registry_csv(csv_2024, year="2024")

    change = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shares=30,
        total_shares=100,
        ownership_pct=30.0,
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2024", change)

    csv_2024_v2 = tmp_path / "aksjeeiebok__2024_v2.csv"
    _write_registry_csv_updated(csv_2024_v2)
    ar_store.import_registry_csv(csv_2024_v2, year="2024")

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")
    pending_owner = overview["pending_owner_changes"]
    assert any(p["change_type"] == "owner_overwrite" for p in pending_owner)

    ar_store.accept_pending_owner_changes(
        "Air Management AS", "2024", [change.change_id]
    )
    overview2 = ar_store.get_client_ownership_overview("Air Management AS", "2024")
    assert overview2["pending_owner_changes"] == []
    ola = next(
        o for o in overview2["owners"]
        if o["shareholder_name"].upper() == "OLA NORDMANN"
    )
    assert ola["shares"] == 40
    assert ola["source"] == "register"


def test_hidden_owner_surfaces_in_compare(monkeypatch, tmp_path) -> None:
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    csv_path = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_path)
    ar_store.import_registry_csv(csv_path, year="2024")

    removal = ar_store.ManualOwnerChange(
        op=ar_store.MANUAL_OWNER_OP_REMOVE,
        shareholder_name="OLA NORDMANN",
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2024", removal)

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")
    owners = overview["owners"]
    assert all(o["shareholder_name"].upper() != "OLA NORDMANN" for o in owners)

    compare = overview["owners_compare"]
    hidden = [r for r in compare if r.get("change_type") == "hidden"]
    assert len(hidden) == 1
    assert hidden[0]["shareholder_name"].upper() == "OLA NORDMANN"
    assert hidden[0]["manual_change_id"] == removal.change_id
    assert hidden[0]["source"] == "manual_hidden"


def test_manual_owner_replaces_fallback_register(monkeypatch, tmp_path) -> None:
    """Når target_year mangler eget register og brukeren har lagt inn manuelle
    eiere, skal disse representere hele eierbildet for target_year. Fallback-
    registeret fra et tidligere år skal ikke lekke inn som 'nå-tall'."""
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    # Seed 2024-register med tre eiere (AIR MANAGEMENT HOLDING + OLA NORDMANN)
    csv_path = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_path)
    ar_store.import_registry_csv(csv_path, year="2024")

    # Bruker er på 2025 (ingen 2025-register) og registrerer én manuell eier.
    change = ar_store.ManualOwnerChange(
        shareholder_name="ATARIS HOLDING",
        shareholder_orgnr="915321445",
        shareholder_kind="company",
        shares=100,
        total_shares=100,
        ownership_pct=100.0,
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2025", change)

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2025")

    # owners skal KUN inneholde manuelt lagrede eiere (ikke fallback fra 2024).
    owners = overview["owners"]
    names = {o["shareholder_name"].upper() for o in owners}
    assert names == {"ATARIS HOLDING"}
    assert owners[0]["source"] == "manual"
    # Current-år skal nå være target_year, ikke fallback-året.
    assert overview["owners_current_year_used"] == "2025"
    # Base-år skal være det gamle fallback-året (2024) for sammenligning.
    assert overview["owners_base_year_used"] == "2024"

    # Compare-viewet skal vise overgangen: tidligere eiere (removed) + ny (new).
    compare = overview["owners_compare"]
    types = {(r["shareholder_name"].upper(), r["change_type"]) for r in compare}
    assert ("ATARIS HOLDING", "new") in types
    assert ("AIR MANAGEMENT HOLDING AS", "removed") in types
    assert ("OLA NORDMANN", "removed") in types


def test_manual_owner_merges_with_target_year_register(monkeypatch, tmp_path) -> None:
    """Når target_year faktisk har eget register, skal manuelle oppføringer
    fortsatt merges inn som overstyringer (ikke erstatte hele registeret)."""
    import src.pages.ar.backend.store as ar_store

    _configure(monkeypatch, tmp_path)
    csv_path = tmp_path / "aksjeeiebok__2024_07052025.csv"
    _write_registry_csv(csv_path)
    ar_store.import_registry_csv(csv_path, year="2024")

    change = ar_store.ManualOwnerChange(
        shareholder_name="OLA NORDMANN",
        shareholder_orgnr="",
        shareholder_kind="person",
        shares=45,
        total_shares=100,
        ownership_pct=45.0,
    )
    ar_store.upsert_manual_owner_change("Air Management AS", "2024", change)

    overview = ar_store.get_client_ownership_overview("Air Management AS", "2024")
    owners = overview["owners"]
    names = {o["shareholder_name"].upper() for o in owners}
    # Registerets AIR MANAGEMENT HOLDING skal fortsatt være med.
    assert "AIR MANAGEMENT HOLDING AS" in names
    assert "OLA NORDMANN" in names
