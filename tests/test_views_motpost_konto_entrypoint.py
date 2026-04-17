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


class DummyMotpostViewWithScope:
    created: List[dict[str, Any]] = []

    def __init__(self, master, df_transactions: pd.DataFrame, konto_list, konto_name_map=None, **kwargs):
        DummyMotpostViewWithScope.created.append(
            {
                "master": master,
                "df_len": len(df_transactions),
                "accounts": list(konto_list),
                "konto_name_map": dict(konto_name_map or {}),
                "kwargs": dict(kwargs),
            }
        )


class _DummyVar:
    def __init__(self, value: int):
        self._value = value

    def get(self):
        return self._value


class _DummyTextVar:
    def __init__(self, value: str):
        self._value = value

    def get(self):
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class _FakeCombo:
    def __init__(self):
        self.configured: dict[str, object] = {}

    def configure(self, **kwargs):
        self.configured.update(kwargs)


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


def test_show_motpost_konto_forwards_rl_scope_keywords_when_supported(monkeypatch) -> None:
    DummyMotpostViewWithScope.created.clear()
    monkeypatch.setattr(views_motpost_konto, "MotpostKontoView", DummyMotpostViewWithScope)

    df = _sample_df()
    views_motpost_konto.show_motpost_konto(
        master="root",
        df_all=df,
        selected_accounts=["3000"],
        konto_name_map={"3000": "Salg"},
        selected_direction="Kredit",
        scope_mode="regnskapslinje",
        scope_items=["10 Salgsinntekt"],
        konto_regnskapslinje_map={"3000": "10 Salgsinntekt"},
    )

    assert len(DummyMotpostViewWithScope.created) == 1
    created = DummyMotpostViewWithScope.created[0]
    assert created["master"] == "root"
    assert created["accounts"] == ["3000"]
    assert created["kwargs"]["selected_direction"] == "Kredit"
    assert created["kwargs"]["scope_mode"] == "regnskapslinje"
    assert created["kwargs"]["scope_items"] == ["10 Salgsinntekt"]
    assert created["kwargs"]["konto_regnskapslinje_map"] == {"3000": "10 Salgsinntekt"}


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


def test_refresh_details_applies_mva_filters_and_updates_code_choices(monkeypatch) -> None:
    def _stub_build_bilag_details(data, motkonto):
        return pd.DataFrame(
            [
                {
                    "Bilag": "10",
                    "Dato": pd.Timestamp("2025-01-01"),
                    "Tekst": "Med forventet mva",
                    "Beløp (valgte kontoer)": -100.0,
                    "Motbeløp": 100.0,
                    "MVA-kode": "3",
                    "MVA-prosent": "25",
                    "MVA-beløp": 25.0,
                    "Kontoer i bilag": "3000, 1500, 2700",
                },
                {
                    "Bilag": "11",
                    "Dato": pd.Timestamp("2025-01-02"),
                    "Tekst": "Uten mva",
                    "Beløp (valgte kontoer)": -80.0,
                    "Motbeløp": 80.0,
                    "MVA-kode": "",
                    "MVA-prosent": "",
                    "MVA-beløp": 0.0,
                    "Kontoer i bilag": "3000, 1500",
                },
            ]
        )

    monkeypatch.setattr(views_motpost_konto, "build_bilag_details", _stub_build_bilag_details)

    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._tree_details = _FakeTree()
    v._details_limit_var = _DummyVar(200)
    v._details_mva_code_var = _DummyTextVar("Alle")
    v._details_mva_code_combo = _FakeCombo()
    v._details_mva_mode_var = _DummyTextVar("Avvik fra forventet")
    v._details_expected_mva_var = _DummyTextVar("25")
    v._selected_motkonto = "2400"
    v._data = SimpleNamespace()

    views_motpost_konto.MotpostKontoView._refresh_details(v)

    assert v._details_mva_code_values == ["Alle", "3"]
    assert v._details_mva_code_combo.configured["values"] == ("Alle", "3")
    assert len(v._tree_details.inserted) == 1
    inserted = v._tree_details.inserted[0]["kwargs"]
    assert inserted["values"][0] == "11"
    assert inserted["values"][5] == ""
    assert inserted["values"][6] == ""
    assert "mva_avvik" in inserted["tags"]


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


