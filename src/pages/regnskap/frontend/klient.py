"""regnskap_klient.py -- Klientoversikt og roller/signatarer.

Ekstrahert fra page_regnskap.py.  Hver funksjon tar ``page`` (RegnskapPage-instans)
som forste argument.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import preferences


def build_klient_tab(page: Any, parent: Any) -> None:
    """Bygg Klientoversikt: orgnr, roller, eksportvalg."""
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)

    canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0)
    vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    inner = ttk.Frame(canvas, padding=(16, 12, 16, 16))
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_cfg(_e: Any) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_cfg(e: Any) -> None:
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_inner_cfg)
    canvas.bind("<Configure>", _on_canvas_cfg)

    def _scroll(event: Any) -> None:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _scroll))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner.columnconfigure(1, weight=1)
    row = 0

    # --- Seksjon: Foretaksinfo ---
    hdr = ttk.Label(inner, text="Foretaksinfo",
                    font=("TkDefaultFont", 11, "bold"), foreground="#1A2E5A")
    hdr.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
    row += 1

    ttk.Label(inner, text="Organisasjonsnr:").grid(row=row, column=0, sticky="w", pady=2)
    page._kl_orgnr_var = tk.StringVar()
    orgnr_entry = ttk.Entry(inner, textvariable=page._kl_orgnr_var, width=16)
    orgnr_entry.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)
    ttk.Button(inner, text="Hent fra Brreg",
               command=page._fetch_brreg_roles, width=14).grid(
        row=row, column=2, sticky="w", padx=(8, 0), pady=2)
    row += 1

    ttk.Label(inner, text="Klientnavn:").grid(row=row, column=0, sticky="w", pady=2)
    page._kl_name_var = tk.StringVar()
    ttk.Entry(inner, textvariable=page._kl_name_var, width=40).grid(
        row=row, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=2)
    row += 1

    ttk.Label(inner, text="Org.form:").grid(row=row, column=0, sticky="w", pady=2)
    page._kl_orgform_var = tk.StringVar()
    ttk.Entry(inner, textvariable=page._kl_orgform_var, width=30).grid(
        row=row, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=2)
    row += 1

    ttk.Label(inner, text="Adresse:").grid(row=row, column=0, sticky="w", pady=2)
    page._kl_adresse_var = tk.StringVar()
    ttk.Entry(inner, textvariable=page._kl_adresse_var, width=50).grid(
        row=row, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=2)
    row += 1

    sep1 = ttk.Separator(inner, orient="horizontal")
    sep1.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1

    # --- Seksjon: Roller (signaturfelt) ---
    hdr2 = ttk.Label(inner, text="Roller / signaturfelt",
                     font=("TkDefaultFont", 11, "bold"), foreground="#1A2E5A")
    hdr2.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
    row += 1

    ttk.Label(inner, text="Hentes automatisk fra Brreg, eller legg inn manuelt.",
              foreground="#888888").grid(row=row, column=0, columnspan=3, sticky="w")
    row += 1

    # Roller treeview
    role_frame = ttk.Frame(inner)
    role_frame.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(4, 2))
    inner.rowconfigure(row, weight=1)
    role_frame.rowconfigure(0, weight=1)
    role_frame.columnconfigure(0, weight=1)

    page._role_tree = ttk.Treeview(
        role_frame,
        columns=("rolle", "navn", "signerer"),
        show="headings",
        selectmode="browse",
        height=8,
    )
    page._role_tree.heading("rolle",    text="Rolle",    anchor="w")
    page._role_tree.heading("navn",     text="Navn",     anchor="w")
    page._role_tree.heading("signerer", text="Signerer", anchor="center")
    page._role_tree.column("rolle",    width=160, anchor="w", stretch=False)
    page._role_tree.column("navn",     width=280, anchor="w", stretch=True)
    page._role_tree.column("signerer", width=80,  anchor="center", stretch=False)

    rsb = ttk.Scrollbar(role_frame, orient="vertical", command=page._role_tree.yview)
    page._role_tree.configure(yscrollcommand=rsb.set)
    page._role_tree.grid(row=0, column=0, sticky="nsew")
    rsb.grid(row=0, column=1, sticky="ns")

    # Toggle signerer on double-click
    page._role_tree.bind("<Double-Button-1>", page._toggle_role_signerer)

    row += 1

    role_btn_bar = ttk.Frame(inner)
    role_btn_bar.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 4))
    ttk.Button(role_btn_bar, text="Legg til rolle",
               command=page._add_role_manual, width=14).pack(side="left", padx=2)
    ttk.Button(role_btn_bar, text="Fjern valgt",
               command=page._remove_selected_role, width=12).pack(side="left", padx=2)
    ttk.Label(role_btn_bar,
              text="  Dobbeltklikk for \u00e5 endre \u00abSignerer\u00bb-status.",
              foreground="#888888").pack(side="left", padx=6)
    row += 1

    sep2 = ttk.Separator(inner, orient="horizontal")
    sep2.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1

    # --- Seksjon: Eksportvalg ---
    hdr3 = ttk.Label(inner, text="Eksportvalg",
                     font=("TkDefaultFont", 11, "bold"), foreground="#1A2E5A")
    hdr3.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
    row += 1

    page._inkl_cf_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(inner, text="Inkluder kontantstr\u00f8m",
                    variable=page._inkl_cf_var).grid(
        row=row, column=0, columnspan=2, sticky="w", pady=2)
    row += 1

    page._inkl_signatur_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(inner, text="Inkluder signaturfelt i eksport",
                    variable=page._inkl_signatur_var).grid(
        row=row, column=0, columnspan=2, sticky="w", pady=2)
    row += 1

    sep3 = ttk.Separator(inner, orient="horizontal")
    sep3.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1

    ttk.Button(inner, text="Lagre klientdata",
               command=page._save_klient_data, width=16).grid(
        row=row, column=0, sticky="w", pady=4)
    ttk.Label(inner, text="Lagres per klient.",
              foreground="#888888").grid(row=row, column=1, sticky="w", padx=(8, 0))
    row += 1

    ttk.Button(inner, text="Berik klientdata\u2026",
               command=page._start_enrichment, width=18).grid(
        row=row, column=0, sticky="w", pady=4)
    ttk.Label(inner, text="Importer orgnr/Knr fra Visena-fil",
              foreground="#888888").grid(row=row, column=1, sticky="w", padx=(8, 0))


# ------------------------------------------------------------------
# Klientoversikt -- datalogikk
# ------------------------------------------------------------------

def fetch_brreg_roles(page: Any) -> None:
    """Hent roller og foretaksinfo fra Brreg basert pa orgnr."""
    orgnr = page._kl_orgnr_var.get().strip().replace(" ", "")
    if not orgnr or len(orgnr) != 9 or not orgnr.isdigit():
        messagebox.showwarning("Ugyldig orgnr",
                               "Skriv inn et gyldig 9-sifret organisasjonsnummer.",
                               parent=page)
        return

    page._set_status("Henter fra Brreg\u2026")
    try:
        page.update_idletasks()
    except Exception:
        pass

    try:
        import brreg_client
        # Enhetsinfo
        enhet = brreg_client.fetch_enhet(orgnr)
        if enhet:
            page._kl_name_var.set(enhet.get("navn", ""))
            page._kl_orgform_var.set(enhet.get("organisasjonsform", ""))
            page._kl_adresse_var.set(enhet.get("forretningsadresse", ""))

        # Roller
        roller = brreg_client.fetch_roller(orgnr)
        if roller:
            page._role_tree.delete(*page._role_tree.get_children())
            for r in roller:
                sign_default = r["rolle_kode"] in ("DAGL", "LEDE", "MEDL")
                page._role_tree.insert("", "end", values=(
                    r["rolle"],
                    r["navn"],
                    "Ja" if sign_default else "",
                ))
            page._set_status(f"Hentet {len(roller)} roller fra Brreg")
        else:
            page._set_status("Ingen roller funnet i Brreg")

        # Auto-lagre slik at data er tilgjengelig neste gang
        page._save_klient_data()

    except Exception as exc:
        log.warning("Brreg fetch failed: %s", exc)
        messagebox.showerror("Brreg-feil",
                             f"Kunne ikke hente fra Brreg:\n{exc}",
                             parent=page)
        page._set_status("Brreg-henting feilet")


def toggle_role_signerer(page: Any, event: Any = None) -> None:
    sel = page._role_tree.selection()
    if not sel:
        return
    item = sel[0]
    vals = list(page._role_tree.item(item, "values"))
    if len(vals) >= 3:
        vals[2] = "" if vals[2] == "Ja" else "Ja"
        page._role_tree.item(item, values=vals)


def add_role_manual(page: Any) -> None:
    dlg = tk.Toplevel(page)
    dlg.title("Legg til rolle")
    dlg.geometry("340x160")
    dlg.transient(page)
    dlg.grab_set()

    ttk.Label(dlg, text="Rolle:").grid(row=0, column=0, padx=12, pady=(12, 2), sticky="w")
    rolle_var = tk.StringVar(value="Styremedlem")
    ttk.Combobox(dlg, textvariable=rolle_var,
                 values=["Daglig leder", "Styreleder", "Nestleder",
                         "Styremedlem", "Varamedlem", "Revisor",
                         "Regnskapsfører", "Annen"],
                 width=24).grid(row=0, column=1, padx=4, pady=(12, 2))

    ttk.Label(dlg, text="Navn:").grid(row=1, column=0, padx=12, pady=2, sticky="w")
    navn_var = tk.StringVar()
    ttk.Entry(dlg, textvariable=navn_var, width=28).grid(
        row=1, column=1, padx=4, pady=2)

    def _ok(*_: Any) -> None:
        name = navn_var.get().strip()
        rolle = rolle_var.get().strip()
        if not name or not rolle:
            return
        sign = rolle in ("Daglig leder", "Styreleder", "Styremedlem")
        page._role_tree.insert("", "end", values=(rolle, name, "Ja" if sign else ""))
        dlg.destroy()

    ttk.Button(dlg, text="Legg til", command=_ok, width=10).grid(
        row=2, column=0, columnspan=2, pady=12)


def remove_selected_role(page: Any) -> None:
    sel = page._role_tree.selection()
    if sel:
        page._role_tree.delete(sel[0])


def start_enrichment(page: Any) -> None:
    """Apne berikelsesflyt (Visena XLSX -> preview -> apply)."""
    import client_store_enrich_ui
    client_store_enrich_ui.start_enrichment_flow(page, on_done=lambda _: page._load_klient_data())


def save_klient_data(page: Any) -> None:
    """Lagre klientdata til preferences + meta.json."""
    data = {
        "orgnr": page._kl_orgnr_var.get().strip(),
        "navn": page._kl_name_var.get().strip(),
        "orgform": page._kl_orgform_var.get().strip(),
        "adresse": page._kl_adresse_var.get().strip(),
        "inkl_cf": page._inkl_cf_var.get(),
        "inkl_signatur": page._inkl_signatur_var.get(),
        "roller": [],
    }
    for item in page._role_tree.get_children():
        vals = page._role_tree.item(item, "values")
        data["roller"].append({
            "rolle": str(vals[0]) if vals else "",
            "navn": str(vals[1]) if len(vals) > 1 else "",
            "signerer": str(vals[2]) == "Ja" if len(vals) > 2 else False,
        })
    preferences.set(page._pref_key("__meta__", "klientdata"), json.dumps(data, ensure_ascii=False))

    # Skriv orgnr tilbake til meta.json
    orgnr = data["orgnr"]
    if orgnr:
        try:
            import src.shared.client_store.store as client_store
            dn = page._client
            if dn:
                client_store.update_client_meta(dn, {"org_number": orgnr})
        except Exception:
            pass

    page._set_status("Klientdata lagret")


def load_klient_data(page: Any) -> None:
    """Last inn klientdata fra preferences, auto-populate orgnr fra meta.json."""
    raw = preferences.get(page._pref_key("__meta__", "klientdata"))
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

    page._kl_orgnr_var.set(data.get("orgnr", ""))
    page._kl_name_var.set(data.get("navn", ""))
    page._kl_orgform_var.set(data.get("orgform", ""))
    page._kl_adresse_var.set(data.get("adresse", ""))
    page._inkl_cf_var.set(data.get("inkl_cf", True))
    page._inkl_signatur_var.set(data.get("inkl_signatur", True))

    page._role_tree.delete(*page._role_tree.get_children())
    for r in data.get("roller", []):
        page._role_tree.insert("", "end", values=(
            r.get("rolle", ""),
            r.get("navn", ""),
            "Ja" if r.get("signerer") else "",
        ))

    # Auto-populate orgnr fra meta.json hvis feltet er tomt
    if not page._kl_orgnr_var.get().strip():
        try:
            import src.shared.client_store.store as client_store
            dn = page._client
            if dn:
                meta = client_store.read_client_meta(dn)
                org = meta.get("org_number", "")
                if org:
                    page._kl_orgnr_var.set(org)
        except Exception:
            pass

    # Auto-hent fra Brreg hvis roller er tomme men orgnr finnes
    orgnr = page._kl_orgnr_var.get().strip().replace(" ", "")
    has_roles = bool(page._role_tree.get_children())
    if orgnr and len(orgnr) == 9 and orgnr.isdigit() and not has_roles:
        try:
            page.after(100, page._fetch_brreg_roles)
        except Exception:
            pass


def get_signatories(page: Any) -> list[dict[str, str]]:
    """Returner liste over personer som skal signere."""
    result: list[dict[str, str]] = []
    for item in page._role_tree.get_children():
        vals = page._role_tree.item(item, "values")
        if len(vals) >= 3 and str(vals[2]) == "Ja":
            result.append({"rolle": str(vals[0]), "navn": str(vals[1])})
    return result
