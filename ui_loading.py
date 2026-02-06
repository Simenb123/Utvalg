from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from contextlib import contextmanager

import queue
import threading
import traceback
from typing import Callable, TypeVar

T = TypeVar("T")


class LoadingOverlay:
    """En enkel 'jobber...' overlay.

    Tips:
      * Bruk `with overlay.busy("..."):` for korte operasjoner.
      * Bruk `overlay.run_async(...)` for lange operasjoner, slik at GUI ikke fryser.
    """

    def __init__(self, master: tk.Widget):
        self.master = master
        self._win: tk.Toplevel | None = None
        self._lbl: ttk.Label | None = None
        self._pb: ttk.Progressbar | None = None
        self._count = 0

    def show(self, text: str = "Arbeider...") -> None:
        self._count += 1
        parent = self.master.winfo_toplevel()
        win = self._win
        if win is None:
            win = tk.Toplevel(parent)
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass
            win.withdraw()
            frm = ttk.Frame(win, padding=12)
            frm.place(relx=0.5, rely=0.5, anchor="center")
            lbl = ttk.Label(frm, text=text)
            lbl.pack(pady=(0, 8))
            pb = ttk.Progressbar(frm, mode="indeterminate", length=220)
            pb.pack()
            self._win = win
            self._lbl = lbl
            self._pb = pb

        # cover parent
        try:
            w = max(parent.winfo_width(), 400)
            h = max(parent.winfo_height(), 200)
            x = parent.winfo_rootx()
            y = parent.winfo_rooty()
            self._win.geometry(f"{w}x{h}+{x}+{y}")  # type: ignore[union-attr]
        except Exception:
            pass

        if self._lbl is not None:
            self._lbl.configure(text=text)

        if self._win is not None:
            self._win.deiconify()
            self._win.lift()

        try:
            parent.config(cursor="watch")
        except Exception:
            pass

        try:
            if self._pb is not None:
                self._pb.start(12)
        except Exception:
            pass

        if self._win is not None:
            self._win.update_idletasks()

    def hide(self) -> None:
        if self._count > 0:
            self._count -= 1
        if self._count > 0:
            return

        win = self._win
        if not win:
            return

        try:
            if self._pb is not None:
                self._pb.stop()
        except Exception:
            pass

        try:
            self.master.winfo_toplevel().config(cursor="")
        except Exception:
            pass

        win.withdraw()

    def run_async(
        self,
        text: str,
        work: Callable[[], T],
        *,
        on_done: Callable[[T], None],
        on_error: Callable[[BaseException, str], None] | None = None,
        poll_ms: int = 100,
    ) -> None:
        """Kjør en tung jobb i bakgrunnstråd mens overlayen vises.

        `on_done` / `on_error` blir alltid kalt i GUI-tråden (via `after`).
        """
        self.show(text)
        q: "queue.Queue[tuple[str, object]]" = queue.Queue()

        def _worker() -> None:
            try:
                res = work()
            except BaseException as e:
                q.put(("err", (e, traceback.format_exc())))
            else:
                q.put(("ok", res))

        threading.Thread(target=_worker, daemon=True).start()

        def _poll() -> None:
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                # GUI kan være lukket mens vi jobber – da vil `after` feile.
                try:
                    self.master.after(poll_ms, _poll)
                except Exception:
                    return
                return

            self.hide()
            if kind == "ok":
                on_done(payload)  # type: ignore[arg-type]
            else:
                err, tb = payload  # type: ignore[misc]
                if on_error is not None:
                    on_error(err, tb)  # type: ignore[arg-type]
                else:
                    raise err

        try:
            self.master.after(poll_ms, _poll)
        except Exception:
            # Hvis vinduet allerede er lukket, gjør vi ingenting.
            pass

    @contextmanager
    def busy(self, text: str = "Arbeider..."):
        self.show(text)
        try:
            yield
        finally:
            self.hide()
