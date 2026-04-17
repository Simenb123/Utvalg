"""style.py — Fargepalett, fonter og konstanter for flowchart_editor.

Paletten er lånt fra motpost_flowchart_svg.py og theme.py i Utvalg-1 for
visuell konsistens uten faktisk import (holder editoren standalone).
"""

from __future__ import annotations

# Bakgrunn og chrome
CANVAS_BG = "#FFFFFF"
CANVAS_BORDER = "#D0D5DD"
GRID_COLOR = "#F2F4F7"

# Standard node-farger
NODE_FILL_DEFAULT = "#FFFFFF"
NODE_STROKE_DEFAULT = "#D0D5DD"
NODE_TEXT_DEFAULT = "#101828"
NODE_SHADOW = "#E4E7EC"

# Subgraph-farger
SUBGRAPH_FILL = "#F9FAFB"
SUBGRAPH_STROKE = "#98A2B3"
SUBGRAPH_LABEL = "#475467"

# Kanter
EDGE_COLOR = "#667085"
EDGE_LABEL_BG = "#FFFFFF"
EDGE_LABEL_FG = "#475467"

# Seleksjon
SELECTION_STROKE = "#1570EF"
SELECTION_WIDTH = 2

# Kategoripalett (for rask fargevalg på subgraphs og noder)
PALETTE = [
    ("Blå",    "#E6F1FB", "#378ADD"),
    ("Lilla",  "#EEEDFE", "#7F77DD"),
    ("Grønn",  "#E1F5EE", "#1D9E75"),
    ("Oransje","#FAEEDA", "#BA7517"),
    ("Rosa",   "#FDECEC", "#D92D20"),
    ("Teal",   "#CFF7F0", "#0E9384"),
    ("Grå",    "#F2F4F7", "#667085"),
]

# Fonter (Tk-stil)
FONT_TITLE = ("Segoe UI", 9, "bold")
FONT_BODY = ("Segoe UI", 9)
FONT_EDGE = ("Segoe UI", 8)
FONT_SUBGRAPH = ("Segoe UI", 10, "bold")

# Layout-konstanter
DEFAULT_NODE_WIDTH = 160
DEFAULT_NODE_HEIGHT = 60
SUBGRAPH_PADDING = 20
SUBGRAPH_LABEL_HEIGHT = 24
ARROW_SIZE = 10
NODE_CORNER_RADIUS = 10  # for "round" og "subroutine"

# Subgraph-headerbar
SUBGRAPH_HEADER_HEIGHT = 30
SUBGRAPH_HEADER_FILL = "#EFF2F6"

# Auto-høyde for noder
NODE_LINE_HEIGHT = 18
NODE_PADDING = 24

# Grid-layout
GRID_COLS_MAX = 4
GRID_GAP_X = 40
GRID_GAP_Y = 30
SUBGRAPH_OUTER_COLS = 2
SUBGRAPH_OUTER_GAP = 80

# Zoom-grenser
ZOOM_MIN = 0.5
ZOOM_MAX = 2.5
ZOOM_STEP = 1.15
