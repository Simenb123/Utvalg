"""reskontro_brreg_panel.py -- BRREG-panel rendering for reskontro.

Ekstrahert fra page_reskontro.py.
Alle funksjoner tar ``page`` som første parameter (ReskontroPage-instansen).
"""
from __future__ import annotations

from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from ..backend.brreg_helpers import (
    _brreg_status_text,
    _brreg_has_risk,
    _fmt_nok,
    _compute_nokkeltall,
)


def build_brreg_panel(page: Any, parent: Any = None) -> None:
    """Bygg tk.Text-basert BRREG-panel med farge-tags.

    Hvis ``parent`` er gitt, brukes det som container; ellers faller vi
    tilbake til ``page._brreg_frame`` av hensyn til eldre kallesteder.
    """
    f = parent if parent is not None else page._brreg_frame
    try:
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
    except Exception:
        pass

    page._brreg_text = tk.Text(
        f, state="disabled", wrap="word",
        font=("TkDefaultFont", 9),
        relief="flat", borderwidth=0,
        height=8, cursor="arrow",
    )
    vsb = ttk.Scrollbar(f, orient="vertical", command=page._brreg_text.yview)
    page._brreg_text.configure(yscrollcommand=vsb.set)
    page._brreg_text.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    # Tags
    page._brreg_text.tag_configure("heading",  font=("TkDefaultFont", 9, "bold"), foreground="#1a4c7a")
    page._brreg_text.tag_configure("key",      foreground="#555555")
    page._brreg_text.tag_configure("val",      foreground="#111111")
    page._brreg_text.tag_configure("warn",     foreground="#C75000")
    page._brreg_text.tag_configure("ok",       foreground="#1a7a2a")
    page._brreg_text.tag_configure("bad",      foreground="#C75000")
    page._brreg_text.tag_configure("dim",      foreground="#888888")

    clear_brreg_panel(page)


def brreg_write(page: Any, *parts: tuple[str, str]) -> None:
    """Hjelpemetode: sett inn (tekst, tag)-par i _brreg_text."""
    t = page._brreg_text
    t.configure(state="normal")
    for text, tag in parts:
        t.insert("end", text, tag)
    t.configure(state="disabled")


def clear_brreg_panel(page: Any) -> None:
    t = page._brreg_text
    t.configure(state="normal")
    t.delete("1.0", "end")
    t.configure(state="disabled")
    brreg_write(
        page,
        ("— kjør BRREG-sjekk for å hente data —", "dim"),
    )


