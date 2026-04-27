"""workpaper_export_klientinfo.py — Eksport av klientinfo/roller/eierskap-arbeidspapir.

Henter BRREG-enhet + roller og eierskapsdata via `ar_store`, bygger Excel
via `workpaper_klientinfo.build_klientinfo_workpaper` og viser Lagre som…
"""

from __future__ import annotations

import logging

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
        safe = "".join(
            ch if ch.isalnum() or ch in {" ", "_", "-"} else "_"
            for ch in str(client)
        ).strip()
        if safe:
            base += f" {safe}"
    if year:
        base += f" {year}"
    return base


def export_klientinfo_workpaper(page) -> None:
    if filedialog is None:
        return

    import src.pages.ar.backend.store as ar_store
    import src.shared.brreg.client as brreg_client
    import src.shared.workpapers.klientinfo as workpaper_klientinfo

    client = getattr(session, "client", None) or ""
    year = str(getattr(session, "year", None) or "")
    if not client:
        if messagebox is not None:
            try:
                messagebox.showinfo("Klientinfo", "Ingen aktiv klient.")
            except Exception:
                pass
        return

    client_orgnr = ""
    try:
        client_orgnr = ar_store.get_client_orgnr(client) or ""
    except Exception:
        client_orgnr = ""

    if not client_orgnr:
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "Klientinfo",
                    "Klienten har ikke registrert orgnr. Sett orgnr i klient-oppsett først.",
                )
            except Exception:
                pass
        return

    # BRREG — tåler at kall feiler (offline, ugyldig orgnr)
    enhet: dict = {}
    roller: list[dict] = []
    try:
        enhet = brreg_client.fetch_enhet(client_orgnr) or {}
    except Exception:
        log.debug("fetch_enhet feilet for %s", client_orgnr, exc_info=True)
    try:
        roller = brreg_client.fetch_roller(client_orgnr) or []
    except Exception:
        log.debug("fetch_roller feilet for %s", client_orgnr, exc_info=True)

    # Eierskapsdata fra aksjonærregisteret
    owners: list[dict] = []
    owned_companies: list[dict] = []
    owners_year_used = ""
    try:
        overview = ar_store.get_client_ownership_overview(client, year) or {}
        owners = list(overview.get("owners") or [])
        owned_companies = list(overview.get("owned_companies") or [])
        owners_year_used = str(overview.get("owners_year_used") or "")
    except Exception:
        log.debug("get_client_ownership_overview feilet", exc_info=True)

    # Indirekte eierskap: slå opp eiere av selskaps-aksjonærer i samme
    # register-år som klientens eiere ble hentet fra (fallback til year).
    lookup_year = owners_year_used or year

    def _indirect_owners(orgnr: str) -> list[dict]:
        try:
            rows = list(ar_store.list_company_owners(orgnr, lookup_year) or [])
        except Exception:
            log.warning(
                "list_company_owners feilet for %s/%s", orgnr, lookup_year, exc_info=True,
            )
            return []
        if not rows:
            log.info(
                "Indirekte eierskap: ingen treff for orgnr=%s i AR-året %s "
                "— kjeden brytes her (ikke importert?).",
                orgnr, lookup_year,
            )
        return rows

    def _indirect_owners_with_fallback(orgnr: str) -> list[dict]:
        try:
            rows = list(ar_store.list_company_owners(orgnr, lookup_year) or [])
        except Exception:
            log.warning(
                "list_company_owners feilet for %s/%s",
                orgnr, lookup_year, exc_info=True,
            )
            rows = []
        if rows:
            return rows

        fallback = getattr(ar_store, "list_company_owners_with_fallback", None)
        if fallback is None:
            return []
        try:
            used_year, fallback_rows = fallback(orgnr, lookup_year)
            rows = list(fallback_rows or [])
        except Exception:
            log.warning(
                "list_company_owners_with_fallback feilet for %s/%s",
                orgnr, lookup_year, exc_info=True,
            )
            return []
        if rows:
            log.info(
                "Indirekte eierskap: bruker AR-året %s for orgnr=%s "
                "(siste tilgjengelige <= %s).",
                used_year, orgnr, lookup_year,
            )
        return rows

    wb = workpaper_klientinfo.build_klientinfo_workpaper(
        client=client,
        year=year,
        client_orgnr=client_orgnr,
        enhet=enhet,
        roller=roller,
        owners=owners,
        owned_companies=owned_companies,
        owners_year_used=owners_year_used,
        indirect_owners_fn=_indirect_owners_with_fallback,
    )

    base_name = _safe_base_name("Klientinfo", client, year)

    try:
        path = filedialog.asksaveasfilename(
            parent=page,
            title="Eksporter klientinfo-arbeidspapir",
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
        wb.save(path)
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror(
                    "Klientinfo",
                    f"Kunne ikke lagre arbeidsboken.\n\n{exc}",
                )
            except Exception:
                pass
        return

    if messagebox is not None:
        try:
            messagebox.showinfo(
                "Klientinfo",
                f"Arbeidspapiret ble lagret:\n{path}",
            )
        except Exception:
            pass
