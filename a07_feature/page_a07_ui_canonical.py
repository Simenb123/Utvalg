from __future__ import annotations

import sys

from .ui import canonical_layout as _impl

sys.modules[__name__] = _impl
