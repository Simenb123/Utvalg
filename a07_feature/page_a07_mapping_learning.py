from __future__ import annotations

from .page_a07_mapping_learning_accounts import A07PageMappingLearningAccountsMixin
from .page_a07_mapping_learning_gl import A07PageMappingLearningGlMixin


class A07PageMappingLearningMixin(
    A07PageMappingLearningAccountsMixin,
    A07PageMappingLearningGlMixin,
):
    pass
