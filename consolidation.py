"""Bakoverkompat-shim — consolidation-pakka har flyttet til
``src.pages.consolidation.backend``.

Aliasserer hele pakka via ``sys.modules`` og pre-loader submoduler
med ``setattr`` på pakka, slik at både ``import consolidation``,
``from consolidation import engine``, og ``import consolidation.engine``
treffer SAMME modul-objekt som den nye lokasjonen. Samme mønster som
motpost-shimmen ([motpost.py](motpost.py)).
"""

from __future__ import annotations

import importlib as _importlib
import pkgutil as _pkgutil
import sys as _sys

from src.pages.consolidation import backend as _consolidation

_sys.modules[__name__] = _consolidation

for _info in _pkgutil.iter_modules(_consolidation.__path__):
    _mod = _importlib.import_module(f"src.pages.consolidation.backend.{_info.name}")
    _sys.modules[f"consolidation.{_info.name}"] = _mod
    setattr(_consolidation, _info.name, _mod)
