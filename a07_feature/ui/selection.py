from __future__ import annotations

from .selection_context import A07PageSelectionContextMixin
from .selection_controls import A07PageSelectionControlsMixin
from .selection_details import A07PageSelectionDetailsMixin
from .selection_events import A07PageSelectionEventsMixin
from .selection_scope import A07PageSelectionScopeMixin
from .selection_tree import A07PageSelectionTreeMixin


class A07PageSelectionMixin(
    A07PageSelectionControlsMixin,
    A07PageSelectionDetailsMixin,
    A07PageSelectionScopeMixin,
    A07PageSelectionContextMixin,
    A07PageSelectionTreeMixin,
    A07PageSelectionEventsMixin,
):
    pass
