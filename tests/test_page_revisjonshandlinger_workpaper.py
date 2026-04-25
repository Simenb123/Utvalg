"""Integration tests for Handlinger 2.0 slice 1 — workpaper confirmation in UI.

Mange av testene under interagerer med CRM-handlinger via tree-iid-er
(``_tree.selection_set("1")``). CRM-rader rendres ikke lenger i
Handlinger-fanens tabell — de er bevisst skjult fordi regnskapslinjer
fra appens lokale handlingsbibliotek skal være primær. CRM-data og
underliggende workpaper-logikk er beholdt og fortsatt testbar i andre
tester (CRM-bridge / store-modulene). Disse end-to-end-testene blir
re-aktivert når vi kobler CRM-handlinger på igjen som sekundær info
per regnskapslinje.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Markér alle CRM-rad-avhengige tester som skipped for nå.
_CRM_HIDDEN_REASON = (
    "CRM-rader vises ikke i Handlinger-fanen for tiden — testen "
    "re-aktiveres når CRM-kobling som sekundær info per RL er klar."
)


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

    import action_workpaper_store as store

    def fake_years_dir(display_name: str, *, year: str) -> Path:
        p = tmp_path / display_name / "years" / year
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(store.client_store, "years_dir", fake_years_dir)

    import page_revisjonshandlinger as page_mod
    from crmsystem_action_matching import ActionMatch, RegnskapslinjeInfo
    from crmsystem_actions import AuditAction, EngagementInfo

    page = page_mod.RevisjonshandlingerPage(nb)
    nb.add(page, text="Handlinger")

    # Seed actions + auto-matches
    actions = [
        AuditAction(action_id=1, area_name="Salg", action_type="substantive",
                    procedure_name="010 Salgsinntekt", status="Åpen"),
        AuditAction(action_id=2, area_name="Varelager", action_type="control",
                    procedure_name="Varelagertelling", status="Åpen"),
        AuditAction(action_id=3, area_name="Uavklart", action_type="substantive",
                    procedure_name="Diverse gjennomgang", status="Åpen"),
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
        2: ActionMatch(action=actions[1], regnr="605", regnskapslinje="Varelager",
                       match_method="alias", confidence=0.85),
        3: ActionMatch(action=actions[2]),
    }
    page._client = "Acme AS"
    page._year = "2025"
    page._workpapers = {}

    return root, page


def test_kilde_column_is_added():
    import tkinter as tk
    from tkinter import ttk

    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("Tk not available")
    root.withdraw()
    nb = ttk.Notebook(root)
    nb.pack()
    try:
        import page_revisjonshandlinger as page_mod
        page = page_mod.RevisjonshandlingerPage(nb)
        assert "kilde" in page._tree["columns"]
    finally:
        root.destroy()


def _row(page, iid):
    cols = list(page._tree["columns"])
    values = page._tree.item(iid, "values")
    return {col: values[i] for i, col in enumerate(cols)}


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_apply_filter_shows_auto_source_for_unconfirmed(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._apply_filter()
        row = _row(page, "1")
        assert row["regnr"] == "10"
        assert row["regnskapslinje"] == "Salgsinntekt"
        assert row["kilde"] == "auto"
        assert "wp_auto" in page._tree.item("1", "tags")
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_apply_filter_shows_confirmed_source_and_tag(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        import action_workpaper_store as store
        store.confirm_regnr(
            "Acme AS", "2025", 1,
            regnr="70", regnskapslinje="Annen driftskostnad",
        )
        page._workpapers = store.load_workpapers("Acme AS", "2025")
        page._apply_filter()
        row = _row(page, "1")
        assert row["regnr"] == "70"
        assert row["regnskapslinje"] == "Annen driftskostnad"
        assert row["kilde"] == "bekreftet"
        assert "wp_confirmed" in page._tree.item("1", "tags")
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_on_confirm_current_persists_auto_match(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._apply_filter()
        page._tree.selection_set("1")
        page._on_confirm_current()

        import action_workpaper_store as store
        loaded = store.load_workpapers("Acme AS", "2025")
        assert 1 in loaded
        assert loaded[1].confirmed_regnr == "10"
        assert loaded[1].confirmed_regnskapslinje == "Salgsinntekt"

        assert _row(page, "1")["kilde"] == "bekreftet"
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_on_confirm_current_skips_when_no_auto_match(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._apply_filter()
        page._tree.selection_set("3")

        import tkinter.messagebox as mb
        calls = []
        monkeypatch.setattr(mb, "showinfo", lambda *a, **k: calls.append(("info", a, k)))
        page._on_confirm_current()

        import action_workpaper_store as store
        assert store.load_workpapers("Acme AS", "2025") == {}
        assert calls, "user should have been informed"
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_on_clear_confirmation_removes_entry(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        import action_workpaper_store as store
        store.confirm_regnr("Acme AS", "2025", 2, regnr="70", regnskapslinje="ADK")
        page._workpapers = store.load_workpapers("Acme AS", "2025")
        page._apply_filter()
        page._tree.selection_set("2")
        page._on_clear_confirmation()

        assert 2 not in store.load_workpapers("Acme AS", "2025")
        row = _row(page, "2")
        assert row["regnr"] == "605"  # tilbake til auto-match
        assert row["kilde"] == "auto"
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_action_buttons_reflect_selection_state(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        page._apply_filter()
        page._update_action_buttons()
        assert str(page._btn_confirm["state"]) == "disabled"
        assert str(page._btn_override["state"]) == "disabled"
        assert str(page._btn_clear["state"]) == "disabled"

        page._tree.selection_set("1")
        page._on_select()
        assert str(page._btn_confirm["state"]) == "normal"
        assert str(page._btn_override["state"]) == "normal"
        assert str(page._btn_clear["state"]) == "disabled"

        page._tree.selection_set("3")
        page._on_select()
        assert str(page._btn_confirm["state"]) == "disabled"
        assert str(page._btn_override["state"]) == "normal"

        import action_workpaper_store as store
        store.confirm_regnr("Acme AS", "2025", 1, regnr="10", regnskapslinje="Salgsinntekt")
        page._workpapers = store.load_workpapers("Acme AS", "2025")
        page._tree.selection_set("1")
        page._on_select()
        assert str(page._btn_clear["state"]) == "normal"
    finally:
        root.destroy()


@pytest.mark.skip(reason=_CRM_HIDDEN_REASON)
def test_select_shows_workpaper_info_in_detail_panel(tmp_path, monkeypatch):
    root, page = _make_page(tmp_path, monkeypatch)
    try:
        import action_workpaper_store as store
        store.confirm_regnr(
            "Acme AS", "2025", 2, regnr="70",
            regnskapslinje="Annen driftskostnad",
            confirmed_by="rev",
        )
        page._workpapers = store.load_workpapers("Acme AS", "2025")
        page._apply_filter()
        page._tree.selection_set("2")
        page._on_select()
        detail = page._detail_var.get()
        assert "Bekreftet: 70" in detail
        assert "Annen driftskostnad" in detail
        assert "rev" in detail
    finally:
        root.destroy()
