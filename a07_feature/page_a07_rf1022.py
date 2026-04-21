from __future__ import annotations

import sys

from .payroll import rf1022 as _impl

sys.modules[__name__] = _impl
