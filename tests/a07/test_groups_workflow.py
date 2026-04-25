from __future__ import annotations

from .shared import *  # noqa: F401,F403

from a07_feature.path_context import build_groups_df


def test_groups_df_includes_amounts_and_locked_status() -> None:
    group_id = "A07_GROUP:fastloenn+timeloenn"
    groups = {
        group_id: page_a07.A07Group(
            group_id=group_id,
            group_name="Lønn samlet",
            member_codes=["fastloenn", "timeloenn"],
        )
    }
    control_df = pd.DataFrame(
        [
            {
                "Kode": group_id,
                "A07_Belop": 1000.0,
                "GL_Belop": 950.0,
                "Diff": 50.0,
            }
        ]
    )

    out = build_groups_df(groups, locked_codes={group_id}, control_df=control_df)

    assert out.loc[0, "Navn"] == "Lønn samlet"
    assert out.loc[0, "Members"] == "fastloenn, timeloenn"
    assert out.loc[0, "A07_Belop"] == 1000.0
    assert out.loc[0, "GL_Belop"] == 950.0
    assert out.loc[0, "Diff"] == 50.0
    assert bool(out.loc[0, "Locked"]) is True


def test_create_group_from_single_code_is_allowed_without_prompt(monkeypatch) -> None:
    autosaved: list[bool] = []
    refreshes: list[str | None] = []
    focuses: list[str] = []

    class _Var:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    monkeypatch.setattr(
        page_a07.simpledialog,
        "askstring",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not prompt")),
    )

    class DummyPage:
        workspace = SimpleNamespace(groups={})
        tree_a07 = object()
        status_var = _Var()

        def _default_group_name(self, codes):
            assert list(codes) == ["fastloenn"]
            return "Fastlønn"

        def _next_group_id(self, codes):
            assert list(codes) == ["fastloenn"]
            return "A07_GROUP:fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

        def _autosave_workspace_state(self) -> None:
            autosaved.append(True)

        def _refresh_core(self, focus_code=None) -> None:
            refreshes.append(focus_code)

        def _focus_control_code(self, code) -> None:
            focuses.append(code)

    dummy = DummyPage()

    out = page_a07.A07Page._create_group_from_codes(dummy, ["fastloenn"])

    assert out == "A07_GROUP:fastloenn"
    assert dummy.workspace.groups[out].member_codes == ["fastloenn"]
    assert dummy.workspace.groups[out].group_name == "Fastlønn"
    assert autosaved == [True]
    assert refreshes == ["A07_GROUP:fastloenn"]
    assert focuses == ["A07_GROUP:fastloenn"]
    assert dummy.status_var.value == "Opprettet A07-gruppe Fastlønn."


def test_a07_panel_has_visible_groups_button() -> None:
    source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "control_layout.py").read_text(
        encoding="utf-8"
    )

    assert 'text="Grupper"' in source
    assert "_open_groups_popup(None)" in source
