"""MVA-fanen.

Pilot 18 av frontend/backend-mappestrukturen:

Backend (ren Python, ingen Tk):
- ``backend/avstemming.py`` — beregningskjernen for MVA-avstemming
- ``backend/avstemming_excel.py`` — Excel-eksport av avstemmingsrapport
- ``backend/codes.py`` — STANDARD_MVA_CODES + ACCOUNTING_SYSTEMS-tabeller
- ``backend/kontroller.py`` — automatiske MVA-kontroller
- ``backend/melding_parser.py`` — XML-parser for MVA-melding
- ``backend/system_defaults.py`` — default kode-mapping per regnskapssystem

Frontend (Tk-widgets):
- ``frontend/page.py`` — MvaPage hovedside
- ``frontend/avstemming_dialog.py`` — avstemmings-dialog
- ``frontend/config_dialog.py`` — MVA-oppsett-dialog
"""

from .frontend.page import MvaPage

__all__ = ["MvaPage"]
