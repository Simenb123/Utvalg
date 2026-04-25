from __future__ import annotations

from .drag_drop_helpers import A07PageDragDropHelpersMixin
from .focus_helpers import A07PageFocusHelpersMixin
from .manual_mapping_defaults import A07PageManualMappingDefaultsMixin
from .tree_builders import A07PageTreeBuilderMixin
from .tree_selection_helpers import A07PageTreeSelectionHelpersMixin
from .tree_sorting import A07PageTreeSortingMixin


class A07PageUiHelpersMixin(
    A07PageTreeBuilderMixin,
    A07PageTreeSortingMixin,
    A07PageTreeSelectionHelpersMixin,
    A07PageManualMappingDefaultsMixin,
    A07PageFocusHelpersMixin,
    A07PageDragDropHelpersMixin,
):
    """Compat facade that keeps the public helper surface stable."""


__all__ = ["A07PageUiHelpersMixin"]
