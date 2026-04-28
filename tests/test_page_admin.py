from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import classification_workspace
import src.pages.admin.page as page_admin
import src.pages.admin.rulebook as page_admin_rulebook


def _field(display: str = "", *, provenance: classification_workspace.ClassificationProvenance | None = None) -> classification_workspace.ClassificationFieldState:
    return classification_workspace.ClassificationFieldState(value=display, display=display, provenance=provenance)


def _current_state(
    *,
    a07: str = "",
    group: str = "",
    tags: str = "",
    source: str = "",
    confidence: float | None = None,
) -> classification_workspace.ClassificationCurrentState:
    return classification_workspace.ClassificationCurrentState(
        a07_code=_field(a07),
        control_group=_field(group),
        control_tags=_field(tags),
        source=source,
        confidence=confidence,
        locked=False,
    )


def _workspace_item(
    *,
    payroll_relevant: bool,
    status_label: str,
    next_action_label: str,
    current: classification_workspace.ClassificationCurrentState | None = None,
    suggested: classification_workspace.ClassificationSuggestedState | None = None,
) -> classification_workspace.ClassificationWorkspaceItem:
    return classification_workspace.ClassificationWorkspaceItem(
        account_no="1000",
        account_name="Testkonto",
        ib=0.0,
        movement=0.0,
        ub=0.0,
        current=current or _current_state(),
        suggested=suggested or classification_workspace.ClassificationSuggestedState(),
        previous=_current_state(),
        queue_state=classification_workspace.ClassificationQueueState(),
        queue_name=classification_workspace.QUEUE_REVIEW,
        status_label=status_label,
        next_action="open_classifier",
        next_action_label=next_action_label,
        current_summary="",
        suggested_summary="",
        why_summary="",
        issue_text="",
        confidence=0.92,
        confidence_label="92%",
        confidence_bucket="Høy",
        payroll_relevant=payroll_relevant,
        result=None,
    )


def test_preview_status_text_marks_irrelevant_accounts() -> None:
    item = _workspace_item(
        payroll_relevant=False,
        status_label="Umappet",
        next_action_label="Åpne klassifisering.",
    )

    assert page_admin._preview_status_text(item) == "Ikke lønnsrelevant"
    assert page_admin._preview_next_action_text(item) == "Ingen handling i lønnsflyten."

    detail = page_admin._preview_detail(item)
    assert "Ikke lønnsrelevant" in detail["headline"]
    assert "Ingen lønnsforslag" in detail["suggested"]
    assert "Ingen handling i lønnsflyten" in detail["why"]


def test_preview_detail_preserves_workspace_explanations_for_relevant_accounts() -> None:
    item = _workspace_item(
        payroll_relevant=True,
        status_label="Klar til forslag",
        next_action_label="Bruk forslag.",
        suggested=classification_workspace.ClassificationSuggestedState(
            a07_code=_field(
                "elektroniskKommunikasjon",
                provenance=classification_workspace.ClassificationProvenance(
                    source="heuristic",
                    reason="Navn/alias: telefon",
                    confidence=0.92,
                ),
            ),
            control_group=_field(
                "Post 111 Naturalytelser",
                provenance=classification_workspace.ClassificationProvenance(
                    source="heuristic",
                    reason="Kode-standard",
                    confidence=0.92,
                    derived_from="a07_standard",
                ),
            ),
            control_tags=_field(
                "Naturalytelse, Opplysningspliktig",
                provenance=classification_workspace.ClassificationProvenance(
                    source="heuristic",
                    reason="Kode-standard",
                    confidence=0.92,
                    derived_from="a07_standard",
                ),
            ),
        ),
    )

    detail = page_admin._preview_detail(item)

    assert "Klar til forslag" in detail["headline"]
    assert "elektroniskKommunikasjon" in detail["suggested"]
    assert "navn/alias: telefon" in detail["why"]
    assert "Avledet fra A07-standard" in detail["why"]


def test_normalize_alias_document_cleans_and_preserves_structure() -> None:
    document = {
        "concepts": {
            "  telefon  ": {
                "aliases": ["telefon", "telefon", " mobil "],
                "exclude_aliases": "bil\nbil\npensjon",
                "account_ranges": ["5210-5219", "  "],
                "boost_accounts": ["5210", "5210", "foo", 5211],
            }
        },
        "meta": {"version": 1},
    }

    normalized = page_admin._normalize_alias_document(document)

    assert normalized["meta"] == {"version": 1}
    assert normalized["concepts"]["telefon"]["aliases"] == ["telefon", "mobil"]
    assert normalized["concepts"]["telefon"]["exclude_aliases"] == ["bil", "pensjon"]
    assert normalized["concepts"]["telefon"]["account_ranges"] == ["5210-5219"]
    assert normalized["concepts"]["telefon"]["boost_accounts"] == [5210, 5211]


def test_alias_preview_text_shows_remaining_count() -> None:
    preview = page_admin._alias_preview_text(["fri bil", "firmabil", "bilfordel", "fri firmabil", "listepris"])

    assert preview == "fri bil, firmabil, bilfordel (+2)"


def test_alias_concept_preview_text_summarizes_selected_concept() -> None:
    preview = page_admin._alias_concept_preview_text(
        "bil",
        {
            "aliases": ["fri bil", "firmabil", "bilfordel", "fri firmabil"],
            "exclude_aliases": ["yrkebil", "listepris"],
            "account_ranges": ["5200-5209"],
            "boost_accounts": [5200],
        },
    )

    assert "Konsept: bil" in preview
    assert "Aliaser (4): fri bil, firmabil, bilfordel, fri firmabil" in preview
    assert "Ekskluder (2): yrkebil, listepris" in preview
    assert "Intervall (1): 5200-5209" in preview
    assert "Boost (1): 5200" in preview


def test_saved_status_text_includes_timestamp_and_path() -> None:
    status = page_admin._saved_status_text(
        "config/classification/global_full_a07_rulebook.json",
        now=page_admin.datetime(2026, 4, 11, 10, 30, 45),
    )

    assert status == "Lagret 2026-04-11 10:30:45 til config/classification/global_full_a07_rulebook.json."


def test_normalize_rulebook_document_cleans_and_preserves_structure() -> None:
    document = {
        "aliases": {"fastloenn": ["lønn"]},
        "rules": {
            "  fastloenn ": {
                "label": " Fastlønn ",
                "category": " lonn ",
                "keywords": ["lønn", " lønn ", "fastlønn"],
                "exclude_keywords": "feriepenger\nferiepenger\npensjon",
                "allowed_ranges": ["5000-5091", " "],
                "boost_accounts": ["5000", "5000", "x", 5001],
                "basis": "Endring",
                "expected_sign": "-1",
                "aga_pliktig": "ja",
                "rf1022_group": "100_loenn_ol",
                "special_add": [
                    {"account": "2900-2999", "keywords": ["feriepenger"], "basis": "Endring", "weight": "1.0"},
                    {"account": "", "basis": "UB"},
                ],
            }
        },
        "meta": {"version": 2},
    }

    normalized = page_admin._normalize_rulebook_document(document)

    assert "aliases" not in normalized
    assert normalized["meta"] == {"version": 2}
    assert normalized["rules"]["fastloenn"]["label"] == "Fastlønn"
    assert normalized["rules"]["fastloenn"]["category"] == "lonn"
    assert normalized["rules"]["fastloenn"]["keywords"] == ["lønn", "fastlønn"]
    assert normalized["rules"]["fastloenn"]["exclude_keywords"] == ["feriepenger", "pensjon"]
    assert normalized["rules"]["fastloenn"]["allowed_ranges"] == ["5000-5091"]
    assert normalized["rules"]["fastloenn"]["boost_accounts"] == [5000, 5001]
    assert normalized["rules"]["fastloenn"]["basis"] == "Endring"
    assert normalized["rules"]["fastloenn"]["expected_sign"] == -1
    assert normalized["rules"]["fastloenn"]["aga_pliktig"] is True
    assert normalized["rules"]["fastloenn"]["rf1022_group"] == "100_loenn_ol"
    assert normalized["rules"]["fastloenn"]["special_add"] == [
        {"account": "2900-2999", "keywords": ["feriepenger"], "basis": "Endring", "weight": 1.0}
    ]


def test_special_add_helpers_roundtrip_editor_format() -> None:
    editor_text = "2900-2999 | feriepenger | Endring | 1,0\n5092 | Endring"

    parsed = page_admin._parse_special_add_lines(editor_text)

    assert parsed == [
        {"account": "2900-2999", "keywords": ["feriepenger"], "basis": "Endring", "weight": 1.0},
        {"account": "5092", "basis": "Endring"},
    ]
    assert "2900-2999 | feriepenger | Endring | 1.0" in page_admin._format_special_add_lines(parsed)


def test_rulebook_special_add_table_roundtrips_json_shape() -> None:
    rows = page_admin_rulebook._special_add_rows_from_payload(
        [{"account": "2900-2999", "keywords": ["feriepenger"], "basis": "Endring", "weight": 1.0}]
    )

    assert rows == [("2900-2999", "feriepenger", "Endring", "1.0")]
    assert page_admin_rulebook._special_add_payload_from_rows(rows) == [
        {"account": "2900-2999", "keywords": ["feriepenger"], "basis": "Endring", "weight": 1.0}
    ]


class _RulebookVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: object) -> None:
        self.value = str(value)


class _RulebookText:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self, *_args: object) -> str:
        return self.value

    def delete(self, *_args: object) -> None:
        self.value = ""

    def insert(self, _index: object, value: object) -> None:
        self.value = str(value)


class _RulebookTree:
    def __init__(self, selection: tuple[str, ...] = ()) -> None:
        self.rows: dict[str, tuple[object, ...]] = {}
        self._selection = list(selection)

    def get_children(self, *_args: object) -> tuple[str, ...]:
        return tuple(self.rows)

    def delete(self, item: str) -> None:
        self.rows.pop(item, None)

    def insert(self, _parent: str, _index: str, *, iid: str, values: tuple[object, ...]) -> None:
        self.rows[iid] = tuple(values)

    def exists(self, item: str) -> bool:
        return item in self.rows

    def selection(self) -> tuple[str, ...]:
        return tuple(self._selection)

    def selection_set(self, item: str) -> None:
        self._selection = [item]

    def selection_remove(self, *_args: object) -> None:
        self._selection = []

    def focus(self, *_args: object) -> None:
        return None

    def see(self, *_args: object) -> None:
        return None

    def item(self, item: str, option: str | None = None, **kwargs: object) -> tuple[object, ...] | None:
        if "values" in kwargs:
            self.rows[item] = tuple(kwargs["values"])  # type: ignore[arg-type]
            return None
        if option == "values":
            return self.rows.get(item, ())
        return self.rows.get(item, ())


