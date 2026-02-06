"""Compatibility wrapper for the bilagsdrill dialog.

Several parts of the app (older/newer code paths) call the bilagsdrill dialog
with different parameter names:

- BilagDrillDialog(master, df, ...)
- BilagDrillDialog(master, df_all=df, title="...")

The canonical implementation lives in `views_bilag_drill.BilagDrillDialog`.
This module provides a small shim that:
  * accepts both `df` and `df_all`
  * optionally applies a custom window title
  * adds a `show_bilag()` helper used by motpost-combination views

This keeps UI code decoupled from constructor signature changes.
"""

from __future__ import annotations

from typing import Any, Optional

from views_bilag_drill import BilagDrillDialog as _BaseBilagDrillDialog


class BilagDrillDialog(_BaseBilagDrillDialog):
    """Backwards/forwards compatible BilagDrillDialog."""

    def __init__(
        self,
        master,
        df=None,
        bilag_col: str = "Bilag",
        *,
        df_all=None,
        title: Optional[str] = None,
        **kwargs,
    ) -> None:
        # Accept both `df` and legacy `df_all` keyword.
        effective_df = df if df is not None else df_all
        if effective_df is None:
            # Keep error readable; base class will fail later otherwise.
            raise TypeError("BilagDrillDialog requires a dataframe via 'df' or 'df_all'.")

        # Ignore unknown kwargs from older call sites.
        # (The base class only accepts `master`, `df`, `bilag_col`.)
        _ = kwargs

        super().__init__(master, effective_df, bilag_col=bilag_col)

        if title:
            try:
                self.title(title)
            except Exception:
                # Title is purely cosmetic; never break drilldown.
                pass

    def show_bilag(self, bilag: Any) -> None:
        """Convenience API used by motpost views.

        Sets the bilag number in the dialog and refreshes the transaction list.
        """

        try:
            # views_bilag_drill.BilagDrillDialog uses an Entry bound to `var_bilag`.
            self.var_bilag.set(str(bilag))
            self._refresh()
        except Exception:
            # Fall back to clicking the 'Vis' button handler if present.
            try:
                self.var_bilag.set(str(bilag))
                self._do_show()
            except Exception:
                # As a last resort: no-op.
                pass
