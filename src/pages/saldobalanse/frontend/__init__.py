"""Saldobalanse — frontend-pakke (Tk-widgets).

Importerer ren backend-logikk fra ``..backend`` og presenterer den i
en ``ttk.Frame``-basert side. Eksterne kallere kan fortsatt bruke
``import page_saldobalanse`` osv. takket være ``sys.modules``-shims
på toppnivå.
"""

from .page import SaldobalansePage

__all__ = ["SaldobalansePage"]
