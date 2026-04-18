from __future__ import annotations

import importlib
from pathlib import Path

import pytest


class MiniVar:
    def __init__(self, value: str = "") -> None:
        self._v = value

    def get(self) -> str:
        return self._v

    def set(self, value: str) -> None:
        self._v = value


def test_refresh_sets_file_path_to_active_version_when_current_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    # Lag klient + aktiv versjon
    src = tmp_path / "hb.xlsx"
    src.write_text("dummy", encoding="utf-8")

    client_store.ensure_client("Demo AS")
    v = client_store.create_version(
        "Demo AS",
        year="2025",
        dtype="hb",
        src_path=src,
        make_active=True,
    )

    import dataset_pane_store

    importlib.reload(dataset_pane_store)

    chosen: list[str] = []

    def on_path_selected(p: str) -> None:
        chosen.append(p)

    def get_current_path() -> str:
        return ""  # Simuler at filfeltet er tomt ved oppstart

    sec = dataset_pane_store.ClientStoreSection(
        frame=None,  # type: ignore[arg-type]
        client_var=MiniVar("Demo AS"),
        year_var=MiniVar("2025"),
        hb_var=MiniVar(""),
        on_path_selected=on_path_selected,
        get_current_path=get_current_path,
    )

    sec.refresh()

    assert sec.hb_var.get() == v.id
    assert chosen, "refresh() skal velge aktiv versjonsfil når filfeltet er tomt"
    assert chosen[-1] == str(v.path)


def test_refresh_does_not_override_existing_valid_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    # Lag klient + aktiv versjon
    src = tmp_path / "hb.xlsx"
    src.write_text("dummy", encoding="utf-8")

    client_store.ensure_client("Demo AS")
    client_store.create_version(
        "Demo AS",
        year="2025",
        dtype="hb",
        src_path=src,
        make_active=True,
    )

    import dataset_pane_store

    importlib.reload(dataset_pane_store)

    existing = tmp_path / "existing.xlsx"
    existing.write_text("x", encoding="utf-8")

    chosen: list[str] = []

    def on_path_selected(p: str) -> None:
        chosen.append(p)

    def get_current_path() -> str:
        return str(existing)

    sec = dataset_pane_store.ClientStoreSection(
        frame=None,  # type: ignore[arg-type]
        client_var=MiniVar("Demo AS"),
        year_var=MiniVar("2025"),
        hb_var=MiniVar(""),
        on_path_selected=on_path_selected,
        get_current_path=get_current_path,
    )

    sec.refresh()

    assert chosen == [], "Eksisterende gyldig fil skal ikke overstyres"


def test_refresh_resets_hb_var_when_year_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresjon: når bruker bytter år skal Kildeversjon-dropdown oppdateres
    til det nye årets aktive versjon, selv om gammel verdi tilfeldigvis
    finnes i ny liste."""
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    src_2024 = tmp_path / "hb_2024.xlsx"
    src_2024.write_text("x", encoding="utf-8")
    src_2025 = tmp_path / "hb_2025.xlsx"
    src_2025.write_text("y", encoding="utf-8")

    client_store.ensure_client("Demo AS")
    v2024 = client_store.create_version(
        "Demo AS", year="2024", dtype="hb", src_path=src_2024, make_active=True,
    )
    v2025 = client_store.create_version(
        "Demo AS", year="2025", dtype="hb", src_path=src_2025, make_active=True,
    )
    assert v2024.id != v2025.id  # sanity

    import dataset_pane_store

    importlib.reload(dataset_pane_store)

    chosen: list[str] = []

    year_var = MiniVar("2025")
    hb_var = MiniVar("")

    def on_path_selected(p: str) -> None:
        chosen.append(p)

    def get_current_path() -> str:
        return chosen[-1] if chosen else ""

    sec = dataset_pane_store.ClientStoreSection(
        frame=None,  # type: ignore[arg-type]
        client_var=MiniVar("Demo AS"),
        year_var=year_var,
        hb_var=hb_var,
        on_path_selected=on_path_selected,
        get_current_path=get_current_path,
    )

    # Første refresh: låser inn 2025-versjonen
    sec.refresh()
    assert sec.hb_var.get() == v2025.id

    # Bytt år → ny refresh
    year_var.set("2024")
    sec.refresh()

    assert sec.hb_var.get() == v2024.id, (
        "hb_var må resette til nytt års aktive versjon ved år-bytte"
    )
