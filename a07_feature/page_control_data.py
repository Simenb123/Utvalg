from __future__ import annotations

import sys

from .control import data as _impl

sys.modules[__name__] = _impl
