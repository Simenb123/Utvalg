"""Pytest configuration for this repo.

Why this exists
---------------
The application is a Windows/Tkinter desktop app. In some CI/container
environments the standard library ``tkinter`` module is not present.

Several production modules import tkinter at module import time. The unit
tests in this repo are intentionally written so that most of them can run
in *headless* mode (they test pure helper functions and interface
contracts), but we still need imports to succeed during pytest collection.

This conftest installs a minimal stub for ``tkinter`` (incl. ttk,
messagebox, filedialog) when the real module is missing.

The stub is only used in the test process; it does not affect normal
runtime on Windows where tkinter is available.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

# Ensure the project root (the directory that contains the application
# modules) is importable when tests are executed from different cwd/rootdir
# setups.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _install_tkinter_stub() -> None:
    if "tkinter" in sys.modules:
        return

    tkinter_mod = types.ModuleType("tkinter")

    class TclError(RuntimeError):
        """Replacement for tkinter.TclError in environments without Tk."""

    class Misc:
        """Base class used in type hints."""

    class _Var:
        def __init__(self, value=None):
            self._value = value

        def get(self):
            return self._value

        def set(self, value):
            self._value = value

    class StringVar(_Var):
        pass

    class IntVar(_Var):
        pass

    class BooleanVar(_Var):
        pass

    class DoubleVar(_Var):
        pass

    class Tk(Misc):
        def __init__(self, *args, **kwargs):
            # Trigger existing headless fallbacks in the app.
            raise TclError("tkinter is not available in this environment")

        def mainloop(self, *args, **kwargs):
            return None

        def withdraw(self):
            return None

        def destroy(self):
            return None

    class Widget(Misc):
        def __init__(self, *args, **kwargs):
            raise TclError("tkinter widgets are not available")

        # common no-op widget APIs used defensively in code paths
        def pack(self, *args, **kwargs):
            return None

        def grid(self, *args, **kwargs):
            return None

        def place(self, *args, **kwargs):
            return None

        def config(self, *args, **kwargs):
            return None

        configure = config

        def bind(self, *args, **kwargs):
            return None

        def insert(self, *args, **kwargs):
            return None

        def delete(self, *args, **kwargs):
            return None

        def get_children(self, *args, **kwargs):
            return []

        def selection_set(self, *args, **kwargs):
            return None

        def selection(self):
            return ()

        def yview(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

        def add(self, *args, **kwargs):
            return None

        def select(self, *args, **kwargs):
            return None

    class Frame(Widget):
        pass

    class Toplevel(Widget):
        pass

    tkinter_mod.END = "end"
    tkinter_mod.W = "w"
    tkinter_mod.E = "e"
    tkinter_mod.N = "n"
    tkinter_mod.S = "s"

    tkinter_mod.TclError = TclError
    tkinter_mod.Misc = Misc
    tkinter_mod.Tk = Tk
    tkinter_mod.Frame = Frame
    tkinter_mod.Toplevel = Toplevel
    tkinter_mod.StringVar = StringVar
    tkinter_mod.IntVar = IntVar
    tkinter_mod.BooleanVar = BooleanVar
    tkinter_mod.DoubleVar = DoubleVar

    # --- ttk submodule ---
    ttk_mod = types.ModuleType("tkinter.ttk")

    class _TtkWidget(Widget):
        pass

    for _name in [
        "Frame",
        "Label",
        "LabelFrame",
        "Button",
        "Entry",
        "Combobox",
        "Checkbutton",
        "Radiobutton",
        "Spinbox",
        "Separator",
        "Notebook",
        "Treeview",
        "Scrollbar",
        "Panedwindow",
        "Progressbar",
        "Style",
    ]:
        setattr(ttk_mod, _name, type(_name, (_TtkWidget,), {}))

    tkinter_mod.ttk = ttk_mod

    # --- messagebox submodule ---
    messagebox_mod = types.ModuleType("tkinter.messagebox")

    def _mb_noop(*_args, **_kwargs):
        return None

    def _ask_no(*_args, **_kwargs):
        return False

    messagebox_mod.showinfo = _mb_noop
    messagebox_mod.showwarning = _mb_noop
    messagebox_mod.showerror = _mb_noop
    messagebox_mod.askyesno = _ask_no
    messagebox_mod.askokcancel = _ask_no
    tkinter_mod.messagebox = messagebox_mod

    # --- filedialog submodule ---
    filedialog_mod = types.ModuleType("tkinter.filedialog")

    def _return_empty(*_args, **_kwargs):
        return ""

    filedialog_mod.askopenfilename = _return_empty
    filedialog_mod.asksaveasfilename = _return_empty
    filedialog_mod.askdirectory = _return_empty
    tkinter_mod.filedialog = filedialog_mod

    sys.modules["tkinter"] = tkinter_mod
    sys.modules["tkinter.ttk"] = ttk_mod
    sys.modules["tkinter.messagebox"] = messagebox_mod
    sys.modules["tkinter.filedialog"] = filedialog_mod


# Install stub at import time for pytest collection.
try:
    import tkinter  # noqa: F401
except Exception:
    _install_tkinter_stub()


def _neutralize_blocking_dialogs() -> None:
    """Erstatt messagebox/filedialog-funksjoner med no-ops under test.

    Why: På Windows er ekte tkinter tilgjengelig, og produksjonskode kaller
    messagebox.showinfo/askyesno/filedialog.askopenfilename osv. i flere
    kodestier. Uten denne patchen poppet testene opp blokkerende GUI-dialoger
    som stoppet hele suiten til en bruker klikket OK.
    """
    try:
        import tkinter.messagebox as _mb  # type: ignore
    except Exception:
        _mb = None  # type: ignore
    if _mb is not None:
        def _none(*_a, **_k):
            return None

        def _false(*_a, **_k):
            return False

        def _no(*_a, **_k):
            return "no"

        for _name in ("showinfo", "showwarning", "showerror"):
            try:
                setattr(_mb, _name, _none)
            except Exception:
                pass
        for _name in ("askyesno", "askokcancel", "askretrycancel", "askyesnocancel"):
            try:
                setattr(_mb, _name, _false)
            except Exception:
                pass
        try:
            setattr(_mb, "askquestion", _no)
        except Exception:
            pass

    try:
        import tkinter.filedialog as _fd  # type: ignore
    except Exception:
        _fd = None  # type: ignore
    if _fd is not None:
        def _empty_str(*_a, **_k):
            return ""

        def _empty_tuple(*_a, **_k):
            return ()

        for _name in ("askopenfilename", "asksaveasfilename", "askdirectory"):
            try:
                setattr(_fd, _name, _empty_str)
            except Exception:
                pass
        for _name in ("askopenfilenames",):
            try:
                setattr(_fd, _name, _empty_tuple)
            except Exception:
                pass


_neutralize_blocking_dialogs()


# ---------------------------------------------------------------------------
# Cache-invalidering mellom tester
#
# Modul-nivå cacher i produksjonskoden kan lekke data mellom tester som
# bruker samme klient-navn med ulik tmp_path. Denne fixturen tømmer
# cachene før hver test så testene ikke ser hverandres tilstand.
# ---------------------------------------------------------------------------


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _reset_module_caches():
    """Tøm modul-nivå cacher som kan lekke mellom tester."""
    try:
        import regnskap_client_overrides as _rco
        _rco.invalidate_client_cache()
        if hasattr(_rco, "_overrides_dir_cached"):
            _rco._overrides_dir_cached.cache_clear()
        if hasattr(_rco, "_read_payload_cached_raw"):
            _rco._read_payload_cached_raw.cache_clear()
    except Exception:
        pass
    yield