def test_show_combinations_passes_rl_scope_context_to_popup(monkeypatch) -> None:
    calls = {"popup": None}

    def _stub_combo(df_scope, selected_accounts, *, outlier_motkonto=None, konto_navn_map=None):
        return pd.DataFrame([{"Kombinasjon #": 1, "Kombinasjon": "2400", "Antall bilag": 1}])

    def _stub_combo_per(df_scope, selected_accounts, *, outlier_motkonto=None, konto_navn_map=None):
        return pd.DataFrame([{"Valgt konto": "3000", "Kombinasjon": "2400"}])

    def _stub_popup(
        parent,
        *,
        df_combos,
        df_combo_per_selected=None,
        title="",
        summary=None,
        df_scope=None,
        selected_accounts=(),
        selected_direction=None,
        konto_navn_map=None,
        scope_mode=None,
        scope_items=None,
        konto_regnskapslinje_map=None,
        outlier_combinations=None,
        combo_status_map=None,
        combo_comment_map=None,
        on_export_excel=None,
    ):
        calls["popup"] = {
            "title": title,
            "summary": summary,
            "scope_mode": scope_mode,
            "scope_items": list(scope_items or ()),
            "konto_regnskapslinje_map": dict(konto_regnskapslinje_map or {}),
            "selected_accounts": list(selected_accounts or ()),
            "selected_direction": selected_direction,
        }

    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations", _stub_combo)
    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations_per_selected_account", _stub_combo_per)
    monkeypatch.setattr(views_motpost_konto, "show_motkonto_combinations_popup", _stub_popup)

    df_scope = pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 3000, "BelÃ¸p": -100.0},
            {"Bilag": 1, "Konto": 2400, "BelÃ¸p": 100.0},
        ]
    )
    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._data = SimpleNamespace(df_scope=df_scope, selected_accounts=("3000",), selected_direction="Kredit")
    v._outliers = set()
    v._scope_mode = "regnskapslinje"
    v._scope_items = ("10 Salgsinntekt",)
    v._konto_regnskapslinje_map = {"3000": "10 Salgsinntekt", "2400": "610 Kundefordringer"}
    v._export_excel = lambda *args, **kwargs: None

    views_motpost_konto.MotpostKontoView._show_combinations(v)

    assert calls["popup"] is not None
    assert calls["popup"]["scope_mode"] == "regnskapslinje"
    assert calls["popup"]["scope_items"] == ["10 Salgsinntekt"]
    assert calls["popup"]["konto_regnskapslinje_map"] == {
        "3000": "10 Salgsinntekt",
        "2400": "610 Kundefordringer",
    }
    assert calls["popup"]["selected_accounts"] == ["3000"]
    assert calls["popup"]["selected_direction"] == "Kredit"


def test_show_combinations_reuses_cached_popup_builds(monkeypatch) -> None:
    calls = {"combo": 0, "combo_per": 0, "popup": 0}

    def _stub_combo(df_scope, selected_accounts, *, selected_direction=None, outlier_motkonto=None, konto_navn_map=None):
        calls["combo"] += 1
        return pd.DataFrame([{"Kombinasjon #": 1, "Kombinasjon": "2400", "Antall bilag": 1}])

    def _stub_combo_per(df_scope, selected_accounts, *, selected_direction=None, outlier_motkonto=None, konto_navn_map=None):
        calls["combo_per"] += 1
        return pd.DataFrame([{"Valgt konto": "3000", "Kombinasjon": "2400"}])

    def _stub_popup(*args, **kwargs):
        calls["popup"] += 1

    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations", _stub_combo)
    monkeypatch.setattr(views_motpost_konto, "build_motkonto_combinations_per_selected_account", _stub_combo_per)
    monkeypatch.setattr(views_motpost_konto, "show_motkonto_combinations_popup", _stub_popup)

    df_scope = pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 3000, "BelÃ¸p": -100.0},
            {"Bilag": 1, "Konto": 2400, "BelÃ¸p": 100.0},
        ]
    )
    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._data = SimpleNamespace(df_scope=df_scope, selected_accounts=("3000",), selected_direction="Kredit")
    v._outliers = set()
    v._export_excel = lambda *args, **kwargs: None

    views_motpost_konto.MotpostKontoView._show_combinations(v)
    views_motpost_konto.MotpostKontoView._show_combinations(v)

    assert calls["combo"] == 1
    assert calls["combo_per"] == 1
    assert calls["popup"] == 2


