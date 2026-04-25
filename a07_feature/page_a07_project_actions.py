from __future__ import annotations

from .page_a07_group_actions import A07PageGroupActionsMixin
from .page_a07_project_io import A07PageProjectIoMixin
from .page_a07_project_tools import A07PageProjectToolsMixin


class A07PageProjectActionsMixin(
    A07PageProjectIoMixin,
    A07PageGroupActionsMixin,
    A07PageProjectToolsMixin,
):
    pass
