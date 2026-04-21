from __future__ import annotations

from .page_a07_background import A07PageBackgroundMixin
from .page_a07_context import A07PageContextMixin
from .page_a07_locking import A07PageLockingMixin
from .page_a07_mapping_actions import A07PageMappingActionsMixin
from .page_a07_project_actions import A07PageProjectActionsMixin
from .page_a07_refresh import A07PageRefreshMixin
from .ui.page import A07PageUiMixin
from .ui.render import A07PageRenderMixin
from .ui.selection import A07PageSelectionMixin
from .page_a07_rf1022 import A07PageRf1022Mixin


class A07PageMethodsMixin(
    A07PageUiMixin,
    A07PageContextMixin,
    A07PageRenderMixin,
    A07PageSelectionMixin,
    A07PageLockingMixin,
    A07PageMappingActionsMixin,
    A07PageProjectActionsMixin,
    A07PageRf1022Mixin,
    A07PageBackgroundMixin,
    A07PageRefreshMixin,
):
    pass
