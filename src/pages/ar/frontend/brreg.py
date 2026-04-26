"""page_ar_brreg.py — BRREG-integrasjon for ARPage.

Utskilt fra page_ar.py. Modulfunksjoner tar page som første argument.
ARPage beholder tynne delegatorer for bakoverkompatibilitet.
"""

from __future__ import annotations

import threading
from typing import Any

from ..backend.store import normalize_orgnr

from ..backend.formatters import _safe_text


def load_brreg_for_selected_row(page, row: dict[str, Any], *, force_refresh: bool = False) -> None:
    orgnr = normalize_orgnr(_safe_text(row.get("company_orgnr")))
    name = _safe_text(row.get("company_name"))
    page._brreg_current_orgnr = orgnr
    page._selected_nr = orgnr
    page._update_brreg_header(orgnr, name)
    try:
        if orgnr and not (force_refresh and orgnr in page._brreg_data):
            pass
        page._btn_brreg_refresh.configure(state="normal" if orgnr else "disabled")
    except Exception:
        pass

    if not orgnr:
        page.var_brreg_status.set("Ingen gyldig org.nr for denne raden — BRREG kan ikke hentes.")
        try:
            import reskontro_brreg_panel
            reskontro_brreg_panel.update_brreg_panel(page, "")
        except Exception:
            pass
        return

    if not force_refresh and orgnr in page._brreg_data:
        page.var_brreg_status.set("Vist fra cache.")
        try:
            import reskontro_brreg_panel
            reskontro_brreg_panel.update_brreg_panel(page, orgnr)
        except Exception:
            pass
        return

    if orgnr in page._brreg_loading and not force_refresh:
        page.var_brreg_status.set("Henter BRREG-data…")
        return

    page._brreg_request_id += 1
    request_id = page._brreg_request_id
    page._brreg_loading.add(orgnr)
    page.var_brreg_status.set("Henter BRREG-data…")
    use_cache = not force_refresh
    threading.Thread(
        target=page._brreg_worker,
        args=(orgnr, request_id, use_cache),
        daemon=True,
    ).start()

def brreg_worker(page, orgnr: str, request_id: int, use_cache: bool) -> None:
    enhet = None
    regnskap = None
    error: str | None = None
    try:
        import src.shared.brreg.client as brreg_client
        enhet = brreg_client.fetch_enhet(orgnr, use_cache=use_cache)
        regnskap = brreg_client.fetch_regnskap(orgnr, use_cache=use_cache)
    except Exception as exc:
        error = str(exc)
    try:
        page.after(0, page._brreg_apply_result, request_id, orgnr, enhet, regnskap, error)
    except Exception:
        pass

def brreg_apply_result(
    page,
    request_id: int,
    orgnr: str,
    enhet: dict[str, Any] | None,
    regnskap: dict[str, Any] | None,
    error: str | None,
) -> None:
    page._brreg_loading.discard(orgnr)
    if error:
        if orgnr == page._brreg_current_orgnr:
            page.var_brreg_status.set(f"Feil ved henting: {error}")
        return
    page._brreg_data[orgnr] = {"enhet": enhet or {}, "regnskap": regnskap or {}}
    if orgnr != page._brreg_current_orgnr:
        return
    if request_id != page._brreg_request_id:
        return
    page.var_brreg_status.set("Hentet fra BRREG.")
    try:
        import reskontro_brreg_panel
        reskontro_brreg_panel.update_brreg_panel(page, orgnr)
    except Exception as exc:
        page.var_brreg_status.set(f"Panel-feil: {exc}")

def on_brreg_refresh_clicked(page) -> None:
    row = page._selected_owned_row()
    if row is None:
        return
    orgnr = normalize_orgnr(_safe_text(row.get("company_orgnr")))
    if orgnr and orgnr in page._brreg_data:
        page._brreg_data.pop(orgnr, None)
    page._load_brreg_for_selected_row(row, force_refresh=True)

def update_brreg_header(page, orgnr: str, name: str) -> None:
    if not orgnr and not name:
        page.var_brreg_header.set("— velg et eid selskap —")
        return
    if orgnr and name:
        page.var_brreg_header.set(f"{name} ({orgnr})")
    elif name:
        page.var_brreg_header.set(name)
    else:
        page.var_brreg_header.set(orgnr)

