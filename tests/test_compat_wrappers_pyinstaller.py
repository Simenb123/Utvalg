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
WRAPPERS: list[tuple[str, str, str]] = [
    # Tom etter pilot 13: alle compat-wrappers er fjernet siden eksterne
    # importerere er oppdatert til ny lokasjon. Listen beholdes som
    # dokumentasjon på mønsteret i tilfelle nye wrappers legges til.
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
