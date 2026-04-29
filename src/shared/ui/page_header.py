"""PageHeader — felles topptittel-komponent for alle hovedfaner.

Mål:
- Konsistent plassering av tittel/sub-tittel (venstre), side-spesifikke
  kontroller (midt) og standard-handlinger (høyre).
- Refresh og Eksport bor alltid på samme sted (høyre side).
- Refresh = ↻-ikon (bilde) — F5 trigger den også.
- Eksport = ⬇-ikon. Én eksport → klikk kjører direkte. Flere eksporter →
  knappen åpner en dropdown-meny.

Bruksmønster:

    from src.shared.ui.page_header import PageHeader

    header = PageHeader(self, title="Regnskap", subtitle="Klient — År")
    header.pack(fill="x", padx=8, pady=(8, 4))

    header.set_refresh(command=self._on_oppdater, key="<F5>")
    header.add_export("Excel", command=self._export_excel)
    header.add_export("HTML",  command=self._export_html)
    header.add_export("PDF",   command=self._export_pdf)

    # Side-spesifikke kontroller (Rammeverk-velger osv.)
    ttk.Label(header.center, text="Rammeverk:").pack(side="left", padx=(0, 6))
    ttk.Combobox(header.center, ...).pack(side="left")

Side-spesifikke kjerne-handlinger ("Beregn", "Bygg datasett") hører IKKE
hjemme i headeren — de er hovedhandling for siden, ikke standard-knapper.
"""
from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ikon-lasting — bruker prosjektets export.png / refresh.png
# ---------------------------------------------------------------------------

_ICON_DIR = Path(__file__).resolve().parents[3] / "doc" / "pictures"
_ICON_SIZE = 28  # piksler — stor nok til at ikonet er tydelig synlig

# Modul-cache for prosesserte PIL-bilder (root-uavhengige).
# PhotoImage må derimot bygges per Tk-rot, fordi den bindes til en spesifikk
# Tk-interpreter — ellers feiler bruk i nye Tk-rot (f.eks. mellom tester
# som opprette/ødelegger root) med ``image "pyimageN" doesn't exist``.
_pil_image_cache: dict[str, Any] = {}

# Custom ttk-style for ikon-knapper — minimerer padding så ikonet fyller
# knappen, og senker borderwidth for et mer flatt/moderne preg.
_styles_initialised = False


def _ensure_styles() -> None:
    """Registrer ttk-stilene én gang. Trygt å kalle flere ganger."""
    global _styles_initialised
    if _styles_initialised:
        return
    try:
        style = ttk.Style()
        style.configure(
            "PageHeaderIcon.TButton",
            padding=4,
            borderwidth=1,
            relief="flat",
        )
        style.configure(
            "PageHeaderIcon.TMenubutton",
            padding=4,
            borderwidth=1,
            relief="flat",
            indicatoron=False,
        )
        _styles_initialised = True
    except Exception:
        pass


def _load_pil_image(name: str) -> Any | None:
    """Last og prosesser et ikon-bilde til PIL-format. Resultatet caches.

    Returnerer None hvis PIL eller filen mangler.
    """
    cached = _pil_image_cache.get(name)
    if cached is not None:
        return cached
    path = _ICON_DIR / f"{name}.png"
    if not path.exists():
        log.debug("Ikon %s mangler på %s", name, path)
        return None
    try:
        from PIL import Image  # type: ignore[import-untyped]
    except Exception:
        log.debug("PIL ikke tilgjengelig — bruker Unicode-fallback for %s", name)
        return None

    try:
        img = Image.open(str(path)).convert("RGBA")

        # Velg resample-algoritme én gang.
        try:
            resample = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]

        # Forhåndsskalering: kilde-PNG-ene er 1254×1254 (~1.5M piksler).
        # _whitepx_to_alpha og _deepen_green itererer per piksel i Python,
        # så vi MÅ skalere ned først eller startup blir veldig tregt.
        # Skalér til 4× target-størrelse (112×112) — gir nok headroom for
        # trim+pad uten å miste detalj, men kutter pikselantallet med 95%.
        prescale = _ICON_SIZE * 4
        if max(img.size) > prescale:
            ratio = prescale / float(max(img.size))
            new_size = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
            img = img.resize(new_size, resample)

        # export.png har hvit bakgrunn — konverter nær-hvitt til transparent
        # slik at ikonet smelter inn i app-bakgrunnen i stedet for å ha en
        # synlig hvit firkant rundt seg.
        if name == "export":
            img = _whitepx_to_alpha(img)

        # Trim transparent kanter slik at ikonet fyller mer av knappen
        # i stedet for å bli liten i en stor padding-firkant.
        img = _trim_transparent(img)

        # Pad til kvadrat (transparent fyll) før resize, slik at vi ikke
        # forvrenger ikoner med ulik aspekt-ratio (f.eks. en bred refresh-
        # symbol vs. en høy download-pil). Resultat: alle ikoner ser
        # konsistent kvadratiske ut etter resize.
        img = _pad_to_square(img)

        # Forsterk fargen så grønnfargen blir tydelig og ikke blassne ved
        # nedskalering. Erstatter eksisterende grønne piksler med en mørkere/
        # mer mettet grønntone — dette gir mer "designet" preg enn de
        # default-blasse pastellfargene fra kilde-PNG-en.
        img = _deepen_green(img)

        # Skaler til presis kvadratstørrelse — bruk RGBA-resize direkte
        # i stedet for thumbnail, slik at vi alltid ender på _ICON_SIZE x _ICON_SIZE
        # uavhengig av aspekt-ratio på input.
        img = img.resize((_ICON_SIZE, _ICON_SIZE), resample)
        _pil_image_cache[name] = img
        return img
    except Exception:
        log.debug("Feil ved lasting av ikon %s", name, exc_info=True)
        return None


