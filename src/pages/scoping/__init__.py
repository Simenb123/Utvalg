"""Scoping-fanen — vesentlighetsbasert scoping per regnskapslinje.

Pilot 16 av frontend/backend-mappestrukturen:
- ``backend/engine.py`` — beregning av scope-klassifisering (vesentlig/
  moderat/ikke vesentlig + auto-scope-ut-forslag)
- ``backend/store.py`` — manuelle overstyringer per klient/år
- ``backend/export.py`` — Excel-eksport
- ``frontend/page.py`` — ScopingPage (Tk-widgets, ManagedTreeview)
"""

from .frontend.page import ScopingPage

__all__ = ["ScopingPage"]
