from __future__ import annotations

from .helpers import A07PageUiHelpersMixin


class A07PageTreeUiMixin(A07PageUiHelpersMixin):
    """Compat wrapper kept importable while helpers own the implementation."""


__all__ = ["A07PageTreeUiMixin"]