def _rulebook_editor_stub(document: dict[str, object], *, selected: str = "fastloenn") -> tuple[object, list[dict[str, object]]]:
    saved: list[dict[str, object]] = []
    editor = page_admin_rulebook._RulebookEditor.__new__(page_admin_rulebook._RulebookEditor)
    editor._title = "A07"
    editor._loader = lambda: (document, "global_full_a07_rulebook.json")
    editor._saver = lambda data: (saved.append(data), "global_full_a07_rulebook.json")[1]
    editor._on_saved = None
    editor._document = deepcopy(document)
    editor._selected_key = selected
    editor._dirty = False
    editor._suspend_dirty = False
    editor._path_var = _RulebookVar()
    editor._status_var = _RulebookVar()
    editor._search_var = _RulebookVar()
    editor._rule_var = _RulebookVar(selected)
    rule = document["rules"][selected]  # type: ignore[index]
    editor._label_var = _RulebookVar(rule.get("label", ""))  # type: ignore[union-attr]
    editor._category_var = _RulebookVar(rule.get("category", ""))  # type: ignore[union-attr]
    editor._basis_var = _RulebookVar(rule.get("basis", "UB"))  # type: ignore[union-attr]
    editor._expected_sign_var = _RulebookVar("Ingen")
    editor._aga_pliktig_var = _RulebookVar(page_admin_rulebook._display_aga_pliktig(rule.get("aga_pliktig")))  # type: ignore[union-attr]
    editor._rf1022_group_var = _RulebookVar(page_admin_rulebook._display_rf1022_group(rule.get("rf1022_group")))  # type: ignore[union-attr]
    editor._special_account_var = _RulebookVar()
    editor._special_keywords_var = _RulebookVar()
    editor._special_basis_var = _RulebookVar("Endring")
    editor._special_weight_var = _RulebookVar("1.0")
    editor._keywords_text = _RulebookText("\n".join(rule.get("keywords", [])))  # type: ignore[union-attr]
    editor._exclude_text = _RulebookText("\n".join(rule.get("exclude_keywords", [])))  # type: ignore[union-attr]
    editor._ranges_text = _RulebookText("\n".join(rule.get("allowed_ranges", [])))  # type: ignore[union-attr]
    editor._boost_text = _RulebookText("\n".join(str(x) for x in rule.get("boost_accounts", [])))  # type: ignore[union-attr]
    editor._special_tree = _RulebookTree()
    for index, values in enumerate(page_admin_rulebook._special_add_rows_from_payload(rule.get("special_add")), start=1):  # type: ignore[union-attr]
        editor._special_tree.insert("", "end", iid=str(index), values=values)
    editor._tree = _RulebookTree(selection=(selected,))
    return editor, saved


def test_rulebook_editor_does_not_save_alias_changes_until_save() -> None:
    editor, saved = _rulebook_editor_stub(
        {"rules": {"fastloenn": {"label": "Fastlønn", "keywords": ["lønn"], "basis": "Endring"}}}
    )

    editor._keywords_text.value = "lønn\nfastlønn"
    assert editor._commit_form(show_errors=True) is True

    assert saved == []
    assert editor._document["rules"]["fastloenn"]["keywords"] == ["lønn", "fastlønn"]

    editor.save()

    assert len(saved) == 1
    assert saved[0]["rules"]["fastloenn"]["keywords"] == ["lønn", "fastlønn"]


def test_rulebook_editor_commits_selection_change_without_saving_to_disk() -> None:
    editor, saved = _rulebook_editor_stub(
        {
            "rules": {
                "fastloenn": {"label": "Fastlønn", "keywords": ["lønn"], "basis": "Endring"},
                "feriepenger": {"label": "Feriepenger", "keywords": ["feriepenger"], "basis": "UB"},
            }
        },
        selected="fastloenn",
    )
    editor._keywords_text.value = "lønn\nfastlønn"
    editor._tree._selection = ["feriepenger"]

    editor._handle_tree_select()

    assert saved == []
    assert editor._selected_key == "feriepenger"
    assert editor._document["rules"]["fastloenn"]["keywords"] == ["lønn", "fastlønn"]


def test_rulebook_editor_reload_discards_working_copy_and_clears_dirty_status() -> None:
    document = {"rules": {"fastloenn": {"label": "Fastlønn", "keywords": ["lønn"], "basis": "Endring"}}}
    editor, _saved = _rulebook_editor_stub(document)
    editor._document["rules"]["fastloenn"]["keywords"] = ["endret"]
    editor._set_dirty(True)

    editor.reload()

    assert editor._dirty is False
    assert editor._status_var.get() == "Lagret"
    assert editor._document["rules"]["fastloenn"]["keywords"] == ["lønn"]


def test_rulebook_editor_reload_can_focus_requested_rule() -> None:
    document = {
        "rules": {
            "fastloenn": {"label": "Fastlonn", "keywords": ["lonn"], "basis": "UB"},
            "tilskuddOgPremieTilPensjon": {
                "label": "Pensjon",
                "keywords": ["pensjon", "OTP Innberettet"],
                "basis": "UB",
            },
        }
    }
    editor, _saved = _rulebook_editor_stub(document)

    editor.reload(select_key="tilskuddOgPremieTilPensjon")

    assert editor._selected_key == "tilskuddOgPremieTilPensjon"
    assert editor._rule_var.get() == "tilskuddOgPremieTilPensjon"
    assert "OTP Innberettet" in editor._keywords_text.get()
    assert editor._dirty is False


def test_normalize_catalog_document_cleans_groups_and_tags() -> None:
    document = {
        "groups": [
            {
                "id": " 100_loenn_ol ",
                "label": " Post 100 Lønn o.l. ",
                "category": " payroll_rf1022_group ",
                "active": 1,
                "sort_order": "1000",
                "applies_to": ["analyse", "a07", "analyse"],
                "aliases": "lønn\nlonn",
            },
            {"id": "", "label": "Ugyldig"},
        ],
        "tags": [
            {
                "id": " opplysningspliktig ",
                "label": " Opplysningspliktig ",
                "category": " payroll_tag ",
                "active": True,
                "sort_order": "25",
                "applies_to": "analyse\na07",
                "aliases": ["oppgavepliktig", "oppgavepliktig"],
            }
        ],
        "meta": {"version": 3},
    }

    normalized = page_admin._normalize_catalog_document(document)

    assert normalized["meta"] == {"version": 3}
    assert normalized["groups"] == [
        {
            "id": "100_loenn_ol",
            "label": "Post 100 Lønn o.l.",
            "category": "payroll_rf1022_group",
            "active": True,
            "sort_order": 1000,
            "applies_to": ["analyse", "a07"],
            "aliases": ["lønn", "lonn"],
            "exclude_aliases": [],
        }
    ]
    assert normalized["tags"] == [
        {
            "id": "opplysningspliktig",
            "label": "Opplysningspliktig",
            "category": "payroll_tag",
            "active": True,
            "sort_order": 25,
            "applies_to": ["analyse", "a07"],
            "aliases": ["oppgavepliktig"],
            "exclude_aliases": [],
        }
    ]


def test_catalog_area_options_prioritize_payroll_areas() -> None:
    assert page_admin._catalog_area_options() == (
        "Payroll-flagg",
        "Legacy analysegrupper",
    )


def test_catalog_area_config_defaults_and_separates_clean_areas() -> None:
    payroll_tags = page_admin._catalog_area_config("Payroll-flagg")
    legacy_groups = page_admin._catalog_area_config("Legacy analysegrupper")
    fallback = page_admin._catalog_area_config("ukjent")

    assert payroll_tags["bucket"] == "tags"
    assert payroll_tags["categories"] == ("payroll_tag",)
    assert legacy_groups["categories"] == ("legacy_group",)
    assert fallback["default_category"] == "payroll_tag"


def test_catalog_area_matches_filters_entries_by_category() -> None:
    payroll_tag = {"id": "opplysningspliktig", "category": "payroll_tag"}
    legacy_group = {"id": "Skyldig MVA", "category": "legacy_group"}

    assert page_admin._catalog_area_matches(payroll_tag, ("payroll_tag",))
    assert not page_admin._catalog_area_matches(legacy_group, ("payroll_tag",))
    assert page_admin._catalog_area_matches(legacy_group, ("legacy_group",))
    assert page_admin._catalog_area_matches({}, ())


def test_normalize_threshold_document_applies_defaults_and_bounds() -> None:
    normalized = page_admin._normalize_threshold_document(
        {
            "tolerance_rel": "-0.5",
            "tolerance_abs": "1000",
            "historical_account_boost": "0.25",
            "historical_combo_boost": "0.40",
            "max_combo": "0",
            "candidates_per_code": "3",
            "top_suggestions_per_code": "2",
        }
    )

    assert normalized["tolerance_rel"] == 0.0
    assert normalized["tolerance_abs"] == 1000.0
    assert normalized["historical_account_boost"] == 0.25
    assert normalized["historical_combo_boost"] == 0.40
    assert normalized["max_combo"] == 1
    assert normalized["candidates_per_code"] == 3
    assert normalized["top_suggestions_per_code"] == 2


def test_normalize_regnskapslinje_rulebook_document_cleans_overlay_fields() -> None:
    normalized = page_admin._normalize_regnskapslinje_rulebook_document(
        {
            "rules": {
                " 1460 ": {
                    "label": " Kundefordringer ",
                    "aliases": ["kunde", " kundefordring ", "kunde"],
                    "exclude_aliases": "gjeld\ngjeld",
                    "usage_keywords": "faktura\nreskontro",
                    "account_ranges": ["1500-1599", ""],
                    "normal_balance_hint": "debet_typisk",
                }
            }
        }
    )

    assert normalized["rules"]["1460"]["label"] == "Kundefordringer"
    assert normalized["rules"]["1460"]["aliases"] == ["kunde", "kundefordring"]
    assert normalized["rules"]["1460"]["exclude_aliases"] == ["gjeld"]
    assert normalized["rules"]["1460"]["usage_keywords"] == ["faktura", "reskontro"]
    assert normalized["rules"]["1460"]["account_ranges"] == ["1500-1599"]
    assert normalized["rules"]["1460"]["normal_balance_hint"] == "debet_typisk"


def _admin_row(
    konto: str = "1500",
    kontonavn: str = "Kunde",
    *,
    interval_regnr: int | None = None,
    override_regnr: int | None = None,
    effective_regnr: int | None = None,
    effective_regnskapslinje: str = "",
    mapping_status: str = "interval",
    mapping_source: str = "interval",
    is_sumline: bool = False,
    suggested_regnr: int | None = None,
    suggested_regnskapslinje: str = "",
    suggestion_reason: str = "",
    suggestion_source: str = "",
    confidence_bucket: str = "",
    sign_note: str = "",
    belop: float = 0.0,
    ub: float = 0.0,
):
    return page_admin.analyse_mapping_service.RLAdminRow(
        konto=konto,
        kontonavn=kontonavn,
        interval_regnr=interval_regnr,
        override_regnr=override_regnr,
        effective_regnr=effective_regnr,
        effective_regnskapslinje=effective_regnskapslinje,
        mapping_status=mapping_status,
        mapping_source=mapping_source,
        is_sumline=is_sumline,
        suggested_regnr=suggested_regnr,
        suggested_regnskapslinje=suggested_regnskapslinje,
        suggestion_reason=suggestion_reason,
        suggestion_source=suggestion_source,
        confidence_bucket=confidence_bucket,
        sign_note=sign_note,
        belop=belop,
        ub=ub,
    )


