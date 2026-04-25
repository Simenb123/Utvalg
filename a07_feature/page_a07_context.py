from __future__ import annotations

from .control.statement_ui import A07PageControlStatementMixin
from .page_a07_context_core import A07PageContextCoreMixin
from .page_a07_context_menu import A07PageContextMenuMixin
from .page_a07_navigation import A07PageNavigationMixin


class A07PageContextMixin(
    A07PageContextMenuMixin,
    A07PageNavigationMixin,
    A07PageContextCoreMixin,
    A07PageControlStatementMixin,
):
    pass
