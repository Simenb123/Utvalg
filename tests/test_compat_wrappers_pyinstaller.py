from __future__ import annotations

import importlib
from pathlib import Path

import pytest


# These root-level modules are kept for backwards compatibility after a
# repo-structure refactor. They must use *static* imports so tools like
# PyInstaller can detect and bundle the real package modules.
#
# If someone accidentally reintroduces importlib.import_module-based wrappers,
# the Windows onefile exe build may miss the package and crash at runtime.
WRAPPERS = [
    # selection_studio wrappers
    ("selectionstudio_filters", "selection_studio.filters", "filter_selectionstudio_dataframe"),
    ("selection_studio_adapters", "selection_studio.adapters", "build_bilag_dataframe"),
    ("selection_studio_bilag", "selection_studio.bilag", "build_bilag_dataframe"),
    ("selection_studio_drill", "selection_studio.drill", "normalize_bilag_value"),
    ("selection_studio_helpers", "selection_studio.helpers", "parse_amount"),
    ("selection_studio_specific", "selection_studio.specific", "compute_specific_selection_recommendation"),
    ("selection_studio_ui_builder", "selection_studio.ui_builder", "build_ui"),
    ("selection_studio_ui_logic", "selection_studio.ui_logic", "parse_custom_strata_bounds"),
    # motpost wrappers
    ("motpost_combinations", "motpost.combinations", "build_motkonto_combinations"),
    ("motpost_combinations_popup", "motpost.combinations_popup", "show_motkonto_combinations_popup"),
    ("motpost_excel", "motpost.excel", "build_motpost_excel_workbook"),
    ("motpost_konto_core", "motpost.konto_core", "build_motpost_data"),
    ("motpost_utils", "motpost.utils", "_clean_name"),
]


@pytest.mark.parametrize("wrapper_mod, real_mod, symbol", WRAPPERS)
def test_wrapper_reexports_symbol_and_is_static(wrapper_mod: str, real_mod: str, symbol: str) -> None:
    w = importlib.import_module(wrapper_mod)
    r = importlib.import_module(real_mod)

    assert hasattr(w, symbol), f"Wrapper {wrapper_mod} mangler {symbol}"
    assert getattr(w, symbol) is getattr(r, symbol)

    # Guardrail for the packaging issue:
    # we should not have the old dynamic import pattern in these wrappers.
    src = Path(w.__file__).read_text(encoding="utf-8")
    assert "_import_module" not in src
    assert "from importlib import import_module" not in src
