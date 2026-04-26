"""Utvalg-fanen.

Pilot 17 av frontend/backend-mappestrukturen:
- ``backend/excel_report.py`` — Excel-rapport for utvalgs-resultater
- ``frontend/page.py`` — UtvalgPage (sample-velger)
- ``frontend/strata.py`` — UtvalgStrataPage (stratifisert sample)
"""

from .frontend.page import UtvalgPage
from .frontend.strata import UtvalgStrataPage

__all__ = ["UtvalgPage", "UtvalgStrataPage"]
