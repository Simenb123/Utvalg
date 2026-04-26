from __future__ import annotations

from unittest.mock import MagicMock, patch

from .shared import *  # noqa: F401,F403


def test_a07_managed_view_id_uses_stable_ui_namespace() -> None:
    from a07_feature.ui.managed_tree import a07_managed_view_id

    assert a07_managed_view_id("history") == "a07.history"
    assert a07_managed_view_id("a07.groups") == "a07.groups"


def test_a07_column_specs_convert_legacy_tuples_to_column_specs() -> None:
    from a07_feature.ui.managed_tree import a07_column_specs

    specs = a07_column_specs(
        [
            ("Konto", "Konto", 90, "w"),
            ("Belop", "Beløp", 120, "e"),
        ]
    )

    assert [spec.id for spec in specs] == ["Konto", "Belop"]
    assert specs[0].heading == "Konto"
    assert specs[0].width == 90
    assert specs[0].anchor == "w"
    assert specs[0].pinned is True
    assert specs[1].heading == "Beløp"
    assert specs[1].anchor == "e"
    assert specs[1].pinned is False


def test_a07_column_specs_use_global_balance_headings_for_active_year() -> None:
    from a07_feature.ui.managed_tree import a07_column_specs

    specs = a07_column_specs(
        [
            ("IB", "IB", 100, "e"),
            ("Endring", "Endring", 100, "e"),
            ("UB", "UB", 100, "e"),
        ],
        year=2025,
    )

    assert [spec.heading for spec in specs] == ["IB 2025", "\u0394 UB-IB 25", "UB 2025"]


def test_a07_column_specs_use_saldobalanse_labels_for_legacy_gl_fields() -> None:
    from a07_feature.ui.managed_tree import a07_column_heading, a07_column_specs

    specs = a07_column_specs(
        [
            ("GL_Belop", "GL", 110, "e"),
            ("GL_Sum", "GL forslag", 110, "e"),
            ("SamledeYtelser", "GL opplys.", 110, "e"),
            ("AgaGrunnlag", "GL AGA", 110, "e"),
        ],
        year=2025,
    )

    assert [spec.heading for spec in specs] == ["SB", "SB forslag", "SB opplys.", "SB AGA"]
    assert a07_column_heading("GL_Belop", "GL", year=2025) == "SB"
    assert a07_column_heading("GL_Sum", "GL forslag", year=2025) == "SB forslag"


def test_a07_managed_tree_builder_uses_ui_pref_prefix_and_body_context_callback() -> None:
    from a07_feature.ui.managed_tree import A07PageManagedTreeMixin

    class _Dummy(A07PageManagedTreeMixin):
        pass

    dummy = _Dummy()
    parent = MagicMock()
    frame = MagicMock()
    tree = MagicMock()
    ybar = MagicMock()
    xbar = MagicMock()
    on_body_right_click = MagicMock()

    def _frame_factory(_parent):
        return frame

    def _tree_factory(_parent, **_kwargs):
        return tree

    def _scrollbar_factory(_parent, **kwargs):
        return ybar if kwargs.get("orient") == "vertical" else xbar

    with patch("a07_feature.ui.managed_tree.ttk.Frame", side_effect=_frame_factory), patch(
        "a07_feature.ui.managed_tree.ttk.Treeview",
        side_effect=_tree_factory,
    ), patch("a07_feature.ui.managed_tree.ttk.Scrollbar", side_effect=_scrollbar_factory), patch(
        "a07_feature.ui.managed_tree.ManagedTreeview"
    ) as managed_cls:
        built = dummy._build_managed_tree_tab(
            parent,
            [("Konto", "Konto", 90, "w")],
            view_id="control_accounts",
            height=6,
            selectmode="extended",
            on_body_right_click=on_body_right_click,
        )

    assert built is tree
    tree.configure.assert_any_call(selectmode="extended")
    tree.configure.assert_any_call(height=6)
    _, kwargs = managed_cls.call_args
    assert kwargs["view_id"] == "a07.control_accounts"
    assert kwargs["pref_prefix"] == "ui"
    assert kwargs["on_body_right_click"] is on_body_right_click
    assert kwargs["auto_bind"] is True
    assert dummy._a07_managed_treeviews["a07.control_accounts"] is managed_cls.return_value
