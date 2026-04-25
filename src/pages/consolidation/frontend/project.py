"""page_consolidation_project.py - facade for project and readiness helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import pandas as pd

from . import mapping_state as _mapping_state
from . import readiness_ui as _readiness_ui
from . import session as _session
from ..backend.models import ConsolidationProject

if TYPE_CHECKING:
    from .page import ConsolidationPage


def refresh_from_session(
    page: "ConsolidationPage",
    sess: object,
    *,
    storage_module,
) -> None:
    _session.refresh_from_session(page, sess, storage_module=storage_module)


def ensure_project(
    page: "ConsolidationPage",
    *,
    session_module,
    storage_module,
) -> ConsolidationProject:
    return _session.ensure_project(page, session_module=session_module, storage_module=storage_module)


def update_session_tb_button(page: "ConsolidationPage", _sess: object) -> None:
    _session.update_session_tb_button(page, _sess)


def resolve_active_client_tb(
    _page: "ConsolidationPage",
    *,
    session_module,
) -> Optional[tuple[pd.DataFrame, str, str]]:
    return _session.resolve_active_client_tb(_page, session_module=session_module)


def on_use_session_tb(
    page: "ConsolidationPage",
    *,
    storage_module,
    simpledialog_module,
    messagebox_module,
) -> None:
    _session.on_use_session_tb(
        page,
        storage_module=storage_module,
        simpledialog_module=simpledialog_module,
        messagebox_module=messagebox_module,
    )


def load_company_tbs(page: "ConsolidationPage", *, storage_module) -> None:
    _session.load_company_tbs(page, storage_module=storage_module)


def load_company_line_bases(page: "ConsolidationPage", *, storage_module) -> None:
    _session.load_company_line_bases(page, storage_module=storage_module)


def load_analyse_parent_overrides(page: "ConsolidationPage") -> dict[str, int]:
    return _mapping_state.load_analyse_parent_overrides(page)


def get_parent_override_deviation_details(page: "ConsolidationPage") -> list[str]:
    return _mapping_state.get_parent_override_deviation_details(page)


def get_effective_company_overrides(page: "ConsolidationPage", company_id: str) -> dict[str, int]:
    return _mapping_state.get_effective_company_overrides(page, company_id)


def get_effective_company_tb(page: "ConsolidationPage", company_id: str) -> pd.DataFrame | None:
    return _mapping_state.get_effective_company_tb(page, company_id)


def get_effective_company_basis(page: "ConsolidationPage", company_id: str) -> pd.DataFrame | None:
    return _mapping_state.get_effective_company_basis(page, company_id)


def get_effective_tbs(page: "ConsolidationPage") -> dict[str, pd.DataFrame]:
    return _mapping_state.get_effective_tbs(page)


def compute_mapping_status(page: "ConsolidationPage") -> None:
    _mapping_state.compute_mapping_status(page)


def split_unmapped_counts(page: "ConsolidationPage", company_id: str) -> tuple[int, int]:
    return _mapping_state.split_unmapped_counts(page, company_id)


def refresh_readiness(page: "ConsolidationPage") -> None:
    _readiness_ui.refresh_readiness(page)


def refresh_controls_tree(page: "ConsolidationPage") -> None:
    _readiness_ui.refresh_controls_tree(page)


def open_selected_readiness_issue(page: "ConsolidationPage") -> None:
    _readiness_ui.open_selected_readiness_issue(page)
