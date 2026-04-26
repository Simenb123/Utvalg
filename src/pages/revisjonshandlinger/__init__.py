"""Revisjonshandlinger-fanen.

Pilot 15 av frontend/backend-mappestrukturen. Hoved-oversikt over
revisjonshandlinger med kobling til regnskapslinjer, scope og status.

Tabellen bruker ManagedTreeview (jf. doc/TREEVIEW_PLAYBOOK.md) — drag-
n-drop, kolonnevelger, klikk-sortering, persist mellom økter.
"""

from .page import RevisjonshandlingerPage

__all__ = ["RevisjonshandlingerPage"]
