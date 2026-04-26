# ui_main.py
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from types import SimpleNamespace
from typing import List, Optional

import numpy as np
import pandas as pd

# Local imports
import session
import theme


class _HashableNamespace(SimpleNamespace):
    __hash__ = object.__hash__

_ADMIN_PASSWORD = "123"
_ADMIN_PASSWORD_TITLE = "Admin"

# Pages / views
from page_dataset import DatasetPage
from page_analyse import AnalysePage
from src.pages.saldobalanse.frontend.page import SaldobalansePage
from page_admin import AdminPage
from src.pages.a07 import A07Page
from page_utvalg_strata import UtvalgStrataPage

# UtvalgPage brukes tidligere som "Resultat"-fane, men den er fjernet.
# Importen beholdes som no-op-trygg hvis annen kode senere referer til den.
try:
    from page_utvalg import UtvalgPage  # noqa: F401
except Exception:
    UtvalgPage = None  # type: ignore
from src.pages.logg import LoggPage
from src.pages.consolidation.frontend.page import ConsolidationPage
from src.pages.ar.frontend.page import ARPage
from src.pages.regnskap.frontend.page import RegnskapPage
from src.pages.materiality.frontend.page import MaterialityPage
from page_mva import MvaPage
from src.pages.skatt import SkattPage
from page_reskontro import ReskontroPage

# Fagchat-fanen er midlertidig deaktivert — utviklingen er parkert.
# Sett _FAGCHAT_ENABLED = True (eller miljøvariabel UTVALG_ENABLE_FAGCHAT=1)
# for å bygge og vise fanen igjen. Importen er beholdt så vi ikke mister
# referansen til modulen.
import os as _os_fagchat
_FAGCHAT_ENABLED = _os_fagchat.getenv("UTVALG_ENABLE_FAGCHAT", "").strip().lower() in {"1", "true", "yes", "on"}

if _FAGCHAT_ENABLED:
    try:
        from src.pages.fagchat import FagchatPage
    except Exception:
        FagchatPage = None  # type: ignore
else:
    FagchatPage = None  # type: ignore

try:
    from src.pages.documents import DocumentsPage
except Exception:
    DocumentsPage = None  # type: ignore

try:
    from src.audit_actions.statistikk import StatistikkPage
except Exception:
    StatistikkPage = None  # type: ignore

try:
    from src.pages.oversikt import OversiktPage
except Exception:
    OversiktPage = None  # type: ignore

try:
    from src.pages.driftsmidler import DriftsmidlerPage
except Exception:
    DriftsmidlerPage = None  # type: ignore

try:
    from src.pages.revisjonshandlinger import RevisjonshandlingerPage
except Exception:
    RevisjonshandlingerPage = None  # type: ignore

try:
    from page_scoping import ScopingPage
except Exception:
    ScopingPage = None  # type: ignore

log = logging.getLogger(__name__)


def _normalize_bilag_key(series: pd.Series) -> pd.Series:
    """Normaliserer bilags-id til en stabil nøkkel (string).

    Mål:
      - "3.0" i sample skal matche 3 i transaksjoner
      - Håndterer blandede typer (str/int/float)
      - Ikke-kvantifiserbare bilag beholdes som trimmet tekst (f.eks. "A12")

    Returnerer:
      pandas Series (dtype 'string') med normalisert nøkkel.
    """
    s_str = series.astype("string").str.strip()

    # Prøv numerisk normalisering (for å samle "3", "3.0", 3, 3.0 -> "3")
    num = pd.to_numeric(s_str, errors="coerce")
    # Robust heltallsdeteksjon (toleranse mot float-feil)
    is_int = num.notna() & np.isclose(num % 1, 0)

    # Konverter kun heltallsverdier til Int64 (bevarer NA) -> string
    num_int = num.where(is_int).astype("Int64")
    num_str = num_int.astype("string")

    # Hvis vi har et heltall: bruk det som nøkkel, ellers behold original tekst
    key = s_str.where(~is_int, num_str)
    return key


def expand_bilag_sample_to_transactions(df_sample_bilag: pd.DataFrame, df_transactions: pd.DataFrame) -> pd.DataFrame:
    """Utvid et bilag-sample (1 rad per bilag) til transaksjoner.

    - Filtrerer `df_transactions` til alle rader som matcher bilag i `df_sample_bilag`
    - Normaliserer bilags-id slik at f.eks. "3.0" matcher 3
    - Slår på metadata fra sample (prefikset med ``Utvalg_``)

    Merk:
      - Hvis sample er tomt: returneres et tomt utsnitt av df_transactions (samme kolonner)
      - Hvis bilag-kolonne mangler: returneres tomt utsnitt av df_transactions
    """
    if not isinstance(df_transactions, pd.DataFrame):
        return pd.DataFrame()

    # Hvis transaksjoner er tomt: returner tomt utsnitt med samme kolonner
    if df_transactions.empty:
        return df_transactions.iloc[0:0].copy()

    # Hvis sample er None/tomt: returner tomt utsnitt med samme kolonner (viktig for tester/GUI)
    if df_sample_bilag is None or not isinstance(df_sample_bilag, pd.DataFrame) or df_sample_bilag.empty:
        return df_transactions.iloc[0:0].copy()

    if "Bilag" not in df_sample_bilag.columns or "Bilag" not in df_transactions.columns:
        return df_transactions.iloc[0:0].copy()

    # Normaliser bilag-key på begge sider
    sample_key = _normalize_bilag_key(df_sample_bilag["Bilag"])
    tx_key = _normalize_bilag_key(df_transactions["Bilag"])

    sample_keys = sample_key.dropna().unique().tolist()
    if not sample_keys:
        return df_transactions.iloc[0:0].copy()

    # Filtrer transaksjoner
    mask = tx_key.isin(sample_keys)
    tx_out = df_transactions.loc[mask].copy()
    if tx_out.empty:
        return tx_out

    # Slå på metadata fra sample
    meta_cols = [c for c in df_sample_bilag.columns if c != "Bilag"]
    if meta_cols:
        meta = df_sample_bilag[["Bilag", *meta_cols]].copy()
        meta["__bilag_key"] = sample_key
        meta = meta.dropna(subset=["__bilag_key"]).drop_duplicates(subset=["__bilag_key"], keep="first")

        rename_map: dict[str, str] = {}
        for c in meta_cols:
            # Ikke dobbel-prefiks hvis kolonnen allerede er prefikset
            if c.startswith("Utvalg_"):
                rename_map[c] = c
            elif c in ("SumBeløp", "SumBelop"):
                rename_map[c] = "Utvalg_SumBilag"
            else:
                rename_map[c] = f"Utvalg_{c}"

        meta = meta.rename(columns=rename_map)

        # Merk: vi merger på en intern nøkkel for robust matching
        tx_out["__bilag_key"] = tx_key.loc[mask].astype("string")
        meta_keep_cols = ["__bilag_key", *[rename_map[c] for c in meta_cols]]
        meta = meta[[c for c in meta_keep_cols if c in meta.columns]]

        tx_out = tx_out.merge(meta, on="__bilag_key", how="left", sort=False)
        tx_out = tx_out.drop(columns=["__bilag_key"], errors="ignore")

    return tx_out


