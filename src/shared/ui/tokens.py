"""Vaak design tokens shared by Tkinter GUI and openpyxl exports.

Single source of truth for brand colors, typography and surface roles.
GUI reads via ``theme.apply_theme``; Excel reads via ``vaak_excel_theme``.
Hex values are stored without leading ``#`` so they can be passed
directly to openpyxl; ``hex_gui(name)`` adds the ``#`` for Tk.
"""
from __future__ import annotations

BG_SAND = "D2BD9C"        # Eksakt match til AarVaaken-logoens banner-tan (presis pikselsampling)
BG_SAND_SOFT = "E5D5B8"   # ~25 % lysere variant av banner-fargen — paneler, kort
BG_NEUTRAL = "F3ECDC"     # Hovedbakgrunn — lys cream som favoriserer tabell-lesbarhet
BG_DATA = "FFFFFF"        # Tabellceller — hvit for maks kontrast
BG_ZEBRA = "F8F2E4"       # Alternerende rad — diskret cream-tone

SAGE = "BDE5AE"
SAGE_DARK = "8CBF7C"
SAGE_WASH = "EAF2DE"
FOREST = "325B1E"
FOREST_HOVER = "24451A"
OLIVE = "A5B572"
SELECT_BG = "2F5FBA"
SELECT_FG = "FFFFFF"

TEXT_PRIMARY = "3A1900"
TEXT_MUTED = "6B5540"
TEXT_ON_SAND = "3A1900"
TEXT_ON_FOREST = "FFFFFF"

BORDER = "C0A580"         # Mellomtone — passer til ny rødtone-baserte sand
BORDER_SOFT = "DDC9AE"    # Lysere kant, samme rødtone

POS_TEXT = "325B1E"
NEG_TEXT = "8B2A1F"
WARN_TEXT = "B7791F"
WARN_SOFT = "F6E5C8"
POS_SOFT = "E6F3DD"
NEG_SOFT = "F3DDD7"

# Mørke status-varianter for fanger med lys bakgrunn (statistikk-tabeller etc.)
POS_TEXT_DARK = "2E7D32"  # Material Green 800 — pille-grønn
NEG_TEXT_DARK = "C62828"  # Material Red 800 — feil-rød

# Info-aksenter (blå) — for "manuell"/"informativ"-status, ikke advarsel/feil
INFO_TEXT = "1565C0"  # mørk blå
INFO_SOFT = "DBEAFE"  # lys blå bakgrunn

# Lett grå border — skiller seg fra BORDER (tan) når neutralt skille trengs
BORDER_LIGHT = "D7D1C7"

# Veldig lys SAGE-wash for chat/info-bakgrunn
SAGE_WASH_SOFT = "EAF7F0"

FONT_FAMILY_DISPLAY = "Segoe UI Variable"
FONT_FAMILY_BODY = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"

FONT_DISPLAY = (FONT_FAMILY_DISPLAY, 22, "bold")
FONT_H1 = (FONT_FAMILY_DISPLAY, 16, "bold")
FONT_H2 = (FONT_FAMILY_DISPLAY, 13, "bold")
FONT_BODY = (FONT_FAMILY_BODY, 10, "normal")
FONT_BODY_BOLD = (FONT_FAMILY_BODY, 10, "bold")
FONT_SMALL = (FONT_FAMILY_BODY, 9, "normal")
FONT_MONO = (FONT_FAMILY_MONO, 10, "normal")


def hex_gui(value: str) -> str:
    """Return ``#RRGGBB`` form required by Tk from token stored without ``#``."""
    return value if value.startswith("#") else f"#{value}"
