from __future__ import annotations

from .page_a07_mapping_shared import *  # noqa: F403
from .page_a07_mapping_assign import A07PageMappingAssignMixin
from .page_a07_mapping_batch import A07PageMappingBatchMixin
from .page_a07_mapping_candidate_apply import A07PageMappingCandidateApplyMixin
from .page_a07_mapping_candidates import A07PageMappingCandidatesMixin
from .page_a07_mapping_control_actions import A07PageMappingControlActionsMixin
from .page_a07_mapping_learning import A07PageMappingLearningMixin


class A07PageMappingActionsMixin(
    A07PageMappingAssignMixin,
    A07PageMappingCandidatesMixin,
    A07PageMappingCandidateApplyMixin,
    A07PageMappingLearningMixin,
    A07PageMappingControlActionsMixin,
    A07PageMappingBatchMixin,
):
    pass
