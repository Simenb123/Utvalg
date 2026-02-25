from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bus
import dataset_export
import session
from dataset_pane_build import BuildRequest, BuildResult, build_dataset, is_saft_path
from dataset_pane_io import (
    auto_detect_header_and_headers,
    is_csv_path,
    is_excel_path,
    list_excel_sheets,
    read_csv_header,
    read_csv_rows,
    read_excel_header,
    read_excel_rows,
)
from dataset_pane_xls import list_xls_sheets, read_xls_header, read_xls_sample
from dataset_pane_ui import build_ui
from ml_map_utils import canonical_fields, load_ml_map, suggest_mapping, update_ml_map
from models import Columns
from ui_loading import LoadingOverlay
from views_preview import show_preview

logger = logging.getLogger(__name__)

# Re-eksporter (tester / eksisterende kode forventer disse navnene herfra)
__all__ = ["DatasetPane", "MAIN_FILETYPES", "is_saft_path"]

MAIN_FILETYPES = [
    ("Alle filer", "*.*"),
    ("Excel", "*.xlsx;*.xls;*.xlsm"),
    ("CSV", "*.csv;*.txt"),
    ("SAF-T (zip/xml)", "*.zip;*.xml"),
]

_REQUIRED = ("Konto", "Bilag", "Beløp")


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
        self._apply_build_result(res, update_ml=True, show_message=True)
        return res.df, res.cols

    # ---- callbacks fra UI-builder ----
    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Velg fil (Excel/CSV/SAF-T)", filetypes=MAIN_FILETYPES)
        if not path:
            return
        self._set_path(path, refresh_headers=True, refresh_sheet=True)
    def _preview(self) -> None:
        p = self._get_path_or_warn()
        if p is None:
            return

        if is_saft_path(p):
            messagebox.showinfo("Forhåndsvisning", "SAF-T forhåndsvises ikke her (velg fil og bygg datasett).")
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
            headers = canonical_fields()
            self._headers = headers
            self._apply_headers_to_mapping_widgets(headers, saft_mode=True)
            self._guess_mapping(force=True)
            self._set_status("SAF-T valgt (sheet/header er ikke relevant).")
            return

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
    def _guess_mapping(self, force: bool = True) -> None:
        p = self.path_var.get().strip()
        if not p:
            return

        if is_saft_path(p):
            for field, var in self.combo_vars.items():
                if force or not var.get().strip():
                    var.set(field)
            return

        if not self._headers:
            return

        mapping = suggest_mapping(self._headers, ml=self._ml_map)
        for canon, src in mapping.items():
            if canon not in self.combo_vars:
                continue
            if (not force) and self.combo_vars[canon].get().strip():
                continue
            if src in self._headers:
                self.combo_vars[canon].set(src)
    def _build_dataset_clicked(self) -> None:
        try:
            req = self._gather_build_request()
        except Exception as e:
            messagebox.showerror("Datasett", str(e))
            return

        def work() -> BuildResult:
            return build_dataset(req)

        def done(res: BuildResult) -> None:
            self._apply_build_result(res, update_ml=True, show_message=True)

        def err(ex: Exception) -> None:
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
    def _try_mount_store_section(self):
        try:
            from dataset_pane_store import ClientStoreSection
        except Exception:
            return None

        def _on_path_selected(s: str) -> None:
            self._set_path(s, refresh_headers=True, refresh_sheet=True)

        def _get_current_path() -> str:
            return self.path_var.get()

        try:
            return ClientStoreSection.create(self._store_container, on_path_selected=_on_path_selected, get_current_path=_get_current_path)
        except Exception:
            logger.exception("Kunne ikke montere ClientStoreSection")
            return None
    def _set_path(self, path: str, *, refresh_headers: bool, refresh_sheet: bool) -> None:
        self.path_var.set(path)
        if refresh_sheet:
            self._refresh_sheet_choices(Path(path))
        if refresh_headers:
            self._load_headers(auto_detect=False)
            self._guess_mapping(force=True)
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
        for canon, cb in self.combo_widgets.items():
            cb.config(values=headers)
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
            missing = [r for r in _REQUIRED if not mapping.get(r)]
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
        self._last_build = (res.df, res.cols)

        try:
            session.set_dataset(res.df, res.cols)
        except Exception:
            session.dataset = (res.df, res.cols)

        try:
            bus.emit("DATASET_BUILT", res.df)
        except Exception:
            pass

        if update_ml and not is_saft_path(self.path_var.get()):
            # NB: update_ml_map() har signatur (headers, mapping, ml=None, path=None)
            # og returnerer oppdatert ML-map. Vi holder self._ml_map i sync.
            try:
                mapping = {k: v.get().strip() for k, v in self.combo_vars.items() if v.get().strip()}
                if self._headers and mapping:
                    self._ml_map = update_ml_map(headers=self._headers, mapping=mapping, ml=self._ml_map)
            except Exception:
                logger.exception("Kunne ikke oppdatere ML-map")

        # Hvis filen ble lagret som versjon: oppdater dropdown (men ikke overskriv filfeltet).
        if self._store_section is not None and res.stored_version_id:
            try:
                self._store_section.hb_var.set(res.stored_version_id)
                self._store_section.refresh()
            except Exception:
                logger.exception("Kunne ikke oppdatere store UI etter auto-store")

        try:
            r, c = res.df.shape
            if getattr(res, "loaded_from_cache", False):
                self._set_status(f"Datasett lastet fra cache (SQL): rader={r:,} kolonner={c}".replace(",", " "))
            else:
                self._set_status(f"Datasett bygd: rader={r:,} kolonner={c}".replace(",", " "))
        except Exception:
            self._set_status("Datasett klart.")

        if show_message:
            messagebox.showinfo("Datasett", "Datasett er bygget og klart til analyse.")

        if self._on_ready:
            try:
                self._on_ready(res.df)
            except Exception:
                logger.exception("on_ready callback failed")
    def _set_status(self, text: str) -> None:
        if self.status_lbl is None:
            return
        self.status_lbl.config(text=text)
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
