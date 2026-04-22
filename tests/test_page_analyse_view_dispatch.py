"""Regresjonstest for Visning-dropdown-dispatcher i Analyse.

Sørger for at når bruker velger "Nøkkeltall" / "Motposter" / "Motposter
(kontonivå)" — så dispatcher til riktig view-funksjon, ikke til SB-tree
(som var bug før 2026-04-17 fordi normalize_view_mode kollapset alle
ukjente moduser til Saldobalansekontoer).
"""
from __future__ import annotations

from types import SimpleNamespace

import page_analyse


class _Var:
    def __init__(self, v: str = "") -> None:
        self._v = v

    def get(self) -> str:
        return self._v

    def set(self, v: str) -> None:
        self._v = v


def _make_page(mode: str):
    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    p._var_tx_view_mode = _Var(mode)
    return p


def test_dispatcher_nokkeltall_calls_show_nk_view(monkeypatch) -> None:
    calls: list[str] = []

    import page_analyse_sb

    monkeypatch.setattr(page_analyse_sb, "show_nk_view",
                        lambda *, page: calls.append("nk"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "show_sb_tree",
                        lambda *, page: calls.append("sb"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "show_tx_tree",
                        lambda *, page: calls.append("tx"), raising=True)

    p = _make_page("Nøkkeltall")
    # stub refresh-hook
    p._refresh_nokkeltall_view = lambda: calls.append("nk_refresh")

    page_analyse.AnalysePage._refresh_transactions_view(p)

    assert calls == ["nk", "nk_refresh"]


def test_dispatcher_motposter_calls_show_mp_tree(monkeypatch) -> None:
    calls: list[str] = []

    import page_analyse_sb

    monkeypatch.setattr(page_analyse_sb, "show_mp_tree",
                        lambda *, page: calls.append("mp"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "refresh_mp_view",
                        lambda *, page: calls.append("mp_refresh"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "show_sb_tree",
                        lambda *, page: calls.append("sb"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "show_tx_tree",
                        lambda *, page: calls.append("tx"), raising=True)

    p = _make_page("Motposter")

    page_analyse.AnalysePage._refresh_transactions_view(p)

    assert calls == ["mp", "mp_refresh"]


def test_dispatcher_saldobalanse_still_routes_to_sb_tree(monkeypatch) -> None:
    """Saldobalanse-modus skal fortsatt dispatche til show_sb_tree."""
    calls: list[str] = []

    import page_analyse_sb

    monkeypatch.setattr(page_analyse_sb, "show_sb_tree",
                        lambda *, page: calls.append("sb"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "refresh_sb_view",
                        lambda *, page: calls.append("sb_refresh"), raising=True)
    monkeypatch.setattr(page_analyse_sb, "show_nk_view",
                        lambda *, page: calls.append("nk"), raising=True)

    p = _make_page("Saldobalanse")

    page_analyse.AnalysePage._refresh_transactions_view(p)

    assert "sb" in calls and "nk" not in calls


def test_view_switch_actually_grids_the_right_frame():
    """Regresjonstest: bytte Visning → riktig høyre-frame skal faktisk bli synlig.

    Dispatcher-testene over monkeypatcher show_mp_tree etc. og ville ikke
    fanget NameError i selve show_mp_tree (jf. manglende _hide_all_views-import
    i analyse_sb_motpost.py, 2026-04-22).
    """
    import tkinter as tk
    from tkinter import ttk
    import pytest

    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("Tk not available")
    root.withdraw()
    nb = ttk.Notebook(root)
    nb.pack()
    try:
        page = page_analyse.AnalysePage(nb)
        nb.add(page, text="Analyse")
        root.update()

        def gridded(attr):
            f = getattr(page, attr, None)
            return bool(f) and bool(f.grid_info())

        # Init: tx-frame er synlig
        assert gridded("_tx_frame")

        page._var_tx_view_mode.set("Motposter")
        root.update()
        assert gridded("_mp_frame"), "Motposter skal grid-e _mp_frame"
        assert not gridded("_tx_frame")

        page._var_tx_view_mode.set("Motposter (kontonivå)")
        root.update()
        assert gridded("_mp_acct_frame"), "Motposter (kontonivå) skal grid-e _mp_acct_frame"

        page._var_tx_view_mode.set("Nøkkeltall")
        root.update()
        assert gridded("_nk_frame"), "Nøkkeltall skal grid-e _nk_frame"

        page._var_tx_view_mode.set("Saldobalanse")
        root.update()
        assert gridded("_sb_frame"), "Saldobalanse skal grid-e _sb_frame"

        page._var_tx_view_mode.set("Hovedbok")
        root.update()
        assert gridded("_tx_frame"), "Hovedbok skal grid-e _tx_frame"
    finally:
        root.destroy()
