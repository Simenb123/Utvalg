"""
AnalysePage module.

This module defines a minimal AnalysePage class that can be used with a
Tkinter‑based GUI. The primary goal of this implementation is to expose
a stable interface for testing and future extensions. The class keeps
track of a session object and an optional dataset, and it allows the
registration of a callback that will be invoked when the user wants to
send a selection of accounts to the next step in the workflow.

The interface is intentionally simple: most of the GUI logic has been
omitted to keep the module lightweight and easy to test. In a real
application, methods like ``_load_from_session`` and ``_send_to_selection``
would contain substantial UI updates and event handling.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

try:
    import pandas as pd  # type: ignore
except Exception:
    # pandas is optional for this minimal interface; only used for type hints.
    pd = None  # type: ignore

# Attempt to import Tkinter. In environments where Tkinter is not available
# (e.g., headless CI systems), we fall back to a dummy ``ttk`` module with a
# minimal ``Frame`` implementation. This allows unit tests to import this
# module without raising ImportError, while still providing a real widget
# hierarchy when running the full GUI application.
try:
    import tkinter as tk  # noqa: F401
    from tkinter import ttk  # type: ignore
except Exception:
    # Fallback dummy Frame if tkinter is unavailable
    class _DummyFrame:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # Store args/kwargs for potential debugging but do nothing else
            self._dummy_args = args
            self._dummy_kwargs = kwargs

    class _DummyTtk:
        Frame = _DummyFrame  # type: ignore

    ttk = _DummyTtk()  # type: ignore


class AnalysePage(ttk.Frame):
    """Minimal AnalysePage for a Tkinter‑based application.

    This class derives from :class:`tkinter.ttk.Frame` so that it can be
    embedded inside a :class:`tkinter.ttk.Notebook`. It holds a reference to
    the current session and an optional dataset. It also allows clients to
    register a callback that will be invoked when the user requests to send
    a selection of accounts to the next step in the workflow.

    Parameters
    ----------
    parent : Any
        The parent widget (typically a :class:`ttk.Notebook` instance). This
        value is forwarded to the :class:`ttk.Frame` constructor.
    """

    def __init__(self, parent: Any) -> None:
        # Initialise the ttk.Frame base class so that this object can be added
        # to a Notebook. Without this call, ttk will raise a TclError when
        # trying to pack or add the widget to a container.
        super().__init__(parent)
        # Store the parent in case it is needed later
        self.parent: Any = parent
        # Reference to the current session; set in refresh_from_session
        self._session: Optional[Any] = None
        # Optional dataset extracted from the session; may be a pandas DataFrame
        self.dataset: Optional[Any] = None
        # Callback to notify when a selection of accounts should be sent to the next step
        self._utvalg_callback: Optional[Callable[[Any], None]] = None

    # Public API -----------------------------------------------------------------

    def set_utvalg_callback(self, callback: Callable[[Any], None]) -> None:
        """Register a callback for sending selected accounts to the utvalg step.

        Parameters
        ----------
        callback : Callable[[Any], None]
            A function that accepts a single argument representing the
            selected accounts. When :meth:`_send_to_selection` is called,
            this callback will be invoked if it has been registered.
        """
        self._utvalg_callback = callback

    def refresh_from_session(self, session: Any) -> None:
        """
        Oppdater AnalysePage basert på et nytt sessionobjekt.

        Denne metoden lagrer en referanse til sessionen og forsøker å
        hente et dataset fra sessionen. Hvis sessionen har en attributt
        ``dataset`` eller ``df``, settes denne verdien på siden som
        ``dataset`` uavhengig av typen. Dersom en feil oppstår ved
        uthenting, beholdes den tidligere verdien. Metoden kaller
        deretter :meth:`_load_from_session` for å oppdatere eventuell
        GUI‑tilstand. Eventuelle unntak herfra slukes stille for å hindre
        at GUI‑en krasjer.

        Parametre
        ----------
        session : Any
            Et objekt som representerer gjeldende sessionstate. Sessionen
            bør inneholde en ``dataset`` eller ``df`` attributt dersom et
            dataset er tilgjengelig.
        """
        # Oppdater referansen til gjeldende session
        self._session = session
        # Prøv å hente dataset fra sessionen. Vi lagrer verdien som den er
        # (kan være hva som helst) slik at tester kan verifisere at
        # tilordningen fungerer. Hvis ingen dataset finnes, beholdes
        # eksisterende verdi.
        value = None
        # Foretrekk attributt "dataset"
        if hasattr(session, "dataset"):
            try:
                value = session.dataset  # type: ignore[attr-defined]
            except Exception:
                value = None
        # Fallback til "df" hvis dataset ikke ble satt
        if value is None and hasattr(session, "df"):
            try:
                value = session.df  # type: ignore[attr-defined]
            except Exception:
                value = None
        if value is not None:
            self.dataset = value
        # Kall intern lastemetode og ignorer feil
        try:
            self._load_from_session()
        except Exception:
            pass

    # Internal API ---------------------------------------------------------------

    def _load_from_session(self) -> None:
        """Load UI state from the current session.

        Subclasses may override this method to perform any necessary
        operations when the session changes, such as rebuilding pivot
        tables or updating widgets. The default implementation does
        nothing.
        """
        # In a full implementation, this method would refresh GUI widgets
        # based on the dataset and any other state stored in the session.
        return None

    def _send_to_selection(self, accounts: Any) -> None:
        """Send selected accounts to the utvalg callback, if one is registered.

        Parameters
        ----------
        accounts : Any
            A representation of the selected accounts, typically a list
            or other iterable. If a callback has been registered via
            :meth:`set_utvalg_callback`, it will be invoked with this
            value.
        """
        if self._utvalg_callback is not None:
            try:
                self._utvalg_callback(accounts)
            except Exception:
                # Swallow exceptions in callbacks to prevent GUI crashes
                pass