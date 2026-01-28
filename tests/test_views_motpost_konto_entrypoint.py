from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pandas as pd

import views_motpost_konto


class DummyMotpostView:
    created: List[dict[str, Any]] = []

    def __init__(self, master, df_transactions: pd.DataFrame, konto_list):
        DummyMotpostView.created.append(
            {
                "master": master,
                "df_len": len(df_transactions),
                "accounts": list(konto_list),
            }
        )


class _DummyVar:
    def __init__(self, value: int):
        self._value = value

    def get(self):
        return self._value


class _FakeTree:
    def __init__(self):
        self._children = ["row1", "row2"]
        self.inserted = []

    def get_children(self):
        return list(self._children)

    def delete(self, *items):
        # emulate deletion
        self._children = []

    def insert(self, *args, **kwargs):
        self.inserted.append({"args": args, "kwargs": kwargs})

    def selection(self):
        return []


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 3000, "Beløp": -100.0, "Tekst": "Salg", "Dato": "2025-01-01"},
            {"Bilag": 1, "Konto": 2400, "Beløp": 100.0, "Tekst": "Mot", "Dato": "2025-01-01"},
        ]
    )


def test_show_motpost_konto_accepts_new_keyword_signature(monkeypatch) -> None:
    DummyMotpostView.created.clear()
    monkeypatch.setattr(views_motpost_konto, "MotpostKontoView", DummyMotpostView)

    df = _sample_df()
    views_motpost_konto.show_motpost_konto(
        master="root",
        df_all=df,
        selected_accounts=["3000"],
        konto_name_map={"3000": "Salg"},
    )

    assert len(DummyMotpostView.created) == 1
    created = DummyMotpostView.created[0]
    assert created["master"] == "root"
    assert created["df_len"] == 2
    assert created["accounts"] == ["3000"]


def test_show_motpost_konto_accepts_positional_konto_name_map(monkeypatch) -> None:
    DummyMotpostView.created.clear()
    monkeypatch.setattr(views_motpost_konto, "MotpostKontoView", DummyMotpostView)

    df = _sample_df()
    # 4th positional argument is konto_name_map in some callers
    views_motpost_konto.show_motpost_konto("root", df, ["3000"], {"3000": "Salg"})

    assert len(DummyMotpostView.created) == 1
    assert DummyMotpostView.created[0]["accounts"] == ["3000"]


def test_show_motpost_konto_with_empty_account_list_does_not_open_view(monkeypatch) -> None:
    """Typisk feiltilfelle: kalles uten kontoer -> skal ikke åpne vindu."""
    DummyMotpostView.created.clear()
    monkeypatch.setattr(views_motpost_konto, "MotpostKontoView", DummyMotpostView)

    df = _sample_df()
    views_motpost_konto.show_motpost_konto(master="root", df_all=df, selected_accounts=[])

    assert DummyMotpostView.created == []


def test_refresh_details_calls_build_bilag_details_without_unexpected_kwargs(monkeypatch) -> None:
    called = {"args": None, "kwargs": None}

    def _stub_build_bilag_details(data, motkonto):
        called["args"] = (data, motkonto)
        called["kwargs"] = {}
        return pd.DataFrame(
            [
                {
                    "Bilag": "10",
                    "Dato": pd.Timestamp("2025-01-01"),
                    "Tekst": "Test",
                    "Beløp (valgte kontoer)": 100.0,
                    "Motbeløp": -100.0,
                }
            ]
        )

    monkeypatch.setattr(views_motpost_konto, "build_bilag_details", _stub_build_bilag_details)

    # Lag en "view" uten Tk-init
    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._tree_details = _FakeTree()
    v._details_limit_var = _DummyVar(200)
    v._selected_motkonto = "2400"
    v._data = SimpleNamespace()  # data-objekt sendes videre til stub

    views_motpost_konto.MotpostKontoView._refresh_details(v)

    assert called["args"] == (v._data, "2400")
    # Stub returnerte 1 rad -> bør ha 1 insert
    assert len(v._tree_details.inserted) == 1


def test_show_combinations_uses_df_scope_positional_args(monkeypatch) -> None:
    calls = {"combo": None, "combo_per": None, "popup": None}

    def _stub_combo(df_scope, selected_accounts, *, outlier_motkonto=None, konto_navn_map=None):
        calls["combo"] = {"df_cols": list(df_scope.columns), "sel": set(selected_accounts), "out": outlier_motkonto}
        return pd.DataFrame([{"Kombinasjon #": 1, "Kombinasjon": "2400", "Antall bilag": 1}])

    def _stub_combo_per(df_scope, selected_accounts, *, outlier_motkonto=None, konto_navn_map=None):
        calls["combo_per"] = {"df_cols": list(df_scope.columns), "sel": set(selected_accounts), "out": outlier_motkonto}
        return pd.DataFrame([{"Valgt konto": "3000", "Kombinasjon": "2400"}])

    def _stub_popup(parent, *, df_combos, df_combo_per_selected=None, title="", summary=None):
        calls["popup"] = {"title": title, "summary": summary, "rows": len(df_combos)}

    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations", _stub_combo)
    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations_per_selected_account", _stub_combo_per)
    monkeypatch.setattr(views_motpost_konto, "show_motkonto_combinations_popup", _stub_popup)

    df_scope = pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 3000, "Beløp": -100.0},
            {"Bilag": 1, "Konto": 2400, "Beløp": 100.0},
        ]
    )
    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._data = SimpleNamespace(df_scope=df_scope, selected_accounts=("3000",))
    v._outliers = set()

    views_motpost_konto.MotpostKontoView._show_combinations(v)

    assert calls["combo"] is not None
    assert calls["combo_per"] is not None
    assert calls["popup"] is not None
    assert calls["combo"]["sel"] == {"3000"}
