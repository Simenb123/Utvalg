"""ui_dialog.py — Standard dialog-konstruktør for popupvinduer.

Tk ``Toplevel`` gir deg et bart vindu uten å håndtere følgende selv:

- sentrering over forelder / skjerm
- fornuftig startstørrelse og minsize
- tilgang til max/min-knapper (ikke bare X) — på Windows fjerner
  ``transient(master)`` disse via "tool window"-stilen; vi setter
  ``-toolwindow`` eksplisitt til False slik at brukeren får det samme
  vinduskontroller-settet som på alle andre vinduer
- modal atferd (grab_set)
- Escape-til-lukking

``make_dialog()`` er en én-linjes erstatning for den gjentatte
``tk.Toplevel(master); dialog.title(...); dialog.transient(...);
dialog.grab_set(); dialog.minsize(...)``-prologen som ellers kopieres
inn i hver eneste dialog. Nye popups bør bruke denne; eksisterende
dialoger kan migreres inkrementelt.
"""
from __future__ import annotations

from typing import Literal

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None  # type: ignore


def make_dialog(
    master,
    *,
    title: str,
    width: int = 720,
    height: int = 520,
    min_width: int | None = None,
    min_height: int | None = None,
    modal: bool = True,
    resizable: bool = True,
    center_on: Literal["parent", "screen"] = "parent",
    bind_escape: bool = True,
):
    """Opprett en ferdig-konfigurert ``Toplevel``.

    Dialogen returneres klar til bruk — legg til innholdet ditt, og
    avslutt med ``dialog.wait_window()`` som før.

    Parameters
    ----------
    master
        Foreldrewidget. Dialogen sentreres relativt til dette vinduet
        (med mindre ``center_on="screen"``).
    title
        Vindustittel.
    width, height
        Startstørrelse. Default 720×520 er romslig nok til at
        kolonnevelger, søkedialoger og enkle skjemaer er lesbare uten
        manuell resize.
    min_width, min_height
        Minste tillatte størrelse. Default ~60 % av start­størrelsen
        slik at innholdet ikke presses sammen.
    modal
        True (default) setter ``grab_set`` så brukeren må håndtere
        dialogen før hen kan interagere med hovedvinduet.
    resizable
        False låser størrelsen. Default True.
    center_on
        "parent" (default) sentrerer dialogen over forelder­vinduets
        bounding box. "screen" bruker hele skjermen.
    bind_escape
        True (default) binder ``<Escape>`` til å lukke dialogen.

    Notes
    -----
    Vi unngår ``transient(master)`` fordi det aktiverer Windows' "tool
    window"-stil og fjerner max/min-knappene. I stedet gir vi dialogen
    et normalt vindusset ved å sette ``-toolwindow`` til False
    eksplisitt. Taskbar-knappen for dialogen vises dermed også som en
    separat oppføring — en liten tradeoff for bedre vinduskontroller.
    """
    if tk is None:
        raise RuntimeError("tkinter er ikke tilgjengelig")

    dialog = tk.Toplevel(master)
    dialog.title(title)

    # Beholde max/min + close. Må settes EKSPLISITT til False for å
    # overstyre Tk sin default for Toplevels som er undervindu-aktige.
    try:
        dialog.wm_attributes("-toolwindow", False)
    except Exception:
        pass

    if not resizable:
        dialog.resizable(False, False)

    mw = int(min_width if min_width is not None else round(width * 0.6))
    mh = int(min_height if min_height is not None else round(height * 0.6))
    try:
        dialog.minsize(mw, mh)
    except Exception:
        pass

    # Startplassering + størrelse. update_idletasks() tvinger Tk til å
    # realisere master-koordinatene før vi regner ut sentrum.
    try:
        dialog.update_idletasks()
    except Exception:
        pass

    x, y = 100, 100
    if center_on == "screen":
        try:
            sw = dialog.winfo_screenwidth()
            sh = dialog.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2)
        except Exception:
            pass
    else:
        try:
            # Hvis master ikke er realisert (winfo_width==1), fall tilbake
            # til skjerm-sentrering.
            pw = int(master.winfo_width() or 0)
            ph = int(master.winfo_height() or 0)
            if pw < 50 or ph < 50:
                sw = dialog.winfo_screenwidth()
                sh = dialog.winfo_screenheight()
                x = max(0, (sw - width) // 2)
                y = max(0, (sh - height) // 2)
            else:
                px = int(master.winfo_rootx() or 0)
                py = int(master.winfo_rooty() or 0)
                x = px + max(0, (pw - width) // 2)
                y = py + max(0, (ph - height) // 2)
        except Exception:
            pass

    try:
        dialog.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        pass

    if modal:
        try:
            dialog.grab_set()
        except Exception:
            pass
        # Gi fokus til dialogen når den åpnes, slik at tastatur-handlere
        # virker umiddelbart.
        try:
            dialog.focus_set()
        except Exception:
            pass

    if bind_escape:
        try:
            dialog.bind("<Escape>", lambda _e=None: dialog.destroy())
        except Exception:
            pass

    return dialog
