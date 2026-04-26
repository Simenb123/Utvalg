from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class _Var:
    """Minimal erstatning for tkinter.StringVar i rene unit-tester."""

    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:  # noqa: D401 - enkel var
        return self._value

    def set(self, value: str) -> None:
        self._value = value


@dataclass
class _DummyStoreSection:
    hb_var: _Var
    refreshed: bool = False

    def refresh(self) -> None:
        self.refreshed = True


def test_apply_build_result_updates_ml_map_and_store_section(monkeypatch, tmp_path):
    """Regression: _apply_build_result må ikke krasje ved ML-map og auto-store."""

    # Legg ml_map-filen i temp for å unngå å skrive i repo-roten.
    monkeypatch.chdir(tmp_path)

    import src.pages.dataset.frontend.pane as dataset_pane
    from src.pages.dataset.backend.pane_build import BuildResult
    from models import Columns

    # Lag en DatasetPane uten å init'e tkinter.
    pane = dataset_pane.DatasetPane.__new__(dataset_pane.DatasetPane)

    # Stubb ut det som _apply_build_result forventer.
    pane._last_build = None
    pane._on_ready = None
    pane._headers = ["AccountID", "VoucherNo"]
    pane._ml_map = {}
    pane.path_var = _Var("dummy.xlsx")
    pane.combo_vars = {
        "Konto": _Var("AccountID"),
        "Bilag": _Var("VoucherNo"),
    }
    pane.status_lbl = None  # _set_status blir no-op

    store = _DummyStoreSection(hb_var=_Var(""))
    pane._store_section = store

    # Ikke la testen avhenge av global session/bus.
    monkeypatch.setattr(dataset_pane.session, "set_dataset", lambda *_a, **_k: None)
    monkeypatch.setattr(dataset_pane.bus, "emit", lambda *_a, **_k: None)

    df = pd.DataFrame({"Konto": ["1000"], "Bilag": ["1"], "Beløp": [1.0]})
    cols = Columns(konto="Konto", bilag="Bilag", belop="Beløp")
    res = BuildResult(df=df, cols=cols, stored_version_id="v1")

    # Skal ikke kaste TypeError (ML-map) eller AttributeError (store-section).
    dataset_pane.DatasetPane._apply_build_result(pane, res, show_message=False, update_ml=True)

    assert store.hb_var.get() == "v1"
    assert store.refreshed is True


def test_apply_build_result_defers_saft_auto_sb(monkeypatch):
    """Regression: SAF-T -> SB må planlegges i bakgrunn, ikke kjøres direkte i GUI-tråden."""
    import src.pages.dataset.frontend.pane as dataset_pane
    from src.pages.dataset.backend.pane_build import BuildResult
    from models import Columns

    pane = dataset_pane.DatasetPane.__new__(dataset_pane.DatasetPane)
    pane._last_build = None
    pane._on_ready = None
    pane._headers = []
    pane._ml_map = {}
    pane.path_var = _Var("dummy.xml")
    pane.combo_vars = {}
    pane.status_lbl = None

    store = _DummyStoreSection(hb_var=_Var(""))
    pane._store_section = store

    monkeypatch.setattr(dataset_pane.session, "set_dataset", lambda *_a, **_k: None)
    monkeypatch.setattr(dataset_pane.bus, "emit", lambda *_a, **_k: None)

    scheduled: dict[str, object] = {}
    pane._schedule_auto_create_sb_from_saft = lambda: scheduled.setdefault("ran", True)
    pane._invalidate_sb_for_current_year = lambda: scheduled.setdefault("invalidated", True)
    captured_fns: list = []
    pane.after_idle = lambda fn: captured_fns.append(fn)

    df = pd.DataFrame({"Konto": ["1000"], "Bilag": ["1"], "Beløp": [1.0]})
    cols = Columns(konto="Konto", bilag="Bilag", belop="Beløp")
    res = BuildResult(df=df, cols=cols, stored_version_id="v1")

    dataset_pane.DatasetPane._apply_build_result(pane, res, show_message=False, update_ml=False)

    # Funksjonen skal være planlagt via after_idle (ikke kjørt direkte).
    assert "ran" not in scheduled
    # Når den planlagte funksjonen senere kjøres, skal den trigge auto-create.
    assert captured_fns, "after_idle skulle vært kalt med en funksjon"
    for fn in captured_fns:
        fn()
    assert scheduled.get("ran") is True