def test_format_rl_mapping_source_labels_each_status() -> None:
    interval_row = _admin_row(
        interval_regnr=10, effective_regnr=10, effective_regnskapslinje="Eiendeler",
        mapping_status="interval", mapping_source="interval",
    )
    override_row = _admin_row(
        konto="3000", kontonavn="Salg",
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        effective_regnskapslinje="Skatt", mapping_status="override", mapping_source="override",
    )
    unmapped_row = _admin_row(
        konto="9999", kontonavn="Ukjent",
        mapping_status="unmapped", mapping_source="",
    )

    assert page_admin._format_rl_mapping_source(interval_row) == "Intervall"
    assert page_admin._format_rl_mapping_source(override_row) == "Overstyrt"
    assert page_admin._format_rl_mapping_source(unmapped_row) == "Ingen"


def test_format_rl_baseline_and_override_show_separate_regnr() -> None:
    row = _admin_row(
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        effective_regnskapslinje="Skatt", mapping_status="override", mapping_source="override",
    )
    assert page_admin._format_rl_baseline(row) == "50"
    assert page_admin._format_rl_override(row) == "165"

    no_baseline = _admin_row(
        override_regnr=165, effective_regnr=165, mapping_status="override",
        mapping_source="override",
    )
    assert page_admin._format_rl_baseline(no_baseline) == ""

    no_override = _admin_row(
        interval_regnr=10, effective_regnr=10, mapping_status="interval",
        mapping_source="interval",
    )
    assert page_admin._format_rl_override(no_override) == ""


def test_format_rl_current_and_suggestion_render_regnr_and_name() -> None:
    row = _admin_row(
        interval_regnr=10, effective_regnr=10, effective_regnskapslinje="Eiendeler",
        mapping_status="interval", mapping_source="interval",
        suggested_regnr=1460, suggested_regnskapslinje="Kundefordringer",
    )
    assert page_admin._format_rl_current(row) == "10 Eiendeler"
    assert page_admin._format_rl_suggestion(row) == "1460 Kundefordringer"

    no_current = _admin_row(konto="9999", kontonavn="Ukjent", mapping_status="unmapped", mapping_source="")
    assert page_admin._format_rl_current(no_current) == ""
    assert page_admin._format_rl_suggestion(no_current) == ""


def test_rl_mapping_source_explanation_uses_baseline_and_override_regnr() -> None:
    sumline_via_interval = _admin_row(
        konto="8800", kontonavn="Skatt", interval_regnr=350, effective_regnr=350,
        effective_regnskapslinje="Sumlinje", mapping_status="sumline",
        mapping_source="interval", is_sumline=True,
    )
    sumline_via_override = _admin_row(
        interval_regnr=10, override_regnr=350, effective_regnr=350,
        effective_regnskapslinje="Sumlinje", mapping_status="sumline",
        mapping_source="override", is_sumline=True,
    )
    unmapped = _admin_row(konto="9999", kontonavn="Ukjent", mapping_status="unmapped", mapping_source="")
    interval = _admin_row(
        interval_regnr=10, effective_regnr=10, effective_regnskapslinje="Eiendeler",
        mapping_status="interval", mapping_source="interval",
    )
    override_overrides_baseline = _admin_row(
        konto="3000", kontonavn="Salg",
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        effective_regnskapslinje="Skatt", mapping_status="override", mapping_source="override",
    )

    assert "intervallet" in page_admin._rl_mapping_source_explanation(sumline_via_interval)
    assert "override" in page_admin._rl_mapping_source_explanation(sumline_via_override)
    assert "Ingen baseline" in page_admin._rl_mapping_source_explanation(unmapped)
    # Forklaringen skal nevne hvilket baseline-regnr som traff
    assert "10" in page_admin._rl_mapping_source_explanation(interval)
    # Override-forklaringen skal nevne både override- og baseline-regnr
    explanation = page_admin._rl_mapping_source_explanation(override_overrides_baseline)
    assert "165" in explanation and "50" in explanation


def test_rl_preview_detail_shows_baseline_override_and_effective() -> None:
    row = _admin_row(
        konto="3000", kontonavn="Salg 25%",
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        effective_regnskapslinje="Skattekostnad",
        mapping_status="override", mapping_source="override", belop=500.0, ub=500.0,
    )

    detail = page_admin._rl_preview_detail(row)

    assert "Baseline (intervall): 50" in detail["current"]
    assert "Override (klient): 165" in detail["current"]
    assert "Effektiv RL: 165 Skattekostnad" in detail["current"]
    assert "Mappingkilde: Overstyrt" in detail["current"]
    assert "Statuskode: override" in detail["current"]
    assert "Klient-override" in detail["why"]


def test_rl_preview_detail_marks_missing_baseline_and_override_with_dash() -> None:
    row = _admin_row(
        konto="9999", kontonavn="Ukjent",
        mapping_status="unmapped", mapping_source="", belop=0.0, ub=0.0,
    )

    detail = page_admin._rl_preview_detail(row)

    assert "Baseline (intervall): -" in detail["current"]
    assert "Override (klient): -" in detail["current"]
    assert "Effektiv RL: -" in detail["current"]
    assert "Mappingkilde: Ingen" in detail["current"]


def test_rl_preview_columns_constants_match_grid_specification() -> None:
    payroll = page_admin.AdminPage._PAYROLL_PREVIEW_COLUMNS
    rl = page_admin.AdminPage._RL_PREVIEW_COLUMNS

    assert payroll == ("Konto", "Kontonavn", "Status", "Neste", "UB")
    assert rl == (
        "Konto",
        "Kontonavn",
        "Status",
        "Mappingkilde",
        "Baseline",
        "Override",
        "Effektiv",
        "Forslag",
        "Belop",
    )


def test_rl_preview_detail_shows_hard_mapping_and_suggestion() -> None:
    row = _admin_row(
        konto="1500", kontonavn="Kundefordringer",
        mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460, suggested_regnskapslinje="Kundefordringer",
        suggestion_reason="navn/alias: kundefordring",
        suggestion_source="alias",
        confidence_bucket="Middels",
        sign_note="Fortegn passer med forventet normalbalanse.",
        belop=1000.0, ub=1000.0,
    )

    detail = page_admin._rl_preview_detail(row)

    # Statuskoden er fortsatt "Umappet" — forslag skal vises separat, ikke
    # overskrive status i headline.
    assert "Umappet" in detail["headline"]
    assert "Klar til forslag" not in detail["headline"]
    assert "Forslag: 1460 Kundefordringer" in detail["suggested"]
    assert "Kilde: alias" in detail["suggested"]
    assert "Fortegn" in detail["suggested"]
    assert "navn/alias" in detail["why"]
    # Neste-handlingen skal si at det finnes et forslag å bruke.
    assert "forslag" in detail["why"].lower()


def test_rl_preview_status_text_prefers_mapping_status_over_suggestion() -> None:
    unmapped_with_suggestion = _admin_row(
        konto="1500", kontonavn="Kundefordringer",
        mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460, suggested_regnskapslinje="Kundefordringer",
    )
    sumline_with_suggestion = _admin_row(
        konto="8800", kontonavn="Skatt",
        interval_regnr=350, effective_regnr=350, effective_regnskapslinje="Sumlinje",
        mapping_status="sumline", mapping_source="interval", is_sumline=True,
        suggested_regnr=8830, suggested_regnskapslinje="Skattekostnad",
    )
    interval_row = _admin_row(
        interval_regnr=10, effective_regnr=10, effective_regnskapslinje="Eiendeler",
        mapping_status="interval", mapping_source="interval",
    )
    override_row = _admin_row(
        konto="3000", kontonavn="Salg",
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        effective_regnskapslinje="Skatt", mapping_status="override", mapping_source="override",
    )

    assert page_admin._rl_preview_status_text(unmapped_with_suggestion) == "Umappet"
    assert page_admin._rl_preview_status_text(sumline_with_suggestion) == "Sumpost"
    assert page_admin._rl_preview_status_text(interval_row) == "Mappet"
    assert page_admin._rl_preview_status_text(override_row) == "Overstyrt"


def test_rl_preview_is_ready_for_suggestion_matches_problems_with_forslag() -> None:
    unmapped_with_suggestion = _admin_row(
        konto="1500", mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460,
    )
    sumline_with_suggestion = _admin_row(
        konto="8800", mapping_status="sumline", mapping_source="interval",
        is_sumline=True, interval_regnr=350, effective_regnr=350,
        suggested_regnr=8830,
    )
    unmapped_without_suggestion = _admin_row(
        konto="9999", mapping_status="unmapped", mapping_source="",
    )
    interval_with_suggestion = _admin_row(
        konto="1000", mapping_status="interval", mapping_source="interval",
        interval_regnr=10, effective_regnr=10, suggested_regnr=11,
    )
    override_with_suggestion = _admin_row(
        konto="3000", mapping_status="override", mapping_source="override",
        interval_regnr=50, override_regnr=165, effective_regnr=165,
        suggested_regnr=170,
    )

    assert page_admin._rl_preview_is_ready_for_suggestion(unmapped_with_suggestion) is True
    assert page_admin._rl_preview_is_ready_for_suggestion(sumline_with_suggestion) is True
    assert page_admin._rl_preview_is_ready_for_suggestion(unmapped_without_suggestion) is False
    # Forslag på allerede-mappede kontoer skal IKKE regnes som arbeidsklart.
    assert page_admin._rl_preview_is_ready_for_suggestion(interval_with_suggestion) is False
    assert page_admin._rl_preview_is_ready_for_suggestion(override_with_suggestion) is False


def _rl_filter_admin(filter_label: str) -> SimpleNamespace:
    """Bygg et minimalistisk AdminPage-fake for å teste RL-filter-matchingen."""

    return SimpleNamespace(_rl_filter_value=lambda: filter_label)


def test_rl_preview_filter_klar_til_forslag_matches_problem_rows_with_suggestion() -> None:
    unmapped_with_suggestion = _admin_row(
        konto="1500", mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460,
    )
    sumline_with_suggestion = _admin_row(
        konto="8800", mapping_status="sumline", mapping_source="interval",
        is_sumline=True, interval_regnr=350, effective_regnr=350,
        suggested_regnr=8830,
    )
    unmapped_without_suggestion = _admin_row(
        konto="9999", mapping_status="unmapped", mapping_source="",
    )
    mapped = _admin_row(
        konto="1000", mapping_status="interval", mapping_source="interval",
        interval_regnr=10, effective_regnr=10,
    )

    admin = _rl_filter_admin("Klar til forslag")
    match = page_admin.AdminPage._rl_matches_filter

    assert match(admin, unmapped_with_suggestion) is True
    assert match(admin, sumline_with_suggestion) is True
    assert match(admin, unmapped_without_suggestion) is False
    assert match(admin, mapped) is False


