from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_a07_tree_sorting_orders_numeric_display_values() -> None:
    class _Tree:
        def __init__(self) -> None:
            self._columns = ("Konto", "Endring")
            self._order = ["a", "b", "c", "d"]
            self._values = {
                "a": ("5000", "1.200,00"),
                "b": ("2940", "-100,00"),
                "c": ("5020", "900,00"),
                "d": ("5096", ""),
            }

        def __getitem__(self, key):
            if key == "columns":
                return self._columns
            raise KeyError(key)

        def get_children(self, *_args):
            return tuple(self._order)

        def set(self, item, column):
            return self._values[item][self._columns.index(column)]

        def item(self, item, option=None):
            if option == "values":
                return self._values[item]
            return {}

        def move(self, item, _parent, index):
            self._order.remove(item)
            self._order.insert(index, item)

    helper = A07PageUiHelpersMixin.__new__(A07PageUiHelpersMixin)
    tree = _Tree()

    helper._sort_tree_by_column(tree, "Endring")
    assert tree.get_children() == ("b", "c", "a", "d")

    helper._sort_tree_by_column(tree, "Endring")
    assert tree.get_children() == ("a", "c", "b", "d")

def test_a07_tree_sorting_keeps_summary_row_at_bottom() -> None:
    class _Tree:
        def __init__(self) -> None:
            self._columns = ("A07Post", "Diff")
            self._order = ["a", "__a07_total__", "b"]
            self._values = {
                "a": ("Feriepenger", "10,00"),
                "b": ("Fastlonn", "-5,00"),
                "__a07_total__": ("SUM viste A07-poster (2)", "5,00"),
            }
            self._tags = {"__a07_total__": ("summary_total",)}

        def __getitem__(self, key):
            if key == "columns":
                return self._columns
            raise KeyError(key)

        def get_children(self, *_args):
            return tuple(self._order)

        def set(self, item, column):
            return self._values[item][self._columns.index(column)]

        def item(self, item, option=None):
            if option == "values":
                return self._values[item]
            if option == "tags":
                return self._tags.get(item, ())
            return {}

        def move(self, item, _parent, index):
            self._order.remove(item)
            self._order.insert(index, item)

    helper = A07PageUiHelpersMixin.__new__(A07PageUiHelpersMixin)
    tree = _Tree()

    helper._sort_tree_by_column(tree, "Diff")
    assert tree.get_children() == ("b", "a", "__a07_total__")

    helper._sort_tree_by_column(tree, "Diff")
    assert tree.get_children() == ("a", "b", "__a07_total__")

def test_append_a07_total_row_sums_visible_control_rows() -> None:
    from a07_feature.ui.render import _append_a07_total_row

    df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "A07Post": "Fastlonn", "AgaPliktig": "Ja", "A07_Belop": 100.0, "GL_Belop": 90.0, "Diff": 10.0},
            {"Kode": "feriepenger", "A07Post": "Feriepenger", "AgaPliktig": "Ja", "A07_Belop": "200,00", "GL_Belop": "185,00", "Diff": "15,00"},
        ]
    )

    out = _append_a07_total_row(df)

    assert out is not None
    total = out.iloc[-1]
    assert total["Kode"] == a07_constants._CONTROL_A07_TOTAL_IID
    assert total["A07Post"] == "SUM viste A07-poster (2)"
    assert total["A07_Belop"] == 300.0
    assert total["GL_Belop"] == 275.0
    assert total["Diff"] == 25.0

def test_filter_a07_match_state_df_splits_zero_diff_rows() -> None:
    from a07_feature.ui.render import _filter_a07_match_state_df

    df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "A07Post": "Fastlonn", "Diff": 0.0},
            {"Kode": "bonus", "A07Post": "Bonus", "Diff": "1 250,00"},
            {"Kode": "feriepenger", "A07Post": "Feriepenger", "Diff": None},
        ]
    )

    assert _filter_a07_match_state_df(df, "alle")["Kode"].tolist() == ["fastloenn", "bonus", "feriepenger"]
    assert _filter_a07_match_state_df(df, "avstemt")["Kode"].tolist() == ["fastloenn"]
    assert _filter_a07_match_state_df(df, "ikke_avstemt")["Kode"].tolist() == ["bonus", "feriepenger"]

def test_control_a07_row_tag_prioritizes_zero_diff_as_matched() -> None:
    from a07_feature.ui.render import _control_a07_row_tag

    assert _control_a07_row_tag(pd.Series({"Kode": "fastloenn", "Diff": 0.0})) == a07_constants._A07_MATCHED_TAG
    assert (
        _control_a07_row_tag(pd.Series({"Kode": a07_constants._CONTROL_A07_TOTAL_IID, "Diff": 0.0}))
        == a07_constants._SUMMARY_TOTAL_TAG
    )

