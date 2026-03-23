"""Versions (HB/SB) dialog.

This dialog started as a simple list for the active *Hovedbok* file per
client/year. With the introduction of *Saldobalanse* (trial balance), the old
"Type" dropdown became easy to miss and therefore confusing.

This version uses tabs (Notebook) and a summary line so it is always clear:
- whether a saldobalanse exists
- which version is active

Additionally, when a SAF-T file is imported as hovedbok, we can also extract a
trial balance from the same SAF-T file (MasterFiles/GeneralLedgerAccount) and
create a saldobalanse version automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging
import re
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import client_store

_log = logging.getLogger(__name__)


DTYPE_LABELS: dict[str, str] = {
    "hb": "Hovedbok",
    "sb": "Saldobalanse",
    "saft": "SAF-T",
}


def _dtype_label(dtype: str) -> str:
    return DTYPE_LABELS.get(dtype, dtype)


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _version_created_ts(version) -> float:
    """Backwards-compatible timestamp accessor for version rows."""
    try:
        return float(getattr(version, "created_at", None) or getattr(version, "created_ts", None) or 0.0)
    except Exception:
        return 0.0


def _open_path(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        _log.exception("Failed to open path: %s", path)


def _get_active_version_id(client: str, year: int, dtype: str) -> str | None:
    if hasattr(client_store, "get_active_version_id"):
        try:
            return client_store.get_active_version_id(client, year=year, dtype=dtype)
        except Exception:
            return None

    # Backwards compatible: get_active_version() -> VersionInfo | None
    try:
        av = client_store.get_active_version(client, year=year, dtype=dtype)
        return av.id if av else None
    except Exception:
        return None


def _set_active_version_id(client: str, year: int, dtype: str, version_id: str) -> None:
    if hasattr(client_store, "set_active_version_id"):
        client_store.set_active_version_id(client, year=year, dtype=dtype, version_id=version_id)
        return

    # Backwards compatible: set_active_version(client, year, dtype, version)
    client_store.set_active_version(client, year=year, dtype=dtype, version_id=version_id)


@dataclass
class _DialogState:
    client: str
    year: int
    dtype: str


class _VersionsDialog:
    def __init__(
        self,
        parent: tk.Misc,
        state: _DialogState,
        current_path_getter,
        on_use_version=None,
        on_after_change=None,
        dtypes: list[str] | None = None,
    ):
        self._parent = parent
        self._state = state
        self._current_path_getter = current_path_getter
        self._on_use_version = on_use_version
        self._on_after_change = on_after_change

        self._dtypes = list(dict.fromkeys(dtypes or [state.dtype]))

        # We keep versions per dtype so we can show a summary.
        self._versions_by_dtype: dict[str, dict[str, object]] = {}

        self.top: tk.Toplevel | None = None
        self.lbl_title: ttk.Label | None = None
        self.lbl_summary: ttk.Label | None = None
        self.nb: ttk.Notebook | None = None
        self.trees: dict[str, ttk.Treeview] = {}

        # Buttons
        self.btn_from_field: ttk.Button | None = None
        self.btn_generate_sb: ttk.Button | None = None
        self.btn_open_file: ttk.Button | None = None
        self.btn_open_folder: ttk.Button | None = None
        self.btn_delete: ttk.Button | None = None
        self.btn_use: ttk.Button | None = None

        self.lbl_hint: ttk.Label | None = None
        self.lbl_selected: ttk.Label | None = None

    # ------------------------- lifecycle -------------------------
    def show_modal(self):
        self.top = tk.Toplevel(self._parent)
        self.top.title("Versjoner")
        self.top.geometry("980x520")
        self.top.transient(self._parent)
        self.top.grab_set()

        self._build_ui(self.top)

        # Center
        try:
            self.top.update_idletasks()
            x = self._parent.winfo_rootx() + (self._parent.winfo_width() // 2) - (self.top.winfo_width() // 2)
            y = self._parent.winfo_rooty() + (self._parent.winfo_height() // 2) - (self.top.winfo_height() // 2)
            self.top.geometry(f"+{x}+{y}")
        except Exception:
            pass

        # Initial tab
        if self.nb is not None and self._state.dtype in self._dtypes:
            try:
                self.nb.select(self._dtypes.index(self._state.dtype))
            except Exception:
                pass

        self._reload_all()
        self._update_buttons_and_hint()

        self.top.wait_window(self.top)

    # ------------------------- UI -------------------------
    def _build_ui(self, parent: tk.Misc) -> None:
        frm = ttk.Frame(parent, padding=10)
        frm.pack(fill="both", expand=True)

        # Header
        self.lbl_title = ttk.Label(frm, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_title.pack(anchor="w")

        self.lbl_summary = ttk.Label(frm, text="", font=("Segoe UI", 9))
        self.lbl_summary.pack(anchor="w", pady=(2, 8))

        # Action buttons
        frm_btns = ttk.Frame(frm)
        frm_btns.pack(fill="x", pady=(0, 6))

        ttk.Button(frm_btns, text="Importer fil...", command=self._on_import_file).pack(side="left")

        self.btn_from_field = ttk.Button(frm_btns, text="Ny versjon fra filfelt", command=self._on_store_from_field)
        self.btn_from_field.pack(side="left", padx=(6, 0))

        self.btn_generate_sb = ttk.Button(
            frm_btns, text="Lag saldobalanse fra SAF-T", command=self._on_generate_sb_from_selected_hb
        )
        self.btn_generate_sb.pack(side="left", padx=(6, 0))

        self.btn_open_file = ttk.Button(frm_btns, text="Åpne fil", command=self._on_open_file)
        self.btn_open_file.pack(side="left", padx=(18, 0))

        self.btn_open_folder = ttk.Button(frm_btns, text="Åpne mappe", command=self._on_open_folder)
        self.btn_open_folder.pack(side="left", padx=(6, 0))

        self.btn_delete = ttk.Button(frm_btns, text="Slett versjon", command=self._on_delete)
        self.btn_delete.pack(side="left", padx=(18, 0))

        # Notebook with one tab per dtype
        self.nb = ttk.Notebook(frm)
        self.nb.pack(fill="both", expand=True)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_changed())

        for dtype in self._dtypes:
            tab = ttk.Frame(self.nb)
            self.nb.add(tab, text=_dtype_label(dtype))
            tree = self._make_tree(tab, dtype)
            self.trees[dtype] = tree

        # Footer
        frm_footer = ttk.Frame(frm)
        frm_footer.pack(fill="x", pady=(6, 0))

        self.lbl_hint = ttk.Label(frm_footer, text="", justify="left")
        self.lbl_hint.pack(side="left", anchor="w")

        frm_footer_right = ttk.Frame(frm_footer)
        frm_footer_right.pack(side="right")

        self.btn_use = ttk.Button(frm_footer_right, text="Bruk valgt", command=self._on_use_and_close)
        self.btn_use.pack(side="left")

        ttk.Button(frm_footer_right, text="Lukk", command=self._on_close).pack(side="left", padx=(6, 0))

        self.lbl_selected = ttk.Label(frm, text="")
        self.lbl_selected.pack(anchor="w", pady=(4, 0))

    def _make_tree(self, parent: tk.Misc, dtype: str) -> ttk.Treeview:
        frm_list = ttk.Frame(parent)
        frm_list.pack(fill="both", expand=True)

        cols = ("active", "file", "created")
        tree = ttk.Treeview(frm_list, columns=cols, show="headings", selectmode="browse")
        tree.heading("active", text="Aktiv")
        tree.heading("file", text="Fil")
        tree.heading("created", text="Opprettet")

        tree.column("active", width=60, anchor="center")
        tree.column("file", width=650, anchor="w")
        tree.column("created", width=160, anchor="w")

        vsb = ttk.Scrollbar(frm_list, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.bind("<Double-1>", lambda _e: self._on_use_and_close())
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons_and_hint())

        return tree

    # ------------------------- state helpers -------------------------
    def _current_dtype(self) -> str:
        # Notebook dictates dtype
        if self.nb is None:
            return self._state.dtype
        try:
            idx = self.nb.index(self.nb.select())
            dtype = self._dtypes[idx]
            self._state.dtype = dtype
            return dtype
        except Exception:
            return self._state.dtype

    def _current_tree(self) -> ttk.Treeview | None:
        return self.trees.get(self._current_dtype())

    def _get_selected_version_id(self, dtype: str | None = None) -> str | None:
        dtype = dtype or self._current_dtype()
        tree = self.trees.get(dtype)
        if tree is None:
            return None
        sel = tree.selection()
        return sel[0] if sel else None

    def _get_version_info(self, dtype: str, version_id: str):
        # VersionInfo is an internal project type; keep it opaque.
        return client_store.get_version(self._state.client, year=self._state.year, dtype=dtype, version_id=version_id)

    # ------------------------- reload -------------------------
    def _reload_all(self, *, focus_dtype: str | None = None, select_id: str | None = None) -> None:
        for dt in self._dtypes:
            self._reload_dtype(dt, select_id=select_id if dt == (focus_dtype or self._current_dtype()) else None)
        self._update_header_summary()

    def _reload_dtype(self, dtype: str, select_id: str | None = None) -> None:
        tree = self.trees.get(dtype)
        if tree is None:
            return

        # Keep versions dict per dtype for summary/lookup
        try:
            versions = client_store.list_versions(self._state.client, year=self._state.year, dtype=dtype)
        except Exception:
            versions = []

        versions_by_id = {v.id: v for v in versions}
        self._versions_by_dtype[dtype] = versions_by_id

        active_id = _get_active_version_id(self._state.client, year=self._state.year, dtype=dtype)

        # Clear
        for item in tree.get_children():
            tree.delete(item)

        # Insert
        for v in sorted(versions, key=_version_created_ts, reverse=True):
            star = "*" if active_id and v.id == active_id else ""
            tree.insert("", "end", iid=v.id, values=(star, Path(v.path).name, _fmt_ts(_version_created_ts(v))))

        # Select
        preferred = select_id or active_id
        if preferred and preferred in versions_by_id:
            try:
                tree.selection_set(preferred)
                tree.see(preferred)
            except Exception:
                pass

    def _update_header_summary(self) -> None:
        if self.lbl_title is None or self.lbl_summary is None:
            return

        self.lbl_title.config(text=f"Klient: {self._state.client}   År: {self._state.year}")

        parts: list[str] = []
        for dt in self._dtypes:
            versions = self._versions_by_dtype.get(dt, {})
            active_id = _get_active_version_id(self._state.client, year=self._state.year, dtype=dt)
            active_name = "-"
            if active_id and active_id in versions:
                try:
                    active_name = Path(versions[active_id].path).name
                except Exception:
                    active_name = "(aktiv)"

            parts.append(f"{_dtype_label(dt)}: {len(versions)} (aktiv: {active_name})")

        self.lbl_summary.config(text=" | ".join(parts))

    # ------------------------- buttons & hint -------------------------
    def _update_buttons_and_hint(self) -> None:
        dtype = self._current_dtype()
        selected_id = self._get_selected_version_id(dtype)

        # Selected label
        if self.lbl_selected is not None:
            self.lbl_selected.config(text=f"Markert: {1 if selected_id else 0} rad")

        # Enable/disable
        if self.btn_use is not None:
            self.btn_use.config(state=("normal" if selected_id else "disabled"))

        if self.btn_open_file is not None:
            self.btn_open_file.config(state=("normal" if selected_id else "disabled"))

        if self.btn_open_folder is not None:
            self.btn_open_folder.config(state=("normal" if selected_id else "disabled"))

        if self.btn_delete is not None:
            self.btn_delete.config(state=("normal" if selected_id else "disabled"))

        if self.btn_from_field is not None:
            self.btn_from_field.config(state=("normal" if dtype == "hb" else "disabled"))

        # Generate SB only makes sense on HB tab + SAF-T selection
        if self.btn_generate_sb is not None:
            can = False
            if dtype == "hb" and selected_id:
                try:
                    v = self._get_version_info("hb", selected_id)
                    p = Path(v.path)
                    can = p.suffix.lower() in {".zip", ".xml"}
                except Exception:
                    can = False
            self.btn_generate_sb.config(state=("normal" if can else "disabled"))

        # Hint text
        if self.lbl_hint is not None:
            if dtype == "hb":
                self.lbl_hint.config(
                    text=(
                        "Tips: Velg en rad og dobbeltklikk for å bruke versjonen. "
                        "'Ny versjon fra filfelt' tar filstien fra Dataset-feltet i hovedvinduet.\n"
                        "Hvis du importerer en SAF-T fil, kan du også lage saldobalanse fra samme fil."
                    )
                )
            elif dtype == "sb":
                self.lbl_hint.config(
                    text=(
                        "Tips: Velg en rad og dobbeltklikk for å bruke saldobalansen. "
                        "Du kan importere en egen fil (Excel/CSV), eller velge en SAF-T fil for å hente saldobalanse."
                    )
                )
            else:
                self.lbl_hint.config(text="Tips: Velg en rad og dobbeltklikk for å bruke versjonen.")

    # ------------------------- events -------------------------
    def _on_tab_changed(self) -> None:
        self._current_dtype()  # updates state
        self._update_buttons_and_hint()

    def _after_change(self) -> None:
        if self._on_after_change:
            try:
                self._on_after_change()
            except Exception:
                _log.exception("on_after_change failed")

    # ------------------------- actions -------------------------
    def _on_import_file(self) -> None:
        dtype = self._current_dtype()

        # File filters
        excel = ("Excel-filer", "*.xlsx *.xls *.xlsm")
        csv = ("CSV", "*.csv")
        saft = ("SAF-T", "*.zip *.xml")
        allf = ("Alle filer", "*.*")

        if dtype == "hb":
            ftypes = [excel, csv, saft, allf]
        elif dtype == "sb":
            ftypes = [excel, csv, saft, allf]
        elif dtype == "saft":
            ftypes = [saft, allf]
        else:
            ftypes = [allf]

        src = filedialog.askopenfilename(title="Velg fil", filetypes=ftypes)
        if not src:
            return

        src_path = Path(src)

        # Special handling: importing SB from SAF-T should generate a trial balance file.
        if dtype == "sb" and src_path.suffix.lower() in {".zip", ".xml"}:
            sb_id = self._import_sb_from_saft(src_path, make_active=True)
            if sb_id:
                # Switch to SB tab and focus imported version
                self._reload_all(focus_dtype="sb", select_id=sb_id)
                if self.nb is not None and "sb" in self._dtypes:
                    try:
                        self.nb.select(self._dtypes.index("sb"))
                    except Exception:
                        pass
                self._after_change()
            return

        try:
            v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype=dtype,
                source_path=str(src_path),
                make_active=True,
            )
        except Exception:
            _log.exception("Failed to create version")
            messagebox.showerror("Versjoner", "Kunne ikke importere filen.", parent=self.top)
            return

        # If HB is SAF-T, auto-create SB from the same file.
        if dtype == "hb" and src_path.suffix.lower() in {".zip", ".xml"}:
            self._auto_create_sb_from_saft(src_path)

        # Reload and focus
        self._reload_all(focus_dtype=dtype, select_id=v.id)
        self._after_change()

        # Only HB updates the main dataset field
        if self._on_use_version and dtype == "hb":
            try:
                self._on_use_version(v.id)
            except Exception:
                _log.exception("on_use_version failed")

    def _on_store_from_field(self) -> None:
        dtype = self._current_dtype()
        if dtype != "hb":
            return

        current_path = (self._current_path_getter() or "").strip()
        if not current_path:
            messagebox.showwarning("Versjoner", "Dataset-feltet er tomt.", parent=self.top)
            return

        src_path = Path(current_path)
        if not src_path.exists():
            messagebox.showwarning("Versjoner", "Filen finnes ikke.", parent=self.top)
            return

        try:
            v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype="hb",
                source_path=str(src_path),
                make_active=True,
            )
        except Exception:
            _log.exception("Failed to create version from dataset field")
            messagebox.showerror("Versjoner", "Kunne ikke opprette ny versjon.", parent=self.top)
            return

        # If SAF-T, also create SB.
        if src_path.suffix.lower() in {".zip", ".xml"}:
            self._auto_create_sb_from_saft(src_path)

        self._reload_all(focus_dtype="hb", select_id=v.id)
        self._after_change()

        if self._on_use_version:
            try:
                self._on_use_version(v.id)
            except Exception:
                _log.exception("on_use_version failed")

    def _on_generate_sb_from_selected_hb(self) -> None:
        # Only meaningful on HB tab
        if self._current_dtype() != "hb":
            return

        hb_id = self._get_selected_version_id("hb")
        if not hb_id:
            return

        try:
            hb_v = self._get_version_info("hb", hb_id)
            hb_path = Path(hb_v.path)
        except Exception:
            _log.exception("Could not resolve selected HB version")
            messagebox.showerror("Versjoner", "Kunne ikke hente valgt hovedbokversjon.", parent=self.top)
            return

        if hb_path.suffix.lower() not in {".zip", ".xml"}:
            messagebox.showinfo(
                "Versjoner",
                "Valgt hovedbok er ikke en SAF-T fil (.zip/.xml).",
                parent=self.top,
            )
            return

        sb_id = self._import_sb_from_saft(hb_path, make_active=True)
        if sb_id:
            self._reload_all(focus_dtype="sb", select_id=sb_id)
            if self.nb is not None and "sb" in self._dtypes:
                try:
                    self.nb.select(self._dtypes.index("sb"))
                except Exception:
                    pass
            self._after_change()

    def _on_open_file(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return
        try:
            v = self._get_version_info(dtype, vid)
            _open_path(Path(v.path))
        except Exception:
            _log.exception("Failed to open version file")

    def _on_open_folder(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return
        try:
            v = self._get_version_info(dtype, vid)
            _open_path(Path(v.path).parent)
        except Exception:
            _log.exception("Failed to open folder")

    def _on_delete(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return

        ok = messagebox.askyesno(
            "Slett versjon",
            "Er du sikker på at du vil slette den valgte versjonen?",
            parent=self.top,
        )
        if not ok:
            return

        try:
            client_store.delete_version(self._state.client, year=self._state.year, dtype=dtype, version_id=vid)
        except Exception:
            _log.exception("Failed to delete version")
            messagebox.showerror("Versjoner", "Kunne ikke slette versjonen.", parent=self.top)
            return

        self._reload_all(focus_dtype=dtype)
        self._after_change()

    def _on_use_and_close(self) -> None:
        dtype = self._current_dtype()
        vid = self._get_selected_version_id(dtype)
        if not vid:
            return

        try:
            _set_active_version_id(self._state.client, year=self._state.year, dtype=dtype, version_id=vid)
        except Exception:
            _log.exception("Failed to set active version")
            messagebox.showerror("Versjoner", "Kunne ikke bruke valgt versjon.", parent=self.top)
            return

        # Only HB updates the main dataset field
        if self._on_use_version and dtype == "hb":
            try:
                self._on_use_version(vid)
            except Exception:
                _log.exception("on_use_version failed")

        self._after_change()
        self._on_close()

    def _on_close(self) -> None:
        if self.top is not None:
            self.top.destroy()

    # ------------------------- SAF-T -> SB helpers -------------------------
    def _auto_create_sb_from_saft(self, saft_path: Path) -> None:
        """Try to create SB version from SAF-T. Never raises."""
        try:
            self._import_sb_from_saft(saft_path, make_active_if_missing=True)
        except Exception:
            _log.exception("Auto SB from SAF-T failed")

    def _import_sb_from_saft(self, saft_path: Path, *, make_active: bool = False, make_active_if_missing: bool = False) -> str | None:
        """Extract trial balance from SAF-T and store as SB version.

        Returns the created SB version id or None.
        """

        try:
            from saft_trial_balance import make_trial_balance_xlsx_from_saft
        except Exception:
            _log.exception("saft_trial_balance module missing")
            messagebox.showerror("Versjoner", "Mangler modul for SAF-T saldobalanse.", parent=self.top)
            return None

        # Decide active behaviour
        if make_active_if_missing:
            active_sb = _get_active_version_id(self._state.client, year=self._state.year, dtype="sb")
            make_active = not bool(active_sb)

        # Create a temp xlsx derived from the SAF-T file
        safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", saft_path.stem)
        tmp_dir = Path(tempfile.mkdtemp(prefix="utvalg_sb_"))
        tmp_xlsx = tmp_dir / f"saldobalanse_fra_{safe_stem}.xlsx"

        try:
            make_trial_balance_xlsx_from_saft(saft_path, tmp_xlsx)
        except Exception:
            _log.exception("Failed to extract trial balance from SAF-T")
            messagebox.showwarning(
                "Versjoner",
                "Kunne ikke hente saldobalanse fra SAF-T. Du kan importere saldobalanse manuelt (Excel) i Saldobalanse-fanen.",
                parent=self.top,
            )
            return None

        try:
            sb_v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype="sb",
                source_path=str(tmp_xlsx),
                make_active=bool(make_active),
            )
        except Exception:
            _log.exception("Failed to create SB version")
            messagebox.showwarning(
                "Versjoner",
                "Klarte å hente saldobalanse fra SAF-T, men kunne ikke lagre som versjon.",
                parent=self.top,
            )
            return None

        # Info message for clarity
        if make_active:
            messagebox.showinfo(
                "Versjoner",
                "Saldobalanse ble hentet fra SAF-T og satt som aktiv versjon.",
                parent=self.top,
            )
        else:
            messagebox.showinfo(
                "Versjoner",
                "Saldobalanse ble hentet fra SAF-T og lagret som en ny versjon.\n"
                "(Den ble ikke satt som aktiv fordi det allerede finnes en aktiv saldobalanseversjon.)",
                parent=self.top,
            )

        return sb_v.id


def open_versions_dialog(
    parent: tk.Misc,
    client: str,
    year: int,
    dtype: str,
    current_path_getter,
    on_use_version=None,
    on_after_change=None,
    dtypes: list[str] | None = None,
) -> None:
    """Open dialog.

    When dtype is hb/sb we automatically include both in the dialog to make it
    obvious whether saldobalanse exists.
    """

    if dtypes is None and dtype in {"hb", "sb"}:
        dtypes = ["hb", "sb"]

    dlg = _VersionsDialog(
        parent,
        state=_DialogState(client=client, year=year, dtype=dtype),
        current_path_getter=current_path_getter,
        on_use_version=on_use_version,
        on_after_change=on_after_change,
        dtypes=dtypes,
    )
    dlg.show_modal()
