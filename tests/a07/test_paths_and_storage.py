from __future__ import annotations

from .shared import *  # noqa: F401,F403
import a07_feature.page_a07_refresh_state as refresh_state

def test_build_gl_picker_options_includes_account_name_and_amount() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "1920", "Navn": "Bank", "Endring": 1250.5},
            {"Konto": "5000", "Navn": "Lonn", "Endring": -50.0},
        ]
    )

    out = page_a07.build_gl_picker_options(gl_df)

    assert [option.key for option in out] == ["1920", "5000"]
    assert out[0].label.startswith("1920 | Bank | ")

def test_build_a07_picker_options_includes_code_name_and_amount() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0},
            {"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 250.25},
        ]
    )

    out = page_a07.build_a07_picker_options(a07_df)

    assert [option.key for option in out] == ["fastloenn", "feriepenger"]
    assert out[0].label.startswith("fastloenn | Fastloenn | ")

def test_load_mapping_clicked_uses_default_path_for_profile_only_context(monkeypatch, tmp_path) -> None:
    default_path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"
    page = object.__new__(page_a07.A07Page)
    page.a07_path = None
    page.workspace = SimpleNamespace(mapping={}, groups={}, locks=set())
    page.mapping_path_var = _DummyVar()
    page.status_var = _DummyVar()
    page.mapping_path = None
    page.groups_path = None
    page.locks_path = None
    page._session_context = lambda _session: ("Air Management AS", "2025")

    calls = {"dialog": 0, "refresh": 0}

    monkeypatch.setattr(
        page_a07,
        "suggest_default_mapping_path",
        lambda a07_path, client=None, year=None: default_path,
    )
    monkeypatch.setattr(
        page,
        "_load_mapping_file_cached",
        lambda path, client=None, year=None: {"5000": "fastloenn"},
    )
    monkeypatch.setattr(page, "_refresh_core", lambda: calls.__setitem__("refresh", calls["refresh"] + 1))
    monkeypatch.setattr(page_a07, "default_a07_groups_path", lambda client, year: tmp_path / "groups.json")
    monkeypatch.setattr(page_a07, "load_a07_groups", lambda path: {"demo": "group"})
    monkeypatch.setattr(page_a07, "default_a07_locks_path", lambda client, year: tmp_path / "locks.json")
    monkeypatch.setattr(page_a07, "load_locks", lambda path: {"fastloenn"})
    monkeypatch.setattr(
        page_a07.filedialog,
        "askopenfilename",
        lambda **kwargs: calls.__setitem__("dialog", calls["dialog"] + 1) or "",
    )

    page_a07.A07Page._load_mapping_clicked(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert page.mapping_path == default_path
    assert page.mapping_path_var.value == f"Mapping: {default_path}"
    assert page.status_var.value == f"Lastet mapping fra {default_path.name}."
    assert page.workspace.groups == {"demo": "group"}
    assert page.workspace.locks == {"fastloenn"}
    assert calls["dialog"] == 0
    assert calls["refresh"] == 1

def test_invalidate_active_tb_path_cache_clears_mapping_file_cache() -> None:
    dummy = SimpleNamespace(
        _active_tb_cache_key=lambda client, year: ("Air Management AS", "2025"),
        _active_tb_path_cache={("Air Management AS", "2025"): Path("tb.xlsx")},
        _mapping_file_cache={((None, None, None), "Air Management AS", "2025"): {"5000": "fastloenn"}},
        _previous_mapping_cache={("Air Management AS", "2025"): ({}, None, None)},
        _rulebook_path_cache={("Air Management AS", "2025"): Path("rulebook.json")},
    )

    page_a07.A07Page._invalidate_active_tb_path_cache(dummy, "Air Management AS", "2025")

    assert dummy._active_tb_path_cache == {}
    assert dummy._mapping_file_cache == {}
    assert dummy._previous_mapping_cache == {}
    assert dummy._rulebook_path_cache == {}

def test_load_mapping_file_cached_prefers_json_over_profiles_by_default(monkeypatch, tmp_path) -> None:
    calls: list[tuple[Path, str | None, str | None, bool]] = []
    dummy = SimpleNamespace(_mapping_file_cache={})
    path = tmp_path / "a07_mapping.json"

    def _fake_load_mapping(path_arg, *, client=None, year=None, prefer_profiles=False):
        calls.append((Path(path_arg), client, year, prefer_profiles))
        return {"5000": "fastloenn"}

    monkeypatch.setattr(refresh_state, "load_mapping", _fake_load_mapping)

    out = page_a07.A07Page._load_mapping_file_cached(
        dummy,
        path,
        client="Air Management AS",
        year="2025",
    )

    assert out == {"5000": "fastloenn"}
    assert calls == [(path, "Air Management AS", "2025", False)]

def test_build_source_overview_rows_keeps_source_labels_in_stable_order() -> None:
    out = page_a07.build_source_overview_rows(
        a07_text="A07: a07_source.json",
        tb_text="Saldobalanse: trial_balance.xlsx",
        mapping_text="Mapping: a07_mapping.json",
        rulebook_text="Rulebook: global_full_a07_rulebook.json",
        history_text="Historikk: ingen tidligere A07-mapping funnet",
    )

    assert out == [
        ("A07-kilde", "A07: a07_source.json"),
        ("Saldobalanse", "Saldobalanse: trial_balance.xlsx"),
        ("Mapping", "Mapping: a07_mapping.json"),
        ("Rulebook", "Rulebook: global_full_a07_rulebook.json"),
        ("Historikk", "Historikk: ingen tidligere A07-mapping funnet"),
    ]

def test_resolve_rf1022_target_code_prefers_single_code_groups() -> None:
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(mapping={}, suggestions=pd.DataFrame(), selected_code=None),
        control_gl_df=pd.DataFrame(),
        _effective_mapping=lambda: {},
    )

    out = page_a07.A07Page._resolve_rf1022_target_code(dummy, "100_refusjon", ["5800"])

    assert out == "sumAvgiftsgrunnlagRefusjon"

def test_resolve_rf1022_target_code_uses_naturalytelse_name_hints() -> None:
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(mapping={}, suggestions=pd.DataFrame(), selected_code=None, gl_df=pd.DataFrame()),
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5210", "Navn": "Fri telefon"},
                {"Konto": "5251", "Navn": "Gruppelivsforsikring"},
            ]
        ),
        _effective_mapping=lambda: {},
    )

    phone_code = page_a07.A07Page._resolve_rf1022_target_code(dummy, "111_naturalytelser", ["5210"])
    insurance_code = page_a07.A07Page._resolve_rf1022_target_code(dummy, "111_naturalytelser", ["5251"])

    assert phone_code == "elektroniskKommunikasjon"
    assert insurance_code == "skattepliktigDelForsikringer"

def test_resolve_rf1022_target_code_does_not_default_broad_payroll_to_annet() -> None:
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(mapping={}, suggestions=pd.DataFrame(), selected_code=None, gl_df=pd.DataFrame()),
        control_gl_df=pd.DataFrame([{"Konto": "6701", "Navn": "Honorar revisjon"}]),
        _effective_mapping=lambda: {},
    )

    out = page_a07.A07Page._resolve_rf1022_target_code(dummy, "100_loenn_ol", ["6701"])

    assert out is None

