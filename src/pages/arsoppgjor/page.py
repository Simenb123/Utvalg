"""Årsoppgjør-fanen — paraply-fane med under-faner for Regnskap, Skatt og
Konsolidering.

Ren container — selve under-pages-klassene bygges utenfor (i ui_main) og
settes inn via :py:meth:`add_subpage`. Dette unngår sirkulære imports og
lar ui_main beholde direkte referanser til de tre underfanene (mange
callere ute i koden bruker ``app.page_regnskap``, ``app.page_skatt`` og
``app.page_consolidation``).

Bruksmønster:

    arsoppgjor = ArsoppgjorPage(parent_notebook)
    parent_notebook.add(arsoppgjor, text="Årsoppgjør")

    regnskap = RegnskapPage(arsoppgjor.sub_notebook)
    arsoppgjor.add_subpage(regnskap, text="Regnskap")

    skatt = SkattPage(arsoppgjor.sub_notebook)
    arsoppgjor.add_subpage(skatt, text="Skatt")
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


class ArsoppgjorPage(ttk.Frame):
    """Container-fane for årsoppgjørs-arbeid.

    Eksponerer en intern :py:class:`ttk.Notebook` (``sub_notebook``)
    som under-pages må bygges med som parent. Etter bygging legges
    pagen til via :py:meth:`add_subpage`.
    """

    def __init__(self, parent: tk.Misc, *args: Any, **kwargs: Any) -> None:
        super().__init__(parent, *args, **kwargs)

        # Notebook for under-faner (Regnskap, Skatt, Konsolidering).
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)
        self._subpages: list[tuple[ttk.Frame, str]] = []

    @property
    def sub_notebook(self) -> ttk.Notebook:
        """Den interne Notebook-en. Under-pages må bygges med denne som
        parent, og deretter legges til via :py:meth:`add_subpage`."""
        return self._nb

    def add_subpage(self, page: ttk.Frame, *, text: str) -> None:
        """Legg til en under-fane.

        Pagen MÅ ha den interne notebook-en (``self.sub_notebook``) som
        parent for at Tk-hierarkiet skal være korrekt.
        """
        self._nb.add(page, text=text)
        self._subpages.append((page, text))

    def refresh_from_session(self, session: Any = None, **kwargs: Any) -> None:
        """Videreformidle refresh-kall til alle under-faner.

        ui_main kaller ``refresh_from_session()`` per top-level fane når
        dataset skifter. Vi videresender til alle under-faner som har
        metoden, og svelger eventuelle individuelle feil så ikke én
        feilende underfane bryter de andre.
        """
        for page, _text in self._subpages:
            method = getattr(page, "refresh_from_session", None)
            if not callable(method):
                continue
            try:
                method(session, **kwargs)
            except TypeError:
                # Eldre under-pages kan ta kun session uten kwargs.
                try:
                    method(session)
                except Exception:
                    pass
            except Exception:
                # Forsøk å fortsette med øvrige under-faner selv om en feiler.
                pass
