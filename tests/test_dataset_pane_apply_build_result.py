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

    import dataset_pane
    from dataset_pane_build import BuildResult
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