def test_rl_preview_filter_sumpost_and_umappet_ignore_suggestion_presence() -> None:
    unmapped_with_suggestion = _admin_row(
        konto="1500", mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460,
    )
    sumline_with_suggestion = _admin_row(
        konto="8800", mapping_status="sumline", mapping_source="interval",
        is_sumline=True, interval_regnr=350, effective_regnr=350,
        suggested_regnr=8830,
    )
    mapped = _admin_row(
        konto="1000", mapping_status="interval", mapping_source="interval",
        interval_regnr=10, effective_regnr=10,
    )

    match = page_admin.AdminPage._rl_matches_filter

    umappet_admin = _rl_filter_admin("Umappet")
    assert match(umappet_admin, unmapped_with_suggestion) is True
    assert match(umappet_admin, sumline_with_suggestion) is False
    assert match(umappet_admin, mapped) is False

    sumpost_admin = _rl_filter_admin("Sumpost")
    assert match(sumpost_admin, sumline_with_suggestion) is True
    assert match(sumpost_admin, unmapped_with_suggestion) is False
    assert match(sumpost_admin, mapped) is False

    mappet_admin = _rl_filter_admin("Mappet")
    assert match(mappet_admin, mapped) is True
    assert match(mappet_admin, unmapped_with_suggestion) is False
    assert match(mappet_admin, sumline_with_suggestion) is False

    alle_admin = _rl_filter_admin("Alle")
    assert match(alle_admin, mapped) is True
    assert match(alle_admin, unmapped_with_suggestion) is True
    assert match(alle_admin, sumline_with_suggestion) is True


def test_after_rl_override_change_swallows_notify_failure_without_touching_rl_control() -> None:
    """Når notify feiler skal vi ikke lenger falle tilbake til RL-kontroll-refresh."""

    calls: list[str] = []

    fake_admin = SimpleNamespace(
        _notify_rule_change=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        _refresh_rl_control_rows=lambda: calls.append("rl-refresh"),
    )

    # Skal ikke kaste, og skal ikke kalle RL-kontroll-helperen.
    page_admin.AdminPage._after_rl_override_change(fake_admin)

    assert calls == []


def test_after_rl_override_change_source_does_not_reference_rl_control() -> None:
    """Fallback-grenen skal ikke nevne _refresh_rl_control_rows lenger."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage._after_rl_override_change)
    assert "_refresh_rl_control_rows" not in source


def _make_notify_admin(calls: list[str], *, preview_tab_active: bool) -> SimpleNamespace:
    fake_admin = SimpleNamespace(
        _refresh_preview_rows=lambda: calls.append("preview"),
        _refresh_rl_control_rows=lambda: calls.append("rl-control"),
        _is_preview_tab_active=lambda: preview_tab_active,
        _preview_loaded_once=False,
        _preview_dirty=False,
        _status_var=SimpleNamespace(set=lambda text: calls.append(text)),
    )

    def _ensure_preview_loaded() -> None:
        if fake_admin._preview_loaded_once and not fake_admin._preview_dirty:
            return
        fake_admin._refresh_preview_rows()
        fake_admin._preview_loaded_once = True
        fake_admin._preview_dirty = False

    fake_admin._ensure_preview_loaded = _ensure_preview_loaded
    return fake_admin


def test_notify_rule_change_invalidates_runtime_caches_and_refreshes_pages(monkeypatch) -> None:
    """Når Preview/Test ikke er aktiv skal _notify_rule_change bare markere preview dirty."""

    calls: list[str] = []

    class _Page:
        def __init__(self, name: str) -> None:
            self.name = name

        def refresh_from_session(self, _session_obj=None, **_kwargs) -> None:
            calls.append(self.name)

    fake_admin = _make_notify_admin(calls, preview_tab_active=False)
    fake_app = SimpleNamespace(
        page_saldobalanse=_Page("saldobalanse"),
        page_a07=_Page("a07"),
        page_analyse=_Page("analyse"),
    )

    monkeypatch.setattr(page_admin.session, "APP", fake_app, raising=False)
    monkeypatch.setattr(
        page_admin.payroll_classification,
        "invalidate_runtime_caches",
        lambda: calls.append("invalidate"),
    )

    page_admin.AdminPage._notify_rule_change(fake_admin)

    assert calls[:4] == ["invalidate", "saldobalanse", "a07", "analyse"]
    assert "preview" not in calls
    assert "rl-control" not in calls
    assert fake_admin._preview_dirty is True
    assert any("Forslags-cache er nullstilt" in entry for entry in calls if isinstance(entry, str))


def test_notify_rule_change_refreshes_preview_immediately_when_tab_active(monkeypatch) -> None:
    """Når Preview/Test er aktiv skal regelendring laste preview på nytt med en gang."""

    calls: list[str] = []

    class _Page:
        def __init__(self, name: str) -> None:
            self.name = name

        def refresh_from_session(self, _session_obj=None, **_kwargs) -> None:
            calls.append(self.name)

    fake_admin = _make_notify_admin(calls, preview_tab_active=True)
    fake_app = SimpleNamespace(
        page_saldobalanse=_Page("saldobalanse"),
        page_a07=_Page("a07"),
        page_analyse=_Page("analyse"),
    )

    monkeypatch.setattr(page_admin.session, "APP", fake_app, raising=False)
    monkeypatch.setattr(
        page_admin.payroll_classification,
        "invalidate_runtime_caches",
        lambda: calls.append("invalidate"),
    )

    page_admin.AdminPage._notify_rule_change(fake_admin)

    assert "preview" in calls
    assert fake_admin._preview_loaded_once is True
    assert fake_admin._preview_dirty is False


def test_rl_control_columns_match_expected_spec() -> None:
    """RL-kontroll-fanen viser den kanoniske 9-kolonne-griden."""

    assert page_admin.AdminPage._RL_PREVIEW_COLUMNS == (
        "Konto",
        "Kontonavn",
        "Status",
        "Mappingkilde",
        "Baseline",
        "Override",
        "Effektiv",
        "Forslag",
        "Belop",
    )


def test_rl_preview_filter_options_include_klar_til_forslag_without_being_status() -> None:
    """'Klar til forslag' er et arbeidsfilter, ikke en statuslabel."""

    assert "Klar til forslag" in page_admin._RL_PREVIEW_FILTER_OPTIONS
    # status-helperen returnerer aldri 'Klar til forslag'
    for status_code in ("interval", "override", "sumline", "unmapped", ""):
        row = _admin_row(mapping_status=status_code)
        assert page_admin._rl_preview_status_text(row) != "Klar til forslag"


def test_on_rl_use_suggestion_sets_override_and_refreshes(monkeypatch) -> None:
    """``Bruk forslag`` skriver suggested_regnr som override og refresher."""

    row = _admin_row(
        konto="1500", mapping_status="unmapped", mapping_source="",
        suggested_regnr=1460, suggested_regnskapslinje="Kundefordringer",
    )
    captured: dict[str, object] = {}

    def _fake_set(client: str, konto: str, regnr: int, **kwargs: object) -> None:
        captured["client"] = client
        captured["konto"] = konto
        captured["regnr"] = regnr
        captured["kwargs"] = kwargs

    monkeypatch.setattr(
        page_admin.analyse_mapping_service,
        "set_account_override",
        _fake_set,
    )

    calls: list[str] = []
    fake_admin = SimpleNamespace(
        _selected_rl_account=lambda: "1500",
        _rl_rows={"1500": row},
        _after_rl_override_change=lambda: calls.append("after"),
    )

    import session as _session

    monkeypatch.setattr(_session, "client", "ACME AS", raising=False)
    monkeypatch.setattr(_session, "year", 2026, raising=False)

    page_admin.AdminPage._on_rl_use_suggestion_clicked(fake_admin)

    assert captured["client"] == "ACME AS"
    assert captured["konto"] == "1500"
    assert captured["regnr"] == 1460
    assert captured["kwargs"] == {"year": "2026"}
    assert calls == ["after"]


def test_on_rl_use_suggestion_requires_problem_status_with_forslag(monkeypatch) -> None:
    """Interval/override-rader med forslag er ikke arbeidsklare — skal no-op."""

    row = _admin_row(
        konto="1000", mapping_status="interval", mapping_source="interval",
        interval_regnr=10, effective_regnr=10,
        suggested_regnr=1460,
    )

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("set_account_override skal ikke kalles")

    monkeypatch.setattr(
        page_admin.analyse_mapping_service,
        "set_account_override",
        _boom,
    )

    # messagebox.showinfo er det eneste som kalles på "ikke klar" — stubb.
    import tkinter.messagebox as _mb

    monkeypatch.setattr(_mb, "showinfo", lambda *a, **kw: None)

    after_called: list[str] = []
    fake_admin = SimpleNamespace(
        _selected_rl_account=lambda: "1000",
        _rl_rows={"1000": row},
        _after_rl_override_change=lambda: after_called.append("after"),
    )

    page_admin.AdminPage._on_rl_use_suggestion_clicked(fake_admin)

    # Ingen override og ingen refresh for rader som ikke er arbeidsklare.
    assert after_called == []


def test_preview_tab_is_payroll_only_with_no_rl_columns_or_domain() -> None:
    """Preview/Test har bare lønnskolonner; RL-domenet er fjernet."""

    assert not hasattr(page_admin, "PREVIEW_DOMAIN_REGNSKAPSLINJER")
    assert not hasattr(page_admin, "PREVIEW_DOMAIN_OPTIONS")
    # Kun lønnskolonner i preview-griden.
    assert "Mappingkilde" not in page_admin.AdminPage._PAYROLL_PREVIEW_COLUMNS
    assert "Baseline" not in page_admin.AdminPage._PAYROLL_PREVIEW_COLUMNS
    assert "Forslag" not in page_admin.AdminPage._PAYROLL_PREVIEW_COLUMNS


# ---------------------------------------------------------------------------
# Regnskapslinjer som global RL-adminflate
# ---------------------------------------------------------------------------


def test_regnskapslinje_editor_tree_columns_include_baseline_view() -> None:
    """Regnskapslinjer-listen må vise linjetype, kontointervall, hierarki og finjustering."""

    cols = page_admin._RegnskapslinjeEditor.TREE_COLUMNS

    for required in (
        "Regnr",
        "Regnskapslinje",
        "Linjetype",
        "Kontointervall",
        "Hierarki",
        "Finjustering",
    ):
        assert required in cols, f"Kolonne mangler: {required}"
    # De gamle kolonnenavnene skal være borte
    assert "Sumpost" not in cols
    assert "Sumtilknytning" not in cols
    assert "Overlay" not in cols


def test_build_rl_baseline_rows_returns_json_baseline_rows_with_kontointervall() -> None:
    """Baseline-builder leser JSON-baseline via regnskap_config og fletter på kontointervall."""

    import pandas as pd

    df_rl = pd.DataFrame(
        {
            "nr": [10, 19, 1500],
            "regnskapslinje": ["Salgsinntekt", "Sum driftsinntekter", "Kundefordringer"],
            "sumpost": ["nei", "ja", "nei"],
            "formel": [None, None, None],
            "sumnr": [80, None, None],
            "sumlinje": ["Driftsresultat", None, None],
            "sluttsumnr": [280, None, None],
            "sluttsumlinje": ["Årsresultat", None, None],
        }
    )
    df_km = pd.DataFrame(
        {
            "fra": [3000, 1500],
            "til": [3299, 1599],
            "regnr": [10, 1500],
            "regnskapslinje": ["Salgsinntekt", "Kundefordringer"],
        }
    )

    import src.shared.regnskap.config as regnskap_config

    original_rl = regnskap_config.load_regnskapslinjer
    original_km = regnskap_config.load_kontoplan_mapping
    try:
        regnskap_config.load_regnskapslinjer = lambda **_kw: df_rl
        regnskap_config.load_kontoplan_mapping = lambda **_kw: df_km

        rows = page_admin.build_rl_baseline_rows(overlay_regnrs={"1500"})
    finally:
        regnskap_config.load_regnskapslinjer = original_rl
        regnskap_config.load_kontoplan_mapping = original_km

    assert [r.regnr for r in rows] == ["10", "19", "1500"]

    first = rows[0]
    assert first.regnskapslinje == "Salgsinntekt"
    assert first.sumpost is False
    assert first.kontointervall_text == "3000-3299"
    assert "Driftsresultat" in first.sumtilknytning_text
    assert "Årsresultat" in first.sumtilknytning_text
    assert first.has_overlay is False

    sumpost_row = rows[1]
    assert sumpost_row.sumpost is True
    assert sumpost_row.kontointervall_text == ""

    overlay_row = rows[2]
    assert overlay_row.has_overlay is True
    assert overlay_row.kontointervall_text == "1500-1599"


def test_rl_kontroll_tab_is_not_registered_in_notebook() -> None:
    """RL-kontroll skal ikke lenger være synlig i Admin-notebooken."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.__init__)
    # 'Regnskapslinjer' må fortsatt være en notebook-tab
    assert 'text="Regnskapslinjer"' in source
    # 'RL-kontroll' skal ikke legges til i notebooken
    assert 'text="RL-kontroll"' not in source


