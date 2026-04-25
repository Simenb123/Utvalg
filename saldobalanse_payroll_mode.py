"""Compatibility shim for the saldobalanse payroll bridge."""

from __future__ import annotations

import importlib as _importlib

_impl = _importlib.import_module("a07_feature.payroll.saldobalanse_bridge")

_EXPORTED_NAMES = [name for name in dir(_impl) if not name.startswith("__")]
globals().update({name: getattr(_impl, name) for name in _EXPORTED_NAMES})

__doc__ = _impl.__doc__
__all__ = list(getattr(_impl, "__all__", [name for name in _EXPORTED_NAMES if not name.startswith("_")]))
