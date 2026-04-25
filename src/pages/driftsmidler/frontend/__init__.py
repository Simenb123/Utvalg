"""Driftsmidler — frontend-pakke (Tk-widgets).

Importerer ren backend-logikk fra ``..backend.compute`` og presenterer
den i en ``ttk.Frame``-basert side.
"""

from .page import DriftsmidlerPage

__all__ = ["DriftsmidlerPage"]
