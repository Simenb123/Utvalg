from __future__ import annotations

import sys

from .ui import render as _impl

sys.modules[__name__] = _impl
