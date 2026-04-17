"""reskontro_brreg_helpers.py -- BRREG-hjelpefunksjoner.

Ekstrahert fra page_reskontro.py.  Rene beregningsfunksjoner uten GUI-kobling.
"""
from __future__ import annotations

import formatting


def _brreg_status_text(enhet: dict) -> str:
    """Kort statustekst for master-listen."""
    flags = []
    if enhet.get("slettedato"):
        flags.append("Slettet")
    if enhet.get("konkurs"):
        flags.append("Konkurs")
    if enhet.get("underTvangsavvikling"):
        flags.append("Tvangsavvikling")
    if enhet.get("underAvvikling"):
        flags.append("Avvikling")
    return "  ".join(f"\u26a0 {f}" for f in flags) if flags else "\u2713 Aktiv"


def _brreg_has_risk(enhet: dict) -> bool:
    return any(enhet.get(k) for k in (
        "konkurs", "underAvvikling", "underTvangsavvikling")) or bool(
        enhet.get("slettedato"))


def _fmt_nok(val: float | None, decimals: int = 0) -> str:
    """Formater regnskapstall. Standard uten desimaler (heltall)."""
    if val is None:
        return "\u2014"
    return formatting.fmt_amount(val, decimals)


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "\u2014"
    return f"{val:.1f} %"


def _compute_nokkeltall(regnsk: dict) -> list[tuple[str, str, str]]:
    """Beregn nokkeltall fra regnskapstall.

    Returnerer liste av (label, verdi_str, risiko_tag) der risiko_tag er
    "ok", "warn" eller "bad".
    """
    rows: list[tuple[str, str, str]] = []
    if not regnsk:
        return rows

    def _g(k: str) -> float | None:
        v = regnsk.get(k)
        return float(v) if v is not None else None

    omloep     = _g("sum_omloepsmidler")
    kgj        = _g("kortsiktig_gjeld")
    ek         = _g("sum_egenkapital")
    eiendeler  = _g("sum_eiendeler")
    aarsres    = _g("aarsresultat")
    driftsinnt = _g("driftsinntekter")
    sum_gjeld  = _g("sum_gjeld")

    # Likviditetsgrad 1 (current ratio)
    if omloep is not None and kgj and kgj != 0:
        lg1 = omloep / kgj
        tag = "ok" if lg1 >= 1.5 else ("warn" if lg1 >= 1.0 else "bad")
        rows.append(("Likviditetsgrad 1", f"{lg1:.2f}", tag))

    # Arbeidskapital
    if omloep is not None and kgj is not None:
        ak = omloep - kgj
        tag = "ok" if ak >= 0 else "bad"
        rows.append(("Arbeidskapital", _fmt_nok(ak), tag))

    # Egenkapitalandel
    if ek is not None and eiendeler and eiendeler != 0:
        eka = ek / eiendeler * 100
        tag = "ok" if eka >= 30 else ("warn" if eka >= 10 else "bad")
        rows.append(("Egenkapitalandel", _fmt_pct(eka), tag))
    elif ek is not None and ek < 0:
        rows.append(("Egenkapital", "\u26a0 Negativ", "bad"))

    # Gjeldsgrad
    if ek is not None and ek > 0 and sum_gjeld is not None:
        gg = sum_gjeld / ek
        tag = "ok" if gg <= 3 else ("warn" if gg <= 5 else "bad")
        rows.append(("Gjeldsgrad", f"{gg:.2f}", tag))

    # Resultatmargin
    if aarsres is not None and driftsinnt and driftsinnt != 0:
        margin = aarsres / driftsinnt * 100
        tag = "ok" if margin >= 5 else ("warn" if margin >= 0 else "bad")
        rows.append(("Resultatmargin", _fmt_pct(margin), tag))
    elif aarsres is not None and aarsres < 0:
        rows.append(("\u00c5rsresultat", "\u26a0 Negativt resultat", "bad"))

    return rows