def test_format_kontointervall_text_handles_empty_and_multiple() -> None:
    assert page_admin._format_kontointervall_text([]) == ""
    assert page_admin._format_kontointervall_text([(1000, 1019)]) == "1000-1019"
    assert (
        page_admin._format_kontointervall_text([(1000, 1019), (1020, 1069)])
        == "1000-1019, 1020-1069"
    )
    # Single-konto intervall (fra == til)
    assert page_admin._format_kontointervall_text([(2740, 2740)]) == "2740"


def test_format_sumtilknytning_text_skips_missing_levels() -> None:
    row = page_admin.RLBaselineRow(
        regnr="10",
        regnskapslinje="Salgsinntekt",
        sumpost=False,
        formel="",
        sumnivaa="1",
        delsumnr="19",
        delsumlinje="Sum driftsinntekter",
        sumnr="",
        sumlinje="",
        sumnr2="160",
        sumlinje2="Resultat før skattekostnad",
        sluttsumnr="280",
        sluttsumlinje="Årsresultat",
        resultat_balanse="Resultatregnskap",
        kontointervall_text="3000-3299",
        sumtilknytning_text="",
        has_overlay=False,
    )
    text = page_admin._format_sumtilknytning_text(row)
    assert "19 Sum driftsinntekter" in text
    assert "160 Resultat før skattekostnad" in text
    assert "280 Årsresultat" in text
    # Tomme nivåer skal hoppes over — ikke vises som blanke segmenter
    assert "  " not in text


def test_regnskapslinje_editor_uses_felles_baseline_section_title() -> None:
    """LabelFrame skal nå hete 'Felles baseline', ikke 'Baseline (Excel)'."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert 'text="Felles baseline"' in source
    assert "Baseline (Excel)" not in source


def test_regnskapslinje_editor_top_area_has_no_redundant_help_text() -> None:
    """Toppområdet skal være rent — kun knapper og status, ingen hjelpetekst-blokker."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    # Gammel hjelpetekst og tilhørende forklaringer skal være borte
    assert "Her redigerer du globale regnskapslinjer og kontointervaller." not in source
    assert "Global baseline leses fra JSON" not in source
    assert "til høyre" not in source


def test_regnskapslinje_editor_overlay_help_text_removed() -> None:
    """Finjustering-hjelpeteksten er fjernet som del av høyresidens polish."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert "Global baseline beholdes uansett" not in source
    assert "Tomt skjema betyr ingen finjustering" not in source


def test_regnskapslinje_editor_has_split_baseline_and_overlay_path_vars() -> None:
    """Header skal vise både baseline- og overlay-kilde som separate linjer."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert "self._baseline_path_var" in source
    assert "self._overlay_path_var" in source
    # Den gamle enkelt-path-varen skal ikke lenger være der
    assert "self._path_var" not in source


def test_format_baseline_source_line_handles_shared_json_and_missing(tmp_path) -> None:
    class _Status:
        def __init__(self, rj=None, rp=None):
            self.regnskapslinjer_json_path = rj
            self.regnskapslinjer_path = rp

    json_path = tmp_path / "regnskapslinjer.json"
    assert page_admin._format_baseline_source_line(_Status(rj=json_path)) == (
        f"Felles baseline: {json_path}"
    )
    assert page_admin._format_baseline_source_line(_Status()) == (
        "Felles baseline: (ikke funnet i datamappen)"
    )
    assert page_admin._format_baseline_source_line(None) == (
        "Felles baseline: (ikke funnet i datamappen)"
    )

def test_format_overlay_source_line_handles_empty_and_path() -> None:
    assert page_admin._format_overlay_source_line("") == "Finjustering: (ikke lagret)"
    assert (
        page_admin._format_overlay_source_line("/a/b/regnskapslinje_rulebook.json")
        == "Finjustering: /a/b/regnskapslinje_rulebook.json"
    )


# ---------------------------------------------------------------------------
# Nye editor-funksjoner: filter, ny/slett, validering, regnr-migrasjon
# ---------------------------------------------------------------------------


def test_parse_kontointervall_text_single_and_range() -> None:
    intervals, errors = page_admin._parse_kontointervall_text("1000\n1100-1199\n")
    assert intervals == [(1000, 1000), (1100, 1199)]
    assert errors == []


def test_parse_kontointervall_text_reports_errors() -> None:
    intervals, errors = page_admin._parse_kontointervall_text("1000\nabc\n200-xyz")
    assert intervals == [(1000, 1000)]
    assert "abc" in errors
    assert "200-xyz" in errors


def test_parse_kontointervall_text_swaps_inverted_range() -> None:
    intervals, errors = page_admin._parse_kontointervall_text("2000-1000")
    assert intervals == [(1000, 2000)]
    assert errors == []


def test_rl_row_matches_filter_handles_all_modes() -> None:
    assert page_admin._rl_row_matches_filter(sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_ALLE)
    assert page_admin._rl_row_matches_filter(sumpost=True, has_overlay=False, mode=page_admin.RL_FILTER_SUMPOST)
    assert not page_admin._rl_row_matches_filter(sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_SUMPOST)
    assert page_admin._rl_row_matches_filter(sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_VANLIG)
    assert not page_admin._rl_row_matches_filter(sumpost=True, has_overlay=False, mode=page_admin.RL_FILTER_VANLIG)
    assert page_admin._rl_row_matches_filter(sumpost=False, has_overlay=True, mode=page_admin.RL_FILTER_MED_FIN)
    assert not page_admin._rl_row_matches_filter(sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_MED_FIN)
    assert page_admin._rl_row_matches_filter(sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_UTEN_FIN)
    assert not page_admin._rl_row_matches_filter(sumpost=False, has_overlay=True, mode=page_admin.RL_FILTER_UTEN_FIN)


def test_rl_filter_values_include_expected_modes() -> None:
    assert page_admin.RL_FILTER_ALLE in page_admin.RL_FILTER_VALUES
    assert page_admin.RL_FILTER_VANLIG in page_admin.RL_FILTER_VALUES
    assert page_admin.RL_FILTER_SUMPOST in page_admin.RL_FILTER_VALUES
    assert page_admin.RL_FILTER_MED_FIN in page_admin.RL_FILTER_VALUES
    assert page_admin.RL_FILTER_UTEN_FIN in page_admin.RL_FILTER_VALUES


def test_regnskapslinje_editor_has_new_and_delete_handlers() -> None:
    """Editor-klassen må ha handlers for Ny linje, Ny sumpost og Slett valgt."""

    assert hasattr(page_admin._RegnskapslinjeEditor, "_handle_new_line")
    assert hasattr(page_admin._RegnskapslinjeEditor, "_handle_new_sumpost")
    assert hasattr(page_admin._RegnskapslinjeEditor, "_handle_delete_selected")
    # Beholdt handler for finjustering-nullstilling
    assert hasattr(page_admin._RegnskapslinjeEditor, "clear_selected_rule")


def test_regnskapslinje_editor_header_has_new_sumpost_button() -> None:
    """Header skal ha 'Ny sumpost'-knapp."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert 'text="Ny linje"' in source
    assert 'text="Ny sumpost"' in source
    assert 'text="Slett valgt"' in source
    # Norsk-polish: 'Last på nytt' med æøå
    assert 'text="Last på nytt"' in source


def test_regnskapslinje_editor_uses_canonical_baseline_document_api() -> None:
    """Editor skal bruke regnskap_config.load_rl_baseline_document/save_rl_baseline_document."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor)
    assert "load_rl_baseline_document" in source
    assert "save_rl_baseline_document" in source


def test_rl_baseline_intervals_round_trip_via_editor_helpers() -> None:
    """Parse -> format round-trip for kontointervall-tekst."""

    text = "1000\n2000-2999\n"
    intervals, errors = page_admin._parse_kontointervall_text(text)
    assert errors == []
    formatted = page_admin._format_kontointervall_text(intervals)
    assert formatted == "1000, 2000-2999"


