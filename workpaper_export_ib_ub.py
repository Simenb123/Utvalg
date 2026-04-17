"""workpaper_export_ib_ub.py — SB/HB-avstemming og IB/UB-kontinuitetskontroll.

Inneholder:
  - export_ib_ub_control  (SB/HB-avstemming)
  - export_ib_ub_continuity  (IB i år == UB fjor)
"""

from __future__ import annotations

import logging
from pathlib import Path as _Path

import pandas as pd

import formatting
import session

try:
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

log = logging.getLogger(__name__)


def _safe_base_name(prefix: str, client: str, year: str) -> str:
    base = prefix
    if client:
        safe = "".join(ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in str(client)).strip()
        if safe:
            base += f" {safe}"
    if year:
        base += f" {year}"
    return base


# ------------------------------------------------------------------
# SB/HB Avstemming
# ------------------------------------------------------------------

def export_ib_ub_control(page) -> None:
    if filedialog is None:
        return

    import ib_ub_control
    import ib_ub_control_excel
    import page_analyse_rl

    # Hent SB
    sb_df = None
    sb_err = ""
    try:
        sb_df = page_analyse_rl.load_sb_for_session()
    except Exception as exc:
        sb_err = str(exc)
    if sb_df is None:
        sb_df = getattr(page, "_rl_sb_df", None)

    # Siste forsøk: last direkte fra client_store
    if sb_df is None or (isinstance(sb_df, pd.DataFrame) and sb_df.empty):
        try:
            import client_store
            from trial_balance_reader import read_trial_balance
            _client = getattr(session, "client", None)
            _year = str(getattr(session, "year", None) or "")
            if _client and _year:
                _v = client_store.get_active_version(_client, year=_year, dtype="sb")
                if _v is not None:
                    _sbp = _Path(_v.path)
                    if _sbp.exists():
                        sb_df = read_trial_balance(_sbp)
                    else:
                        sb_err = f"SB-fil finnes ikke: {_sbp}"
                else:
                    sb_err = f"Ingen aktiv SB-versjon for {_client}/{_year}"
            else:
                sb_err = f"session.client={_client!r}, session.year={_year!r}"
        except Exception as exc:
            sb_err = str(exc)

    if sb_df is None or (isinstance(sb_df, pd.DataFrame) and sb_df.empty):
        if messagebox is not None:
            try:
                detail = f"\n\nDetalj: {sb_err}" if sb_err else ""
                messagebox.showinfo(
                    "SB/HB Avstemming",
                    "Ingen saldobalanse tilgjengelig.\n\n"
                    "Last inn en saldobalanse (SB) via Versjoner-dialogen for å bruke denne funksjonen."
                    + detail,
                )
            except Exception:
                pass
        return

    # Hent HB
    hb_df = getattr(page, "_df_filtered", None)
    if hb_df is None or not isinstance(hb_df, pd.DataFrame) or hb_df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("SB/HB Avstemming", "Ingen hovedbok-data å avstemme mot.")
            except Exception:
                pass
        return

    # RL-mapping (valgfri)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    account_overrides = None
    try:
        account_overrides = page_analyse_rl._load_current_client_account_overrides()
    except Exception:
        pass

    # Beregn
    try:
        result = ib_ub_control.reconcile(
            sb_df,
            hb_df,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("SB/HB Avstemming", f"Feil ved beregning av avstemming.\n\n{exc}")
            except Exception:
                pass
        return

    # Filnavn
    client = getattr(session, "client", None) or ""
    year = getattr(session, "year", None) or ""
    base_name = _safe_base_name("SB_HB_Avstemming", str(client), str(year))

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter SB/HB-avstemming",
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
        wb = ib_ub_control_excel.build_ib_ub_workpaper(
            result.account_level,
            rl_recon=result.rl_level,
            summary=result.summary,
            client=client,
            year=year,
        )
        wb.save(path)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("SB/HB Avstemming", f"Kunne ikke lagre arbeidspapir.\n\n{exc}")
            except Exception:
                pass
        return

    # Suksessmelding
    n_avvik = result.summary.get("antall_avvik", 0)
    total_diff = result.summary.get("total_differanse", 0)
    msg = f"Arbeidspapir lagret til:\n{path}\n\n"
    if n_avvik == 0:
        msg += "\u2713 Ingen avvik funnet \u2014 SB og HB stemmer overens."
    else:
        msg += f"\u26a0 {n_avvik} konto(er) med avvik.\nTotal differanse: {formatting.fmt_amount(total_diff)}"

    if messagebox is not None:
        try:
            messagebox.showinfo("SB/HB Avstemming", msg)
        except Exception:
            pass


# ------------------------------------------------------------------
# IB/UB-kontinuitetskontroll (IB i år == UB fjor)
# ------------------------------------------------------------------

def export_ib_ub_continuity(page) -> None:
    """Eksporter IB/UB-kontinuitetskontroll: sjekk at IB(i år) == UB(fjor)."""
    if filedialog is None:
        return

    import ib_ub_control
    import ib_ub_control_excel
    import page_analyse_rl
    from previous_year_comparison import load_previous_year_sb

    client = getattr(session, "client", None) or ""
    year = str(getattr(session, "year", None) or "")

    # Hent SB for inneværende år
    sb_current = None
    sb_err = ""
    try:
        sb_current = page_analyse_rl.load_sb_for_session()
    except Exception as exc:
        sb_err = str(exc)
    if sb_current is None:
        sb_current = getattr(page, "_rl_sb_df", None)

    if sb_current is None or (isinstance(sb_current, pd.DataFrame) and sb_current.empty):
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "IB/UB-kontroll",
                    "Ingen saldobalanse for inneværende år tilgjengelig.\n\n"
                    "Last inn en saldobalanse (SB) via Versjoner-dialogen."
                    + (f"\n\nDetalj: {sb_err}" if sb_err else ""),
                )
            except Exception:
                pass
        return

    # Hent SB for forrige år
    sb_previous = None
    if client and year:
        sb_previous = load_previous_year_sb(client, year)

    if sb_previous is None or (isinstance(sb_previous, pd.DataFrame) and sb_previous.empty):
        prev_year = ""
        try:
            prev_year = str(int(year) - 1)
        except (ValueError, TypeError):
            pass
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "IB/UB-kontroll",
                    f"Ingen saldobalanse for forrige år ({prev_year or 'fjor'}) tilgjengelig.\n\n"
                    f"Last inn en saldobalanse (SB) for {prev_year or 'forrige år'} via Versjoner-dialogen "
                    f"for å kunne kjøre IB/UB-kontinuitetskontroll.\n\n"
                    f"Kontroller at klient \u00ab{client}\u00bb har en aktiv SB-versjon for år {prev_year}.",
                )
            except Exception:
                pass
        return

    # Beregn
    try:
        result = ib_ub_control.check_continuity(sb_current, sb_previous)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("IB/UB-kontroll", f"Feil ved beregning.\n\n{exc}")
            except Exception:
                pass
        return

    # Filnavn
    base_name = _safe_base_name("IB_UB_Kontroll", str(client), str(year))

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter IB/UB-kontinuitetskontroll",
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
        wb = ib_ub_control_excel.build_continuity_workpaper(
            result.account_level,
            summary=result.summary,
            client=client,
            year=year,
        )
        wb.save(path)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("IB/UB-kontroll", f"Kunne ikke lagre arbeidspapir.\n\n{exc}")
            except Exception:
                pass
        return

    n_avvik = result.summary.get("antall_avvik", 0)
    total_diff = result.summary.get("total_differanse", 0)
    msg = f"Arbeidspapir lagret til:\n{path}\n\n"
    if n_avvik == 0:
        msg += "\u2713 Ingen avvik \u2014 IB stemmer med UB fjor."
    else:
        msg += f"\u26a0 {n_avvik} konto(er) der IB \u2260 UB fjor.\nTotal differanse: {formatting.fmt_amount(total_diff)}"

    if messagebox is not None:
        try:
            messagebox.showinfo("IB/UB-kontroll", msg)
        except Exception:
            pass
