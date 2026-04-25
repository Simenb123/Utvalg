from __future__ import annotations

import sys

from .frontend import page as _page

sys.modules[__name__] = _page
