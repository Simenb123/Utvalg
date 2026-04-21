from __future__ import annotations

import sys

from .control import matching as _impl

sys.modules[__name__] = _impl