def _load_icon(name: str, master: Optional[tk.Misc] = None) -> Any | None:
    """Returner en PhotoImage bundet til ``master``-vinduet.

    PIL-bildet caches globalt (root-uavhengig), men selve PhotoImage-
    instansen må bygges per Tk-rot. Ellers feiler ikonet i nye Tk-rot
    (typisk mellom tester) med ``image "pyimageN" doesn't exist``.
    """
    img = _load_pil_image(name)
    if img is None:
        return None
    try:
        from PIL import ImageTk  # type: ignore[import-untyped]
    except Exception:
        return None
    try:
        return ImageTk.PhotoImage(img, master=master)
    except Exception:
        log.debug("Kunne ikke bygge PhotoImage for %s", name, exc_info=True)
        return None


# Dyp grønntone matchet til app-temaets aktive piller (HB/SB grønn = #2e7d32).
# Bruker samme verdi for å gi visuell sammenheng — når en pille er grønn
# fordi noe er aktivt/lastet, bruker handlings-knappene samme grønn.
_DEEP_GREEN_RGB = (46, 125, 50)  # #2e7d32 — Material Green 800 / app-pille-grønn


def _deepen_green(img: "Any") -> "Any":
    """Erstatt grønnaktige piksler med en dypere, mer mettet grønntone.

    Bevarer alpha-kanalen og piksel-formen (linjer/anti-alias-kanter), men
    overstyrer fargen til ``_DEEP_GREEN_RGB``. Dette gir konsistent dypere
    grønnfarge på tvers av alle ikoner uten at brukeren trenger å lage nye
    PNG-filer.

    Strategien: alle piksler der grønn er den dominerende kanalen og
    pikselen er ikke-transparent, får ny grønn-toning med samme alpha
    (slik at anti-alias-graderingen i kantene beholdes).
    """
    try:
        deep_r, deep_g, deep_b = _DEEP_GREEN_RGB
        data = list(img.getdata())
        new = []
        for r, g, b, a in data:
            if a == 0:
                new.append((r, g, b, a))
                continue
            # Er dette en grønn piksel? Grønn-kanal dominerer og pikselen
            # er ikke nær svart/hvit/grå.
            is_greenish = (g > r and g > b and g > 80)
            if is_greenish:
                # Bruk alpha til å vekte mellom dyp grønn og full deep green.
                # Anti-alias-kanter har lavere alpha → forblir mykere.
                new.append((deep_r, deep_g, deep_b, a))
            else:
                new.append((r, g, b, a))
        img.putdata(new)
        return img
    except Exception:
        return img


def _trim_transparent(img: "Any") -> "Any":
    """Klipp vekk transparente kanter så ikonet fyller hele billed-rammen.

    Hindrer at små ikoner blir enda mindre når PNG-en har stor luftmargin.
    """
    try:
        bbox = img.getbbox()
        if bbox and bbox != (0, 0, img.width, img.height):
            return img.crop(bbox)
    except Exception:
        pass
    return img


