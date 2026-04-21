from __future__ import annotations

import sys

from .ui import selection as _impl

sys.modules[__name__] = _impl
