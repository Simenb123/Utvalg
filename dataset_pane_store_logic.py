# -*- coding: utf-8 -*-
"""dataset_pane_store_logic.py

Logikk for ClientStoreSection som er flyttet ut for å holde UI-fila mindre.

Funksjonene her opererer på en *seksjon-instans* (duck-typing):
de forventer at objektet har feltene/metodene som brukes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import logging

import app_paths

log = logging.getLogger(__name__)


try:
    import client_store

    _HAS_CLIENT_STORE = True
except Exception:
    client_store = None
    _HAS_CLIENT_STORE = False


def apply_active_version_to_path_if_needed(sec) -> None:  # noqa: ANN001
    """Hvis filfeltet er tomt/ugyldig, sett path til aktiv versjon."""

    if not _HAS_CLIENT_STORE or client_store is None:
        return
    c = (sec._client() or "").strip()
    if not c:
        return
    y = (sec._year() or "").strip()
    if not y:
        return

    cur_path_str = str(sec.get_current_path() or "").strip()
    cur_path = Path(cur_path_str) if cur_path_str else None
    # Overstyr kun når feltet er tomt eller peker på en fil som ikke finnes.
    # (Hvis brukeren har valgt en gyldig fil manuelt, lar vi den stå.)
    if cur_path is not None and cur_path.exists():
        return

    try:
        v = client_store.get_active_version(c, year=y, dtype=sec.dtype)
        p = getattr(v, "path", None)
    except Exception:
        p = None
    if p is None:
        return
    pp = Path(str(p))
    if not pp.exists():
        return
    try:
        sec.on_path_selected(str(pp))
    except Exception:
        pass


def auto_store_hb_from_path(sec, path: str, *, show_messages: bool = False) -> Optional[str]:  # noqa: ANN001
    """Lagre fil som ny versjon i klientlageret.

    Returnerer lagret path (string) dersom alt OK eller duplikat, ellers None.
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None

    c = (sec._client() or "").strip()
    if not c:
        return None
    y = (sec._year() or "").strip()
    if not y:
        return None

    src = Path(str(path)).expanduser()
    if not src.exists():
        return None

    # Hvis allerede lagret i client_store-mappen, gjør ingenting.
    try:
        root = (app_paths.data_dir() / "clients").resolve()
        if root in src.resolve().parents:
            return str(src)
    except Exception:
        pass

    try:
        v = client_store.create_version(c, year=y, dtype=sec.dtype, src_path=src, make_active=True)
        sec.hb_var.set(v.id)
        sec.refresh()

        vv = client_store.get_version(c, year=y, dtype=sec.dtype, version_id=v.id)
        stored = getattr(vv, "path", None)
        stored_s = str(stored) if stored else None
        if stored_s:
            try:
                sec.on_path_selected(stored_s)
            except Exception:
                pass

        if show_messages:
            from tkinter import messagebox

            messagebox.showinfo("Lagring", "Filen ble lagret som ny HB-versjon.")
        return stored_s

    except Exception as e:
        # Duplikat: velg eksisterende
        if _HAS_CLIENT_STORE and client_store is not None and isinstance(e, getattr(client_store, "DuplicateContentError", Exception)):
            try:
                client_store.set_active_version(c, year=y, dtype=sec.dtype, version_id=e.existing_id)
                sec.hb_var.set(e.existing_id)
                sec.refresh()
                vv = client_store.get_version(c, year=y, dtype=sec.dtype, version_id=e.existing_id)
                stored = getattr(vv, "path", None)
                stored_s = str(stored) if stored else None
                if stored_s:
                    try:
                        sec.on_path_selected(stored_s)
                    except Exception:
                        pass
                if show_messages:
                    from tkinter import messagebox

                    messagebox.showinfo("Lagring", "Filinnholdet finnes allerede. Valgte eksisterende versjon.")
                return stored_s
            except Exception:
                pass

        if show_messages:
            from tkinter import messagebox

            messagebox.showerror("Lagring", f"Kunne ikke lagre filen: {e}")
        log.warning("auto_store feilet: %s", e)
        return None
