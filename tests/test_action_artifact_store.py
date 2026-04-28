"""Tester for action_artifact_store — manifest og kommentarer per handling."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.audit_actions.artifact_store as store
from src.audit_actions.artifact_store import Artifact


@pytest.fixture
def stub_client_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Stubber client_store.years_dir slik at vi kan teste uten ekte client_store-oppsett."""

    class _Stub:
        @staticmethod
        def years_dir(client: str, *, year: str) -> Path:
            d = tmp_path / client / "years" / year
            d.mkdir(parents=True, exist_ok=True)
            return d

    monkeypatch.setattr(store, "client_store", _Stub)
    return tmp_path


# ---------------------------------------------------------------------------
# Manifest


def test_load_artifacts_empty(stub_client_store: Path) -> None:
    assert store.load_artifacts("ACME", "2025") == []


def test_register_and_load_artifact(stub_client_store: Path) -> None:
    # Lag en faktisk fil så from_path kan hente størrelse
    f = stub_client_store / "dummy.pdf"
    f.write_bytes(b"hello")
    art = Artifact.from_path(
        action_key="L:abc",
        workpaper_id="wp:nokkeltall_pdf",
        workpaper_navn="Nøkkeltall (PDF)",
        path=f,
        kjort_av="simen",
    )
    store.register_artifact("ACME", "2025", art)
    loaded = store.load_artifacts("ACME", "2025")
    assert len(loaded) == 1
    assert loaded[0].workpaper_id == "wp:nokkeltall_pdf"
    assert loaded[0].filename == "dummy.pdf"
    assert loaded[0].size == 5
    assert loaded[0].kjort_av == "simen"
    assert loaded[0].kjort_at  # satt av from_path


def test_register_dedupes_same_action_and_path(stub_client_store: Path) -> None:
    f = stub_client_store / "dummy.pdf"
    f.write_bytes(b"hello")
    a1 = Artifact.from_path(action_key="L:abc", workpaper_id="wp:x", workpaper_navn="X", path=f)
    a2 = Artifact.from_path(action_key="L:abc", workpaper_id="wp:x", workpaper_navn="X", path=f)
    store.register_artifact("ACME", "2025", a1)
    store.register_artifact("ACME", "2025", a2)
    assert len(store.load_artifacts("ACME", "2025")) == 1


def test_artifacts_for_filters_by_action_key(stub_client_store: Path) -> None:
    f = stub_client_store / "dummy.pdf"
    f.write_bytes(b"hello")
    a = Artifact.from_path(action_key="L:abc", workpaper_id="wp:x", workpaper_navn="X", path=f)
    b = Artifact.from_path(action_key="L:def", workpaper_id="wp:y", workpaper_navn="Y", path=f)
    store.register_artifact("ACME", "2025", a)
    store.register_artifact("ACME", "2025", b)
    assert [x.action_key for x in store.artifacts_for("ACME", "2025", "L:abc")] == ["L:abc"]


def test_prune_missing_removes_vanished_files(stub_client_store: Path) -> None:
    f = stub_client_store / "dummy.pdf"
    f.write_bytes(b"x")
    a = Artifact.from_path(action_key="L:abc", workpaper_id="wp:x", workpaper_navn="X", path=f)
    store.register_artifact("ACME", "2025", a)
    f.unlink()
    remaining = store.prune_missing("ACME", "2025")
    assert remaining == []
    assert store.load_artifacts("ACME", "2025") == []


def test_no_client_or_year_returns_empty() -> None:
    # Uten client_store stub returnerer modulen tom liste.
    assert store.load_artifacts("", "") == []
    assert store.artifacts_for("", "", "L:abc") == []


# ---------------------------------------------------------------------------
# Kommentarer


def test_save_and_get_comment(stub_client_store: Path) -> None:
    store.save_comment("ACME", "2025", "L:abc", "Avstemt mot forrige år.", updated_by="simen")
    c = store.get_comment("ACME", "2025", "L:abc")
    assert c.text == "Avstemt mot forrige år."
    assert c.updated_by == "simen"
    assert c.updated_at  # ISO-stempel


def test_save_comment_empty_removes_entry(stub_client_store: Path) -> None:
    store.save_comment("ACME", "2025", "L:abc", "tekst")
    assert store.get_comment("ACME", "2025", "L:abc").text == "tekst"
    store.save_comment("ACME", "2025", "L:abc", "   ")
    assert store.get_comment("ACME", "2025", "L:abc").text == ""


def test_comments_scoped_per_action_key(stub_client_store: Path) -> None:
    store.save_comment("ACME", "2025", "L:abc", "kommentar 1")
    store.save_comment("ACME", "2025", "42", "kommentar 2")
    all_comments = store.load_comments("ACME", "2025")
    assert all_comments["L:abc"].text == "kommentar 1"
    assert all_comments["42"].text == "kommentar 2"


def test_comments_scoped_per_year(stub_client_store: Path) -> None:
    store.save_comment("ACME", "2024", "L:abc", "i fjor")
    store.save_comment("ACME", "2025", "L:abc", "i år")
    assert store.get_comment("ACME", "2024", "L:abc").text == "i fjor"
    assert store.get_comment("ACME", "2025", "L:abc").text == "i år"
