from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analyse_mapping_service import UnmappedAccountIssue
from account_profile import AccountProfile, AccountProfileDocument


def _make_sb(*, konto: list[str], navn: list[str], ib: list[float], ub: list[float], netto: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "konto": konto,
            "kontonavn": navn,
            "ib": ib,
            "ub": ub,
            "netto": netto,
        }
    )


def _workspace_item(
    *,
    current_a07: str = "",
    current_group: str = "",
    current_tags: tuple[str, ...] = (),
    suggested_a07: str | None = None,
    suggested_group: str | None = None,
    suggested_tags: tuple[str, ...] | None = None,
    locked: bool = False,
):
    def _field(value):
        return SimpleNamespace(value=value, display=str(value or ""))

    def _tuple_field(value):
        value_tuple = tuple(value or ())
        return SimpleNamespace(value=value_tuple, display=", ".join(value_tuple))

    return SimpleNamespace(
        current=SimpleNamespace(
            locked=locked,
            a07_code=_field(current_a07),
            control_group=_field(current_group),
            control_tags=_tuple_field(current_tags),
        ),
        suggested=SimpleNamespace(
            a07_code=None if suggested_a07 is None else _field(suggested_a07),
            control_group=None if suggested_group is None else _field(suggested_group),
            control_tags=None if suggested_tags is None else _tuple_field(suggested_tags),
        ),
    )


def test_build_saldobalanse_df_merges_ao_and_mapping(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(
        dataset=pd.DataFrame(
            {
                "Konto": ["1000", "1000", "2000"],
                "Kontonavn": ["Bank", "Bank", "Kostnad"],
                "Beløp": [10.0, -5.0, 2.0],
            }
        )
    )
    base = _make_sb(
        konto=["1000", "2000"],
        navn=["Bank", "Kostnad"],
        ib=[10.0, 0.0],
        ub=[10.0, -5.0],
        netto=[0.0, -5.0],
    )
    adjusted = _make_sb(
        konto=["1000", "2000"],
        navn=["Bank", "Kostnad"],
        ib=[10.0, 0.0],
        ub=[15.0, -5.0],
        netto=[5.0, -5.0],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (base, adjusted, adjusted))
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_mapping_issues",
        lambda _page: [
            UnmappedAccountIssue(
                konto="1000",
                kontonavn="Bank",
                kilde="SB",
                belop=15.0,
                regnr=320,
                regnskapslinje="Avsatt til annen egenkapital",
                mapping_status="override",
            ),
            UnmappedAccountIssue(
                konto="2000",
                kontonavn="Kostnad",
                kilde="HB",
                belop=-3.0,
                regnr=None,
                regnskapslinje="",
                mapping_status="unmapped",
            ),
        ],
    )
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {"1000": "bank"})
    # Hot-path bruker konto_klassifisering.group_label_map() for batch-lookup.
    import konto_klassifisering as _kk
    monkeypatch.setattr(_kk, "group_label_map", lambda scope=None: {"bank": "Bankgruppe"})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)

    row_1000 = df.loc[df["Konto"] == "1000"].iloc[0]
    row_2000 = df.loc[df["Konto"] == "2000"].iloc[0]

    assert int(row_1000["Antall"]) == 2
    assert float(row_1000["UB før ÅO"]) == pytest.approx(10.0)
    assert float(row_1000["UB etter ÅO"]) == pytest.approx(15.0)
    assert float(row_1000["Tilleggspostering"]) == pytest.approx(5.0)
    assert row_1000["Regnskapslinje"] == "Avsatt til annen egenkapital"
    assert row_1000["Mappingstatus"] == "Overstyrt"
    assert row_1000["Gruppe"] == "Bankgruppe"

    assert row_2000["Mappingstatus"] == "Umappet"
    assert pd.isna(row_2000["Regnr"])


def test_build_saldobalanse_df_filters_unmapped_and_search(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(
        dataset=pd.DataFrame(
            {
                "Konto": ["1000", "2000"],
                "Kontonavn": ["Bank", "Gebyr"],
                "Beløp": [1.0, 2.0],
            }
        )
    )
    sb = _make_sb(
        konto=["1000", "2000"],
        navn=["Bank", "Gebyr"],
        ib=[0.0, 0.0],
        ub=[100.0, -50.0],
        netto=[100.0, -50.0],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_mapping_issues",
        lambda _page: [
            UnmappedAccountIssue(
                konto="1000",
                kontonavn="Bank",
                kilde="SB",
                belop=100.0,
                regnr=10,
                regnskapslinje="Bankinnskudd",
                mapping_status="interval",
            ),
            UnmappedAccountIssue(
                konto="2000",
                kontonavn="Gebyr",
                kilde="HB",
                belop=-50.0,
                regnr=350,
                regnskapslinje="Sum overføringer",
                mapping_status="sumline",
            ),
        ],
    )
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    only_unmapped = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        only_unmapped=True,
    )
    searched = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        search_text="bank",
    )

    assert only_unmapped["Konto"].tolist() == ["2000"]
    assert searched["Konto"].tolist() == ["1000"]


def test_build_saldobalanse_df_filters_mapping_source_and_ao(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(
        dataset=pd.DataFrame(
            {
                "Konto": ["1000", "2000", "3000"],
                "Kontonavn": ["Bank", "Gebyr", "AO-konto"],
                "Beløp": [1.0, 2.0, 3.0],
            }
        )
    )
    base = _make_sb(
        konto=["1000", "2000", "3000"],
        navn=["Bank", "Gebyr", "AO-konto"],
        ib=[0.0, 0.0, 0.0],
        ub=[100.0, -50.0, 0.0],
        netto=[100.0, -50.0, 0.0],
    )
    adjusted = _make_sb(
        konto=["1000", "2000", "3000"],
        navn=["Bank", "Gebyr", "AO-konto"],
        ib=[0.0, 0.0, 0.0],
        ub=[125.0, -50.0, 0.0],
        netto=[125.0, -50.0, 0.0],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (base, adjusted, adjusted))
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_mapping_issues",
        lambda _page: [
            UnmappedAccountIssue(
                konto="1000",
                kontonavn="Bank",
                kilde="SB",
                belop=125.0,
                regnr=10,
                regnskapslinje="Bankinnskudd",
                mapping_status="override",
            ),
            UnmappedAccountIssue(
                konto="2000",
                kontonavn="Gebyr",
                kilde="HB",
                belop=-50.0,
                regnr=350,
                regnskapslinje="Sum overføringer",
                mapping_status="sumline",
            ),
            UnmappedAccountIssue(
                konto="3000",
                kontonavn="AO-konto",
                kilde="AO_ONLY",
                belop=0.0,
                regnr=320,
                regnskapslinje="Annen egenkapital",
                mapping_status="interval",
            ),
        ],
    )
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    mapping_filtered = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        mapping_status_filter="Overstyrt",
    )
    source_filtered = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        source_filter="HB",
    )
    ao_filtered = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        only_with_ao=True,
        include_zero=True,
    )

    assert mapping_filtered["Konto"].tolist() == ["1000"]
    assert source_filtered["Konto"].tolist() == ["2000"]
    assert ao_filtered["Konto"].tolist() == ["1000"]


def test_preset_name_for_visible_columns_matches_known_and_custom_presets() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    assert page_saldobalanse._preset_name_for_visible_columns(
        list(page_saldobalanse.COLUMN_PRESETS["Mapping"])
    ) == "Mapping"
    assert page_saldobalanse._preset_name_for_visible_columns(
        ["Konto", "Kontonavn", "UB"]
    ) == "Egendefinert"


def test_build_saldobalanse_df_adds_payroll_columns_and_filters(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000", "5210"], "Beløp": [1.0, 2.0]}))
    sb = _make_sb(
        konto=["5000", "5210"],
        navn=["Lønn til ansatte", "Fri telefon"],
        ib=[0.0, 0.0],
        ub=[525000.0, 8784.0],
        netto=[525000.0, 8784.0],
    )
    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                a07_code="fastloenn",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
                source="manual",
                confidence=0.95,
            )
        },
    )
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)
    only_suggested = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        payroll_scope="Kun forslag",
    )

    row_5000 = df.loc[df["Konto"] == "5000"].iloc[0]
    row_5210 = df.loc[df["Konto"] == "5210"].iloc[0]

    # Assertions restricted to columns that remain in ALL_COLUMNS after the
    # A07-workflow cleanup — payroll-suggestion columns (A07-forslag,
    # A07 OK, RF-1022-forslag, RF-1022 OK, Flagg-forslag, Matchgrunnlag)
    # are no longer part of the Saldobalanse schema and get reindexed out.
    assert row_5000["A07-kode"] == "fastloenn"
    assert "Post 100" in row_5000["RF-1022-post"]
    assert row_5000["Kol"] == "UB"
    assert row_5000["Lønnsstatus"] == "Manuell"
    assert row_5210["A07-kode"] == ""
    assert row_5210["RF-1022-post"] == ""
    assert row_5210["Kol"] == "UB"
    assert row_5210["Lønnsstatus"] == "Forslag"
    assert row_5210["Problem"] != ""
    assert only_suggested["Konto"].tolist() == ["5210"]


def test_build_saldobalanse_df_adds_kol_for_balance_and_profit_loss(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["2940", "3000"], "Belop": [1.0, 2.0]}))
    sb = _make_sb(
        konto=["2940", "3000"],
        navn=["Skyldig feriepenger", "Salgsinntekt"],
        ib=[-743491.69, 0.0],
        ub=[-747698.87, -17095891.74],
        netto=[-4207.18, -17095891.74],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        include_payroll=False,
    )

    assert df.loc[df["Konto"] == "2940", "Kol"].iloc[0] == "Endring"
    assert df.loc[df["Konto"] == "3000", "Kol"].iloc[0] == "UB"


