from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bus
from ..backend import export as dataset_export
import session
from ..backend.pane_build import BuildRequest, BuildResult, build_dataset, is_saft_path
from ..backend.pane_io import (
    auto_detect_header_and_headers,
    is_csv_path,
    is_excel_path,
    list_excel_sheets,
    read_csv_header,
    read_csv_rows,
    read_excel_header,
    read_excel_rows,
)
from ..backend.pane_xls import list_xls_sheets, read_xls_header, read_xls_sample
from .pane_ui import build_ui
from ml_map_utils import canonical_fields, load_ml_map, suggest_mapping, update_ml_map
from models import Columns
from src.shared.ui.loading import LoadingOverlay
from views_preview import show_preview

logger = logging.getLogger(__name__)

# Re-eksporter (tester / eksisterende kode forventer disse navnene herfra)
__all__ = ["DatasetPane", "MAIN_FILETYPES", "is_saft_path"]

MAIN_FILETYPES = [
    # NB: Første filter blir default i Windows-dialogen.
    # Eksisterende tester forventer at "Alle filer" er default.
    ("Alle filer", "*.*"),
    ("Excel/CSV/SAF-T", "*.xlsx;*.xls;*.xlsm;*.csv;*.txt;*.zip;*.xml"),
    ("Excel", "*.xlsx;*.xls;*.xlsm"),
    ("CSV", "*.csv;*.txt"),
    ("SAF-T (zip/xml)", "*.zip;*.xml"),
]

_REQUIRED_HB = ("Konto", "Bilag", "Beløp")
_REQUIRED_SB = ("Konto",)
_REQUIRED = _REQUIRED_HB  # default, overridden by _source_mode