def test_rl_filter_values_use_new_sumpost_labels() -> None:
    """Filtervalgene skal si 'Skjul sumposter' og 'Bare sumposter', ikke de gamle etikettene."""

    assert page_admin.RL_FILTER_VANLIG == "Skjul sumposter"
    assert page_admin.RL_FILTER_SUMPOST == "Bare sumposter"
    assert page_admin.RL_FILTER_VALUES == (
        "Alle",
        "Skjul sumposter",
        "Bare sumposter",
        "Med finjustering",
        "Uten finjustering",
    )


def test_rl_row_matches_filter_skjul_sumposter_filters_out_sumposter() -> None:
    """'Skjul sumposter' skjuler sumpost-rader, viser vanlige."""

    assert page_admin._rl_row_matches_filter(
        sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_VANLIG
    )
    assert not page_admin._rl_row_matches_filter(
        sumpost=True, has_overlay=False, mode=page_admin.RL_FILTER_VANLIG
    )


def test_rl_row_matches_filter_bare_sumposter_keeps_only_sumposter() -> None:
    """'Bare sumposter' viser kun sumpost-rader."""

    assert page_admin._rl_row_matches_filter(
        sumpost=True, has_overlay=False, mode=page_admin.RL_FILTER_SUMPOST
    )
    assert not page_admin._rl_row_matches_filter(
        sumpost=False, has_overlay=False, mode=page_admin.RL_FILTER_SUMPOST
    )


def test_admin_page_init_does_not_call_build_rl_control_ui() -> None:
    """RL-kontroll-fanen er parkert og skal ikke bygges ved oppstart."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.__init__)
    assert "self._build_rl_control_ui()" not in source


def test_admin_page_refresh_from_session_does_not_call_refresh_rl_control_rows() -> None:
    """refresh_from_session skal ikke trigge RL-kontroll-refresh lenger."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.refresh_from_session)
    assert "_refresh_rl_control_rows" not in source


def test_admin_page_notify_rule_change_does_not_call_refresh_rl_control_rows() -> None:
    """_notify_rule_change skal ikke trigge RL-kontroll-refresh lenger."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage._notify_rule_change)
    assert "_refresh_rl_control_rows" not in source


def test_admin_page_refresh_from_session_status_does_not_mention_rl_control() -> None:
    """Statusteksten etter refresh skal ikke nevne 'RL-kontroll'."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.refresh_from_session)
    assert "RL-kontroll" not in source


def test_admin_page_notify_rule_change_status_does_not_mention_rl_control() -> None:
    """Statusteksten etter regelendring skal ikke nevne 'RL-kontroll'."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage._notify_rule_change)
    assert "RL-kontroll" not in source


def test_admin_page_preview_ui_help_does_not_mention_rl_control() -> None:
    """Preview/Test-hjelpeteksten skal ikke lenger peke til RL-kontroll-fanen."""

    import inspect

    import src.pages.admin.preview_panel as page_admin_preview_panel

    source = inspect.getsource(page_admin_preview_panel.build_preview_ui)
    assert "RL-kontroll" not in source


def test_refresh_rl_control_rows_returns_early_when_widgets_missing() -> None:
    """Den parkerte helperen skal tåle at widgetene ikke er bygd."""

    fake_admin = SimpleNamespace(_rl_control_tree=None)
    # Skal ikke kaste selv om andre RL-kontroll-widgets mangler
    page_admin.AdminPage._refresh_rl_control_rows(fake_admin)


def test_regnskapslinje_editor_sumpost_tag_uses_distinct_styling() -> None:
    """Sumpost-raden skal være mer enn bare fet — den skal ha egen bakgrunn/forgrunn."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert 'tag_configure(' in source
    assert '"sumpost"' in source
    # Må ha både bakgrunns- og forgrunnsfarge i tillegg til fet skrift
    assert "background=" in source
    assert "foreground=" in source


def test_regnskapslinje_editor_edit_zone_indicator_removed() -> None:
    """'Du redigerer'-indikatoren er fjernet som del av topområde-polishen."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert "Du redigerer: Global baseline og Finjustering" not in source


def test_regnskapslinje_editor_linjetype_label_uses_section_style() -> None:
    """Linjetype er den viktigste editor-handlingen og skal ha Section-styling."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    # Etiketten 'Linjetype' skal være nært en Section.TLabel-referanse
    idx = source.find('text="Linjetype"')
    assert idx >= 0
    window = source[max(0, idx - 120) : idx + 160]
    assert "Section.TLabel" in window


def test_regnskapslinje_editor_hints_removed() -> None:
    """Formel- og Kontointervall-hintene er fjernet som del av polishen."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert "_formel_hint" not in source
    assert "Kun for sumposter" not in source
    assert "_intervall_hint" not in source
    assert "Kun for vanlige linjer" not in source


class _FakeWidget:
    def __init__(self) -> None:
        self.state: str | None = None
        self.style: str | None = None

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]
        if "style" in kwargs:
            self.style = kwargs["style"]


class _FakeVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


def _fake_editor_for_toggle(linjetype: str) -> SimpleNamespace:
    return SimpleNamespace(
        _linjetype_var=_FakeVar(linjetype),
        _formel_entry=_FakeWidget(),
        _intervall_text=_FakeWidget(),
    )


def test_apply_linjetype_toggle_sumpost_enables_formel_disables_kontointervall() -> None:
    """Sumpost: Formel aktiv, Kontointervall deaktivert."""

    editor = _fake_editor_for_toggle(page_admin.LINJETYPE_SUMPOST)

    page_admin._RegnskapslinjeEditor._apply_linjetype_toggle(editor)

    assert editor._formel_entry.state == "normal"
    assert editor._intervall_text.state == "disabled"


def test_apply_linjetype_toggle_vanlig_enables_kontointervall_disables_formel() -> None:
    """Vanlig linje: Kontointervall aktiv, Formel deaktivert."""

    editor = _fake_editor_for_toggle(page_admin.LINJETYPE_VANLIG)

    page_admin._RegnskapslinjeEditor._apply_linjetype_toggle(editor)

    assert editor._formel_entry.state == "disabled"
    assert editor._intervall_text.state == "normal"


# ---------------------------------------------------------------------------
# Lazy Preview/Test (åpning av Admin/Regnskapslinjer skal ikke blokkere)
# ---------------------------------------------------------------------------


def _make_lazy_preview_admin(*, preview_tab_active: bool) -> SimpleNamespace:
    calls: list[str] = []
    fake_admin = SimpleNamespace(
        _analyse_page=None,
        _preview_loaded_once=False,
        _preview_dirty=True,
        _is_preview_tab_active=lambda: preview_tab_active,
        _refresh_preview_rows=lambda: calls.append("preview"),
        _status_var=SimpleNamespace(set=lambda text: calls.append(f"status:{text}")),
        _calls=calls,
    )

    def _ensure_preview_loaded() -> None:
        if fake_admin._preview_loaded_once and not fake_admin._preview_dirty:
            return
        fake_admin._refresh_preview_rows()
        fake_admin._preview_loaded_once = True
        fake_admin._preview_dirty = False

    fake_admin._ensure_preview_loaded = _ensure_preview_loaded
    return fake_admin


def test_set_analyse_page_does_not_refresh_preview_rows() -> None:
    """Å koble til Analyse-pagen skal ikke trigge tung preview-bygging."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=False)

    page_admin.AdminPage.set_analyse_page(fake_admin, object())

    assert "preview" not in fake_admin._calls
    assert fake_admin._preview_dirty is True
    assert fake_admin._preview_loaded_once is False


def test_refresh_from_session_does_not_refresh_preview_when_tab_inactive() -> None:
    """refresh_from_session skal ikke laste preview når Preview/Test ikke er aktiv."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=False)

    page_admin.AdminPage.refresh_from_session(fake_admin)

    assert "preview" not in fake_admin._calls
    assert fake_admin._preview_dirty is True


def test_refresh_from_session_refreshes_preview_when_tab_active() -> None:
    """Når Preview/Test allerede er aktiv skal refresh_from_session laste preview."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=True)

    page_admin.AdminPage.refresh_from_session(fake_admin)

    assert "preview" in fake_admin._calls
    assert fake_admin._preview_loaded_once is True
    assert fake_admin._preview_dirty is False


def test_on_admin_tab_changed_loads_preview_first_time() -> None:
    """Første gang Preview/Test åpnes skal preview lastes."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=True)

    page_admin.AdminPage._on_admin_tab_changed(fake_admin)

    assert "preview" in fake_admin._calls
    assert fake_admin._preview_loaded_once is True


def test_on_admin_tab_changed_does_nothing_when_other_tab_active() -> None:
    """Fanebytte til andre faner (f.eks. Regnskapslinjer) skal ikke trigge preview."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=False)

    page_admin.AdminPage._on_admin_tab_changed(fake_admin)

    assert "preview" not in fake_admin._calls
    assert fake_admin._preview_loaded_once is False


def test_on_admin_tab_changed_refreshes_when_dirty_after_load() -> None:
    """Hvis preview er markert dirty skal neste fanebytte refreshe."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=True)
    fake_admin._preview_loaded_once = True
    fake_admin._preview_dirty = True

    page_admin.AdminPage._on_admin_tab_changed(fake_admin)

    assert fake_admin._calls.count("preview") == 1
    assert fake_admin._preview_dirty is False


def test_on_admin_tab_changed_skips_when_clean_and_loaded() -> None:
    """Åpning av en allerede lastet og ren preview skal ikke laste på nytt."""

    fake_admin = _make_lazy_preview_admin(preview_tab_active=True)
    fake_admin._preview_loaded_once = True
    fake_admin._preview_dirty = False

    page_admin.AdminPage._on_admin_tab_changed(fake_admin)

    assert "preview" not in fake_admin._calls


def test_ensure_preview_loaded_is_idempotent_when_clean() -> None:
    """_ensure_preview_loaded skal være idempotent når state er loaded+clean."""

    calls: list[str] = []
    fake_admin = SimpleNamespace(
        _preview_loaded_once=True,
        _preview_dirty=False,
        _refresh_preview_rows=lambda: calls.append("preview"),
    )

    page_admin.AdminPage._ensure_preview_loaded(fake_admin)

    assert calls == []


def test_ensure_preview_loaded_calls_refresh_when_dirty() -> None:
    """_ensure_preview_loaded skal laste preview når dirty-flagget er satt."""

    calls: list[str] = []
    fake_admin = SimpleNamespace(
        _preview_loaded_once=True,
        _preview_dirty=True,
        _refresh_preview_rows=lambda: calls.append("preview"),
    )

    page_admin.AdminPage._ensure_preview_loaded(fake_admin)

    assert calls == ["preview"]
    assert fake_admin._preview_loaded_once is True
    assert fake_admin._preview_dirty is False


def test_build_preview_ui_initial_headline_says_not_loaded_yet() -> None:
    """Første Preview/Test-visning skal tydelig si at preview ikke er lastet ennå."""

    import inspect

    import src.pages.admin.preview_panel as page_admin_preview_panel

    source = inspect.getsource(page_admin_preview_panel.build_preview_ui)
    assert "Preview er ikke lastet ennå" in source


def test_refresh_preview_button_still_wires_refresh_preview_rows() -> None:
    """Manuell refresh-knapp i Preview/Test skal fortsatt kalle den tunge loaderen."""

    import inspect

    import src.pages.admin.preview_panel as page_admin_preview_panel

    source = inspect.getsource(page_admin_preview_panel.build_preview_ui)
    assert 'text="Oppfrisk preview"' in source
    assert "refresh_preview_rows(page)" in source


def test_admin_init_binds_notebook_tab_changed_to_lazy_preview() -> None:
    """AdminPage må binde <<NotebookTabChanged>> for å lastes preview lazy."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.__init__)
    assert "<<NotebookTabChanged>>" in source
    assert "_on_admin_tab_changed" in source


