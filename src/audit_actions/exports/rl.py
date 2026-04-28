"""workpaper_export_rl.py — Eksport av regnskapsoppstilling og nøkkeltall.

Inneholder:
  - export_regnskapsoppstilling_excel
  - export_nokkeltall_html
  - export_nokkeltall_pdf
  - export_active_view_excel
"""

from __future__ import annotations

import logging

import pandas as pd

import page_analyse_export
import session

try:
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

log = logging.getLogger(__name__)


def _merge_fjor(rl_df: pd.DataFrame, page) -> pd.DataFrame:
    """Merge UB_fjor/Endring_fjor/Endring_pct fra pivot inn i rl_df."""
    # Bruk _pivot_df_rl (RL-spesifikk) — _pivot_df_last kan være SB-/HB-
    # konto-pivot som ikke har regnr-kolonne.
    pivot_df = getattr(page, "_pivot_df_rl", None)
    if (
        isinstance(pivot_df, pd.DataFrame)
        and "UB_fjor" in pivot_df.columns
        and "regnr" in pivot_df.columns
        and "regnr" in rl_df.columns
    ):
        rl_df = rl_df.copy()
        for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
            if col in pivot_df.columns and col not in rl_df.columns:
                merged = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                rl_df = rl_df.merge(merged, on="regnr", how="left")
    return rl_df


def _get_rl_payload(page) -> tuple[pd.DataFrame | None, str, str]:
    """Hent rl_df + client/year fra page, returner (rl_df, client, year)."""
    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=page)
    rl_df = payload.get("rl_df")
    if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
        return None, "", ""
    rl_df = _merge_fjor(rl_df, page)
    client = str(payload.get("client") or "").strip()
    year = str(payload.get("year") or "").strip()
    return rl_df, client, year


def _safe_base_name(prefix: str, client: str, year: str) -> str:
    base = prefix
    if client:
        safe = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
        if safe:
            base += f" {safe}"
    if year:
        base += f" {year}"
    return base


# ------------------------------------------------------------------
# Regnskapsoppstilling → Excel
# ------------------------------------------------------------------

