from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import a07_feature.control.data as a07_control_data
import a07_feature.control.matching as a07_control_matching
import a07_feature.page_a07_context_menu as a07_context_menu
import a07_feature.page_a07_constants as a07_constants
import a07_feature.page_a07_control_statement as page_a07_control_statement
import a07_feature.page_a07_mapping_actions as a07_mapping_actions
import a07_feature.rule_learning as a07_rule_learning
import a07_feature.ui.canonical_layout as a07_canonical_layout
import a07_feature.ui.control_layout as a07_control_layout
import a07_feature.ui.groups_popup as a07_groups_popup
import a07_feature.ui.support_layout as a07_support_layout
from a07_feature.ui.helpers import A07PageUiHelpersMixin
import classification_config
import classification_workspace
import page_a07
import ui_main
from account_profile import AccountProfile, AccountProfileDocument
from a07_feature.suggest.rulebook import RulebookRule


def _seed_prior_profile_document(
    tmp_path,
    *,
    client_slug: str,
    year: int,
    mapping: dict[str, str],
) -> Path:
    path = (
        tmp_path
        / "data"
        / "konto_klassifisering_profiles"
        / client_slug
        / str(year)
        / "account_profiles.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles = {
        account_no: {"account_no": account_no, "a07_code": code}
        for account_no, code in mapping.items()
    }
    payload = {
        "schema_version": 1,
        "client": "Air Management AS",
        "year": year,
        "profiles": profiles,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class _DummyVar:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


class _ScopeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _ScopeWidget:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.config: dict[str, object] = {}

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def configure(self, **kwargs) -> None:
        self.config.update(kwargs)


def _control_gl_scope_page(scope: str, *, work_level: str = "a07", group_id: str = ""):
    page = object.__new__(page_a07.A07Page)
    page.control_gl_scope_var = _ScopeVar(scope)
    page.control_gl_scope_label_var = _ScopeVar("")
    page.control_gl_scope_widget = None
    page._selected_control_work_level = lambda: work_level
    page._selected_rf1022_group = lambda: group_id
    page._selected_control_suggestion_accounts = lambda: []
    return page


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__all__",
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
    }
]
