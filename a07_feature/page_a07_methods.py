from __future__ import annotations

from .page_a07_background import A07PageBackgroundMixin
from .page_a07_context import A07PageContextMixin
from .page_a07_locking import A07PageLockingMixin
from .page_a07_mapping_actions import A07PageMappingActionsMixin
from .page_a07_project_actions import A07PageProjectActionsMixin
from .page_a07_refresh import A07PageRefreshMixin
from .page_a07_render import A07PageRenderMixin
from .page_a07_rf1022 import A07PageRf1022Mixin
from .page_a07_selection import A07PageSelectionMixin
from .page_a07_ui import A07PageUiMixin


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
