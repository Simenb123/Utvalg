from __future__ import annotations

from .shared import *  # noqa: F401,F403

def test_get_active_trial_balance_path_for_context_uses_active_version(monkeypatch, tmp_path) -> None:
    tb_path = tmp_path / "clients" / "air" / "years" / "2025" / "versions" / "sb.xlsx"
    monkeypatch.setattr(
        page_a07.client_store,
        "get_active_version",
        lambda client, year, dtype: SimpleNamespace(path=tb_path),
    )

    out = page_a07.get_active_trial_balance_path_for_context("Air Management AS", "2025")

    assert out == tb_path

def test_load_active_trial_balance_cached_falls_back_to_session_tb(monkeypatch) -> None:
    original_tb_df = getattr(page_a07.session, "tb_df", None)
    monkeypatch.setattr(
        page_a07.session,
        "tb_df",
        pd.DataFrame(
            [
                {"konto": "5000", "kontonavn": "Lonn", "ib": 0.0, "ub": 100.0, "netto": 100.0},
            ]
        ),
    )

    class DummyPage:
        def _get_cached_active_trial_balance_path(self, client, year, *, refresh=False):
            return None

        def _invalidate_active_tb_path_cache(self, client=None, year=None):
            return None

    try:
        gl_df, tb_path = page_a07.A07Page._load_active_trial_balance_cached(DummyPage(), "Air Management AS", "2025")
    finally:
        monkeypatch.setattr(page_a07.session, "tb_df", original_tb_df)

    assert tb_path is None
    assert gl_df.to_dict("records") == [
        {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "UB": 100.0, "Endring": 100.0, "Belop": 100.0}
    ]

def test_get_context_snapshot_tracks_workspace_and_tb(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    tb_path = years_dir / "versions" / "sb.xlsx"
    tb_path.parent.mkdir(parents=True, exist_ok=True)
    tb_path.write_text("demo", encoding="utf-8")
    monkeypatch.setattr(
        page_a07.client_store,
        "get_active_version",
        lambda client, year, dtype: SimpleNamespace(path=tb_path),
    )

    source_path = years_dir / "a07" / "a07_source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text('{"demo": true}', encoding="utf-8")

    mapping_path = years_dir / "a07" / "a07_mapping.json"
    mapping_path.write_text('{"1000": "fastloenn"}', encoding="utf-8")

    out = page_a07.get_context_snapshot("Air Management AS", "2025")

    assert out[0][0] == str(tb_path)
    assert out[1][0] == str(source_path)
    assert out[2][0] == str(mapping_path)

