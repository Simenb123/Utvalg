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
