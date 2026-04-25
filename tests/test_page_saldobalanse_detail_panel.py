from types import SimpleNamespace


def test_refresh_detail_panel_mentions_when_suggestion_matches_saved_values() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    statuses: list[str] = []
    item = SimpleNamespace(
        account_no="5000",
        account_name="Lønn til ansatte",
        status_label="Lagret",
        next_action_label="Kontroller lagret klassifisering.",
    )
    dummy = SimpleNamespace(
        _detail_headline_var=_Var(),
        _detail_current_var=_Var(),
        _detail_suggested_var=_Var(),
        _detail_treatment_var=_Var(),
        _detail_next_var=_Var(),
        _detail_why_var=_Var(),
        _selected_workspace_items=lambda: [item],
        _determine_primary_action=lambda items: ("", ""),
        _current_primary_action="",
        _is_payroll_mode=lambda: True,
        _set_status_detail=lambda text: statuses.append(text),
    )

    original_format = page_saldobalanse.classification_workspace.format_why_panel
    original_match = page_saldobalanse.classification_workspace.matching_suggestion_labels
    try:
        page_saldobalanse.classification_workspace.format_why_panel = lambda selected: {
            "headline": f"{selected.account_no} | {selected.account_name}",
            "current": "Nå: lagret",
            "suggested": "Forslag: samsvarer",
            "why": "Hvorfor: test",
            "treatment": "RF-1022: Endring -> kostnadsført",
            "next": "Kontroller lagret klassifisering.",
        }
        page_saldobalanse.classification_workspace.matching_suggestion_labels = lambda selected: (
            "A07",
            "RF-1022",
            "Flagg",
        )

        page_saldobalanse.SaldobalansePage._refresh_detail_panel(dummy)
    finally:
        page_saldobalanse.classification_workspace.format_why_panel = original_format
        page_saldobalanse.classification_workspace.matching_suggestion_labels = original_match

    assert dummy._detail_headline_var.get() == "5000 | Lønn til ansatte"
    assert dummy._detail_treatment_var.get() == "RF-1022: Endring -> kostnadsført"
    assert dummy._detail_next_var.get() == "Kontroller lagret klassifisering."
    assert statuses[-1] == "Valgt 5000 | Lønn til ansatte | Status Lagret"


def test_refresh_detail_panel_mentions_when_saved_classification_is_used_without_new_suggestion() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    statuses: list[str] = []
    item = SimpleNamespace(
        account_no="5000",
        account_name="Lønn til ansatte",
        status_label="Lagret",
        next_action_label="Kontroller lagret klassifisering.",
        current=SimpleNamespace(
            a07_code=SimpleNamespace(display="fastloenn"),
            control_group=SimpleNamespace(display="Post 100 Lønn o.l."),
            control_tags=SimpleNamespace(display="AGA-pliktig"),
        ),
    )
    dummy = SimpleNamespace(
        _detail_headline_var=_Var(),
        _detail_current_var=_Var(),
        _detail_suggested_var=_Var(),
        _detail_treatment_var=_Var(),
        _detail_next_var=_Var(),
        _detail_why_var=_Var(),
        _selected_workspace_items=lambda: [item],
        _determine_primary_action=lambda items: ("", ""),
        _current_primary_action="",
        _is_payroll_mode=lambda: True,
        _set_status_detail=lambda text: statuses.append(text),
    )

    original_format = page_saldobalanse.classification_workspace.format_why_panel
    original_match = page_saldobalanse.classification_workspace.matching_suggestion_labels
    try:
        page_saldobalanse.classification_workspace.format_why_panel = lambda selected: {
            "headline": f"{selected.account_no} | {selected.account_name}",
            "current": "Nå: lagret",
            "suggested": "Forslag: Ingen nytt forslag - lagret klassifisering brukes",
            "why": "Hvorfor: test",
            "treatment": "RF-1022: Endring -> kostnadsført",
            "next": "Kontroller lagret klassifisering.",
        }
        page_saldobalanse.classification_workspace.matching_suggestion_labels = lambda selected: ()

        page_saldobalanse.SaldobalansePage._refresh_detail_panel(dummy)
    finally:
        page_saldobalanse.classification_workspace.format_why_panel = original_format
        page_saldobalanse.classification_workspace.matching_suggestion_labels = original_match

    assert dummy._detail_next_var.get() == "Kontroller lagret klassifisering."
    assert statuses[-1] == "Valgt 5000 | Lønn til ansatte | Status Lagret"


def test_refresh_detail_panel_mentions_rf1022_treatment_for_accrual_account() -> None:
    import src.pages.saldobalanse.frontend.page as page_saldobalanse

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self):
            return self.value

    statuses: list[str] = []
    item = SimpleNamespace(
        account_no="2940",
        account_name="Skyldig feriepenger",
        status_label="Forslag",
        next_action_label="Åpne klassifisering.",
        current=SimpleNamespace(
            a07_code=SimpleNamespace(display=""),
            control_group=SimpleNamespace(display=""),
            control_tags=SimpleNamespace(display=""),
        ),
    )
    dummy = SimpleNamespace(
        _detail_headline_var=_Var(),
        _detail_current_var=_Var(),
        _detail_suggested_var=_Var(),
        _detail_treatment_var=_Var(),
        _detail_next_var=_Var(),
        _detail_why_var=_Var(),
        _selected_workspace_items=lambda: [item],
        _determine_primary_action=lambda items: ("", ""),
        _current_primary_action="",
        _is_payroll_mode=lambda: True,
        _set_status_detail=lambda text: statuses.append(text),
        _row_for_account=lambda account_no: {
            "IB": -743_491.69,
            "Endring": -4_207.18,
            "UB": -747_698.87,
            "RF-1022-post": "",
            "RF-1022-forslag": "Post 100 Lønn o.l.",
        },
    )

    original_format = page_saldobalanse.classification_workspace.format_why_panel
    original_match = page_saldobalanse.classification_workspace.matching_suggestion_labels
    try:
        page_saldobalanse.classification_workspace.format_why_panel = lambda selected: {
            "headline": f"{selected.account_no} | {selected.account_name}",
            "current": "Nå: tom",
            "suggested": "Forslag: Post 100 Lønn o.l.",
            "why": "Hvorfor: feriepenger",
            "treatment": "RF-1022: +|IB| 743 491,69 - |UB| 747 698,87 = -4 207,18",
            "next": "Åpne klassifisering.",
        }
        page_saldobalanse.classification_workspace.matching_suggestion_labels = lambda selected: ()

        page_saldobalanse.SaldobalansePage._refresh_detail_panel(dummy)
    finally:
        page_saldobalanse.classification_workspace.format_why_panel = original_format
        page_saldobalanse.classification_workspace.matching_suggestion_labels = original_match

    assert dummy._detail_treatment_var.get() == "RF-1022: +|IB| 743 491,69 - |UB| 747 698,87 = -4 207,18"