def test_admin_init_declares_lazy_preview_state() -> None:
    """AdminPage må ha eget state for lazy preview."""

    import inspect

    source = inspect.getsource(page_admin.AdminPage.__init__)
    assert "_preview_loaded_once" in source
    assert "_preview_dirty" in source


def test_regnskapslinje_save_does_not_force_preview_load_when_tab_inactive(monkeypatch) -> None:
    """Lagre i Regnskapslinjer skal markere preview dirty, ikke laste den tunge loaderen."""

    calls: list[str] = []

    fake_admin = SimpleNamespace(
        _refresh_preview_rows=lambda: calls.append("preview"),
        _is_preview_tab_active=lambda: False,
        _preview_loaded_once=False,
        _preview_dirty=False,
        _status_var=SimpleNamespace(set=lambda text: calls.append(f"status:{text}")),
    )

    def _ensure_preview_loaded() -> None:
        if fake_admin._preview_loaded_once and not fake_admin._preview_dirty:
            return
        fake_admin._refresh_preview_rows()
        fake_admin._preview_loaded_once = True
        fake_admin._preview_dirty = False

    fake_admin._ensure_preview_loaded = _ensure_preview_loaded

    monkeypatch.setattr(page_admin.session, "APP", None, raising=False)
    monkeypatch.setattr(
        page_admin.payroll_classification,
        "invalidate_runtime_caches",
        lambda: None,
    )

    # Regnskapslinjer-save ender i _notify_rule_change via on_saved-callbacken.
    page_admin.AdminPage._notify_rule_change(fake_admin)

    assert "preview" not in calls
    assert fake_admin._preview_dirty is True
    assert fake_admin._preview_loaded_once is False


# ---------------------------------------------------------------------------
# Regnskapslinjer: selection-guard og refresh-churn
# ---------------------------------------------------------------------------


class _FakeRLTree:
    """Minimal ttk.Treeview-stand-in for _RegnskapslinjeEditor-tester."""

    def __init__(self) -> None:
        self._items: list[str] = []
        self._values: dict[str, tuple[str, ...]] = {}
        self._selection: tuple[str, ...] = ()
        self.focus_calls: list[str] = []
        self.see_calls: list[str] = []
        self.selection_set_calls: list[tuple[str, ...]] = []
        self.insert_calls: list[tuple[str, tuple[str, ...]]] = []
        self.delete_calls: list[str] = []

    def exists(self, iid: str) -> bool:
        return iid in self._items

    def selection(self) -> tuple[str, ...]:
        return self._selection

    def selection_set(self, iid) -> None:
        if isinstance(iid, (tuple, list)):
            value = tuple(str(x) for x in iid)
        else:
            value = (str(iid),)
        self.selection_set_calls.append(value)
        self._selection = value

    def focus(self, iid=None) -> str | None:
        if iid is not None:
            self.focus_calls.append(str(iid))
            return None
        return self._selection[0] if self._selection else None

    def see(self, iid) -> None:
        self.see_calls.append(str(iid))

    def get_children(self, parent: str = "") -> tuple[str, ...]:
        return tuple(self._items)

    def delete(self, iid: str) -> None:
        self.delete_calls.append(iid)
        if iid in self._items:
            self._items.remove(iid)
        self._values.pop(iid, None)

    def insert(self, parent, index, *, iid: str, values=(), tags=()) -> None:  # noqa: ANN001
        self._items.append(iid)
        self._values[iid] = tuple(values)
        self.insert_calls.append((iid, tuple(values)))

    def item(self, iid: str, key: str) -> tuple[str, ...]:
        if key == "values":
            return self._values.get(iid, ())
        return ()


def _make_rl_editor_fake(
    *,
    lines: list | None = None,
    intervals: dict[str, list[tuple[int, int]]] | None = None,
    rules: dict[str, dict] | None = None,
    selected: str = "",
    search: str = "",
    filter_mode: str | None = None,
) -> SimpleNamespace:
    """Bygg en minimal fake-editor for tester som ikke krever ekte Tk."""

    from src.shared.regnskap.config import RLBaselineDocument, RLBaselineLine

    baseline_lines = list(lines) if lines is not None else []
    baseline_doc = RLBaselineDocument(lines=baseline_lines, intervals=[])
    baseline_by_regnr = {l.regnr: l for l in baseline_lines}
    intervals_by_regnr = dict(intervals or {})
    rules_dict = dict(rules or {})
    tree = _FakeRLTree()

    class _Var:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

        def set(self, value: str) -> None:
            self._value = value

    editor = SimpleNamespace(
        _tree=tree,
        _selected_regnr=selected,
        _suspend_tree_select=False,
        _last_commit_changed_row=False,
        _baseline_doc=baseline_doc,
        _baseline_by_regnr=baseline_by_regnr,
        _intervals_by_regnr=intervals_by_regnr,
        _search_var=_Var(search),
        _filter_var=_Var(filter_mode if filter_mode is not None else page_admin.RL_FILTER_ALLE),
        _status_var=_Var(""),
        _rules=lambda: rules_dict,
        _hierarki_text=lambda line: "",
        _load_form=lambda regnr: editor._load_form_calls.append(regnr),
        _clear_form=lambda: editor._load_form_calls.append("__clear__"),
        _load_form_calls=[],
        _commit_calls=[],
        _refresh_calls=[],
    )
    editor._compute_tree_row_values = (
        lambda line: page_admin._RegnskapslinjeEditor._compute_tree_row_values(editor, line)
    )
    editor._select_tree_item = (
        lambda regnr: page_admin._RegnskapslinjeEditor._select_tree_item(editor, regnr)
    )
    return editor


def test_regnskapslinje_editor_init_exposes_selection_guard_attribute() -> None:
    """__init__ må sette _suspend_tree_select = False som dokumentert state."""

    import inspect

    source = inspect.getsource(page_admin._RegnskapslinjeEditor.__init__)
    assert "_suspend_tree_select" in source
    assert "_last_commit_changed_row" in source


def test_select_tree_item_guards_selection_events() -> None:
    """_select_tree_item må holde guard-flagget True mens selection_set kjører."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False)],
    )
    editor._tree._items.append("10")
    observed: list[tuple[str, bool]] = []

    original_selection_set = editor._tree.selection_set

    def capturing(iid) -> None:
        observed.append(("selection_set", editor._suspend_tree_select))
        original_selection_set(iid)

    editor._tree.selection_set = capturing

    page_admin._RegnskapslinjeEditor._select_tree_item(editor, "10")

    assert observed == [("selection_set", True)]
    assert editor._suspend_tree_select is False


def test_select_tree_item_ignores_nonexistent_regnr() -> None:
    """_select_tree_item skal ikke kalle selection_set når raden ikke finnes."""

    editor = _make_rl_editor_fake()
    page_admin._RegnskapslinjeEditor._select_tree_item(editor, "99")
    assert editor._tree.selection_set_calls == []


def test_handle_tree_select_ignores_event_when_guard_active() -> None:
    """Programmatisk selection (guard=True) skal ikke trigge ny behandling."""

    editor = _make_rl_editor_fake(selected="10")
    editor._suspend_tree_select = True
    editor._tree._items.append("20")
    editor._tree._selection = ("20",)
    editor._commit_form = lambda *, show_errors: editor._commit_calls.append(show_errors) or True
    editor._refresh_tree = lambda **kwargs: editor._refresh_calls.append(kwargs)

    page_admin._RegnskapslinjeEditor._handle_tree_select(editor)

    assert editor._commit_calls == []
    assert editor._refresh_calls == []
    assert editor._load_form_calls == []


def test_handle_tree_select_without_row_changes_skips_refresh_tree() -> None:
    """Radbytte uten strukturelle endringer skal bare bytte form — ikke rebuild."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )
    editor._tree._items.extend(["10", "20"])
    editor._tree._selection = ("20",)

    def fake_commit(*, show_errors: bool) -> bool:
        editor._commit_calls.append(show_errors)
        editor._last_commit_changed_row = False
        return True

    editor._commit_form = fake_commit
    editor._refresh_tree = lambda **kwargs: editor._refresh_calls.append(kwargs)

    page_admin._RegnskapslinjeEditor._handle_tree_select(editor)

    assert editor._commit_calls == [True]
    assert editor._refresh_calls == []
    assert editor._selected_regnr == "20"
    assert editor._load_form_calls == ["20"]


def test_handle_tree_select_with_row_changes_refreshes_with_next_key() -> None:
    """Commit som endrer raden skal trigge _refresh_tree(preserve_selection=Y)."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )
    editor._tree._items.extend(["10", "20"])
    editor._tree._selection = ("20",)

    def fake_commit(*, show_errors: bool) -> bool:
        editor._commit_calls.append(show_errors)
        editor._last_commit_changed_row = True
        return True

    editor._commit_form = fake_commit
    editor._refresh_tree = lambda **kwargs: editor._refresh_calls.append(kwargs)

    page_admin._RegnskapslinjeEditor._handle_tree_select(editor)

    assert editor._refresh_calls == [{"preserve_selection": "20"}]
    assert editor._selected_regnr == "20"
    assert editor._load_form_calls == ["20"]


def test_handle_tree_select_reverts_when_commit_fails() -> None:
    """Mislykket commit skal reselektere forrige rad uten å laste ny form."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )
    editor._tree._items.extend(["10", "20"])
    editor._tree._selection = ("20",)

    editor._commit_form = lambda *, show_errors: False
    editor._refresh_tree = lambda **kwargs: editor._refresh_calls.append(kwargs)

    page_admin._RegnskapslinjeEditor._handle_tree_select(editor)

    assert editor._refresh_calls == []
    # _select_tree_item for "10" må ha reselektert
    assert editor._tree.selection_set_calls[-1] == ("10",)
    # Form skal ikke lastes på ny
    assert editor._load_form_calls == []
    # Selected_regnr er IKKE endret
    assert editor._selected_regnr == "10"