def _pad_to_square(img: "Any") -> "Any":
    """Pad et bilde til kvadrat med transparent fyll, så aspekt-ratio
    bevares ved senere resize til kvadratisk størrelse.
    """
    try:
        from PIL import Image  # type: ignore[import-untyped]
        w, h = img.size
        if w == h:
            return img
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        offset_x = (side - w) // 2
        offset_y = (side - h) // 2
        canvas.paste(img, (offset_x, offset_y))
        return canvas
    except Exception:
        return img


def _whitepx_to_alpha(img: "Any") -> "Any":
    """Erstatt nær-hvite piksler med transparent (alpha=0).

    Brukes på export.png som har hvit firkant-bakgrunn — vi vil at den
    skal være gjennomsiktig så ikonet flyter med app-tema.
    """
    try:
        data = img.getdata()
        new = []
        for r, g, b, a in data:
            if r > 240 and g > 240 and b > 240:
                new.append((r, g, b, 0))
            else:
                new.append((r, g, b, a))
        img.putdata(new)
        return img
    except Exception:
        return img


# ---------------------------------------------------------------------------
# PageHeader-komponenten
# ---------------------------------------------------------------------------

class PageHeader(ttk.Frame):
    """Standard topptittel for hovedfaner med konsistent knapp-plassering.

    Layout:
        ┌─────────────────────────────────────────────────────────┐
        │  Tittel                  [center-sone]      ↻  ⬇       │
        │  Sub-tittel                                             │
        └─────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        subtitle: str = "",
        subtitle_var: Optional[tk.StringVar] = None,
    ) -> None:
        super().__init__(parent)

        # Tre soner: venstre (tittel), midt (custom widgets), høyre (knapper)
        self.columnconfigure(1, weight=1)

        self.left = ttk.Frame(self)
        self.left.grid(row=0, column=0, sticky="w")

        self.center = ttk.Frame(self)
        self.center.grid(row=0, column=1, sticky="ew", padx=(20, 8))

        self.right = ttk.Frame(self)
        self.right.grid(row=0, column=2, sticky="e")

        # Tittel + sub-tittel
        ttk.Label(
            self.left,
            text=title,
            font=("Segoe UI", 14, "bold"),
            foreground="#1a4c7a",
        ).pack(anchor="w")

        # Sub-tittel kan være statisk tekst eller bundet til en StringVar
        # (f.eks. "Klient — År" som oppdateres ved klient-bytte).
        if subtitle_var is not None:
            self._subtitle_lbl = ttk.Label(
                self.left, textvariable=subtitle_var,
                foreground="#666",
            )
        else:
            self._subtitle_lbl = ttk.Label(
                self.left, text=subtitle,
                foreground="#666",
            )
        self._subtitle_lbl.pack(anchor="w")

        # Tilstand for handlings-knapper
        self._refresh_btn: Optional[ttk.Button] = None
        self._export_btn: Optional[Any] = None  # Button eller Menubutton
        self._exports: list[tuple[str, Callable[[], None]]] = []
        self._refresh_command: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Refresh-knapp
    # ------------------------------------------------------------------

    def set_refresh(
        self,
        command: Callable[[], None],
        *,
        key: str | None = "<F5>",
    ) -> None:
        """Sett refresh-handler og legg til ↻-knappen til høyre.

        Hvis `key` er angitt (default ``F5``), bindes den til toplevel-
        vinduet slik at trykket trigger refresh uansett fokus i appen.
        """
        self._refresh_command = command
        if self._refresh_btn is None:
            self._refresh_btn = self._make_icon_button(
                self.right,
                icon_name="refresh",
                fallback_text="↻",
                command=self._on_refresh_clicked,
                tooltip="Oppdater",
            )
            self._refresh_btn.pack(side="left", padx=(4, 0))

        if key:
            try:
                top = self.winfo_toplevel()
                top.bind(key, lambda _e: self._on_refresh_clicked(), add="+")
            except Exception:
                pass

    def _on_refresh_clicked(self) -> None:
        if self._refresh_command is None:
            return
        try:
            self._refresh_command()
        except Exception:
            log.exception("PageHeader refresh-handler feilet")

    # ------------------------------------------------------------------
    # Eksport-knapp / -meny
    # ------------------------------------------------------------------

    def add_export(self, label: str, *, command: Callable[[], None]) -> None:
        """Legg til en eksport-handling.

        Første kall: lager en ⬇-knapp som kjører handlingen direkte.
        Andre kall+: konverterer til en Menubutton med dropdown.
        Tredje+ kall: legger til ny rad i menyen.
        """
        self._exports.append((label, command))

        if len(self._exports) == 1:
            # Første eksport — enkel knapp
            self._export_btn = self._make_icon_button(
                self.right,
                icon_name="export",
                fallback_text="⬇",
                command=lambda: self._run_export(0),
                tooltip=f"Eksporter ({label})",
            )
            self._export_btn.pack(side="left", padx=(4, 0))
        elif len(self._exports) == 2:
            # Andre eksport — bytt ut knappen med en menubutton
            self._convert_to_menu()
        else:
            # Tredje+ — bare oppdater menyen
            self._rebuild_export_menu()

    def _run_export(self, index: int) -> None:
        if 0 <= index < len(self._exports):
            _label, cmd = self._exports[index]
            try:
                cmd()
            except Exception:
                log.exception("PageHeader eksport-handler feilet (%s)", _label)

    def _convert_to_menu(self) -> None:
        """Bytt enkel eksport-knapp ut med en Menubutton + dropdown."""
        if self._export_btn is not None:
            try:
                self._export_btn.destroy()
            except Exception:
                pass

        _ensure_styles()
        icon = _load_icon("export", master=self.right)
        mb = ttk.Menubutton(
            self.right,
            text="" if icon else "⬇",
            image=icon if icon else "",
            compound="left" if icon else "none",
            style="PageHeaderIcon.TMenubutton",
        )
        # Holdt referanse for å unngå GC av PhotoImage
        if icon is not None:
            mb._icon_ref = icon  # type: ignore[attr-defined]

        menu = tk.Menu(mb, tearoff=0)
        mb["menu"] = menu
        self._rebuild_export_menu(menubutton=mb, menu=menu)
        self._export_btn = mb
        mb.pack(side="left", padx=(4, 0))
        _attach_tooltip(mb, "Eksporter…")

    def _rebuild_export_menu(
        self,
        *,
        menubutton: Optional[ttk.Menubutton] = None,
        menu: Optional[tk.Menu] = None,
    ) -> None:
        if menubutton is None:
            menubutton = self._export_btn
        if menubutton is None or not isinstance(menubutton, ttk.Menubutton):
            return
        if menu is None:
            menu = menubutton["menu"]
            if isinstance(menu, str):
                menu = menubutton.nametowidget(menu)
        if menu is None:
            return
        try:
            menu.delete(0, "end")
        except Exception:
            return
        for i, (label, _cmd) in enumerate(self._exports):
            menu.add_command(label=label, command=lambda i=i: self._run_export(i))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_icon_button(
        parent: tk.Misc,
        *,
        icon_name: str,
        fallback_text: str,
        command: Callable[[], None],
        tooltip: str = "",
    ) -> ttk.Button:
        _ensure_styles()
        icon = _load_icon(icon_name, master=parent)
        if icon is not None:
            btn = ttk.Button(
                parent, image=icon, command=command,
                takefocus=0, style="PageHeaderIcon.TButton",
            )
            btn._icon_ref = icon  # type: ignore[attr-defined]
        else:
            # Fallback: Unicode-tegn hvis bildet ikke kunne lastes
            btn = ttk.Button(
                parent, text=fallback_text, command=command, width=3,
                style="PageHeaderIcon.TButton",
            )
        if tooltip:
            _attach_tooltip(btn, tooltip)
        return btn


# ---------------------------------------------------------------------------
# Lett tooltip-implementasjon — viser tekst ved hover
# ---------------------------------------------------------------------------

def _attach_tooltip(widget: tk.Widget, text: str) -> None:
    """Vis en liten tooltip ved hover. Kompakt og selvinnesluttet."""
    state: dict[str, Any] = {"top": None, "after_id": None}

    def _show() -> None:
        if state.get("top") is not None:
            return
        try:
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            top = tk.Toplevel(widget)
            top.wm_overrideredirect(True)
            top.wm_geometry(f"+{x}+{y}")
            tk.Label(
                top, text=text,
                background="#333", foreground="#fff",
                font=("Segoe UI", 9), padx=8, pady=3,
                borderwidth=0,
            ).pack()
            state["top"] = top
        except Exception:
            pass

    def _hide() -> None:
        top = state.get("top")
        if top is not None:
            try:
                top.destroy()
            except Exception:
                pass
            state["top"] = None
        if state.get("after_id") is not None:
            try:
                widget.after_cancel(state["after_id"])
            except Exception:
                pass
            state["after_id"] = None

    def _on_enter(_event: Any) -> None:
        state["after_id"] = widget.after(500, _show)

    def _on_leave(_event: Any) -> None:
        _hide()

    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")
    widget.bind("<ButtonPress>", _on_leave, add="+")
