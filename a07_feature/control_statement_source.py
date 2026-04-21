from __future__ import annotations

import sys

from .control import statement_source as _impl

sys.modules[__name__] = _impl
