"""workpaper_export_hb_diff.py — HB versjonsdiff eksport.

Inneholder:
  - export_hb_version_diff
  - pick_hb_version
  - load_hb_version_df
"""

from __future__ import annotations

import logging
from pathlib import Path as _Path
from typing import Optional

import pandas as pd

import session

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

log = logging.getLogger(__name__)


def export_hb_version_diff(page) -> None:
    """Sammenlign gjeldende HB med en tidligere versjon og eksporter diff."""
    if filedialog is None:
        return

    import src.shared.client_store.store as client_store

    client = getattr(session, "client", None) or ""
    year = str(getattr(session, "year", None) or "")

    if not client or not year:
        if messagebox is not None:
            try:
                messagebox.showinfo("HB Versjonsdiff", "Ingen klient/år valgt.")
            except Exception:
                pass
        return

    # Hent alle HB-versjoner
    try:
        versions = client_store.list_versions(client, year=year, dtype="hb")
    except Exception:
        versions = []

    if len(versions) < 2:
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "HB Versjonsdiff",
                    "Du trenger minst 2 HB-versjoner for å sammenligne.\n\n"
                    "Importer en ny hovedbok via Versjoner-dialogen.",
                )
            except Exception:
                pass
        return

    active_id = None
    try:
        active_id = client_store.get_active_version_id(client, year=year, dtype="hb")
    except Exception:
        pass

    # Velg versjon å sammenligne med
    chosen_id = pick_hb_version(page, versions, active_id)
    if not chosen_id:
        return

    # Last gammel versjon
    old_df = load_hb_version_df(page, client, year, chosen_id)
    if old_df is None or old_df.empty:
        if messagebox is not None:
            try:
                messagebox.showerror("HB Versjonsdiff", "Kunne ikke laste valgt versjon.")
            except Exception:
                pass
        return

    # Gjeldende HB
    current_df = getattr(page, "_df_filtered", None)
    if current_df is None or not isinstance(current_df, pd.DataFrame):
        current_df = getattr(page, "dataset", None)
    if current_df is None or not isinstance(current_df, pd.DataFrame) or current_df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("HB Versjonsdiff", "Ingen aktiv hovedbok å sammenligne med.")
            except Exception:
                pass
        return

    # Beregn diff
    import hb_version_diff
    import hb_version_diff_excel

    try:
        result = hb_version_diff.diff_hb_versions(old_df, current_df)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("HB Versjonsdiff", f"Feil ved beregning av diff.\n\n{exc}")
            except Exception:
                pass
        return

    # Finn versjonsnavn
    old_label = "Forrige"
    current_label = "Gjeldende"
    try:
        old_v = client_store.get_version(client, year=year, dtype="hb", version_id=chosen_id)
        if old_v:
            old_label = _Path(old_v.filename or old_v.path).stem
    except Exception:
        pass

    # Filnavn
    base_name = "HB_Versjonsdiff"
    safe_client = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in str(client)).strip()
    if safe_client:
        base_name += f" {safe_client}"
    if year:
        base_name += f" {year}"

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter HB versjonsdiff",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=base_name + ".xlsx",
            initialdir=page._get_export_initialdir(str(client), str(year)),
        )
    except Exception:
        path = ""

    if not path:
        return

    try:
        wb = hb_version_diff_excel.build_hb_diff_workpaper(
            result,
            client=client,
            year=year,
            version_a_label=old_label,
            version_b_label=current_label,
        )
        wb.save(path)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("HB Versjonsdiff", f"Kunne ikke lagre.\n\n{exc}")
            except Exception:
                pass
        return

    # Suksessmelding
    s = result.summary
    msg = f"Versjonsdiff lagret til:\n{path}\n\n"
    msg += f"Nye bilag: {s.get('nye_bilag', 0)}\n"
    msg += f"Fjernede bilag: {s.get('fjernede_bilag', 0)}\n"
    msg += f"Endrede bilag: {s.get('endrede_bilag', 0)}\n"
    msg += f"Uendrede bilag: {s.get('uendrede_bilag', 0)}"

    if messagebox is not None:
        try:
            messagebox.showinfo("HB Versjonsdiff", msg)
        except Exception:
            pass


def pick_hb_version(page, versions, active_id) -> Optional[str]:
    """Enkel dialog for å velge en HB-versjon å sammenligne med."""
    if tk is None:
        return None

    from datetime import datetime as _dt

    result_var = {"id": None}

    top = tk.Toplevel(page)
    top.title("Velg HB-versjon å sammenligne med")
    top.geometry("480x320")
    top.transient(page)
    top.grab_set()

    ttk.Label(top, text="Velg en tidligere versjon å sammenligne mot gjeldende HB:").pack(
        padx=10, pady=(10, 5), anchor="w",
    )

    frame = ttk.Frame(top)
    frame.pack(fill="both", expand=True, padx=10, pady=5)

    tree = ttk.Treeview(frame, columns=("name", "date"), show="headings", selectmode="browse")
    tree.heading("name", text="Fil")
    tree.heading("date", text="Importert")
    tree.column("name", width=280)
    tree.column("date", width=150)

    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    for v in reversed(versions):
        if v.id == active_id:
            continue
        name = _Path(v.filename or v.path).name
        try:
            ts = _dt.fromtimestamp(v.created_at).strftime("%d.%m.%Y %H:%M")
        except Exception:
            ts = ""
        tree.insert("", "end", iid=v.id, values=(name, ts))

    def on_ok():
        sel = tree.selection()
        if sel:
            result_var["id"] = sel[0]
        top.destroy()

    def on_cancel():
        top.destroy()

    btn_frame = ttk.Frame(top)
    btn_frame.pack(fill="x", padx=10, pady=(5, 10))
    ttk.Button(btn_frame, text="Sammenlign", command=on_ok).pack(side="right", padx=5)
    ttk.Button(btn_frame, text="Avbryt", command=on_cancel).pack(side="right")

    tree.bind("<Double-1>", lambda e: on_ok())

    top.wait_window()
    return result_var["id"]


def load_hb_version_df(page, client: str, year: str, version_id: str) -> Optional[pd.DataFrame]:
    """Last en HB-versjon som DataFrame."""
    import src.shared.client_store.store as client_store

    v = client_store.get_version(client, year=year, dtype="hb", version_id=version_id)
    if v is None:
        return None

    # Forsøk cache først
    try:
        dc = (v.meta or {}).get("dataset_cache", {})
        if isinstance(dc, dict) and dc.get("file"):
            import src.pages.dataset.backend.cache_sqlite as dataset_cache_sqlite
            ds_dir = client_store.datasets_dir(client, year=year, dtype="hb")
            db_path = ds_dir / str(dc["file"])
            if db_path.exists():
                df, _ = dataset_cache_sqlite.load_cache(db_path)
                if df is not None and not df.empty:
                    return df
    except Exception:
        pass

    # Fallback: bygg fra fil med lagret mapping
    try:
        from src.pages.dataset.backend.build_fast import build_from_file

        build_info = ((v.meta or {}).get("dataset_cache") or {}).get("build") or {}
        mapping = build_info.get("mapping")
        sheet_name = build_info.get("sheet_name")
        header_row = build_info.get("header_row", 1)

        p = _Path(v.path)
        if not p.exists():
            return None

        df = build_from_file(
            p,
            mapping=mapping,
            sheet_name=sheet_name,
            header_row=header_row,
        )
        return df
    except Exception:
        return None
