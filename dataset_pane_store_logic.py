# -*- coding: utf-8 -*-
"""dataset_pane_store_logic.py

Logikk for ClientStoreSection som er flyttet ut for å holde UI-fila mindre.

Funksjonene her opererer på en *seksjon-instans* (duck-typing):
De forventer at objektet har feltene/metodene som brukes.

Denne fila er en del av "Safe A"-opplegget:
- kildefiler lagres urørt som HB-versjoner
- ferdigbygd datasett caches i sqlite

For å unngå rot i GUI må filfeltet oppdatere seg riktig når bruker bytter
klient/år/versjon.
"""

from __future__ import annotations

from pathlib import Path
import os
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


def _clients_root() -> Optional[Path]:
    try:
        # Ikke bruk resolve() her – det kan bli tregt på nettverksdisker.
        return (app_paths.data_dir() / "clients").absolute()
    except Exception:
        return None


def _norm_path(p: Path) -> str:
    """Normaliser path for raske sammenligninger uten filsystem-oppslag.

    Viktig: Ikke bruk resolve() – det kan trigge nettverksoppslag.
    """
    return os.path.normcase(os.path.normpath(str(p)))


def _is_under(base: Path, p: Path) -> bool:
    try:
        base_n = _norm_path(base)
        p_n = _norm_path(p)
        common = os.path.commonpath([p_n, base_n])
        return common == base_n
    except Exception:
        return False



def apply_active_version_to_path_if_needed(sec, *, force: bool = False) -> None:  # noqa: ANN001
    """Oppdater filfeltet til aktiv HB-versjon når det gir mening.

    Bakgrunn:
    Når man bytter klient skal GUI normalt peke på klientens aktive HB-versjon.
    Tidligere lot vi alltid en gyldig fil stå urørt, men det gir lett "rot" –
    spesielt når filen peker på en annen klient.

    Regler:
    - Hvis valgt klient/år ikke er satt: gjør ingenting.
    - Finn aktiv versjon-path (hvis finnes).
    - Hvis filfeltet er tomt eller peker på en fil som ikke finnes: sett til aktiv path (hvis finnes).
    - Hvis filfeltet peker på en fil *inne i* clients-root, og den ikke er den aktive pathen:
        - sett til aktiv path hvis finnes, ellers tøm feltet.
    - Hvis filfeltet peker på en fil utenfor clients-root (brukeren holder på å importere en ny fil):
        - ikke overstyr.

    Parametere:
        force: Brukes av UI når bruker bytter klient/år for å trigge en ny vurdering.
               Foreløpig følger vi fortsatt reglene over (dvs. overskriver ikke en
               gyldig, bruker-valgt fil utenfor clients-root).
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return

    c = (sec._client() or "").strip()
    if not c:
        return

    y = (sec._year() or "").strip()
    if not y:
        return

    # Current path (from dataset pane)
    cur_path_str = str(sec.get_current_path() or "").strip()
    cur_path = Path(cur_path_str).expanduser() if cur_path_str else None
    root = _clients_root()
    cur_exists = False
    cur_in_store = False
    try:
        if cur_path is not None:
            cur_exists = cur_path.exists()
            if root is not None:
                cur_in_store = _is_under(root, cur_path)
    except Exception:
        cur_exists = False
        cur_in_store = False

    # Active version path
    active_path: Optional[Path] = None
    try:
        v = client_store.get_active_version(c, year=y, dtype=sec.dtype)
        p = getattr(v, "path", None)
        if p:
            pp = Path(str(p))
            if pp.exists():
                active_path = pp
    except Exception:
        active_path = None

    # 1) If user is pointing to an external (non-store) file, don't override.
    if cur_exists and not cur_in_store:
        return

    # 2) If current is empty or missing
    if not cur_exists:
        if active_path is not None:
            try:
                sec.on_path_selected(str(active_path))
            except Exception:
                pass
        else:
            # If we previously had an internal store-file that is now missing, clear the field.
            if cur_path_str:
                try:
                    sec.on_path_selected("")
                except Exception:
                    pass
        return

    # 3) Current exists and is inside store-root.
    if active_path is not None:
        try:
            if cur_path is None or _norm_path(cur_path) != _norm_path(active_path):
                sec.on_path_selected(str(active_path))
        except Exception:
            try:
                sec.on_path_selected(str(active_path))
            except Exception:
                pass
        return

    # 4) No active version for this client/year – clear internal path to avoid mixing clients.
    try:
        sec.on_path_selected("")
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
        root = (app_paths.data_dir() / "clients").absolute()
        if _is_under(root, src):
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