class App(tk.Tk):
    """Hovedapp (Tk).

    Denne klassen forsøker å være *test/CI-vennlig*:
    Hvis Tk ikke kan initialiseres (typisk i headless Linux), faller den tilbake
    til et minimalt objekt med de attributtene testene trenger.
    """

    def __init__(self) -> None:
        self._tk_ok: bool = True
        self._tk_init_error: Optional[Exception] = None
        # Side-widget → refresh-callable. Populeres av _on_data_ready
        # for sider som ikke er Analyse — de refreshes først når brukeren
        # aktiverer fanen (lazy refresh, jf. _on_notebook_tab_changed).
        self._post_load_dirty_refreshers: dict = {}
        self._admin_unlocked: bool = False
        self._last_allowed_tab_widget: object | None = None

        # Ytelsesovervåking — se src/monitoring/README.md.
        # EventStore flusher i bakgrunnstråd, så dette tar ~ingen tid.
        try:
            from src.monitoring.perf import init_monitoring
            init_monitoring()
        except Exception:
            pass

        # Stoppeklokker for app-init-faser. Sendes som startup.app.<fase>
        # til Utvalg Monitor.
        import time as _t_init
        try:
            from src.monitoring.perf import record_event as _rec_init
        except Exception:
            _rec_init = None  # type: ignore[assignment]

        def _phase_init(label: str, t0: float) -> float:
            t1 = _t_init.perf_counter()
            if _rec_init is not None:
                try:
                    _rec_init(f"startup.app.{label}", (t1 - t0) * 1000.0)
                except Exception:
                    pass
            return t1

        _ti = _t_init.perf_counter()
        try:
            super().__init__()
        except Exception as e:  # TclError / display-problemer
            self._tk_ok = False
            self._tk_init_error = e
            self._init_headless()
            return
        _ti = _phase_init("tk_init", _ti)

        # --- Normal GUI-init ---
        self.title("Utvalg – revisjonsverktøy")
        self.minsize(1100, 780)
        # Sentrer hovedvinduet på skjermen — gir samme posisjon som splash
        # slik at fade-overgangen føles som ett sammenhengende vindu.
        self._center_window_on_screen(1280, 900)

        # Splash-vindu først — vises mens resten av app-init kjører.
        # Hovedvinduet skjules midlertidig så brukeren ser kun splash.
        self.withdraw()
        _splash_started_at = self._show_splash()
        _ti = _phase_init("splash", _ti)

        try:
            theme.apply_theme(self)
        except Exception:
            pass
        _ti = _phase_init("theme", _ti)

        # Global footer må pakkes før notebook slik at den reserverer plass
        # i bunnen før notebooken fyller resten.
        self.nb = ttk.Notebook(self)
        self._build_global_footer()
        self.nb.pack(fill="both", expand=True)
        _ti = _phase_init("notebook+footer", _ti)

        # App-nivå LoadingOverlay som dekker hele vinduet. Brukes til å
        # holde "Bygger Analyse..." synlig fra dataset er ferdig lastet og
        # til Analyse-fanen faktisk er klar (jf. _on_data_ready).
        try:
            from ui_loading import LoadingOverlay
            self._app_loading_overlay = LoadingOverlay(self)
        except Exception:
            self._app_loading_overlay = None

        # Pages — alltid målt og sendt til Utvalg Monitor som
        # startup.page.<navn>-events. Brukes til å diagnostisere treg
        # app-oppstart uten miljøvariabler.
        import os as _os
        import time as _time
        try:
            from src.monitoring.perf import record_event as _record_event_startup
        except Exception:
            _record_event_startup = None  # type: ignore[assignment]
        _profile_pages = _os.environ.get("UTVALG_PROFILE_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}
        _page_times: dict[str, float] = {}

        def _build(label: str, fn):
            t0 = _time.perf_counter()
            result = fn()
            duration_ms = (_time.perf_counter() - t0) * 1000.0
            if _profile_pages:
                _page_times[label] = duration_ms
            if _record_event_startup is not None:
                try:
                    _record_event_startup(f"startup.page.{label}", duration_ms)
                except Exception:
                    pass
            return result

        self.page_dataset = _build("dataset", lambda: DatasetPage(self.nb))
        self.page_analyse = _build("analyse", lambda: AnalysePage(self.nb))
        self.page_saldobalanse = _build("saldobalanse", lambda: SaldobalansePage(self.nb))
        self.page_admin = _build("admin", lambda: AdminPage(self.nb))
        self.page_a07 = _build("a07", lambda: A07Page(self.nb))
        self.page_ar = _build("ar", lambda: ARPage(self.nb))
        self.page_utvalg = _build("utvalg_strata", lambda: UtvalgStrataPage(self.nb, on_commit_sample=self._on_utvalg_commit_sample))
        self.page_logg = _build("logg", lambda: LoggPage(self.nb))
        self.page_consolidation = _build("consolidation", lambda: ConsolidationPage(self.nb))
        self.page_regnskap = _build("regnskap", lambda: RegnskapPage(self.nb))
        self.page_materiality = _build("materiality", lambda: MaterialityPage(self.nb))
        self.page_mva = _build("mva", lambda: MvaPage(self.nb))
        self.page_skatt = _build("skatt", lambda: SkattPage(self.nb))
        self.page_reskontro = _build("reskontro", lambda: ReskontroPage(self.nb))
        self.page_fagchat = _build("fagchat", lambda: FagchatPage(self.nb)) if FagchatPage is not None else None
        self.page_documents = _build("documents", lambda: DocumentsPage(self.nb)) if DocumentsPage is not None else None
        # Statistikk er nå en on-demand popup, ikke fast fane. Instansen lages
        # først ved første høyreklikk → "Vis statistikk for ..." via
        # _open_statistikk_popup(). Attributtet beholdes som None så eksterne
        # consumers (f.eks. session.APP.page_statistikk) ikke krasjer.
        self.page_statistikk = None
        self.page_driftsmidler = _build("driftsmidler", lambda: DriftsmidlerPage(self.nb)) if DriftsmidlerPage is not None else None
        self.page_revisjonshandlinger = _build("revisjonshandlinger", lambda: RevisjonshandlingerPage(self.nb)) if RevisjonshandlingerPage is not None else None
        self.page_oversikt = _build("oversikt", lambda: OversiktPage(self.nb, nb=self.nb, dataset_page=self.page_dataset)) if OversiktPage is not None else None

        if _profile_pages and _page_times:
            import sys as _sys
            ranked = sorted(_page_times.items(), key=lambda kv: -kv[1])
            total = sum(_page_times.values())
            parts = [f"[STARTUP PROFILE] total={total:.0f}ms"]
            for label, ms in ranked:
                parts.append(f"{label}={ms:.0f}ms")
            print(" | ".join(parts), file=_sys.stderr, flush=True)
        _ti = _phase_init("all_pages", _ti)

        if self.page_oversikt is not None:
            self.nb.add(self.page_oversikt, text="Oversikt")
        self.nb.add(self.page_dataset, text="Dataset")
        self.nb.add(self.page_analyse, text="Analyse")
        self.nb.add(self.page_saldobalanse, text="Saldobalanse")
        self.nb.add(self.page_reskontro, text="Reskontro")
        self.nb.add(self.page_materiality, text="Vesentlighet")
        if ScopingPage is not None:
            self.page_scoping = ScopingPage(self.nb)
            self.nb.add(self.page_scoping, text="Scoping")
        else:
            self.page_scoping = None
        if self.page_revisjonshandlinger is not None:
            self.nb.add(self.page_revisjonshandlinger, text="Handlinger")
        self.nb.add(self.page_mva, text="MVA")
        self.nb.add(self.page_a07, text="A07")
        if self.page_driftsmidler is not None:
            self.nb.add(self.page_driftsmidler, text="Driftsmidler")
        self.nb.add(self.page_ar, text="AR")
        self.nb.add(self.page_consolidation, text="Konsolidering")
        self.nb.add(self.page_utvalg, text="Utvalg")
        if self.page_fagchat is not None:
            self.nb.add(self.page_fagchat, text="Fagchat")
        if self.page_documents is not None:
            self.nb.add(self.page_documents, text="Dokumenter")
        # Regnskap + Skatt + Admin helt til høyre (avslutning + skattemelding + systeminnstillinger).
        self.nb.add(self.page_regnskap, text="Regnskap")
        self.nb.add(self.page_skatt, text="Skatt")
        self.nb.add(self.page_admin, text="Admin")
        # Statistikk lives in a Toplevel-popup — ikke i tab-strippen.
        try:
            self.nb.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed, add="+")
        except Exception:
            pass

        # Diskrete fargeaksenter per fanegruppe (tynne vertikale striper).
        try:
            self._tab_accents = theme.apply_tab_group_accents(self.nb, {
                "nav": [self.page_oversikt, self.page_dataset],
                "analyse": [self.page_analyse, self.page_saldobalanse, self.page_reskontro],
                "planning": [
                    self.page_materiality,
                    getattr(self, "page_scoping", None),
                    self.page_revisjonshandlinger,
                ],
                "kontroll": [
                    self.page_mva,
                    self.page_a07,
                    self.page_driftsmidler,
                ],
            })
        except Exception:
            self._tab_accents = {}

        # Koble RegnskapPage og MvaPage til AnalysePage som datakilde
        if hasattr(self.page_regnskap, "set_analyse_page"):
            self.page_regnskap.set_analyse_page(self.page_analyse)
        if hasattr(self.page_saldobalanse, "set_analyse_page"):
            self.page_saldobalanse.set_analyse_page(self.page_analyse)
        if hasattr(self.page_admin, "set_analyse_page"):
            self.page_admin.set_analyse_page(self.page_analyse)
        if hasattr(self.page_mva, "set_analyse_page"):
            self.page_mva.set_analyse_page(self.page_analyse)
        if hasattr(self.page_skatt, "set_analyse_page"):
            self.page_skatt.set_analyse_page(self.page_analyse)
        if self.page_statistikk is not None and hasattr(self.page_statistikk, "set_analyse_page"):
            self.page_statistikk.set_analyse_page(self.page_analyse)
        if self.page_driftsmidler is not None and hasattr(self.page_driftsmidler, "set_analyse_page"):
            self.page_driftsmidler.set_analyse_page(self.page_analyse)
        if self.page_driftsmidler is not None and hasattr(self.page_regnskap, "set_driftsmidler_page"):
            self.page_regnskap.set_driftsmidler_page(self.page_driftsmidler)
        if self.page_revisjonshandlinger is not None and hasattr(self.page_revisjonshandlinger, "set_analyse_page"):
            self.page_revisjonshandlinger.set_analyse_page(self.page_analyse)

        # Gi AnalysePage callback for "Til utvalg"
        if hasattr(self.page_analyse, "set_utvalg_callback"):
            self.page_analyse.set_utvalg_callback(self._on_analyse_send_to_utvalg)

        # La session peke på relevante objekter (brukes av andre moduler)
        try:
            session.APP = self
            session.NOTEBOOK = self.nb
            session.UTVALG_STRATA_PAGE = self.page_utvalg
        except Exception:
            pass

        # Forsøk å koble DatasetPage -> on ready hook slik at Analyse oppdateres etter import
        self._maybe_install_dataset_ready_hook()

        # Start alltid paa Oversikt ved oppstart
        self._restore_last_tab()

        # Lukk splash etter at hovedvinduet er klart. Minimum visningstid
        # 2 sekunder så banneret rekker å bli sett — hvis app-init var
        # raskere, ventes resten av tiden via after().
        self._close_splash_when_ready(_splash_started_at)

    # ------------------------------------------------------------------
    # Splash screen — vises ved oppstart mens app-init kjører
    # ------------------------------------------------------------------

    _SPLASH_MIN_VISIBLE_MS = 2000

    def _center_window_on_screen(self, width: int, height: int) -> None:
        """Plasser dette Tk-vinduet sentrert på primær-skjermen."""
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            try:
                self.geometry(f"{width}x{height}")
            except Exception:
                pass

    def _show_splash(self) -> float:
        """Vis splash-vindu med AarVaaken-banner i app-tema-farger.

        Hovedvinduet skal være withdraw'et før kallet. Splash vises
        sentrert på skjermen med banner + diskret undertittel.
        Bakgrunn matcher app-temaet (BG_SAND_SOFT) så overgangen til
        hovedvinduet blir sammenhengende.
        """
        import time
        t0 = time.perf_counter()
        self._splash_window = None

        # Theme-farger fra vaak_tokens (faller tilbake hvis import feiler)
        try:
            import vaak_tokens as _vt
            bg_color = "#" + _vt.BG_SAND_SOFT
            border_color = "#" + _vt.SAGE_DARK
            text_color = "#" + _vt.FOREST
            text_secondary = "#" + _vt.TEXT_PRIMARY
            font_family = _vt.FONT_FAMILY_BODY
        except Exception:
            bg_color = "#F4EDDC"
            border_color = "#8CBF7C"
            text_color = "#325B1E"
            text_secondary = "#3A1900"
            font_family = "Segoe UI"

        try:
            from PIL import Image, ImageChops, ImageTk  # type: ignore[import-untyped]
            from pathlib import Path
            import sys

            # Finn AarVaaken.png — samme søkerekkefølge som LoadingOverlay
            candidates = []
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "doc" / "pictures" / "AarVaaken.png")
            candidates.append(Path(__file__).resolve().parent / "doc" / "pictures" / "AarVaaken.png")

            pic_path = next((p for p in candidates if p.exists()), None)
            if pic_path is None:
                return t0

            img = Image.open(str(pic_path))

            # Auto-crop near-white kanter slik at motivet flukter med
            # splash-bakgrunnen. PNG-en har hvite marger som ikke er rent
            # 255,255,255 (typisk 254,254,254), så vi bruker en grayscale-
            # terskel (250) i stedet for eksakt sammenligning.
            try:
                gray = img.convert("L")
                # bw: 255 der innhold er, 0 der near-white bakgrunn er
                bw = gray.point(lambda p: 255 if p < 250 else 0)
                bbox = bw.getbbox()
                if bbox:
                    img = img.crop(bbox)
            except Exception:
                pass

            # Skaler bildet til 50% av skjermbredden, behold aspekt-ratio
            screen_w = self.winfo_screenwidth()
            target_w = max(500, int(screen_w * 0.5))
            w, h = img.size
            target_h = max(1, int(round(target_w * h / w)))
            img = img.resize((target_w, target_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            splash = tk.Toplevel(self)
            splash.overrideredirect(True)
            try:
                splash.attributes("-topmost", True)
            except Exception:
                pass
            splash.configure(bg=border_color)  # ramme-farge

            # Inner frame — gir 2px border via padding på ytre
            inner = tk.Frame(splash, bg=bg_color)
            inner.pack(padx=2, pady=2, fill="both", expand=True)

            # Banner
            banner_lbl = tk.Label(inner, image=photo, bg=bg_color, borderwidth=0)
            banner_lbl.image = photo  # behold referanse
            banner_lbl.pack(padx=24, pady=(28, 14))

            # Undertittel — Forest-grønn, samme font som appen
            subtitle = tk.Label(
                inner,
                text="Revisjonsverktøy",
                bg=bg_color,
                fg=text_color,
                font=(font_family, 13, "bold"),
            )
            subtitle.pack(pady=(0, 4))

            # Liten "laster..."-tekst i muted brun
            loading_lbl = tk.Label(
                inner,
                text="laster…",
                bg=bg_color,
                fg=text_secondary,
                font=(font_family, 9, "italic"),
            )
            loading_lbl.pack(pady=(0, 28))

            # Sentrer på skjermen
            splash.update_idletasks()
            sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
            ww, wh = splash.winfo_reqwidth(), splash.winfo_reqheight()
            x = (sw - ww) // 2
            y = (sh - wh) // 2
            splash.geometry(f"{ww}x{wh}+{x}+{y}")

            splash.update()
            self._splash_window = splash
        except Exception:
            self._splash_window = None
        return t0

    def _close_splash_when_ready(self, started_at: float) -> None:
        """Lukk splash etter min-visningstid, deretter fade-ut og vis app.

        Bruker -alpha-attributtet (Windows) for myk overgang. Hvis
        attributtet ikke støttes faller vi tilbake til umiddelbar destroy.
        """
        import time
        splash = getattr(self, "_splash_window", None)

        def _show_main() -> None:
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass

        def _fade_step(alpha: float) -> None:
            if splash is None:
                _show_main()
                return
            try:
                splash.attributes("-alpha", alpha)
            except Exception:
                # Plattform støtter ikke alpha — bare destroy
                try:
                    splash.destroy()
                except Exception:
                    pass
                _show_main()
                return
            if alpha <= 0.0:
                try:
                    splash.destroy()
                except Exception:
                    pass
                _show_main()
                return
            try:
                self.after(30, lambda a=alpha - 0.15: _fade_step(a))
            except Exception:
                try:
                    splash.destroy()
                except Exception:
                    pass
                _show_main()

        def _begin_fade() -> None:
            # Vis hovedvinduet før fade så det dukker opp under splash
            _show_main()
            _fade_step(1.0)

        try:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            wait_ms = max(0, self._SPLASH_MIN_VISIBLE_MS - elapsed_ms)
            self.after(wait_ms, _begin_fade)
        except Exception:
            try:
                if splash is not None:
                    splash.destroy()
            except Exception:
                pass
            _show_main()

    def _build_global_footer(self) -> None:
        """Bygg en diskret footer-linje nederst i hovedvinduet.

        Venstre felt viser selection-summary for aktiv Treeview.
        Høyre felt viser vanlige statusmeldinger.
        """
        try:
            # Separator over footeren gir en subtil toppkant uten SUNKEN-look.
            sep = ttk.Separator(self, orient="horizontal")
            sep.pack(side="bottom", fill="x")

            footer = ttk.Frame(self, padding=(8, 2))
            footer.pack(side="bottom", fill="x")

            sel_lbl = ttk.Label(footer, text="", anchor="w")
            sel_lbl.pack(side="left", fill="x", expand=True)

            status_lbl = ttk.Label(footer, text="", anchor="e", foreground="#6B5540")
            status_lbl.pack(side="right")

            self._footer_frame = footer
            self._footer_selection_label = sel_lbl
            self._footer_status_label = status_lbl
        except Exception:
            self._footer_frame = None
            self._footer_selection_label = None
            self._footer_status_label = None

    def set_selection_summary(self, text: str) -> None:
        """Skriv tekst i venstre footer-felt (selection-summary)."""
        lbl = getattr(self, "_footer_selection_label", None)
        if lbl is None:
            return
        try:
            lbl.config(text=str(text) if text else "")
        except Exception:
            pass

    def clear_selection_summary(self) -> None:
        """Tøm venstre footer-felt."""
        self.set_selection_summary("")

    def set_status_message(self, text: str) -> None:
        """Skriv tekst i høyre footer-felt (vanlige statusmeldinger)."""
        lbl = getattr(self, "_footer_status_label", None)
        if lbl is None:
            return
        try:
            lbl.config(text=str(text) if text else "")
        except Exception:
            pass

    def set_status(self, text: str) -> None:
        """Bakoverkompatibelt alias til `set_status_message`."""
        self.set_status_message(text)

    def _init_headless(self) -> None:
        """Initialiserer en minimal app når Tk ikke kan brukes."""
        # Minimal notebook-stub
        self.nb = _HashableNamespace(  # type: ignore[assignment]
            select=lambda *_args, **_kwargs: None,
            add=lambda *_args, **_kwargs: None,
        )

        # Footer-stubs (no-op, men samme API som GUI-varianten)
        self._footer_frame = None
        self._footer_selection_label = None
        self._footer_status_label = None

        # Minimal pages/stubs som testene forventer
        self.page_analyse = _HashableNamespace(dataset=None)  # type: ignore[assignment]
        self.page_saldobalanse = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_admin = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]

        # DatasetPage må eksponere .dp, og DatasetPane må ha ._on_ready
        dp_stub = _HashableNamespace(_on_ready=None)
        self.page_dataset = _HashableNamespace(dp=dp_stub)  # type: ignore[assignment]

        # Resten brukes ikke av testene, men vi setter dem for robusthet
        self.page_a07 = _HashableNamespace(refresh_from_session=lambda *_args, **_kwargs: None)  # type: ignore[assignment]
        self.page_ar = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_utvalg = _HashableNamespace()  # type: ignore[assignment]
        self.page_logg = _HashableNamespace()  # type: ignore[assignment]
        self.page_consolidation = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_regnskap = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_materiality = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_mva = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_skatt = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_reskontro = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_driftsmidler = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]
        self.page_revisjonshandlinger = None
        self.page_oversikt = _HashableNamespace(refresh_from_session=lambda *_a, **_kw: None)  # type: ignore[assignment]

        # Installer hook slik at testene kan finne dp._on_ready og kalle callback
        self._maybe_install_dataset_ready_hook()

    # --- Tk-sikre wrappers (hindrer krasj i headless) ---
    def withdraw(self) -> None:  # type: ignore[override]
        if self._tk_ok:
            try:
                super().withdraw()
            except Exception:
                pass

    def destroy(self) -> None:  # type: ignore[override]
        if self._tk_ok:
            try:
                super().destroy()
            except Exception:
                pass

    def mainloop(self, n: int = 0) -> None:  # type: ignore[override]
        if not self._tk_ok:
            raise RuntimeError("tkinter er ikke tilgjengelig i dette miljøet (headless).") from self._tk_init_error
        super().mainloop(n)

    def _maybe_install_dataset_ready_hook(self) -> None:
        """Installer callback for når DatasetPane har bygget datasett.

        DatasetPage/DatasetPane har hatt flere varianter i repoet, derfor prøver vi
        flere attributtnavn.

        Mål:
          - dp._on_ready skal være callable etter create_app()
          - Når dataset bygges, skal Analyse-fanen oppdateres automatisk
        """
        try:
            # Ny standard i repoet: DatasetPage.dp
            dp = getattr(self.page_dataset, "dp", None)

            # Bakoverkompat: dataset_pane / pane
            if dp is None:
                dp = getattr(self.page_dataset, "dataset_pane", None)
            if dp is None:
                dp = getattr(self.page_dataset, "pane", None)

            if dp is None:
                return

            # Vanlig mønster: dp._on_ready er en callback (DatasetPane)
            if hasattr(dp, "_on_ready"):
                existing = getattr(dp, "_on_ready", None)

                if callable(existing):
                    # Unngå dobbel-wrapping av samme callback så godt vi kan
                    if existing is self._on_data_ready:
                        return

                    def _wrapped_on_ready(df: pd.DataFrame) -> None:
                        try:
                            existing(df)
                        finally:
                            self._on_data_ready(df)

                    dp._on_ready = _wrapped_on_ready  # type: ignore[attr-defined]
                    return

                # Hvis eksisterende ikke er callable (typisk None): sett direkte
                dp._on_ready = self._on_data_ready  # type: ignore[attr-defined]
                return

            # Alternativt: dp.on_data_ready
            if hasattr(dp, "on_data_ready"):
                existing = getattr(dp, "on_data_ready", None)

                if callable(existing):
                    if existing is self._on_data_ready:
                        return

                    def _wrapped_on_ready(df: pd.DataFrame) -> None:
                        try:
                            existing(df)
                        finally:
                            self._on_data_ready(df)

                    dp.on_data_ready = _wrapped_on_ready  # type: ignore[attr-defined]
                    return

                dp.on_data_ready = self._on_data_ready  # type: ignore[attr-defined]
                return

        except Exception:
            # Ikke kræsje appen om hook feiler
            return

    def _restore_last_tab(self) -> None:
        """Velg oppstartsfanen.

        Appen skal alltid aapne paa Oversikt, ikke siste aktive fane.
        Fallback er foerste tilgjengelige fane hvis Oversikt ikke finnes.
        """
        try:
            oversikt_page = getattr(self, "page_oversikt", None)
            if oversikt_page is not None:
                self.nb.select(oversikt_page)
                return
            tabs = self.nb.tabs()
            if tabs:
                self.nb.select(tabs[0])
        except Exception:
            pass

    def _fallback_tab_after_admin_denied(self) -> object | None:
        admin_page = self.__dict__.get("page_admin")
        fallback = self.__dict__.get("_last_allowed_tab_widget")
        if fallback is not None and fallback is not admin_page:
            return fallback

        for attr_name in ("page_oversikt", "page_dataset"):
            candidate = self.__dict__.get(attr_name)
            if candidate is not None and candidate is not admin_page:
                return candidate

        try:
            for tab_id in self.nb.tabs():
                try:
                    widget = self.nametowidget(tab_id)
                except Exception:
                    widget = tab_id
                if widget is not admin_page:
                    return widget
        except Exception:
            pass
        return None

    def _ensure_admin_access(self, selected_widget: object) -> bool:
        # Tilgang til Admin-fanen styres nå av landing-siden i AdminPage —
        # ikke av et passord-prompt på fanebytte. Brukeren ser en
        # ufarlig landing med "Ytelsesmonitor…" og "Oppsett…", og
        # "Oppsett…" er det som faktisk ber om passord.
        # Vi returnerer alltid True her så fane-bytte ikke blokkeres.
        return True

    def _save_current_tab(self) -> None:
        """Lagre aktiv fane i preferences."""
        try:
            import preferences
            selected_id = self.nb.select()
            tab_text = self.nb.tab(selected_id, "text")
            if tab_text:
                preferences.set("ui.last_tab", tab_text)
        except Exception:
            pass

    def _on_notebook_tab_changed(self, _event=None) -> None:
        try:
            selected_id = self.nb.select()
            selected_widget = self.nametowidget(selected_id)
        except Exception:
            return

        if not self._ensure_admin_access(selected_widget):
            return

        self._save_current_tab()
        self._last_allowed_tab_widget = selected_widget

        # Nullstill selection-summary nar man bytter fane, slik at en markering
        # pa Analyse ikke blir staende igjen nederst pa en annen side.
        try:
            self.clear_selection_summary()
        except Exception:
            pass

        self._sync_session_context_from_dataset_store()

        # Lazy refresh: hvis fanen ble markert som dirty etter datasett-last
        # uten å ha blitt åpnet ennå, kjør den nå (kun én gang).
        try:
            dirty_fn = self._post_load_dirty_refreshers.pop(selected_widget, None)
            if dirty_fn is not None:
                self.after_idle(dirty_fn)
        except Exception:
            pass

        if selected_widget is getattr(self, "page_consolidation", None):
            try:
                self.after_idle(self._refresh_consolidation_from_session)
            except Exception:
                self._refresh_consolidation_from_session()
            return

        if selected_widget is getattr(self, "page_a07", None):
            try:
                self.after_idle(self._refresh_a07_from_session)
            except Exception:
                self._refresh_a07_from_session()
            return

        if selected_widget is getattr(self, "page_saldobalanse", None):
            try:
                self.after_idle(self._refresh_saldobalanse_from_session)
            except Exception:
                self._refresh_saldobalanse_from_session()
            return

        if selected_widget is getattr(self, "page_admin", None):
            try:
                self.after_idle(self._refresh_admin_from_session)
            except Exception:
                self._refresh_admin_from_session()
            return

        if selected_widget is getattr(self, "page_ar", None):
            try:
                self.after_idle(self._refresh_ar_from_session)
            except Exception:
                self._refresh_ar_from_session()
            return

        if selected_widget is getattr(self, "page_revisjonshandlinger", None):
            try:
                self.after_idle(self._refresh_handlinger_from_session)
            except Exception:
                self._refresh_handlinger_from_session()
            return

        if selected_widget is getattr(self, "page_scoping", None):
            try:
                self.after_idle(self._refresh_scoping_from_session)
            except Exception:
                self._refresh_scoping_from_session()
            return

        if selected_widget is getattr(self, "src.pages.materiality.frontend.page", None):
            # Auto-refresh ved aktivering — Vesentlighet leser session.client/year
            # og må synkes hver gang brukeren bytter klient eller år, ikke kun
            # ved første dataset-load.
            try:
                self.after_idle(self._refresh_materiality_from_session)
            except Exception:
                self._refresh_materiality_from_session()
            return

        if selected_widget is getattr(self, "page_documents", None):
            # Auto-refresh ved aktivering — sparer brukeren for å trykke
            # "Oppdater" hver gang de bytter til fanen.
            try:
                self.after_idle(self._refresh_documents_on_tab_activate)
            except Exception:
                self._refresh_documents_on_tab_activate()

    def _dataset_store_context(self) -> tuple[str | None, str | None]:
        try:
            dp = getattr(self.page_dataset, "dp", None)
            if dp is None:
                dp = getattr(self.page_dataset, "dataset_pane", None)
            if dp is None:
                dp = getattr(self.page_dataset, "pane", None)
            sec = getattr(dp, "_store_section", None) if dp else None
            if sec is None:
                return None, None
            client = (getattr(sec, "client_var", None) and sec.client_var.get() or "").strip() or None
            year = (getattr(sec, "year_var", None) and sec.year_var.get() or "").strip() or None
            return client, year
        except Exception:
            return None, None

    def _sync_session_context_from_dataset_store(self) -> tuple[str | None, str | None]:
        client = (getattr(session, "client", None) or "").strip() or None
        year = (getattr(session, "year", None) or "").strip() or None
        store_client, store_year = self._dataset_store_context()
        if store_client:
            client = store_client
        if store_year:
            year = store_year
        try:
            session.client = client
            session.year = year
        except Exception:
            pass
        return client, year

    def _refresh_consolidation_from_session(self) -> None:
        try:
            if hasattr(self.page_consolidation, "refresh_from_session") and callable(getattr(self.page_consolidation, "refresh_from_session")):
                self.page_consolidation.refresh_from_session(session)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Consolidation refresh after tab change failed")

    def _refresh_a07_from_session(self) -> None:
        try:
            if hasattr(self.page_a07, "refresh_from_session") and callable(getattr(self.page_a07, "refresh_from_session")):
                self.page_a07.refresh_from_session(session)  # type: ignore[attr-defined]
        except Exception:
            log.exception("A07 refresh after tab change failed")

    def _refresh_saldobalanse_from_session(self) -> None:
        try:
            if hasattr(self.page_saldobalanse, "refresh_from_session") and callable(getattr(self.page_saldobalanse, "refresh_from_session")):
                self.page_saldobalanse.refresh_from_session(session)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Saldobalanse refresh after tab change failed")

    def _refresh_admin_from_session(self) -> None:
        try:
            if hasattr(self.page_admin, "refresh_from_session") and callable(getattr(self.page_admin, "refresh_from_session")):
                self.page_admin.refresh_from_session(session)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Admin refresh after tab change failed")

    def _refresh_ar_from_session(self) -> None:
        try:
            if hasattr(self.page_ar, "refresh_from_session") and callable(getattr(self.page_ar, "refresh_from_session")):
                self.page_ar.refresh_from_session(session)  # type: ignore[attr-defined]
        except Exception:
            log.exception("AR refresh after tab change failed")

    def _open_statistikk_popup(self, *, regnr: int | None = None) -> None:
        """Åpne Statistikk i en Toplevel-popup (erstatter tidligere egen fane).

        Første kall instansierer StatistikkPage inne i Toplevel-en og lagrer
        referansen på self.page_statistikk (for bakoverkompat). Senere kall
        gjenbruker vinduet hvis det fortsatt er levende.
        """
        existing = getattr(self, "_statistikk_toplevel", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    try:
                        existing.deiconify()
                        existing.lift()
                        existing.focus_set()
                    except Exception:
                        pass
                    if regnr is not None and self.page_statistikk is not None:
                        try:
                            self.page_statistikk.show_regnr(int(regnr))
                        except Exception:
                            pass
                    return
            except Exception:
                pass
            self._statistikk_toplevel = None
            self.page_statistikk = None

        if StatistikkPage is None:
            return

        try:
            top = tk.Toplevel(self)
        except Exception:
            return

        top.title("Statistikk")
        try:
            top.geometry("1200x800")
        except Exception:
            pass
        top.minsize(800, 500)

        try:
            stat_page = StatistikkPage(top)
            stat_page.pack(fill="both", expand=True)
        except Exception:
            log.exception("Kunne ikke bygge StatistikkPage i popup")
            try:
                top.destroy()
            except Exception:
                pass
            return

        # Koble til Analyse-page (samme som tidligere ved fane-init).
        try:
            if hasattr(stat_page, "set_analyse_page"):
                stat_page.set_analyse_page(self.page_analyse)
        except Exception:
            pass

        # Synk klient/år slik at data lastes umiddelbart.
        try:
            if hasattr(stat_page, "refresh_from_session"):
                stat_page.refresh_from_session(session)
        except Exception:
            pass

        def _on_close() -> None:
            self._statistikk_toplevel = None
            self.page_statistikk = None
            try:
                top.destroy()
            except Exception:
                pass

        try:
            top.protocol("WM_DELETE_WINDOW", _on_close)
        except Exception:
            pass

        self._statistikk_toplevel = top
        self.page_statistikk = stat_page

        if regnr is not None:
            try:
                stat_page.show_regnr(int(regnr))
            except Exception:
                pass

    def _refresh_materiality_from_session(self) -> None:
        """Auto-refresh Vesentlighet-fanen når brukeren aktiverer den.

        Sikrer at klient/år alltid er synket, uavhengig av om datasett ble
        lastet før eller etter at fanen ble besøkt.
        """
        try:
            page = getattr(self, "src.pages.materiality.frontend.page", None)
            if page is None:
                return
            if hasattr(page, "refresh_from_session") and callable(getattr(page, "refresh_from_session")):
                page.refresh_from_session(session)
        except Exception:
            log.exception("Materiality refresh after tab change failed")

    def _refresh_handlinger_from_session(self) -> None:
        try:
            page = getattr(self, "page_revisjonshandlinger", None)
            if page is not None and hasattr(page, "on_client_changed"):
                client = getattr(session, "client", None)
                year = getattr(session, "year", None)
                page.on_client_changed(client, year)
        except Exception:
            log.exception("Handlinger refresh after tab change failed")

    def _refresh_scoping_from_session(self) -> None:
        try:
            page = getattr(self, "page_scoping", None)
            if page is not None and hasattr(page, "on_client_changed"):
                client = getattr(session, "client", None)
                year = getattr(session, "year", None)
                page.on_client_changed(client, year)
        except Exception:
            log.exception("Scoping refresh after tab change failed")

    def _refresh_documents_on_tab_activate(self) -> None:
        """Auto-refresh Dokumenter-fanen når brukeren aktiverer den.

        Bruker DocumentsPage._refresh() (samme som "Oppdater"-knappen)
        i stedet for refresh_from_session() — sistnevnte returnerer
        tidlig hvis (klient, år) ikke er endret. Brukeren forventer at
        ny fil dukket opp uten å klikke noe.
        """
        try:
            page = getattr(self, "page_documents", None)
            if page is None:
                return
            # Sørg for at klient/år er synket først
            if hasattr(page, "refresh_from_session"):
                try:
                    page.refresh_from_session(session)
                except Exception:
                    pass
            # Tving en disk-skann uavhengig av endring
            if hasattr(page, "_refresh"):
                page._refresh()
        except Exception:
            log.exception("Documents auto-refresh on tab change failed")

    def _preload_ownership_map_async(self) -> None:
        """Forhåndslast ar_store.get_client_ownership_overview i bakgrunnstråd.

        Oppslaget tar typisk 3+ sekunder cold og brukes av Saldobalanse-fanen
        til å dekorere konto-navn med selskapsnavn. Ved å kjøre det parallelt
        med Analyse-refreshen er cachen varm før brukeren bytter til SB.

        Idempotent — hvis allerede i gang eller cache allerede fylt, er kallet
        en no-op (cache-treffet i _load_owned_company_name_map returnerer
        umiddelbart).
        """
        client = (getattr(session, "client", None) or "").strip()
        year_raw = getattr(session, "year", None)
        if not client:
            return

        try:
            year_int: int | None = int(str(year_raw).strip()) if year_raw else None
        except (TypeError, ValueError):
            year_int = None

        import threading
        import time as _time

        def _worker() -> None:
            try:
                from src.monitoring.perf import record_event as _record_event
            except Exception:
                _record_event = None  # type: ignore[assignment]

            t0 = _time.perf_counter()
            try:
                from src.pages.saldobalanse.backend.payload import _load_owned_company_name_map
                _load_owned_company_name_map(client, year_int)
            except Exception:
                # Stille feil — hvis preload feiler laster SB den syncront som før.
                return
            finally:
                if _record_event is not None:
                    try:
                        duration_ms = (_time.perf_counter() - t0) * 1000.0
                        _record_event(
                            "startup.ownership_map.preload",
                            duration_ms,
                            meta={"client": client, "year": str(year_int or "")},
                        )
                    except Exception:
                        pass

        threading.Thread(
            target=_worker, name="ownership-map-preload", daemon=True
        ).start()

    def _on_data_ready(self, df: pd.DataFrame) -> None:
        """Kalles når dataset er lastet.

        Oppdaterer session.dataset, refresher Analyse-fanen og bytter til Analyse.
        """
        if df is None or df.empty:
            return

        # Per-fase timing — _on_data_ready kalles synkront fra
        # dataset.apply.on_ready_callback og blokkerer brukeren i 1+ sek.
        # Vi måler hver del for å finne hva som dominerer tiden.
        import time as _t_dr
        try:
            from src.monitoring.perf import record_event as _rec_dr
        except Exception:
            _rec_dr = None  # type: ignore[assignment]
        _tdr = _t_dr.perf_counter()

        def _dr_phase(label: str) -> None:
            nonlocal _tdr
            t1 = _t_dr.perf_counter()
            if _rec_dr is not None:
                try:
                    _rec_dr(f"dataset.on_data_ready.{label}", (t1 - _tdr) * 1000.0)
                except Exception:
                    pass
            _tdr = t1

        try:
            session.dataset = df
            session.version_type = "hb"
        except Exception:
            pass
        _dr_phase("session_set")

        # Oppdater session.client / session.year fra DatasetPane sin store-seksjon
        try:
            self._sync_session_context_from_dataset_store()
        except Exception:
            pass
        _dr_phase("sync_session_context")

        # Bakgrunns-preload av ownership_map (3+ sekunder cold). Kjøres mens
        # Analyse-fanen bygger — når brukeren bytter til Saldobalanse er cachen
        # allerede varm.
        try:
            self._preload_ownership_map_async()
        except Exception:
            log.exception("Ownership map preload failed to start")
        _dr_phase("preload_ownership_map_thread_start")

        # Sett dataset-referanse umiddelbart (tester og andre moduler forventer dette)
        try:
            setattr(self.page_analyse, "dataset", df)
        except Exception:
            pass
        _dr_phase("set_analyse_dataset")

        # Defer tung refresh (pivot, filtre, SB) til etter at GUI har malt seg.
        # Spre oppdateringene litt utover for å redusere opplevd heng.
        def _refresh_analyse() -> None:
            try:
                if hasattr(self.page_analyse, "refresh_from_session") and callable(getattr(self.page_analyse, "refresh_from_session")):
                    self.page_analyse.refresh_from_session(session, defer_heavy=True)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Analyse refresh after dataset load failed")

        def _refresh_saldobalanse() -> None:
            try:
                if hasattr(self.page_saldobalanse, "refresh_from_session") and callable(getattr(self.page_saldobalanse, "refresh_from_session")):
                    self.page_saldobalanse.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Saldobalanse refresh after dataset load failed")

        def _refresh_regnskap() -> None:
            try:
                if hasattr(self.page_regnskap, "refresh_from_session") and callable(getattr(self.page_regnskap, "refresh_from_session")):
                    self.page_regnskap.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Regnskap refresh after dataset load failed")

        def _refresh_materiality() -> None:
            try:
                if hasattr(self.page_materiality, "refresh_from_session") and callable(getattr(self.page_materiality, "refresh_from_session")):
                    self.page_materiality.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Materiality refresh after dataset load failed")

        def _refresh_mva() -> None:
            try:
                if hasattr(self.page_mva, "refresh_from_session") and callable(getattr(self.page_mva, "refresh_from_session")):
                    self.page_mva.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("MVA refresh after dataset load failed")

        def _refresh_skatt() -> None:
            try:
                if hasattr(self.page_skatt, "refresh_from_session") and callable(getattr(self.page_skatt, "refresh_from_session")):
                    self.page_skatt.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Skatt refresh after dataset load failed")

        def _refresh_reskontro() -> None:
            try:
                if hasattr(self.page_reskontro, "refresh_from_session") and callable(getattr(self.page_reskontro, "refresh_from_session")):
                    self.page_reskontro.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Reskontro refresh after dataset load failed")

        def _refresh_documents() -> None:
            try:
                if hasattr(self, "page_documents") and self.page_documents is not None:
                    if hasattr(self.page_documents, "refresh_from_session"):
                        self.page_documents.refresh_from_session(session)
            except Exception:
                log.exception("Documents refresh after dataset load failed")

        def _refresh_statistikk() -> None:
            try:
                if hasattr(self, "page_statistikk") and self.page_statistikk is not None:
                    if hasattr(self.page_statistikk, "refresh_from_session"):
                        self.page_statistikk.refresh_from_session(session)
            except Exception:
                log.exception("Statistikk refresh after dataset load failed")

        def _refresh_driftsmidler() -> None:
            try:
                if hasattr(self, "page_driftsmidler") and self.page_driftsmidler is not None:
                    if hasattr(self.page_driftsmidler, "refresh_from_session"):
                        self.page_driftsmidler.refresh_from_session(session)
            except Exception:
                log.exception("Driftsmidler refresh after dataset load failed")

        def _refresh_oversikt() -> None:
            try:
                if hasattr(self, "page_oversikt") and self.page_oversikt is not None:
                    if hasattr(self.page_oversikt, "refresh_from_session"):
                        self.page_oversikt.refresh_from_session(session)
            except Exception:
                log.exception("Oversikt refresh after dataset load failed")

        _dr_phase("define_callbacks")

        # Vis app-nivå loading-overlay til Analyse-fanen er faktisk ferdig
        # bygget (ikke bare når dataset er lastet). Dette dekker tidsvinduet
        # mellom dataset-bygging og Analyse-refresh — som tar 2-6 sekunder
        # og ellers gir "looks done but isn't"-UX.
        overlay = getattr(self, "_app_loading_overlay", None)
        if overlay is not None:
            try:
                overlay.show("Bygger Analyse-fanen...")
            except Exception:
                overlay = None
        _dr_phase("show_overlay")

        # Registrer skjul-overlay som callback når Analyse-refresh er ferdig.
        # Knytt også overlay til page slik at hver stage kan oppdatere
        # status-tekst for visuell progresjon.
        if overlay is not None:
            try:
                page = self.page_analyse
                cbs = list(getattr(page, "_post_heavy_refresh_callbacks", None) or [])

                def _hide_and_clear(o=overlay, p=page):
                    try:
                        o.hide()
                    finally:
                        try:
                            p._loading_status_text_setter = None
                        except Exception:
                            pass

                def _bring_to_front(app=self):
                    """Løft hovedvinduet til fremst etter at loading er ferdig.

                    Windows skjuler ofte Tk-vinduer bak andre vinduer hvis
                    start-skjermen overlappet. Bruker kort topmost-toggle
                    for å tvinge z-order uten å pinne vinduet permanent.
                    """
                    try:
                        app.deiconify()
                        app.lift()
                        app.focus_force()
                        app.attributes("-topmost", True)
                        app.after(250, lambda: app.attributes("-topmost", False))
                    except Exception:
                        pass

                cbs.append(_hide_and_clear)
                cbs.append(_bring_to_front)
                page._post_heavy_refresh_callbacks = cbs
                page._loading_status_text_setter = overlay.set_text
            except Exception:
                # Hvis vi ikke får registrert callback, skjul overlay
                # umiddelbart så vi ikke etterlater den hengende.
                try:
                    overlay.hide()
                except Exception:
                    pass

        _dr_phase("setup_overlay_callbacks")

        # Eager: kun Analyse (mål-fanen brukeren bytter til umiddelbart).
        # Lazy: alle andre faner får en "dirty"-markering og refreshes
        # først når brukeren aktiverer dem. Tidligere ble alle 13 faner
        # refreshet etter hverandre over 310ms etter datasett-last —
        # mesteparten av de tunge operasjonene var bortkastet hvis
        # brukeren bare skulle se Analyse-fanen.
        try:
            self.after_idle(_refresh_analyse)
        except Exception:
            _refresh_analyse()
        _dr_phase("schedule_analyse_refresh")

        # Bygg mapping: side-widget → refresh-callable. Filtreres for
        # None (sider som ikke er konstruert i denne build-en).
        candidate_refreshers: list[tuple[object | None, callable]] = [
            (getattr(self, "page_saldobalanse", None), _refresh_saldobalanse),
            (getattr(self, "src.pages.regnskap.frontend.page", None),     _refresh_regnskap),
            (getattr(self, "src.pages.materiality.frontend.page", None),  _refresh_materiality),
            (getattr(self, "page_mva", None),          _refresh_mva),
            (getattr(self, "page_skatt", None),        _refresh_skatt),
            (getattr(self, "page_reskontro", None),    _refresh_reskontro),
            (getattr(self, "page_documents", None),    _refresh_documents),
            (getattr(self, "page_statistikk", None),   _refresh_statistikk),
            (getattr(self, "page_driftsmidler", None), _refresh_driftsmidler),
            (getattr(self, "page_oversikt", None),     _refresh_oversikt),
        ]
        self._post_load_dirty_refreshers = {
            widget: fn for widget, fn in candidate_refreshers if widget is not None
        }

        _dr_phase("build_dirty_refreshers")

        # Vis Analyse som neste steg
        try:
            if hasattr(self, "nb") and hasattr(self.nb, "select"):
                self.nb.select(self.page_analyse)
        except Exception:
            pass
        _dr_phase("nb_select_analyse")

    def _on_tb_ready(self) -> None:
        """Kalles naar en SB-versjon er valgt og session.tb_df er satt.

        Refresher Konsolidering og Analyse (som allerede haandterer TB-only).
        """
        def _refresh_analyse() -> None:
            try:
                if hasattr(self.page_analyse, "refresh_from_session") and callable(getattr(self.page_analyse, "refresh_from_session")):
                    self.page_analyse.refresh_from_session(session, defer_heavy=True)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Analyse refresh after TB load failed")

        def _refresh_consolidation() -> None:
            try:
                if hasattr(self.page_consolidation, "refresh_from_session") and callable(getattr(self.page_consolidation, "refresh_from_session")):
                    self.page_consolidation.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Consolidation refresh after TB load failed")

        def _refresh_saldobalanse() -> None:
            try:
                if hasattr(self.page_saldobalanse, "refresh_from_session") and callable(getattr(self.page_saldobalanse, "refresh_from_session")):
                    self.page_saldobalanse.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Saldobalanse refresh after TB load failed")

        def _refresh_ar() -> None:
            try:
                if hasattr(self.page_ar, "refresh_from_session") and callable(getattr(self.page_ar, "refresh_from_session")):
                    self.page_ar.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("AR refresh after TB load failed")

        def _refresh_materiality() -> None:
            try:
                if hasattr(self.page_materiality, "refresh_from_session") and callable(getattr(self.page_materiality, "refresh_from_session")):
                    self.page_materiality.refresh_from_session(session)  # type: ignore[attr-defined]
            except Exception:
                log.exception("Materiality refresh after TB load failed")

        try:
            self.after_idle(_refresh_analyse)
            self.after(20, _refresh_saldobalanse)
            self.after(35, _refresh_consolidation)
            self.after(60, _refresh_ar)
            self.after(85, _refresh_materiality)
        except Exception:
            _refresh_analyse()
            _refresh_saldobalanse()
            _refresh_consolidation()
            _refresh_ar()
            _refresh_materiality()

    def _on_analyse_send_to_utvalg(self, accounts: List[str]) -> None:
        """Callback fra Analyse-fanen ("Til utvalg")."""
        accounts = [str(a).strip() for a in (accounts or []) if str(a).strip()]
        if not accounts:
            return

        # Lagre i session selection
        try:
            if hasattr(session, "set_selection"):
                session.set_selection(accounts=accounts)
            else:
                session.SELECTION["accounts"] = accounts  # type: ignore[attr-defined]
                session.SELECTION["version"] = int(session.SELECTION.get("version", 0)) + 1  # type: ignore[attr-defined]
        except Exception:
            pass

        # Last populasjon i Utvalg
        try:
            if hasattr(self.page_utvalg, "load_population"):
                self.page_utvalg.load_population(accounts)  # type: ignore[attr-defined]
        except Exception as e:
            try:
                messagebox.showerror("Feil", f"Kunne ikke overføre kontoer til Utvalg:\n{e}")
            except Exception:
                pass
            return

        # Bytt til Utvalg-fanen
        try:
            if hasattr(self, "nb") and hasattr(self.nb, "select"):
                self.nb.select(self.page_utvalg)
        except Exception:
            pass

    def _on_utvalg_commit_sample(self, df_sample: pd.DataFrame) -> None:
        """Callback fra UtvalgStrataPage/SelectionStudio når brukeren klikker "Legg i utvalg".

        Tidligere åpnet denne en egen Resultat-fane med utvalget. Resultat-fanen
        er fjernet, så callbacken er nå en no-op — utvalget vises i Utvalg-fanens
        egen visning. Beholdes for å bevare callback-kontrakten mot UtvalgStrataPage.
        """
        return


def create_app() -> App:
    """Fabrikk for tester og app.py."""
    return App()


def install_runtime_ui_behaviors(app: "App") -> None:
    """Installer runtime-oppførsel som skal være lik uansett entrypoint.

    Samlet på ett sted slik at både `app.py` og `ui_main.__main__` gir
    identisk oppførsel (globale hotkeys, autofit, opt-in selection-summary
    som skriver til app-footeren).
    """
    try:
        import ui_hotkeys

        setter = getattr(app, "set_selection_summary", None)
        ui_hotkeys.install_global_hotkeys(
            app,
            status_setter=setter if callable(setter) else None,
            selection_summary_require_opt_in=True,
        )
        ui_hotkeys.install_autofit_all(app)
    except Exception:
        # Runtime-oppsett skal aldri stoppe oppstart
        log.exception("install_runtime_ui_behaviors failed")


if __name__ == "__main__":
    app = create_app()
    install_runtime_ui_behaviors(app)
    app.mainloop()



