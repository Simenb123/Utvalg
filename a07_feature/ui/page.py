from __future__ import annotations

"""Canonical UI entrypoint for A07.

Runtime goes through one stable method name only: ``_build_ui``. The
concrete layout is assembled by :class:`A07PageCanonicalUiMixin`.
"""

from .bindings import A07PageBindingsMixin
from .canonical_layout import A07PageCanonicalUiMixin
from .helpers import A07PageUiHelpersMixin


class A07PageUiMixin(A07PageUiHelpersMixin, A07PageBindingsMixin, A07PageCanonicalUiMixin):
    def _build_ui(self) -> None:
        self._build_ui_canonical()
