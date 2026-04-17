"""workpaper_export_motpost.py — Motpost-flytdiagram eksport (HTML/PDF).

Inneholder:
  - build_konto_to_rl
  - export_motpost_flowchart_html
  - export_motpost_flowchart_pdf
"""

from __future__ import annotations

import logging

import pandas as pd

import session

try:
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

log = logging.getLogger(__name__)


def build_konto_to_rl(page) -> dict | None:
    """Bygg mapping konto_str -> (regnr, rl_name) fra sidens RL-intervaller."""
    agg_var = getattr(page, "_var_aggregering", None)
    if agg_var is None:
        return None
    try:
        mode = str(agg_var.get())
    except Exception:
        return None
    if mode != "Regnskapslinje":
        return None

    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    df = getattr(page, "_df_filtered", None)

    if intervals is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {}

    try:
        from regnskap_mapping import apply_interval_mapping, normalize_regnskapslinjer

        rl_name_map: dict[int, str] = {}
        if isinstance(regnskapslinjer, pd.DataFrame) and not regnskapslinjer.empty:
            try:
                regn = normalize_regnskapslinjer(regnskapslinjer)
                for _, row in regn.iterrows():
                    try:
                        rl_name_map[int(row["regnr"])] = str(row.get("regnskapslinje", "") or "")
                    except Exception:
                        pass
            except Exception:
                pass

        kontos = df["Konto"].dropna().astype(str).str.strip().unique().tolist()
        probe = pd.DataFrame({"konto": kontos})
        result = apply_interval_mapping(probe, intervals, konto_col="konto")
        mapped = result.mapped.dropna(subset=["regnr"])

        konto_to_rl: dict[str, tuple[int, str]] = {}
        for _, row in mapped.iterrows():
            try:
                regnr = int(row["regnr"])
                rl_name = rl_name_map.get(regnr, str(regnr))
                konto_to_rl[str(row["konto"])] = (regnr, rl_name)
            except Exception:
                pass

        return konto_to_rl
    except Exception:
        return {}


def _safe_base_name(prefix: str, client: str, year: str) -> str:
    base = prefix
    if client:
        safe = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client).strip()
        if safe:
            base += f" {safe}"
    if year:
        base += f" {year}"
    return base


def export_motpost_flowchart_html(page) -> None:
    """Eksporter motpost-flytdiagram som HTML for valgte kontoer."""
    if filedialog is None:
        return

    accounts = page._get_selected_accounts()
    if not accounts:
        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", "Velg minst en konto i pivoten først.")
            except Exception:
                pass
        return

    df = getattr(page, "_df_filtered", None)
    if not isinstance(df, pd.DataFrame) or df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", "Ingen transaksjonsdata tilgjengelig.")
            except Exception:
                pass
        return

    try:
        client = str(getattr(session, "client", "") or "").strip()
        year = str(getattr(session, "year", "") or "").strip()
    except Exception:
        client, year = "", ""

    base_name = _safe_base_name("Motpost-flytdiagram", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter motpost-flytdiagram",
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
        from motpost_flowchart_report import save_flowchart_html

        saved = save_flowchart_html(
            path,
            df=df,
            start_accounts=accounts,
            max_depth=2,
            client=client,
            year=year,
            konto_to_rl=build_konto_to_rl(page),
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("Motpost-flytdiagram", f"Kunne ikke generere flytdiagram.\n\n{exc}")
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
            messagebox.showinfo("Motpost-flytdiagram", f"Flytdiagram lagret og åpnet:\n{saved}")
        except Exception:
            pass


def export_motpost_flowchart_pdf(page) -> None:
    """Eksporter motpost-flytdiagram som PDF for valgte kontoer."""
    if filedialog is None:
        return

    accounts = page._get_selected_accounts()
    if not accounts:
        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", "Velg minst en konto i pivoten først.")
            except Exception:
                pass
        return

    df = getattr(page, "_df_filtered", None)
    if not isinstance(df, pd.DataFrame) or df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("Motpost-flytdiagram", "Ingen transaksjonsdata tilgjengelig.")
            except Exception:
                pass
        return

    try:
        client = str(getattr(session, "client", "") or "").strip()
        year = str(getattr(session, "year", "") or "").strip()
    except Exception:
        client, year = "", ""

    base_name = _safe_base_name("Motpost-flytdiagram", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter motpost-flytdiagram (PDF)",
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
        from motpost_flowchart_report import save_flowchart_pdf

        saved = save_flowchart_pdf(
            path,
            df=df,
            start_accounts=accounts,
            max_depth=2,
            client=client,
            year=year,
            konto_to_rl=build_konto_to_rl(page),
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
                messagebox.showerror("Motpost-flytdiagram", f"Kunne ikke generere PDF.\n\n{exc}")
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
            messagebox.showinfo("Motpost-flytdiagram", f"Flytdiagram (PDF) lagret:\n{saved}")
        except Exception:
            pass
