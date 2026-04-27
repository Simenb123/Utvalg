"""UI-utilities — cross-cutting Tk-komponenter brukt av alle faner.

Pilot 26 av frontend/backend-mappestrukturen. Pakka samler felles
Tk-baserte komponenter og utility-funksjoner som flere faner deler.

Moduler:
- ``dialog.py``            — ``make_dialog()`` (standard popup-Toplevel)
- ``hotkeys.py``           — felles hurtigtaster + binding-helpere
- ``loading.py``           — loading-overlay
- ``managed_treeview.py``  — ManagedTreeview (drag-n-drop, kolonnevelger,
                              sortering, persist)
- ``selection_summary.py`` — utvalgssummering nederst i appen
- ``treeview_sort.py``     — klikk-sortering for ttk.Treeview
- ``utils.py``             — diverse Tk-helpere
- ``excel_theme.py``       — openpyxl-temaer (ikke Tk, men theming)
- ``tokens.py``            — fargevariabler / palett-tokens

NB (i motsetning til andre src/shared/-pakker): denne pakka SKAL
kunne importere ``tkinter`` — den er definisjonsmessig en GUI-pakke.
"""

# Eksporter undermoduler så ``from src.shared.ui import dialog`` virker
# uten at hver kaller må gjøre full punkt-import.
from . import (  # noqa: F401
    dialog,
    excel_theme,
    hotkeys,
    loading,
    managed_treeview,
    selection_summary,
    tokens,
    treeview_sort,
    utils,
)

__all__ = [
    "dialog",
    "excel_theme",
    "hotkeys",
    "loading",
    "managed_treeview",
    "selection_summary",
    "tokens",
    "treeview_sort",
    "utils",
]