def update_brreg_panel(page: Any, orgnr: str) -> None:
    """Fyll BRREG-panelet med data for valgt orgnr."""
    t = page._brreg_text
    t.configure(state="normal")
    t.delete("1.0", "end")
    t.configure(state="disabled")

    def w(*parts: tuple[str, str]) -> None:
        brreg_write(page, *parts)

    def kv(key: str, val: str, val_tag: str = "val") -> None:
        w((f"  {key}: ", "key"), (val + "\n", val_tag))

    if not orgnr or orgnr not in page._brreg_data:
        msg = "Ikke hentet — trykk BRREG-sjekk" if orgnr else "— velg en post —"
        w((msg, "dim"))
        return

    rec    = page._brreg_data[orgnr]
    enhet  = rec.get("enhet") or {}
    regnsk = rec.get("regnskap") or {}

    # --- Firmainformasjon ---
    w(("Firmainformasjon\n", "heading"))
    kv("Orgnr", orgnr)

    if not enhet:
        kv("Status", "Ikke funnet i Enhetsregisteret", "bad")
        return

    try:
        import src.shared.brreg.client as _brreg
        exempt = _brreg.is_likely_exempt(enhet.get("naeringskode", ""))
    except Exception:
        exempt = False

    status_txt = _brreg_status_text(enhet)
    status_tag = "bad" if any(
        enhet.get(k) for k in ("konkurs", "underAvvikling", "underTvangsavvikling")
    ) else "ok"
    kv("Status", status_txt, status_tag)

    mva_reg = enhet.get("registrertIMvaregisteret", False)
    mva_txt = "✓ Ja" if mva_reg else "✗ Nei"
    kv("MVA-registrert", mva_txt, "ok" if mva_reg else "bad")
    kv("Org.form", enhet.get("organisasjonsform", "") or "—")
    kv("Adresse", enhet.get("forretningsadresse", "") or "—")

    nk = enhet.get("naeringskode", "")
    nn = enhet.get("naeringsnavn", "")
    bransje_txt = f"{nk} {nn}".strip() if nk else nn
    kv("Bransje", bransje_txt or "—")
    if exempt:
        w(("  ⚠ Bransjen er typisk unntatt MVA\n", "warn"))

    if not regnsk:
        w(("\nRegnskap\n", "heading"))
        w(("  Ikke tilgjengelig\n", "dim"))
        return

    # --- Resultatregnskap ---
    valuta  = regnsk.get("valuta", "NOK")
    fra     = regnsk.get("fra_dato", "")[:10]
    til     = regnsk.get("til_dato", "")[:10]
    aar     = regnsk.get("regnskapsaar", "")
    periode = f"{fra} – {til}" if fra and til else aar
    w((f"\nResultatregnskap {aar}  ({valuta}  {periode})\n", "heading"))

    def _r(key: str, label: str, val_tag: str = "val") -> None:
        v = regnsk.get(key)
        kv(label, _fmt_nok(v) if v is not None else "—", val_tag)

    _r("driftsinntekter",    "Driftsinntekter")
    _r("driftskostnader",    "Driftskostnader")
    _r("driftsresultat",     "Driftsresultat")
    w(("  —\n", "dim"))
    _r("finansinntekter",    "Finansinntekter")
    _r("finanskostnader",    "Finanskostnader")
    _r("netto_finans",       "Netto finans")
    w(("  —\n", "dim"))
    _r("resultat_for_skatt", "Res. før skatt")

    aarsres_v = regnsk.get("aarsresultat")
    driftsinnt_v = regnsk.get("driftsinntekter")
    aarsres_tag = "val"
    if aarsres_v is not None and aarsres_v < 0:
        aarsres_tag = "bad"
    _r("aarsresultat", "Årsresultat", aarsres_tag)

    rev_txt = regnsk.get("revisorberetning", "")
    if regnsk.get("ikke_revidert") or regnsk.get("fravalg_revisjon"):
        kv("Revisjon", rev_txt, "warn")
    else:
        kv("Revisjon", rev_txt, "ok")

    # --- Balanse ---
    w((f"\nBalanse ({aar})\n", "heading"))
    _r("sum_anleggsmidler",  "Anleggsmidler")
    _r("sum_omloepsmidler",  "Omløpsmidler")
    _r("sum_eiendeler",      "Sum eiendeler")
    w(("  —\n", "dim"))

    ek_v = regnsk.get("sum_egenkapital")
    ek_tag = "bad" if (ek_v is not None and ek_v < 0) else "val"
    _r("sum_egenkapital",    "Egenkapital", ek_tag)
    w(("  —\n", "dim"))
    _r("langsiktig_gjeld",   "Langsiktig gjeld")
    _r("kortsiktig_gjeld",   "Kortsiktig gjeld")
    _r("sum_gjeld",          "Sum gjeld")

    # --- Nøkkeltall ---
    nokkeltall = _compute_nokkeltall(regnsk)
    if nokkeltall:
        w(("\nNøkkeltall\n", "heading"))
        risk_map = {"ok": "ok", "warn": "warn", "bad": "bad"}
        for label, verdi, risiko in nokkeltall:
            tag = risk_map.get(risiko, "val")
            kv(label, verdi, tag)

    # --- Risikovurdering (kun kunder med åpen saldo) ---
    has_ub = False
    try:
        if page._master_df is not None and "nr" in page._master_df.columns:
            sel_nr = page._selected_nr
            if sel_nr:
                row_m = page._master_df[page._master_df["nr"].astype(str) == sel_nr]
                if not row_m.empty:
                    ub_val = float(row_m["ub"].iloc[0])
                    has_ub = abs(ub_val) > 0.01
    except Exception:
        pass

    if has_ub and page._mode == "kunder":
        w(("\nRisikovurdering — tapsavsetning\n", "heading"))
        if _brreg_has_risk(enhet):
            w(("  ⚠ Konkurs/avvikling — vurder 100 % avsetning\n", "bad"))
        else:
            risk_signals = []
            if ek_v is not None and ek_v < 0:
                risk_signals.append("Negativ egenkapital")
            omloep_v = regnsk.get("sum_omloepsmidler")
            kgj_v    = regnsk.get("kortsiktig_gjeld")
            if omloep_v is not None and kgj_v and kgj_v != 0:
                lg1 = omloep_v / kgj_v
                if lg1 < 1.0:
                    risk_signals.append(f"Likviditetsgrad {lg1:.2f} < 1,0")
            if aarsres_v is not None and aarsres_v < 0:
                risk_signals.append("Negativt årsresultat")
            if risk_signals:
                w(("  ⚠ Risikosignaler:\n", "warn"))
                for s in risk_signals:
                    w((f"    • {s}\n", "warn"))
            else:
                w(("  ✓ Ingen umiddelbare risikosignaler\n", "ok"))