def test_focus_payroll_accounts_switches_to_payroll_preset_and_selects_account() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self, value):
            self.value = value

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    class _Tree:
        def __init__(self) -> None:
            self.selection = None
            self.focused = None
            self.seen = None

        def get_children(self):
            return ("5000", "5210")

        def selection_set(self, value) -> None:
            self.selection = value

        def focus(self, value) -> None:
            self.focused = value

        def see(self, value) -> None:
            self.seen = value

    refresh_calls: list[str] = []
    dummy = SimpleNamespace(
        _var_preset=_Var("Standard"),
        _var_payroll_scope=_Var("Kun uklare"),
        _var_mapping_status=_Var("Overstyrt"),
        _var_source=_Var("HB"),
        _var_only_unmapped=_Var(True),
        _var_only_with_ao=_Var(True),
        _var_search=_Var("bonus"),
        _tree=_Tree(),
        refresh=lambda: refresh_calls.append("refresh"),
    )

    page_saldobalanse.SaldobalansePage.focus_payroll_accounts(
        dummy,
        ["5000"],
        payroll_scope="Kun forslag",
    )

    assert refresh_calls == ["refresh"]
    assert dummy._var_preset.get() == "Lønnsklassifisering"
    assert dummy._var_payroll_scope.get() == "Kun forslag"
    assert dummy._var_mapping_status.get() == page_saldobalanse.FILTER_ALL
    assert dummy._var_source.get() == page_saldobalanse.FILTER_ALL
    assert dummy._var_only_unmapped.get() is False
    assert dummy._var_only_with_ao.get() is False
    assert dummy._var_search.get() == "5000"
    assert dummy._tree.selection == ("5000",)
    assert dummy._tree.focused == "5000"
    assert dummy._tree.seen == "5000"


def test_prepare_context_menu_selection_preserves_existing_multiselect() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Tree:
        def __init__(self) -> None:
            self._selection = ("5000", "5002")
            self._focused = "5000"

        def selection(self):
            return self._selection

        def selection_set(self, value) -> None:
            if isinstance(value, tuple):
                self._selection = tuple(str(item) for item in value)
            else:
                self._selection = (str(value),)

        def focus(self, value=None):
            if value is None:
                return self._focused
            self._focused = str(value)

    refresh_calls: list[str] = []
    dummy = SimpleNamespace(
        _tree=_Tree(),
        _refresh_detail_panel=lambda: refresh_calls.append("refresh"),
    )
    dummy._explicitly_selected_accounts = lambda: page_saldobalanse.SaldobalansePage._explicitly_selected_accounts(dummy)

    page_saldobalanse.SaldobalansePage._prepare_context_menu_selection(dummy, "5002")

    assert dummy._tree._selection == ("5000", "5002")
    assert dummy._tree._focused == "5002"
    assert refresh_calls == ["refresh"]


def test_refresh_restores_visible_multiselect_after_render(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Tree:
        def __init__(self) -> None:
            self.children = ("5000", "5001", "5002")
            self._selection = ("5000", "5002")
            self._focused = "5002"
            self.seen = None

        def selection(self):
            return self._selection

        def selection_set(self, value) -> None:
            if isinstance(value, tuple):
                self._selection = tuple(str(item) for item in value)
            else:
                self._selection = (str(value),)

        def focus(self, value=None):
            if value is None:
                return self._focused
            self._focused = str(value)

        def see(self, value) -> None:
            self.seen = str(value)

        def get_children(self):
            return self.children

    df = pd.DataFrame(
        {
            "Konto": ["5000", "5001", "5002"],
            "Kontonavn": ["Lønn", "Etterlønn", "Feriepenger"],
            "IB": [0.0, 0.0, 0.0],
            "Endring": [100.0, 50.0, 25.0],
            "UB": [100.0, 50.0, 25.0],
        }
    )
    payload = SimpleNamespace(
        df=df,
        profile_document=None,
        history_document=None,
        catalog=None,
        suggestions={},
        classification_items={},
    )

    monkeypatch.setattr(page_saldobalanse, "build_saldobalanse_payload", lambda **_kwargs: payload)
    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", lambda: [])

    statuses: list[str] = []
    refresh_detail_calls: list[str] = []
    map_button_calls: list[str] = []
    tree = _Tree()

    def _render_df(frame: pd.DataFrame) -> None:
        tree.children = tuple(frame["Konto"].astype(str).tolist())

    dummy = SimpleNamespace(
        _tree=tree,
        _analyse_page=SimpleNamespace(),
        _var_search=None,
        _var_only_unmapped=None,
        _var_include_zero=None,
        _var_mapping_status=None,
        _var_source=None,
        _var_only_with_ao=None,
        _var_payroll_scope=None,
        _should_include_payroll_payload=lambda: True,
        _render_df=_render_df,
        _clear_tree=lambda: None,
        _set_status=lambda text: statuses.append(text),
        _refresh_detail_panel=lambda: refresh_detail_calls.append("refresh"),
        _update_map_button_state=lambda: map_button_calls.append("update"),
    )
    dummy._explicitly_selected_accounts = lambda: page_saldobalanse.SaldobalansePage._explicitly_selected_accounts(dummy)
    dummy._restore_tree_selection = lambda accounts, focused_account="": page_saldobalanse.SaldobalansePage._restore_tree_selection(
        dummy,
        accounts,
        focused_account=focused_account,
    )

    page_saldobalanse.SaldobalansePage.refresh(dummy)

    assert tree._selection == ("5000", "5002")
    assert tree._focused == "5002"
    assert tree.seen == "5002"
    assert statuses == ["3 kontoer | Sum UB: 175,00"]
    assert refresh_detail_calls == ["refresh"]
    assert map_button_calls == ["update"]


def test_build_saldobalanse_df_searches_suggested_payroll_fields(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5210"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5210"],
        navn=["Fri telefon"],
        ib=[0.0],
        ub=[8784.0],
        netto=[8784.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        search_text="elektroniskKommunikasjon",
    )

    assert df["Konto"].tolist() == ["5210"]


def test_build_saldobalanse_df_leaves_payroll_columns_blank_for_weak_irrelevant_hint(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["1280"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["1280"],
        navn=["Kontormaskiner"],
        ib=[0.0],
        ub=[27486.88],
        netto=[27486.88],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)
    monkeypatch.setattr(
        page_saldobalanse.payroll_classification,
        "suggest_a07_code",
        lambda **_kwargs: page_saldobalanse.payroll_classification.AccountProfileSuggestion(
            field_name="a07_code",
            value="fastloenn",
            source="heuristic",
            confidence=0.07,
            reason="Heuristisk treff",
        ),
    )

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)

    row = df.iloc[0]
    assert row["A07-kode"] == ""
    assert row["Lønnsstatus"] == ""
    assert row["Problem"] == ""


def test_build_saldobalanse_df_can_skip_payroll_enrichment(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5210"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5210"],
        navn=["Fri telefon"],
        ib=[0.0],
        ub=[8784.0],
        netto=[8784.0],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    called: list[str] = []

    def _unexpected_payroll_context(_client, _year):
        called.append("context")
        raise AssertionError("payroll context should not be loaded when include_payroll is False")

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", _unexpected_payroll_context)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        include_payroll=False,
    )

    assert called == []
    row = df.iloc[0]
    assert row["A07-kode"] == ""
    assert row["Lønnsstatus"] == ""
    assert row["Problem"] == ""


def test_build_saldobalanse_df_filters_suspicious_saved_payroll_profiles(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["1930", "5000"], "Beløp": [1.0, 2.0]}))
    sb = _make_sb(
        konto=["1930", "5000"],
        navn=["BN Bank - Pensjon", "Lønn til ansatte"],
        ib=[0.0, 0.0],
        ub=[55229.19, -525000.0],
        netto=[55229.19, -525000.0],
    )
    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "1930": AccountProfile(
                account_no="1930",
                a07_code="fastloenn",
                source="manual",
                confidence=1.0,
            ),
            "5000": AccountProfile(
                account_no="5000",
                a07_code="fastloenn",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig",),
                source="manual",
                confidence=1.0,
            ),
        },
    )
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        payroll_scope="Mistenkelig lagret",
    )

    assert df["Konto"].tolist() == ["1930"]
    assert "lagret lønnsklassifisering" in str(df.iloc[0]["Problem"]).lower()


def test_should_include_payroll_payload_depends_on_scope_or_visible_columns() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    # Minimal non-payroll view: no payroll columns visible, scope=Alle.
    non_payroll_cols = ["Konto", "Kontonavn", "IB", "UB", "Regnskapslinje"]

    dummy = SimpleNamespace(
        _var_payroll_scope=_Var(page_saldobalanse.FILTER_ALL),
        _visible_cols=list(non_payroll_cols),
    )

    assert page_saldobalanse.SaldobalansePage._should_include_payroll_payload(dummy) is False

    # DEFAULT_VISIBLE_COLUMNS now includes A07-kode (a payroll column), so the
    # default view pulls payroll data — matches the UI now that A07-kode/
    # RF-1022-post/Detaljklassifisering are part of the standard column set.
    dummy._visible_cols = list(page_saldobalanse.DEFAULT_VISIBLE_COLUMNS)
    assert page_saldobalanse.SaldobalansePage._should_include_payroll_payload(dummy) is True

    dummy._visible_cols = list(page_saldobalanse.COLUMN_PRESETS["Lønn/A07"])
    assert page_saldobalanse.SaldobalansePage._should_include_payroll_payload(dummy) is True

    dummy._visible_cols = list(non_payroll_cols)
    dummy._var_payroll_scope = _Var("Kun forslag")
    assert page_saldobalanse.SaldobalansePage._should_include_payroll_payload(dummy) is True


def test_payroll_preset_contains_core_columns() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    # A07-workflow tracking columns (A07-forslag, A07 OK, RF-1022-forslag,
    # RF-1022 OK, Status) are no longer part of the Saldobalanse schema — the
    # classification workflow lives in the A07 tab. The payroll preset keeps
    # the reference identifiers the auditor still cares about when reviewing
    # accounts from Saldobalanse.
    preset = page_saldobalanse.COLUMN_PRESETS["Lønnsklassifisering"]
    assert "IB" in preset
    assert "A07-kode" in preset
    assert "RF-1022-post" in preset
    for removed in ("A07-forslag", "A07 OK", "RF-1022-forslag", "RF-1022 OK", "Status"):
        assert removed not in preset


