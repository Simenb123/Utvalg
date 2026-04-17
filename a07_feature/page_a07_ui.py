from __future__ import annotations

"""Canonical UI entrypoint for A07.

Runtime goes through one stable method name only: ``_build_ui``. The
concrete layout is assembled by :class:`A07PageCanonicalUiMixin`.
"""

from .page_a07_ui_canonical import A07PageCanonicalUiMixin
from .page_a07_ui_helpers import A07PageUiHelpersMixin


class A07PageUiMixin(A07PageUiHelpersMixin, A07PageCanonicalUiMixin):
    def _build_ui(self) -> None:
        self._build_ui_canonical()