def test_refresh_tree_preserve_selection_overrides_current_selected_regnr() -> None:
    """preserve_selection skal vinne over self._selected_regnr ved rebuild."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )

    page_admin._RegnskapslinjeEditor._refresh_tree(editor, preserve_selection="20")

    assert editor._selected_regnr == "20"
    # Siste selection_set skal treffe "20", ikke "10"
    assert editor._tree.selection_set_calls[-1] == ("20",)


def test_refresh_tree_default_target_is_current_selected_regnr() -> None:
    """Uten preserve_selection skal _refresh_tree gjenopprette valgt rad."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )

    page_admin._RegnskapslinjeEditor._refresh_tree(editor)

    assert editor._selected_regnr == "10"
    assert editor._tree.selection_set_calls[-1] == ("10",)


def test_refresh_tree_sets_guard_during_bulk_delete_and_insert() -> None:
    """Bulk-rebuild skal undertrykke selection-events for å unngå churn."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False)],
        selected="10",
    )
    observed_states: list[bool] = []

    original_insert = editor._tree.insert

    def capturing_insert(parent, index, *, iid, values=(), tags=()) -> None:  # noqa: ANN001
        observed_states.append(editor._suspend_tree_select)
        original_insert(parent, index, iid=iid, values=values, tags=tags)

    editor._tree.insert = capturing_insert

    page_admin._RegnskapslinjeEditor._refresh_tree(editor)

    assert observed_states == [True]
    # Guard restaureres etter rebuild
    assert editor._suspend_tree_select is False


def test_commit_form_marks_row_unchanged_when_values_equal() -> None:
    """Commit uten endring skal sette _last_commit_changed_row til False."""

    from src.shared.regnskap.config import RLBaselineLine

    line = RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False)
    editor = _make_rl_editor_fake(lines=[line], selected="10")

    class _Var:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

    class _Text:
        def __init__(self, value: str) -> None:
            self._value = value

    editor._regnr_var = _Var("10")
    editor._line_var = _Var("Salg")
    editor._linjetype_var = _Var(page_admin.LINJETYPE_VANLIG)
    editor._baseline_rb_var = _Var("")
    editor._baseline_formel_var = _Var("")
    editor._baseline_delsumnr_var = _Var("")
    editor._baseline_sumnr_var = _Var("")
    editor._baseline_sumnr2_var = _Var("")
    editor._baseline_sluttsumnr_var = _Var("")
    editor._intervall_text = _Text("")
    editor._aliases_text = _Text("")
    editor._exclude_text = _Text("")
    editor._usage_text = _Text("")
    editor._ranges_text = _Text("")
    editor._balance_hint_var = _Var("")
    editor._title = "Regnskapslinjer"
    editor._get_text_widget = lambda w: w._value
    editor._rebuild_baseline_lookups = lambda: None
    editor._current_payload = lambda: {}

    ok = page_admin._RegnskapslinjeEditor._commit_form(editor, show_errors=False)

    assert ok is True
    assert editor._last_commit_changed_row is False


def test_commit_form_marks_row_changed_on_regnr_migration() -> None:
    """Regnr-migrasjon skal alltid sette _last_commit_changed_row til True."""

    from src.shared.regnskap.config import RLBaselineLine

    line = RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False)
    editor = _make_rl_editor_fake(lines=[line], selected="10")

    class _Var:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

    class _Text:
        def __init__(self, value: str) -> None:
            self._value = value

    editor._regnr_var = _Var("15")  # migrert
    editor._line_var = _Var("Salg")
    editor._linjetype_var = _Var(page_admin.LINJETYPE_VANLIG)
    editor._baseline_rb_var = _Var("")
    editor._baseline_formel_var = _Var("")
    editor._baseline_delsumnr_var = _Var("")
    editor._baseline_sumnr_var = _Var("")
    editor._baseline_sumnr2_var = _Var("")
    editor._baseline_sluttsumnr_var = _Var("")
    editor._intervall_text = _Text("")
    editor._aliases_text = _Text("")
    editor._exclude_text = _Text("")
    editor._usage_text = _Text("")
    editor._ranges_text = _Text("")
    editor._balance_hint_var = _Var("")
    editor._title = "Regnskapslinjer"
    editor._get_text_widget = lambda w: w._value
    editor._rebuild_baseline_lookups = lambda: editor._baseline_by_regnr.__setitem__(
        "15", editor._baseline_by_regnr.pop("10")
    ) if "10" in editor._baseline_by_regnr else None
    editor._current_payload = lambda: {}

    ok = page_admin._RegnskapslinjeEditor._commit_form(editor, show_errors=False)

    assert ok is True
    assert editor._last_commit_changed_row is True


def test_handle_tree_select_keeps_tree_and_form_consistent_after_rowswap() -> None:
    """End-to-end: når bruker bytter rad, skal tree-selection og _selected_regnr matche."""

    from src.shared.regnskap.config import RLBaselineLine

    editor = _make_rl_editor_fake(
        lines=[
            RLBaselineLine(regnr="10", regnskapslinje="Salg", sumpost=False),
            RLBaselineLine(regnr="20", regnskapslinje="Kostnad", sumpost=False),
        ],
        selected="10",
    )
    editor._tree._items.extend(["10", "20"])
    editor._tree._selection = ("20",)  # brukeren klikker "20"

    def fake_commit(*, show_errors: bool) -> bool:
        editor._last_commit_changed_row = False  # ingen endring
        return True

    editor._commit_form = fake_commit

    # Bruk ekte _refresh_tree-logikk for å se at selection holder
    def real_refresh(*, preserve_selection=None):
        page_admin._RegnskapslinjeEditor._refresh_tree(
            editor, preserve_selection=preserve_selection
        )

    editor._refresh_tree = real_refresh

    page_admin._RegnskapslinjeEditor._handle_tree_select(editor)

    assert editor._selected_regnr == "20"
    # Form lastet med Y (20)
    assert editor._load_form_calls == ["20"]


# ---------------------------------------------------------------------------
# Ny Admin-fane: Kontoklassifisering (_DetailClassEditor)
# ---------------------------------------------------------------------------


def test_detail_class_editor_class_exists() -> None:
    assert hasattr(page_admin, "_DetailClassEditor")


def test_admin_page_registers_detail_class_editor_tab() -> None:
    import inspect

    source = inspect.getsource(page_admin.AdminPage.__init__)
    assert "_DetailClassEditor(" in source
    assert 'text="Kontoklassifisering"' in source


def test_admin_page_exposes_detail_class_loader_and_saver() -> None:
    assert hasattr(page_admin.AdminPage, "_load_account_detail_classification_document")
    assert hasattr(page_admin.AdminPage, "_save_account_detail_classification_document")


def test_detail_class_editor_init_exposes_selection_guard_attribute() -> None:
    import inspect

    source = inspect.getsource(page_admin._DetailClassEditor.__init__)
    assert "_suspend_tree_select" in source


def test_detail_class_editor_uses_richer_form_fields() -> None:
    import inspect

    source = inspect.getsource(page_admin._DetailClassEditor)
    # Kategori, sortering og aktiv-flagg må være til stede
    assert "_category_var" in source
    assert "_sort_var" in source
    assert "_active_var" in source
    # Tekstfeltene for aliaser/ekskluder/intervall
    assert "_aliases_text" in source
    assert "_exclude_text" in source
    assert "_ranges_text" in source
    assert 'text="Grunnregel"' in source
    assert 'text="Kontoer"' in source
    assert 'text="Aliaser"' in source
    assert '"Forkast endringer"' in source


def test_detail_class_editor_tree_columns_cover_id_navn_kategori_intervall() -> None:
    import inspect

    source = inspect.getsource(page_admin._DetailClassEditor.__init__)
    assert '("class_id", "name", "category", "accounts", "active", "sort")' in source
    assert '"Klasse-id"' in source
    assert '"Kontoer"' in source


def test_detail_class_editor_saves_via_classification_config() -> None:
    import inspect

    source = inspect.getsource(page_admin.AdminPage._save_account_detail_classification_document)
    assert "classification_config.save_account_detail_classification_document" in source


def test_detail_class_editor_loads_via_classification_config() -> None:
    import inspect

    source = inspect.getsource(page_admin.AdminPage._load_account_detail_classification_document)
    assert "classification_config.load_account_detail_classification_document" in source
    assert "classification_config.resolve_account_detail_classification_path" in source


def _make_detail_class_editor_fake(*, selected: str = "") -> SimpleNamespace:
    """Minimal fake av `_DetailClassEditor` for selection-guard-tester."""

    class _Tree:
        def __init__(self) -> None:
            self._items: list[str] = []
            self._selection: tuple[str, ...] = ()
            self.selection_set_calls: list[str] = []

        def selection(self) -> tuple[str, ...]:
            return self._selection

        def selection_set(self, iid: str) -> None:
            self.selection_set_calls.append(iid)
            self._selection = (iid,)

        def exists(self, iid: str) -> bool:
            return iid in self._items

    editor = SimpleNamespace(
        _tree=_Tree(),
        _selected_key=selected,
        _suspend_tree_select=False,
        _commit_calls=[],
        _load_form_calls=[],
    )
    return editor


def test_detail_class_editor_handle_tree_select_skips_when_guard_active() -> None:
    editor = _make_detail_class_editor_fake(selected="skyldig_mva")
    editor._suspend_tree_select = True
    editor._tree._items.extend(["skyldig_mva", "skyldig_aga"])
    editor._tree._selection = ("skyldig_aga",)
    editor._commit_form = lambda *, show_errors: editor._commit_calls.append(show_errors) or True
    editor._load_form = lambda key: editor._load_form_calls.append(key)

    page_admin._DetailClassEditor._handle_tree_select(editor)

    assert editor._commit_calls == []
    assert editor._load_form_calls == []


def test_detail_class_editor_handle_tree_select_noop_when_same_key() -> None:
    editor = _make_detail_class_editor_fake(selected="skyldig_mva")
    editor._tree._items.append("skyldig_mva")
    editor._tree._selection = ("skyldig_mva",)
    editor._commit_form = lambda *, show_errors: editor._commit_calls.append(show_errors) or True
    editor._load_form = lambda key: editor._load_form_calls.append(key)

    page_admin._DetailClassEditor._handle_tree_select(editor)

    # Ingen re-load når raden er den samme
    assert editor._commit_calls == []
    assert editor._load_form_calls == []


def test_detail_class_editor_handle_tree_select_loads_new_row() -> None:
    editor = _make_detail_class_editor_fake(selected="skyldig_mva")
    editor._tree._items.extend(["skyldig_mva", "skyldig_aga"])
    editor._tree._selection = ("skyldig_aga",)
    editor._commit_form = lambda *, show_errors: editor._commit_calls.append(show_errors) or True
    editor._load_form = lambda key: editor._load_form_calls.append(key)

    page_admin._DetailClassEditor._handle_tree_select(editor)

    assert editor._commit_calls == [True]
    assert editor._load_form_calls == ["skyldig_aga"]
    assert editor._selected_key == "skyldig_aga"
