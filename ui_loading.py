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

    # Bredde i piksler for AarVaaken-banneret på loading-overlayen.
    # Bildets aspekt er 4:1 (2508x627) — høyde beregnes proporsjonalt.
    _BANNER_WIDTH = 360

    def __init__(self, master: tk.Widget):
        self.master = master
        self._win: tk.Toplevel | None = None
        self._lbl: ttk.Label | None = None
        self._pb: ttk.Progressbar | None = None
        self._banner_photo: object | None = None  # tk.PhotoImage | ImageTk.PhotoImage
        self._count = 0

    def _load_banner(self) -> object | None:
        """Last AarVaaken-bannerbildet fra doc/pictures (lazy, én gang).

        Krever Pillow for resize. Hvis Pillow eller filen mangler:
        returnerer None (overlay vises uten bilde).

        Søkerekkefølge:
          1. PyInstaller-bundle (sys._MEIPASS/doc/pictures)
          2. Repo-rot relativt til denne filen (dev-kjøring)
          3. app_paths.sources_dir/data_dir (hvis konfigurert til repo)
        """
        if self._banner_photo is not None:
            return self._banner_photo
        try:
            from PIL import Image, ImageTk  # type: ignore[import-untyped]
        except Exception:
            return None

        from pathlib import Path
        import sys

        candidates: list[Path] = []
        # PyInstaller — datas blir lagt under _MEIPASS
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "doc" / "pictures" / "AarVaaken.png")
        # Dev-kjøring fra repo
        candidates.append(Path(__file__).resolve().parent / "doc" / "pictures" / "AarVaaken.png")
        # Bruker-konfigurert kilde-/data-mappe som siste fallback
        try:
            import app_paths
            for base in (app_paths.sources_dir(), app_paths.data_dir()):
                if base is None:
                    continue
                candidates.append(base / "doc" / "pictures" / "AarVaaken.png")
        except Exception:
            pass

        pic_path = next((p for p in candidates if p.exists()), None)
        if pic_path is None:
            return None

        try:
            img = Image.open(str(pic_path))

            # Crop near-white kanter slik at motivet flukter med
            # overlay-bakgrunnen (samme tilnærming som splash).
            try:
                gray = img.convert("L")
                bw = gray.point(lambda p: 255 if p < 250 else 0)
                bbox = bw.getbbox()
                if bbox:
                    img = img.crop(bbox)
            except Exception:
                pass

            w, h = img.size
            target_w = self._BANNER_WIDTH
            target_h = max(1, int(round(target_w * h / w)))
            img = img.resize((target_w, target_h), Image.LANCZOS)
            self._banner_photo = ImageTk.PhotoImage(img)
        except Exception:
            self._banner_photo = None
        return self._banner_photo

    def show(self, text: str = "Arbeider...") -> None:
        self._count += 1
        parent = self.master.winfo_toplevel()
        win = self._win
        if win is None:
            # Theme-farger fra vaak_tokens (samme som splash-skjermen)
            try:
                import vaak_tokens as _vt
                bg_color = "#" + _vt.BG_SAND_SOFT
                border_color = "#" + _vt.SAGE_DARK
                text_color = "#" + _vt.FOREST
                font_family = _vt.FONT_FAMILY_BODY
            except Exception:
                bg_color = "#F4EDDC"
                border_color = "#8CBF7C"
                text_color = "#325B1E"
                font_family = "Segoe UI"

            win = tk.Toplevel(parent)
            win.overrideredirect(True)
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass
            win.withdraw()
            win.configure(bg=border_color)  # ramme-farge

            # Inner frame: pack med 2px padding gir 2px sage-ramme i win-bg
            inner = tk.Frame(win, bg=bg_color)
            inner.pack(padx=2, pady=2, fill="both", expand=True)

            # AarVaaken-banner — vises kun hvis bildet kan lastes
            banner = self._load_banner()
            if banner is not None:
                banner_lbl = tk.Label(inner, image=banner, bg=bg_color, borderwidth=0)
                banner_lbl.image = banner  # GC-referanse
                banner_lbl.pack(padx=24, pady=(20, 12))

            # Status-tekst i Forest-grønn (samme som splash-undertittel)
            lbl = tk.Label(
                inner,
                text=text,
                bg=bg_color,
                fg=text_color,
                font=(font_family, 10, "normal"),
            )
            lbl.pack(padx=24, pady=(0, 10))

            pb = ttk.Progressbar(inner, mode="indeterminate", length=240)
            pb.pack(padx=24, pady=(0, 20))

            self._win = win
            self._lbl = lbl
            self._pb = pb

        # Sentrer kompakt overlay på parent-vinduet (ikke dekk hele).
        # Inner-frame styrer størrelsen via dens requested_size + 2px ramme.
        try:
            self._win.update_idletasks()  # type: ignore[union-attr]
            ww = self._win.winfo_reqwidth()  # type: ignore[union-attr]
            wh = self._win.winfo_reqheight()  # type: ignore[union-attr]
            pw = max(parent.winfo_width(), 400)
            ph = max(parent.winfo_height(), 200)
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = px + max(0, (pw - ww) // 2)
            y = py + max(0, (ph - wh) // 2)
            self._win.geometry(f"{ww}x{wh}+{x}+{y}")  # type: ignore[union-attr]
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

    def set_text(self, text: str) -> None:
        """Oppdater label-tekst uten å vise/skjule. Brukes for å gi
        brukeren visuell progresjon mens en lang jobb går gjennom flere
        stadier."""
        if self._lbl is not None:
            try:
                self._lbl.configure(text=text)
            except Exception:
                pass
        if self._win is not None:
            try:
                self._win.update_idletasks()
            except Exception:
                pass

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

            # Kjør on_done FØR hide. Da kan callbacken vise en ny overlay
            # (f.eks. App-nivå "Bygger Analyse...") før vår blir borte —
            # ingen synlig flicker mellom dem. Hvis callback'en feiler,
            # skjuler vi uansett etterpå.
            try:
                if kind == "ok":
                    on_done(payload)  # type: ignore[arg-type]
                else:
                    err, tb = payload  # type: ignore[misc]
                    if on_error is not None:
                        on_error(err, tb)  # type: ignore[arg-type]
                    else:
                        raise err
            finally:
                self.hide()

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
