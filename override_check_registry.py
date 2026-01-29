"""
Kompatibilitetsmodul.

Historisk/planlagt importsti i repoet:
    from override_check_registry import get_override_check_specs, ...

Selve implementasjonen ligger i pakken `overstyring/`.
"""

from overstyring.registry import CheckSpec, ParamSpec, get_override_check_specs, run_override_check_by_id

__all__ = [
    "ParamSpec",
    "CheckSpec",
    "get_override_check_specs",
    "run_override_check_by_id",
]
