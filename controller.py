"""
controller.py (façade)
----------------------
Samler controller-modulene i én klasse med stabilt API for GUI:
- DataControllerCore: kjerne (innlesing, filtre, pivot, scope, drilldown)
- DataControllerSample: trekk/utvalg
- DataControllerExport: eksport til Excel (inkl. analyser)

GUI-en kan fortsette å `from controller import DataController`.
"""

from __future__ import annotations

from controller_core import DataControllerCore
from controller_sample import DataControllerSample
from controller_export import DataControllerExport


class DataController(DataControllerCore, DataControllerSample, DataControllerExport):
    """Hovedcontroller – arver kjerne, trekk og eksport i én klasse."""
    def __init__(self) -> None:
        DataControllerCore.__init__(self)
        DataControllerSample.__init__(self)
        # DataControllerExport har ingen egen __init__


__all__ = ["DataController"]