def test_apply_best_suggestions_updates_only_actionable_deltas() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    persisted: list[tuple[dict[str, dict[str, object]], dict[str, object]]] = []
    statuses: list[str] = []

    items = {
        "5000": _workspace_item(
            current_a07="",
            current_group="",
            current_tags=(),
            suggested_a07="fastloenn",
            suggested_group="100_loenn_ol",
            suggested_tags=("aga_pliktig",),
        ),
        "5001": _workspace_item(
            current_a07="fastloenn",
            current_group="100_loenn_ol",
            current_tags=("aga_pliktig",),
            suggested_a07="fastloenn",
            suggested_group="100_loenn_ol",
            suggested_tags=("aga_pliktig",),
        ),
        "5002": _workspace_item(
            current_a07="",
            current_group="",
            current_tags=(),
            suggested_a07="fastloenn",
            locked=True,
        ),
    }

    dummy = SimpleNamespace(
        _selected_accounts=lambda: ["5000", "5001", "5002"],
        _workspace_item_for_account=lambda account_no: items.get(account_no),
        _persist_payroll_updates=lambda updates, **kwargs: persisted.append((updates, kwargs)),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._apply_best_suggestions_to_selected_accounts(dummy)

    assert statuses == []
    assert len(persisted) == 1
    updates, kwargs = persisted[0]
    assert updates == {
        "5000": {
            "a07_code": "fastloenn",
            "control_group": "100_loenn_ol",
            "control_tags": ("aga_pliktig",),
        }
    }
    assert kwargs["feedback_action"] == "approve_suggestion"
    assert "Godkjente forslag på 1 kontoer." in kwargs["status_text"]
    assert "Hoppet over 2." in kwargs["status_text"]


def test_apply_best_suggestions_reports_when_everything_is_skipped() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    persisted: list[object] = []
    statuses: list[str] = []

    items = {
        "5000": _workspace_item(
            current_a07="fastloenn",
            current_group="100_loenn_ol",
            current_tags=("aga_pliktig",),
            suggested_a07="fastloenn",
            suggested_group="100_loenn_ol",
            suggested_tags=("aga_pliktig",),
        ),
        "5001": _workspace_item(
            current_a07="",
            current_group="",
            current_tags=(),
            suggested_a07="fastloenn",
            locked=True,
        ),
        "5002": _workspace_item(),
    }

    dummy = SimpleNamespace(
        _selected_accounts=lambda: ["5000", "5001", "5002"],
        _workspace_item_for_account=lambda account_no: items.get(account_no),
        _persist_payroll_updates=lambda updates, **kwargs: persisted.append((updates, kwargs)),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._apply_best_suggestions_to_selected_accounts(dummy)

    assert persisted == []
    assert len(statuses) == 1
    assert statuses[0].startswith("Ingen forslag godkjent")
    assert "1 i samsvar" in statuses[0]
    assert "1 låst" in statuses[0]
    assert "1 uten forslag" in statuses[0]


def test_apply_history_skips_missing_and_identical_profiles() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    persisted: list[tuple[dict[str, dict[str, object]], dict[str, object]]] = []
    statuses: list[str] = []

    history = AccountProfileDocument(
        client="Test",
        year=2024,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                a07_code="fastloenn",
                control_group="100_loenn_ol",
                control_tags=("aga_pliktig",),
            ),
            "5001": AccountProfile(
                account_no="5001",
                a07_code="fastloenn",
                control_group="100_loenn_ol",
                control_tags=("aga_pliktig",),
            ),
        },
    )
    current_profiles = {
        "5000": AccountProfile(account_no="5000"),
        "5001": AccountProfile(
            account_no="5001",
            a07_code="fastloenn",
            control_group="100_loenn_ol",
            control_tags=("aga_pliktig",),
        ),
    }

    dummy = SimpleNamespace(
        _selected_accounts=lambda: ["5000", "5001", "5002"],
        _history_document=history,
        _ensure_payroll_context_loaded=lambda: None,
        _profile_for_account=lambda account_no: current_profiles.get(account_no),
        _persist_payroll_updates=lambda updates, **kwargs: persisted.append((updates, kwargs)),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._apply_history_to_selected_accounts(dummy)

    assert statuses == []
    assert len(persisted) == 1
    updates, kwargs = persisted[0]
    assert updates == {
        "5000": {
            "a07_code": "fastloenn",
            "control_group": "100_loenn_ol",
            "control_tags": ("aga_pliktig",),
        }
    }
    assert kwargs["feedback_action"] == "use_history"
    assert "Brukte fjorårets klassifisering på 1 kontoer." in kwargs["status_text"]
    assert "Hoppet over 2." in kwargs["status_text"]


def test_rf1022_treatment_text_for_cost_account() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    text = page_saldobalanse._rf1022_treatment_text(
        "5000",
        "Lønn til ansatte",
        ib=0.0,
        endring=7_073_783.57,
        ub=7_073_783.57,
        rf1022_text="Post 100 Lønn o.l.",
    )

    assert "RF-1022: Endring -> kostnadsført 7 073 783,57" == text


def test_rf1022_treatment_text_for_accrual_account() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    text = page_saldobalanse._rf1022_treatment_text(
        "2940",
        "Skyldig feriepenger",
        ib=-743_491.69,
        endring=-4_207.18,
        ub=-747_698.87,
        rf1022_text="Post 100 Lønn o.l.",
    )

    assert "Tillegg tidligere år" not in text
    assert "RF-1022: +|IB| 743 491,69 - |UB| 747 698,87 = -4 207,18" == text


def test_selected_payroll_detail_text_shows_lazy_suggestion_summary(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5210"], "Beløp": [1.0]}))
    df = pd.DataFrame(
        {
            "Konto": ["5210"],
            "Kontonavn": ["Fri telefon"],
            "IB": [0.0],
            "Endring": [8784.0],
            "UB": [8784.0],
        }
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()
    suggestion_cls = page_saldobalanse.payroll_classification.AccountProfileSuggestion
    result = page_saldobalanse.payroll_classification.PayrollSuggestionResult(
        suggestions={
            "a07_code": suggestion_cls(
                field_name="a07_code",
                value="elektroniskKommunikasjon",
                source="heuristic",
                confidence=0.93,
                reason="Navn/alias: telefon",
            ),
            "control_group": suggestion_cls(
                field_name="control_group",
                value="111_naturalytelser",
                source="heuristic",
                confidence=0.93,
                reason="Kode-standard",
            ),
            "control_tags": suggestion_cls(
                field_name="control_tags",
                value=("naturalytelse", "opplysningspliktig", "aga_pliktig"),
                source="heuristic",
                confidence=0.93,
                reason="Kode-standard",
            ),
        },
        payroll_relevant=True,
        payroll_status="Forslag",
    )

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(saldobalanse_payload, "_resolve_payroll_usage_features", lambda _page: {})
    monkeypatch.setattr(saldobalanse_payload.payroll_classification, "classify_payroll_account", lambda **_kwargs: result)

    dummy = SimpleNamespace(
        _df_last=df,
        _payroll_suggestions={},
        _profile_document=None,
        _history_document=None,
        _profile_catalog=None,
        _analyse_page=analyse_page,
        _payroll_context_key=None,
        _payroll_usage_features_cache=None,
        _payroll_usage_cache_key=None,
    )
    dummy._selected_account = lambda: ("5210", "Fri telefon")
    dummy._row_for_account = lambda account_no: df.iloc[0]
    dummy._client_context = lambda: ("Testklient", 2025)
    dummy._ensure_payroll_context_loaded = lambda: page_saldobalanse.SaldobalansePage._ensure_payroll_context_loaded(dummy)
    dummy._ensure_payroll_usage_features_loaded = lambda: page_saldobalanse.SaldobalansePage._ensure_payroll_usage_features_loaded(dummy)
    dummy._payroll_result_for_account = lambda account_no: page_saldobalanse.SaldobalansePage._payroll_result_for_account(dummy, account_no)
    dummy._profile_for_account = lambda account_no: page_saldobalanse.SaldobalansePage._profile_for_account(dummy, account_no)
    dummy._history_profile_for_account = lambda account_no: page_saldobalanse.SaldobalansePage._history_profile_for_account(dummy, account_no)
    dummy._suspicious_profile_issue_for_account = lambda account_no, account_name="", profile=None: page_saldobalanse.SaldobalansePage._suspicious_profile_issue_for_account(
        dummy,
        account_no,
        account_name=account_name,
        profile=profile,
    )
    dummy._next_action_for_account = lambda account_no, account_name="", result=None, profile=None: page_saldobalanse.SaldobalansePage._next_action_for_account(
        dummy,
        account_no,
        account_name=account_name,
        result=result,
        profile=profile,
    )

    text = page_saldobalanse.SaldobalansePage._selected_payroll_detail_text(dummy)

    assert "Forslag A07: elektroniskKommunikasjon" in text
    assert "Forslag RF-1022: Post 111" in text
    assert "Forslag flagg:" in text
    assert "Status: Forslag" in text
    assert "Sikkerhet: 93%" in text
    assert "Match: A07: Navn/alias: telefon" in text
    assert "RF-1022/Flagg: A07-standard" in text
    assert "RF-1022: Endring -> kostnadsført 8 784,00" in text
    assert "Neste: Godkjenn forslag eller åpne klassifisering." in text


def test_selected_payroll_detail_text_prefers_reset_for_suspicious_saved_profile(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    df = pd.DataFrame(
        {
            "Konto": ["1930"],
            "Kontonavn": ["BN Bank - Pensjon"],
            "IB": [0.0],
            "Endring": [55229.0],
            "UB": [55229.0],
        }
    )
    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "1930": AccountProfile(
                account_no="1930",
                account_name="BN Bank - Pensjon",
                a07_code="fastloenn",
                source="manual",
                confidence=1.0,
            )
        },
    )

    dummy = SimpleNamespace(
        _df_last=df,
        _payroll_suggestions={},
        _profile_document=document,
        _history_document=None,
        _profile_catalog=None,
    )
    dummy._selected_account = lambda: ("1930", "BN Bank - Pensjon")
    dummy._row_for_account = lambda account_no: df.iloc[0]
    dummy._profile_for_account = lambda account_no: page_saldobalanse.SaldobalansePage._profile_for_account(dummy, account_no)
    dummy._suspicious_profile_issue_for_account = lambda account_no, account_name="", profile=None: page_saldobalanse.SaldobalansePage._suspicious_profile_issue_for_account(
        dummy,
        account_no,
        account_name=account_name,
        profile=profile,
    )
    dummy._history_profile_for_account = lambda account_no: None
    dummy._next_action_for_account = lambda account_no, account_name="", result=None, profile=None: page_saldobalanse.SaldobalansePage._next_action_for_account(
        dummy,
        account_no,
        account_name=account_name,
        result=result,
        profile=profile,
    )
    dummy._payroll_result_for_account = lambda account_no: None

    text = page_saldobalanse.SaldobalansePage._selected_payroll_detail_text(dummy)

    assert "Lagret A07: fastloenn" in text
    assert "Bank-/kassekonto har lagret lønnsklassifisering." in text
    assert "Neste: Nullstill lagret lønnsklassifisering." in text


def test_selected_payroll_detail_text_explains_accrual_treatment() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    df = pd.DataFrame(
        {
            "Konto": ["2940"],
            "Kontonavn": ["Skyldig feriepenger"],
            "IB": [-743_491.69],
            "Endring": [-4_207.18],
            "UB": [-747_698.87],
        }
    )

    dummy = SimpleNamespace(
        _df_last=df,
        _payroll_suggestions={},
        _profile_document=None,
        _history_document=None,
        _profile_catalog=None,
    )
    dummy._selected_account = lambda: ("2940", "Skyldig feriepenger")
    dummy._row_for_account = lambda account_no: df.iloc[0]
    dummy._profile_for_account = lambda account_no: None
    dummy._suspicious_profile_issue_for_account = lambda account_no, account_name="", profile=None: ""
    dummy._history_profile_for_account = lambda account_no: None
    dummy._next_action_for_account = lambda account_no, account_name="", result=None, profile=None: ""
    suggestion_cls = page_saldobalanse.payroll_classification.AccountProfileSuggestion
    result = page_saldobalanse.payroll_classification.PayrollSuggestionResult(
        suggestions={
            "control_group": suggestion_cls(
                field_name="control_group",
                value="100_loenn_ol",
                source="heuristic",
                confidence=0.93,
                reason="Navn/alias: feriepenger",
            ),
        },
        payroll_relevant=True,
        payroll_status="Forslag",
    )
    dummy._payroll_result_for_account = lambda account_no: result

    text = page_saldobalanse.SaldobalansePage._selected_payroll_detail_text(dummy)

    assert "Forslag RF-1022: Post 100" in text
    assert "RF-1022: +|IB| 743 491,69 - |UB| 747 698,87 = -4 207,18" in text


def test_update_map_button_state_enables_visible_payroll_actions() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Button:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def state(self, values) -> None:
            self.calls.append(tuple(values))

    dummy = SimpleNamespace(
        _btn_use_suggestion=_Button(),
        _btn_use_history=_Button(),
        _btn_reset_suspicious=_Button(),
        _btn_map=_Button(),
        _btn_classify=_Button(),
        _sync_selection_actions_visibility=lambda: None,
    )
    dummy._selected_accounts = lambda: ["5210"]
    dummy._has_history_for_selected_accounts = lambda: True
    dummy._has_strict_suggestions_for_selected_accounts = lambda: True
    dummy._selected_suspicious_accounts = lambda: []

    page_saldobalanse.SaldobalansePage._update_map_button_state(dummy)

    assert dummy._btn_use_suggestion.calls[-1] == ("!disabled",)
    assert dummy._btn_use_history.calls[-1] == ("!disabled",)
    assert dummy._btn_reset_suspicious.calls[-1] == ("disabled",)
    assert dummy._btn_map.calls[-1] == ("!disabled",)
    assert dummy._btn_classify.calls[-1] == ("!disabled",)


def test_update_map_button_state_enables_reset_for_suspicious_selection() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Button:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def state(self, values) -> None:
            self.calls.append(tuple(values))

    dummy = SimpleNamespace(
        _btn_use_suggestion=_Button(),
        _btn_use_history=_Button(),
        _btn_reset_suspicious=_Button(),
        _btn_map=_Button(),
        _btn_classify=_Button(),
        _sync_selection_actions_visibility=lambda: None,
    )
    dummy._selected_accounts = lambda: ["1930", "5000"]
    dummy._has_history_for_selected_accounts = lambda: False
    dummy._has_strict_suggestions_for_selected_accounts = lambda: False
    dummy._selected_suspicious_accounts = lambda: ["1930"]

    page_saldobalanse.SaldobalansePage._update_map_button_state(dummy)

    assert dummy._btn_reset_suspicious.calls[-1] == ("!disabled",)


def test_clear_selected_suspicious_payroll_fields_only_resets_flagged_accounts() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    persisted: list[dict[str, dict[str, object]]] = []
    statuses: list[str] = []

    dummy = SimpleNamespace()
    dummy._selected_suspicious_accounts = lambda: ["1930", "2020"]
    dummy._persist_payroll_updates = lambda updates, **kwargs: persisted.append(updates)
    dummy._set_status = lambda text: statuses.append(text)

    page_saldobalanse.SaldobalansePage._clear_selected_suspicious_payroll_fields(dummy)

    assert statuses == []
    assert persisted == [
        {
            "1930": {"a07_code": "", "control_group": "", "control_tags": ()},
            "2020": {"a07_code": "", "control_group": "", "control_tags": ()},
        }
    ]


def test_clear_selected_suspicious_payroll_fields_reports_when_nothing_is_flagged() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    persisted: list[dict[str, dict[str, object]]] = []
    statuses: list[str] = []

    dummy = SimpleNamespace()
    dummy._selected_suspicious_accounts = lambda: []
    dummy._persist_payroll_updates = lambda updates, **kwargs: persisted.append(updates)
    dummy._set_status = lambda text: statuses.append(text)

    page_saldobalanse.SaldobalansePage._clear_selected_suspicious_payroll_fields(dummy)

    assert persisted == []
    assert statuses == ["Fant ingen mistenkelige lagrede lønnsklassifiseringer i utvalget."]


def test_on_work_mode_changed_resets_and_restores_hidden_filters_for_payroll_mode() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload
    calls: list[str] = []

    class _Var:
        def __init__(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    dummy = SimpleNamespace(
        _var_work_mode=_Var(page_saldobalanse.WORK_MODE_PAYROLL),
        _var_mapping_status=_Var("Overstyrt"),
        _var_source=_Var("HB"),
        _var_only_unmapped=_Var(True),
        _var_include_zero=_Var(True),
        _var_only_with_ao=_Var(True),
        _var_include_ao_fallback=_Var(True),
        _visible_cols=["Konto", "Kontonavn", "UB"],
        _column_order=["Konto", "Kontonavn", "UB"],
        _saved_non_payroll_visible_cols=None,
        _saved_non_payroll_order=None,
        _saved_non_payroll_filters=None,
        _apply_visible_columns=lambda: calls.append("apply"),
        _sync_preset_var=lambda: calls.append("preset"),
        _sync_mode_ui=lambda: calls.append("sync"),
        _is_payroll_mode=lambda: True,
    )
    dummy._var_value = lambda var, default="": page_saldobalanse.SaldobalansePage._var_value(dummy, var, default)
    dummy._set_var_value = lambda var, value: page_saldobalanse.SaldobalansePage._set_var_value(dummy, var, value)
    dummy._save_non_payroll_filters = lambda: page_saldobalanse.SaldobalansePage._save_non_payroll_filters(dummy)
    dummy._reset_hidden_filters_for_payroll_mode = lambda: page_saldobalanse.SaldobalansePage._reset_hidden_filters_for_payroll_mode(dummy)
    dummy._restore_non_payroll_filters = lambda: page_saldobalanse.SaldobalansePage._restore_non_payroll_filters(dummy)

    page_saldobalanse.SaldobalansePage._on_work_mode_changed(dummy, refresh=False)

    assert dummy._var_mapping_status.get() == page_saldobalanse.FILTER_ALL
    assert dummy._var_source.get() == page_saldobalanse.FILTER_ALL
    assert dummy._var_only_unmapped.get() is False
    assert dummy._var_include_zero.get() is False
    assert dummy._var_only_with_ao.get() is False
    assert dummy._saved_non_payroll_filters == {
        "mapping_status": "Overstyrt",
        "source": "HB",
        "only_unmapped": True,
        "include_zero": True,
        "only_with_ao": True,
        "include_ao": True,
    }
    assert dummy._visible_cols == list(page_saldobalanse.COLUMN_PRESETS["Lønnsklassifisering"])

    dummy._is_payroll_mode = lambda: False
    page_saldobalanse.SaldobalansePage._on_work_mode_changed(dummy, refresh=False)

    assert dummy._var_mapping_status.get() == "Overstyrt"
    assert dummy._var_source.get() == "HB"
    assert dummy._var_only_unmapped.get() is True
    assert dummy._var_include_zero.get() is True
    assert dummy._var_only_with_ao.get() is True
    assert dummy._saved_non_payroll_filters is None
    assert dummy._saved_non_payroll_visible_cols is None
    assert dummy._saved_non_payroll_order is None


def test_sync_mode_ui_hides_source_filter_and_relabels_payroll_controls() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Widget:
        def __init__(self, name: str) -> None:
            self.name = name
            self.config: dict[str, object] = {}

        def configure(self, **kwargs) -> None:
            self.config.update(kwargs)

    shown: list[tuple[str, bool]] = []
    pane_shown: list[tuple[str, bool, int]] = []
    dummy = SimpleNamespace(
        _is_payroll_mode=lambda: True,
        _show_grid_widget=lambda widget, show: shown.append((widget.name, show)) if widget is not None else None,
        _show_pane_widget=lambda widget, show, weight=1: pane_shown.append((widget.name, show, weight)) if widget is not None else None,
        _sync_selection_actions_visibility=lambda: shown.append(("selection_sync", True)),
        _lbl_mode=_Widget("mode_label"),
        _cmb_mode=_Widget("mode_combo"),
        _btn_leave_payroll=_Widget("leave_payroll"),
        _lbl_preset=_Widget("preset_label"),
        _cmb_preset=_Widget("preset_combo"),
        _lbl_mapping_status=_Widget("mapping_label"),
        _cmb_mapping_status=_Widget("mapping_combo"),
        _lbl_source=_Widget("source_label"),
        _cmb_source=_Widget("source_combo"),
        _btn_columns=_Widget("columns"),
        _chk_include_ao=_Widget("include_ao"),
        _chk_only_unmapped=_Widget("only_unmapped"),
        _chk_include_zero=_Widget("include_zero"),
        _chk_only_with_ao=_Widget("only_with_ao"),
        _btn_use_suggestion=_Widget("use_suggestion"),
        _btn_use_history=_Widget("use_history"),
        _btn_reset_suspicious=_Widget("reset_suspicious"),
        _btn_map=_Widget("map"),
        _btn_primary_action=_Widget("primary"),
        _btn_classify=_Widget("classify"),
        _details_frame=_Widget("details"),
        _lbl_payroll_scope=_Widget("payroll_scope"),
    )

    page_saldobalanse.SaldobalansePage._sync_mode_ui(dummy)

    assert ("mode_label", False) in shown
    assert ("mode_combo", False) in shown
    assert ("leave_payroll", True) in shown
    assert ("source_label", False) in shown
    assert ("source_combo", False) in shown
    assert ("primary", True) in shown
    assert pane_shown[-1] == ("details", True, 3)
    assert dummy._lbl_payroll_scope.config["text"] == "Kø:"
    assert dummy._btn_classify.config["text"] == "Åpne klassifisering..."
    assert dummy._details_frame.config["text"] == "Detaljer"


def test_leave_payroll_mode_switches_back_to_standard() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self):
            return self.value

        def set(self, value: str) -> None:
            self.value = value

    calls: list[bool] = []
    dummy = SimpleNamespace(
        _var_work_mode=_Var(page_saldobalanse.WORK_MODE_PAYROLL),
        _on_work_mode_changed=lambda: calls.append(True),
    )

    page_saldobalanse.SaldobalansePage._leave_payroll_mode(dummy)

    assert dummy._var_work_mode.get() == page_saldobalanse.WORK_MODE_STANDARD
    assert calls == [True]


def test_sync_selection_actions_visibility_summarizes_selected_payroll_accounts() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    class _Widget:
        def __init__(self) -> None:
            self.name = "selection_actions"

    shown: list[bool] = []
    dummy = SimpleNamespace(
        _selection_actions_frame=_Widget(),
        _selection_actions_summary_var=_Var(),
        _is_payroll_mode=lambda: True,
        _selected_accounts=lambda: ["1925", "1950"],
        _df_last=pd.DataFrame(
            {
                "Konto": ["1925", "1950"],
                "Endring": [-28047.49, 109484.0],
                "UB": [647.26, 465291.26],
            }
        ),
        _selected_workspace_items=lambda: [
            SimpleNamespace(queue_name=page_saldobalanse.classification_workspace.QUEUE_READY),
            SimpleNamespace(queue_name=page_saldobalanse.classification_workspace.QUEUE_SUSPICIOUS),
        ],
        _determine_primary_action=lambda items: (
            page_saldobalanse.classification_workspace.NEXT_OPEN_CLASSIFIER,
            "Åpne klassifisering",
        ),
        _show_grid_widget=lambda widget, show: shown.append(show),
    )

    page_saldobalanse.SaldobalansePage._sync_selection_actions_visibility(dummy)

    assert shown == [True]
    summary = dummy._selection_actions_summary_var.get()
    assert "2 valgt" in summary
    assert "IB 0,00" in summary
    assert "Endring 81 436,51" in summary
    assert "UB 465 938,52" in summary
    assert "Neste: Åpne klassifisering" in summary


def test_refresh_detail_panel_shows_payroll_intro_without_selection() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    statuses: list[str] = []
    dummy = SimpleNamespace(
        _detail_headline_var=_Var(),
        _detail_current_var=_Var(),
        _detail_suggested_var=_Var(),
        _detail_treatment_var=_Var(),
        _detail_next_var=_Var(),
        _detail_why_var=_Var(),
        _selected_workspace_items=lambda: [],
        _determine_primary_action=lambda items: ("", ""),
        _current_primary_action="",
        _is_payroll_mode=lambda: True,
        _set_status_detail=lambda text: statuses.append(text),
    )
    dummy._payroll_intro_sections = lambda: page_saldobalanse.SaldobalansePage._payroll_intro_sections(dummy)

    page_saldobalanse.SaldobalansePage._refresh_detail_panel(dummy)

    assert dummy._detail_headline_var.get() == "Lønnsklassifisering"
    assert "Mistenkelig lagret" in dummy._detail_current_var.get()
    assert "1. Velg kø" in dummy._detail_suggested_var.get()
    assert "RF-1022-behandling vises her" in dummy._detail_treatment_var.get()
    assert "Velg en konto" in dummy._detail_next_var.get()
    assert statuses[-1] == "Velg kø og konto for å starte."


def test_refresh_detail_panel_guides_multi_selection() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    statuses: list[str] = []
    dummy = SimpleNamespace(
        _detail_headline_var=_Var(),
        _detail_current_var=_Var(),
        _detail_suggested_var=_Var(),
        _detail_treatment_var=_Var(),
        _detail_next_var=_Var(),
        _detail_why_var=_Var(),
        _selected_workspace_items=lambda: [
            SimpleNamespace(queue_name=page_saldobalanse.classification_workspace.QUEUE_READY),
            SimpleNamespace(queue_name=page_saldobalanse.classification_workspace.QUEUE_REVIEW),
        ],
        _determine_primary_action=lambda items: (
            page_saldobalanse.classification_workspace.NEXT_OPEN_CLASSIFIER,
            "Åpne klassifisering",
        ),
        _current_primary_action="",
        _is_payroll_mode=lambda: True,
        _set_status_detail=lambda text: statuses.append(text),
    )
    dummy._selection_detail_sections = lambda items, button_label="": page_saldobalanse.SaldobalansePage._selection_detail_sections(
        dummy,
        items,
        button_label=button_label,
    )

    page_saldobalanse.SaldobalansePage._refresh_detail_panel(dummy)

    assert dummy._detail_headline_var.get() == "2 valgte kontoer"
    assert "Utvalg" in dummy._detail_current_var.get()
    assert "Klar til forslag: 1" in dummy._detail_current_var.get()
    assert "Trenger vurdering: 1" in dummy._detail_current_var.get()
    assert "Primærhandling: Åpne klassifisering" in dummy._detail_suggested_var.get()
    assert "RF-1022-behandling må vurderes per konto" in dummy._detail_treatment_var.get()
    assert "Åpne klassifisering" in dummy._detail_next_var.get()
    assert statuses[-1] == "2 valgte kontoer | Åpne klassifisering"
def test_append_selected_account_name_to_rf1022_alias_is_disabled(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse

    saved: dict[str, object] = {}
    monkeypatch.setattr(
        page_saldobalanse.classification_config,
        "save_catalog_document",
        lambda data: (saved.setdefault("document", data), Path("account_classification_catalog.json"))[1],
    )

    statuses: list[str] = []
    dummy = SimpleNamespace(
        _selected_account=lambda: ("5002", "Etterl?nn /uferiepenger"),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._append_selected_account_name_to_rf1022_alias(dummy, "100_loenn_ol")

    assert saved == {}
    assert "RF-1022-aliaser er fjernet" in statuses[-1]

def test_append_selected_account_name_to_a07_alias_refreshes_after_save(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.frontend.actions as saldobalanse_actions
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    calls: list[str] = []
    learned: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(
        saldobalanse_actions,
        "append_a07_rule_keyword",
        lambda code, term, exclude=False: (
            learned.append((code, term, exclude)),
            SimpleNamespace(path=Path("global_full_a07_rulebook.json")),
        )[1],
    )
    monkeypatch.setattr(
        page_saldobalanse.payroll_classification,
        "invalidate_runtime_caches",
        lambda: calls.append("invalidate"),
    )
    monkeypatch.setattr(
        page_saldobalanse.session,
        "APP",
        SimpleNamespace(page_a07=None, page_analyse=None),
        raising=False,
    )

    statuses: list[str] = []
    dummy = SimpleNamespace(
        _selected_account=lambda: ("5000", "LÃ¸nn til ansatte"),
        refresh=lambda: calls.append("refresh"),
        _set_status=lambda text: statuses.append(text),
    )
    dummy._after_rule_learning_saved = (
        lambda message: page_saldobalanse.SaldobalansePage._after_rule_learning_saved(dummy, message)
    )

    page_saldobalanse.SaldobalansePage._append_selected_account_name_to_a07_alias(dummy, "fastloenn")

    assert calls == ["invalidate", "refresh"]
    assert learned == [("fastloenn", "LÃ¸nn til ansatte", False)]
    assert "A07-alias" in statuses[-1]
    assert "global_full_a07_rulebook.json" in statuses[-1]


def test_export_current_view_to_excel_uses_visible_columns_and_selected_sheet(monkeypatch, tmp_path) -> None:
    import analyse_export_excel
    import controller_export
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    captured: dict[str, object] = {}
    statuses: list[str] = []
    export_path = tmp_path / "saldobalanse_test.xlsx"

    monkeypatch.setattr(
        analyse_export_excel,
        "open_save_dialog",
        lambda **_kwargs: str(export_path),
    )

    def _capture_export(path, *_, sheets=None, **__):
        captured["path"] = path
        captured["sheets"] = sheets
        return str(path)

    monkeypatch.setattr(controller_export, "export_to_excel", _capture_export)

    dummy = SimpleNamespace(
        _df_last=pd.DataFrame(
            {
                "Konto": ["5000", "5002"],
                "Kontonavn": ["Lønn til ansatte", "Etterlønn /uferiepenger"],
                "IB": [0.0, 0.0],
                "Endring": [100.0, 50.0],
                "UB": [100.0, 50.0],
                "A07-kode": ["fastloenn", ""],
                "RF-1022-post": ["Post 100 Lønn o.l.", ""],
            }
        ),
        _column_order=["Konto", "Kontonavn", "Endring", "A07-kode", "RF-1022-post", "IB", "UB"],
        _visible_cols=["Konto", "Kontonavn", "Endring", "A07-kode"],
        _selected_accounts=lambda: ["5002"],
        _client_context=lambda: ("Test/Klient", 2025),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._export_current_view_to_excel(dummy)

    assert captured["path"] == str(export_path)
    sheets = captured["sheets"]
    assert isinstance(sheets, dict)
    assert list(sheets.keys()) == ["Saldobalanse", "Valgte kontoer"]
    full_df = sheets["Saldobalanse"]
    selected_df = sheets["Valgte kontoer"]
    assert list(full_df.columns) == ["Konto", "Kontonavn", "Endring", "A07-kode"]
    assert full_df["Konto"].tolist() == ["5000", "5002"]
    assert selected_df["Konto"].tolist() == ["5002"]
    assert "Valgte kontoer: 1" in statuses[-1]


def test_export_current_view_to_excel_reports_when_nothing_to_export() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    statuses: list[str] = []
    dummy = SimpleNamespace(
        _df_last=pd.DataFrame(),
        _set_status=lambda text: statuses.append(text),
    )

    page_saldobalanse.SaldobalansePage._export_current_view_to_excel(dummy)

    assert statuses == ["Ingen rader å eksportere fra saldobalansen."]


def test_build_saldobalanse_df_decorates_only_filtered_subset(monkeypatch) -> None:
    """Cheap filters (only_unmapped etc.) must narrow the set before payroll decoration runs."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000", "5210"], "Beløp": [1.0, 2.0]}))
    sb = _make_sb(
        konto=["5000", "5210"],
        navn=["Lønn til ansatte", "Fri telefon"],
        ib=[0.0, 0.0],
        ub=[525000.0, 8784.0],
        netto=[525000.0, 8784.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_mapping_issues",
        lambda _page: [
            UnmappedAccountIssue(
                konto="5000",
                kontonavn="Lønn til ansatte",
                kilde="HB",
                belop=525000.0,
                regnr=None,
                regnskapslinje="",
                mapping_status="unmapped",
            ),
        ],
    )
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    decorated_accounts: list[list[str]] = []
    original_decorate = page_saldobalanse._decorate_with_payroll_columns

    def _spy_decorate(df, *, client, year, usage_features, **kwargs):
        decorated_accounts.append(list(df["Konto"].astype(str)))
        return original_decorate(df, client=client, year=year, usage_features=usage_features, **kwargs)

    monkeypatch.setattr(saldobalanse_payload, "_decorate_with_payroll_columns", _spy_decorate)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        only_unmapped=True,
    )

    assert df["Konto"].tolist() == ["5000"]
    # Decorate must run only on the filtered subset — not on both accounts.
    assert decorated_accounts == [["5000"]]


def test_schedule_refresh_coalesces_rapid_triggers() -> None:
    """Multiple rapid _schedule_refresh calls must cancel earlier timers and run refresh once."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    after_calls: list[tuple[int, object]] = []
    cancelled: list[object] = []
    next_id = {"n": 0}
    refresh_calls: list[int] = []

    def _fake_after(delay, callback):
        next_id["n"] += 1
        token = f"after#{next_id['n']}"
        after_calls.append((delay, token))
        return token

    def _fake_after_cancel(token):
        cancelled.append(token)

    dummy = SimpleNamespace(
        _refresh_after_id=None,
        after=_fake_after,
        after_cancel=_fake_after_cancel,
        refresh=lambda: refresh_calls.append(1),
        _run_scheduled_refresh=lambda: None,
    )

    page_saldobalanse.SaldobalansePage._schedule_refresh(dummy, 200)
    page_saldobalanse.SaldobalansePage._schedule_refresh(dummy, 200)
    page_saldobalanse.SaldobalansePage._schedule_refresh(dummy, 200)

    assert cancelled == ["after#1", "after#2"]
    assert dummy._refresh_after_id == "after#3"
    assert refresh_calls == []

    # Fire the scheduled refresh.
    page_saldobalanse.SaldobalansePage._run_scheduled_refresh(dummy)
    assert refresh_calls == [1]
    assert dummy._refresh_after_id is None


def test_refresh_cancels_pending_scheduled_refresh() -> None:
    """A direct refresh() call must cancel any queued debounced refresh to avoid duplicate work."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    cancelled: list[object] = []

    def _fake_after_cancel(token):
        cancelled.append(token)

    dummy = SimpleNamespace(
        _refresh_after_id="after#42",
        after_cancel=_fake_after_cancel,
    )

    page_saldobalanse.SaldobalansePage._cancel_scheduled_refresh(dummy)

    assert cancelled == ["after#42"]
    assert dummy._refresh_after_id is None


def _build_cache_refresh_dummy(page_saldobalanse, analyse_page, **extras):
    tree_children: list[str] = []

    class _Tree:
        def focus(self):
            return ""

    dummy = SimpleNamespace(
        _tree=_Tree(),
        _analyse_page=analyse_page,
        _var_search=SimpleNamespace(get=lambda: extras.pop("search", "") if "search" in extras else ""),
        _var_only_unmapped=None,
        _var_include_zero=None,
        _var_mapping_status=None,
        _var_source=None,
        _var_only_with_ao=None,
        _var_payroll_scope=None,
        _should_include_payroll_payload=lambda: True,
        _render_df=lambda _df: tree_children.append("render"),
        _clear_tree=lambda: None,
        _set_status=lambda _text: None,
        _refresh_detail_panel=lambda: None,
        _update_map_button_state=lambda: None,
        _base_payload_cache=None,
        _base_payload_cache_key=None,
        _df_last=None,
        _profile_document=None,
        _history_document=None,
        _profile_catalog=None,
        _payroll_suggestions={},
        _classification_items={},
        _a07_options=[],
        _client_context=lambda: ("Testklient", 2025),
    )
    dummy._explicitly_selected_accounts = lambda: ()
    dummy._restore_tree_selection = lambda _accounts, focused_account="": None
    return dummy


def test_refresh_reuses_base_payload_cache_for_search_changes(monkeypatch) -> None:
    """Changing search_text must NOT rebuild the expensive payroll-decorated base."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5000", "5210"],
        navn=["Lønn til ansatte", "Fri telefon"],
        ib=[0.0, 0.0],
        ub=[525000.0, 8784.0],
        netto=[525000.0, 8784.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)
    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", lambda: [])

    decorate_calls = {"n": 0}
    original = page_saldobalanse._decorate_with_payroll_columns

    def _spy(df, *, client, year, usage_features, **kwargs):
        decorate_calls["n"] += 1
        return original(df, client=client, year=year, usage_features=usage_features, **kwargs)

    monkeypatch.setattr(saldobalanse_payload, "_decorate_with_payroll_columns", _spy)

    dummy = _build_cache_refresh_dummy(page_saldobalanse, analyse_page)

    # First refresh: cache miss → decorate runs.
    dummy._var_search = SimpleNamespace(get=lambda: "")
    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 1
    assert dummy._base_payload_cache is not None

    # Second refresh with new search text: cache hit → decorate must NOT run again.
    dummy._var_search = SimpleNamespace(get=lambda: "lønn")
    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 1, "search-only change must reuse the cached decorated base"


def test_refresh_reuses_base_payload_cache_for_payroll_scope_changes(monkeypatch) -> None:
    """Changing payroll_scope must NOT rebuild the expensive payroll-decorated base."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5000", "5210"],
        navn=["Lønn til ansatte", "Fri telefon"],
        ib=[0.0, 0.0],
        ub=[525000.0, 8784.0],
        netto=[525000.0, 8784.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)
    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", lambda: [])

    decorate_calls = {"n": 0}
    original = page_saldobalanse._decorate_with_payroll_columns

    def _spy(df, *, client, year, usage_features, **kwargs):
        decorate_calls["n"] += 1
        return original(df, client=client, year=year, usage_features=usage_features, **kwargs)

    monkeypatch.setattr(saldobalanse_payload, "_decorate_with_payroll_columns", _spy)

    dummy = _build_cache_refresh_dummy(page_saldobalanse, analyse_page)
    dummy._var_payroll_scope = SimpleNamespace(get=lambda: page_saldobalanse.FILTER_ALL)

    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 1

    # Change only payroll_scope: cache must still be reused.
    dummy._var_payroll_scope = SimpleNamespace(get=lambda: "Kun forslag")
    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 1, "payroll_scope change must reuse cached decorated base"


def test_hard_refresh_invalidates_payload_cache(monkeypatch) -> None:
    """Explicit Oppfrisk must drop the cached base and force a fresh decorate."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5000"],
        navn=["Lønn til ansatte"],
        ib=[0.0],
        ub=[525000.0],
        netto=[525000.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", lambda _client, _year: (document, history, catalog))
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)
    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", lambda: [])

    decorate_calls = {"n": 0}
    original = page_saldobalanse._decorate_with_payroll_columns

    def _spy(df, *, client, year, usage_features, **kwargs):
        decorate_calls["n"] += 1
        return original(df, client=client, year=year, usage_features=usage_features, **kwargs)

    monkeypatch.setattr(saldobalanse_payload, "_decorate_with_payroll_columns", _spy)

    dummy = _build_cache_refresh_dummy(page_saldobalanse, analyse_page)
    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 1

    # Simulate Oppfrisk: invalidate, then refresh.
    page_saldobalanse.SaldobalansePage._invalidate_payload_cache(dummy)
    assert dummy._base_payload_cache is None
    assert dummy._base_payload_cache_key is None

    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert decorate_calls["n"] == 2, "hard refresh must rebuild the decorated base"


def test_invalidate_payload_cache_clears_state() -> None:
    """_invalidate_payload_cache must reset both cache object and key."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    dummy = SimpleNamespace(
        _base_payload_cache=SimpleNamespace(df=pd.DataFrame()),
        _base_payload_cache_key=("some", "key"),
    )

    page_saldobalanse.SaldobalansePage._invalidate_payload_cache(dummy)

    assert dummy._base_payload_cache is None
    assert dummy._base_payload_cache_key is None


def test_build_saldobalanse_payload_accepts_precomputed_base(monkeypatch) -> None:
    """If base_payload is provided, build_saldobalanse_payload must not rerun the decorate pipeline."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    def _fail(*_args, **_kwargs):
        raise AssertionError("_build_decorated_base_payload must not be called when base_payload is supplied")

    monkeypatch.setattr(saldobalanse_payload, "_build_decorated_base_payload", _fail)

    base_df = pd.DataFrame(
        {
            "Konto": ["5000", "5210"],
            "Kontonavn": ["Lønn", "Telefon"],
            "Gruppe": ["", ""],
            "IB": [0.0, 0.0],
            "Endring": [100.0, 50.0],
            "UB": [100.0, 50.0],
            "UB før ÅO": [100.0, 50.0],
            "UB etter ÅO": [100.0, 50.0],
            "Tilleggspostering": [0.0, 0.0],
            "Antall": [0, 0],
            "Regnskapslinje": ["", ""],
            "Mappingstatus": ["", ""],
            "Regnr": pd.Series([pd.NA, pd.NA], dtype="Int64"),
            "Kilde": ["", ""],
            "_mapping_status_code": ["", ""],
            "Nåværende": ["", ""],
            "Forslag": ["", ""],
            "Status": ["", ""],
            "A07-kode": ["", ""],
            "A07-forslag": ["", ""],
            "A07 OK": ["", ""],
            "RF-1022-post": ["", ""],
            "RF-1022-forslag": ["", ""],
            "RF-1022 OK": ["", ""],
            "Lønnsflagg": ["", ""],
            "Flagg-forslag": ["", ""],
            "Lønnsstatus": ["", ""],
            "Matchgrunnlag": ["", ""],
            "Problem": ["", ""],
            "Profilkilde": ["", ""],
            "Sikkerhet": ["", ""],
            "Låst": ["", ""],
        }
    )
    base = page_saldobalanse.SaldobalanseBasePayload(
        df=base_df,
        profile_document=None,
        history_document=None,
        catalog=None,
        suggestions={},
        classification_items={},
        include_payroll=True,
    )

    payload = page_saldobalanse.build_saldobalanse_payload(
        analyse_page=SimpleNamespace(),
        search_text="lønn",
        base_payload=base,
    )

    # Post-filter step (search) must still apply to cached base.
    assert payload.df["Konto"].tolist() == ["5000"]


def test_build_decorated_base_payload_uses_preloaded_context(monkeypatch) -> None:
    """When preloaded document/history/catalog are passed, _load_payroll_context must NOT be called."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    sb = _make_sb(
        konto=["5000"],
        navn=["Lønn"],
        ib=[0.0],
        ub=[100.0],
        netto=[100.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    load_calls = {"n": 0}

    def _fail_if_called(_client, _year):
        load_calls["n"] += 1
        return document, history, catalog

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", _fail_if_called)

    # Also verify usage_features is not re-resolved when provided
    usage_calls = {"n": 0}
    original_resolve = page_saldobalanse._resolve_payroll_usage_features

    def _count_usage(analyse_page):
        usage_calls["n"] += 1
        return original_resolve(analyse_page)

    monkeypatch.setattr(saldobalanse_payload, "_resolve_payroll_usage_features", _count_usage)

    result = page_saldobalanse._build_decorated_base_payload(
        analyse_page=SimpleNamespace(dataset=pd.DataFrame()),
        profile_document=document,
        history_document=history,
        catalog=catalog,
        usage_features={},
    )

    assert load_calls["n"] == 0, "preloaded context must bypass _load_payroll_context"
    assert usage_calls["n"] == 0, "preloaded usage_features must bypass _resolve_payroll_usage_features"
    assert not result.df.empty
    assert result.profile_document is document
    assert result.history_document is history
    assert result.catalog is catalog


def test_build_decorated_base_payload_without_preloaded_args_still_loads(monkeypatch) -> None:
    """Without preloaded args, loading path must still execute (back-compat)."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    sb = _make_sb(
        konto=["5000"],
        navn=["Lønn"],
        ib=[0.0],
        ub=[100.0],
        netto=[100.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    load_calls = {"n": 0}

    def _loader(_client, _year):
        load_calls["n"] += 1
        return document, history, catalog

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", _loader)

    page_saldobalanse._build_decorated_base_payload(
        analyse_page=SimpleNamespace(dataset=pd.DataFrame()),
    )

    assert load_calls["n"] == 1


def test_refresh_uses_side_caches_for_payroll_context(monkeypatch) -> None:
    """On a cache miss, refresh() must pull document/history/catalog from page-level
    side caches (``_ensure_payroll_context_loaded`` / ``_ensure_payroll_usage_features_loaded``)
    and pass them into _build_decorated_base_payload, so _load_payroll_context is not hit."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["5000"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["5000"],
        navn=["Lønn"],
        ib=[0.0],
        ub=[525000.0],
        netto=[525000.0],
    )
    document = AccountProfileDocument(client="Testklient", year=2025)
    history = AccountProfileDocument(client="Testklient", year=2024)
    catalog = page_saldobalanse.konto_klassifisering.load_catalog()

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)
    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", lambda: [])

    load_calls = {"n": 0}

    def _loader(_client, _year):
        load_calls["n"] += 1
        return document, history, catalog

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", _loader)

    dummy = _build_cache_refresh_dummy(page_saldobalanse, analyse_page)
    # Side caches: preloaded context + usage features
    dummy._ensure_payroll_context_loaded = lambda: (document, history, catalog)
    dummy._ensure_payroll_usage_features_loaded = lambda: {}

    page_saldobalanse.SaldobalansePage.refresh(dummy)
    assert load_calls["n"] == 0, "refresh must use side-cached context instead of calling _load_payroll_context"


def test_map_selected_account_invalidates_cache(monkeypatch) -> None:
    """Remapping a konto must drop the base-payload cache so the next refresh rebuilds."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    monkeypatch.setitem(
        __import__("sys").modules,
        "page_analyse_sb",
        SimpleNamespace(remap_sb_account=lambda **_kw: None),
    )

    dummy = SimpleNamespace(
        _analyse_page=SimpleNamespace(),
        _base_payload_cache=SimpleNamespace(df=pd.DataFrame()),
        _base_payload_cache_key=("stale",),
        _selected_account=lambda: ("5000", "Lønn"),
        refresh=lambda: None,
    )

    page_saldobalanse.SaldobalansePage._map_selected_account(dummy)

    assert dummy._base_payload_cache is None
    assert dummy._base_payload_cache_key is None


def test_on_include_ao_toggled_invalidates_cache(monkeypatch) -> None:
    """Toggling include-ÅO must drop the cache since underlying SB frames swap."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    refresh_calls = {"n": 0}

    dummy = SimpleNamespace(
        _analyse_page=SimpleNamespace(_on_include_ao_changed=lambda: None),
        _base_payload_cache=SimpleNamespace(df=pd.DataFrame()),
        _base_payload_cache_key=("stale",),
    )
    dummy.refresh = lambda: refresh_calls.__setitem__("n", refresh_calls["n"] + 1)

    page_saldobalanse.SaldobalansePage._on_include_ao_toggled(dummy)

    assert dummy._base_payload_cache is None
    assert dummy._base_payload_cache_key is None
    assert refresh_calls["n"] == 1


def test_a07_options_cached_across_refreshes(monkeypatch) -> None:
    """_ensure_a07_options_loaded must call load_a07_code_options only once across
    consecutive refreshes, and _hard_refresh must force a re-fetch."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    load_calls = {"n": 0}

    def _loader():
        load_calls["n"] += 1
        return [("fastloenn", "Fastlønn")]

    monkeypatch.setattr(saldobalanse_payload.konto_klassifisering, "load_a07_code_options", _loader)

    dummy = SimpleNamespace(_a07_options=[], _a07_options_loaded=False)

    page_saldobalanse.SaldobalansePage._ensure_a07_options_loaded(dummy)
    assert load_calls["n"] == 1
    assert dummy._a07_options == [("fastloenn", "Fastlønn")]
    assert dummy._a07_options_loaded is True

    # Second call must be a no-op.
    page_saldobalanse.SaldobalansePage._ensure_a07_options_loaded(dummy)
    assert load_calls["n"] == 1

    # Hard refresh resets the flag (we simulate just the reset here).
    dummy._a07_options_loaded = False
    page_saldobalanse.SaldobalansePage._ensure_a07_options_loaded(dummy)
    assert load_calls["n"] == 2


def test_render_df_semantic_equivalence(monkeypatch) -> None:
    """_render_df must produce the same (iid, values, tags) triples as before for
    representative payroll/locked/mapping states — protects the render refactor."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    inserted: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    class _Tree:
        def insert(self, _parent, _where, *, iid, values, tags):
            inserted.append((str(iid), tuple(values), tuple(tags)))

        def get_children(self, _parent=""):
            return ()

        def delete(self, *_items):
            return None

    df = pd.DataFrame(
        {
            "Konto": ["5000", "5210", "2940", "3000"],
            "Kontonavn": ["Lønn", "Fri telefon", "Skyldig feriepenger", "Salg"],
            "Gruppe": ["", "", "", ""],
            "Nåværende": ["", "", "", ""],
            "Forslag": ["", "", "", ""],
            "Status": ["Uklar", "Forslag", "", ""],
            "A07-kode": ["", "", "", ""],
            "A07-forslag": ["", "", "", ""],
            "A07 OK": ["", "", "", ""],
            "RF-1022-post": ["", "", "", ""],
            "RF-1022-forslag": ["", "", "", ""],
            "RF-1022 OK": ["", "", "", ""],
            "Lønnsflagg": ["", "", "", ""],
            "Flagg-forslag": ["", "", "", ""],
            "Lønnsstatus": ["", "", "", ""],
            "Matchgrunnlag": ["", "", "", ""],
            "Problem": ["", "", "", ""],
            "Profilkilde": ["", "", "", ""],
            "Sikkerhet": ["", "", "", ""],
            "Låst": ["", "Ja", "", ""],
            "IB": [0.0, 0.0, -743491.69, 0.0],
            "Endring": [525000.0, 8784.0, -4207.18, 1000.0],
            "UB": [525000.0, 8784.0, -747698.87, 1000.0],
            "Antall": [5, 0, 12, 3],
            "Regnskapslinje": ["", "", "", ""],
            "Mappingstatus": ["", "", "Umappet", "Overstyrt"],
            "Regnr": pd.Series([pd.NA, pd.NA, pd.NA, pd.NA], dtype="Int64"),
            "Kilde": ["", "", "", ""],
            "Tilleggspostering": [0.0, 0.0, 0.0, 0.0],
            "UB før ÅO": [525000.0, 8784.0, -747698.87, 1000.0],
            "UB etter ÅO": [525000.0, 8784.0, -747698.87, 1000.0],
        }
    )

    dummy = SimpleNamespace(_tree=_Tree(), _clear_tree=lambda: None)

    page_saldobalanse.SaldobalansePage._render_df(dummy, df)

    assert [row[0] for row in inserted] == ["5000", "5210", "2940", "3000"]
    tags_by_konto = {iid: tags for iid, _values, tags in inserted}
    # Status "Uklar" → payroll_unclear
    assert tags_by_konto["5000"] == ("payroll_unclear",)
    # Låst "Ja" overrides status priority → payroll_locked
    assert tags_by_konto["5210"] == ("payroll_locked",)
    # Mappingstatus "Umappet" → problem
    assert tags_by_konto["2940"] == ("problem",)
    # Mappingstatus "Overstyrt" → override
    assert tags_by_konto["3000"] == ("override",)

    # Antall formatting: 5 renders, 0 renders as empty
    values_by_konto = {iid: values for iid, values, _tags in inserted}
    # Column order follows ALL_COLUMNS
    antall_idx = list(page_saldobalanse.ALL_COLUMNS).index("Antall")
    assert values_by_konto["5000"][antall_idx] != ""
    assert values_by_konto["5210"][antall_idx] == ""


def test_render_df_tolerates_missing_columns() -> None:
    """If some ALL_COLUMNS fields are absent in df, render must still emit blanks."""
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    inserted: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    class _Tree:
        def insert(self, _parent, _where, *, iid, values, tags):
            inserted.append((str(iid), tuple(values), tuple(tags)))

    df = pd.DataFrame(
        {
            "Konto": ["5000"],
            "Kontonavn": ["Lønn"],
            "IB": [0.0],
            "Endring": [100.0],
            "UB": [100.0],
            "Mappingstatus": [""],
            "Status": [""],
            "Låst": [""],
        }
    )

    dummy = SimpleNamespace(_tree=_Tree(), _clear_tree=lambda: None)
    page_saldobalanse.SaldobalansePage._render_df(dummy, df)

    assert len(inserted) == 1
    iid, values, tags = inserted[0]
    assert iid == "5000"
    # Length matches ALL_COLUMNS — missing cols emit ""
    assert len(values) == len(page_saldobalanse.ALL_COLUMNS)
    assert tags == ()


# ---------------------------------------------------------------------------
# Runde 2 — Detaljklassifisering + Eid selskap
# ---------------------------------------------------------------------------


def test_all_columns_includes_detail_class_and_owned_company() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    assert "Detaljklassifisering" in page_saldobalanse.ALL_COLUMNS
    assert "Eid selskap" in page_saldobalanse.ALL_COLUMNS


def test_sb_detail_class_uses_profile_override_when_set(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["2740"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["2740"],
        navn=["Skyldig mva"],
        ib=[0.0],
        ub=[1000.0],
        netto=[1000.0],
    )

    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "2740": AccountProfile(
                account_no="2740",
                detail_class_id="skyldig_feriepenger",
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_owned_company_name_map", lambda _client, _year: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_payroll_context",
        lambda _client, _year: (document, None, None),
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)

    row = df.iloc[0]
    # Profile override vinner selv om konto ligger i skyldig-mva-intervallet
    assert row["Detaljklassifisering"] == "Skyldig feriepenger"


def test_sb_detail_class_falls_back_to_global_rule_when_no_override(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["2740"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["2740"],
        navn=["Skyldig mva"],
        ib=[0.0],
        ub=[1000.0],
        netto=[1000.0],
    )

    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_owned_company_name_map", lambda _client, _year: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_payroll_context",
        lambda _client, _year: (None, None, None),
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)
    row = df.iloc[0]
    # 2740 + "skyldig mva" skal matche global seed-klasse
    assert row["Detaljklassifisering"] == "Skyldig MVA"


def test_sb_owned_company_uses_profile_orgnr_and_ownership_name(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["1380"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["1380"],
        navn=["Aksjer i datter"],
        ib=[0.0],
        ub=[5_000_000.0],
        netto=[5_000_000.0],
    )

    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "1380": AccountProfile(
                account_no="1380",
                owned_company_orgnr="987 654 321",
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_owned_company_name_map",
        lambda _client, _year: {"987654321": "Datter AS"},
    )
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_payroll_context",
        lambda _client, _year: (document, None, None),
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)
    row = df.iloc[0]
    assert row["Eid selskap"] == "Datter AS (987654321)"


def test_sb_owned_company_shows_stale_label_when_orgnr_missing(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["1380"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["1380"],
        navn=["Aksjer"],
        ib=[0.0],
        ub=[100.0],
        netto=[100.0],
    )
    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "1380": AccountProfile(
                account_no="1380",
                owned_company_orgnr="111222333",
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_owned_company_name_map", lambda _client, _year: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_payroll_context",
        lambda _client, _year: (document, None, None),
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)
    row = df.iloc[0]
    assert row["Eid selskap"] == "utgått kobling (111222333)"


def test_sb_owned_company_empty_when_profile_has_no_orgnr(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["1000"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["1000"],
        navn=["Bank"],
        ib=[0.0],
        ub=[100.0],
        netto=[100.0],
    )
    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(saldobalanse_payload, "_load_owned_company_name_map", lambda _client, _year: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_payroll_context",
        lambda _client, _year: (None, None, None),
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(analyse_page=analyse_page)
    assert df.iloc[0]["Eid selskap"] == ""


def test_sb_include_payroll_false_still_populates_detail_columns(monkeypatch) -> None:
    """include_payroll=False skal ikke kalle _load_payroll_context, men likevel vise kolonnene."""

    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    analyse_page = SimpleNamespace(dataset=pd.DataFrame({"Konto": ["2740"], "Beløp": [1.0]}))
    sb = _make_sb(
        konto=["2740"],
        navn=["Skyldig mva"],
        ib=[0.0],
        ub=[1000.0],
        netto=[1000.0],
    )
    document = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "2740": AccountProfile(
                account_no="2740",
                detail_class_id="skyldig_feriepenger",
                owned_company_orgnr="987654321",
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(saldobalanse_payload, "_resolve_sb_views", lambda _page: (sb, sb, sb))
    monkeypatch.setattr(saldobalanse_payload, "_load_mapping_issues", lambda _page: [])
    monkeypatch.setattr(saldobalanse_payload, "_load_group_mapping", lambda _client: {})
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_owned_company_name_map",
        lambda _client, _year: {"987654321": "Datter AS"},
    )

    def _refuse_payroll(*_args, **_kwargs):
        raise AssertionError("_load_payroll_context should not be called")

    monkeypatch.setattr(saldobalanse_payload, "_load_payroll_context", _refuse_payroll)
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_account_profile_document_only",
        lambda _client, _year: document,
    )
    monkeypatch.setattr(page_saldobalanse.session, "client", "Testklient", raising=False)
    monkeypatch.setattr(page_saldobalanse.session, "year", "2025", raising=False)

    df = page_saldobalanse.build_saldobalanse_df(
        analyse_page=analyse_page,
        include_payroll=False,
    )
    row = df.iloc[0]
    assert row["Detaljklassifisering"] == "Skyldig feriepenger"
    assert row["Eid selskap"] == "Datter AS (987654321)"


def test_format_owned_company_display_empty_for_blank_orgnr() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    assert page_saldobalanse._format_owned_company_display("", {}) == ""
    assert page_saldobalanse._format_owned_company_display(None, {}) == ""


def test_format_owned_company_display_strips_non_digits_before_lookup() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    assert (
        page_saldobalanse._format_owned_company_display(
            "NO 987 654 321", {"987654321": "Datter AS"}
        )
        == "Datter AS (987654321)"
    )


def test_load_owned_company_name_map_returns_empty_without_client() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    assert page_saldobalanse._load_owned_company_name_map("", 2025) == {}
    assert page_saldobalanse._load_owned_company_name_map(None, 2025) == {}


def test_load_owned_company_name_map_filters_invalid_rows(monkeypatch) -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    # Cache er modul-level og kan være forurenset fra tidligere tester.
    saldobalanse_payload._invalidate_owned_company_cache()

    class _FakeAr:
        @staticmethod
        def get_client_ownership_overview(_client: str, _year: str) -> dict:
            return {
                "owned_companies": [
                    {"company_orgnr": "987654321", "company_name": "Datter AS"},
                    {"company_orgnr": "", "company_name": "Uten orgnr"},
                    {"company_orgnr": "111222333", "company_name": ""},
                    "ikke en dict",
                ]
            }

    import src.pages.ar.backend as _ar_backend
    monkeypatch.setattr(_ar_backend, "store", _FakeAr)
    mapping = page_saldobalanse._load_owned_company_name_map("Testklient", 2025)
    assert mapping == {"987654321": "Datter AS"}


def test_sb_context_menu_handlers_persist_updates(monkeypatch) -> None:
    """Handlers skal kalle _persist_payroll_updates med rett felt og verdi."""

    import src.pages.saldobalanse.frontend.page as page_saldobalanse
    import src.pages.saldobalanse.backend.payload as saldobalanse_payload

    captured: list[tuple[dict, str]] = []

    class _FakePage:
        _profile_document = None

        def _selected_accounts(self):
            return ["2740", "2741"]

        def _profile_for_account(self, _account):
            return AccountProfile(
                account_no="2740",
                detail_class_id="skyldig_forskuddstrekk",
                owned_company_orgnr="111222333",
            )

        def _client_context(self):
            return "Testklient", 2025

        def _prompt_detail_class_choice(self, _catalog, current_id):
            captured.append({"current": current_id})
            return "skyldig_mva"

        def _prompt_owned_company_choice(self, _map, current):
            captured.append({"current": current})
            return "987654321"

        def _persist_payroll_updates(self, updates, *, status_text=None, feedback_action=None):
            captured.append((updates, feedback_action or ""))

    fake = _FakePage()
    monkeypatch.setattr(
        page_saldobalanse.account_detail_classification,
        "load_detail_class_catalog",
        lambda: [],
    )
    monkeypatch.setattr(
        saldobalanse_payload,
        "_load_owned_company_name_map",
        lambda _c, _y: {"987654321": "Datter AS"},
    )

    page_saldobalanse.SaldobalansePage._edit_detail_class_for_selected_accounts(fake)
    page_saldobalanse.SaldobalansePage._edit_owned_company_for_selected_accounts(fake)

    assert captured[0] == {"current": "skyldig_forskuddstrekk"}
    updates_detail, action_detail = captured[1]  # type: ignore[misc]
    assert updates_detail == {
        "2740": {"detail_class_id": "skyldig_mva"},
        "2741": {"detail_class_id": "skyldig_mva"},
    }
    assert action_detail == "manual_set_detail_class"

    assert captured[2] == {"current": "111222333"}
    updates_owned, action_owned = captured[3]  # type: ignore[misc]
    assert updates_owned == {
        "2740": {"owned_company_orgnr": "987654321"},
        "2741": {"owned_company_orgnr": "987654321"},
    }
    assert action_owned == "manual_set_owned_company"


def test_apply_profile_field_updates_persists_new_fields() -> None:
    """update_profiles-bridge skal håndtere detail_class_id + owned_company_orgnr."""

    from account_profile_bridge import apply_profile_field_updates

    base = AccountProfileDocument(client="Testklient", year=2025)
    updated = apply_profile_field_updates(
        base,
        {
            "2740": {
                "detail_class_id": "skyldig_mva",
                "owned_company_orgnr": "987 654 321",
            }
        },
    )
    profile = updated.profiles["2740"]
    assert profile.detail_class_id == "skyldig_mva"
    assert profile.owned_company_orgnr == "987654321"


def test_apply_profile_field_updates_clears_fields_on_blank() -> None:
    from account_profile_bridge import apply_profile_field_updates

    base = AccountProfileDocument(
        client="Testklient",
        year=2025,
        profiles={
            "2740": AccountProfile(
                account_no="2740",
                detail_class_id="skyldig_mva",
                owned_company_orgnr="987654321",
            )
        },
    )
    cleared = apply_profile_field_updates(
        base,
        {"2740": {"detail_class_id": "", "owned_company_orgnr": ""}},
    )
    profile = cleared.profiles["2740"]
    assert profile.detail_class_id is None
    assert profile.owned_company_orgnr is None
