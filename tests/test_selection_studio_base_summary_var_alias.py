"""Regression test: UI startup should not crash due to missing summary StringVar.

We had a runtime crash where SelectionStudio._refresh_all tried to call
`self._var_base_summary.set(...)` but __init__ only defined `var_base_summary`.
This is hard to catch with regular unit tests because Tkinter widgets aren't
constructed during most test runs.

This test is intentionally lightweight (no Tk window created): it just asserts
that if the implementation refers to `_var_base_summary`, it also initialises it.
"""

from __future__ import annotations

from pathlib import Path

import views_selection_studio_ui as v


def test_selection_studio_initialises_base_summary_alias_if_used() -> None:
    src = Path(v.__file__).read_text(encoding="utf-8")

    # If the code refers to `_var_base_summary` anywhere, make sure it is assigned.
    if "self._var_base_summary" in src:
        assert (
            "self._var_base_summary =" in src
        ), "SelectionStudio uses _var_base_summary but does not initialise it"