def export_regnskapsoppstilling_excel(page) -> None:
    if filedialog is None:
        return

    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=page)
    rl_df = payload.get("rl_df")
    if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", "Fant ingen regnskapsoppstilling å eksportere.")
            except Exception:
                pass
        return

    rl_df = _merge_fjor(rl_df, page)
    client = str(payload.get("client") or "").strip()
    year = str(payload.get("year") or "").strip()
    base_name = _safe_base_name("Regnskapsoppstilling", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter regnskapsoppstilling",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=base_name + ".xlsx",
            initialdir=page._get_export_initialdir(client, year),
        )
    except Exception:
        path = ""

    if not path:
        return

    try:
        import analyse_regnskapsoppstilling_excel

        # Kontospesifisert-arket skal alltid vise alle kontoer pr. RL,
        # uavhengig av hva brukeren har markert i UI. Bruk derfor den
        # ufiltrerte HB (df_hb), ikke den seleksjons-filtrerte
        # transactions_df som brukes til andre eksporter.
        hb_full = payload.get("df_hb")
        if hb_full is None or (isinstance(hb_full, pd.DataFrame) and hb_full.empty):
            hb_full = payload.get("transactions_df")

        saved = analyse_regnskapsoppstilling_excel.save_regnskapsoppstilling_workbook(
            path,
            rl_df=rl_df,
            regnskapslinjer=payload.get("regnskapslinjer"),
            transactions_df=hb_full,
            sb_df=payload.get("sb_df"),
            intervals=payload.get("intervals"),
            account_overrides=payload.get("account_overrides"),
            client=payload.get("client"),
            year=payload.get("year"),
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("Eksport", f"Kunne ikke eksportere regnskapsoppstilling.\n\n{exc}")
            except Exception:
                pass
        return

    if messagebox is not None:
        try:
            messagebox.showinfo("Eksport", f"Regnskapsoppstilling lagret til:\n{saved}")
        except Exception:
            pass


# ------------------------------------------------------------------
# Eksport aktiv visning (generell)
# ------------------------------------------------------------------

def export_active_view_excel(page) -> None:
    """Eksporter den aktive høyre-visningen (TX, SB, Motposter, etc.) til Excel."""
    if filedialog is None:
        return

    from page_analyse_columns import normalize_view_mode

    raw_mode = ""
    try:
        raw_mode = str(page._var_tx_view_mode.get()) if page._var_tx_view_mode else ""
    except Exception:
        pass
    mode = normalize_view_mode(raw_mode)

    tree = None
    # Arknavn i Excel speiler de nye synlige labels i GUI.
    if mode == "Transaksjoner":
        tree = getattr(page, "_tx_tree", None)
        sheet_name = "Hovedbok"
    elif mode == "Saldobalansekontoer":
        f = getattr(page, "_sb_frame", None)
        tree = getattr(f, "_sb_tree", None) if f else None
        sheet_name = "Saldobalanse"
    elif raw_mode == "Motposter":
        f = getattr(page, "_mp_frame", None)
        tree = getattr(f, "_mp_tree", None) if f else None
        sheet_name = "Motposter"
    elif raw_mode == "Motposter (kontonivå)":
        f = getattr(page, "_mp_acct_frame", None)
        tree = getattr(f, "_mp_acct_tree", None) if f else None
        sheet_name = "Motposter kontonivå"
    else:
        sheet_name = raw_mode or "Data"

    if tree is None or not tree.get_children():
        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", "Ingen data å eksportere i aktiv visning.")
            except Exception:
                pass
        return

    import session as _session
    client = str(getattr(_session, "client", "") or "")
    year = str(getattr(_session, "year", "") or "")

    safe_mode = "".join(c if c.isalnum() or c in " _-" else "_" for c in sheet_name).strip()
    base_name = f"Analyse_{safe_mode}"
    if client:
        safe_client = "".join(c if c.isalnum() or c in " _-" else "_" for c in client).strip()
        base_name += f"_{safe_client}"
    if year:
        base_name += f"_{year}"

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title=f"Eksporter {sheet_name}",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=base_name + ".xlsx",
            initialdir=page._get_export_initialdir(client, year),
        )
    except Exception:
        path = ""

    if not path:
        return

    try:
        import analyse_export_excel
        analyse_export_excel.export_trees_to_excel(
            path,
            [analyse_export_excel.treeview_to_sheet_dict(tree, title=sheet_name)],
            title=sheet_name,
            client=client,
            year=year,
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("Eksport", f"Eksport feilet.\n\n{exc}")
            except Exception:
                pass
        return

    try:
        import os
        os.startfile(path)
    except Exception:
        pass


# ------------------------------------------------------------------
# Nøkkeltallsrapport (HTML / PDF)
# ------------------------------------------------------------------

def export_nokkeltall_html(page) -> None:
    if filedialog is None:
        return

    rl_df, client, year = _get_rl_payload(page)
    if rl_df is None:
        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", "Fant ingen regnskapsdata for nøkkeltallsrapport.")
            except Exception:
                pass
        return

    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=page)
    base_name = _safe_base_name("Nokkeltall", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter nøkkeltallsrapport",
            defaultextension=".html",
            filetypes=[("HTML-rapport", "*.html"), ("Alle filer", "*.*")],
            initialfile=base_name + ".html",
            initialdir=page._get_export_initialdir(client, year),
        )
    except Exception:
        path = ""

    if not path:
        return

    try:
        import src.audit_actions.nokkeltall.report as nokkeltall_report

        saved = nokkeltall_report.save_report_html(
            path,
            rl_df=rl_df,
            transactions_df=payload.get("transactions_df"),
            reskontro_df=payload.get("reskontro_df"),
            client=client,
            year=year,
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("Eksport", f"Kunne ikke generere nøkkeltallsrapport.\n\n{exc}")
            except Exception:
                pass
        return

    try:
        import webbrowser
        from pathlib import Path
        webbrowser.open(Path(saved).as_uri())
    except Exception:
        pass

    if messagebox is not None:
        try:
            messagebox.showinfo("Eksport", f"Nøkkeltallsrapport lagret og åpnet:\n{saved}")
        except Exception:
            pass


def export_nokkeltall_pdf(page) -> None:
    if filedialog is None:
        return

    rl_df, client, year = _get_rl_payload(page)
    if rl_df is None:
        if messagebox is not None:
            try:
                messagebox.showinfo("Eksport", "Fant ingen regnskapsdata for nøkkeltallsrapport.")
            except Exception:
                pass
        return

    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=page)
    base_name = _safe_base_name("Nokkeltall", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter nøkkeltallsrapport (PDF)",
            defaultextension=".pdf",
            filetypes=[("PDF-rapport", "*.pdf"), ("Alle filer", "*.*")],
            initialfile=base_name + ".pdf",
            initialdir=page._get_export_initialdir(client, year),
        )
    except Exception:
        path = ""

    if not path:
        return

    try:
        import src.audit_actions.nokkeltall.report as nokkeltall_report

        saved = nokkeltall_report.save_report_pdf(
            path,
            rl_df=rl_df,
            transactions_df=payload.get("transactions_df"),
            reskontro_df=payload.get("reskontro_df"),
            client=client,
            year=year,
        )
    except ImportError as exc:
        if messagebox is not None:
            try:
                messagebox.showerror(
                    "Mangler playwright",
                    f"PDF-eksport krever playwright.\n\nInstaller med:\n"
                    f"pip install playwright\n"
                    f"python -m playwright install chromium\n\n{exc}",
                )
            except Exception:
                pass
        return
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("Eksport", f"Kunne ikke generere PDF-rapport.\n\n{exc}")
            except Exception:
                pass
        return

    try:
        import os
        os.startfile(saved)
    except Exception:
        pass

    if messagebox is not None:
        try:
            messagebox.showinfo("Eksport", f"Nøkkeltallsrapport (PDF) lagret:\n{saved}")
        except Exception:
            pass