def test_filter_control_gl_df_supports_mapped_and_account_series_filters() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -100.0, "Endring": 20.0, "UB": -80.0, "Kode": "feriepenger"},
            {"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "6000", "Navn": "Husleie", "IB": 0.0, "Endring": 250.0, "UB": 250.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(
        control_gl_df,
        mapping_filter="mappede",
        account_series="5",
    )

    assert out["Konto"].tolist() == ["5000"]

def test_a07_page_format_value_formats_numeric_strings_with_thousands_separator() -> None:
    out = page_a07.A07Page._format_value(object(), "17036305.83", "Belop")

    assert out == "17 036 305,83"

def test_a07_page_format_value_formats_decimal_values_with_thousands_separator() -> None:
    out = page_a07.A07Page._format_value(object(), Decimal("-765740.42"), "Belop")

    assert out == "-765 740,42"

def test_control_tree_tag_maps_work_statuses_to_visual_tags() -> None:
    assert page_a07.control_tree_tag("Ferdig") == "control_done"
    assert page_a07.control_tree_tag("Forslag") == "control_review"
    assert page_a07.control_tree_tag("Historikk") == "control_review"
    assert page_a07.control_tree_tag("Har forslag") == "control_review"
    assert page_a07.control_tree_tag("Har historikk") == "control_review"
    assert page_a07.control_tree_tag("Manuell") == "control_manual"
    assert page_a07.control_tree_tag("Kontroller kobling") == "control_manual"
    assert page_a07.control_tree_tag("Uløst") == "control_manual"
    assert page_a07.control_tree_tag("Annet") == "control_default"

def test_control_gl_tree_tag_marks_unmapped_and_mapped_rows() -> None:
    unmapped = pd.Series({"Kode": ""})
    mapped = pd.Series({"Kode": "fastloenn"})

    assert page_a07.control_gl_tree_tag(unmapped, "fastloenn") == "control_gl_unmapped"
    assert page_a07.control_gl_tree_tag(mapped, "fastloenn") == "control_gl_mapped"

def test_control_tree_tags_treat_avstemt_as_non_error_display_state() -> None:
    assert a07_control_data.control_gl_family_tree_tag(
        pd.Series({"Kode": "styrehonorarOgGodtgjoerelseVerv", "MappingAuditStatus": "Avstemt"})
    ) == "suggestion_ok"
    assert a07_control_data.control_family_tree_tag(
        pd.Series({"MappingAuditStatus": "Feil", "Diff": 0.0, "AntallKontoer": 1})
    ) == "suggestion_ok"
    assert page_a07.control_queue_tree_tag(
        pd.Series({"MappingAuditStatus": "Feil", "Diff": 0.0, "AntallKontoer": 1})
    ) == "control_done"
    assert page_a07.control_queue_tree_tag(
        pd.Series({"MappingAuditStatus": "Feil", "Diff": 10.0, "AntallKontoer": 1})
    ) == "control_manual"

def test_rf1022_overview_tree_tag_uses_diff_tracks() -> None:
    assert a07_control_data.rf1022_overview_tree_tag(
        pd.Series({"GroupId": a07_control_data.RF1022_TOTAL_ROW_ID, "Status": "Sum"})
    ) == "summary_total"
    assert a07_control_data.rf1022_overview_tree_tag(
        pd.Series({"GroupId": "100_loenn_ol", "Diff": 0.0, "AgaDiff": 0.0, "Status": "Ferdig"})
    ) == "suggestion_ok"
    assert a07_control_data.rf1022_overview_tree_tag(
        pd.Series({"GroupId": "100_loenn_ol", "Diff": 12.0, "AgaDiff": 0.0, "Status": "Ferdig"})
    ) == "suggestion_review"
    assert a07_control_data.rf1022_overview_tree_tag(
        pd.Series({"GroupId": "uavklart_rf1022", "Diff": 0.0, "AgaDiff": 0.0})
    ) == "family_warning"

def test_payroll_family_tag_uses_visible_sage_color() -> None:
    source = (
        Path(a07_control_layout.__file__).read_text(encoding="utf-8")
        + "\n"
        + Path(a07_support_layout.__file__).read_text(encoding="utf-8")
    )

    assert source.count('"family_payroll": ("SAGE_WASH", "FOREST")') >= 5

