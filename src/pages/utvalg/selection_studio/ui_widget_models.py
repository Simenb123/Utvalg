"""UI widget models for Selection Studio.

We keep these small dataclasses separate so that the main Tkinter view module
(`views_selection_studio_ui.py`) can stay small and focused on wiring.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Recommendation:
    """Recommended sample sizes for Selection Studio.

    This matches the data the UI shows and uses to populate the default sample
    size.
    """

    conf_factor: float
    n_specific: int
    n_random_recommended: int
    n_total_recommended: int
    population_value_remaining: float
