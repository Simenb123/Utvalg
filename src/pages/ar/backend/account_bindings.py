"""Reverse-mapping fra eid selskap (orgnr) → SB-kontoer.

Brukes av AR-fanens «Eide selskaper»-tre for å vise hvilke
SB-kontoer som er bundet til hvert eid selskap (kolonnen
«Bokført på»).

Bindingen settes på SB-siden via ``AccountProfile.owned_company_orgnr``
(felt på account_profile.AccountProfile). Dette modulet gjør oppslaget
andre vei: gitt en klient og et år, returner en dict
``{orgnr_digits: [(account_no, account_name), ...]}``.
"""

from __future__ import annotations

from typing import Any


def _digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def account_bindings_for_owned(
    client: str | None,
    year: int | None,
    *,
    load_document: Any = None,
) -> dict[str, list[tuple[str, str]]]:
    """Returner orgnr → [(account_no, account_name), ...] for klient/år.

    Tom dict hvis klient eller år mangler, eller hvis profil-dokumentet
    ikke kan lastes. Bare profiler med ``owned_company_orgnr`` satt
    inkluderes.

    ``load_document`` (valgfri) kan injiseres for testing slik at
    helperen ikke trenger å importere ``konto_klassifisering`` direkte.
    """
    if not client or not year:
        return {}
    if load_document is None:
        try:
            import konto_klassifisering as _kk
            load_document = _kk.load_document
        except Exception:
            return {}
    try:
        document = load_document(str(client), year=int(year))
    except Exception:
        return {}
    if document is None:
        return {}
    profiles = getattr(document, "profiles", None) or {}

    out: dict[str, list[tuple[str, str]]] = {}
    for account_no, profile in profiles.items():
        orgnr_raw = getattr(profile, "owned_company_orgnr", None)
        digits = _digits_only(orgnr_raw)
        if not digits:
            continue
        name = str(getattr(profile, "account_name", "") or "")
        out.setdefault(digits, []).append((str(account_no), name))

    # Sorter kontoer per orgnr (laveste nr først)
    for digits in out:
        out[digits].sort(key=lambda pair: pair[0])
    return out


def format_account_binding(
    company_orgnr: object,
    bindings: dict[str, list[tuple[str, str]]],
    *,
    empty: str = "—",
) -> str:
    """Format «Bokført på»-cellen for én rad.

    - Returnerer ``empty`` (default «—») når ingen binding finnes.
    - Returnerer ``"1321"`` når én konto er bundet.
    - Returnerer ``"1321, 1322 (+ 1)"`` når 3+ kontoer er bundet —
      truncates for å holde cellen lesbar.
    """
    digits = _digits_only(company_orgnr)
    if not digits:
        return empty
    rows = bindings.get(digits)
    if not rows:
        return empty
    if len(rows) == 1:
        return rows[0][0]
    if len(rows) == 2:
        return f"{rows[0][0]}, {rows[1][0]}"
    return f"{rows[0][0]}, {rows[1][0]} (+ {len(rows) - 2})"
