"""Tkinter theme built on Vaak brand tokens.

Single entry: ``apply_theme(root)``. All colors and fonts come from
``vaak_tokens`` so the Excel exports stay visually consistent with
the GUI.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import vaak_tokens as vt

_H = vt.hex_gui


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    bg = _H(vt.BG_NEUTRAL)
    surface = _H(vt.BG_DATA)
    surface_soft = _H(vt.BG_SAND_SOFT)
    sand = _H(vt.BG_SAND)
    select_bg = _H(vt.SELECT_BG)
    select_fg = _H(vt.SELECT_FG)
    border = _H(vt.BORDER)
    border_soft = _H(vt.BORDER_SOFT)
    fg = _H(vt.TEXT_PRIMARY)
    muted = _H(vt.TEXT_MUTED)
    forest = _H(vt.FOREST)
    forest_hover = _H(vt.FOREST_HOVER)
    sage = _H(vt.SAGE)
    sage_dark = _H(vt.SAGE_DARK)
    pos = _H(vt.POS_TEXT)
    pos_soft = _H(vt.POS_SOFT)
    warn = _H(vt.WARN_TEXT)
    warn_soft = _H(vt.WARN_SOFT)
    zebra = _H(vt.BG_ZEBRA)

    try:
        root.configure(background=bg)
    except Exception:
        pass

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            f = tkfont.nametofont(name)
            f.configure(family=vt.FONT_FAMILY_BODY, size=10)
        except Exception:
            pass
    try:
        tkfont.nametofont("TkHeadingFont").configure(
            family=vt.FONT_FAMILY_BODY, size=10, weight="bold"
        )
    except Exception:
        pass

    body = (vt.FONT_FAMILY_BODY, 10)
    body_bold = (vt.FONT_FAMILY_BODY, 10, "bold")

    style.configure(".", background=bg, foreground=fg, font=body)

    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=surface)
    style.configure("Sand.TFrame", background=sand)
    style.configure("SandSoft.TFrame", background=surface_soft)

    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Muted.TLabel", background=bg, foreground=muted)
    style.configure("Section.TLabel", background=bg, foreground=fg, font=body_bold)
    style.configure("Status.TLabel", background=bg, foreground=muted)
    style.configure(
        "Logo.TLabel",
        background=sand,
        foreground=forest,
        font=(vt.FONT_FAMILY_DISPLAY, 16, "bold"),
        padding=(12, 6),
    )
    style.configure("Ready.TLabel", background=pos_soft, foreground=pos, padding=(8, 4))
    style.configure(
        "Warning.TLabel", background=warn_soft, foreground=warn, padding=(8, 4)
    )

    style.configure("TLabelframe", background=bg, bordercolor=border, relief="solid")
    style.configure(
        "TLabelframe.Label", background=bg, foreground=fg, font=body_bold
    )

    style.configure(
        "TButton",
        padding=(10, 6),
        background=surface_soft,
        foreground=fg,
        bordercolor=border,
    )
    style.map(
        "TButton",
        background=[("active", sand), ("pressed", border)],
        bordercolor=[("focus", forest)],
    )
    style.configure(
        "Primary.TButton",
        padding=(12, 7),
        background=forest,
        foreground=_H(vt.TEXT_ON_FOREST),
        bordercolor=forest,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", forest_hover),
            ("pressed", forest_hover),
            ("disabled", "#B8C5AD"),
        ],
        foreground=[("disabled", "#F5F5F0")],
    )
    style.configure(
        "Secondary.TButton",
        padding=(10, 6),
        background=sand,
        foreground=fg,
        bordercolor=border,
    )
    style.map(
        "Secondary.TButton",
        background=[("active", sage), ("pressed", sage_dark)],
    )

    style.configure(
        "TEntry",
        fieldbackground=surface,
        background=surface,
        foreground=fg,
        bordercolor=border_soft,
        insertcolor=fg,
    )
    style.map("TEntry", bordercolor=[("focus", forest)])
    style.configure(
        "TCombobox",
        fieldbackground=surface,
        background=surface,
        foreground=fg,
        bordercolor=border_soft,
        arrowsize=14,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", surface), ("disabled", surface_soft)],
        foreground=[("disabled", muted)],
        bordercolor=[("focus", forest)],
    )

    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=surface_soft,
        foreground=fg,
        padding=(14, 7),
        font=body,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", sand), ("active", sage)],
        foreground=[("selected", fg)],
    )

    style.configure(
        "Treeview",
        rowheight=24,
        font=body,
        background=surface,
        fieldbackground=surface,
        foreground=fg,
        bordercolor=border_soft,
    )
    style.configure(
        "Treeview.Heading",
        font=body_bold,
        background=surface_soft,
        foreground=fg,
        bordercolor=border,
    )
    style.map(
        "Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )


_TREEVIEW_TAGS = {
    "sumline": {
        "background": _H(vt.SAGE_WASH),
        "foreground": _H(vt.TEXT_PRIMARY),
        "font": (vt.FONT_FAMILY_BODY, 10, "bold"),
    },
    "sumline_major": {
        "background": _H(vt.SAGE_DARK),
        "foreground": _H(vt.TEXT_PRIMARY),
        "font": (vt.FONT_FAMILY_BODY, 10, "bold"),
    },
    "sumline_total": {
        "background": _H(vt.FOREST),
        "foreground": _H(vt.TEXT_ON_FOREST),
        "font": (vt.FONT_FAMILY_BODY, 11, "bold"),
    },
    "total": {
        "background": _H(vt.FOREST),
        "foreground": _H(vt.TEXT_ON_FOREST),
        "font": (vt.FONT_FAMILY_BODY, 11, "bold"),
    },
    "zebra": {"background": _H(vt.BG_ZEBRA)},
    "commented": {"foreground": _H(vt.FOREST)},
    "warning": {"background": _H(vt.WARN_SOFT), "foreground": _H(vt.WARN_TEXT)},
    "positive": {"foreground": _H(vt.POS_TEXT)},
    "negative": {"foreground": _H(vt.NEG_TEXT)},
}


def style_treeview_tags(tree: ttk.Treeview, *names: str) -> None:
    """Apply Vaak-themed Treeview tags. ``names`` limits which tags to apply;
    empty means all standard tags.
    """
    if not names:
        names = tuple(_TREEVIEW_TAGS.keys())
    for tag in names:
        conf = _TREEVIEW_TAGS.get(tag)
        if conf:
            try:
                tree.tag_configure(tag, **conf)
            except Exception:
                pass


def tree_tag(name: str) -> dict:
    """Return a copy of the configured options for a standard tag."""
    return dict(_TREEVIEW_TAGS.get(name, {}))


# ---------------------------------------------------------------------------
# Tab group accents — tynne fargestriper til venstre for fanetekst
#
# ttk.Notebook støtter ikke direkte per-tab bakgrunnsfarge på en robust måte.
# I stedet bygger vi små PhotoImage-striper og setter dem som tab-ikoner via
# ``nb.tab(tab_id, image=..., compound="left")``. Det gir en diskret visuell
# gruppering uten å hacke ttk-layoutet.

# Semantiske grupper med fargene deres. Holdes med i palette-familien så
# aksentene ikke klasher med tema-fargene.
TAB_GROUP_COLORS: dict[str, str] = {
    "nav":      "7A8FA8",   # Oversikt/Dataset — slate blå (inngang/navigasjon)
    "analyse":  "8CBF7C",   # Analyse/Saldobalanse/Reskontro — sage (dataanalyse)
    "planning": "C89860",   # Vesentlighet/Scoping/Handlinger — amber (planlegging)
    "kontroll": "A86C80",   # MVA/A07/Driftsmidler — plum (områdekontroller)
}


def make_tab_accent(root: tk.Misc, color_hex: str,
                    width: int = 4, height: int = 18) -> tk.PhotoImage:
    """Lag en tynn farget PhotoImage til bruk som tab-ikon.

    Kalleren må selv beholde en referanse til bildet (ellers GC-ryddes det
    og Tk viser ingenting). Typisk: lagres som attr på App-instansen.
    """
    hex_code = color_hex if color_hex.startswith("#") else f"#{color_hex}"
    img = tk.PhotoImage(master=root, width=width, height=height)
    try:
        img.put(hex_code, to=(0, 0, width, height))
    except Exception:
        pass
    return img


def apply_tab_group_accents(
    nb: ttk.Notebook,
    groups: dict[str, list],
    *,
    _cache: dict[str, tk.PhotoImage] | None = None,
) -> dict[str, tk.PhotoImage]:
    """Sett fargeaksent på angitte faner gruppert etter semantisk gruppe.

    ``groups`` mapper gruppenøkkel → liste med tab-widgets (page-instanser).
    Gruppe-nøkler må finnes i ``TAB_GROUP_COLORS``. Returnerer dict med de
    opprettede PhotoImage-ene så kaller kan holde referansen i live.
    """
    if _cache is None:
        _cache = {}
    for group_name, pages in groups.items():
        color = TAB_GROUP_COLORS.get(group_name)
        if not color:
            continue
        img = _cache.get(group_name)
        if img is None:
            img = make_tab_accent(nb, color)
            _cache[group_name] = img
        for page in pages:
            if page is None:
                continue
            try:
                nb.tab(page, image=img, compound="left")
            except Exception:
                pass
    return _cache