class DatasetPane(ttk.Frame):
    """Dataset-pane med sheet/header/mapping + valgfri klient/versjonsseksjon."""
    def __init__(
        self,
        master: tk.Misc,
        title: str = "Dataset",
        *,
        on_ready: Optional[Callable[[pd.DataFrame], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_dataset_ready: Optional[Callable[[pd.DataFrame], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)

        self._title = title
        self._on_ready = on_ready or on_dataset_ready
        self._on_error = on_error

        self._ml_map = load_ml_map()
        self._headers: list[str] = []
        self._last_build: Optional[Tuple[pd.DataFrame, Columns]] = None
        self._source_mode: str = "hb"  # "hb" or "sb"

        self.path_var = tk.StringVar(value="")
        self.sheet_var = tk.StringVar(value="")
        self.header_row_var = tk.StringVar(value="1")

        self.loading = LoadingOverlay(self)

        # Container for klient/versjon-seksjon (egen container → unngår pack/grid-konflikt)
        self._store_container = ttk.Frame(self)
        self._store_container.pack(fill="x", padx=8, pady=(8, 0))

        # Bygg resten av UI
        self.sheet_combo, self.status_lbl, self.combo_vars, self.combo_widgets = build_ui(
            self, title=self._title, canon_fields=canonical_fields()
        )

        # Valgfri klient/versjonsseksjon
        self._store_section = self._try_mount_store_section()

        # Eksportknappen ligger i PageDataset (for å unngå duplikate knapper).

        self._set_status("Klar.")
        self._sync_source_mode(saft_mode=False)
        self._update_build_readiness()

        try:
            self.path_var.trace_add("write", lambda *_args: self._update_build_readiness())
        except Exception:
            pass

    # ---- legacy/kompat API ----
    @property
    def frm(self) -> ttk.Frame:
        return self
    def get_last_build(self) -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
        if self._last_build is None:
            return None, None
        return self._last_build
    def build_dataset(self) -> Tuple[pd.DataFrame, Columns]:
        req = self._gather_build_request()
        res = build_dataset(req)
        self._apply_build_result(res, update_ml=True, show_message=False)
        return res.df, res.cols

    def _sync_source_mode(self, *, saft_mode: bool) -> None:
        widgets = [
            getattr(self, "_sheet_label", None),
            self.sheet_combo,
            getattr(self, "_header_label", None),
            getattr(self, "_header_entry", None),
            getattr(self, "_header_button", None),
        ]

        for widget in widgets:
            if widget is None:
                continue
            try:
                if saft_mode:
                    widget.grid_remove()
                else:
                    widget.grid()
            except Exception:
                pass

        hint = getattr(self, "_structure_hint_label", None)
        if hint is not None:
            try:
                hint.configure(
                    text=(
                        getattr(self, "_structure_hint_saft_text", "")
                        if saft_mode
                        else getattr(self, "_structure_hint_default_text", "")
                    )
                )
            except Exception:
                pass

        # I SAF-T-modus: skjul avanserte felt (de er uansett auto-mappet og låst)
        adv_container = getattr(self, "_advanced_container", None)
        if adv_container is not None:
            try:
                if saft_mode:
                    adv_container.grid_remove()
                else:
                    adv_container.grid()
            except Exception:
                pass

    def _set_readiness(self, text: str, *, level: str) -> None:
        label = getattr(self, "_readiness_lbl", None)
        if label is None:
            return

        style_map = {
            "info": "Status.TLabel",
            "ready": "Ready.TLabel",
            "warning": "Warning.TLabel",
        }
        label.configure(text=text, style=style_map.get(level, "Status.TLabel"))

    def _update_build_readiness(self) -> None:
        # In SB mode, readiness comes from session.tb_df, not from mapping combos
        if self._source_mode == "sb":
            self._set_readiness("Saldobalanse lastet — TB-only modus.", level="ready")
            self._set_kolonnekart_collapsed(True)
            return

        path = self.path_var.get().strip()
        if not path:
            self._set_readiness("Velg fil eller versjon for å starte.", level="warning")
            self._set_kolonnekart_collapsed(False)
            return

        if is_saft_path(path):
            self._set_readiness("Klar til å bygge SAF-T-datasett.", level="ready")
            self._set_kolonnekart_collapsed(True)
            return

        if not self._headers:
            self._set_readiness("Kontroller ark og header-rad før du bygger datasettet.", level="warning")
            self._set_kolonnekart_collapsed(False)
            return

        required = _REQUIRED_HB
        missing = [field for field in required if not self.combo_vars[field].get().strip()]
        if missing:
            self._set_readiness("Mangler påkrevde felt: " + ", ".join(missing), level="warning")
            self._set_kolonnekart_collapsed(False)
            return

        self._set_readiness("Klar til å bygge datasett.", level="ready")
        self._set_kolonnekart_collapsed(True)

    def _set_kolonnekart_collapsed(self, collapsed: bool, *, user: bool = False) -> None:
        """Vis/skjul Kolonnekart-seksjonen.

        Når collapsed=True: skjul mapf og vis "Endre kolonnekart"-knapp.
        Når collapsed=False: vis mapf og skjul knappen.
        user=True når brukeren eksplisitt har trykket "Endre kolonnekart" —
        overstyrer auto-kollaps frem til neste varsel om ufullstendig mapping.
        """
        mapf = getattr(self, "_mapf", None)
        btn = getattr(self, "_btn_edit_map", None)
        if mapf is None or btn is None:
            return
        if user and not collapsed:
            self._user_expanded_kolonnekart = True
        elif not collapsed:
            self._user_expanded_kolonnekart = False
        if collapsed and getattr(self, "_user_expanded_kolonnekart", False):
            return
        try:
            if collapsed:
                mapf.pack_forget()
                btn.grid()
            else:
                if not mapf.winfo_ismapped():
                    actions = getattr(self, "_actions_frame", None)
                    if actions is not None:
                        mapf.pack(fill="x", padx=8, pady=(0, 6), before=actions)
                    else:
                        mapf.pack(fill="x", padx=8, pady=(0, 6))
                btn.grid_remove()
        except Exception:
            pass

    # ---- callbacks fra UI-builder ----
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Velg fil (Excel/CSV/SAF-T)", filetypes=MAIN_FILETYPES)
        if not path:
            return
        # Brukeren skal velge grunnlagsfil (Excel/CSV/SAF-T). SQLite brukes kun som
        # intern cache for ferdig bygget datasett.
        if str(path).lower().endswith(".sqlite"):
            messagebox.showwarning(
                "Datasett",
                "Du valgte en SQLite-cache (.sqlite). Velg grunnlagsfilen (Excel/CSV/SAF-T) i stedet.",
            )
            return
        # Signaler at vi har valgt en ny fil som ikke er lagret versjon ennå:
        # tøm Kildeversjon-dropdown så Bygg-flyten ikke gjenbruker gammel versjon/cache.
        if self._store_section is not None:
            try:
                self._store_section.hb_var.set("")
            except Exception:
                pass
        self._set_path(path, refresh_headers=True, refresh_sheet=True)
    def _preview(self) -> None:
        p = self._get_path_or_warn()
        if p is None:
            return

        if is_saft_path(p):
            messagebox.showinfo("Forhåndsvisning", "SAF-T forhåndsvises ikke her (velg fil og bygg datasett).")
            return

        if p.suffix.lower() == ".sqlite":
            messagebox.showwarning(
                "Forhåndsvisning",
                "Valgt fil er en SQLite-cache (.sqlite). Forhåndsvisning er kun for grunnlagsfiler (Excel/CSV/SAF-T).",
            )
            return

        sheet = self._sheet_name_or_none()
        try:
            if p.suffix.lower() == ".xls":
                df_raw = read_xls_sample(p, nrows=200)
            elif p.suffix.lower() in {".xlsx", ".xlsm"}:
                rows = read_excel_rows(
                    p,
                    sheet_name=sheet,
                    start_row=1,
                    max_rows=200,
                    max_cols=60,
                )
                df_raw = pd.DataFrame(rows)
            else:
                rows = read_csv_rows(
                    p,
                    start_row=1,
                    max_rows=200,
                    max_cols=60,
                )
                df_raw = pd.DataFrame(rows)
        except Exception:
            logger.exception("Preview failed")
            messagebox.showerror("Forhåndsvisning", "Kunne ikke lese data for forhåndsvisning.")
            return

        def _on_choose_header(idx_1based: int) -> None:
            self.header_row_var.set(str(idx_1based))
            self._load_headers()
            self._guess_mapping(force=True)

        show_preview(self.winfo_toplevel(), df_raw=df_raw, on_choose_header=_on_choose_header)
    def _on_sheet_selected(self) -> None:
        self._load_headers()
        self._guess_mapping(force=False)
    def _autodetect_header(self) -> None:
        self._load_headers(auto_detect=True)
        self._guess_mapping(force=True)
    def _load_headers(self, auto_detect: bool = False) -> None:
        p = self._get_path_or_warn()
        if p is None:
            return

        if is_saft_path(p):
            self._sync_source_mode(saft_mode=True)
            headers = canonical_fields()
            self._headers = headers
            self._apply_headers_to_mapping_widgets(headers, saft_mode=True)
            self._guess_mapping(force=True)
            self._set_status("SAF-T valgt. Ark og header-rad brukes ikke her.")
            return

        self._sync_source_mode(saft_mode=False)
        self._refresh_sheet_choices(p)

        header_row = self._parse_header_row()
        sheet = self._sheet_name_or_none()

        try:
            if auto_detect and p.suffix.lower() != ".xls":
                header_row, headers = auto_detect_header_and_headers(p, sheet_name=sheet)
                self.header_row_var.set(str(header_row))
            else:
                if is_excel_path(p):
                    headers = read_excel_header(p, sheet_name=sheet, header_row=header_row)
                elif p.suffix.lower() == ".xls":
                    headers = read_xls_header(p, header_row=header_row, sheet_name=sheet)
                elif is_csv_path(p):
                    headers = read_csv_header(p, header_row=header_row)
                elif p.suffix.lower() == ".sqlite":
                    raise ValueError(
                        "Valgt fil er en SQLite-cache (.sqlite). Velg grunnlagsfil (Excel/CSV/SAF-T) for å hente header og mapping."
                    )
                else:
                    raise ValueError(f"Ukjent filtype: {p.suffix}")
        except Exception as e:
            logger.exception("Header read failed")
            messagebox.showerror("Header", f"Kunne ikke lese header:\n{e}")
            return

        self._headers = headers
        self._apply_headers_to_mapping_widgets(headers, saft_mode=False)

        found = sum(1 for v in self.combo_vars.values() if v.get().strip())
        self._set_status(f"Lest {len(headers)} kolonner. Fant {found}/{len(self.combo_vars)} felt (ML/alias).")
        self._update_build_readiness()
    def _guess_mapping(self, force: bool = True) -> None:
        p = self.path_var.get().strip()
        if not p:
            return

        if is_saft_path(p):
            for field, var in self.combo_vars.items():
                if force or not var.get().strip():
                    var.set(field)
            self._update_build_readiness()
            return

        if not self._headers:
            self._update_build_readiness()
            return

        # Prøv lagret klient-mapping først
        stored = self._load_stored_client_mapping()
        if stored:
            applied = 0
            for canon, src in stored.items():
                if canon not in self.combo_vars:
                    continue
                if (not force) and self.combo_vars[canon].get().strip():
                    continue
                if src in self._headers:
                    self.combo_vars[canon].set(src)
                    applied += 1
            if applied > 0:
                self._update_build_readiness()
                return

        mapping = suggest_mapping(self._headers, ml=self._ml_map)
        for canon, src in mapping.items():
            if canon not in self.combo_vars:
                continue
            if (not force) and self.combo_vars[canon].get().strip():
                continue
            if src in self._headers:
                self.combo_vars[canon].set(src)
        self._update_build_readiness()
    def _build_dataset_clicked(self) -> None:
        try:
            req = self._gather_build_request()
        except Exception as e:
            messagebox.showerror("Datasett", str(e))
            return

        # Stoppeklokke fra klikk → ferdig — inkluderer bakgrunnsbygging,
        # ikke bare GUI-vente.
        import time as _t_ds
        try:
            from src.monitoring.perf import record_event as _rec_ds
        except Exception:
            _rec_ds = None  # type: ignore[assignment]
        _t0_build = _t_ds.perf_counter()

        def work() -> BuildResult:
            return build_dataset(req)

        def done(res: BuildResult) -> None:
            self._apply_build_result(res, update_ml=True, show_message=False)
            if _rec_ds is not None:
                try:
                    _rec_ds(
                        "dataset.build_total",
                        (_t_ds.perf_counter() - _t0_build) * 1000.0,
                        meta={"cache_hit": bool(getattr(res, "loaded_from_cache", False))},
                    )
                except Exception:
                    pass

        def err(ex: BaseException, tb: str = "") -> None:
            logger.exception("Build dataset failed")
            messagebox.showerror("Datasett", f"Kunne ikke bygge datasett:\n{ex}")
            if self._on_error:
                try:
                    self._on_error(ex)
                except Exception:
                    logger.exception("on_error callback failed")

        self.loading.run_async(
            "Laster datasett, vennligst vent…",
            work,
            on_done=done,
            on_error=err,
        )

    # ---- intern ----
    def set_sb_mode(self, active: bool = True) -> None:
        """Switch the DatasetPane to SB (saldobalanse) or HB (hovedbok) mode.

        In SB mode the mapping combos for Bilag/Beloep are hidden and
        the readiness label shows "TB-only modus".
        """
        self._source_mode = "sb" if active else "hb"

        # Hide/show mapping combos for HB-only fields
        hb_only_fields = {"Bilag", "Beløp", "Dato", "Tekst", "Kundenr", "Kundenavn",
                          "Leverandørnr", "Leverandørnavn", "MVA-kode", "MVA-beløp",
                          "MVA-prosent", "Valuta", "Valutabeløp"}
        for field_name, widget in getattr(self, "combo_widgets", {}).items():
            if widget is None:
                continue
            try:
                label = getattr(widget, "_label", None)
                if active and field_name in hb_only_fields:
                    widget.grid_remove()
                    if label is not None:
                        label.grid_remove()
                else:
                    widget.grid()
                    if label is not None:
                        label.grid()
            except Exception:
                pass

        self._update_build_readiness()

    def _try_mount_store_section(self):
        try:
            from .pane_store import ClientStoreSection
        except Exception:
            return None

        def _on_path_selected(s: str) -> None:
            # If we were in SB mode and user selects a new file, switch back to HB
            if self._source_mode == "sb":
                self.set_sb_mode(False)
            self._set_path(s, refresh_headers=True, refresh_sheet=True)

        def _on_tb_selected(s: str) -> None:
            self.set_sb_mode(True)

        def _get_current_path() -> str:
            return self.path_var.get()

        try:
            sec = ClientStoreSection.create(self._store_container, on_path_selected=_on_path_selected, get_current_path=_get_current_path)
            sec._on_tb_selected_cb = _on_tb_selected
            return sec
        except Exception:
            logger.exception("Kunne ikke montere ClientStoreSection")
            return None

    def _set_path(self, path: str, *, refresh_headers: bool, refresh_sheet: bool) -> None:
        path = (path or "").strip()
        self._last_build = None

        # Guard: never allow internal SQLite cache files to be used as the
        # *source* dataset file.
        if path.lower().endswith((".sqlite", ".db")):
            try:
                messagebox.showerror(
                    "Dataset",
                    "SQLite-cache (.sqlite/.db) kan ikke velges som grunnlagsfil.\n"
                    "Velg original Excel/CSV/SAF-T fil under 'Dataset'.",
                )
            except Exception:
                pass
            path = ""

        if not path:
            # Clear UI when switching client/year with no active version.
            self.path_var.set("")
            self._sync_source_mode(saft_mode=False)

            # Disable sheet selector
            try:
                self.sheet_combo.config(values=[], state="disabled")
            except Exception:
                pass
            self.sheet_var.set("")

            # Clear headers + dropdowns
            self._headers = []
            try:
                self._apply_headers_to_mapping_widgets([], saft_mode=False)
            except Exception:
                pass
            for v in self.combo_vars.values():
                try:
                    v.set("")
                except Exception:
                    pass

            self._set_status("Velg fil eller versjon for å komme i gang.", level="info")
            self._update_build_readiness()
            return

        self.path_var.set(path)
        self._sync_source_mode(saft_mode=is_saft_path(path))
        if refresh_sheet:
            self._refresh_sheet_choices(Path(path))
        if refresh_headers:
            self._load_headers(auto_detect=False)
            self._guess_mapping(force=True)
        else:
            self._update_build_readiness()

    def _load_stored_client_mapping(self) -> Dict[str, str]:
        """Hent lagret kolonne-mapping for aktiv klient (hvis finnes)."""
        try:
            if self._store_section is None:
                return {}
            client = (self._store_section.client_var.get() or "").strip()
            if not client:
                return {}
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
            return regnskap_client_overrides.load_column_mapping(client)
        except Exception:
            return {}

    def _invalidate_sb_for_current_year(self) -> None:
        """Slett aktiv SB-versjon for gjeldende klient/år.

        Brukes når en ny HB er lastet opp, slik at SB regenereres fra
        den nye kildefilen i stedet for å vise utdaterte tall.
        """
        if self._store_section is None:
            return
        try:
            client = (self._store_section.client_var.get() or "").strip()
            year = (self._store_section.year_var.get() or "").strip()
        except Exception:
            return
        if not client or not year:
            return
        try:
            import src.shared.client_store.store as client_store
            existing = client_store.get_active_version(client, year=year, dtype="sb")
            if existing is None:
                return
            client_store.delete_version(client, year=year, dtype="sb", version_id=existing.id)
            logger.info("Invaliderte SB for %s/%s etter ny HB-versjon", client, year)
        except Exception:
            logger.debug("Invalidate SB feilet", exc_info=True)

    def _auto_create_sb_from_saft(
        self,
        *,
        client: str,
        year: str,
        saft_path: Path,
    ) -> bool:
        """Opprett SB-versjon automatisk fra SAF-T-kildefilen.

        Returnerer ``True`` hvis en ny SB-versjon faktisk ble opprettet.
        All tung IO kjøres i bakgrunnstråd; kalleren må derfor samle inn
        klient/år/path før jobben starter i GUI-tråden.
        """
        try:
            import src.shared.client_store.store as client_store
            from src.shared.saft.trial_balance import make_trial_balance_xlsx_from_saft

            if not client or not year:
                return False

            # Sjekk om SB allerede finnes og har data
            existing_sb = client_store.get_active_version(client, year=year, dtype="sb")
            if existing_sb is not None:
                # Sjekk om eksisterende SB er tom (0 rader) — kan skje pga. gammel parser-bug
                try:
                    _sb_df = pd.read_excel(existing_sb.path)
                    if not _sb_df.empty:
                        return False  # Har data, OK
                    logger.info("Eksisterende SB er tom — sletter og oppretter på nytt")
                    client_store.delete_version(
                        client, year=year, dtype="sb", version_id=existing_sb.id
                    )
                except Exception:
                    return False  # Kan ikke lese — la den være

            if not saft_path.exists():
                return False

            import re
            import tempfile
            safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", saft_path.stem)
            tmp_dir = Path(tempfile.mkdtemp(prefix="utvalg_sb_"))
            tmp_xlsx = tmp_dir / f"saldobalanse_fra_{safe_stem}.xlsx"

            make_trial_balance_xlsx_from_saft(saft_path, tmp_xlsx)

            client_store.create_version(
                client,
                year=year,
                dtype="sb",
                src_path=tmp_xlsx,
                make_active=True,
            )
            logger.info("Auto-opprettet SB fra SAF-T for %s/%s", client, year)
            return True
        except Exception:
            logger.debug("Auto SB fra SAF-T feilet", exc_info=True)
            return False

    def _schedule_auto_create_sb_from_saft(self) -> None:
        """Start auto-oppretting av SB fra SAF-T i bakgrunnstråd."""
        try:
            store = self._store_section
            if store is None:
                return
            client = (store.client_var.get() or "").strip()
            year = (store.year_var.get() or "").strip()
            saft_path = Path(self.path_var.get().strip())
        except Exception:
            logger.debug("Kunne ikke samle inn SAF-T auto-SB input", exc_info=True)
            return

        if not client or not year or not saft_path.exists():
            return

        def work() -> bool:
            return self._auto_create_sb_from_saft(client=client, year=year, saft_path=saft_path)

        def done(created: bool) -> None:
            if not created:
                return
            try:
                if self._store_section is not None:
                    self._store_section.refresh()
            except Exception:
                logger.exception("Kunne ikke oppdatere store UI etter auto-opprettet SB")

            # Load the newly-created SB into session so Analyse gets fresh tb_df
            # and fjorårs-sammenligning er basert på nye tall.
            try:
                import src.shared.client_store.store as client_store
                from trial_balance_reader import read_trial_balance
                import session as _session
                import bus

                v = client_store.get_active_version(client, year=year, dtype="sb")
                if v is not None and Path(v.path).exists():
                    tb_df = read_trial_balance(Path(v.path))
                    if tb_df is not None and not tb_df.empty:
                        _session.set_tb(tb_df)
                        _session.client = client
                        _session.year = year
                        # Reset Analyse's fjor-SB-cache så neste refresh laster på nytt
                        try:
                            app = getattr(_session, "APP", None)
                            page_analyse = getattr(app, "page_analyse", None)
                            if page_analyse is not None:
                                setattr(page_analyse, "_rl_sb_prev_df", None)
                        except Exception:
                            logger.debug("Kunne ikke nullstille _rl_sb_prev_df", exc_info=True)
                        bus.emit("TB_LOADED", tb_df)
            except Exception:
                logger.exception("Kunne ikke laste ny SB inn i session etter auto-opprett")

            try:
                self._set_status("Datasett klart. Saldobalanse fra SAF-T er opprettet i bakgrunnen.", level="ready")
            except Exception:
                pass

        def err(ex: BaseException, tb: str = "") -> None:
            logger.exception("Auto-oppretting av SB fra SAF-T feilet")

        try:
            self.loading.run_async(
                "Oppretter saldobalanse fra SAF-T…",
                work,
                on_done=done,
                on_error=err,
            )
        except Exception:
            logger.exception("Kunne ikke starte bakgrunnsjobb for SAF-T -> SB")

    def _refresh_sheet_choices(self, p: Path) -> None:
        sheets: list[str] = []

        if is_excel_path(p):
            try:
                sheets = list_excel_sheets(p)
            except Exception:
                logger.exception("Kunne ikke liste sheets")
        elif p.suffix.lower() == ".xls":
            sheets = list_xls_sheets(p)

        if sheets:
            self.sheet_combo.config(values=sheets, state="readonly")
        else:
            # Ikke excel / ingen ark → deaktiver arkvalg.
            self.sheet_combo.config(values=[], state="disabled")
            self.sheet_var.set("")
            return

        cur = self.sheet_var.get().strip()
        if cur and cur in sheets:
            return
        self.sheet_var.set(sheets[0] if sheets else "")
    def _apply_headers_to_mapping_widgets(self, headers: list[str], *, saft_mode: bool) -> None:
        # SAF-T: mapping er forhåndsdefinert og brukes ikke som "fri" mapping i UI.
        # Vi viser likevel feltene for transparens, men låser comboboxene.
        for canon, cb in self.combo_widgets.items():
            cb.config(values=headers if saft_mode else ["", *headers])
            cb.config(state="disabled" if saft_mode else "readonly")
            v = self.combo_vars[canon].get().strip()
            if v and (v not in headers) and not saft_mode:
                self.combo_vars[canon].set("")
    def _get_path_or_warn(self) -> Optional[Path]:
        s = self.path_var.get().strip()
        if not s:
            messagebox.showwarning("Fil", "Velg gyldig fil først.")
            return None
        p = Path(s)
        if not p.exists():
            messagebox.showwarning("Fil", "Velg gyldig fil først.")
            return None
        return p
    def _parse_header_row(self) -> int:
        s = self.header_row_var.get().strip()
        try:
            n = int(s)
        except Exception:
            n = 1
        return max(1, n)
    def _sheet_name_or_none(self) -> Optional[str]:
        s = self.sheet_var.get().strip()
        return s or None
    def _gather_build_request(self) -> BuildRequest:
        p = self._get_path_or_warn()
        if p is None:
            raise ValueError("Velg gyldig fil først.")

        mapping: Dict[str, str] = {}
        if not is_saft_path(p):
            mapping = {k: v.get().strip() for k, v in self.combo_vars.items() if v.get().strip()}
            required = _REQUIRED_SB if self._source_mode == "sb" else _REQUIRED_HB
            missing = [r for r in required if not mapping.get(r)]
            if missing:
                raise ValueError("Mapping mangler påkrevde felt: " + ", ".join(missing))

        store_client = None
        store_year = None
        store_version_id = None
        if self._store_section is not None:
            try:
                store_client = (self._store_section.client_var.get() or "").strip() or None
                store_year = (self._store_section.year_var.get() or "").strip() or None
                store_version_id = self._store_section.get_current_version_id()
            except Exception:
                store_client = None
                store_year = None
                store_version_id = None

        return BuildRequest(
            path=p,
            mapping=mapping,
            sheet_name=self._sheet_name_or_none(),
            header_row=self._parse_header_row(),
            store_client=store_client,
            store_year=store_year,
            store_version_id=store_version_id,
        )
    def _apply_build_result(self, res: BuildResult, *, update_ml: bool, show_message: bool) -> None:
        # Per-fase timing for å finne hvor tid forsvinner mellom build_dataset
        # og GUI-oppdatert. _on_ready og bus.emit kan trigge tunge listenere.
        import time as _t_apply
        try:
            from src.monitoring.perf import record_event as _rec_apply
        except Exception:
            _rec_apply = None  # type: ignore[assignment]
        _ta = _t_apply.perf_counter()

        def _apply_phase(label: str) -> None:
            nonlocal _ta
            t1 = _t_apply.perf_counter()
            if _rec_apply is not None:
                try:
                    _rec_apply(f"dataset.apply.{label}", (t1 - _ta) * 1000.0)
                except Exception:
                    pass
            _ta = t1

        self._last_build = (res.df, res.cols)

        try:
            session.set_dataset(res.df, res.cols)
        except Exception:
            session.dataset = (res.df, res.cols)
        _apply_phase("session_set_dataset")

        try:
            bus.emit("DATASET_BUILT", res.df)
        except Exception:
            pass
        _apply_phase("bus_emit_DATASET_BUILT")

        if update_ml and not is_saft_path(self.path_var.get()):
            # NB: update_ml_map() har signatur (headers, mapping, ml=None, path=None)
            # og returnerer oppdatert ML-map. Vi holder self._ml_map i sync.
            try:
                mapping = {k: v.get().strip() for k, v in self.combo_vars.items() if v.get().strip()}
                if self._headers and mapping:
                    self._ml_map = update_ml_map(headers=self._headers, mapping=mapping, ml=self._ml_map)
            except Exception:
                logger.exception("Kunne ikke oppdatere ML-map")

            # Lagre mapping per klient for gjenbruk
            try:
                client = None
                if self._store_section is not None:
                    client = (self._store_section.client_var.get() or "").strip() or None
                if client and mapping:
                    import src.shared.regnskap.client_overrides as regnskap_client_overrides
                    regnskap_client_overrides.save_column_mapping(client, mapping)
            except Exception:
                logger.debug("Kunne ikke lagre kolonne-mapping per klient", exc_info=True)
        _apply_phase("update_ml_and_save_mapping")

        # Hvis filen ble lagret som versjon: oppdater dropdown (men ikke overskriv filfeltet).
        # Flyttet til after_idle: refresh() leser versjonsliste fra disk (~344 ms)
        # og blokkerer ellers brukeren mens hen venter på Analyse-fanen.
        # hb_var.set er rask og må gjøres synkront så _store_section.refresh()
        # plukker riktig valgt versjon.
        if self._store_section is not None and res.stored_version_id:
            try:
                self._store_section.hb_var.set(res.stored_version_id)
            except Exception:
                logger.exception("Kunne ikke sette store UI hb_var")

            def _deferred_store_refresh(section=self._store_section):
                try:
                    section.refresh()
                except Exception:
                    logger.exception("Kunne ikke oppdatere store UI etter auto-store")
            try:
                self.after_idle(_deferred_store_refresh)
            except Exception:
                _deferred_store_refresh()
        _apply_phase("store_section_refresh")

        # Auto-opprett SB fra SAF-T hvis det er en SAF-T-fil og ingen aktiv SB finnes.
        # Hele blokken er flyttet til after_idle: _invalidate_sb_for_current_year
        # leser disk (~344 ms) og _schedule_auto_create_sb_from_saft sin
        # planlegging burde uansett ikke blokkere brukeren.
        if self._store_section is not None and is_saft_path(self.path_var.get()):
            stored_vid = res.stored_version_id
            stored_dup = res.stored_was_duplicate

            def _deferred_saft_actions(vid=stored_vid, dup=stored_dup):
                if vid and not dup:
                    try:
                        self._invalidate_sb_for_current_year()
                    except Exception:
                        logger.debug("Kunne ikke invalidere SB etter ny HB-versjon", exc_info=True)
                try:
                    self._schedule_auto_create_sb_from_saft()
                except Exception:
                    logger.exception("Kunne ikke planlegge SAF-T auto-create")
            try:
                self.after_idle(_deferred_saft_actions)
            except Exception:
                _deferred_saft_actions()
        _apply_phase("saft_auto_create_check")

        try:
            r, c = res.df.shape
            if getattr(res, "loaded_from_cache", False):
                self._set_status(
                    f"Datasett lastet fra cache (SQL): rader={r:,} kolonner={c}".replace(",", " "),
                    level="ready",
                )
            else:
                self._set_status(f"Datasett bygd: rader={r:,} kolonner={c}".replace(",", " "), level="ready")
        except Exception:
            self._set_status("Datasett klart.", level="ready")
        _apply_phase("set_status")

        if show_message:
            messagebox.showinfo("Datasett", "Datasett er bygget og klart til analyse.")

        if self._on_ready:
            try:
                self._on_ready(res.df)
            except Exception:
                logger.exception("on_ready callback failed")
        _apply_phase("on_ready_callback")
    def _set_status(self, text: str, *, level: str = "info") -> None:
        if self.status_lbl is None:
            return
        style_map = {
            "info": "Status.TLabel",
            "ready": "Ready.TLabel",
            "warning": "Warning.TLabel",
        }
        self.status_lbl.config(text=text, style=style_map.get(level, "Status.TLabel"))
        try:
            self.status_lbl.update_idletasks()
        except Exception:
            pass
    def _export_hovedbok(self) -> None:
        df, _cols = self.get_last_build()
        if df is None:
            messagebox.showwarning("Eksport", "Bygg datasett først.")
            return
        try:
            dataset_export.export_hovedbok_to_excel(df)
        except Exception as e:
            logger.exception("Export failed")
            messagebox.showerror("Eksport", f"Kunne ikke eksportere:\n{e}")
