from __future__ import annotations

from .support_filters import A07PageSupportFiltersMixin
from .support_guidance import A07PageSupportGuidanceMixin
from .support_panel import A07PageSupportPanelMixin
from .support_suggestions import A07PageSupportSuggestionsMixin
from .support_trees import A07PageSupportTreesMixin


class A07PageSupportRenderMixin(
    A07PageSupportFiltersMixin,
    A07PageSupportSuggestionsMixin,
    A07PageSupportTreesMixin,
    A07PageSupportPanelMixin,
    A07PageSupportGuidanceMixin,
):
    pass
