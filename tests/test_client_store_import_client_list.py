from __future__ import annotations

from pathlib import Path

import pytest


def test_import_clients_from_csv_creates_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isoler data-dir for testen
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store
    import client_store_import

    csv_path = tmp_path / "clients.csv"
    csv_path.write_text(
        "Klient\nDemo AS\nDemo AS\n  Alfa AS  \n\nBeta AS\n",
        encoding="utf-8",
    )

    stats = client_store_import.import_clients_from_file(csv_path)
    # read_client_names_from_file returnerer unike navn i rekkefølge
    assert stats["found"] == 3
    assert stats["created"] == 3

    clients = client_store.list_clients()
    assert set(c.lower() for c in clients) >= {"demo as", "alfa as", "beta as"}


def test_import_clients_raises_when_file_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store_import

    with pytest.raises(Exception):
        client_store_import.import_clients_from_file(tmp_path / "missing.xlsx")


def test_import_clients_does_not_call_ensure_for_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Importer skal ikke prøve å ensure_client() for navn som allerede finnes.

    Dette er viktig for ytelse (store lister) og for å unngå at GUI oppleves som
    "hengt" på nytt ved re-import.
    """

    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store
    import client_store_import

    # Sett opp en eksisterende klient
    client_store.ensure_client("Eksisterende AS")

    csv_path = tmp_path / "clients.csv"
    csv_path.write_text("Klient\nEksisterende AS\n", encoding="utf-8")

    # Hvis ensure_client blir kalt under import nå, er det en regresjon.
    def _boom(_name: str):
        raise RuntimeError("ensure_client skal ikke kalles for eksisterende klient")

    monkeypatch.setattr(client_store, "ensure_client", _boom)

    stats = client_store_import.import_clients_from_file(csv_path)
    assert stats["found"] == 1
    assert stats["created"] == 0
