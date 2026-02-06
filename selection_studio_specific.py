"""Compatibility wrapper.

This module used to live at the repository root. It has been moved to
``selection_studio.specific`` as part of a repo-structure refactor.

Keep importing from the old path for now; new code should import from the
package instead.

NB: We use a *static* import (not importlib.import_module) so tools like
PyInstaller can detect and bundle the dependency in onefile/onedir builds.
"""

from selection_studio import specific as _mod

for _name, _value in _mod.__dict__.items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

__all__ = getattr(_mod, "__all__", [k for k in globals().keys() if not k.startswith("_")])
