"""Admin-fanen.

Pilot 27 av frontend/backend-mappestrukturen — flyttet 16 page_admin-filer
fra rot til denne pakken. Fanen er ren UI uten egen backend, så det er
ingen frontend/backend-undermapper her: alle filene ligger flatt.
"""

from .page import AdminPage

__all__ = ["AdminPage"]