def test_a07_account_series_filter_uses_analysis_style_checkboxes() -> None:
    source = Path(a07_control_layout.__file__).read_text(encoding="utf-8")
    page_source = Path(page_a07.__file__).read_text(encoding="utf-8")

    assert 'ttk.Label(control_gl_filters, text="Kontoserier:")' in source
    assert 'text="Skjul null"' in source
    assert "self.control_gl_active_only_var = tk.BooleanVar(value=True)" in page_source
    assert "ttk.Checkbutton(" in source
    assert "control_gl_series_vars" in source

def test_control_queue_tree_tag_uses_diff_first_for_green_and_red() -> None:
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": 0.0, "Arbeidsstatus": "Ulost"})) == "control_done"
    assert page_a07.control_queue_tree_tag(
        pd.Series({"Diff": 0.0, "GuidetStatus": "Kontroller kobling", "AntallKontoer": 1})
    ) == "control_done"
    assert page_a07.control_queue_tree_tag(
        pd.Series({"Diff": 0.0, "GuidetStatus": "Mistenkelig kobling", "AntallKontoer": 1})
    ) == "control_manual"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": 10.0, "Arbeidsstatus": "Historikk"})) == "control_review"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": None, "Arbeidsstatus": "Forslag"})) == "control_review"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": None, "GuidetStatus": "Kontroller kobling"})) == "control_review"

def test_control_family_tree_tag_marks_linked_zero_diff_a07_rows_green() -> None:
    assert a07_control_data.control_family_tree_tag(
        pd.Series({"Diff": 0.0, "GuidetStatus": "Kontroller kobling", "AntallKontoer": 1})
    ) == "suggestion_ok"
    assert a07_control_data.control_family_tree_tag(
        pd.Series({"Diff": 0.0, "GuidetStatus": "Mistenkelig kobling", "AntallKontoer": 1})
    ) == "family_warning"

def test_control_action_style_maps_work_labels() -> None:
    assert page_a07.control_action_style("Ferdig") == "Ready.TLabel"
    assert page_a07.control_action_style("Forslag") == "Warning.TLabel"
    assert page_a07.control_action_style("Historikk") == "Warning.TLabel"
    assert page_a07.control_action_style("Manuell") == "Warning.TLabel"
    assert page_a07.control_action_style("Uløst") == "Warning.TLabel"
    assert page_a07.control_action_style("Annet") == "Muted.TLabel"

def test_control_intro_text_guides_user_toward_best_next_step() -> None:
    safe_best = pd.Series({"WithinTolerance": True})

    assert (
        page_a07.control_intro_text("Ferdig", has_history=False, best_suggestion=None)
        == "Ser ferdig ut. Kontroller kort og gå videre hvis du er enig."
    )
    assert (
        page_a07.control_intro_text("Historikk", has_history=True, best_suggestion=None)
        == "Historikk finnes for posten. Sammenlign kort før du godkjenner."
    )
    assert (
        page_a07.control_intro_text("Forslag", has_history=False, best_suggestion=safe_best)
        == "Det finnes et forslag som bør vurderes."
    )
    assert (
        page_a07.control_intro_text("Manuell", has_history=False, best_suggestion=None)
        == "Posten er koblet, men bør kontrolleres."
    )
    assert (
        page_a07.control_intro_text("Uløst", has_history=False, best_suggestion=None)
        == "Velg koblinger eller jobb videre i forslagene nederst."
    )

def test_suggestion_and_reconcile_tree_tags_map_visual_state() -> None:
    suggestion_ok = pd.Series({"WithinTolerance": True, "Score": 0.62, "HistoryAccounts": "5000"})
    suggestion_candidate = pd.Series({"WithinTolerance": True, "Score": 0.62})
    suggestion_review = pd.Series({"WithinTolerance": False, "Score": 0.91})
    suggestion_default = pd.Series({"WithinTolerance": False, "Score": 0.55})
    reconcile_ok = pd.Series({"WithinTolerance": True})
    reconcile_diff = pd.Series({"WithinTolerance": False})

    assert page_a07.suggestion_tree_tag(suggestion_ok) == "suggestion_ok"
    assert page_a07.suggestion_tree_tag(suggestion_candidate) == "suggestion_review"
    assert page_a07.suggestion_tree_tag(suggestion_review) == "suggestion_review"
    assert page_a07.suggestion_tree_tag(suggestion_default) == "suggestion_default"
    assert page_a07.reconcile_tree_tag(reconcile_ok) == "reconcile_ok"
    assert page_a07.reconcile_tree_tag(reconcile_diff) == "reconcile_diff"

