from __future__ import annotations

import app_paths as _app_paths
import session as _session
from tkinter import filedialog as _filedialog, messagebox as _messagebox, simpledialog as _simpledialog

try:
    import src.shared.client_store.store as _client_store
except Exception:
    _client_store = None

try:
    import konto_klassifisering as _konto_klassifisering
except Exception:
    _konto_klassifisering = None


_UNSET = object()

app_paths = _app_paths
client_store = _client_store
session = _session
filedialog = _filedialog
messagebox = _messagebox
simpledialog = _simpledialog
konto_klassifisering = _konto_klassifisering


def set_runtime_refs(
    *,
    app_paths_ref: object = _UNSET,
    client_store_ref: object = _UNSET,
    session_ref: object = _UNSET,
    filedialog_ref: object = _UNSET,
    messagebox_ref: object = _UNSET,
    simpledialog_ref: object = _UNSET,
    konto_klassifisering_ref: object = _UNSET,
) -> None:
    global app_paths, client_store, session, filedialog, messagebox, simpledialog, konto_klassifisering

    if app_paths_ref is not _UNSET:
        app_paths = app_paths_ref
    if client_store_ref is not _UNSET:
        client_store = client_store_ref
    if session_ref is not _UNSET:
        session = session_ref
    if filedialog_ref is not _UNSET:
        filedialog = filedialog_ref
    if messagebox_ref is not _UNSET:
        messagebox = messagebox_ref
    if simpledialog_ref is not _UNSET:
        simpledialog = simpledialog_ref
    if konto_klassifisering_ref is not _UNSET:
        konto_klassifisering = konto_klassifisering_ref


__all__ = [
    "app_paths",
    "client_store",
    "filedialog",
    "konto_klassifisering",
    "messagebox",
    "session",
    "set_runtime_refs",
    "simpledialog",
]
