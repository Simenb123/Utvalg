"""Tests for Beløp/Scope-kolonner og «RL uten handling»-rader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _make_page(tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import ttk

    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("Tk not available in this environment")
    root.withdraw()
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    import action_assignment_store as asg_store
    import action_workpaper_store as wp_store

    def fake_years_dir(display_name: str, *, year: str) -> Path:
        p = tmp_path / display_name / "years" / year
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(asg_store.client_store, "years_dir", fake_years_dir)
    monkeypatch.setattr(wp_store.client_store, "years_dir", fake_years_dir)

    import scoping_store
    monkeypatch.setattr(scoping_store, "_overrides_path",
                        lambda c, y: fake_years_dir(c, year=y) / "scoping_overrides.json")

    import page_revisjonshandlinger as page_mod
    from crmsystem_action_matching import ActionMatch, RegnskapslinjeInfo
    from crmsystem_actions import AuditAction, EngagementInfo

    page = page_mod.RevisjonshandlingerPage(nb)
    nb.add(page, text="Handlinger")

    actions = [
        AuditAction(action_id=1, area_name="Salg", action_type="substantive",
                    procedure_name="010 Salgsinntekt", status="Åpen"),
    ]
    page._actions = actions
    page._engagement = EngagementInfo(client_number="100", client_name="Acme AS",
                                      engagement_year=2025)
    rl_list = [
        RegnskapslinjeInfo(nr="10", regnskapslinje="Salgsinntekt"),
        RegnskapslinjeInfo(nr="605", regnskapslinje="Varelager"),
        RegnskapslinjeInfo(nr="70", regnskapslinje="Annen driftskostnad"),
    ]
    page._rl_list = rl_list
    page._match_by_action_id = {
        1: ActionMatch(action=actions[0], regnr="10", regnskapslinje="Salgsinntekt",
                       match_method="prefix", confidence=1.0),
    }
    page._client = "Acme AS"
    page._year = "2025"
    page._workpapers = {}
    return root, page


def test_belop_column_present_and_formatted(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {10: 1234567.0}
        page._apply_filter()
        cols = page._tree["columns"]
        assert "belop" in cols
        idx = list(cols).index("belop")
        values = page._tree.item("1", "values")
        assert values[idx] == "1 234 567"
    finally:
        root.destroy()


def test_scope_column_uses_override(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_scope = {"10": "inn", "70": "ut"}
        page._apply_filter()
        idx = list(page._tree["columns"]).index("scope")
        values = page._tree.item("1", "values")
        assert values[idx] == "✓"
    finally:
        root.destroy()


def test_belop_blank_when_no_amount(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {}
        page._apply_filter()
        idx = list(page._tree["columns"]).index("belop")
        assert page._tree.item("1", "values")[idx] == ""
    finally:
        root.destroy()


def test_rl_gap_rows_hidden_by_default(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._apply_filter()
        # Bare den ene faktiske handlingen
        children = page._tree.get_children()
        assert children == ("1",)
    finally:
        root.destroy()


def test_rl_gap_rows_show_when_toggle_on(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0, 70: 12000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        ids = page._tree.get_children()
        # action 1 dekker regnr=10 → RL:605 og RL:70 skal komme som gap
        assert "1" in ids
        assert "RL:605" in ids
        assert "RL:70" in ids
        assert "RL:10" not in ids
    finally:
        root.destroy()


def test_rl_gap_rows_hidden_when_no_amount(tmp_path, monkeypatch):
    """RL uten beløp skal ikke vises som gap-rad selv med toggle på."""
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0}  # 70 mangler beløp
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        ids = page._tree.get_children()
        assert "RL:605" in ids
        assert "RL:70" not in ids
    finally:
        root.destroy()


def test_rl_gap_row_has_handling_placeholder_text(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        idx = list(page._tree["columns"]).index("handling")
        text = page._tree.item("RL:605", "values")[idx]
        assert "ingen handling" in text.lower()
    finally:
        root.destroy()


def test_rl_gap_row_has_amount_and_scope(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0}
        page._rl_scope = {"605": "ut"}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        cols = list(page._tree["columns"])
        values = page._tree.item("RL:605", "values")
        assert values[cols.index("belop")] == "50 000"
        assert values[cols.index("scope")] == "–"
    finally:
        root.destroy()


def test_rl_gap_row_has_gap_tag(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        assert "rl_gap" in page._tree.item("RL:605", "tags")
    finally:
        root.destroy()


def test_select_rl_gap_shows_helpful_detail(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        page._tree.selection_set("RL:605")
        page._on_select()
        detail = page._detail_var.get().lower()
        assert "ingen handling" in detail
        assert "dobbeltklikk" in detail
    finally:
        root.destroy()


def test_heading_click_sorts_ascending_then_descending(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        # Legg til en lokal handling slik at vi har minst to rader å sortere
        from crmsystem_actions import AuditAction
        page._actions.append(
            AuditAction(action_id=2, area_name="Bank", action_type="substantive",
                        procedure_name="020 Bankavstemming", status="Åpen")
        )
        from crmsystem_action_matching import ActionMatch
        page._match_by_action_id[2] = ActionMatch(
            action=page._actions[1], regnr="655", regnskapslinje="Bank",
            match_method="prefix", confidence=1.0,
        )
        page._apply_filter()

        page._on_heading_click("regnr")
        order_asc = list(page._tree.get_children())
        assert order_asc.index("1") < order_asc.index("2")  # 10 < 655
        assert page._tree.heading("regnr", "text").endswith("↑")

        page._on_heading_click("regnr")
        order_desc = list(page._tree.get_children())
        assert order_desc.index("2") < order_desc.index("1")
        assert page._tree.heading("regnr", "text").endswith("↓")
    finally:
        root.destroy()


def test_belop_sort_is_numeric(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        from crmsystem_actions import AuditAction
        from crmsystem_action_matching import ActionMatch
        page._actions.append(
            AuditAction(action_id=2, area_name="Bank", action_type="substantive",
                        procedure_name="020 Bankavstemming", status="Åpen")
        )
        page._match_by_action_id[2] = ActionMatch(
            action=page._actions[1], regnr="655", regnskapslinje="Bank",
            match_method="prefix", confidence=1.0,
        )
        # 1: 9 000 000, 2: 1 000 — numerisk sortering må bruke tallet, ikke strengen
        page._rl_amounts = {10: 9_000_000.0, 655: 1_000.0}
        page._apply_filter()

        page._on_heading_click("belop")
        order_asc = list(page._tree.get_children())
        assert order_asc.index("2") < order_asc.index("1")  # 1 000 < 9 000 000
    finally:
        root.destroy()


def test_sort_keeps_rl_gap_rows_at_bottom(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {605: 50000.0, 70: 12000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        page._on_heading_click("regnr")
        # Etter usynkende sortering skal "RL:" fortsatt komme etter alle vanlige rader
        children = list(page._tree.get_children())
        last_regular = max(i for i, iid in enumerate(children) if not iid.startswith("RL:"))
        first_gap = min(i for i, iid in enumerate(children) if iid.startswith("RL:"))
        assert last_regular < first_gap
    finally:
        root.destroy()


def test_double_click_on_rl_gap_calls_link_dialog(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._rl_amounts = {70: 12000.0}
        page.var_show_rl_gaps.set(True)
        page._apply_filter()
        page._tree.selection_set("RL:70")

        calls: list[dict[str, Any]] = []
        import action_link_dialog
        monkeypatch.setattr(action_link_dialog, "open_action_link_dialog",
                            lambda **kw: calls.append(kw))

        page._on_double_click()
        assert len(calls) == 1
        assert calls[0]["kind"] == "rl"
        assert calls[0]["entity_key"] == "70"
        assert "Annen driftskostnad" in calls[0]["entity_label"]
    finally:
        root.destroy()
