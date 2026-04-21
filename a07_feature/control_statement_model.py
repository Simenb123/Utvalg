from __future__ import annotations

import sys

from .control import statement_model as _impl

sys.modules[__name__] = _impl
