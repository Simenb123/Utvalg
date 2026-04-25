"""Bakoverkompat-shim — motpost-pakka har flyttet til
``src.audit_actions.motpost``.

Aliasserer hele pakka via ``sys.modules`` slik at ``import motpost``,
``from motpost import excel``, ``import motpost.excel`` osv. virker
uendret. Pre-loader alle submoduler så ``motpost.X`` og
``src.audit_actions.motpost.X`` peker til SAMME modul-objekt — viktig
for monkeypatch-konsistens i tester og for at compat-wrapper-tester
(``test_compat_wrappers_pyinstaller.py``) holder identitet.
"""

from __future__ import annotations

import importlib as _importlib
import pkgutil as _pkgutil
import sys as _sys

# Importer pakka — dette laster `src.audit_actions.motpost` og dens __init__.py.
from src.audit_actions import motpost as _motpost

# Aliasser pakka selv: `import motpost` returnerer _motpost.
_sys.modules[__name__] = _motpost

# Pre-load alle submoduler. Bruk både sys.modules-alias OG attribut på pakka,
# ellers vil ``from motpost import utils`` re-laste modulen og lage
# duplikate funksjonsobjekter (se kommentar i loop).
for _info in _pkgutil.iter_modules(_motpost.__path__):
    _mod = _importlib.import_module(f"src.audit_actions.motpost.{_info.name}")
    _sys.modules[f"motpost.{_info.name}"] = _mod
    # ``from <pkg> import <name>`` slår først opp <name> som attributt på
    # pakka — hvis det mangler, faller Python tilbake til submodule-import
    # som re-eksekverer modulen. Sett attributtet for å unngå det.
    setattr(_motpost, _info.name, _mod)
