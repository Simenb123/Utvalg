"""Dialog for managing stored versions (HB/SAF-T etc.) for a given client/year.

The Dataset pane deliberately stays lean; version CRUD is handled here.

This module is imported lazily (on button click) to avoid adding startup overhead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import os
import subprocess
import sys
import time

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import client_store
except Exception:  # pragma: no cover
    client_store = None  # type: ignore


def _fmt_ts(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return ""


def _open_path(path: str) -> None:
    """Open a file or folder in the OS default handler."""
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return
        subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Åpne", f"Kunne ikke åpne: {e}")


@dataclass
class _DialogState:
    client: str
    year: str
    dtype: str


class _VersionsDialog:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        client: str,
        year: str,
        dtype: str,
        current_path_getter: Optional[Callable[[], str]] = None,
        on_use_version: Optional[Callable[[str], None]] = None,
        on_after_change: Optional[Callable[[], None]] = None,
    ) -> None:
        if client_store is None:
            raise RuntimeError("client_store er ikke tilgjengelig")

        self._state = _DialogState(client=client, year=year, dtype=dtype)
        self._current_path_getter = current_path_getter
        self._on_use_version = on_use_version
        self._on_after_change = on_after_change

        self.top = tk.Toplevel(parent)
        self.top.title("Versjoner")
        self.top.transient(parent)

        # Layout
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(2, weight=1)

        hdr = ttk.Frame(self.top)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        hdr.columnconfigure(0, weight=1)

        self.lbl_title = ttk.Label(
            hdr,
            text=f"Klient: {client}   År: {year}",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_title.grid(row=0, column=0, sticky="w")

        # Buttons row (actions)
        actions = ttk.Frame(self.top)
        actions.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        self.btn_import = ttk.Button(actions, text="Importer fil…", command=self._on_import_file)
        self.btn_from_field = ttk.Button(actions, text="Ny versjon fra filfelt", command=self._on_store_from_field)
        self.btn_open_file = ttk.Button(actions, text="Åpne fil", command=self._on_open_file)
        self.btn_open_folder = ttk.Button(actions, text="Åpne mappe", command=self._on_open_folder)
        self.btn_delete = ttk.Button(actions, text="Slett versjon", command=self._on_delete)

        self.btn_import.grid(row=0, column=0, padx=(0, 6))
        self.btn_from_field.grid(row=0, column=1, padx=(0, 12))
        self.btn_open_file.grid(row=0, column=2, padx=(0, 6))
        self.btn_open_folder.grid(row=0, column=3, padx=(0, 12))
        self.btn_delete.grid(row=0, column=4)

        # Versions table
        body = ttk.Frame(self.top)
        body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            body,
            columns=("active", "filename", "created"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("active", text="Aktiv")
        self.tree.heading("filename", text="Fil")
        self.tree.heading("created", text="Opprettet")

        self.tree.column("active", width=50, anchor="center", stretch=False)
        self.tree.column("filename", width=520, anchor="w")
        self.tree.column("created", width=160, anchor="w", stretch=False)

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Double-1>", lambda _e: self._on_use_and_close())

        # Footer
        footer = ttk.Frame(self.top)
        footer.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        footer.columnconfigure(0, weight=1)

        self.lbl_hint = ttk.Label(
            footer,
            text=(
                "Tips: Velg en rad og dobbeltklikk for å bruke versjonen. "
                "'Ny versjon fra filfelt' tar filstien fra Dataset-feltet i hovedvinduet."
            ),
        )
        self.lbl_hint.grid(row=0, column=0, sticky="w")

        btns = ttk.Frame(footer)
        btns.grid(row=0, column=1, sticky="e")

        self.btn_use = ttk.Button(btns, text="Bruk valgt", command=self._on_use_and_close)
        self.btn_close = ttk.Button(btns, text="Lukk", command=self.top.destroy)
        self.btn_use.grid(row=0, column=0, padx=(0, 6))
        self.btn_close.grid(row=0, column=1)

        self._reload(select_id=None)

        # Center relative to parent
        self.top.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = min(max(self.top.winfo_width(), 820), 1100)
            h = min(max(self.top.winfo_height(), 420), 720)
            x = px + max((pw - w) // 2, 40)
            y = py + max((ph - h) // 2, 40)
            self.top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    # ---- Helpers -------------------------------------------------

    def _selected_id(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            return None
        return str(sel[0])

    def _get_version(self, version_id: str):
        assert client_store is not None
        return client_store.get_version(self._state.client, year=self._state.year, dtype=self._state.dtype, version_id=version_id)

    def _reload(self, *, select_id: Optional[str]) -> None:
        assert client_store is not None
        versions = client_store.list_versions(self._state.client, year=self._state.year, dtype=self._state.dtype)
        # client_store exposes get_active_version() (VersionModel|None). Older code used
        # get_active_version_id(); keep this robust even if the helper doesn't exist.
        try:
            v_active = client_store.get_active_version(
                self._state.client,
                year=self._state.year,
                dtype=self._state.dtype,
            )
            active_id = v_active.id if v_active else None
        except Exception:
            active_id = None

        # Clear
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        # Insert (newest first)
        versions_sorted = sorted(versions, key=lambda v: v.created_at, reverse=True)
        for v in versions_sorted:
            mark = "*" if (active_id and v.id == active_id) else ""
            self.tree.insert("", "end", iid=v.id, values=(mark, v.filename, _fmt_ts(v.created_at)))

        # Selection
        preferred = select_id or active_id
        if preferred and preferred in {v.id for v in versions}:
            try:
                self.tree.selection_set(preferred)
                self.tree.see(preferred)
            except Exception:
                pass

    def _after_change(self) -> None:
        if self._on_after_change:
            try:
                self._on_after_change()
            except Exception:
                pass

    # ---- Actions -------------------------------------------------

    def _on_use_and_close(self) -> None:
        vid = self._selected_id()
        if not vid:
            messagebox.showinfo("Versjoner", "Velg en versjon først.")
            return

        assert client_store is not None
        ok = client_store.set_active_version(self._state.client, year=self._state.year, dtype=self._state.dtype, version_id=vid)
        if ok and self._on_use_version:
            try:
                self._on_use_version(vid)
            except Exception:
                pass

        self._after_change()
        self.top.destroy()

    def _on_import_file(self) -> None:
        if client_store is None:
            return

        path = filedialog.askopenfilename(title="Velg fil som skal lagres som ny versjon")
        if not path:
            return

        p = Path(path)
        if not p.exists() or not p.is_file():
            messagebox.showerror("Versjoner", "Valgt fil finnes ikke.")
            return

        try:
            v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype=self._state.dtype,
                src_path=str(p),
                make_active=True,
            )
        except Exception as e:
            messagebox.showerror("Versjoner", f"Kunne ikke lagre ny versjon: {e}")
            return

        self._reload(select_id=v.id)
        if self._on_use_version:
            try:
                self._on_use_version(v.id)
            except Exception:
                pass
        self._after_change()

    def _on_store_from_field(self) -> None:
        if client_store is None:
            return

        if not self._current_path_getter:
            messagebox.showinfo("Versjoner", "Kunne ikke finne filfeltet i hovedvinduet.")
            return

        path = (self._current_path_getter() or "").strip()
        if not path:
            messagebox.showinfo("Versjoner", "Dataset-feltet er tomt. Velg en fil først.")
            return

        p = Path(path)
        if not p.exists() or not p.is_file():
            messagebox.showerror("Versjoner", "Dataset-feltet peker ikke på en eksisterende fil.")
            return

        try:
            v = client_store.create_version(
                self._state.client,
                year=self._state.year,
                dtype=self._state.dtype,
                src_path=str(p),
                make_active=True,
            )
        except Exception as e:
            messagebox.showerror("Versjoner", f"Kunne ikke lagre ny versjon: {e}")
            return

        self._reload(select_id=v.id)
        if self._on_use_version:
            try:
                self._on_use_version(v.id)
            except Exception:
                pass
        self._after_change()

    def _on_delete(self) -> None:
        if client_store is None:
            return

        vid = self._selected_id()
        if not vid:
            messagebox.showinfo("Versjoner", "Velg en versjon først.")
            return

        v = self._get_version(vid)
        if v is None:
            messagebox.showerror("Versjoner", "Fant ikke valgt versjon.")
            return

        if not messagebox.askyesno(
            "Slett versjon",
            f"Slette versjonen?\n\n{v.filename}\n\nDette kan ikke angres.",
            icon="warning",
        ):
            return

        ok = client_store.delete_version(self._state.client, year=self._state.year, dtype=self._state.dtype, version_id=vid)
        if not ok:
            messagebox.showerror("Versjoner", "Kunne ikke slette versjonen.")
            return

        # Select new active version if any
        try:
            v_active = client_store.get_active_version(
                self._state.client,
                year=self._state.year,
                dtype=self._state.dtype,
            )
            active_id = v_active.id if v_active else None
        except Exception:
            active_id = None

        self._reload(select_id=active_id)

        if active_id and self._on_use_version:
            try:
                self._on_use_version(active_id)
            except Exception:
                pass

        self._after_change()

    def _on_open_file(self) -> None:
        vid = self._selected_id()
        if not vid:
            messagebox.showinfo("Versjoner", "Velg en versjon først.")
            return
        v = self._get_version(vid)
        if v is None:
            messagebox.showerror("Versjoner", "Fant ikke valgt versjon.")
            return
        _open_path(v.path)

    def _on_open_folder(self) -> None:
        vid = self._selected_id()
        if not vid:
            messagebox.showinfo("Versjoner", "Velg en versjon først.")
            return
        v = self._get_version(vid)
        if v is None:
            messagebox.showerror("Versjoner", "Fant ikke valgt versjon.")
            return
        folder = str(Path(v.path).parent)
        _open_path(folder)


def open_versions_dialog(
    parent: tk.Misc,
    *,
    client: str,
    year: str,
    dtype: str,
    current_path_getter: Optional[Callable[[], str]] = None,
    on_use_version: Optional[Callable[[str], None]] = None,
    on_after_change: Optional[Callable[[], None]] = None,
) -> None:
    """Open the version overview dialog.

    The dialog is modal (grabs focus) and returns when closed.
    """
    dlg = _VersionsDialog(
        parent,
        client=client,
        year=year,
        dtype=dtype,
        current_path_getter=current_path_getter,
        on_use_version=on_use_version,
        on_after_change=on_after_change,
    )

    # Modal behavior
    dlg.top.grab_set()
    dlg.top.wait_window()