def test_single_source_regnr_returns_regnr_for_single_scope() -> None:
    assert (
        views_motpost_konto._single_source_regnr(
            "regnskapslinje", ("10 Salgsinntekt",)
        )
        == 10
    )
    assert (
        views_motpost_konto._single_source_regnr(
            "regnskapslinje", ("10 Salgsinntekt", "20 Annen driftsinntekt")
        )
        is None
    )
    assert views_motpost_konto._single_source_regnr("konto", ("10",)) is None


def test_render_summary_marks_expected_motkonto_rows() -> None:
    v = SimpleNamespace()
    v._tree_summary = _FakeTree()
    v._data = SimpleNamespace(
        df_motkonto=pd.DataFrame(
            [
                {
                    "Motkonto": "1500",
                    "Kontonavn": "Kundefordringer",
                    "Sum": 17329550.29,
                    "% andel": -112.6,
                    "Antall bilag": 105,
                },
                {
                    "Motkonto": "2700",
                    "Kontonavn": "Utgående merverdiavgift, høy sats",
                    "Sum": -3714400.34,
                    "% andel": 24.1,
                    "Antall bilag": 112,
                },
            ]
        )
    )
    v._outliers = set()
    v._expected_motkontoer = {"1500"}

    views_motpost_konto.render_summary(v)

    first = v._tree_summary.inserted[0]["kwargs"]
    second = v._tree_summary.inserted[1]["kwargs"]
    assert "expected" in first["tags"]
    assert "(forventet)" in first["values"][1]
    assert "expected" not in second["tags"]


def test_export_excel_accepts_combo_status_and_comment_payloads(monkeypatch, tmp_path) -> None:
    captured = {"kwargs": None, "saved_to": None, "info": []}

    class _DummyWorkbook:
        def save(self, path):
            captured["saved_to"] = path

    def _stub_build_workbook(data, **kwargs):
        captured["kwargs"] = kwargs
        return _DummyWorkbook()

    filedialog_stub = SimpleNamespace(asksaveasfilename=lambda **_kwargs: str(tmp_path / "motpost.xlsx"))
    messagebox_stub = SimpleNamespace(
        showinfo=lambda *args, **kwargs: captured["info"].append((args, kwargs)),
        showerror=lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(views_motpost_konto, "filedialog", filedialog_stub)
    monkeypatch.setattr(views_motpost_konto, "messagebox", messagebox_stub)
    monkeypatch.setattr(views_motpost_konto, "build_motpost_excel_workbook", _stub_build_workbook)
    monkeypatch.setattr("motpost.view_konto_actions._best_effort_open_file", lambda _path: None)

    v = views_motpost_konto.MotpostKontoView.__new__(views_motpost_konto.MotpostKontoView)
    v._data = SimpleNamespace(df_scope=pd.DataFrame(), selected_accounts=("3000",))
    v._selected_motkonto = None
    v._outliers = set()
    v._outlier_combinations = set()

    views_motpost_konto.MotpostKontoView._export_excel(
        v,
        {"1500, 2700": "outlier"},
        {"1500, 2700": "Forklar kombinasjonen"},
    )

    assert captured["saved_to"] == str(tmp_path / "motpost.xlsx")
    assert captured["kwargs"]["combo_status_map"] == {"1500, 2700": "outlier"}
    assert captured["kwargs"]["combo_comment_map"] == {"1500, 2700": "Forklar kombinasjonen"}
